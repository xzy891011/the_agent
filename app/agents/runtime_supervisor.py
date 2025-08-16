"""
运行时监督者智能体 - 负责执行过程监控、中断处理和质量控制
"""

import logging
import time
from typing import Dict, List, Any, Optional
from langchain_core.language_models import BaseChatModel
from app.core.state import IsotopeSystemState, StateManager
from app.agents.registry import AgentProtocol

logger = logging.getLogger(__name__)

class RuntimeSupervisor(AgentProtocol):
    """运行时监督者 - 负责执行监控、错误恢复、人类在环控制"""
    
    def __init__(self, llm: BaseChatModel, config: Optional[Dict[str, Any]] = None, memory_integration: Optional[Any] = None, info_hub: Optional[Any] = None, interrupt_manager: Optional[Any] = None):
        self.llm = llm
        self.config = config or {}
        self.name = "runtime_supervisor"
        self.description = "运行时监督者，负责任务执行监控、异常处理和人类在环控制"
        
        # 增强功能模块
        self.memory_integration = memory_integration
        self.info_hub = info_hub
        self.interrupt_manager = interrupt_manager
        
        # 执行历史和监控状态
        self.execution_history = []
        self.active_tasks = {}
        self.error_patterns = []
        self.performance_metrics = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "average_duration": 0.0,
            "retry_rate": 0.0
        }
    
    def run(self, state: IsotopeSystemState) -> IsotopeSystemState:
        """执行运行时监控和决策"""
        logger.info("RuntimeSupervisor开始执行监控")
        
        try:
            # 获取当前任务计划
            task_plan = state.get("metadata", {}).get("task_plan", {})
            if not task_plan:
                logger.warning("RuntimeSupervisor未找到任务计划")
                return state
            
            # 监控当前执行状态
            monitoring_result = self.monitor_execution(state, task_plan)
            
            # 根据监控结果决定下一步行动
            next_action = self.decide_next_action(state, task_plan, monitoring_result)
            
            # 更新状态
            state["metadata"]["runtime_monitoring"] = monitoring_result
            state["metadata"]["next_action"] = next_action
            state["metadata"]["supervised_by"] = self.name
            
            logger.info(f"RuntimeSupervisor监控完成，下一步行动: {next_action}")
            return state
            
        except Exception as e:
            logger.error(f"RuntimeSupervisor执行失败: {str(e)}")
            # 设置安全的下一步行动
            state["metadata"]["next_action"] = "error_recovery"
            state["metadata"]["runtime_error"] = str(e)
            return state
    
    def get_name(self) -> str:
        return self.name
    
    def get_description(self) -> str:
        return self.description
    
    def monitor_execution(self, state: IsotopeSystemState, task_plan: Dict[str, Any]) -> Dict[str, Any]:
        """监控当前任务执行状态"""
        logger.info("RuntimeSupervisor监控任务执行")
        
        monitoring_result = {
            "overall_status": "healthy",
            "issues_detected": [],
            "recommendations": [],
            "performance_metrics": {},
            "should_continue": True,
            "requires_intervention": False,
            "human_approval_needed": False,
            "checkpoint_recommended": False
        }
        
        try:
            # 1. 检查任务执行时间
            task_start_time = state.get("metadata", {}).get("task_start_time")
            if task_start_time:
                elapsed_time = time.time() - task_start_time
                estimated_duration = task_plan.get("estimated_duration", 300)  # 默认5分钟
                
                if elapsed_time > estimated_duration * 1.5:
                    monitoring_result["issues_detected"].append({
                        "type": "execution_timeout",
                        "message": "任务执行时间超出预期",
                        "severity": "medium",
                        "elapsed_time": elapsed_time,
                        "expected_duration": estimated_duration
                    })
                    monitoring_result["recommendations"].append("考虑中断当前任务或申请更多执行时间")
                
                # 更新性能指标
                monitoring_result["performance_metrics"]["elapsed_time"] = elapsed_time
                monitoring_result["performance_metrics"]["progress_ratio"] = min(elapsed_time / estimated_duration, 1.0)
            
            # 2. 检查错误历史
            recent_errors = [
                action for action in state.get("action_history", [])
                if action.get("status") == "error" and 
                time.time() - action.get("timestamp", 0) < 300  # 最近5分钟的错误
            ]
            
            if len(recent_errors) > 2:
                monitoring_result["issues_detected"].append({
                    "type": "frequent_errors",
                    "message": f"检测到频繁错误({len(recent_errors)}次)",
                    "severity": "high",
                    "error_count": len(recent_errors)
                })
                monitoring_result["requires_intervention"] = True
                monitoring_result["recommendations"].append("需要人工干预，检查错误原因")
            
            # 3. 检查MCP工具可用性
            required_tools = task_plan.get("mcp_tools_required", [])
            if required_tools:
                tool_status = self._check_mcp_tool_availability(required_tools)
                unavailable_tools = [tool for tool, available in tool_status.items() if not available]
                
                if unavailable_tools:
                    monitoring_result["issues_detected"].append({
                        "type": "tool_unavailability", 
                        "message": f"MCP工具不可用: {unavailable_tools}",
                        "severity": "high",
                        "unavailable_tools": unavailable_tools
                    })
                    monitoring_result["should_continue"] = False
                    monitoring_result["recommendations"].append("等待MCP工具服务恢复")
            
            # 4. 检查人类审批要求
            if task_plan.get("requires_human_approval", False):
                human_approval_status = state.get("metadata", {}).get("human_approval_status")
                if not human_approval_status:
                    monitoring_result["human_approval_needed"] = True
                    monitoring_result["recommendations"].append("等待人类审批后继续")
                elif human_approval_status == "rejected":
                    monitoring_result["should_continue"] = False
                    monitoring_result["recommendations"].append("任务被人类拒绝，需要重新规划")
            
            # 5. 检查并行任务协调
            parallel_groups = task_plan.get("parallel_groups", {})
            if parallel_groups:
                coordination_status = self._check_parallel_coordination(state, parallel_groups)
                monitoring_result["performance_metrics"]["parallel_efficiency"] = coordination_status.get("efficiency", 1.0)
                
                if coordination_status.get("conflicts"):
                    monitoring_result["issues_detected"].append({
                        "type": "parallel_conflicts",
                        "message": "检测到并行任务冲突",
                        "severity": "medium",
                        "conflicts": coordination_status["conflicts"]
                    })
            
            # 6. 资源使用监控
            resource_usage = self._monitor_resource_usage(state)
            if resource_usage.get("memory_usage", 0) > 0.8:
                monitoring_result["issues_detected"].append({
                    "type": "high_memory_usage",
                    "message": "内存使用率过高",
                    "severity": "medium",
                    "memory_usage": resource_usage["memory_usage"]
                })
                monitoring_result["checkpoint_recommended"] = True
            
            # 7. 确定整体状态
            high_severity_issues = [
                issue for issue in monitoring_result["issues_detected"]
                if issue.get("severity") == "high"
            ]
            
            if high_severity_issues:
                monitoring_result["overall_status"] = "critical"
            elif monitoring_result["issues_detected"]:
                monitoring_result["overall_status"] = "warning"
            else:
                monitoring_result["overall_status"] = "healthy"
            
            return monitoring_result
            
        except Exception as e:
            logger.error(f"执行监控失败: {str(e)}")
            return {
                "overall_status": "error",
                "issues_detected": [{"type": "monitoring_error", "message": str(e), "severity": "high"}],
                "should_continue": False,
                "requires_intervention": True
            }
    
    def decide_next_action(
        self, 
        state: IsotopeSystemState, 
        task_plan: Dict[str, Any],
        monitoring_result: Dict[str, Any]
    ) -> str:
        """基于监控结果和当前状态决定下一步行动"""
        
        # 如果检测到严重问题，优先处理
        if monitoring_result["overall_status"] == "critical":
            if monitoring_result["requires_intervention"]:
                return "request_human_intervention"
            else:
                return "error_recovery"
        
        # 如果需要人类审批
        if monitoring_result.get("human_approval_needed", False):
            return "wait_for_human_approval"
        
        # 如果应该停止执行
        if not monitoring_result.get("should_continue", True):
            return "pause_execution"
        
        # 如果建议检查点
        if monitoring_result.get("checkpoint_recommended", False):
            return "create_checkpoint"
        
        # 检查任务完成状态
        current_step = task_plan.get("current_step", 0)
        total_steps = len(task_plan.get("steps", []))
        
        if current_step >= total_steps:
            return "task_complete"
        
        # 获取下一步可执行的步骤
        next_steps = self._get_next_executable_steps(task_plan)
        
        if not next_steps:
            return "wait_for_dependencies"
        elif len(next_steps) == 1:
            # 单个步骤，直接执行
            next_step = next_steps[0]
            return f"execute_{next_step.get('agent', 'general_analysis')}"
        else:
            # 多个并行步骤，使用任务分发器
            return "dispatch_parallel_tasks"
    
    def _check_mcp_tool_availability(self, required_tools: List[str]) -> Dict[str, bool]:
        """检查MCP工具可用性"""
        try:
            from app.tools.mcp_client_manager import mcp_client_manager
            
            tool_status = {}
            for tool_name in required_tools:
                try:
                    schema = mcp_client_manager.get_tool_schema(tool_name)
                    tool_status[tool_name] = schema is not None
                except Exception as e:
                    logger.debug(f"检查工具{tool_name}可用性失败: {str(e)}")
                    tool_status[tool_name] = False
            
            return tool_status
            
        except ImportError:
            logger.warning("MCP客户端管理器不可用")
            # 假设所有工具都可用（兼容模式）
            return {tool: True for tool in required_tools}
    
    def _check_parallel_coordination(self, state: IsotopeSystemState, parallel_groups: Dict[str, List[str]]) -> Dict[str, Any]:
        """检查并行任务协调状态"""
        coordination_status = {
            "efficiency": 1.0,
            "conflicts": [],
            "completed_groups": [],
            "active_groups": []
        }
        
        # 简化实现：检查并行组的完成状态
        for group_name, tasks in parallel_groups.items():
            completed_tasks = sum(
                1 for task in tasks
                if any(
                    action.get("task_id") == task and action.get("status") == "completed"
                    for action in state.get("action_history", [])
                )
            )
            
            if completed_tasks == len(tasks):
                coordination_status["completed_groups"].append(group_name)
            elif completed_tasks > 0:
                coordination_status["active_groups"].append(group_name)
                # 计算并行效率
                efficiency = completed_tasks / len(tasks)
                coordination_status["efficiency"] = min(coordination_status["efficiency"], efficiency)
        
        return coordination_status
    
    def _monitor_resource_usage(self, state: IsotopeSystemState) -> Dict[str, float]:
        """监控系统资源使用情况"""
        import psutil
        
        try:
            return {
                "cpu_usage": psutil.cpu_percent(interval=1) / 100.0,
                "memory_usage": psutil.virtual_memory().percent / 100.0,
                "disk_usage": psutil.disk_usage('/').percent / 100.0
            }
        except Exception as e:
            logger.debug(f"资源监控失败: {str(e)}")
            return {"cpu_usage": 0.0, "memory_usage": 0.0, "disk_usage": 0.0}
    
    def _get_next_executable_steps(self, task_plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        """获取下一步可执行的任务步骤"""
        steps = task_plan.get("steps", [])
        current_step = task_plan.get("current_step", 0)
        dependencies = task_plan.get("dependencies", {})
        
        executable_steps = []
        
        for i, step in enumerate(steps):
            if i <= current_step:
                continue  # 跳过已完成的步骤
                
            step_id = step.get("step_id", f"step_{i}")
            step_dependencies = dependencies.get(step_id, [])
            
            # 检查依赖是否满足（简化实现）
            if not step_dependencies:
                executable_steps.append(step)
            # TODO: 实现更复杂的依赖检查逻辑
        
        return executable_steps
    
    def handle_human_intervention(self, state: IsotopeSystemState, intervention_type: str, user_input: str) -> Dict[str, Any]:
        """处理人类干预请求"""
        logger.info(f"RuntimeSupervisor处理人类干预: {intervention_type}")
        
        intervention_result = {
            "status": "processed",
            "action_taken": intervention_type,
            "user_input": user_input,
            "timestamp": time.time(),
            "recommendations": []
        }
        
        if intervention_type == "approval":
            intervention_result["approved"] = "approve" in user_input.lower()
            if intervention_result["approved"]:
                intervention_result["recommendations"].append("继续执行任务")
            else:
                intervention_result["recommendations"].append("暂停任务，等待进一步指令")
                
        elif intervention_type == "feedback":
            # 处理用户反馈，可能需要调整任务参数
            intervention_result["feedback_processed"] = True
            intervention_result["recommendations"].append("根据用户反馈调整执行策略")
            
        elif intervention_type == "interrupt":
            # 处理中断请求
            intervention_result["interrupted"] = True
            intervention_result["recommendations"].append("保存当前状态并暂停执行")
            
        return intervention_result
    
    def create_execution_checkpoint(self, state: IsotopeSystemState) -> Dict[str, Any]:
        """创建执行检查点"""
        logger.info("RuntimeSupervisor创建执行检查点")
        
        checkpoint = {
            "checkpoint_id": f"checkpoint_{int(time.time())}",
            "timestamp": time.time(),
            "state_snapshot": {
                "metadata": state.get("metadata", {}),
                "current_step": state.get("metadata", {}).get("task_plan", {}).get("current_step", 0),
                "execution_history": self.execution_history[-10:],  # 保留最近10条记录
                "performance_metrics": self.performance_metrics.copy()
            },
            "recovery_instructions": {
                "resume_from": state.get("metadata", {}).get("task_plan", {}).get("current_step", 0),
                "required_tools": state.get("metadata", {}).get("task_plan", {}).get("mcp_tools_required", []),
                "dependencies": state.get("metadata", {}).get("task_plan", {}).get("dependencies", {})
            }
        }
        
        return checkpoint
