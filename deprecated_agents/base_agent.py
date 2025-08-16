"""
基础智能体模块 - 为所有智能体提供共同的基础功能
"""
from typing import Dict, List, Any, Optional, Callable, Union, Type, Tuple
import logging
from abc import ABC, abstractmethod
from datetime import datetime

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import BaseTool
from langchain_core.messages import (
    BaseMessage, 
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage
)
from app.utils.qwen_chat import SFChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

from app.core.state import IsotopeSystemState, StateManager

# 配置日志
logger = logging.getLogger(__name__)

class BaseAgent(ABC):
    """基础智能体类，提供通用方法和接口
    
    该类是所有智能体的基类，提供了共同的功能，如：
    - LLM调用
    - 工具注册和使用
    - 状态管理
    - 输出格式化
    """
    
    def __init__(
        self,
        llm: Optional[BaseChatModel] = None,
        tools: Optional[List[BaseTool]] = None,
        system_prompt: Optional[str] = None,
        name: str = "base_agent",
        verbose: bool = False
    ):
        """初始化基础智能体
        
        Args:
            llm: 语言模型，如果为None，将使用默认配置创建
            tools: 可用工具列表
            system_prompt: 系统提示词
            name: 智能体名称
            verbose: 是否输出详细日志
        """
        self.name = name
        self.verbose = verbose
        
        # 设置语言模型
        self.llm = llm if llm is not None else self._create_default_llm()
        
        # 设置工具列表
        self.tools = tools if tools is not None else []
        
        # 设置系统提示词
        self.system_prompt = system_prompt
        
        # 设置消息历史记录
        self.memory = []
        
        # 初始化检查点保存器
        self.checkpointer = MemorySaver()
        
        if self.verbose:
            logger.info(f"初始化智能体: {self.name}")
    
    def _create_default_llm(self) -> BaseChatModel:
        """创建默认的语言模型
        
        Returns:
            默认配置的语言模型
        """
        try:
            # 从配置中获取LLM配置
            from app.core.config import ConfigManager
            config = ConfigManager()
            model_config = config.get_model_config()
            return SFChatOpenAI(model=model_config["model"], temperature=model_config["temperature"])
        except Exception as e:
            logger.error(f"创建默认LLM失败: {e}")
            raise
    
    def add_tool(self, tool: BaseTool) -> None:
        """添加工具到智能体
        
        Args:
            tool: 要添加的工具
        """
        self.tools.append(tool)
        if self.verbose:
            logger.info(f"添加工具: {tool.name} 到智能体 {self.name}")
    
    def add_tools(self, tools: List[BaseTool]) -> None:
        """批量添加工具到智能体
        
        Args:
            tools: 要添加的工具列表
        """
        self.tools.extend(tools)
        if self.verbose:
            logger.info(f"添加 {len(tools)} 个工具到智能体 {self.name}")
    
    def get_available_tools(self) -> List[BaseTool]:
        """获取智能体可用的工具列表
        
        Returns:
            可用工具列表
        """
        return self.tools
    
    def get_tool_descriptions(self) -> List[Dict[str, str]]:
        """获取工具描述列表
        
        Returns:
            工具描述字典列表，包含name和description字段
        """
        return [{"name": tool.name, "description": tool.description} for tool in self.tools]
    
    def create_system_message(self, custom_content: Optional[str] = None) -> SystemMessage:
        """创建系统消息
        
        Args:
            custom_content: 自定义内容，如果提供则使用此内容
            
        Returns:
            系统消息对象
        """
        content = custom_content if custom_content is not None else self.system_prompt
        if not content:
            content = "你是一个帮助用户分析天然气碳同位素数据的智能助手。"
        
        return SystemMessage(content=content)
    
    def format_tool_for_prompt(self) -> str:
        """格式化工具信息用于提示词
        
        Returns:
            工具信息的格式化字符串
        """
        if not self.tools:
            return "你没有可用的工具。"
        
        tool_strings = []
        for tool in self.tools:
            tool_strings.append(f"{tool.name}: {tool.description}")
        
        return "\n".join(tool_strings)
    
    @abstractmethod
    def run(self, state: IsotopeSystemState) -> Dict[str, Any]:
        """运行智能体，处理当前状态
        
        该方法需要由子类实现，处理用户输入并生成响应
        
        Args:
            state: 当前系统状态
            
        Returns:
            更新后的状态
        """
        pass
    
    def _prepare_messages_for_llm(self, state: IsotopeSystemState) -> List[BaseMessage]:
        """准备发送给LLM的消息
        
        Args:
            state: 系统状态
            
        Returns:
            准备好的消息列表
        """
        import logging
        logger = logging.getLogger(__name__)
        
        messages = []
        
        # 添加系统提示词
        if self.system_prompt:
            messages.append(SystemMessage(content=self.system_prompt))
        
        # 添加任务说明
        task = state.get("current_task", {})
        if task:
            task_description = task.get("description", "")
            task_type = task.get("type", "general")
            if task_description:
                task_message = f"当前任务: {task_description}\n任务类型: {task_type}"
                messages.append(SystemMessage(content=task_message))
        
        # 状态信息添加
        status_info = []
        
        # 添加文件信息
        files = state.get("files", {})
        if files:
            status_info.append(f"已上传的文件 ({len(files)} 个):")
            for file_id, file_info in files.items():
                file_name = file_info.get("file_name", "未知文件名")
                file_type = file_info.get("file_type", "未知类型")
                status_info.append(f"- ID: {file_id}, 名称: {file_name}, 类型: {file_type}")
        
        # 如果有状态信息，添加为系统消息
        if status_info:
            status_message = "\n".join(status_info)
            messages.append(SystemMessage(content=f"当前状态信息:\n{status_message}"))
            
        # 检查是否有工具执行结果
        current_task = state.get("current_task")
        if current_task is not None and isinstance(current_task, dict):
            tool_executions = current_task.get("tool_executions", [])
            if tool_executions:
                # 添加工具执行历史摘要
                tool_summary = [f"以下是之前的工具执行历史 (共{len(tool_executions)}个):"]
                for idx, tool_exec in enumerate(tool_executions):
                    tool_name = tool_exec.get("tool_name", "未知工具")
                    input = tool_exec.get("input", "未知输入")
                    status = tool_exec.get("status", "未知状态")
                    tool_summary.append(f"- [{idx+1}] 工具: {tool_name}, 输入: {input}, 状态: {status}")
                
                tool_history_msg = SystemMessage(content="\n".join(tool_summary))
                messages.append(tool_history_msg)
        else:
            # 当current_task为None时，记录日志
            logger.warning(f"状态中current_task为None或不是字典类型: {type(current_task)}")
        
        # 使用StateManager的方法处理对话历史，确保工具消息得到保留
        agent_type = self.name
        processed_history = StateManager.prepare_messages_for_agent(state, agent_type)
        
        # 添加处理后的历史消息
        messages.extend(processed_history)
        
        return messages
    
    def log_messages(self, messages: List[BaseMessage]) -> None:
        """记录消息日志
        
        Args:
            messages: 要记录的消息列表
        """
        if not self.verbose:
            return
        
        for msg in messages:
            sender = msg.__class__.__name__.replace("Message", "")
            content = msg.content
            
            # 为工具消息添加工具名称
            if sender == "Tool" and hasattr(msg, "name"):
                tool_name = getattr(msg, "name", "未知工具")
                sender = f"Tool({tool_name})"
                
            if len(content) > 100:
                content = content[:97] + "..."
            logger.info(f"{sender}: {content}")
    
    def handle_error(self, error: Exception, state: IsotopeSystemState) -> Dict[str, Any]:
        """处理智能体执行过程中的错误
        
        Args:
            error: 异常对象
            state: 当前系统状态
            
        Returns:
            更新后的状态
        """
        error_msg = f"智能体 {self.name} 执行出错: {str(error)}"
        logger.error(error_msg)
        
        # 向状态添加错误消息
        error_ai_msg = AIMessage(content=f"很抱歉，我遇到了一个问题: {error_msg}")
        return StateManager.update_messages(state, error_ai_msg) 