"""
任务分发器智能体 - 负责动态调度和并行执行Task DAG
"""

import logging
import asyncio
import time
from typing import Dict, List, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, Future
from langchain_core.language_models import BaseChatModel
from app.core.state import IsotopeSystemState, StateManager
from app.agents.registry import AgentProtocol, agent_registry

logger = logging.getLogger(__name__)

class TaskDispatcher(AgentProtocol):
    """任务分发器 - 基于Task DAG进行动态智能体调度和并行执行"""
    
    def __init__(self, llm: Optional[BaseChatModel] = None, config: Optional[Dict[str, Any]] = None, memory_integration: Optional[Any] = None, info_hub: Optional[Any] = None):
        self.llm = llm
        self.config = config or {}
        self.name = "task_dispatcher"
        self.description = "任务分发器，负责根据Task DAG动态调度专业智能体并行执行"
        
        # 增强功能模块
        self.memory_integration = memory_integration
        self.info_hub = info_hub
        
        # 并发控制
        self.max_parallel_tasks = self.config.get("max_parallel_tasks", 3)
        self.task_timeout = self.config.get("task_timeout", 300)  # 5分钟超时
        
        # 执行状态跟踪
        self.active_futures = {}
        self.completed_tasks = {}
        self.failed_tasks = {}
        
        # 线程池执行器
        self.executor = ThreadPoolExecutor(max_workers=self.max_parallel_tasks)
    
    def run(self, state: IsotopeSystemState) -> IsotopeSystemState:
        """执行任务分发和调度"""
        logger.info("TaskDispatcher开始任务分发")
        
        try:
            # 获取任务计划
            task_plan = state.get("metadata", {}).get("task_plan", {})
            if not task_plan:
                raise ValueError("TaskDispatcher需要任务计划")
            
            # 获取下一步可执行的任务
            executable_steps = self._get_executable_steps(task_plan, state)
            
            if not executable_steps:
                logger.info("TaskDispatcher没有发现可执行的任务步骤")
                state["metadata"]["dispatch_status"] = "no_executable_tasks"
                return state
            
            # 执行任务分发
            dispatch_result = self._dispatch_tasks(executable_steps, state)
            
            # 更新状态
            state["metadata"]["dispatch_result"] = dispatch_result
            state["metadata"]["dispatched_by"] = self.name
            state["metadata"]["dispatch_timestamp"] = time.time()
            
            # 如果是并行执行，等待所有任务完成
            if len(executable_steps) > 1:
                logger.info(f"TaskDispatcher并行执行{len(executable_steps)}个任务")
                state = self._handle_parallel_execution(executable_steps, state)
            else:
                logger.info("TaskDispatcher执行单个任务")
                state = self._handle_single_execution(executable_steps[0], state)
            
            return state
            
        except Exception as e:
            logger.error(f"TaskDispatcher执行失败: {str(e)}")
            state["metadata"]["dispatch_error"] = str(e)
            state["metadata"]["dispatch_status"] = "failed"
            return state
    
    def get_name(self) -> str:
        return self.name
    
    def get_description(self) -> str:
        return self.description
    
    def _get_executable_steps(self, task_plan: Dict[str, Any], state: IsotopeSystemState) -> List[Dict[str, Any]]:
        """获取当前可执行的任务步骤"""
        steps = task_plan.get("steps", [])
        current_step = task_plan.get("current_step", 0)
        dependencies = task_plan.get("dependencies", {})
        parallel_groups = task_plan.get("parallel_groups", {})
        
        executable_steps = []
        completed_step_ids = set()
        
        # 获取已完成的步骤ID
        for i in range(current_step):
            if i < len(steps):
                step_id = steps[i].get("step_id", f"step_{i}")
                completed_step_ids.add(step_id)
        
        # 检查每个未执行的步骤
        for i, step in enumerate(steps):
            if i <= current_step:
                continue
            
            step_id = step.get("step_id", f"step_{i}")
            step_dependencies = dependencies.get(step_id, [])
            
            # 检查依赖是否都已完成
            dependencies_met = all(dep_id in completed_step_ids for dep_id in step_dependencies)
            
            if dependencies_met:
                executable_steps.append({**step, "step_index": i})
        
        # 处理并行组 - 同一个并行组的任务可以一起执行
        if executable_steps and parallel_groups:
            grouped_steps = self._group_parallel_steps(executable_steps, parallel_groups)
            return grouped_steps
        
        return executable_steps[:1] if executable_steps else []  # 如果没有并行组，一次只执行一个
    
    def _group_parallel_steps(self, executable_steps: List[Dict[str, Any]], parallel_groups: Dict[str, List[str]]) -> List[Dict[str, Any]]:
        """将可并行执行的步骤分组"""
        grouped_steps = []
        processed_steps = set()
        
        # 按并行组处理
        for group_name, group_step_ids in parallel_groups.items():
            group_steps = []
            for step in executable_steps:
                step_id = step.get("step_id")
                if step_id in group_step_ids and step_id not in processed_steps:
                    group_steps.append(step)
                    processed_steps.add(step_id)
            
            if group_steps:
                # 如果组内有多个步骤，标记为并行执行
                if len(group_steps) > 1:
                    for step in group_steps:
                        step["parallel_group"] = group_name
                        step["parallel_execution"] = True
                    grouped_steps.extend(group_steps)
                else:
                    grouped_steps.extend(group_steps)
                break  # 一次只处理一个并行组
        
        # 处理不在并行组中的步骤
        remaining_steps = [
            step for step in executable_steps
            if step.get("step_id") not in processed_steps
        ]
        
        if remaining_steps and not grouped_steps:
            grouped_steps = remaining_steps[:1]  # 非并行步骤一次只执行一个
        
        return grouped_steps
    
    def _dispatch_tasks(self, executable_steps: List[Dict[str, Any]], state: IsotopeSystemState) -> Dict[str, Any]:
        """分发任务到相应的智能体"""
        dispatch_result = {
            "dispatched_tasks": [],
            "failed_dispatches": [],
            "agents_used": [],
            "parallel_groups": set(),
            "dispatch_timestamp": time.time()
        }
        
        for step in executable_steps:
            try:
                # 获取目标智能体
                agent_type = step.get("agent", "general_analysis")
                agent = self._get_agent_instance(agent_type)
                
                if not agent:
                    dispatch_result["failed_dispatches"].append({
                        "step_id": step.get("step_id"),
                        "agent_type": agent_type,
                        "error": f"智能体{agent_type}不可用"
                    })
                    continue
                
                # 准备任务上下文
                task_context = {
                    "step": step,
                    "state": state,
                    "dispatch_time": time.time(),
                    "agent": agent
                }
                
                dispatch_result["dispatched_tasks"].append({
                    "step_id": step.get("step_id"),
                    "agent_type": agent_type,
                    "agent_name": agent.get_name(),
                    "parallel_group": step.get("parallel_group"),
                    "estimated_duration": step.get("estimated_duration", 60)
                })
                
                dispatch_result["agents_used"].append(agent_type)
                
                if step.get("parallel_group"):
                    dispatch_result["parallel_groups"].add(step.get("parallel_group"))
                
            except Exception as e:
                logger.error(f"分发任务{step.get('step_id')}失败: {str(e)}")
                dispatch_result["failed_dispatches"].append({
                    "step_id": step.get("step_id"),
                    "error": str(e)
                })
        
        dispatch_result["agents_used"] = list(set(dispatch_result["agents_used"]))
        dispatch_result["parallel_groups"] = list(dispatch_result["parallel_groups"])
        
        return dispatch_result
    
    def _handle_single_execution(self, step: Dict[str, Any], state: IsotopeSystemState) -> IsotopeSystemState:
        """处理单个任务执行"""
        agent_type = step.get("agent", "general_analysis")
        agent = self._get_agent_instance(agent_type)
        
        if not agent:
            logger.error(f"无法获取智能体实例: {agent_type}")
            state["metadata"]["execution_error"] = f"智能体{agent_type}不可用"
            return state
        
        try:
            logger.info(f"TaskDispatcher执行单个任务: {step.get('step_id')} -> {agent_type}")
            
            # 设置任务特定的上下文
            task_state = self._prepare_task_state(step, state)
            
            # 执行智能体
            result_state = agent.run(task_state)
            
            # 合并结果状态
            state = self._merge_task_result(state, result_state, step)
            
            # 更新任务进度
            task_plan = state.get("metadata", {}).get("task_plan", {})
            task_plan["current_step"] = step.get("step_index", 0) + 1
            
            logger.info(f"TaskDispatcher单个任务执行完成: {step.get('step_id')}")
            
        except Exception as e:
            logger.error(f"单个任务执行失败: {str(e)}")
            state["metadata"]["execution_error"] = str(e)
        
        return state
    
    def _handle_parallel_execution(self, steps: List[Dict[str, Any]], state: IsotopeSystemState) -> IsotopeSystemState:
        """处理并行任务执行"""
        logger.info(f"TaskDispatcher开始并行执行{len(steps)}个任务")
        
        # 提交所有任务到线程池
        futures = {}
        for step in steps:
            agent_type = step.get("agent", "general_analysis")
            agent = self._get_agent_instance(agent_type)
            
            if agent:
                task_state = self._prepare_task_state(step, state)
                future = self.executor.submit(self._execute_agent_task, agent, task_state, step)
                futures[step.get("step_id")] = {
                    "future": future,
                    "step": step,
                    "start_time": time.time()
                }
        
        # 等待所有任务完成
        completed_results = {}
        failed_results = {}
        
        for step_id, future_info in futures.items():
            try:
                future = future_info["future"]
                step = future_info["step"]
                start_time = future_info["start_time"]
                
                # 等待任务完成（带超时）
                result = future.result(timeout=self.task_timeout)
                
                completed_results[step_id] = {
                    "result": result,
                    "step": step,
                    "duration": time.time() - start_time
                }
                
                logger.info(f"并行任务{step_id}执行完成")
                
            except TimeoutError:
                logger.error(f"并行任务{step_id}执行超时")
                failed_results[step_id] = {
                    "error": "执行超时",
                    "step": future_info["step"]
                }
            except Exception as e:
                logger.error(f"并行任务{step_id}执行失败: {str(e)}")
                failed_results[step_id] = {
                    "error": str(e),
                    "step": future_info["step"]
                }
        
        # 合并所有结果
        state = self._merge_parallel_results(state, completed_results, failed_results)
        
        logger.info(f"TaskDispatcher并行执行完成: {len(completed_results)}成功, {len(failed_results)}失败")
        
        return state
    
    def _execute_agent_task(self, agent: AgentProtocol, task_state: IsotopeSystemState, step: Dict[str, Any]) -> IsotopeSystemState:
        """在线程中执行智能体任务"""
        try:
            logger.debug(f"执行智能体任务: {agent.get_name()} - {step.get('step_id')}")
            return agent.run(task_state)
        except Exception as e:
            logger.error(f"智能体任务执行失败: {agent.get_name()} - {str(e)}")
            # 返回包含错误信息的状态
            task_state["metadata"]["task_error"] = str(e)
            task_state["metadata"]["task_status"] = "failed"
            return task_state
    
    def _prepare_task_state(self, step: Dict[str, Any], base_state: IsotopeSystemState) -> IsotopeSystemState:
        """为特定任务准备状态上下文"""
        import copy
        task_state = copy.deepcopy(base_state)
        
        # 添加任务特定信息
        task_state["metadata"]["current_step"] = step
        task_state["metadata"]["step_id"] = step.get("step_id")
        task_state["metadata"]["task_action"] = step.get("action", "process")
        task_state["metadata"]["mcp_tools"] = step.get("mcp_tools", [])
        task_state["metadata"]["estimated_duration"] = step.get("estimated_duration", 60)
        task_state["metadata"]["requires_human"] = step.get("requires_human", False)
        
        return task_state
    
    def _merge_task_result(
        self, 
        base_state: IsotopeSystemState, 
        result_state: IsotopeSystemState, 
        step: Dict[str, Any]
    ) -> IsotopeSystemState:
        """合并单个任务的执行结果"""
        
        # 合并消息
        if "messages" in result_state:
            if "messages" not in base_state:
                base_state["messages"] = []
            base_state["messages"].extend(result_state["messages"])
        
        # 合并生成的文件
        if "files" in result_state:
            if "files" not in base_state:
                base_state["files"] = {}
            base_state["files"].update(result_state["files"])
        
        # 记录执行历史
        if "action_history" not in base_state:
            base_state["action_history"] = []
        
        base_state["action_history"].append({
            "step_id": step.get("step_id"),
            "agent": step.get("agent"),
            "action": step.get("action"),
            "status": "completed" if not result_state.get("metadata", {}).get("task_error") else "failed",
            "timestamp": time.time(),
            "duration": step.get("estimated_duration", 0)
        })
        
        return base_state
    
    def _merge_parallel_results(
        self,
        base_state: IsotopeSystemState,
        completed_results: Dict[str, Dict[str, Any]],
        failed_results: Dict[str, Dict[str, Any]]
    ) -> IsotopeSystemState:
        """合并并行任务的执行结果"""
        
        # 合并成功的结果
        for step_id, result_info in completed_results.items():
            result_state = result_info["result"]
            step = result_info["step"]
            duration = result_info["duration"]
            
            base_state = self._merge_task_result(base_state, result_state, step)
        
        # 记录失败的任务
        for step_id, error_info in failed_results.items():
            step = error_info["step"]
            error = error_info["error"]
            
            if "action_history" not in base_state:
                base_state["action_history"] = []
            
            base_state["action_history"].append({
                "step_id": step_id,
                "agent": step.get("agent"),
                "action": step.get("action"),
                "status": "failed",
                "error": error,
                "timestamp": time.time()
            })
        
        # 更新任务进度（基于最高的step_index）
        if completed_results:
            max_step_index = max(
                result_info["step"].get("step_index", 0)
                for result_info in completed_results.values()
            )
            task_plan = base_state.get("metadata", {}).get("task_plan", {})
            task_plan["current_step"] = max_step_index + 1
        
        # 记录并行执行摘要
        base_state["metadata"]["parallel_execution_summary"] = {
            "completed_tasks": len(completed_results),
            "failed_tasks": len(failed_results),
            "total_tasks": len(completed_results) + len(failed_results),
            "success_rate": len(completed_results) / (len(completed_results) + len(failed_results)) if (completed_results or failed_results) else 0
        }
        
        return base_state
    
    def _get_agent_instance(self, agent_type: str) -> Optional[AgentProtocol]:
        """获取智能体实例"""
        try:
            # 先从注册表获取
            agent = agent_registry.get(agent_type)
            if agent:
                return agent
            
            # 兼容性映射
            agent_mapping = {
                "general_analysis": "general_analysis", 
                "geophysics": "geophysics",
                "reservoir": "reservoir",
                "economics": "economics",
                "quality_control": "quality_control",
                "logging_agent": "logging",
                "seismic_agent": "seismic",
                "supervisor": "supervisor"
            }
            
            mapped_type = agent_mapping.get(agent_type, agent_type)
            return agent_registry.get(mapped_type)
            
        except Exception as e:
            logger.error(f"获取智能体实例失败: {agent_type} - {str(e)}")
            return None
    
    def __del__(self):
        """清理资源"""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)
