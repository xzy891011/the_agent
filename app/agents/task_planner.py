"""
任务规划器智能体 - 将用户需求拆解为可执行的Task DAG
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional
from enum import Enum
from langchain_core.language_models import BaseChatModel
from app.core.state import IsotopeSystemState, StateManager, TaskStatus
from app.agents.registry import AgentProtocol

logger = logging.getLogger(__name__)

class TaskPriority(str, Enum):
    """任务优先级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class TaskPlan:
    """任务计划类 - 包含DAG结构的任务执行计划"""
    
    def __init__(
        self,
        task_id: str,
        task_type: str,
        description: str,
        priority: TaskPriority = TaskPriority.MEDIUM,
        steps: Optional[List[Dict[str, Any]]] = None,
        parallel_groups: Optional[Dict[str, List[str]]] = None,
        dependencies: Optional[Dict[str, List[str]]] = None,
        estimated_duration: Optional[int] = None,
        requires_human_approval: bool = False,
        retry_policy: Optional[Dict[str, Any]] = None,
        mcp_tools_required: Optional[List[str]] = None
    ):
        self.task_id = task_id
        self.task_type = task_type
        self.description = description
        self.priority = priority
        self.steps = steps or []
        self.parallel_groups = parallel_groups or {}
        self.dependencies = dependencies or {}
        self.estimated_duration = estimated_duration
        self.requires_human_approval = requires_human_approval
        self.retry_policy = retry_policy or {"max_retries": 1, "backoff": "exponential"}
        self.mcp_tools_required = mcp_tools_required or []
        self.created_at = datetime.now()
        self.status = TaskStatus.NOT_STARTED
        self.current_step = 0
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "description": self.description,
            "priority": self.priority.value,
            "steps": self.steps,
            "parallel_groups": self.parallel_groups,
            "dependencies": self.dependencies,
            "estimated_duration": self.estimated_duration,
            "requires_human_approval": self.requires_human_approval,
            "retry_policy": self.retry_policy,
            "mcp_tools_required": self.mcp_tools_required,
            "created_at": self.created_at.isoformat(),
            "status": self.status.value,
            "current_step": self.current_step
        }
    
    def get_next_executable_steps(self) -> List[Dict[str, Any]]:
        """获取下一步可执行的任务步骤（考虑依赖关系）"""
        executable_steps = []
        
        for i, step in enumerate(self.steps):
            if i <= self.current_step:
                continue  # 已完成的步骤
                
            step_id = step.get("step_id", f"step_{i}")
            dependencies = self.dependencies.get(step_id, [])
            
            # 检查依赖是否都已完成
            dependencies_met = all(
                any(completed_step.get("step_id") == dep_id 
                    for completed_step in self.steps[:self.current_step])
                for dep_id in dependencies
            )
            
            if dependencies_met:
                executable_steps.append(step)
        
        return executable_steps

