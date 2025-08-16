"""
Specialized Agents for Extended Capabilities
扩展的专业化智能体角色
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.agents.langgraph_agent import LangGraphAgent, create_langgraph_agent
from app.core.state import IsotopeSystemState, StateManager
from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)


class GeophysicsAgent(LangGraphAgent):
    """地球物理智能体，专门处理地球物理数据分析"""
    
    def __init__(self, llm: Any, config: Optional[Dict[str, Any]] = None):
        """初始化地球物理智能体"""
        capabilities = [
            "seismic_data_analysis",
            "well_log_interpretation",
            "reservoir_characterization",
            "formation_evaluation"
        ]
        
        super().__init__(
            name="geophysics_agent",
            role="geophysics_analysis",
            llm=llm,
            capabilities=capabilities,
            config=config
        )
        
        logger.info("初始化地球物理智能体")
    
    def _capability_matches_role(self, capability_type: Any) -> bool:
        """扩展能力匹配以包含地球物理相关能力"""
        from app.core.system_capability_registry import CapabilityType
        
        # 地球物理智能体可以处理数据处理和分析类型的任务
        allowed_types = [
            CapabilityType.DATA_PROCESSING,
            CapabilityType.ANALYSIS,
            CapabilityType.TOOL
        ]
        
        return capability_type in allowed_types


class ReservoirAgent(LangGraphAgent):
    """油藏智能体，专门处理油藏工程相关分析"""
    
    def __init__(self, llm: Any, config: Optional[Dict[str, Any]] = None):
        """初始化油藏智能体"""
        capabilities = [
            "reservoir_simulation",
            "production_optimization",
            "recovery_factor_estimation",
            "pressure_transient_analysis"
        ]
        
        super().__init__(
            name="reservoir_agent",
            role="reservoir_engineering",
            llm=llm,
            capabilities=capabilities,
            config=config
        )
        
        logger.info("初始化油藏智能体")
    
    def _analyze_request(self, state: IsotopeSystemState) -> IsotopeSystemState:
        """重写分析请求方法，添加油藏特定的分析逻辑"""
        # 首先调用父类方法
        state = super()._analyze_request(state)
        
        # 添加油藏特定的分析
        analysis = state.get("agent_analysis", {})
        
        # 检查是否涉及油藏相关关键词
        last_msg = StateManager.get_last_human_message(state)
        if last_msg:
            content = last_msg.content.lower()
            reservoir_keywords = ["油藏", "产量", "压力", "渗透率", "孔隙度", "饱和度", "采收率"]
            
            if any(keyword in content for keyword in reservoir_keywords):
                analysis["reservoir_related"] = True
                analysis["confidence"] = min(analysis.get("confidence", 0.5) + 0.2, 1.0)
                logger.info("检测到油藏相关请求，提高分析置信度")
        
        state["agent_analysis"] = analysis
        return state


class EconomicsAgent(LangGraphAgent):
    """经济评价智能体，专门处理经济分析和评估"""
    
    def __init__(self, llm: Any, config: Optional[Dict[str, Any]] = None):
        """初始化经济评价智能体"""
        capabilities = [
            "npv_calculation",
            "irr_analysis",
            "sensitivity_analysis",
            "risk_assessment",
            "cost_benefit_analysis"
        ]
        
        super().__init__(
            name="economics_agent",
            role="economic_evaluation",
            llm=llm,
            capabilities=capabilities,
            config=config
        )
        
        logger.info("初始化经济评价智能体")
    
    def _generate_response(self, state: IsotopeSystemState) -> IsotopeSystemState:
        """重写响应生成，添加经济指标的专业格式化"""
        # 获取任务执行结果
        task_results = state.get("task_results", [])
        
        # 检查是否有经济相关的结果
        economic_results = [r for r in task_results if self._is_economic_result(r)]
        
        if economic_results:
            # 生成专业的经济分析报告
            response = self._format_economic_report(economic_results)
            
            ai_message = AIMessage(
                content=response,
                additional_kwargs={
                    "source": self.name,
                    "role": self.role,
                    "report_type": "economic_analysis"
                }
            )
            
            state = StateManager.update_messages(state, ai_message)
            return state
        else:
            # 使用父类的默认响应生成
            return super()._generate_response(state)
    
    def _is_economic_result(self, result: Dict[str, Any]) -> bool:
        """判断是否为经济相关结果"""
        economic_tasks = ["npv", "irr", "sensitivity", "risk", "cost"]
        task_name = result.get("task_name", "").lower()
        return any(keyword in task_name for keyword in economic_tasks)
    
    def _format_economic_report(self, results: List[Dict[str, Any]]) -> str:
        """格式化经济分析报告"""
        report = "## 经济评价分析报告\n\n"
        report += f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        for result in results:
            task_name = result.get("task_name", "未知任务")
            status = result.get("status", "unknown")
            
            if status == "success":
                report += f"### {task_name}\n"
                report += f"执行状态: ✅ 成功\n"
                
                # 根据不同的任务类型格式化结果
                if "npv" in task_name.lower():
                    report += self._format_npv_result(result.get("result", {}))
                elif "irr" in task_name.lower():
                    report += self._format_irr_result(result.get("result", {}))
                else:
                    report += f"结果: {result.get('result', '无结果')}\n"
            else:
                report += f"### {task_name}\n"
                report += f"执行状态: ❌ 失败\n"
                report += f"错误信息: {result.get('error', '未知错误')}\n"
            
            report += "\n"
        
        return report
    
    def _format_npv_result(self, npv_data: Any) -> str:
        """格式化NPV结果"""
        if isinstance(npv_data, dict):
            return f"""
