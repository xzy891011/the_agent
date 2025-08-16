"""
增强版图构建器 - 阶段1：任务-子图框架

实现分层智能体架构：
1. Meta-Supervisor（元监督者）：负责任务分解和高层决策
2. Task-Planner（任务规划器）：负责具体任务规划
3. Runtime-Supervisor（运行时监督者）：负责执行过程监控
4. Domain-Expert-Subgraph（领域专家子图）：专门的领域处理子图
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable, Union, Literal, Set, Tuple
from enum import Enum
import uuid

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import add_messages
from langgraph.constants import Send
from langgraph.types import Command

from app.core.state import IsotopeSystemState, StateManager, TaskStatus
from app.core.config import ConfigManager
from app.core.postgres_checkpoint import get_postgres_checkpoint_manager, PostgreSQLCheckpointManager
from app.core.task_decorator import task_registry, get_task_by_name, apply_langgraph_decorator
from app.core.critic_node import create_critic_node, CriticResult

logger = logging.getLogger(__name__)

class TaskType(str, Enum):
    """任务类型枚举"""
    CONSULTATION = "consultation"  # 咨询类任务
    DATA_ANALYSIS = "data_analysis"  # 数据分析任务
    EXPERT_ANALYSIS = "expert_analysis"  # 专家分析任务
    MULTI_STEP = "multi_step"  # 多步骤复合任务
    TOOL_EXECUTION = "tool_execution"  # 工具执行任务

class TaskPriority(str, Enum):
    """任务优先级枚举"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class SubgraphType(str, Enum):
    """子图类型枚举"""
    DATA_PROCESSING = "data_processing"  # 数据处理子图
    ISOTOPE_ANALYSIS = "isotope_analysis"  # 同位素分析子图
    VISUALIZATION = "visualization"  # 可视化子图
    REPORT_GENERATION = "report_generation"  # 报告生成子图

class TaskPlan:
    """任务计划类"""
    
    def __init__(
        self,
        task_id: str,
        task_type: TaskType,
        description: str,
        priority: TaskPriority = TaskPriority.MEDIUM,
        steps: Optional[List[Dict[str, Any]]] = None,
        subgraphs: Optional[List[SubgraphType]] = None,
        estimated_duration: Optional[int] = None,
        dependencies: Optional[List[str]] = None
    ):
        self.task_id = task_id
        self.task_type = task_type
        self.description = description
        self.priority = priority
        self.steps = steps or []
        self.subgraphs = subgraphs or []
        self.estimated_duration = estimated_duration
        self.dependencies = dependencies or []
        self.created_at = datetime.now()
        self.status = TaskStatus.NOT_STARTED
        self.current_step = 0
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "description": self.description,
            "priority": self.priority.value,
            "steps": self.steps,
            "subgraphs": [sg.value for sg in self.subgraphs],
            "estimated_duration": self.estimated_duration,
            "dependencies": self.dependencies,
            "created_at": self.created_at.isoformat(),
            "status": self.status.value,
            "current_step": self.current_step
        }