class TaskPlanner(AgentProtocol):
    """任务规划器 - 基于LLM生成动态Task DAG"""
    
    def __init__(
        self, 
        llm: BaseChatModel, 
        config: Optional[Dict[str, Any]] = None,
        memory_integration: Optional[Any] = None,
        info_hub: Optional[Any] = None
    ):
        self.llm = llm
        self.config = config or {}
        self.name = "task_planner"
        self.description = "任务规划器，负责将用户需求拆解为可并行执行的Task DAG"
        
        # 增强功能模块
        self.memory_integration = memory_integration
        self.info_hub = info_hub
        
        # 获取系统能力和任务注册表
        try:
            from app.core.system_capability_registry import get_system_capabilities, system_capability_registry
            from app.core.task_decorator import task_registry
            self.system_capabilities = get_system_capabilities()
            self.capability_registry = system_capability_registry
            self.task_registry = task_registry
        except ImportError:
            logger.warning("无法导入系统能力注册表，使用默认设置")
            self.system_capabilities = {}
            self.capability_registry = None
            self.task_registry = None
    
    def run(self, state: IsotopeSystemState) -> IsotopeSystemState:
        """执行任务规划"""
        logger.info("TaskPlanner开始任务规划")
        
        try:
            # 获取MetaSupervisor的分析结果
            analysis = state.get("metadata", {}).get("task_analysis", {})
            strategy = state.get("metadata", {}).get("execution_strategy", {})
            
            if not analysis:
                raise ValueError("缺少任务分析结果，TaskPlanner需要MetaSupervisor的输出")
            
            # 创建任务计划
            task_plan = self.create_task_plan(analysis, strategy, state)
            
            # 更新状态
            state["metadata"]["task_plan"] = task_plan.to_dict()
            state["metadata"]["planned_by"] = self.name
            
            logger.info(f"TaskPlanner规划完成，共{len(task_plan.steps)}个步骤")
            return state
            
        except Exception as e:
            logger.error(f"TaskPlanner执行失败: {str(e)}")
            # 创建简单的fallback计划
            fallback_plan = self._create_fallback_plan(state)
            state["metadata"]["task_plan"] = fallback_plan.to_dict()
            state["metadata"]["planned_by"] = f"{self.name}_fallback"
            return state
    
    def get_name(self) -> str:
        return self.name
    
    def get_description(self) -> str:
        return self.description
    
    def create_task_plan(
        self, 
        analysis: Dict[str, Any], 
        strategy: Dict[str, Any],
        state: IsotopeSystemState
    ) -> TaskPlan:
        """基于分析结果和策略创建任务执行计划"""
        
        task_type = analysis.get("task_type", "consultation")
        complexity = analysis.get("complexity", "simple")
        suggested_agents = analysis.get("suggested_agents", ["general_analysis"])
        
        # 根据任务类型创建专业化计划
        if task_type == "seismic_processing":
            return self._create_seismic_processing_plan(analysis, strategy, state)
        elif task_type == "logging_reconstruction":
            return self._create_logging_reconstruction_plan(analysis, strategy, state)
        elif task_type == "well_logging_analysis":
            return self._create_well_logging_analysis_plan(analysis, strategy, state)
        elif task_type == "structure_recognition":
            return self._create_structure_recognition_plan(analysis, strategy, state)
        elif task_type == "well_seismic_fusion":
            return self._create_well_seismic_fusion_plan(analysis, strategy, state)
        elif task_type == "reservoir_modeling":
            return self._create_reservoir_modeling_plan(analysis, strategy, state)
        elif task_type == "reservoir_simulation":
            return self._create_reservoir_simulation_plan(analysis, strategy, state)
        elif task_type == "multi_step":
            return self._create_multi_step_plan(analysis, strategy, state)
        else:
            return self._create_consultation_plan(analysis, strategy, state)
    
    def _create_seismic_processing_plan(
        self, 
        analysis: Dict[str, Any], 
        strategy: Dict[str, Any], 
        state: IsotopeSystemState
    ) -> TaskPlan:
        """创建地震处理任务计划"""
        
        task_id = f"seismic_{uuid.uuid4().hex[:8]}"
        
        # 地震处理标准流程步骤
        steps = [
            {
                "step_id": "data_qc",
                "agent": "seismic_agent",
                "action": "quality_control",
                "description": "地震数据质量检查",
                "mcp_tools": ["seismic_data_loader", "data_qc_tools"],
                "estimated_duration": 10,
                "parallel_group": "preparation"
            },
            {
                "step_id": "noise_reduction",
                "agent": "seismic_agent", 
                "action": "denoise",
                "description": "地震数据去噪处理",
                "mcp_tools": ["denoise_filter", "spectral_whitening"],
                "estimated_duration": 30,
                "parallel_group": "processing_1"
            },
            {
                "step_id": "deconvolution",
                "agent": "seismic_agent",
                "action": "deconvolution",
                "description": "反褶积处理",
                "mcp_tools": ["predictive_decon", "spike_decon"],
                "estimated_duration": 25,
                "parallel_group": "processing_1"
            },
            {
                "step_id": "migration",
                "agent": "seismic_agent",
                "action": "migration",
                "description": "偏移处理",
                "mcp_tools": ["time_migration", "depth_migration"],
                "estimated_duration": 45,
                "depends_on": ["noise_reduction", "deconvolution"]
            },
            {
                "step_id": "attribute_analysis",
                "agent": "seismic_agent",
                "action": "compute_attributes",
                "description": "地震属性计算",
                "mcp_tools": ["coherence_attr", "curvature_attr", "amplitude_attr"],
                "estimated_duration": 20,
                "parallel_group": "analysis",
                "depends_on": ["migration"]
            },
            {
                "step_id": "interpretation",
                "agent": "seismic_agent",
                "action": "interpret",
                "description": "地震解释",
                "mcp_tools": ["fault_detection", "horizon_picking"],
                "estimated_duration": 40,
                "depends_on": ["attribute_analysis"],
                "requires_human": True
            }
        ]
        
        # 定义并行组
        parallel_groups = {
            "preparation": ["data_qc"],
            "processing_1": ["noise_reduction", "deconvolution"],
            "analysis": ["attribute_analysis"]
        }
        
        # 定义依赖关系
        dependencies = {
            "migration": ["noise_reduction", "deconvolution"],
            "attribute_analysis": ["migration"],
            "interpretation": ["attribute_analysis"]
        }
        
        # 收集所需的MCP工具
        mcp_tools = []
        for step in steps:
            mcp_tools.extend(step.get("mcp_tools", []))
        
        return TaskPlan(
            task_id=task_id,
            task_type="seismic_processing",
            description="地震数据处理与解释完整流程",
            priority=TaskPriority.HIGH,
            steps=steps,
            parallel_groups=parallel_groups,
            dependencies=dependencies,
            estimated_duration=sum(step.get("estimated_duration", 0) for step in steps),
            requires_human_approval=True,
            mcp_tools_required=list(set(mcp_tools))
        )
    
    def _create_logging_reconstruction_plan(
        self, 
        analysis: Dict[str, Any], 
        strategy: Dict[str, Any], 
        state: IsotopeSystemState
    ) -> TaskPlan:
        """创建测井数据重构任务计划"""
        
        task_id = f"logging_recon_{uuid.uuid4().hex[:8]}"
        
        steps = [
            {
                "step_id": "data_validation",
                "agent": "logging_agent",
                "action": "validate_data",
                "description": "测井数据验证",
                "mcp_tools": ["log_data_loader", "data_validator"],
                "estimated_duration": 5
            },
            {
                "step_id": "curve_analysis",
                "agent": "logging_agent",
                "action": "analyze_curves",
                "description": "测井曲线分析",
                "mcp_tools": ["curve_analyzer", "missing_detector"],
                "estimated_duration": 10,
                "depends_on": ["data_validation"]
            },
            {
                "step_id": "reconstruction",
                "agent": "logging_agent",
                "action": "reconstruct_curves",
                "description": "缺失曲线重构",
                "mcp_tools": ["neural_reconstructor", "statistical_interpolator"],
                "estimated_duration": 30,
                "depends_on": ["curve_analysis"]
            },
            {
                "step_id": "quality_check",
                "agent": "quality_control",
                "action": "validate_reconstruction",
                "description": "重构结果质量检查",
                "mcp_tools": ["qc_validator", "statistical_analyzer"],
                "estimated_duration": 10,
                "depends_on": ["reconstruction"]
            }
        ]
        
        dependencies = {
            "curve_analysis": ["data_validation"],
            "reconstruction": ["curve_analysis"],
            "quality_check": ["reconstruction"]
        }
        
        mcp_tools = ["log_data_loader", "data_validator", "curve_analyzer", 
                    "missing_detector", "neural_reconstructor", "statistical_interpolator",
                    "qc_validator", "statistical_analyzer"]
        
        return TaskPlan(
            task_id=task_id,
            task_type="logging_reconstruction",
            description="测井数据重构补全流程",
            priority=TaskPriority.MEDIUM,
            steps=steps,
            dependencies=dependencies,
            estimated_duration=55,
            mcp_tools_required=mcp_tools
        )
    
    def _create_well_logging_analysis_plan(
        self,
        analysis: Dict[str, Any],
        strategy: Dict[str, Any], 
        state: IsotopeSystemState
    ) -> TaskPlan:
        """创建录井资料分析任务计划"""
        
        task_id = f"well_log_{uuid.uuid4().hex[:8]}"
        
        steps = [
            {
                "step_id": "sample_preparation",
                "agent": "logging_agent",
                "action": "prepare_samples",
                "description": "岩屑样品预处理",
                "mcp_tools": ["sample_processor", "image_analyzer"],
                "estimated_duration": 15
            },
            {
                "step_id": "lithology_analysis",
                "agent": "logging_agent",
                "action": "analyze_lithology",
                "description": "岩性分析",
                "mcp_tools": ["lithology_classifier", "mineral_identifier"],
                "estimated_duration": 20,
                "parallel_group": "analysis"
            },
            {
                "step_id": "show_detection",
                "agent": "logging_agent",
                "action": "detect_shows",
                "description": "油气显示识别",
                "mcp_tools": ["fluorescence_detector", "hydrocarbon_analyzer"],
                "estimated_duration": 25,
                "parallel_group": "analysis"
            },
            {
                "step_id": "interpretation",
                "agent": "logging_agent",
                "action": "interpret_results",
                "description": "综合解释",
                "mcp_tools": ["interpretation_engine", "report_generator"],
                "estimated_duration": 30,
                "depends_on": ["lithology_analysis", "show_detection"],
                "requires_human": True
            }
        ]
        
        parallel_groups = {
            "analysis": ["lithology_analysis", "show_detection"]
        }
        
        dependencies = {
            "interpretation": ["lithology_analysis", "show_detection"]
        }
        
        mcp_tools = ["sample_processor", "image_analyzer", "lithology_classifier",
                    "mineral_identifier", "fluorescence_detector", "hydrocarbon_analyzer",
                    "interpretation_engine", "report_generator"]
        
        return TaskPlan(
            task_id=task_id,
            task_type="well_logging_analysis",
            description="录井资料处理与解释流程",
            priority=TaskPriority.MEDIUM,
            steps=steps,
            parallel_groups=parallel_groups,
            dependencies=dependencies,
            estimated_duration=90,
            requires_human_approval=True,
            mcp_tools_required=mcp_tools
        )
    
    def _create_structure_recognition_plan(self, analysis: Dict[str, Any], strategy: Dict[str, Any], state: IsotopeSystemState) -> TaskPlan:
        """创建构造识别任务计划"""
        task_id = f"structure_{uuid.uuid4().hex[:8]}"
        # 简化实现
        return self._create_simple_plan(task_id, "structure_recognition", "构造识别流程", ["geophysics_agent"])
    
    def _create_well_seismic_fusion_plan(self, analysis: Dict[str, Any], strategy: Dict[str, Any], state: IsotopeSystemState) -> TaskPlan:
        """创建井震联合任务计划"""
        task_id = f"fusion_{uuid.uuid4().hex[:8]}"
        # 简化实现
        return self._create_simple_plan(task_id, "well_seismic_fusion", "井震联合分析流程", ["seismic_agent", "logging_agent"])
    
    def _create_reservoir_modeling_plan(self, analysis: Dict[str, Any], strategy: Dict[str, Any], state: IsotopeSystemState) -> TaskPlan:
        """创建储层建模任务计划"""
        task_id = f"reservoir_model_{uuid.uuid4().hex[:8]}"
        # 简化实现
        return self._create_simple_plan(task_id, "reservoir_modeling", "储层建模流程", ["reservoir_agent"])
    
    def _create_reservoir_simulation_plan(self, analysis: Dict[str, Any], strategy: Dict[str, Any], state: IsotopeSystemState) -> TaskPlan:
        """创建油藏模拟任务计划"""
        task_id = f"reservoir_sim_{uuid.uuid4().hex[:8]}"
        # 简化实现
        return self._create_simple_plan(task_id, "reservoir_simulation", "油藏数值模拟流程", ["reservoir_agent"])
    
    def _create_multi_step_plan(self, analysis: Dict[str, Any], strategy: Dict[str, Any], state: IsotopeSystemState) -> TaskPlan:
        """创建多步骤复合任务计划"""
        task_id = f"multi_step_{uuid.uuid4().hex[:8]}"
        # TODO: 基于LLM动态生成复合任务计划
        return self._create_simple_plan(task_id, "multi_step", "多步骤复合任务", ["supervisor"])
    
    def _create_consultation_plan(self, analysis: Dict[str, Any], strategy: Dict[str, Any], state: IsotopeSystemState) -> TaskPlan:
        """创建咨询任务计划"""
        task_id = f"consultation_{uuid.uuid4().hex[:8]}"
        return self._create_simple_plan(task_id, "consultation", "一般咨询", ["general_analysis"])
    
    def _create_simple_plan(self, task_id: str, task_type: str, description: str, agents: List[str]) -> TaskPlan:
        """创建简单的单步任务计划"""
        steps = [
            {
                "step_id": "execute",
                "agent": agents[0] if agents else "general_analysis",
                "action": "process",
                "description": description,
                "estimated_duration": 10
            }
        ]
        
        return TaskPlan(
            task_id=task_id,
            task_type=task_type,
            description=description,
            priority=TaskPriority.MEDIUM,
            steps=steps,
            estimated_duration=10
        )
    
    def _create_fallback_plan(self, state: IsotopeSystemState) -> TaskPlan:
        """创建fallback任务计划"""
        return self._create_simple_plan(
            task_id=f"fallback_{uuid.uuid4().hex[:8]}",
            task_type="consultation",
            description="系统fallback处理",
            agents=["general_analysis"]
        )