净现值(NPV): ${npv_data.get('value', 0):,.2f}
折现率: {npv_data.get('discount_rate', 0)*100:.1f}%
评价期: {npv_data.get('period', 0)}年
"""
        else:
            return f"净现值: {npv_data}\n"
    
    def _format_irr_result(self, irr_data: Any) -> str:
        """格式化IRR结果"""
        if isinstance(irr_data, dict):
            return f"""
内部收益率(IRR): {irr_data.get('value', 0)*100:.2f}%
投资回收期: {irr_data.get('payback_period', 0):.1f}年
"""
        else:
            return f"内部收益率: {irr_data}\n"


class QualityControlAgent(LangGraphAgent):
    """质量控制智能体，专门进行数据质量检查和验证"""
    
    def __init__(self, llm: Any, config: Optional[Dict[str, Any]] = None):
        """初始化质量控制智能体"""
        capabilities = [
            "data_validation",
            "outlier_detection",
            "consistency_check",
            "completeness_check",
            "accuracy_verification"
        ]
        
        super().__init__(
            name="quality_control_agent",
            role="quality_assurance",
            llm=llm,
            capabilities=capabilities,
            config=config
        )
        
        logger.info("初始化质量控制智能体")
    
    def _execute_task(self, state: IsotopeSystemState) -> IsotopeSystemState:
        """重写任务执行，添加质量检查的前置和后置处理"""
        # 执行前的数据质量检查
        state = self._pre_execution_check(state)
        
        # 调用父类执行任务
        state = super()._execute_task(state)
        
        # 执行后的结果验证
        state = self._post_execution_validation(state)
        
        return state
    
    def _pre_execution_check(self, state: IsotopeSystemState) -> IsotopeSystemState:
        """执行前的数据质量检查"""
        logger.info("执行前置数据质量检查")
        
        # 检查输入数据的完整性
        files = state.get("files", [])
        if files:
            quality_issues = []
            
            for file_info in files:
                # 检查文件是否存在必要字段
                if not file_info.get("name"):
                    quality_issues.append("文件缺少名称")
                if not file_info.get("type"):
                    quality_issues.append("文件缺少类型信息")
            
            if quality_issues:
                state["quality_warnings"] = quality_issues
                logger.warning(f"发现数据质量问题: {quality_issues}")
        
        return state
    
    def _post_execution_validation(self, state: IsotopeSystemState) -> IsotopeSystemState:
        """执行后的结果验证"""
        logger.info("执行后置结果验证")
        
        # 验证任务执行结果
        task_results = state.get("task_results", [])
        
        for result in task_results:
            if result.get("status") == "success":
                # 验证结果的合理性
                self._validate_result_reasonableness(result)
        
        return state
    
    def _validate_result_reasonableness(self, result: Dict[str, Any]) -> None:
        """验证结果的合理性"""
        task_name = result.get("task_name", "")
        task_result = result.get("result")
        
        # 根据不同任务类型进行合理性验证
        if "isotope" in task_name.lower() and isinstance(task_result, dict):
            # 检查同位素值的合理范围
            isotope_value = task_result.get("value")
            if isotope_value is not None:
                if isotope_value < -100 or isotope_value > 100:
                    logger.warning(f"同位素值 {isotope_value} 可能超出合理范围")


class GeneralAnalysisAgent(LangGraphAgent):
    """通用分析智能体，处理不属于特定专业领域的分析任务"""
    
    def __init__(self, llm: Any, config: Optional[Dict[str, Any]] = None):
        """初始化通用分析智能体"""
        capabilities = [
            "general_data_processing",
            "basic_statistical_analysis",
            "data_visualization",
            "report_generation",
            "cross_domain_analysis"
        ]
        
        super().__init__(
            name="general_analysis_agent",
            role="general_analysis",
            llm=llm,
            capabilities=capabilities,
            config=config
        )
        
        logger.info("初始化通用分析智能体")
    
    def _capability_matches_role(self, capability_type: Any) -> bool:
        """通用分析智能体可以处理所有类型的基础任务"""
        from app.core.system_capability_registry import CapabilityType
        
        # 通用智能体可以处理大部分类型的任务，作为兜底方案
        allowed_types = [
            CapabilityType.DATA_PROCESSING,
            CapabilityType.ANALYSIS,
            CapabilityType.VISUALIZATION,
            CapabilityType.TOOL
        ]
        
        return capability_type in allowed_types
    
    def _analyze_request(self, state: IsotopeSystemState) -> IsotopeSystemState:
        """重写分析请求方法，添加通用分析逻辑"""
        # 首先调用父类方法
        state = super()._analyze_request(state)
        
        # 添加通用分析的特殊处理
        analysis = state.get("agent_analysis", {})
        
        # 检查是否为跨领域或综合性任务
        last_msg = StateManager.get_last_human_message(state)
        if last_msg:
            content = last_msg.content.lower()
            
            # 跨领域关键词
            cross_domain_keywords = ["综合", "整体", "全面", "比较", "对比", "总结", "汇总"]
            # 基础分析关键词
            basic_keywords = ["统计", "描述", "概况", "基本", "简单"]
            
            if any(keyword in content for keyword in cross_domain_keywords):
                analysis["cross_domain"] = True
                analysis["confidence"] = min(analysis.get("confidence", 0.5) + 0.3, 1.0)
                logger.info("检测到跨领域分析请求")
                
            elif any(keyword in content for keyword in basic_keywords):
                analysis["basic_analysis"] = True
                analysis["confidence"] = min(analysis.get("confidence", 0.5) + 0.2, 1.0)
                logger.info("检测到基础分析请求")
        
        state["agent_analysis"] = analysis
        return state


def create_specialized_agent(
    agent_type: str,
    llm: Any,
    config: Optional[Dict[str, Any]] = None
) -> Optional[LangGraphAgent]:
    """
    工厂函数：创建专业化智能体
    
    Args:
        agent_type: 智能体类型
        llm: 语言模型
        config: 配置参数
        
    Returns:
        专业化智能体实例，如果类型无效则返回None
    """
    agent_classes = {
        "geophysics": GeophysicsAgent,
        "reservoir": ReservoirAgent,
        "economics": EconomicsAgent,
        "quality_control": QualityControlAgent,
        "general_analysis": GeneralAnalysisAgent  # 新增通用分析智能体
    }
    
    agent_class = agent_classes.get(agent_type)
    if agent_class:
        return agent_class(llm=llm, config=config)
    else:
        logger.warning(f"未知的智能体类型: {agent_type}")
        return None


def get_available_agent_types() -> List[str]:
    """获取所有可用的智能体类型"""
    return [
        "geophysics",      # 地球物理
        "reservoir",       # 油藏工程
        "economics",       # 经济评价
        "quality_control", # 质量控制
        "general_analysis" # 通用分析
    ]


def recommend_agent_for_request(request: str, llm=None) -> str:
    """
    使用LLM智能推荐最合适的智能体类型
    
    Args:
        request: 用户请求内容
        llm: 语言模型实例，如果未提供则使用关键字匹配作为fallback
        
    Returns:
        推荐的智能体类型
    """
    if llm is None:
        # Fallback到关键字匹配
        return _keyword_based_recommendation(request)
    
    try:
        # 使用LLM进行智能意图识别
        prompt = f"""请根据以下用户请求，分析用户的意图并推荐最合适的专业智能体。

