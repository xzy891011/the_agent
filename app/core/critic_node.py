"""
Critic Node模块 - 阶段1实现

该模块实现质量与安全审查节点，负责：
1. LLM + 规则的质量审查
2. 安全策略检查
3. 结果验证和评估
4. 失败时的重新规划或用户交互决策
"""

import logging
import json
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Union, Literal
from enum import Enum

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from pydantic import BaseModel, Field

from app.core.state import IsotopeSystemState, StateManager, TaskStatus
from app.core.system_capability_registry import get_system_capability_registry
from app.core.memory.enhanced_memory_integration import EnhancedMemoryIntegration
from app.tools.registry import task_registry

logger = logging.getLogger(__name__)

class CriticLevel(str, Enum):
    """审查级别枚举"""
    INFO = "info"          # 信息级别
    WARNING = "warning"    # 警告级别
    ERROR = "error"        # 错误级别
    CRITICAL = "critical"  # 严重错误级别

class CriticResult(BaseModel):
    """审查结果模型"""
    passed: bool = Field(description="是否通过审查")
    level: CriticLevel = Field(description="审查级别")
    score: float = Field(description="质量评分 (0.0-1.0)", ge=0.0, le=1.0)
    issues: List[str] = Field(default_factory=list, description="发现的问题列表")
    recommendations: List[str] = Field(default_factory=list, description="改进建议")
    next_action: Literal["continue", "replan", "interrupt", "abort"] = Field(description="下一步动作")
    reasoning: str = Field(description="审查推理过程")

