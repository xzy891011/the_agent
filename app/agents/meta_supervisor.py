"""
元监督者智能体 - 负责身份校验、需求分析和异常兜底
"""

import logging
from typing import Dict, List, Any, Optional
from langchain_core.language_models import BaseChatModel
from app.core.state import IsotopeSystemState, StateManager
from app.agents.registry import AgentProtocol

logger = logging.getLogger(__name__)

class TaskType:
    """任务类型常量"""
    CONSULTATION = "consultation"
    DATA_ANALYSIS = "data_analysis" 
    EXPERT_ANALYSIS = "expert_analysis"
    MULTI_STEP = "multi_step"
    TOOL_EXECUTION = "tool_execution"
    
    # 油气勘探专业任务类型
    SEISMIC_PROCESSING = "seismic_processing"           # 地震处理与解释
    LOGGING_RECONSTRUCTION = "logging_reconstruction"   # 测井数据重构补全与解释
    WELL_LOGGING_ANALYSIS = "well_logging_analysis"     # 录井资料处理与解释
    STRUCTURE_RECOGNITION = "structure_recognition"     # 构造识别
    WELL_SEISMIC_FUSION = "well_seismic_fusion"        # 井震联合
    RESERVOIR_MODELING = "reservoir_modeling"          # 储层建模
    RESERVOIR_SIMULATION = "reservoir_simulation"      # 油藏模拟

class TaskComplexity:
    """任务复杂度常量"""
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"