可选的智能体类型及其专业领域：
1. geophysics - 地球物理：地震数据分析、测井解释、储层表征、地层评价
2. reservoir - 油藏工程：油藏模拟、产量优化、采收率评估、压力分析
3. economics - 经济评价：NPV计算、IRR分析、敏感性分析、风险评估、成本效益分析
4. quality_control - 质量控制：数据验证、异常检测、一致性检查、准确性验证
5. general_analysis - 通用分析：基础统计分析、数据可视化、报告生成、跨领域分析
6. logging - 录井资料处理：数据清洗、曲线重构补全、岩性解释、油气显示识别
7. seismic - 地震处理与解释：去噪、反褶积、时深转换、属性计算、断层层位解释

特殊情况处理：
- 如果是简单的身份确认问题（如"你是谁"、"你好"、"介绍一下"），推荐 "identity_response"
- 如果是通用咨询或不明确的请求，推荐 "general_analysis"

用户请求："{request}"

请只返回推荐的智能体类型（如 "geophysics" 或 "identity_response"），不要包含其他内容。"""

        response = llm.invoke(prompt)
        
        # 提取推荐结果
        if hasattr(response, 'content'):
            recommendation = response.content.strip().lower()
        else:
            recommendation = str(response).strip().lower()
        
        # 验证推荐结果是否有效
        valid_types = ["geophysics", "reservoir", "economics", "quality_control", 
                      "general_analysis", "logging", "seismic", "identity_response"]
        
        if recommendation in valid_types:
            logger.info(f"LLM智能推荐: {request[:50]}... -> {recommendation}")
            return recommendation
        else:
            logger.warning(f"LLM返回无效推荐类型: {recommendation}，使用关键字匹配作为fallback")
            return _keyword_based_recommendation(request)
            
    except Exception as e:
        logger.error(f"LLM智能推荐失败: {e}，使用关键字匹配作为fallback")
        return _keyword_based_recommendation(request)


def _keyword_based_recommendation(request: str) -> str:
    """
    基于关键字的智能体推荐（作为LLM的fallback方案）
    """
    request_lower = request.lower()
    
    # 录井资料相关关键词（优先级较高，更专业化）
    if any(keyword in request_lower for keyword in ["录井", "岩性", "油气显示", "曲线重构", "测井曲线"]):
        return "logging"
    
    # 地震处理相关关键词（优先级较高，更专业化）
    elif any(keyword in request_lower for keyword in ["地震处理", "地震解释", "去噪", "反褶积", 
                                                       "时深转换", "属性体", "断层", "层位"]):
        return "seismic"
    
    # 地球物理相关关键词（更通用）
    elif any(keyword in request_lower for keyword in ["地震", "测井", "储层", "地层", "构造"]):
        return "geophysics"
    
    # 油藏工程相关关键词
    elif any(keyword in request_lower for keyword in ["油藏", "产量", "压力", "渗透", "采收"]):
        return "reservoir"
    
    # 经济评价相关关键词
    elif any(keyword in request_lower for keyword in ["经济", "成本", "收益", "投资", "npv", "irr"]):
        return "economics"
    
    # 质量控制相关关键词
    elif any(keyword in request_lower for keyword in ["质量", "检查", "验证", "校验", "异常"]):
        return "quality_control"
    
    # 简单身份确认问题
    elif any(keyword in request_lower for keyword in ["你是谁", "你好", "介绍", "身份", "hello", "hi"]):
        return "identity_response"
    
    # 默认使用通用分析智能体
    else:
        return "general_analysis" 