class SafetyPolicy:
    """安全策略类"""
    
    def __init__(self):
        self.forbidden_operations = [
            "system_shutdown", "delete_all", "format_disk",
            "modify_system_files", "network_attack"
        ]
        self.restricted_file_patterns = [
            r".*\.exe$", r".*\.bat$", r".*\.sh$", r".*\.ps1$"
        ]
        self.max_file_size = 100 * 1024 * 1024  # 100MB
        self.max_processing_time = 3600  # 1小时
        
    def check_operation_safety(self, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """检查操作安全性"""
        issues = []
        
        # 检查禁止操作
        if operation.lower() in self.forbidden_operations:
            issues.append(f"禁止的危险操作: {operation}")
        
        # 检查文件相关操作
        if "file" in params:
            file_path = params.get("file", "")
            import re
            for pattern in self.restricted_file_patterns:
                if re.match(pattern, file_path, re.IGNORECASE):
                    issues.append(f"限制的文件类型: {file_path}")
        
        # 检查文件大小
        if "file_size" in params and params["file_size"] > self.max_file_size:
            issues.append(f"文件大小超限: {params['file_size']} > {self.max_file_size}")
        
        return {
            "safe": len(issues) == 0,
            "issues": issues
        }

class QualityChecker:
    """质量检查器"""
    
    def __init__(self):
        self.min_content_length = 10
        self.max_content_length = 10000
        self.required_fields = ["content", "timestamp"]
        
    def check_content_quality(self, content: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """检查内容质量"""
        issues = []
        score = 1.0
        
        # 检查内容长度
        if len(content) < self.min_content_length:
            issues.append(f"内容过短: {len(content)} < {self.min_content_length}")
            score -= 0.3
        elif len(content) > self.max_content_length:
            issues.append(f"内容过长: {len(content)} > {self.max_content_length}")
            score -= 0.2
        
        # 检查内容完整性
        if "error" in content.lower() and "failed" in content.lower():
            issues.append("内容包含错误信息")
            score -= 0.4
        
        # 检查是否包含有效信息
        if content.strip() in ["", "无", "N/A", "null", "undefined"]:
            issues.append("内容无有效信息")
            score -= 0.5
        
        # 检查格式合法性
        if context.get("expected_format") == "json":
            try:
                json.loads(content)
            except json.JSONDecodeError:
                issues.append("JSON格式不正确")
                score -= 0.3
        
        return {
            "quality_score": max(0.0, score),
            "issues": issues
        }
    
    def check_tool_result_quality(self, tool_name: str, result: Any, expected_type: str = None) -> Dict[str, Any]:
        """检查工具执行结果质量"""
        issues = []
        score = 1.0
        
        # 检查结果是否为空
        if result is None:
            issues.append("工具返回结果为空")
            score -= 0.5
        
        # 检查结果类型
        if expected_type and not isinstance(result, eval(expected_type)):
            issues.append(f"结果类型不匹配: 期望{expected_type}, 实际{type(result).__name__}")
            score -= 0.3
        
        # 特定工具的质量检查
        if tool_name.startswith("plot") or "visualization" in tool_name.lower():
            # 图像工具结果检查
            if isinstance(result, str) and not any(ext in result.lower() for ext in ['.png', '.jpg', '.svg']):
                issues.append("可视化工具未返回图像文件路径")
                score -= 0.4
        
        elif tool_name.startswith("calculate") or "analysis" in tool_name.lower():
            # 计算工具结果检查
            if isinstance(result, str) and "error" in result.lower():
                issues.append("计算工具返回错误信息")
                score -= 0.4
        
        return {
            "quality_score": max(0.0, score),
            "issues": issues
        }

class CriticNode:
    """Critic审查节点
    
    负责对智能体执行结果进行质量与安全审查，包括：
    1. 内容质量检查
    2. 安全策略验证
    3. 工具执行结果评估
    4. 决策下一步行动
    """
    
    def __init__(
        self,
        llm: BaseChatModel,
        config: Optional[Dict[str, Any]] = None,
        enable_llm_review: bool = True,
        enable_safety_check: bool = True,
        enable_quality_check: bool = True,
        enable_rag_review: bool = True,  # 新增RAG审查开关
        enable_capability_check: bool = True  # 新增能力检查开关
    ):
        """初始化Critic节点
        
        Args:
            llm: 语言模型，用于LLM审查
            config: 配置参数
            enable_llm_review: 是否启用LLM审查
            enable_safety_check: 是否启用安全检查
            enable_quality_check: 是否启用质量检查
            enable_rag_review: 是否启用RAG审查
            enable_capability_check: 是否启用系统能力检查
        """
        self.llm = llm
        self.config = config or {}
        self.enable_llm_review = enable_llm_review
        self.enable_safety_check = enable_safety_check
        self.enable_quality_check = enable_quality_check
        self.enable_rag_review = enable_rag_review
        self.enable_capability_check = enable_capability_check
        
        # 初始化检查器
        self.safety_policy = SafetyPolicy()
        self.quality_checker = QualityChecker()
        
        # 初始化增强RAG组件
        self.enhanced_memory_integration = None
        if self.enable_rag_review:
            try:
                from app.core.memory.enhanced_memory_integration import create_enhanced_memory_integration
                from app.core.config import ConfigManager
                
                logger.info("开始初始化增强RAG组件...")
                
                # 创建ConfigManager实例
                config_manager = ConfigManager()
                if self.config:
                    # 如果提供了config字典，使用它
                    config_manager.config = self.config
                    logger.debug("使用提供的配置初始化ConfigManager")
                else:
                    # 否则加载默认配置
                    try:
                        config_manager.load_config()
                        logger.debug("加载默认配置")
                    except Exception as config_e:
                        logger.warning(f"加载默认配置失败: {config_e}")
                        # 使用最简化配置
                        config_manager.config = {
                            'elasticsearch': {
                                'hosts': ['http://localhost:9200'],
                                'enable': False  # 禁用ES以避免连接错误
                            }
                        }
                
                # 尝试创建增强记忆集成
                self.enhanced_memory_integration = create_enhanced_memory_integration(config_manager)
                
                # 验证增强记忆集成是否可用
                if self.enhanced_memory_integration and hasattr(self.enhanced_memory_integration, 'enhance_state_with_agent_memories'):
                    logger.info("增强RAG组件初始化成功，功能验证通过")
                else:
                    logger.warning("增强RAG组件创建成功但功能验证失败")
                    self.enhanced_memory_integration = None
                    self.enable_rag_review = False
                    
            except ImportError as ie:
                logger.warning(f"增强RAG组件依赖缺失: {str(ie)}")
                self.enhanced_memory_integration = None
                self.enable_rag_review = False
            except Exception as e:
                logger.warning(f"增强RAG组件初始化失败: {str(e)}")
                self.enhanced_memory_integration = None
                self.enable_rag_review = False
                # 在debug模式下打印完整错误
                import traceback
                logger.debug(f"增强RAG初始化详细错误: {traceback.format_exc()}")
        
        # 初始化系统能力注册表
        if self.enable_capability_check:
            try:
                self.capability_registry = get_system_capability_registry()
                self.task_registry = task_registry
                logger.info("系统能力注册表初始化成功")
            except Exception as e:
                logger.warning(f"系统能力注册表初始化失败: {str(e)}")
                self.capability_registry = None
                self.task_registry = None
                self.enable_capability_check = False
        
        # 配置参数
        self.min_quality_score = self.config.get("min_quality_score", 0.6)
        self.auto_replan_threshold = self.config.get("auto_replan_threshold", 0.3)
        self.interrupt_threshold = self.config.get("interrupt_threshold", 0.8)
        
        logger.info(f"Critic节点已初始化: LLM审查={enable_llm_review}, 安全检查={enable_safety_check}, "
                   f"质量检查={enable_quality_check}, RAG审查={enable_rag_review}, 能力检查={enable_capability_check}")
    
    def review(self, state: IsotopeSystemState) -> CriticResult:
        """执行综合审查
        
        Args:
            state: 当前系统状态
            
        Returns:
            CriticResult: 审查结果
        """
        logger.info("开始Critic综合审查")
        
        try:
            # 获取最新的执行结果
            recent_results = self._extract_recent_results(state)
            
            # 执行各项检查
            safety_result = self._safety_review(recent_results) if self.enable_safety_check else {"passed": True, "issues": []}
            quality_result = self._quality_review(recent_results) if self.enable_quality_check else {"passed": True, "score": 1.0, "issues": []}
            llm_result = self._llm_review(state, recent_results) if self.enable_llm_review else {"passed": True, "score": 1.0, "issues": [], "reasoning": "LLM审查已禁用"}
            rag_result = self._rag_review(state, recent_results) if self.enable_rag_review else {"passed": True, "score": 1.0, "issues": [], "reasoning": "RAG审查已禁用"}
            capability_result = self._capability_review(recent_results) if self.enable_capability_check else {"passed": True, "issues": []}
            
            # 综合评估
            overall_result = self._synthesize_results(safety_result, quality_result, llm_result, rag_result, capability_result)
            
            logger.info(f"Critic审查完成: 通过={overall_result.passed}, 评分={overall_result.score:.2f}, 下一步={overall_result.next_action}")
            
            return overall_result
            
        except Exception as e:
            logger.error(f"Critic审查失败: {str(e)}")
            return CriticResult(
                passed=False,
                level=CriticLevel.ERROR,
                score=0.0,
                issues=[f"审查过程出错: {str(e)}"],
                recommendations=["请检查系统状态和配置"],
                next_action="interrupt",
                reasoning=f"审查过程发生异常: {str(e)}"
            )
    
    def _extract_recent_results(self, state: IsotopeSystemState) -> Dict[str, Any]:
        """提取最近的执行结果"""
        recent_results = {
            "messages": [],
            "tool_results": [],
            "actions": [],
            "current_task": None
        }
        
        # 提取最近的消息（最后5条）
        messages = state.get("messages", [])
        recent_results["messages"] = messages[-5:] if len(messages) > 5 else messages
        
        # 提取最近的工具执行结果（最后3条）
        tool_results = state.get("tool_results", [])
        recent_results["tool_results"] = tool_results[-3:] if len(tool_results) > 3 else tool_results
        
        # 提取最近的动作历史（最后5条）
        actions = state.get("action_history", [])
        recent_results["actions"] = actions[-5:] if len(actions) > 5 else actions
        
        # 当前任务
        recent_results["current_task"] = state.get("current_task")
        
        return recent_results
    
    def _safety_review(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """安全审查"""
        logger.debug("执行安全审查")
        
        all_issues = []
        
        # 检查工具执行安全性
        for tool_result in results.get("tool_results", []):
            tool_name = tool_result.get("tool_name", "")
            input_params = tool_result.get("input_params", {})
            
            safety_check = self.safety_policy.check_operation_safety(tool_name, input_params)
            if not safety_check["safe"]:
                all_issues.extend(safety_check["issues"])
        
        # 检查动作安全性
        for action in results.get("actions", []):
            action_type = action.get("action_type", "")
            params = action.get("params", {})
            
            safety_check = self.safety_policy.check_operation_safety(action_type, params)
            if not safety_check["safe"]:
                all_issues.extend(safety_check["issues"])
        
        return {
            "passed": len(all_issues) == 0,
            "issues": all_issues
        }
    
    def _quality_review(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """质量审查"""
        logger.debug("执行质量审查")
        
        all_issues = []
        quality_scores = []
        
        # 检查消息质量
        for message in results.get("messages", []):
            if hasattr(message, 'content') and message.content:
                quality_check = self.quality_checker.check_content_quality(
                    message.content, 
                    {"type": "message"}
                )
                quality_scores.append(quality_check["quality_score"])
                all_issues.extend(quality_check["issues"])
        
        # 检查工具结果质量
        for tool_result in results.get("tool_results", []):
            tool_name = tool_result.get("tool_name", "")
            output = tool_result.get("output", "")
            
            quality_check = self.quality_checker.check_tool_result_quality(tool_name, output)
            quality_scores.append(quality_check["quality_score"])
            all_issues.extend(quality_check["issues"])
        
        # 计算总体质量评分
        overall_score = sum(quality_scores) / len(quality_scores) if quality_scores else 0.5
        
        return {
            "passed": overall_score >= self.min_quality_score,
            "score": overall_score,
            "issues": all_issues
        }
    
    def _llm_review(self, state: IsotopeSystemState, results: Dict[str, Any]) -> Dict[str, Any]:
        """LLM审查"""
        logger.debug("执行LLM审查")
        
        try:
            # 构建审查提示
            review_prompt = self._build_review_prompt(state, results)
            
            # 调用LLM进行审查
            response = self.llm.invoke([SystemMessage(content=review_prompt)])
            
            # 解析LLM响应
            return self._parse_llm_response(response.content)
            
        except Exception as e:
            logger.warning(f"LLM审查失败: {str(e)}")
            return {
                "passed": True,  # 默认通过，避免阻塞
                "score": 0.7,
                "issues": [f"LLM审查异常: {str(e)}"],
                "reasoning": f"LLM审查过程出错: {str(e)}"
            }
    
    def _build_review_prompt(self, state: IsotopeSystemState, results: Dict[str, Any]) -> str:
        """构建LLM审查提示"""
        current_task = results.get("current_task")
        task_description = current_task.get("description", "未知任务") if current_task else "未知任务"
        
        # 提取关键信息
        recent_messages = results.get("messages", [])
        recent_tools = results.get("tool_results", [])
        
        message_summary = "\n".join([
            f"- {msg.type}: {msg.content[:100]}..." if hasattr(msg, 'content') and len(msg.content) > 100
            else f"- {msg.type}: {msg.content}" if hasattr(msg, 'content') else f"- {msg.type}: [无内容]"
            for msg in recent_messages[-3:]
        ])
        
        tool_summary = "\n".join([
            f"- {tool.get('tool_name', '未知工具')}: {str(tool.get('output', ''))[:100]}..."
            for tool in recent_tools[-3:]
        ])
        
        return f"""
请对以下智能体执行结果进行质量审查：

当前任务: {task_description}

最近消息:
{message_summary}

最近工具执行:
{tool_summary}

请从以下角度进行审查：
1. 结果的准确性和完整性
2. 是否回答了用户的问题
3. 是否存在明显错误或遗漏
4. 结果的可用性和实用性

请以JSON格式回复：
{{
    "passed": true/false,
    "score": 0.0-1.0的评分,
    "issues": ["发现的问题列表"],
    "reasoning": "详细的审查推理过程"
}}
"""
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """解析LLM审查响应"""
        try:
            # 提取JSON部分
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return {
                    "passed": result.get("passed", True),
                    "score": result.get("score", 0.7),
                    "issues": result.get("issues", []),
                    "reasoning": result.get("reasoning", "LLM审查完成")
                }
        except Exception as e:
            logger.warning(f"解析LLM响应失败: {str(e)}")
        
        # 回退解析
        passed = "passed" in response.lower() and "true" in response.lower()
        return {
            "passed": passed,
            "score": 0.7,
            "issues": [],
            "reasoning": f"LLM审查完成，回退解析结果: {'通过' if passed else '未通过'}"
        }
    
    def _rag_review(self, state: IsotopeSystemState, results: Dict[str, Any]) -> Dict[str, Any]:
        """基于增强RAG的历史经验审查"""
        logger.debug("执行增强RAG审查")
        
        # 双重检查增强RAG组件是否可用
        if not self.enhanced_memory_integration:
            logger.warning("增强RAG组件未初始化，无法执行RAG审查")
            return {
                "passed": True,
                "score": 0.7,
                "issues": ["增强RAG组件未初始化"],
                "reasoning": "无法执行RAG审查"
            }
        
        try:
            # 再次检查enhanced_memory_integration是否有效
            if not hasattr(self.enhanced_memory_integration, 'enhance_state_with_agent_memories'):
                logger.warning("enhanced_memory_integration对象缺少enhance_state_with_agent_memories方法")
                return {
                    "passed": True,
                    "score": 0.7,
                    "issues": ["增强RAG组件方法缺失"],
                    "reasoning": "增强RAG组件不完整"
                }
            
            # 提取关键信息进行相似性搜索
            current_task = results.get("current_task", {})
            task_description = current_task.get("description", "")
            
            # 获取最近的消息内容
            recent_messages = results.get("messages", [])
            message_content = " ".join([
                msg.content if hasattr(msg, 'content') else str(msg)
                for msg in recent_messages[-3:]
            ])
            
            # 组合查询内容
            query = f"{task_description} {message_content}".strip()
            if not query:
                logger.warning("无法提取有效的查询内容进行RAG审查")
                return {
                    "passed": True,
                    "score": 0.7,
                    "issues": ["查询内容为空"],
                    "reasoning": "无法构建有效查询"
                }
            
            # 使用增强记忆功能搜索相似的历史案例
            logger.debug(f"增强RAG查询: {query[:100]}...")
            agent_memory_context = self.enhanced_memory_integration.enhance_state_with_agent_memories(
                state=state,
                agent_role='critic',  # 作为Critic角色查询
                query=query
            )
            
            if not agent_memory_context:
                logger.warning("增强记忆返回了空上下文")
                return {
                    "passed": True,
                    "score": 0.7,
                    "issues": ["增强记忆上下文为空"],
                    "reasoning": "无法获取增强记忆上下文"
                }
            
            # 从episodic记忆中获取相似案例
            similar_cases = agent_memory_context.episodic_memories
            
            # 分析历史案例
            issues = []
            warnings = []
            score = 0.8  # 基础分数
            
            if similar_cases:
                # 统计历史案例的结果
                success_count = 0
                failure_patterns = []
                
                for case in similar_cases:
                    try:
                        # 安全地提取案例内容
                        case_content = None
                        if hasattr(case, 'content'):
                            case_content = case.content
                        elif hasattr(case, 'get'):
                            case_content = case.get("content", {})
                        elif isinstance(case, dict) and "content" in case:
                            case_content = case["content"]
                        
                        if case_content and isinstance(case_content, str):
                            # 简单的成功/失败模式匹配
                            if any(word in case_content.lower() for word in ["成功", "完成", "通过", "success"]):
                                success_count += 1
                            elif any(word in case_content.lower() for word in ["失败", "错误", "异常", "error", "fail"]):
                                # 尝试提取失败原因
                                failure_reason = "未知原因"
                                if ":" in case_content:
                                    parts = case_content.split(":")
                                    if len(parts) > 1:
                                        failure_reason = parts[1].strip()[:50]
                                failure_patterns.append(failure_reason)
                            else:
                                # 无明确成功/失败标识，默认为中性
                                success_count += 0.5
                    except Exception as e:
                        logger.warning(f"解析历史案例失败: {e}")
                        continue
                
                # 计算成功率
                if len(similar_cases) > 0:
                    success_rate = success_count / len(similar_cases)
                    score = max(0.5, success_rate)  # 确保分数不低于0.5
                else:
                    success_rate = 0.7
                    score = 0.7
                
                # 检查是否存在相似的失败模式
                if failure_patterns:
                    unique_failures = list(set(failure_patterns))
                    for failure in unique_failures[:3]:  # 只显示前3个失败原因
                        warnings.append(f"历史案例显示可能失败原因: {failure}")
                
                # 如果成功率低，生成警告
                if success_rate < 0.5:
                    issues.append(f"相似案例成功率较低: {success_rate:.1%}")
                
                reasoning = f"基于{len(similar_cases)}个历史案例分析，成功率为{success_rate:.1%}"
            else:
                # 没有找到相似案例
                reasoning = "未找到相似的历史案例，无法基于经验判断"
                score = 0.7  # 中性分数
            
            return {
                "passed": score >= 0.6,
                "score": score,
                "issues": issues,
                "warnings": warnings,
                "reasoning": reasoning
            }
            
        except Exception as e:
            logger.warning(f"RAG审查失败: {str(e)}")
            return {
                "passed": True,
                "score": 0.7,
                "issues": [f"RAG审查异常: {str(e)}"],
                "reasoning": f"RAG审查过程出错: {str(e)}"
            }
    
    def _capability_review(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """系统能力审查"""
        logger.debug("执行系统能力审查")
        
        if not self.capability_registry or not self.task_registry:
            return {
                "passed": True,
                "issues": ["系统能力注册表未初始化"]
            }
        
        try:
            issues = []
            
            # 检查工具调用的合法性
            for tool_result in results.get("tool_results", []):
                tool_name = tool_result.get("tool_name", "")
                
                # 检查工具是否在系统能力中注册
                capability = self.capability_registry.get_capability(tool_name)
                if not capability:
                    # 检查是否是task装饰的函数
                    if tool_name not in self.task_registry.registry:
                        issues.append(f"未注册的工具/任务: {tool_name}")
                    continue
                
                # 检查参数合法性
                input_params = tool_result.get("input_params", {})
                expected_params = capability.parameters
                
                # 检查必需参数
                for param_name, param_info in expected_params.items():
                    if param_info.get("required", False) and param_name not in input_params:
                        issues.append(f"工具 {tool_name} 缺少必需参数: {param_name}")
            
            # 检查动作的合法性
            for action in results.get("actions", []):
                action_type = action.get("action_type", "")
                
                # 验证动作是否在系统能力范围内
                if action_type and not any(
                    action_type in cap.name 
                    for cap in self.capability_registry.get_all_capabilities()
                ):
                    issues.append(f"未知的动作类型: {action_type}")
            
            return {
                "passed": len(issues) == 0,
                "issues": issues
            }
            
        except Exception as e:
            logger.warning(f"系统能力审查失败: {str(e)}")
            return {
                "passed": True,
                "issues": [f"能力审查异常: {str(e)}"]
            }
    
    def _synthesize_results(
        self, 
        safety_result: Dict[str, Any], 
        quality_result: Dict[str, Any], 
        llm_result: Dict[str, Any],
        rag_result: Dict[str, Any],
        capability_result: Dict[str, Any]
    ) -> CriticResult:
        """综合各项审查结果"""
        
        # 安全检查是硬性要求
        if not safety_result.get("passed", True):
            return CriticResult(
                passed=False,
                level=CriticLevel.CRITICAL,
                score=0.0,
                issues=safety_result.get("issues", []),
                recommendations=["立即停止执行", "检查安全策略配置"],
                next_action="abort",
                reasoning="安全检查未通过，存在风险操作"
            )
        
        # 能力检查也是硬性要求
        if not capability_result.get("passed", True):
            return CriticResult(
                passed=False,
                level=CriticLevel.ERROR,
                score=0.2,
                issues=capability_result.get("issues", []),
                recommendations=["使用系统注册的工具和能力", "检查工具参数完整性"],
                next_action="replan",
                reasoning="能力检查未通过，使用了未注册的工具或参数不正确"
            )
        
        # 综合质量评分（调整权重）
        quality_score = quality_result.get("score", 0.5)
        llm_score = llm_result.get("score", 0.7)
        rag_score = rag_result.get("score", 0.7)
        
        # 加权平均：质量30%，LLM 40%，RAG 30%
        overall_score = (quality_score * 0.3 + llm_score * 0.4 + rag_score * 0.3)
        
        # 收集所有问题和警告
        all_issues = []
        all_issues.extend(safety_result.get("issues", []))
        all_issues.extend(quality_result.get("issues", []))
        all_issues.extend(llm_result.get("issues", []))
        all_issues.extend(rag_result.get("issues", []))
        all_issues.extend(capability_result.get("issues", []))
        
        # 收集RAG警告
        rag_warnings = rag_result.get("warnings", [])
        
        # 决定下一步行动（考虑RAG历史经验）
        if overall_score < self.auto_replan_threshold:
            next_action = "replan"
            level = CriticLevel.ERROR
        elif overall_score < self.min_quality_score:
            # 如果RAG显示历史失败率高，倾向于中断而非重试
            if rag_score < 0.5 and len(rag_warnings) > 0:
                next_action = "interrupt"
                level = CriticLevel.WARNING
            elif overall_score < self.interrupt_threshold:
                next_action = "interrupt"
                level = CriticLevel.WARNING
            else:
                next_action = "replan"
                level = CriticLevel.WARNING
        else:
            next_action = "continue"
            level = CriticLevel.INFO
        
        # 生成改进建议（包含RAG洞察）
        recommendations = self._generate_recommendations(all_issues, overall_score, rag_warnings)
        
        # 构建综合推理说明
        reasoning_parts = [
            f"综合评分: {overall_score:.2f} (质量:{quality_score:.2f}, LLM:{llm_score:.2f}, RAG:{rag_score:.2f})"
        ]
        
        if llm_result.get("reasoning"):
            reasoning_parts.append(llm_result["reasoning"])
        
        if rag_result.get("reasoning"):
            reasoning_parts.append(f"RAG分析: {rag_result['reasoning']}")
        
        if rag_warnings:
            reasoning_parts.append(f"历史警告: {'; '.join(rag_warnings[:2])}")
        
        return CriticResult(
            passed=overall_score >= self.min_quality_score,
            level=level,
            score=overall_score,
            issues=all_issues,
            recommendations=recommendations,
            next_action=next_action,
            reasoning=". ".join(reasoning_parts)
        )
    
    def _generate_recommendations(self, issues: List[str], score: float, warnings: List[str]) -> List[str]:
        """生成改进建议"""
        recommendations = []
        
        if score < 0.3:
            recommendations.append("建议重新规划任务，当前执行质量过低")
        elif score < 0.6:
            recommendations.append("建议优化执行策略，提高结果质量")
        
        if any("错误" in issue for issue in issues):
            recommendations.append("检查错误处理机制")
        
        if any("内容" in issue for issue in issues):
            recommendations.append("改善内容生成质量")
        
        if any("工具" in issue for issue in issues):
            recommendations.append("优化工具选择和参数配置")
        
        if warnings:
            recommendations.append("考虑历史经验，避免重复错误")
        
        if not recommendations:
            recommendations.append("继续当前执行策略")
        
        return recommendations

# 节点函数，供图构建器使用
def create_critic_node(
    llm: BaseChatModel, 
    config: Optional[Dict[str, Any]] = None,
    enable_rag_review: bool = True,
    enable_capability_check: bool = True
) -> callable:
    """创建Critic审查节点
    
    Args:
        llm: 语言模型
        config: 配置参数
        enable_rag_review: 是否启用RAG审查
        enable_capability_check: 是否启用系统能力检查
        
    Returns:
        可调用的节点函数
    """
    critic = CriticNode(
        llm=llm, 
        config=config,
        enable_rag_review=enable_rag_review,
        enable_capability_check=enable_capability_check
    )
    
    def critic_node(state: IsotopeSystemState) -> Dict[str, Any]:
        """Critic节点函数"""
        try:
            # 执行审查
            result = critic.review(state)
            
            # 更新状态
            updated_state = state.copy()
            if "metadata" not in updated_state:
                updated_state["metadata"] = {}
            
            # 存储审查结果
            updated_state["metadata"]["critic_result"] = result.dict()
            
            # 添加审查结果消息
            if result.passed:
                msg_content = f"✅ 审查通过 (评分: {result.score:.2f})"
            else:
                msg_content = f"❌ 审查未通过 (评分: {result.score:.2f})\n问题: {', '.join(result.issues[:3])}"
            
            critic_msg = AIMessage(content=msg_content)
            updated_state = StateManager.update_messages(updated_state, critic_msg)
            
            # 记录审查动作
            action = {
                "action_id": f"critic_review_{int(time.time() * 1000)}",
                "action_type": "critic_review", 
                "timestamp": datetime.now().isoformat(),
                "result": result.dict(),
                "status": "success" if result.passed else "warning"
            }
            updated_state = StateManager.add_action_record(updated_state, action)
            
            return updated_state
            
        except Exception as e:
            logger.error(f"Critic节点执行失败: {str(e)}")
            # 返回带错误信息的状态
            error_msg = AIMessage(content=f"❌ Critic审查失败: {str(e)}")
            return StateManager.update_messages(state, error_msg)
    
    return critic_node 