class MetaSupervisor(AgentProtocol):
    """元监督者 - 基于LLM的用户意图识别和需求分析"""
    
    def __init__(
        self, 
        llm: BaseChatModel, 
        config: Optional[Dict[str, Any]] = None,
        memory_integration: Optional[Any] = None,
        info_hub: Optional[Any] = None,
        interrupt_manager: Optional[Any] = None
    ):
        self.llm = llm
        self.config = config or {}
        self.name = "meta_supervisor"
        self.description = "元监督者，负责用户意图识别、任务类型分析和执行策略决策"
        
        # 增强功能模块
        self.memory_integration = memory_integration
        self.info_hub = info_hub
        self.interrupt_manager = interrupt_manager
        
        # 获取系统能力
        try:
            from app.core.system_capability_registry import get_system_capabilities, system_capability_registry
            self.system_capabilities = get_system_capabilities()
            self.capability_registry = system_capability_registry
        except ImportError:
            logger.warning("无法导入系统能力注册表，使用默认设置")
            self.system_capabilities = {}
            self.capability_registry = None
    
    def run(self, state: IsotopeSystemState) -> IsotopeSystemState:
        """执行元监督者分析"""
        logger.info("MetaSupervisor开始分析用户请求")
        
        try:
            # 分析用户请求
            analysis = self.analyze_user_request(state)
            
            # 决定执行策略
            strategy = self.decide_execution_strategy(analysis)
            
            # 更新状态
            state["metadata"]["task_analysis"] = analysis
            state["metadata"]["execution_strategy"] = strategy
            state["metadata"]["analyzed_by"] = self.name
            
            logger.info(f"MetaSupervisor分析完成: {analysis.get('task_type', 'unknown')}")
            return state
            
        except Exception as e:
            logger.error(f"MetaSupervisor执行失败: {str(e)}")
            # 提供fallback分析
            fallback_analysis = self._fallback_analysis("系统分析失败")
            state["metadata"]["task_analysis"] = fallback_analysis
            state["metadata"]["execution_strategy"] = self.decide_execution_strategy(fallback_analysis)
            return state
    
    def get_name(self) -> str:
        return self.name
    
    def get_description(self) -> str:
        return self.description
    
    def analyze_user_request(self, state: IsotopeSystemState) -> Dict[str, Any]:
        """基于LLM分析用户请求，识别油气勘探相关任务"""
        
        # 获取最后一条用户消息
        last_human_msg = StateManager.get_last_human_message(state)
        if not last_human_msg:
            return self._fallback_analysis("无用户输入")
        
        user_input = last_human_msg.content
        
        # 构建油气勘探专业分析提示词
        prompt = f"""
        你是油气地质勘探建模系统的智能分析器，请分析用户请求并识别任务类型。

        用户请求: {user_input}

        可用的油气勘探任务类型：
        1. seismic_processing - 地震数据处理与解释（去噪、反褶积、偏移、属性提取等）
        2. logging_reconstruction - 测井数据重构补全与解释（曲线修复、环境校正等）  
        3. well_logging_analysis - 录井资料处理与解释（岩屑分析、油气显示等）
        4. structure_recognition - 构造识别（断层识别、层位追踪等）
        5. well_seismic_fusion - 井震联合（时深转换、井震标定等）
        6. reservoir_modeling - 储层建模（三维地质建模、属性建模等）
        7. reservoir_simulation - 油藏模拟（数值模拟、开发方案优化等）
        8. consultation - 一般咨询问题
        9. multi_step - 需要多个步骤的复合任务

        请基于专业知识分析用户意图，返回JSON格式：
        {{
            "task_type": "任务类型（从上述列表选择）",
            "confidence": 0.0-1.0,
            "required_capabilities": ["所需专业能力列表"],
            "complexity": "simple/medium/complex",
            "requires_human_approval": true/false,
            "requires_mcp_tools": ["可能需要的工具类型"],
            "parallel_executable": true/false,
            "estimated_duration": "预估时长（分钟）",
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
                
                # 验证和标准化任务类型
                analysis["task_type"] = self._validate_task_type(analysis.get("task_type"))
                
                # 添加MCP工具路由信息
                analysis["suggested_agents"] = self._suggest_agents_for_task(analysis["task_type"])
                
                return analysis
            else:
                logger.warning("MetaSupervisor无法解析LLM响应为JSON")
                return self._fallback_analysis(user_input)
        
        except Exception as e:
            logger.error(f"MetaSupervisor LLM分析失败: {str(e)}")
            return self._fallback_analysis(user_input)
    
    def _validate_task_type(self, task_type: str) -> str:
        """验证和标准化任务类型"""
        valid_types = [
            TaskType.SEISMIC_PROCESSING, TaskType.LOGGING_RECONSTRUCTION,
            TaskType.WELL_LOGGING_ANALYSIS, TaskType.STRUCTURE_RECOGNITION,
            TaskType.WELL_SEISMIC_FUSION, TaskType.RESERVOIR_MODELING,
            TaskType.RESERVOIR_SIMULATION, TaskType.CONSULTATION,
            TaskType.MULTI_STEP, TaskType.DATA_ANALYSIS, TaskType.EXPERT_ANALYSIS
        ]
        
        if task_type in valid_types:
            return task_type
        
        # 兼容旧类型
        legacy_mapping = {
            "data_analysis": TaskType.DATA_ANALYSIS,
            "expert_analysis": TaskType.EXPERT_ANALYSIS,
            "tool_execution": TaskType.TOOL_EXECUTION
        }
        
        return legacy_mapping.get(task_type, TaskType.CONSULTATION)
    
    def _suggest_agents_for_task(self, task_type: str) -> List[str]:
        """根据任务类型建议专业智能体"""
        agent_mapping = {
            TaskType.SEISMIC_PROCESSING: ["seismic_agent"],
            TaskType.LOGGING_RECONSTRUCTION: ["logging_agent", "quality_control"],
            TaskType.WELL_LOGGING_ANALYSIS: ["logging_agent"],
            TaskType.STRUCTURE_RECOGNITION: ["geophysics_agent", "seismic_agent"],
            TaskType.WELL_SEISMIC_FUSION: ["seismic_agent", "logging_agent", "geophysics_agent"],
            TaskType.RESERVOIR_MODELING: ["reservoir_agent", "geophysics_agent"],
            TaskType.RESERVOIR_SIMULATION: ["reservoir_agent", "economics_agent"],
            TaskType.MULTI_STEP: ["supervisor", "task_coordinator"],
            TaskType.CONSULTATION: ["general_analysis"]
        }
        
        return agent_mapping.get(task_type, ["general_analysis"])
    
    def _fallback_analysis(self, user_input: str) -> Dict[str, Any]:
        """基于关键词的fallback分析"""
        
        # 油气勘探关键词映射
        task_keywords = {
            TaskType.SEISMIC_PROCESSING: ["地震", "seismic", "震波", "偏移", "反褶积", "去噪", "叠前", "叠后", "属性"],
            TaskType.LOGGING_RECONSTRUCTION: ["测井", "well log", "曲线", "重构", "补全", "环境校正"],
            TaskType.WELL_LOGGING_ANALYSIS: ["录井", "mud log", "岩屑", "油气显示", "荧光", "含油性"],
            TaskType.STRUCTURE_RECOGNITION: ["构造", "断层", "层位", "褶皱", "解释", "追踪"],
            TaskType.WELL_SEISMIC_FUSION: ["井震", "标定", "时深", "合成", "子波"],
            TaskType.RESERVOIR_MODELING: ["储层", "建模", "三维", "属性", "相控", "地质统计"],
            TaskType.RESERVOIR_SIMULATION: ["油藏", "数值模拟", "开发", "注水", "采收率", "优化"]
        }
        
        user_lower = user_input.lower()
        
        # 关键词匹配
        for task_type, keywords in task_keywords.items():
            if any(keyword in user_lower for keyword in keywords):
                return {
                    "task_type": task_type,
                    "confidence": 0.7,
                    "complexity": TaskComplexity.MEDIUM,
                    "reasoning": f"基于关键词匹配识别为{task_type}",
                    "required_capabilities": [task_type],
                    "suggested_agents": self._suggest_agents_for_task(task_type),
                    "requires_mcp_tools": True,
                    "fallback": True
                }
        
        # 默认为咨询
        return {
            "task_type": TaskType.CONSULTATION,
            "confidence": 0.5,
            "complexity": TaskComplexity.SIMPLE,
            "reasoning": "未识别到专业任务关键词，归类为一般咨询",
            "required_capabilities": [],
            "suggested_agents": ["general_analysis"],
            "requires_mcp_tools": False,
            "fallback": True
        }
    
    def decide_execution_strategy(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """基于分析结果决定执行策略"""
        task_type = analysis.get("task_type", TaskType.CONSULTATION)
        complexity = analysis.get("complexity", TaskComplexity.SIMPLE)
        
        # 专业任务需要更复杂的策略
        professional_tasks = [
            TaskType.SEISMIC_PROCESSING, TaskType.LOGGING_RECONSTRUCTION,
            TaskType.WELL_LOGGING_ANALYSIS, TaskType.STRUCTURE_RECOGNITION,
            TaskType.WELL_SEISMIC_FUSION, TaskType.RESERVOIR_MODELING,
            TaskType.RESERVOIR_SIMULATION
        ]
        
        strategy = {
            "use_task_planner": complexity in [TaskComplexity.MEDIUM, TaskComplexity.COMPLEX] or task_type in professional_tasks,
            "use_dynamic_subgraphs": task_type in professional_tasks,
            "requires_human_approval": complexity == TaskComplexity.COMPLEX or analysis.get("requires_human_approval", False),
            "enable_parallel_execution": analysis.get("parallel_executable", False),
            "monitoring_level": "high" if complexity == TaskComplexity.COMPLEX else "medium",
            "use_mcp_tools": analysis.get("requires_mcp_tools", True),
            "suggested_agents": analysis.get("suggested_agents", ["general_analysis"]),
            "max_retries": 3 if complexity == TaskComplexity.COMPLEX else 1,
            "enable_checkpoints": task_type in professional_tasks,
            "human_in_loop_points": ["task_planning", "critical_decisions", "final_review"] if complexity == TaskComplexity.COMPLEX else []
        }
        
        logger.info(f"MetaSupervisor决策策略: {strategy}")
        return strategy