class MetaSupervisor:
    """元监督者 - 负责身份校验、需求分析和异常兜底"""
    
    def __init__(self, llm: BaseChatModel, config: Optional[Dict[str, Any]] = None):
        self.llm = llm
        self.config = config or {}
        # 获取系统能力
        from app.core.system_capability_registry import get_system_capabilities, system_capability_registry
        self.system_capabilities = get_system_capabilities()
        self.capability_registry = system_capability_registry
    
    def analyze_user_request(self, state: IsotopeSystemState) -> Dict[str, Any]:
        """分析用户请求，确定任务类型和执行策略"""
        logger.info("MetaSupervisor开始分析用户请求")
        
        # 获取最后一条用户消息
        last_human_msg = StateManager.get_last_human_message(state)
        if not last_human_msg:
            return self._fallback_analysis("无用户输入")
        
        user_input = last_human_msg.content
        
        # 快速识别简单身份确认问题
        simple_identity_keywords = ["你是谁", "你好", "介绍一下", "什么是", "系统", "身份", "功能"]
        user_lower = user_input.lower()
        
        # 如果是简单的身份确认或问候，直接标记为consultation
        if any(keyword in user_lower for keyword in simple_identity_keywords) and len(user_input) < 20:
            logger.info(f"识别为简单身份确认问题: {user_input}")
            return {
                "task_type": TaskType.CONSULTATION,
                "complexity": "simple",
                "confidence": 0.95,
                "required_capabilities": [],
                "need_human_interaction": False,
                "reasoning": "简单身份确认问题，无需复杂处理"
            }
        
        # 搜索相关能力
        from app.core.system_capability_registry import search_capabilities
        relevant_capabilities = search_capabilities(user_input)
        
        # 构建分析提示词
        capability_info = "\n".join([
            f"- {cap.name}: {cap.description}" 
            for cap in relevant_capabilities[:5]  # 限制显示前5个最相关的
        ])
        
        prompt = f"""
        分析用户请求并确定任务类型和所需能力。
        
        用户请求: {user_input}
        
        系统当前可用的相关能力:
        {capability_info}
        
        系统能力摘要:
        - 总能力数: {len(self.system_capabilities)}
        - 工具数: {len([c for c in self.system_capabilities.values() if c.metadata.get('is_tool')])}
        - 任务数: {len([c for c in self.system_capabilities.values() if c.type.value == 'task'])}
        
        请分析并返回JSON格式:
        {{
            "task_type": "consultation/data_analysis/expert_analysis/multi_step/tool_execution",
            "confidence": 0.0-1.0,
            "required_capabilities": ["能力1", "能力2"],
            "complexity": "simple/medium/complex",
            "need_human_interaction": true/false,
            "reasoning": "分析理由"
        }}
        """
        
        try:
            response = self.llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            
            # 解析JSON
            import json
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                
                # 验证所需能力是否真实存在
                validated_capabilities = []
                for cap_name in analysis.get("required_capabilities", []):
                    if self.capability_registry.get_capability(cap_name):
                        validated_capabilities.append(cap_name)
                    else:
                        # 尝试模糊匹配
                        matches = search_capabilities(cap_name)
                        if matches:
                            validated_capabilities.append(matches[0].name)
                
                analysis["required_capabilities"] = validated_capabilities
                analysis["available_capabilities"] = [cap.name for cap in relevant_capabilities]
                
                return analysis
            else:
                logger.warning("MetaSupervisor无法解析LLM响应为JSON")
                return self._fallback_analysis(user_input)
        
        except Exception as e:
            logger.error(f"MetaSupervisor分析失败: {str(e)}")
            return self._fallback_analysis(user_input)
    
    def _fallback_analysis(self, user_input: str) -> Dict[str, Any]:
        """回退分析方法"""
        # 基于关键词的简单分析
        data_keywords = ["数据", "分析", "图表", "可视化", "文件"]
        expert_keywords = ["同位素", "碳", "气体", "成熟度", "来源"]
        tool_keywords = ["生成", "计算", "处理", "转换"]
        
        user_lower = user_input.lower()
        
        if any(keyword in user_lower for keyword in expert_keywords):
            return {
                "task_type": TaskType.EXPERT_ANALYSIS,
                "complexity": "medium",
                "reasoning": "包含专业领域关键词",
                "requires_tools": ["isotope_analysis"],
                "estimated_steps": 3
            }
        elif any(keyword in user_lower for keyword in data_keywords):
            return {
                "task_type": TaskType.DATA_ANALYSIS,
                "complexity": "medium",
                "reasoning": "包含数据分析关键词",
                "requires_tools": ["data_processing"],
                "estimated_steps": 2
            }
        elif any(keyword in user_lower for keyword in tool_keywords):
            return {
                "task_type": TaskType.TOOL_EXECUTION,
                "complexity": "low",
                "reasoning": "包含工具执行关键词",
                "requires_tools": ["general"],
                "estimated_steps": 1
            }
        else:
            return {
                "task_type": TaskType.CONSULTATION,
                "complexity": "low",
                "reasoning": "简单咨询问题",
                "requires_tools": [],
                "estimated_steps": 1
            }
    
    def decide_execution_strategy(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """根据分析结果决定执行策略"""
        # 安全解析任务类型，处理LLM可能返回的复合值
        task_type_str = analysis.get("task_type", "consultation")
        
        # 如果LLM返回了复合类型，取第一个有效的类型
        if "/" in task_type_str:
            task_type_str = task_type_str.split("/")[0]
        
        # 映射到有效的TaskType枚举值
        task_type_mapping = {
            "consultation": TaskType.CONSULTATION,
            "data_analysis": TaskType.DATA_ANALYSIS,
            "expert_analysis": TaskType.EXPERT_ANALYSIS,
            "multi_step": TaskType.MULTI_STEP,
            "tool_execution": TaskType.TOOL_EXECUTION
        }
        
        task_type = task_type_mapping.get(task_type_str.lower(), TaskType.CONSULTATION)
        complexity = analysis.get("complexity", "low")
        
        strategy = {
            "use_task_planner": complexity in ["medium", "high"],
            "use_subgraphs": task_type in [TaskType.DATA_ANALYSIS, TaskType.EXPERT_ANALYSIS, TaskType.MULTI_STEP],
            "requires_human_approval": complexity == "high",
            "parallel_execution": len(analysis.get("requires_tools", [])) > 1,
            "monitoring_level": "high" if complexity == "high" else "medium"
        }
        
        logger.info(f"Meta-Supervisor决策: {strategy}")
        return strategy

class TaskPlanner:
    """任务规划器 - 将用户需求拆解为可执行的DAG子图"""
    
    def __init__(self, llm: BaseChatModel, config: Optional[Dict[str, Any]] = None):
        self.llm = llm
        self.config = config or {}
        # 获取系统能力和任务注册表
        from app.core.system_capability_registry import get_system_capabilities, system_capability_registry
        from app.core.task_decorator import task_registry
        self.system_capabilities = get_system_capabilities()
        self.capability_registry = system_capability_registry
        self.task_registry = task_registry
    
    def create_task_plan(
        self, 
        analysis: Dict[str, Any], 
        strategy: Dict[str, Any],
        state: IsotopeSystemState
    ) -> TaskPlan:
        """基于分析结果创建任务执行计划"""
        logger.info("TaskPlanner开始创建任务执行计划")
        
        task_type = analysis.get("task_type", "consultation")
        task_id = f"task_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        # 获取所需能力的详细信息
        required_capabilities = []
        for cap_name in analysis.get("required_capabilities", []):
            cap = self.capability_registry.get_capability(cap_name)
            if cap:
                required_capabilities.append(cap)
        
        # 基于任务类型和可用能力创建计划
        if task_type == "consultation":
            return self._create_consultation_plan(task_id, analysis, state)
        elif task_type == "data_analysis":
            return self._create_data_analysis_plan(task_id, analysis, state, required_capabilities)
        elif task_type == "expert_analysis":
            return self._create_expert_analysis_plan(task_id, analysis, state, required_capabilities)
        elif task_type == "multi_step":
            return self._create_multi_step_plan(task_id, analysis, state, required_capabilities)
        elif task_type == "tool_execution":
            return self._create_tool_execution_plan(task_id, analysis, state, required_capabilities)
        else:
            return self._create_default_plan(task_id, analysis, state)
    
    def _create_consultation_plan(self, task_id: str, analysis: Dict[str, Any], state: IsotopeSystemState) -> TaskPlan:
        """创建咨询类任务计划"""
        steps = [
            {
                "step_id": 1,
                "name": "理解问题",
                "description": "分析用户问题并提供回答",
                "agent": "supervisor",
                "tools": [],
                "expected_output": "直接回答"
            }
        ]
        
        return TaskPlan(
            task_id=task_id,
            task_type=TaskType.CONSULTATION,
            description=analysis.get("reasoning", "咨询类任务"),
            priority=TaskPriority.MEDIUM,
            steps=steps,
            estimated_duration=30  # 30秒
        )
    
    def _create_data_analysis_plan(self, task_id: str, analysis: Dict[str, Any], state: IsotopeSystemState, required_capabilities: List[Any]) -> TaskPlan:
        """创建数据分析任务计划"""
        steps = [
            {
                "step_id": 1,
                "name": "数据预处理",
                "description": "检查和预处理上传的数据文件",
                "agent": "data_agent",
                "tools": ["preview_file_content", "search_documents_rag"],
                "expected_output": "数据概览"
            },
            {
                "step_id": 2,
                "name": "数据分析",
                "description": "执行具体的数据分析任务",
                "agent": "expert_agent",
                "tools": ["enhanced_analyze_isotope_depth_trends"],
                "expected_output": "分析结果"
            }
        ]
        
        # 确定需要的子图类型
        subgraphs = [
            SubgraphType.DATA_PROCESSING,
            SubgraphType.ISOTOPE_ANALYSIS,
            SubgraphType.VISUALIZATION
        ]
        
        # 为每个步骤分配子图
        for i, step in enumerate(steps):
            if "数据预处理" in step.get("description", ""):
                step["subgraph"] = SubgraphType.DATA_PROCESSING.value
            elif "数据分析" in step.get("description", ""):
                step["subgraph"] = SubgraphType.ISOTOPE_ANALYSIS.value
            else:
                step["subgraph"] = SubgraphType.DATA_PROCESSING.value
        
        return TaskPlan(
            task_id=task_id,
            task_type=TaskType.DATA_ANALYSIS,
            description=analysis.get("reasoning", "数据分析任务"),
            priority=TaskPriority.MEDIUM,
            steps=steps,
            subgraphs=subgraphs,
            estimated_duration=300  # 5分钟
        )
    
    def _create_expert_analysis_plan(self, task_id: str, analysis: Dict[str, Any], state: IsotopeSystemState, required_capabilities: List[Any]) -> TaskPlan:
        """创建专家分析任务计划"""
        steps = [
            {
                "step_id": 1,
                "name": "专业分析",
                "description": "使用专业工具进行同位素分析",
                "agent": "expert_agent",
                "tools": ["enhanced_classify_gas_source", "enhanced_analyze_gas_maturity"],
                "expected_output": "专业分析结果"
            },
            {
                "step_id": 2,
                "name": "结果可视化",
                "description": "生成分析图表和可视化",
                "agent": "expert_agent",
                "tools": ["enhanced_plot_bernard_diagram", "enhanced_plot_whiticar_diagram"],
                "expected_output": "可视化图表"
            },
            {
                "step_id": 3,
                "name": "报告生成",
                "description": "生成综合分析报告",
                "agent": "expert_agent",
                "tools": ["generate_isotope_report"],
                "expected_output": "分析报告"
            }
        ]
        
        return TaskPlan(
            task_id=task_id,
            task_type=TaskType.EXPERT_ANALYSIS,
            description=analysis.get("reasoning", "专家分析任务"),
            priority=TaskPriority.HIGH,
            steps=steps,
            subgraphs=[SubgraphType.ISOTOPE_ANALYSIS, SubgraphType.VISUALIZATION, SubgraphType.REPORT_GENERATION],
            estimated_duration=600  # 10分钟
        )
    
    def _create_multi_step_plan(self, task_id: str, analysis: Dict[str, Any], state: IsotopeSystemState, required_capabilities: List[Any]) -> TaskPlan:
        """创建多步骤任务计划"""
        # 这里可以根据具体需求实现更复杂的多步骤规划
        return self._create_expert_analysis_plan(task_id, analysis, state, required_capabilities)
    
    def _create_tool_execution_plan(self, task_id: str, analysis: Dict[str, Any], state: IsotopeSystemState, required_capabilities: List[Any]) -> TaskPlan:
        """创建工具执行任务计划"""
        steps = [
            {
                "step_id": 1,
                "name": "工具执行",
                "description": "执行指定的工具",
                "agent": "supervisor",
                "tools": required_capabilities,
                "expected_output": "工具执行结果"
            }
        ]
        
        return TaskPlan(
            task_id=task_id,
            task_type=TaskType.TOOL_EXECUTION,
            description=analysis.get("reasoning", "工具执行任务"),
            priority=TaskPriority.MEDIUM,
            steps=steps,
            estimated_duration=120  # 2分钟
        )
    
    def _create_default_plan(self, task_id: str, analysis: Dict[str, Any], state: IsotopeSystemState) -> TaskPlan:
        """创建默认任务计划"""
        return self._create_consultation_plan(task_id, analysis, state)

class RuntimeSupervisor:
    """运行时监督者 - 负责执行过程监控"""
    
    def __init__(self, llm: BaseChatModel, config: Optional[Dict[str, Any]] = None):
        self.llm = llm
        self.config = config or {}
        self.execution_history = []
    
    def monitor_execution(self, state: IsotopeSystemState, current_step: Dict[str, Any]) -> Dict[str, Any]:
        """监控当前执行步骤"""
        logger.info(f"Runtime-Supervisor: 监控执行步骤 {current_step.get('step_id')}")
        
        monitoring_result = {
            "step_status": "in_progress",
            "issues_detected": [],
            "recommendations": [],
            "should_continue": True,
            "requires_intervention": False
        }
        
        # 检查执行时间
        step_start_time = current_step.get("start_time")
        if step_start_time:
            elapsed_time = time.time() - step_start_time
            expected_duration = current_step.get("expected_duration", 60)
            
            if elapsed_time > expected_duration * 1.5:
                monitoring_result["issues_detected"].append("执行时间超出预期")
                monitoring_result["recommendations"].append("考虑优化或中断当前步骤")
        
        # 检查错误历史
        recent_errors = [action for action in state.get("action_history", []) 
                        if action.get("status") == "error"]
        
        if len(recent_errors) > 2:
            monitoring_result["issues_detected"].append("频繁出现错误")
            monitoring_result["requires_intervention"] = True
        
        return monitoring_result
    
    def decide_next_action(self, state: IsotopeSystemState, task_plan: TaskPlan) -> str:
        """决定下一步行动"""
        current_step = task_plan.current_step
        
        if current_step >= len(task_plan.steps):
            return "complete"
        
        next_step = task_plan.steps[current_step]
        agent_type = next_step.get("agent", "supervisor")
        
        # 根据智能体类型决定路由
        if agent_type == "data_agent":
            return "data_processing_subgraph"
        elif agent_type == "expert_agent":
            return "expert_analysis_subgraph"
        else:
            return "supervisor"

class EnhancedGraphBuilder:
    """增强版图构建器 - 阶段2版本
    
    新增功能：
    1. MySQL checkpoint集成
    2. @task支持和管理
    3. 失败节点重播
    4. 子图级别检查点
    5. Task级别的错误恢复
    """
    
    def __init__(
        self,
        agents: Optional[Dict[str, Any]] = None,
        config: Optional[Union[ConfigManager, Dict[str, Any]]] = None,  # 修改类型提示，支持字典和ConfigManager
        enable_postgres_checkpoint: bool = True,
        enable_mysql_checkpoint: bool = False,  # 新增MySQL选项
        checkpoint_backend: str = "postgres",  # 默认使用postgres，可选 "mysql", "postgres", "memory"
        enable_task_support: bool = True,
        # 阶段1兼容参数
        llm: Optional[BaseChatModel] = None,
        supervisor_agent: Optional[Any] = None,
        specialized_agents: Optional[Dict[str, Any]] = None,  # 新增专业智能体参数
        checkpointer: Optional[Any] = None
    ):
        """
        初始化增强版图构建器
        
        Args:
            agents: 智能体字典 {agent_name: agent_instance}
            config: 配置管理器实例或配置字典，如果为None则创建默认实例
            enable_postgres_checkpoint: 是否启用PostgreSQL检查点（向后兼容）
            enable_mysql_checkpoint: 是否启用MySQL检查点
            checkpoint_backend: 检查点后端类型 ("postgres", "mysql", "memory")
            enable_task_support: 是否启用Task支持
            # 以下为阶段1兼容参数，会逐步废弃
            llm: LLM实例（兼容）
            supervisor_agent: 监督者智能体（兼容）
            data_agent: 数据智能体（兼容）
            expert_agent: 专家智能体（兼容）
            checkpointer: 检查点器（兼容）
        """
        # 兼容阶段1参数：如果传入了llm等参数，构建agents字典
        if llm and (supervisor_agent or specialized_agents):
            self.agents = {
                "llm": llm,
                "supervisor_agent": supervisor_agent,
            }
            # 添加专业智能体到agents字典
            if specialized_agents:
                self.agents.update(specialized_agents)
            
            # 创建阶段1需要的组件
            self.llm = llm
            # 安全地获取配置
            config_dict = self._safe_get_config(config)
            self.meta_supervisor = MetaSupervisor(llm, config_dict)
            self.task_planner = TaskPlanner(llm, config_dict)
            self.runtime_supervisor = RuntimeSupervisor(llm, config_dict)
            
            logger.info("使用阶段1兼容模式初始化增强版图构建器（专业智能体架构）")
        else:
            # 阶段2模式
            self.agents = agents or {}
            # 即使在阶段2模式，也尝试获取或创建LLM配置
            if llm:
                self.llm = llm
            else:
                # 尝试创建默认LLM
                try:
                    from app.utils.qwen_chat import SFChatOpenAI
                    self.llm = SFChatOpenAI(
                        model="Qwen/Qwen2.5-72B-Instruct",
                        temperature=0.1,
                    )
                    logger.info("阶段2模式创建默认LLM成功")
                except Exception as e:
                    logger.warning(f"阶段2模式创建默认LLM失败: {str(e)}")
                    self.llm = None
                    
            self.meta_supervisor = None
            self.task_planner = None
            self.runtime_supervisor = None
            
            logger.info("使用阶段2模式初始化增强版图构建器")
        
        # 处理配置参数：确保self.config始终是ConfigManager对象
        if isinstance(config, ConfigManager):
            # 如果已经是ConfigManager对象，直接使用
            self.config = config
        elif isinstance(config, dict):
            # 如果是字典，创建ConfigManager并合并配置
            self.config = ConfigManager()
            try:
                # 加载默认配置
                self.config.load_config()
                # 合并传入的配置字典
                for key, value in config.items():
                    self.config.update_config(key, value)
                logger.debug(f"已合并字典配置到ConfigManager中")
            except Exception as e:
                logger.warning(f"合并配置失败: {str(e)}，使用默认配置")
        else:
            # 如果为None或其他类型，创建默认ConfigManager
            self.config = ConfigManager()
            try:
                self.config.load_config()
                logger.debug("使用默认ConfigManager配置")
            except Exception as e:
                logger.warning(f"加载默认配置失败: {str(e)}")
        
        self.enable_postgres_checkpoint = enable_postgres_checkpoint
        self.enable_mysql_checkpoint = enable_mysql_checkpoint
        self.checkpoint_backend = checkpoint_backend
        self.enable_task_support = enable_task_support
        self.checkpointer = checkpointer  # 保存外部传入的检查点器
        
        # 检查点管理器初始化 - 支持多种后端
        self.postgres_checkpoint_manager: Optional[PostgreSQLCheckpointManager] = None
        self.mysql_checkpoint_manager: Optional[Any] = None  # 将在需要时导入
        
        # 根据配置确定实际使用的后端
        actual_backend = self._determine_checkpoint_backend()
        
        if actual_backend == "postgres":
            self._init_postgres_checkpoint()
        elif actual_backend == "mysql":
            self._init_mysql_checkpoint()
        else:
            logger.info("使用内存检查点器")
        
        # Task注册表
        self.task_registry = task_registry if enable_task_support else None
        
        # 初始化中断管理器
        self.enable_interrupt = self.config.get_config_value("system.enable_interrupt", True)
        self.interrupt_manager = None
        if self.enable_interrupt:
            try:
                from app.core.interrupt_manager import create_default_interrupt_manager
                self.interrupt_manager = create_default_interrupt_manager(self._safe_get_config(config))
                logger.info("中断管理器已启用")
            except Exception as e:
                logger.warning(f"初始化中断管理器失败: {str(e)}")
                self.enable_interrupt = False
        
        logger.info(f"检查点后端: {actual_backend}, 中断机制: {'启用' if self.enable_interrupt else '禁用'}")
    
    def _determine_checkpoint_backend(self) -> str:
        """确定实际使用的检查点后端
        
        Returns:
            实际使用的后端类型 ("postgres", "mysql", "memory")
        """
        # 如果显式指定了后端
        if self.checkpoint_backend in ["postgres", "mysql", "memory"]:
            return self.checkpoint_backend
        
        # 基于旧参数的兼容性检查
        if self.enable_postgres_checkpoint:
            return "postgres"
        elif self.enable_mysql_checkpoint:
            return "mysql"
        else:
            return "memory"
    
    def _init_postgres_checkpoint(self):
        """初始化PostgreSQL检查点管理器"""
        try:
            logger.info("正在启用PostgreSQL检查点管理器...")
            self.postgres_checkpoint_manager = get_postgres_checkpoint_manager(self.config)
            
            if self.postgres_checkpoint_manager:
                # 测试连接
                postgres_available = self.postgres_checkpoint_manager.test_connection()
                if postgres_available:
                    logger.info("PostgreSQL检查点管理器连接测试成功")
                else:
                    logger.warning("PostgreSQL连接测试失败，但检查点管理器已创建")
            else:
                logger.warning("PostgreSQL检查点管理器创建失败")
                self.postgres_checkpoint_manager = None
        except Exception as e:
            logger.error(f"初始化PostgreSQL检查点管理器失败: {str(e)}")
            self.postgres_checkpoint_manager = None
    
    def _init_mysql_checkpoint(self):
        """初始化MySQL检查点管理器"""
        try:
            logger.info("正在启用MySQL检查点管理器...")
            # 动态导入MySQL检查点管理器
            from app.core.mysql_checkpoint import get_mysql_checkpoint_manager
            self.mysql_checkpoint_manager = get_mysql_checkpoint_manager(self.config)
            
            if self.mysql_checkpoint_manager:
                # 测试连接
                mysql_available = self.mysql_checkpoint_manager.test_connection()
                if mysql_available:
                    logger.info("MySQL检查点管理器连接测试成功")
                else:
                    logger.warning("MySQL连接测试失败，但检查点管理器已创建")
            else:
                logger.warning("MySQL检查点管理器创建失败")
                self.mysql_checkpoint_manager = None
        except Exception as e:
            logger.error(f"初始化MySQL检查点管理器失败: {str(e)}")
            self.mysql_checkpoint_manager = None
    
    def _safe_get_config(self, config: Any) -> Dict[str, Any]:
        """安全地获取配置字典
        
        Args:
            config: 配置对象或字典
            
        Returns:
            配置字典
        """
        try:
            if config is None:
                return {}
            elif hasattr(config, 'config'):
                # ConfigManager对象
                return config.config
            elif isinstance(config, dict):
                # 普通字典
                return config
            else:
                # 其他类型，尝试转换为字典
                return dict(config) if config else {}
        except Exception as e:
            logger.warning(f"获取配置失败: {str(e)}，使用空配置")
            return {}
    
    def build_enhanced_graph(self, session_id: Optional[str] = None) -> StateGraph:
        """构建增强版图 - 阶段1版本，集成Critic节点
        
        集成PostgreSQL checkpoint、@task支持和Critic审查节点
        
        Args:
            session_id: 会话ID，可选，如果不提供则生成一个随机ID
            
        Returns:
            增强版状态图
        """
        # 如果没有提供session_id，生成一个随机ID
        if session_id is None:
            import uuid
            session_id = str(uuid.uuid4())
            
        logger.info(f"开始构建阶段1增强版图（含Critic节点），会话ID: {session_id}")
        
        try:
            # 导入状态类型
            from app.core.state import IsotopeSystemState
            
            # 创建状态图 - 使用正确的状态类型
            graph = StateGraph(IsotopeSystemState)
            
            # 创建Meta-Supervisor和TaskPlanner
            config_dict = self._safe_get_config(self.config)
            llm_for_components = self.llm or self._get_default_llm()
            meta_supervisor = MetaSupervisor(llm_for_components, config_dict)
            task_planner = TaskPlanner(llm_for_components, config_dict)
            runtime_supervisor = RuntimeSupervisor(llm_for_components, config_dict)
            
            # 创建Critic节点（现在具有健壮的RAG审查）
            llm_for_critic = self.llm or self._get_default_llm()
            critic_node_func = create_critic_node(
                llm_for_critic, 
                config_dict,
                enable_rag_review=True,  # 重新启用RAG审查，现在有健壮的错误处理
                enable_capability_check=True
            )
            
            # 创建支持task的增强节点
            enhanced_nodes = self.create_task_enhanced_nodes()
            
            # 添加Meta-Supervisor节点
            def meta_supervisor_node(state: IsotopeSystemState) -> IsotopeSystemState:
                """Meta-Supervisor节点：分析用户请求"""
                # 推送节点开始执行信息
                from app.core.stream_writer_helper import (
                    push_node_start, push_node_complete, push_thinking, push_error
                )
                push_node_start("meta_supervisor", "开始分析用户请求")
                
                logger.info("执行Meta-Supervisor节点")
                
                try:
                    # 推送思考过程
                    push_thinking("meta_supervisor", "正在分析用户请求的意图和复杂度", "request_analysis")
                    
                    # 分析用户请求
                    analysis = meta_supervisor.analyze_user_request(state)
                    
                    # 推送分析进度
                    push_thinking("meta_supervisor", f"请求分析完成：{analysis.get('task_type', '未知')}类型，复杂度{analysis.get('complexity', '未知')}", "strategy_planning")
                    
                    # 决策执行策略
                    strategy = meta_supervisor.decide_execution_strategy(analysis)
                    
                    # 更新状态
                    updated_state = state.copy()
                    if "metadata" not in updated_state:
                        updated_state["metadata"] = {}
                    
                    updated_state["metadata"]["task_analysis"] = analysis
                    updated_state["metadata"]["execution_strategy"] = strategy
                    
                    # 添加分析消息
                    from langchain_core.messages import AIMessage
                    analysis_msg = AIMessage(
                        content=f"📋 任务分析完成：{analysis.get('task_type', '未知')} "
                                f"(复杂度: {analysis.get('complexity', '未知')})"
                    )
                    updated_state = StateManager.update_messages(updated_state, analysis_msg)
                    
                    # 推送节点完成信息
                    push_node_complete("meta_supervisor", f"用户请求分析完成，任务类型：{analysis.get('task_type', '未知')}")
                    
                    return updated_state
                    
                except Exception as e:
                    logger.error(f"Meta-Supervisor执行失败: {str(e)}")
                    
                    # 推送错误信息
                    push_error(f"Meta-Supervisor分析失败: {str(e)}", "meta_supervisor")
                    
                    error_msg = AIMessage(content=f"❌ Meta-Supervisor分析失败: {str(e)}")
                    return StateManager.update_messages(state, error_msg)
            
            # 添加Task-Planner节点
            def task_planner_node(state: IsotopeSystemState) -> IsotopeSystemState:
                """Task-Planner节点：创建任务计划并生成动态子图"""
                # 推送节点开始执行信息
                from app.core.stream_writer_helper import (
                    push_node_start, push_node_complete, push_thinking, push_error, push_progress
                )
                push_node_start("task_planner", "开始创建任务执行计划")
                
                logger.info("执行Task-Planner节点")
                
                try:
                    # 推送思考过程
                    push_thinking("task_planner", "正在获取分析结果并制定执行计划", "plan_creation")
                    
                    # 获取分析结果
                    analysis = state.get("metadata", {}).get("task_analysis", {})
                    strategy = state.get("metadata", {}).get("execution_strategy", {})
                    
                    if not analysis:
                        logger.warning("缺少任务分析结果，使用默认分析")
                        push_thinking("task_planner", "未找到分析结果，使用默认分析策略", "fallback_planning")
                        analysis = {"task_type": "consultation", "complexity": "low"}
                    
                    # 推送计划创建进度
                    push_progress("task_planning", 0.3, f"开始创建{analysis.get('task_type', '未知')}类型的任务计划")
                    
                    # 创建任务计划
                    task_plan = task_planner.create_task_plan(analysis, strategy, state)
                    
                    # 更新状态
                    updated_state = state.copy()
                    updated_state["metadata"]["task_plan"] = task_plan.to_dict()
                    
                    # ⭐ 阶段5核心功能：动态子图生成
                    if task_plan.subgraphs:
                        # 推送子图生成开始信息
                        subgraph_names = [sg.value for sg in task_plan.subgraphs]
                        push_thinking("task_planner", f"任务需要生成{len(subgraph_names)}个动态子图：{', '.join(subgraph_names)}", "subgraph_generation")
                        push_progress("subgraph_generation", 0.5, f"开始生成{len(subgraph_names)}个动态子图")
                        
                        logger.info(f"🔧 TaskPlanner开始生成动态子图：{subgraph_names}")
                        
                        try:
                            # 导入子图生成器
                            from app.core.subgraph_generator import get_subgraph_generator
                            subgraph_generator = get_subgraph_generator(self._safe_get_config(self.config))
                            
                            # 为每个子图类型生成对应的动态子图
                            generated_subgraphs = {}
                            total_subgraphs = len(task_plan.subgraphs)
                            
                            for i, subgraph_type in enumerate(task_plan.subgraphs):
                                # 推送当前子图生成进度
                                current_progress = 0.5 + (i / total_subgraphs) * 0.4  # 0.5-0.9之间
                                push_progress("subgraph_generation", current_progress, f"正在生成子图: {subgraph_type.value} ({i+1}/{total_subgraphs})")
                                
                                logger.info(f"📊 生成子图: {subgraph_type.value}")
                                
                                # 生成动态子图
                                subgraph = subgraph_generator.generate_subgraph(
                                    subgraph_type=subgraph_type,
                                    task_plan=task_plan.to_dict(),
                                    context={"state": updated_state, "session_id": session_id}
                                )
                                
                                if subgraph:
                                    # 编译子图
                                    compiled_subgraph = subgraph_generator.compile_subgraph(
                                        subgraph=subgraph,
                                        session_id=session_id,
                                        subgraph_name=f"{subgraph_type.value}_subgraph"
                                    )
                                    generated_subgraphs[subgraph_type.value] = compiled_subgraph
                                    logger.info(f"✅ 子图 {subgraph_type.value} 生成并编译成功")
                                    
                                    # 推送子图完成信息
                                    push_thinking("task_planner", f"子图 {subgraph_type.value} 生成并编译成功", "subgraph_complete")
                                else:
                                    logger.warning(f"⚠️ 子图 {subgraph_type.value} 生成失败")
                                    push_error(f"子图 {subgraph_type.value} 生成失败", "task_planner")
                            
                            # 将生成的子图保存到状态中
                            updated_state["metadata"]["generated_subgraphs"] = generated_subgraphs
                            updated_state["metadata"]["subgraph_execution_plan"] = {
                                "subgraphs": list(generated_subgraphs.keys()),
                                "current_subgraph_index": 0,
                                "execution_mode": "sequential"  # 默认顺序执行子图
                            }
                            
                            # 推送最终进度
                            push_progress("subgraph_generation", 1.0, f"所有子图生成完成：{len(generated_subgraphs)}/{total_subgraphs}")
                            
                            # 添加成功消息
                            plan_msg = AIMessage(
                                content=f"📝 任务规划完成：{task_plan.description}\n"
                                        f"🔧 动态子图已生成：{len(generated_subgraphs)} 个子图\n"
                                        f"📊 子图类型：{', '.join(generated_subgraphs.keys())}"
                            )
                            updated_state = StateManager.update_messages(updated_state, plan_msg)
                            
                        except Exception as subgraph_error:
                            logger.error(f"动态子图生成失败: {str(subgraph_error)}")
                            
                            # 推送子图生成失败信息
                            push_error(f"动态子图生成失败: {str(subgraph_error)}", "task_planner")
                            push_thinking("task_planner", "子图生成失败，回退到传统处理模式", "fallback_mode")
                            
                            # 子图生成失败时，回退到传统路由
                            error_msg = AIMessage(
                                content=f"⚠️ 动态子图生成失败，使用传统处理模式: {str(subgraph_error)}"
                            )
                            updated_state = StateManager.update_messages(updated_state, error_msg)
                    else:
                        # 没有子图需求的简单任务
                        push_thinking("task_planner", "任务无需复杂子图，使用简单执行计划", "simple_plan")
                        push_progress("task_planning", 0.8, f"创建简单任务计划，预计{len(task_plan.steps)}个步骤")
                        
                        plan_msg = AIMessage(
                            content=f"📝 任务规划完成：{task_plan.description} "
                                    f"(预计 {len(task_plan.steps)} 个步骤)"
                        )
                        updated_state = StateManager.update_messages(updated_state, plan_msg)
                    
                    # 更新当前任务
                    task_info = {
                        "task_id": task_plan.task_id,
                        "task_type": task_plan.task_type.value,
                        "description": task_plan.description,
                        "status": "in_progress",
                        "created_at": task_plan.created_at.isoformat(),
                        "updated_at": task_plan.created_at.isoformat(),
                        "steps": task_plan.steps,
                        "current_step": 0
                    }
                    updated_state = StateManager.update_current_task(updated_state, task_info)
                    
                    # 推送节点完成信息
                    push_progress("task_planning", 1.0, "任务规划完成")
                    push_node_complete("task_planner", f"任务规划完成：{task_plan.task_type.value}类型，{len(task_plan.steps)}个步骤")
                    
                    return updated_state
                    
                except Exception as e:
                    logger.error(f"Task-Planner执行失败: {str(e)}")
                    
                    # 推送错误信息
                    push_error(f"Task-Planner规划失败: {str(e)}", "task_planner")
                    
                    error_msg = AIMessage(content=f"❌ Task-Planner规划失败: {str(e)}")
                    return StateManager.update_messages(state, error_msg)
            
            # 添加Runtime-Supervisor节点
            def runtime_supervisor_node(state: IsotopeSystemState) -> IsotopeSystemState:
                """Runtime-Supervisor节点：监控执行过程并执行动态子图"""
                # 推送节点开始执行信息
                from app.core.stream_writer_helper import (
                    push_node_start, push_node_complete, push_thinking, push_error, push_progress
                )
                push_node_start("runtime_supervisor", "开始监控和执行任务")
                
                logger.info("执行Runtime-Supervisor节点")
                
                try:
                    current_task = state.get("current_task")
                    if not current_task:
                        push_thinking("runtime_supervisor", "无当前任务，跳过执行", "task_check")
                        push_node_complete("runtime_supervisor", "无任务需要执行")
                        return state
                    
                    # 推送监控开始信息
                    push_thinking("runtime_supervisor", f"开始监控任务执行：{current_task.get('description', '未知任务')}", "monitoring")
                    
                    # 监控执行
                    monitor_result = runtime_supervisor.monitor_execution(state, current_task)
                    
                    # ⭐ 阶段5核心功能：执行动态子图
                    generated_subgraphs = state.get("metadata", {}).get("generated_subgraphs", {})
                    subgraph_plan = state.get("metadata", {}).get("subgraph_execution_plan", {})
                    
                    if generated_subgraphs and subgraph_plan:
                        # 推送子图执行开始信息
                        push_thinking("runtime_supervisor", f"发现{len(generated_subgraphs)}个动态子图，开始执行", "subgraph_execution")
                        logger.info("🚀 RuntimeSupervisor开始执行动态子图")
                        
                        current_index = subgraph_plan.get("current_subgraph_index", 0)
                        subgraph_list = subgraph_plan.get("subgraphs", [])
                        
                        if current_index < len(subgraph_list):
                            current_subgraph_name = subgraph_list[current_index]
                            current_subgraph = generated_subgraphs.get(current_subgraph_name)
                            
                            if current_subgraph:
                                # 推送子图执行进度
                                execution_progress = current_index / len(subgraph_list)
                                push_progress("subgraph_execution", execution_progress, f"执行子图 {current_subgraph_name} ({current_index + 1}/{len(subgraph_list)})")
                                push_thinking("runtime_supervisor", f"开始执行子图: {current_subgraph_name}", "subgraph_run")
                                
                                logger.info(f"📊 执行子图: {current_subgraph_name}")
                                
                                try:
                                    # 执行子图
                                    subgraph_result = current_subgraph.invoke(
                                        state,
                                        config={"configurable": {"thread_id": f"{session_id}_{current_subgraph_name}"}}
                                    )
                                    
                                    # 合并子图执行结果
                                    updated_state = state.copy()
                                    if isinstance(subgraph_result, dict):
                                        # 更新消息
                                        if "messages" in subgraph_result and subgraph_result["messages"]:
                                            if "messages" not in updated_state:
                                                updated_state["messages"] = []
                                            updated_state["messages"].extend(subgraph_result["messages"])
                                        
                                        # 更新其他字段
                                        for key, value in subgraph_result.items():
                                            if key != "messages":
                                                updated_state[key] = value
                                    
                                    # 更新子图执行进度
                                    updated_state["metadata"]["subgraph_execution_plan"]["current_subgraph_index"] = current_index + 1
                                    
                                    # 推送子图执行成功信息
                                    completion_progress = (current_index + 1) / len(subgraph_list)
                                    push_progress("subgraph_execution", completion_progress, f"子图 {current_subgraph_name} 执行完成")
                                    push_thinking("runtime_supervisor", f"子图 {current_subgraph_name} 执行成功，结果已合并", "subgraph_complete")
                                    
                                    # 添加执行成功消息
                                    exec_msg = AIMessage(
                                        content=f"✅ 子图 {current_subgraph_name} 执行完成 ({current_index + 1}/{len(subgraph_list)})"
                                    )
                                    updated_state = StateManager.update_messages(updated_state, exec_msg)
                                    
                                    logger.info(f"✅ 子图 {current_subgraph_name} 执行成功")
                                    
                                    # 检查是否还有更多子图需要执行
                                    if current_index + 1 < len(subgraph_list):
                                        # 标记需要继续执行下一个子图
                                        updated_state["metadata"]["next_action"] = "continue_subgraph"
                                    else:
                                        # 所有子图执行完成
                                        updated_state["metadata"]["next_action"] = "all_subgraphs_complete"
                                        complete_msg = AIMessage(
                                            content="🎉 所有动态子图执行完成！"
                                        )
                                        updated_state = StateManager.update_messages(updated_state, complete_msg)
                                    
                                    return updated_state
                                    
                                except Exception as subgraph_exec_error:
                                    logger.error(f"子图 {current_subgraph_name} 执行失败: {str(subgraph_exec_error)}")
                                    
                                    # 推送子图执行失败信息
                                    push_error(f"子图 {current_subgraph_name} 执行失败: {str(subgraph_exec_error)}", "runtime_supervisor")
                                    push_thinking("runtime_supervisor", f"子图 {current_subgraph_name} 执行失败，标记错误状态", "error_handling")
                                    
                                    error_msg = AIMessage(
                                        content=f"❌ 子图 {current_subgraph_name} 执行失败: {str(subgraph_exec_error)}"
                                    )
                                    updated_state = state.copy()
                                    updated_state = StateManager.update_messages(updated_state, error_msg)
                                    updated_state["metadata"]["next_action"] = "subgraph_error"
                                    return updated_state
                            else:
                                logger.warning(f"子图 {current_subgraph_name} 不存在")
                        else:
                            # 推送所有子图执行完成信息
                            push_progress("subgraph_execution", 1.0, "所有动态子图执行完成")
                            push_thinking("runtime_supervisor", "所有动态子图已执行完成，准备进入最终审查", "completion")
                            
                            logger.info("所有子图已执行完成")
                            updated_state = state.copy()
                            updated_state["metadata"]["next_action"] = "all_subgraphs_complete"
                            return updated_state
                    
                    # 传统任务监控逻辑（无子图时的回退）
                    task_plan_dict = state.get("metadata", {}).get("task_plan", {})
                    if task_plan_dict:
                        task_plan = TaskPlan(
                            task_id=task_plan_dict["task_id"],
                            task_type=TaskType(task_plan_dict["task_type"]),
                            description=task_plan_dict["description"]
                        )
                        next_action = runtime_supervisor.decide_next_action(state, task_plan)
                        
                        # 更新状态
                        updated_state = state.copy()
                        if "metadata" not in updated_state:
                            updated_state["metadata"] = {}
                        updated_state["metadata"]["runtime_monitor"] = monitor_result
                        updated_state["metadata"]["next_action"] = next_action
                        
                        # 添加监控消息
                        monitor_msg = AIMessage(content=f"🔍 Runtime监控：{next_action}")
                        updated_state = StateManager.update_messages(updated_state, monitor_msg)
                        
                        # 推送节点完成信息
                        push_node_complete("runtime_supervisor", f"传统任务监控完成，下一步动作：{next_action}")
                        
                        return updated_state
                    
                    # 推送节点完成信息（无任务或子图的情况）
                    push_node_complete("runtime_supervisor", "无需执行任务或子图")
                    return state
                    
                except Exception as e:
                    logger.error(f"Runtime-Supervisor执行失败: {str(e)}")
                    
                    # 推送错误信息
                    push_error(f"Runtime-Supervisor监控失败: {str(e)}", "runtime_supervisor")
                    
                    error_msg = AIMessage(content=f"❌ Runtime-Supervisor监控失败: {str(e)}")
                    return StateManager.update_messages(state, error_msg)
            
            # 添加所有节点到图中
            graph.add_node("meta_supervisor", meta_supervisor_node)
            graph.add_node("task_planner", task_planner_node)
            graph.add_node("runtime_supervisor", runtime_supervisor_node)
            graph.add_node("critic", critic_node_func)
            
            # 添加增强的智能体节点
            for node_name, node_func in enhanced_nodes.items():
                graph.add_node(node_name, node_func)
                logger.info(f"添加增强节点: {node_name}")
            
            # 创建路由函数
            def route_after_meta_supervisor(state: IsotopeSystemState) -> str:
                """Meta-Supervisor后的路由"""
                analysis = state.get("metadata", {}).get("task_analysis", {})
                task_type = analysis.get("task_type", "consultation")
                
                if task_type == "consultation":
                    return "main_agent"
                else:
                    return "task_planner"
            
            def route_after_task_planner(state: IsotopeSystemState) -> str:
                """Task-Planner后的路由 - 使用专业智能体架构"""
                task_plan = state.get("metadata", {}).get("task_plan", {})
                task_type = task_plan.get("task_type", "consultation")
                
                # 阶段5架构：所有任务都通过智能路由器进行最佳智能体选择
                if "smart_router" in enhanced_nodes:
                    logger.info(f"任务类型 {task_type} -> 智能路由器")
                    return "smart_router"
                else:
                    # 回退方案：如果没有智能路由器，使用传统路由
                    if task_type == "data_analysis":
                        return "quality_control_agent" if "quality_control_agent" in enhanced_nodes else "main_agent"
                    elif task_type == "expert_analysis":
                        return "general_analysis_agent" if "general_analysis_agent" in enhanced_nodes else "main_agent"
                    else:
                        return "main_agent"
            
            def route_after_agent_execution(state: IsotopeSystemState) -> str:
                """智能体执行后的路由"""
                # 先进行Critic审查
                return "critic"
            
            def route_after_critic(state: IsotopeSystemState) -> str:
                """Critic审查后的路由"""
                critic_result = state.get("metadata", {}).get("critic_result", {})
                next_action = critic_result.get("next_action", "continue")
                
                logger.info(f"Critic决策: {next_action}")
                
                if next_action == "continue":
                    return "runtime_supervisor"
                elif next_action == "replan":
                    return "task_planner"
                elif next_action == "interrupt":
                    # 处理中断
                    if self.interrupt_manager:
                        interrupt_reason = self.interrupt_manager.create_interrupt_for_critic(critic_result)
                        if interrupt_reason:
                            # 将中断信息添加到状态中
                            updated_state = state.copy()
                            if "metadata" not in updated_state:
                                updated_state["metadata"] = {}
                            updated_state["metadata"]["interrupt_reason"] = interrupt_reason.dict()
                            
                            # 发送中断信号
                            interrupt_msg = AIMessage(
                                content=f"⏸️ 执行中断: {interrupt_reason.reason}",
                                additional_kwargs={
                                    "__interrupt__": interrupt_reason.dict()
                                }
                            )
                            StateManager.update_messages(updated_state, interrupt_msg)
                            
                            logger.info(f"触发中断: {interrupt_reason.reason}")
                    
                    # 根据配置决定后续路由
                    return "runtime_supervisor"  # 暂时先到runtime_supervisor
                else:  # abort
                    return "__end__"
            
            def route_after_runtime_supervisor(state: IsotopeSystemState) -> str:
                """Runtime-Supervisor后的路由 - 支持动态子图循环执行"""
                next_action = state.get("metadata", {}).get("next_action", "complete")
                logger.info(f"Runtime-Supervisor路由决策: {next_action}")
                
                # 动态子图执行逻辑
                if next_action == "continue_subgraph":
                    # 继续执行下一个子图，回到runtime_supervisor
                    logger.info("🔄 继续执行下一个动态子图")
                    return "runtime_supervisor"
                elif next_action == "all_subgraphs_complete":
                    # 所有子图执行完成，进行最终审查
                    logger.info("✅ 所有子图执行完成，进入Critic审查")
                    return "critic"
                elif next_action == "subgraph_error":
                    # 子图执行出错，进行审查和决策
                    logger.info("❌ 子图执行出错，进入Critic审查")
                    return "critic"
                elif next_action == "replan":
                    # 需要重新规划
                    logger.info("🔄 需要重新规划，返回TaskPlanner")
                    return "task_planner"
                elif next_action == "interrupt":
                    # 需要中断
                    logger.info("⏸️ 需要中断，直接结束")
                    return "__end__"
                else:
                    # 默认完成流程
                    logger.info("🏁 流程完成，直接结束")
                    return "__end__"
            
            # 设置图的流程
            graph.set_entry_point("meta_supervisor")
            
            # 添加条件边
            graph.add_conditional_edges(
                "meta_supervisor",
                route_after_meta_supervisor,
                {
                    "main_agent": "main_agent",
                    "task_planner": "task_planner"
                }
            )
            
            graph.add_conditional_edges(
                "task_planner", 
                route_after_task_planner,
                {
                    "main_agent": "main_agent",
                    "smart_router": "smart_router" if "smart_router" in enhanced_nodes else "main_agent",
                    "general_analysis_agent": "general_analysis_agent" if "general_analysis_agent" in enhanced_nodes else "main_agent"
                }
            )
            
            # 添加智能路由器的条件边
            def route_after_smart_router(state: IsotopeSystemState) -> str:
                """智能路由器后的路由"""
                route_to = state.get("metadata", {}).get("route_to", "general_analysis_agent")
                logger.info(f"智能路由器决策: 路由到 {route_to}")
                return route_to
            
            if "smart_router" in enhanced_nodes:
                graph.add_conditional_edges(
                    "smart_router",
                    route_after_smart_router,
                    {
                        "geophysics_agent": "geophysics_agent" if "geophysics_agent" in enhanced_nodes else "general_analysis_agent",
                        "reservoir_agent": "reservoir_agent" if "reservoir_agent" in enhanced_nodes else "general_analysis_agent",
                        "economics_agent": "economics_agent" if "economics_agent" in enhanced_nodes else "general_analysis_agent",
                        "quality_control_agent": "quality_control_agent" if "quality_control_agent" in enhanced_nodes else "general_analysis_agent",
                        "logging_agent": "logging_agent" if "logging_agent" in enhanced_nodes else "general_analysis_agent",  # 录井智能体
                        "seismic_agent": "seismic_agent" if "seismic_agent" in enhanced_nodes else "general_analysis_agent",  # 地震智能体
                        "general_analysis_agent": "general_analysis_agent" if "general_analysis_agent" in enhanced_nodes else "main_agent",
                        "critic": "critic"  # 支持直接到critic的身份确认响应
                    }
                )
            
            # 只有实际执行任务的智能体才需要经过Critic审查（智能路由器不需要）
            for agent_name in ["main_agent", "general_analysis_agent", 
                             "geophysics_agent", "reservoir_agent", "economics_agent", 
                             "quality_control_agent", "logging_agent", "seismic_agent"]:
                if agent_name in enhanced_nodes:
                    graph.add_edge(agent_name, "critic")
            
            # Critic审查后的路由
            graph.add_conditional_edges(
                "critic",
                route_after_critic,
                {
                    "runtime_supervisor": "runtime_supervisor",
                    "task_planner": "task_planner",
                    "__end__": "__end__"
                }
            )
            
            # Runtime-Supervisor后的路由
            graph.add_conditional_edges(
                "runtime_supervisor",
                route_after_runtime_supervisor,
                {
                    "task_planner": "task_planner",
                    "__end__": "__end__"
                }
            )
            
            logger.info("阶段1增强版图（含Critic节点）构建完成")
            return graph
            
        except Exception as e:
            logger.error(f"构建增强版图失败: {str(e)}")
            raise
    
    def create_graph_with_checkpoint(
        self,
        session_id: str,
        enable_subgraph_checkpoint: bool = True
    ) -> StateGraph:
        """创建带检查点的图
        
        Args:
            session_id: 会话ID
            enable_subgraph_checkpoint: 是否启用子图检查点
            
        Returns:
            配置了检查点的状态图
        """
        logger.info(f"开始创建带检查点的图，会话ID: {session_id}")
        
        try:
            # 创建增强版图（使用MetaSupervisor架构）
            graph = self.build_enhanced_graph(session_id)
            
            # 获取检查点器
            checkpointer = self.get_active_checkpointer()
            
            if checkpointer:
                # 获取检查点系统状态
                checkpoint_status = self.get_checkpoint_status()
                logger.info(f"使用检查点后端: {checkpoint_status['active_backend']}")
                
                # 尝试设置thread_id属性（如果支持）
                try:
                    if hasattr(checkpointer, 'thread_id'):
                        checkpointer.thread_id = session_id
                except Exception as e:
                    logger.warning(f"无法设置检查点器thread_id: {str(e)}")
            else:
                logger.warning("所有检查点器都不可用，图将无法持久化")
            
            # 如果PostgreSQL检查点不可用，尝试使用内存检查点
            if not checkpointer:
                try:
                    from langgraph.checkpoint.memory import MemorySaver
                    checkpointer = MemorySaver()
                    logger.info("使用内存检查点器作为回退")
                except Exception as memory_error:
                    logger.warning(f"内存检查点器也不可用: {str(memory_error)}")
                    logger.warning("图将无法持久化")
            
            # 编译图并配置检查点
            if checkpointer:
                # 定义中断点（可以根据需要配置）
                interrupt_before = []
                interrupt_after = []
                
                # 编译图
                compiled_graph = graph.compile(
                    checkpointer=checkpointer,
                    # 启用中断和恢复
                    interrupt_before=interrupt_before,  # 可以配置在哪些节点前中断
                    interrupt_after=interrupt_after     # 可以配置在哪些节点后中断
                )
                logger.info("图已编译并配置了检查点")
            else:
                compiled_graph = graph.compile()
                logger.warning("图已编译但未配置检查点")
            
            return compiled_graph
            
        except Exception as e:
            logger.error(f"创建带检查点的图失败: {str(e)}")
            # 回退到无检查点版本（使用增强图）
            try:
                fallback_graph = self.build_enhanced_graph(session_id)
                return fallback_graph.compile()
            except Exception as compile_error:
                logger.error(f"回退编译也失败: {str(compile_error)}")
                # 创建最小化的图
                minimal_graph = StateGraph(dict)
                minimal_graph.add_node("default", lambda state: state)
                minimal_graph.set_entry_point("default")
                return minimal_graph.compile()
    
    def create_task_enhanced_nodes(self) -> Dict[str, Callable]:
        """创建支持@task的增强节点
        
        Returns:
            增强节点字典
        """
        enhanced_nodes = {}
        
        if not self.enable_task_support:
            logger.info("Task支持未启用，但仍使用新架构节点")
        
        logger.info("创建支持@task的增强节点")
        
        # 使用新的LangGraph架构创建智能体节点
        logger.info("使用新的LangGraph架构创建智能体节点")
        
        # 导入注册表
        from app.agents.registry import agent_registry
        
        # 创建统一智能体节点生成器
        def create_agent_node(agent_name: str, role: str) -> Callable:
            """创建使用注入智能体的节点"""
            def agent_node(state: IsotopeSystemState) -> IsotopeSystemState:
                try:
                    logger.info(f"{agent_name}节点开始执行")
                    
                    # 确保state是字典格式
                    if not isinstance(state, dict):
                        state = {}
                    
                    # 确保必要字段存在
                    state = self._ensure_state_fields(state)
                    
                    # 从注入的智能体中获取
                    agent = None
                    
                    # 首先尝试从传入的supervisor_agent获取
                    if agent_name == "main_agent" and self.supervisor_agent:
                        agent = self.supervisor_agent
                        logger.info(f"使用注入的supervisor_agent作为{agent_name}")
                    # 否则从注册表获取
                    elif agent_registry.has_agent(role):
                        agent = agent_registry.get(role)
                        logger.info(f"从注册表获取智能体: {role}")
                    # 如果还是没有，尝试通过名称获取
                    elif agent_registry.has_agent(agent_name):
                        agent = agent_registry.get(agent_name)
                        logger.info(f"从注册表获取智能体: {agent_name}")
                    else:
                        raise ValueError(f"未找到智能体: {agent_name} (role: {role})")
                    
                    # 运行智能体
                    result_state = agent.run(state)
                    
                    logger.info(f"{agent_name}节点执行完成")
                    return result_state
                    
                except Exception as e:
                    logger.error(f"{agent_name}节点执行失败: {str(e)}")
                    state = self._ensure_state_fields(state)
                    state["messages"].append({
                        "role": "assistant", 
                        "content": f"{agent_name}处理出错: {str(e)}"
                    })
                    return state
            
            return agent_node
        
        # 创建专业智能体节点生成器
        def create_specialized_agent_node(agent_type: str) -> Callable:
            """创建专业智能体节点"""
            
            def specialized_agent_node(state: IsotopeSystemState) -> IsotopeSystemState:
                try:
                    # 推送节点开始执行信息
                    from app.core.stream_writer_helper import (
                        push_node_start, push_node_complete, push_thinking, push_error
                    )
                    push_node_start(f"{agent_type}_agent", f"开始执行专业智能体：{agent_type}")
                    
                    logger.info(f"{agent_type}专业智能体节点开始执行")
                    
                    # 确保state是字典格式
                    if not isinstance(state, dict):
                        state = {}
                    
                    # 确保必要字段存在
                    state = self._ensure_state_fields(state)
                    
                    # 从注册表或注入的智能体中获取
                    agent = None
                    
                    # 首先尝试从specialized_agents中获取
                    if self.specialized_agents and agent_type in self.specialized_agents:
                        agent = self.specialized_agents[agent_type]
                        logger.info(f"使用注入的专业智能体: {agent_type}")
                    # 否则从注册表获取
                    elif agent_registry.has_agent(agent_type):
                        agent = agent_registry.get(agent_type)
                        logger.info(f"从注册表获取专业智能体: {agent_type}")
                    else:
                        error_msg = f"未找到专业智能体: {agent_type}"
                        push_error(error_msg, f"{agent_type}_agent")
                        raise ValueError(error_msg)
                    
                    # 推送Agent开始处理用户请求
                    push_thinking(f"{agent_type}_agent", f"开始使用{agent_type}专业智能体处理用户请求", "processing")
                    
                    # 运行智能体
                    result_state = agent.run(state)
                    
                    # 推送节点完成信息
                    push_node_complete(f"{agent_type}_agent", f"{agent_type}专业智能体处理完成")
                    
                    logger.info(f"{agent_type}专业智能体节点执行完成")
                    return result_state
                    
                except Exception as e:
                    logger.error(f"{agent_type}专业智能体节点执行失败: {str(e)}")
                    
                    # 推送错误信息
                    push_error(f"{agent_type}专业智能体处理失败: {str(e)}", f"{agent_type}_agent")
                    
                    state = self._ensure_state_fields(state)
                    state["messages"].append({
                        "role": "assistant", 
                        "content": f"{agent_type}专业智能体处理出错: {str(e)}"
                    })
                    return state
            
            return specialized_agent_node
        
        # 创建智能路由节点
        def create_smart_router_node() -> Callable:
            """创建智能路由节点，使用LLM智能推荐合适的专业智能体"""
            def smart_router_node(state: IsotopeSystemState) -> IsotopeSystemState:
                try:
                    # 推送节点开始执行信息
                    from app.core.stream_writer_helper import push_node_start, push_thinking
                    push_node_start("smart_router", "开始智能路由分析")
                    
                    logger.info("智能路由节点开始执行")
                    
                    # 确保state是字典格式
                    if not isinstance(state, dict):
                        state = {}
                    
                    # 确保必要字段存在
                    state = self._ensure_state_fields(state)
                    
                    # 导入推荐函数
                    from app.agents.specialized_agents import recommend_agent_for_request
                    
                    # 获取最后一条用户消息
                    from app.core.state import StateManager
                    last_msg = StateManager.get_last_human_message(state)
                    if not last_msg:
                        raise ValueError("未找到用户消息")
                    
                    # 使用LLM进行智能意图识别和智能体推荐
                    llm = self.llm or self._get_default_llm()
                    recommended_agent = recommend_agent_for_request(last_msg.content, llm)
                    
                    # 处理特殊的身份确认响应
                    if recommended_agent == "identity_response":
                        # 使用流式LLM生成身份确认回答，避免重复输出问题
                        from langchain_core.messages import AIMessage
                        
                        # 获取用户的具体问题内容
                        user_question = last_msg.content if last_msg else "你是谁"
                        
                        # 构建身份确认的提示词
                        identity_prompt = f"""用户问题：{user_question}
 
 请作为一个专业的天然气碳同位素数据解释智能助手来回答这个身份确认问题。
 
 你的回答应该：
 1. 简洁明了地介绍自己的身份和专业领域
 2. 突出你在天然气碳同位素数据解释方面的专业能力
 3. 提及你能够协助的主要技术领域（如地球物理分析、油藏工程、经济评价等）
 4. 语气专业但友好，展现出专业性和可信度
 5. 简短地询问用户有什么可以帮助的
 
 请直接回答，不要包含任何解释或额外说明。"""
                        
                        try:
                            # 使用流式写入辅助工具推送节点开始信息
                            from app.core.stream_writer_helper import push_node_start, push_thinking
                            push_node_start("smart_router", "开始生成身份确认回复")
                            
                            # 推送Agent思考过程
                            push_thinking("smart_router", "检测到身份确认问题，正在生成专业回复", "identity_response")
                            
                            # 使用LLM流式生成身份确认响应
                            llm = self.llm or self._get_default_llm()
                            
                            # 获取LangGraph原生流写入器用于LLM token流式输出
                            from langgraph.config import get_stream_writer
                            stream_writer = get_stream_writer()
                            
                            if stream_writer:
                                # 如果有流写入器，使用流式输出
                                response_content = ""
                                for chunk in llm.stream(identity_prompt):
                                    if hasattr(chunk, 'content') and chunk.content:
                                        chunk_content = chunk.content
                                        response_content += chunk_content
                                        # 实时流式输出
                                        stream_writer({
                                            "role": "assistant",
                                            "content": chunk_content,
                                            "is_token": True,
                                            "source": "smart_router"
                                        })
                                
                                # 创建AI消息并添加到状态
                                ai_message = AIMessage(
                                    content=response_content,
                                    additional_kwargs={
                                        "source": "smart_router",
                                        "route_decision": "identity_response",
                                        "llm_generated": True,
                                        "streamed": True  # 标记为已流式输出
                                    }
                                )
                            else:
                                # 如果没有流写入器，直接生成响应（但不会有重复问题，因为没有流处理）
                                identity_response = llm.invoke(identity_prompt)
                                
                                # 确保响应是字符串格式
                                if hasattr(identity_response, 'content'):
                                    response_content = identity_response.content
                                else:
                                    response_content = str(identity_response)
                                
                                ai_message = AIMessage(
                                    content=response_content,
                                    additional_kwargs={
                                        "source": "smart_router",
                                        "route_decision": "identity_response",
                                        "llm_generated": True,
                                        "streamed": False  # 标记为非流式输出
                                    }
                                )
                            
                            state = StateManager.update_messages(state, ai_message)
                            state["metadata"]["route_to"] = "critic"  # 直接到critic结束
                            
                            # 推送节点完成和路由决策信息
                            from app.core.stream_writer_helper import push_node_complete, push_route
                            push_node_complete("smart_router", "身份确认回复生成完成")
                            push_route("smart_router", "critic", "身份确认问题，直接结束对话")
                            
                            # 清理不可序列化的对象，避免检查点序列化错误
                            if "memory_store" in state:
                                del state["memory_store"]
                            
                            logger.info("智能路由器: 身份确认问题，已使用流式LLM生成回答")
                            return state
                            
                        except Exception as e:
                            logger.error(f"LLM生成身份确认响应失败: {str(e)}")
                            # 如果LLM调用失败，路由到通用分析智能体
                            state["metadata"]["selected_agent"] = "general_analysis"
                            state["metadata"]["route_to"] = "general_analysis_agent"
                            logger.info("身份确认LLM调用失败，路由到通用分析智能体")
                            return state
                    
                    # 在状态中记录路由决策
                    if "metadata" not in state:
                        state["metadata"] = {}
                    state["metadata"]["selected_agent"] = recommended_agent
                    state["metadata"]["route_to"] = f"{recommended_agent}_agent"  # 设置路由目标
                    
                    # 推送路由决策信息
                    from app.core.stream_writer_helper import push_node_complete, push_route
                    push_node_complete("smart_router", f"智能路由分析完成，选择{recommended_agent}智能体")
                    push_route("smart_router", f"{recommended_agent}_agent", f"LLM推荐使用{recommended_agent}智能体处理此请求")
                    
                    logger.info(f"LLM智能路由决策: 选择 {recommended_agent} 智能体")
                    return state
                    
                except Exception as e:
                    logger.error(f"智能路由节点执行失败: {str(e)}")
                    
                    # 推送错误信息
                    from app.core.stream_writer_helper import push_error, push_route
                    push_error(f"智能路由执行失败: {str(e)}", "smart_router")
                    
                    # 默认路由到通用分析智能体
                    state = self._ensure_state_fields(state)
                    if "metadata" not in state:
                        state["metadata"] = {}
                    state["metadata"]["selected_agent"] = "general_analysis"
                    state["metadata"]["route_to"] = "general_analysis_agent"
                    
                    # 推送兜底路由决策
                    push_route("smart_router", "general_analysis_agent", "智能路由失败，使用通用分析智能体作为兜底")
                    
                    logger.info("智能路由失败，默认选择通用分析智能体")
                    return state
            
            return smart_router_node
        
        # 创建新架构的节点（专业智能体架构）
        enhanced_nodes = {
            "smart_router": create_smart_router_node(),
            "geophysics_agent": create_specialized_agent_node("geophysics"),
            "reservoir_agent": create_specialized_agent_node("reservoir"),
            "economics_agent": create_specialized_agent_node("economics"),
            "quality_control_agent": create_specialized_agent_node("quality_control"),
            "general_analysis_agent": create_specialized_agent_node("general_analysis"),
            # 新增专业智能体
            "logging_agent": create_specialized_agent_node("logging"),  # 录井资料处理
            "seismic_agent": create_specialized_agent_node("seismic"),  # 地震处理
            # 保留传统智能体作为兜底（向后兼容）
            "main_agent": create_agent_node("main_agent", "supervisor"),
        }
        
        return enhanced_nodes
    
    def _default_agent_node(self, state: IsotopeSystemState, agent_type: str) -> IsotopeSystemState:
        """默认智能体节点，用于未配置特定智能体的情况
        
        Args:
            state: 系统状态
            agent_type: 智能体类型（data、expert等）
            
        Returns:
            更新后的状态
        """
        try:
            logger.info(f"执行默认{agent_type}智能体节点")
            
            # 确保state是字典格式
            if not isinstance(state, dict):
                state = {}
            
            # 确保messages字段存在
            if "messages" not in state or state["messages"] is None:
                state["messages"] = []
            
            # 使用LLM生成智能回复，而不是硬编码
            try:
                # 获取用户最近的消息
                user_content = ""
                if state["messages"]:
                    last_message = state["messages"][-1]
                    if hasattr(last_message, 'content'):
                        user_content = last_message.content
                    elif isinstance(last_message, dict):
                        user_content = last_message.get("content", "")
                    else:
                        user_content = str(last_message)
                
                # 构建专业的LLM提示词
                agent_descriptions = {
                    "data": "数据分析专家，专注于天然气碳同位素数据的处理、清洗和初步分析",
                    "expert": "同位素地球化学专家，专门进行天然气成因和来源的深度分析",
                    "quality_control": "数据质量控制专家，负责数据验证、异常检测和质量评估",
                    "general_analysis": "综合分析专家，提供跨领域的综合性分析和建议",
                    "geophysics": "地球物理分析专家，专注于地震、测井等地球物理数据解释",
                    "reservoir": "油藏工程专家，专门分析储层特征和开发方案",
                    "economics": "经济评价专家，进行项目经济性分析和风险评估"
                }
                
                agent_desc = agent_descriptions.get(agent_type, f"{agent_type}领域专家")
                
                llm_prompt = f"""作为{agent_desc}，请对用户的请求给出专业回应。

用户输入：{user_content}

请以专业、详细的方式回答，体现出你在{agent_type}领域的专业能力。如果用户的问题不在你的专业范围内，请礼貌地说明并提供可能的建议。"""
                
                # 尝试使用LLM生成回复
                llm = self.llm or self._get_default_llm()
                if llm:
                    llm_response = llm.invoke(llm_prompt)
                    if hasattr(llm_response, 'content'):
                        content = llm_response.content
                    else:
                        content = str(llm_response)
                    
                    logger.info(f"默认{agent_type}智能体使用LLM生成回复")
                else:
                    # 如果没有LLM，生成一个专业的后备回复
                    content = f"作为{agent_desc}，我已收到您的请求。请提供更多具体信息，以便我为您提供更准确的专业分析。"
                    
            except Exception as e:
                logger.error(f"LLM生成{agent_type}智能体回复失败: {str(e)}")
                # LLM失败时的最后后备方案
                content = f"抱歉，{agent_type}智能体暂时遇到技术问题，请稍后再试。"
            
            # 添加响应消息
            state["messages"].append({
                "role": "assistant",
                "content": content
            })
            
            logger.info(f"默认{agent_type}智能体节点执行完成")
            return state
            
        except Exception as e:
            logger.error(f"默认{agent_type}智能体节点执行失败: {str(e)}")
            if not isinstance(state, dict):
                state = {}
            if "messages" not in state:
                state["messages"] = []
            state["messages"].append({
                "role": "assistant",
                "content": f"默认{agent_type}智能体执行出错: {str(e)}"
            })
            return state
    
    def _find_suitable_task(self, user_input: str) -> Optional[str]:
        """根据用户输入找到合适的task
        
        Args:
            user_input: 用户输入
            
        Returns:
            合适的task名称，如果没有则返回None
        """
        if not self.task_registry:
            return None
        
        all_tasks = self.task_registry.get_all_tasks()
        
        # 简单的关键词匹配
        # 在实际应用中，可以使用更复杂的语义匹配
        task_keywords = {
            "enhanced_classify_gas_source_task": ["气源", "分类", "同位素", "碳同位素"],
            "load_and_preprocess_isotope_data": ["加载", "预处理", "数据"],
            "generate_gas_source_visualization": ["可视化", "图表", "图片"],
        }
        
        user_input_lower = user_input.lower()
        
        for task_name, keywords in task_keywords.items():
            if task_name in all_tasks:
                for keyword in keywords:
                    if keyword in user_input_lower:
                        return task_name
        
        return None
    
    def _execute_task_safely(
        self, 
        task_func: Callable, 
        user_input: str, 
        state: IsotopeSystemState
    ) -> Optional[str]:
        """安全执行task
        
        Args:
            task_func: task函数
            user_input: 用户输入
            state: 系统状态
            
        Returns:
            执行结果或None
        """
        try:
            # 确保应用了LangGraph装饰器
            from app.core.task_decorator import apply_langgraph_decorator
            task_func = apply_langgraph_decorator(task_func)
            
            # 这里需要根据具体的task签名来构造参数
            # 这是一个简化的示例，实际应用中需要更复杂的参数推断
            
            # 检查是否有文件上下文
            if hasattr(state, 'current_file_id') and state.current_file_id:
                result = task_func(state.current_file_id)
            else:
                # 尝试其他参数组合
                result = task_func(user_input)
            
            return str(result)
            
        except Exception as e:
            logger.error(f"安全执行task失败: {str(e)}")
            return None
    
    def _get_data_analysis_tasks(self) -> List[str]:
        """获取数据分析相关的task列表"""
        if not self.task_registry:
            return []
        
        all_tasks = self.task_registry.get_all_tasks()
        
        # 筛选数据分析相关的task
        data_tasks = []
        for task_name in all_tasks.keys():
            if any(keyword in task_name.lower() for keyword in 
                   ["isotope", "data", "analysis", "classify", "visualiz"]):
                data_tasks.append(task_name)
        
        return data_tasks
    
    def _execute_data_analysis_task(
        self, 
        data_tasks: List[str], 
        state: IsotopeSystemState
    ) -> Optional[str]:
        """执行数据分析task"""
        # 这里可以实现更复杂的task选择和执行逻辑
        # 简化版本：选择第一个可用的task
        
        # 导入应用装饰器函数
        from app.core.task_decorator import apply_langgraph_decorator
        
        for task_name in data_tasks:
            try:
                task_func = get_task_by_name(task_name)
                if task_func:
                    # 应用LangGraph装饰器
                    task_func = apply_langgraph_decorator(task_func)
                    
                    if hasattr(state, 'current_file_id') and state.current_file_id:
                        result = task_func(state.current_file_id)
                        return f"数据分析Task '{task_name}' 执行结果：\n{result}"
            except Exception as e:
                logger.warning(f"执行数据分析task {task_name} 失败: {str(e)}")
                continue
        
        return None
    
    def create_subgraph_with_checkpoint(
        self, 
        subgraph_name: str,
        subgraph_nodes: Dict[str, Callable],
        session_id: Optional[str] = None
    ) -> StateGraph:
        """创建带检查点的子图
        
        Args:
            subgraph_name: 子图名称
            subgraph_nodes: 子图节点
            session_id: 会话ID，如果为None则生成随机ID
            
        Returns:
            配置了检查点的子图
        """
        # 如果没有提供session_id，生成一个随机ID
        if session_id is None:
            import uuid
            session_id = str(uuid.uuid4())
            
        logger.info(f"创建子图 '{subgraph_name}' 的检查点配置，会话ID: {session_id}")
        
        try:
            # 创建子图
            subgraph = StateGraph(dict)
            
            # 添加节点
            for node_name, node_func in subgraph_nodes.items():
                subgraph.add_node(node_name, node_func)
            
            # 添加边（简化版本）
            node_names = list(subgraph_nodes.keys())
            for i in range(len(node_names) - 1):
                subgraph.add_edge(node_names[i], node_names[i + 1])
            
            # 设置入口和出口
            if node_names:
                subgraph.set_entry_point(node_names[0])
                subgraph.set_finish_point(node_names[-1])
            
            # 获取检查点器
            checkpointer = None
            # 严格检查MySQL检查点器可用性
            postgres_available = (self.postgres_checkpoint_manager and 
                             self.postgres_checkpoint_manager.is_postgres_available() and 
                             self.postgres_checkpoint_manager.test_connection())
            
            if postgres_available:
                checkpointer = self.postgres_checkpoint_manager.get_checkpointer()
                if checkpointer:
                    logger.info(f"子图 '{subgraph_name}' 使用PostgreSQL检查点器")
                    
                    # 尝试设置thread_id属性
                    try:
                        if hasattr(checkpointer, 'thread_id'):
                            checkpointer.thread_id = f"{session_id}_{subgraph_name}"
                    except Exception as e:
                        logger.warning(f"无法设置子图检查点器thread_id: {str(e)}")
                else:
                    logger.warning(f"无法获取PostgreSQL检查点器实例，尝试使用内存检查点器")
            else:
                # 尝试使用内存检查点器
                try:
                    from langgraph.checkpoint.memory import MemorySaver
                    checkpointer = MemorySaver()
                    logger.info(f"子图 '{subgraph_name}' 使用内存检查点器")
                except Exception as memory_error:
                    logger.warning(f"创建内存检查点器失败: {str(memory_error)}")
                    checkpointer = None
            
            # 编译子图
            if checkpointer:
                # 子图级别的中断点配置
                interrupt_before = node_names[1:] if len(node_names) > 1 else []
                
                # 编译子图
                compiled_subgraph = subgraph.compile(
                    checkpointer=checkpointer,
                    interrupt_before=interrupt_before  # 在除第一个节点外的所有节点前中断
                )
                logger.info(f"子图 '{subgraph_name}' 已配置检查点")
            else:
                compiled_subgraph = subgraph.compile()
                logger.warning(f"子图 '{subgraph_name}' 未配置检查点")
            
            return compiled_subgraph
            
        except Exception as e:
            logger.error(f"创建子图检查点失败: {str(e)}")
            # 返回一个基本的编译子图
            try:
                minimal_subgraph = StateGraph(dict)
                minimal_subgraph.add_node("default", lambda state: state)
                minimal_subgraph.set_entry_point("default")
                return minimal_subgraph.compile()
            except:
                # 最后的回退
                raise
    
    def replay_from_checkpoint(
        self, 
        session_id: str, 
        checkpoint_id: Optional[str] = None,
        target_node: Optional[str] = None,
        is_test: bool = False
    ) -> Dict[str, Any]:
        """从检查点重播执行
        
        Args:
            session_id: 会话ID
            checkpoint_id: 检查点ID，None表示最新的
            target_node: 目标节点，None表示重播到结束
            is_test: 是否为测试模式，测试模式下如果没有找到检查点会创建一个空检查点
            
        Returns:
            重播结果
        """
        logger.info(f"开始从检查点重播，会话ID: {session_id}, 检查点ID: {checkpoint_id}")
        
        try:
            # 严格检查MySQL检查点器可用性
            postgres_available = (self.postgres_checkpoint_manager and 
                             self.postgres_checkpoint_manager.is_postgres_available() and 
                             self.postgres_checkpoint_manager.test_connection())
            
            # 检查是否有可用的检查点管理器
            if postgres_available:
                # 获取检查点
                checkpoint_data = self.postgres_checkpoint_manager.get_checkpoint(
                    session_id, checkpoint_id
                )
                
                if not checkpoint_data:
                    logger.warning(f"未找到检查点: {session_id}/{checkpoint_id}，尝试使用内存检查点")
                    
                    # 如果是测试模式，则自动创建一个初始检查点
                    if is_test:
                        logger.info(f"测试模式: 为会话 {session_id} 创建测试检查点")
                        
                        # 创建一个空的初始状态
                        initial_state = {"messages": []}
                        
                        # 创建配置
                        config = {"configurable": {"thread_id": session_id}}
                        
                        # 尝试保存检查点
                        try:
                            self.postgres_checkpoint_manager.put_checkpoint(
                                config, 
                                initial_state, 
                                {"created_for": "test", "created_at": time.time()}
                            )
                            logger.info(f"成功创建测试检查点: {session_id}")
                            
                            # 返回内存检查点
                            return {
                                "success": True,
                                "session_id": session_id,
                                "checkpoint_id": checkpoint_id,
                                "thread_id": session_id,
                                "note": "已创建测试检查点",
                                "source": "postgres_test"
                            }
                        except Exception as create_error:
                            logger.warning(f"创建测试检查点失败: {str(create_error)}")
                    
                    return self._fallback_to_memory_checkpoint(session_id, checkpoint_id)
                
                # 创建图
                graph = self.create_graph_with_checkpoint(session_id)
                
                # 从检查点恢复状态并重播
                # 注意：在最新版LangGraph中，不再使用config，而是直接在checkpointer中设置thread_id
                logger.info(f"检查点重播设置完成: {session_id}")
                return {
                    "success": True,
                    "session_id": session_id,
                    "checkpoint_id": checkpoint_id,
                    "thread_id": session_id,  # 用于重播的线程ID
                    "source": "postgres"
                }
            else:
                # 使用内存检查点回退
                return self._fallback_to_memory_checkpoint(session_id, checkpoint_id)
            
        except Exception as e:
            logger.error(f"检查点重播失败: {str(e)}")
            return {"error": str(e)}
            
    def _fallback_to_memory_checkpoint(self, session_id: str, checkpoint_id: Optional[str] = None) -> Dict[str, Any]:
        """回退到内存检查点重播
        
        Args:
            session_id: 会话ID
            checkpoint_id: 检查点ID
            
        Returns:
            重播配置
        """
        try:
            # 尝试创建内存检查点图
            from langgraph.checkpoint.memory import MemorySaver
            logger.info("PostgreSQL检查点管理器不可用，尝试使用内存检查点")
            
            return {
                "success": True,
                "session_id": session_id,
                "checkpoint_id": checkpoint_id,
                "thread_id": session_id,
                "note": "使用内存检查点，可能无法恢复之前的状态",
                "source": "memory"
            }
        except Exception as memory_error:
            logger.error(f"内存检查点创建失败: {str(memory_error)}")
            return {"error": "检查点系统不可用", "reason": str(memory_error)}
    
    def get_checkpoint_statistics(self) -> Dict[str, Any]:
        """获取检查点统计信息"""
        if self.postgres_checkpoint_manager and self.postgres_checkpoint_manager.is_postgres_available():
            return self.postgres_checkpoint_manager.get_statistics()
        
        # 如果PostgreSQL不可用，返回内存检查点的基本信息
        try:
            # 获取一个内存检查点统计
            from langgraph.checkpoint.memory import MemorySaver
            return {
                "checkpointer_type": "MemorySaver",
                "postgres_available": False,
                "connection_healthy": True,
                "total_checkpoints": 0,  # 内存检查点不跟踪数量
                "unique_threads": 0,
                "status": "内存检查点模式"
            }
        except Exception as e:
            logger.error(f"无法获取检查点统计信息: {str(e)}")
            return {"error": "无法获取检查点统计信息", "reason": str(e)}
    
    def compile_enhanced_graph(self, graph: Optional[StateGraph] = None, session_id: Optional[str] = None) -> Any:
        """编译增强版图
        
        Args:
            graph: 要编译的图，如果为None则自动构建一个新图
            session_id: 会话ID，如果为None则生成随机ID
            
        Returns:
            编译后的图
        """
        try:
            # 生成一个随机的会话ID（如果未提供）
            if session_id is None:
                import uuid
                session_id = str(uuid.uuid4())
                
            if graph is None:
                # 构建增强版图（MetaSupervisor架构）
                graph = self.build_enhanced_graph(session_id)
            
            logger.info(f"编译增强版图，会话ID: {session_id}...")
            
            # 尝试获取检查点器
            checkpointer = None
            if self.postgres_checkpoint_manager:
                checkpointer = self.postgres_checkpoint_manager.get_checkpointer()
            
            # 准备配置线程ID
            thread_id = session_id
            
            # 编译图
            if checkpointer:
                # 检查checkpointer是否支持thread_id参数
                try:
                    import inspect
                    if hasattr(checkpointer, 'get_checkpointer'):
                        # 某些封装类可能有这个方法
                        sig = inspect.signature(checkpointer.get_checkpointer)
                        if 'thread_id' in sig.parameters:
                            # 如果支持thread_id作为参数
                            compiled_graph = graph.compile(
                                checkpointer=checkpointer,
                                thread_id=thread_id
                            )
                        else:
                            compiled_graph = graph.compile(checkpointer=checkpointer)
                    else:
                        # 尝试直接设置thread_id属性
                        if hasattr(checkpointer, 'thread_id'):
                            checkpointer.thread_id = thread_id
                        
                        compiled_graph = graph.compile(checkpointer=checkpointer)
                except Exception as e:
                    logger.warning(f"设置thread_id失败，使用标准编译: {str(e)}")
                    compiled_graph = graph.compile(checkpointer=checkpointer)
                    
                logger.info("增强版图使用PostgreSQL检查点器编译完成")
            else:
                # 如果没有检查点器，尝试使用内存检查点器
                try:
                    from langgraph.checkpoint.memory import MemorySaver
                    memory_checkpointer = MemorySaver()
                    compiled_graph = graph.compile(checkpointer=memory_checkpointer)
                    logger.info("增强版图使用内存检查点器编译完成")
                except Exception as memory_error:
                    logger.warning(f"使用内存检查点器失败: {str(memory_error)}")
                    compiled_graph = graph.compile()
                    logger.info("增强版图不使用检查点器编译完成")
            
            return compiled_graph
            
        except Exception as e:
            logger.error(f"编译增强版图失败: {str(e)}")
            # 尝试最简单的编译方式
            if graph:
                return graph.compile()
            else:
                # 创建最小化的图
                minimal_graph = StateGraph(dict)
                minimal_graph.add_node("default", lambda state: state)
                minimal_graph.set_entry_point("default")
                return minimal_graph.compile()
    
    def create_thread_config(self, thread_id: Optional[str] = None) -> Dict[str, Any]:
        """创建线程配置"""
        if thread_id is None:
            import uuid
            thread_id = str(uuid.uuid4())
        
        return {
            "configurable": {
                "thread_id": thread_id
            }
        }
    
    def visualize_graph(self, compiled_graph: Optional[Any] = None) -> Tuple[str, Optional[bytes]]:
        """可视化增强版图结构
        
        Args:
            compiled_graph: 已编译的图，如果为None则使用当前图
            
        Returns:
            (Mermaid文本表示, PNG图像数据)
        """
        try:
            if compiled_graph is None:
                # 如果没有提供编译图，先编译一个
                graph = self.build_enhanced_graph()
                compiled_graph = self.compile_enhanced_graph(graph)
            
            # 获取图对象
            graph_obj = compiled_graph.get_graph()
            
            # 生成Mermaid文本
            mermaid_text = graph_obj.draw_mermaid()
            
            # 尝试生成PNG图像
            png_data = None
            try:
                png_data = graph_obj.draw_png()
            except Exception as e:
                logger.warning(f"生成PNG图像失败: {str(e)}")
            
            return mermaid_text, png_data
            
        except Exception as e:
            logger.error(f"可视化增强版图失败: {str(e)}")
            return f"可视化失败: {str(e)}", None

    def _create_standard_nodes(self) -> Dict[str, Callable]:
        """创建标准节点
        
        Returns:
            标准节点字典
        """
        standard_nodes = {}
        
        # 主智能体节点
        def main_agent_node(state: IsotopeSystemState) -> IsotopeSystemState:
            """标准主智能体节点"""
            try:
                # 兼容阶段1和阶段2的智能体获取方式
                main_agent = self.agents.get("supervisor_agent") or self.agents.get("main_agent")
                if not main_agent:
                    # 确保messages列表存在
                    if "messages" not in state or state["messages"] is None:
                        state["messages"] = []
                    state["messages"].append({"role": "assistant", "content": "主智能体不可用"})
                    return state
                
                # 确保messages列表存在
                if "messages" not in state or state["messages"] is None:
                    state["messages"] = []
                
                if state["messages"] and len(state["messages"]) > 0:
                    last_message = state["messages"][-1]
                    if isinstance(last_message, dict) and last_message.get("role") == "user":
                        content = last_message.get("content", "")
                        
                        if hasattr(main_agent, "invoke"):
                            response = main_agent.invoke(content)
                        elif callable(main_agent):
                            # 如果是可调用对象，调用它并传入状态
                            result_state = main_agent(state)
                            return result_state if result_state else state
                        else:
                            response = "主智能体未实现invoke方法"
                            
                        state["messages"].append({"role": "assistant", "content": str(response)})
                return state
            except Exception as e:
                logger.error(f"主智能体节点执行失败: {str(e)}")
                # 确保messages列表存在
                if "messages" not in state or state["messages"] is None:
                    state["messages"] = []
                state["messages"].append({"role": "assistant", "content": f"执行出错: {str(e)}"})
                return state
        
        # 数据智能体节点
        def data_agent_node(state: IsotopeSystemState) -> IsotopeSystemState:
            """标准数据智能体节点"""
            try:
                data_agent = self.agents.get("data_agent")
                if not data_agent:
                    # 如果没有数据智能体，直接返回状态不报错
                    return state
                
                # 确保messages列表存在
                if "messages" not in state or state["messages"] is None:
                    state["messages"] = []
                
                if state["messages"] and len(state["messages"]) > 0:
                    last_message = state["messages"][-1]
                    if isinstance(last_message, dict) and last_message.get("role") == "user":
                        content = last_message.get("content", "")
                        
                        if hasattr(data_agent, "run"):
                            logger.info("调用数据智能体的run方法")
                            # DataAgent使用run方法，传入完整状态
                            result = data_agent.run(state)
                            
                            # run方法返回的是完整的更新后的状态
                            if isinstance(result, dict):
                                # 如果返回的是状态字典，更新当前状态
                                logger.info("数据智能体返回了状态字典")
                                for key, value in result.items():
                                    state[key] = value
                            else:
                                logger.warning(f"数据智能体返回了意外的结果类型: {type(result)}")
                                
                        elif hasattr(data_agent, "invoke"):
                            logger.info("调用数据智能体的invoke方法")
                            response = data_agent.invoke(content)
                            
                            # 确保响应是字符串格式
                            if hasattr(response, 'content'):
                                response_content = response.content
                            else:
                                response_content = str(response)
                                
                            logger.info(f"数据智能体回复: {response_content[:100]}...")
                            state["messages"].append({"role": "assistant", "content": response_content})
                            
                        elif callable(data_agent):
                            logger.info("数据智能体是可调用对象，直接调用")
                            # 如果是可调用对象，调用它并传入状态
                            result_state = data_agent(state)
                            if result_state:
                                logger.info("数据智能体返回了新状态")
                                return result_state
                            else:
                                logger.warning("数据智能体返回空状态，使用原状态")
                                state["messages"].append({"role": "assistant", "content": "数据智能体处理完成"})
                        else:
                            logger.warning("数据智能体既不是run也不是invoke也不是callable，生成默认回复")
                            response_content = f"数据智能体已处理消息: {content[:50]}..."
                            state["messages"].append({"role": "assistant", "content": response_content})
                            
                return state
            except Exception as e:
                logger.error(f"数据智能体节点执行失败: {str(e)}")
                # 确保messages列表存在
                if "messages" not in state or state["messages"] is None:
                    state["messages"] = []
                state["messages"].append({"role": "assistant", "content": f"数据智能体执行出错: {str(e)}"})
                return state
        
        standard_nodes["main_agent"] = main_agent_node
        
        # 只有在有数据智能体时才添加数据智能体节点
        if self.agents.get("data_agent"):
            standard_nodes["data_agent"] = data_agent_node
        
        return standard_nodes 

    def get_active_checkpointer(self):
        """获取当前活跃的检查点器
        
        Returns:
            当前可用的检查点器实例，如果都不可用则返回None
        """
        # 优先使用PostgreSQL检查点器
        if (self.postgres_checkpoint_manager and 
            self.postgres_checkpoint_manager.is_postgres_available() and 
            self.postgres_checkpoint_manager.test_connection()):
            return self.postgres_checkpoint_manager.get_checkpointer()
        
        # 然后尝试MySQL检查点器
        if (self.mysql_checkpoint_manager and 
            hasattr(self.mysql_checkpoint_manager, 'test_connection') and
            self.mysql_checkpoint_manager.test_connection()):
            return self.mysql_checkpoint_manager.get_checkpointer()
        
        # 最后回退到内存检查点器
        try:
            from langgraph.checkpoint.memory import MemorySaver
            logger.info("回退到内存检查点器")
            return MemorySaver()
        except Exception as e:
            logger.error(f"创建内存检查点器失败: {str(e)}")
            return None
    
    def get_checkpoint_status(self) -> Dict[str, Any]:
        """获取检查点系统状态
        
        Returns:
            检查点系统状态信息
        """
        status = {
            "postgres_available": False,
            "mysql_available": False,
            "active_backend": "none",
            "fallback_to_memory": False
        }
        
        # 检查PostgreSQL状态
        if self.postgres_checkpoint_manager:
            try:
                status["postgres_available"] = (
                    self.postgres_checkpoint_manager.is_postgres_available() and
                    self.postgres_checkpoint_manager.test_connection()
                )
                if status["postgres_available"]:
                    status["active_backend"] = "postgres"
            except Exception as e:
                logger.warning(f"检查PostgreSQL状态失败: {str(e)}")
        
        # 检查MySQL状态
        if self.mysql_checkpoint_manager:
            try:
                mysql_available = (
                    hasattr(self.mysql_checkpoint_manager, 'test_connection') and
                    self.mysql_checkpoint_manager.test_connection()
                )
                status["mysql_available"] = mysql_available
                if mysql_available and status["active_backend"] == "none":
                    status["active_backend"] = "mysql"
            except Exception as e:
                logger.warning(f"检查MySQL状态失败: {str(e)}")
        
        # 如果都不可用，标记回退到内存
        if status["active_backend"] == "none":
            status["fallback_to_memory"] = True
            status["active_backend"] = "memory"
        
        return status
    
    def _ensure_state_fields(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """确保状态包含所有必需字段
        
        Args:
            state: 当前状态
            
        Returns:
            包含所有必需字段的状态
        """
        if not isinstance(state, dict):
            state = {}
        
        # 定义必需字段及其默认值
        required_fields = {
            "messages": [],
            "action_history": [],
            "files": [],
            "current_task": None,
            "tool_results": [],
            "metadata": {},
            "task_results": [],
            "agent_analysis": {}
        }
        
        # 确保所有字段存在且不为None（修复状态传递问题）
        for field, default_value in required_fields.items():
            if field not in state or state[field] is None:
                state[field] = default_value
        
        return state
    
    def _get_default_llm(self):
        """获取默认的LLM实例"""
        try:
            from app.utils.qwen_chat import SFChatOpenAI
            return SFChatOpenAI(
                model="Qwen/Qwen2.5-72B-Instruct",
                temperature=0.1,
                max_tokens=4000  # 修复：适配模型上下文限制
            )
        except Exception as e:
            logger.warning(f"无法创建默认LLM: {e}")
            try:
                # 回退到基础ChatOpenAI，但要使用正确的模型
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(
                    model="Qwen/Qwen2.5-72B-Instruct",
                    temperature=0.1
                )
            except Exception as e2:
                logger.error(f"创建回退LLM也失败: {e2}")
                return None