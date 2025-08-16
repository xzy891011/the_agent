"""
助手智能体 - 处理咨询类问题的系统代表
"""

import logging
import time
from typing import Dict, List, Any, Optional
from datetime import datetime

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from app.core.state import IsotopeSystemState, StateManager
from app.agents.registry import AgentProtocol, agent_registry
from app.agents.langgraph_agent import LangGraphAgent

logger = logging.getLogger(__name__)

class AssistantAgent(LangGraphAgent):
    """助手智能体 - 系统咨询与知识检索专家
    
    职责：
    1. 处理用户的通用咨询问题
    2. 调用知识检索类工具
    3. 代表整个多智能体系统与用户交互
    4. 提供系统功能介绍和使用指导
    """
    
    def __init__(
        self,
        llm: BaseChatModel,
        config: Optional[Dict[str, Any]] = None,
        memory_integration: Optional[Any] = None,
        info_hub: Optional[Any] = None,
        interrupt_manager: Optional[Any] = None,
        message_router: Optional[Any] = None
    ):
        # 获取知识检索相关的工具能力
        knowledge_capabilities = self._get_knowledge_capabilities()
        
        super().__init__(
            name="assistant",
            role="系统助手与咨询专家",
            llm=llm,
            capabilities=knowledge_capabilities,
            config=config,
            memory_integration=memory_integration,
            info_hub=info_hub,
            interrupt_manager=interrupt_manager,
            message_router=message_router
        )
        
        self.description = "油气勘探多智能体系统的助手，负责咨询问答、知识检索和系统功能介绍"
        
        # 系统知识库
        self.system_knowledge = {
            "system_capabilities": [
                "录井资料处理与解释",
                "地震数据处理与解释", 
                "构造识别与分析",
                "井震联合解释",
                "储层建模",
                "油藏模拟",
                "经济评价分析"
            ],
            "available_agents": {
                "logging": "录井资料处理专家 - 专门处理测井数据重构补全与解释",
                "seismic": "地震数据处理专家 - 专门处理地震数据处理与解释",
                "assistant": "系统助手 - 提供咨询服务和知识检索"
            },
            "workflow_guidance": [
                "上传相关数据文件",
                "描述您的分析需求",
                "系统自动选择合适的专业智能体",
                "智能体执行分析并生成结果",
                "质量审查确保结果可靠性"
            ]
        }
    
    def get_description(self) -> str:
        return self.description
    
    def _get_knowledge_capabilities(self) -> List[str]:
        """获取知识检索相关的工具能力"""
        knowledge_tools = [
            # 文档检索类
            "search_documents_rag",
            "ragflow_query", 
            "preview_file_content",
            
            # 系统功能类
            "get_system_status",
            "list_available_tools",
            "explain_workflow",
            
            # 数据查询类
            "query_database",
            "search_knowledge_base",
            "get_historical_results",
            
            # 通用分析类
            "generate_report",
            "analyze_data_structure",
            "provide_recommendations"
        ]
        
        # 过滤出实际存在的工具
        try:
            from app.tools.registry import get_all_tools
            available_tools = {tool.name for tool in get_all_tools()}
            filtered_tools = [tool for tool in knowledge_tools if tool in available_tools]
            
            if not filtered_tools:
                # 如果没有找到专门的知识工具，使用一些通用工具
                filtered_tools = [
                    "file_processor",
                    "data_analyzer",
                    "report_generator",
                    "search_documents_rag",
                    "ragflow_query"
                ]
            
            logger.info(f"助手智能体获得{len(filtered_tools)}种知识检索能力: {filtered_tools}")
            return filtered_tools
            
        except Exception as e:
            logger.warning(f"获取知识工具能力失败: {str(e)}，使用默认能力")
            return [
                "search_documents_rag",
                "ragflow_query", 
                "file_processor",
                "data_analyzer",
                "report_generator"
            ]
    
    def _create_system_prompt(self) -> str:
        """创建系统提示词"""
        return f"""你是油气勘探多智能体系统的助手，代表整个系统与用户交互。

## 你的身份和职责
- 系统助手与咨询专家
- 负责处理用户的咨询类问题
- 提供系统功能介绍和使用指导
- 调用知识检索工具获取相关信息
- 代表整个多智能体系统的专业形象

## 系统能力概览
{chr(10).join([f'- {cap}' for cap in self.system_knowledge['system_capabilities']])}

## 可用专业智能体
{chr(10).join([f'- {name}: {desc}' for name, desc in self.system_knowledge['available_agents'].items()])}

## 标准工作流程
{chr(10).join([f'{i+1}. {step}' for i, step in enumerate(self.system_knowledge['workflow_guidance'])])}

## 交互原则
- 始终保持专业和友好的态度
- 主动了解用户的具体需求
- 提供清晰的指导和建议
- 在必要时推荐合适的专业智能体
- 使用知识检索工具获取准确信息

## 可用工具
你可以调用以下类型的工具：
- 文档检索和知识搜索工具
- 文件内容预览工具
- 数据分析和报告生成工具
- 系统状态查询工具

请根据用户问题，智能地选择和使用合适的工具来提供最佳的帮助。
"""
    
    def _analyze_consultation_type(self, user_input: str) -> Dict[str, Any]:
        """分析咨询类型"""
        user_lower = user_input.lower()
        
        # 咨询类型映射
        consultation_types = {
            "system_intro": ["介绍", "功能", "能做什么", "系统", "概述"],
            "workflow_guidance": ["怎么用", "流程", "步骤", "如何", "使用方法"],
            "technical_consultation": ["技术", "原理", "算法", "方法", "理论"],
            "tool_inquiry": ["工具", "软件", "模块", "插件"],
            "data_question": ["数据", "格式", "文件", "上传"],
            "result_interpretation": ["结果", "解释", "分析", "图表", "报告"],
            "general_question": ["问题", "疑问", "咨询", "帮助"]
        }
        
        detected_types = []
        for consultation_type, keywords in consultation_types.items():
            if any(keyword in user_lower for keyword in keywords):
                detected_types.append(consultation_type)
        
        # 如果没有匹配到特定类型，归类为通用咨询
        if not detected_types:
            detected_types = ["general_question"]
        
        return {
            "consultation_types": detected_types,
            "primary_type": detected_types[0],
            "requires_knowledge_search": any(t in ["technical_consultation", "result_interpretation"] for t in detected_types),
            "requires_system_info": any(t in ["system_intro", "workflow_guidance", "tool_inquiry"] for t in detected_types)
        }
    
    def _handle_system_introduction(self, state: IsotopeSystemState) -> str:
        """处理系统介绍类咨询"""
        intro_text = f"""
## 欢迎使用油气勘探多智能体系统！

### 🎯 系统概述
这是一个专业的油气勘探地质建模智能化系统，集成了多个专业领域的智能体，可以协助您完成各种油气勘探开发任务。

### 🔧 核心能力
{chr(10).join([f'• {cap}' for cap in self.system_knowledge['system_capabilities']])}

### 🤖 专业智能体团队
{chr(10).join([f'• **{name}**: {desc}' for name, desc in self.system_knowledge['available_agents'].items()])}

### 🚀 使用优势
- **专业化**: 每个智能体都是特定领域的专家
- **智能化**: 自动选择最适合的智能体处理您的需求
- **模块化**: 可以单独或组合使用不同的分析工具
- **质量保证**: 内置质量审查机制确保结果可靠性

### 💡 开始使用
只需要描述您的需求，系统会自动为您匹配合适的专业智能体和工具。如有任何疑问，随时可以咨询我！
"""
        return intro_text
    
    def _handle_workflow_guidance(self, state: IsotopeSystemState) -> str:
        """处理工作流程指导"""
        guidance_text = f"""
## 📋 系统使用指南

### 🔄 标准工作流程
{chr(10).join([f'{i+1}. **{step}**' for i, step in enumerate(self.system_knowledge['workflow_guidance'])])}

### 📁 支持的数据格式
- **录井数据**: LAS、CSV、Excel格式的测井曲线数据
- **地震数据**: SEG-Y、SEGY格式的地震数据
- **文档资料**: PDF、Word、文本格式的地质报告

### 🎯 任务示例

**录井分析任务**:
- "请分析这个井的录井数据，识别储层段"
- "对比多口井的测井曲线，分析储层连续性"

**地震解释任务**:
- "处理这个地震数据，识别断层结构"
- "进行地震属性分析，圈定有利区域"

**综合咨询**:
- "这个区块的勘探前景如何？"
- "推荐合适的开发方案"

### ⚡ 快速开始
1. 上传您的数据文件
2. 简单描述您想要进行的分析
3. 系统会自动开始处理并返回结果

有任何问题随时问我！
"""
        return guidance_text
    
    def run(self, state: IsotopeSystemState) -> IsotopeSystemState:
        """执行助手智能体逻辑"""
        logger.info("助手智能体开始处理咨询问题")
        
        try:
            # 获取用户消息
            last_human_msg = StateManager.get_last_human_message(state)
            user_input = last_human_msg.content if last_human_msg else ""
            
            if not user_input.strip():
                response = "您好！我是油气勘探系统的助手。请告诉我您需要什么帮助？"
                state = StateManager.update_messages(state, AIMessage(content=response))
                return state
            
            # 分析咨询类型
            consultation_analysis = self._analyze_consultation_type(user_input)
            primary_type = consultation_analysis["primary_type"]
            
            # 根据咨询类型提供回应
            if primary_type == "system_intro":
                response = self._handle_system_introduction(state)
            elif primary_type == "workflow_guidance":
                response = self._handle_workflow_guidance(state)
            else:
                # 使用ReAct模式处理其他类型的咨询
                response = self._handle_general_consultation(state, user_input, consultation_analysis)
            
            # 更新状态
            state = StateManager.update_messages(state, AIMessage(content=response))
            
            # 记录咨询处理信息
            state["metadata"]["assistant_analysis"] = consultation_analysis
            state["metadata"]["consultation_handled"] = True
            state["metadata"]["assistant_response_time"] = time.time()
            
            logger.info(f"助手智能体完成咨询处理: {primary_type}")
            return state
            
        except Exception as e:
            logger.error(f"助手智能体处理失败: {str(e)}")
            error_response = f"很抱歉，处理您的咨询时遇到了问题。请重新描述您的需求，或者联系技术支持。\n\n错误信息: {str(e)}"
            state = StateManager.update_messages(state, AIMessage(content=error_response))
            return state
    
    def _handle_general_consultation(self, state: IsotopeSystemState, user_input: str, analysis: Dict[str, Any]) -> str:
        """处理通用咨询（使用ReAct模式）"""
        try:
            # 构建咨询处理的prompt
            consultation_prompt = f"""
作为油气勘探系统的助手，请回答用户的咨询问题。

用户问题: {user_input}

咨询分析:
- 主要类型: {analysis['primary_type']}
- 需要知识搜索: {analysis['requires_knowledge_search']}
- 需要系统信息: {analysis['requires_system_info']}

请提供专业、准确、有帮助的回答。如果需要，可以：
1. 推荐用户使用特定的专业智能体
2. 提供操作指导
3. 解释相关的技术概念
4. 给出下一步建议

回答要求：
- 保持专业友好的语调
- 提供具体可行的建议
- 如果涉及专业分析，明确说明需要哪个专业智能体
- 回答要简洁明了，易于理解
"""
            
            # 使用LLM生成回答
            llm_response = self.llm.invoke(consultation_prompt)
            response_content = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
            
            # 增强回答内容
            enhanced_response = self._enhance_consultation_response(response_content, analysis)
            
            return enhanced_response
            
        except Exception as e:
            logger.error(f"通用咨询处理失败: {str(e)}")
            return f"我理解了您的问题，但目前无法提供详细回答。建议您：\n\n1. 重新详细描述您的需求\n2. 或者直接使用相关的专业智能体\n3. 如需技术支持，请联系系统管理员"
    
    def _enhance_consultation_response(self, base_response: str, analysis: Dict[str, Any]) -> str:
        """增强咨询回答"""
        enhanced = base_response
        
        # 添加相关智能体推荐
        if "录井" in base_response.lower() or "测井" in base_response.lower():
            enhanced += "\n\n💡 **推荐**: 如需进行录井数据分析，可以直接说 '请分析录井数据' 来使用录井专家智能体。"
        
        if "地震" in base_response.lower():
            enhanced += "\n\n💡 **推荐**: 如需进行地震数据处理，可以直接说 '请处理地震数据' 来使用地震专家智能体。"
        
        # 添加后续指导
        if analysis["requires_system_info"]:
            enhanced += "\n\n📚 **更多帮助**: 如需了解更多系统功能，请说 '介绍系统功能' 或 '使用指南'。"
        
        return enhanced

def create_assistant_agent(
    llm: BaseChatModel,
    config: Optional[Dict[str, Any]] = None,
    memory_integration: Optional[Any] = None,
    info_hub: Optional[Any] = None,
    interrupt_manager: Optional[Any] = None,
    message_router: Optional[Any] = None
) -> AssistantAgent:
    """创建助手智能体实例"""
    return AssistantAgent(
        llm=llm,
        config=config,
        memory_integration=memory_integration,
        info_hub=info_hub,
        interrupt_manager=interrupt_manager,
        message_router=message_router
    )
