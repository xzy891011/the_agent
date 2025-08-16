from typing import Annotated, Dict, List, Any, Optional, Union, TypeVar, Generic
from typing_extensions import TypedDict
from datetime import datetime
from enum import Enum
import time
import uuid

from langchain_core.messages import (
    AIMessage, 
    HumanMessage, 
    SystemMessage, 
    ToolMessage, 
    BaseMessage,
    FunctionMessage
)
from langgraph.graph.message import add_messages

# 任务状态枚举
class TaskStatus(str, Enum):
    """任务状态枚举类型"""
    NOT_STARTED = "not_started"  # 未开始
    IN_PROGRESS = "in_progress"  # 进行中
    WAITING_USER = "waiting_user"  # 等待用户输入
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败

# 工具执行记录
class ToolExecution(TypedDict):
    """工具执行记录"""
    tool_name: str  # 工具名称
    input_params: Dict[str, Any]  # 输入参数
    output: Any  # 输出结果
    status: str  # 执行状态
    error: Optional[str]  # 错误信息
    timestamp: str  # 执行时间戳

# 文件信息
class FileInfo(TypedDict):
    """文件信息结构"""
    file_id: str  # 文件ID
    file_name: str  # 文件名
    file_path: str  # 文件路径
    file_type: str  # 文件类型
    content_type: str  # 内容类型
    size: int  # 文件大小
    upload_time: str  # 上传时间
    metadata: Dict[str, Any]  # 元数据

# 主要任务信息
class TaskInfo(TypedDict):
    """任务信息结构"""
    task_id: str  # 任务ID
    task_type: str  # 任务类型
    description: str  # 任务描述
    status: TaskStatus  # 任务状态
    created_at: str  # 创建时间
    updated_at: str  # 更新时间
    steps: List[Dict[str, Any]]  # 任务步骤
    current_step: int  # 当前步骤索引

# 智能体系统状态
class IsotopeSystemState(TypedDict):
    """天然气碳同位素数据解释智能体系统的状态定义"""
    messages: Annotated[List[BaseMessage], add_messages]  # 对话消息历史
    action_history: List[Dict[str, Any]]  # 执行动作历史
    files: Dict[str, FileInfo]  # 文件信息
    current_task: Optional[TaskInfo]  # 当前任务状态
    tool_results: List[ToolExecution]  # 工具执行结果历史
    metadata: Dict[str, Any]  # 元数据，包括会话信息等
    # *** 新增：智能体分析结果字段，支持LangGraphAgent状态传递 ***
    agent_analysis: Optional[Dict[str, Any]]  # 智能体任务分析结果
    task_results: Optional[List[Dict[str, Any]]]  # 任务执行结果

class StateManager:
    """状态管理器类，提供状态创建和更新的方法"""
    
    @staticmethod
    def create_initial_state() -> IsotopeSystemState:
        """创建初始状态"""
        return {
            "messages": [],
            "action_history": [],
            "files": {},
            "current_task": None,
            "tool_results": [],
            "metadata": {
                "session_id": "",
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat()
            },
            # *** 新增字段初始化 ***
            "agent_analysis": None,
            "task_results": None
        }
    
    @staticmethod
    def update_messages(state: IsotopeSystemState, message: Union[BaseMessage, List[BaseMessage]]) -> IsotopeSystemState:
        """更新消息历史
        
        Args:
            state: 当前状态
            message: 新消息或消息列表
        
        Returns:
            更新后的状态
        """
        if isinstance(message, list):
            return {**state, "messages": state["messages"] + message}
        else:
            return {**state, "messages": state["messages"] + [message]}
    
    @staticmethod
    def add_action_record(state: IsotopeSystemState, action: Dict[str, Any]) -> IsotopeSystemState:
        """添加执行动作记录
        
        Args:
            state: 当前状态
            action: 动作记录
        
        Returns:
            更新后的状态
        """
        # 确保动作记录包含时间戳
        if "timestamp" not in action:
            action["timestamp"] = datetime.now().isoformat()
            
        updated_history = state["action_history"] + [action]
        
        # 信息中枢钩子：记录动作日志
        try:
            from app.core.info_hub import get_info_hub
            info_hub = get_info_hub()
            session_id = state.get("metadata", {}).get("session_id", "unknown")
            info_hub.log_event(session_id, action)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"记录动作到信息中枢失败: {str(e)}")
        
        return {**state, "action_history": updated_history}
    
    @staticmethod
    def add_file(state: IsotopeSystemState, file_info: FileInfo) -> IsotopeSystemState:
        """添加文件信息到状态
        
        Args:
            state: 当前状态
            file_info: 文件信息
        
        Returns:
            更新后的状态
        """
        updated_files = {**state["files"], file_info["file_id"]: file_info}
        
        # 信息中枢钩子：保存文件元数据
        try:
            StateManager.index_file_to_infohub(file_info)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"保存文件元数据到信息中枢失败: {str(e)}")
        
        return {**state, "files": updated_files}
    
    @staticmethod
    def index_file_to_infohub(file_info: Dict[str, Any], session_id: Optional[str] = None) -> None:
        """将文件索引到InfoHub
        
        Args:
            file_info: 文件信息
            session_id: 会话ID (可选)
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            from app.core.info_hub import get_info_hub
            info_hub = get_info_hub()
            
            # 保存文件元数据
            info_hub.save_file_meta(file_info)
            
            # 如果有内容，索引到Elasticsearch
            content = file_info.get('content')
            file_id = file_info.get('file_id')
            
            if content and file_id:
                info_hub.index_file_to_elasticsearch(file_id, file_info, content)
                
            logger.info(f"文件记录已添加到InfoHub: {file_id}")
            
        except Exception as e:
            logger.warning(f"向InfoHub保存文件索引失败: {str(e)}")
            logger.debug("", exc_info=True)
    
    @staticmethod
    def remove_file(state: IsotopeSystemState, file_id: str) -> IsotopeSystemState:
        """删除文件信息
        
        Args:
            state: 当前状态
            file_id: 文件ID
        
        Returns:
            更新后的状态
        """
        updated_files = state["files"].copy()
        if file_id in updated_files:
            del updated_files[file_id]
        return {**state, "files": updated_files}
    
    @staticmethod
    def update_current_task(state: IsotopeSystemState, task_info: Optional[TaskInfo]) -> IsotopeSystemState:
        """更新当前任务状态
        
        Args:
            state: 当前状态
            task_info: 任务信息，None表示清除当前任务
        
        Returns:
            更新后的状态
        """
        # 如果有现有任务，更新时间戳
        if task_info is not None:
            task_info = {**task_info, "updated_at": datetime.now().isoformat()}
        
        return {**state, "current_task": task_info}
    
    @staticmethod
    def add_tool_result(state: IsotopeSystemState, tool_execution: ToolExecution) -> IsotopeSystemState:
        """添加工具执行结果
        
        Args:
            state: 当前状态
            tool_execution: 工具执行记录
        
        Returns:
            更新后的状态
        """
        updated_results = state["tool_results"] + [tool_execution]
        
        # 信息中枢钩子：记录工具执行结果
        try:
            from app.core.info_hub import get_info_hub
            info_hub = get_info_hub()
            session_id = state.get("metadata", {}).get("session_id", "unknown")
            info_hub.log_tool_result(session_id, tool_execution)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"记录工具结果到信息中枢失败: {str(e)}")
        
        return {**state, "tool_results": updated_results}
    
    @staticmethod
    def update_metadata(state: IsotopeSystemState, metadata_updates: Dict[str, Any]) -> IsotopeSystemState:
        """更新元数据
        
        Args:
            state: 当前状态
            metadata_updates: 元数据更新
        
        Returns:
            更新后的状态
        """
        updated_metadata = {**state["metadata"], **metadata_updates, "last_updated": datetime.now().isoformat()}
        return {**state, "metadata": updated_metadata}
    
    @staticmethod
    def get_last_message(state: IsotopeSystemState) -> Optional[BaseMessage]:
        """获取最后一条消息
        
        Args:
            state: 当前状态
        
        Returns:
            最后一条消息，如果没有消息则返回None
        """
        messages = state.get("messages", [])
        if not messages:
            return None
        return messages[-1]
    
    @staticmethod
    def get_last_human_message(state: IsotopeSystemState) -> Optional[HumanMessage]:
        """获取最后一条人类消息
        
        Args:
            state: 当前状态
        
        Returns:
            最后一条人类消息，如果没有人类消息则返回None
        """
        messages = state.get("messages", [])
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                return message
        return None
    
    @staticmethod
    def get_last_ai_message(state: IsotopeSystemState) -> Optional[AIMessage]:
        """获取最后一条AI消息
        
        Args:
            state: 当前状态
        
        Returns:
            最后一条AI消息，如果没有AI消息则返回None
        """
        messages = state.get("messages", [])
        for message in reversed(messages):
            if isinstance(message, AIMessage):
                return message
        return None
    
    @staticmethod
    def get_conversation_history(state: IsotopeSystemState, max_messages: Optional[int] = None) -> List[BaseMessage]:
        """获取对话历史
        
        Args:
            state: 当前状态
            max_messages: 最大消息数量，None表示获取所有消息
        
        Returns:
            对话历史消息列表
        """
        messages = state.get("messages", [])
        if max_messages is not None and max_messages > 0:
            return messages[-max_messages:]
        return messages
    
    @staticmethod
    def get_formatted_state_for_llm(state: IsotopeSystemState) -> Dict[str, Any]:
        """获取格式化的状态信息，用于发送给LLM
        
        Args:
            state: 当前状态
        
        Returns:
            格式化的状态信息
        """
        # 格式化消息历史，转换成适合LLM的格式
        formatted_messages = []
        for msg in state.get("messages", []):
            if isinstance(msg, dict):
                formatted_messages.append(msg)
            else:
                # 转换BaseMessage对象为字典
                formatted_msg = {
                    "role": msg.type,
                    "content": msg.content
                }
                if hasattr(msg, "name") and msg.name:
                    formatted_msg["name"] = msg.name
                if hasattr(msg, "tool_call_id") and msg.tool_call_id:
                    formatted_msg["tool_call_id"] = msg.tool_call_id
                formatted_messages.append(formatted_msg)
        
        # 格式化工具执行结果
        formatted_tool_results = []
        for result in state.get("tool_results", []):
            formatted_tool_results.append({
                "tool": result["tool_name"],
                "input": result["input_params"],
                "output": result["output"],
                "status": result["status"],
                "timestamp": result["timestamp"]
            })
        
        # 格式化当前任务信息
        current_task = state.get("current_task")
        formatted_task = None
        if current_task:
            formatted_task = {
                "type": current_task["task_type"],
                "description": current_task["description"],
                "status": current_task["status"],
                "current_step": current_task["current_step"],
                "total_steps": len(current_task["steps"])
            }
        
        return {
            "messages": formatted_messages,
            "tool_executions": formatted_tool_results,
            "current_task": formatted_task,
            "files": list(state.get("files", {}).keys())
        }

    @staticmethod
    def prepare_messages_for_agent(state: IsotopeSystemState, agent_type: str) -> List[BaseMessage]:
        """准备传递给特定智能体的消息，标记消息来源
        
        Args:
            state: 系统状态
            agent_type: 目标智能体类型 (data_agent, expert_agent)
            
        Returns:
            带有标记的消息列表
        """
        messages = state.get("messages", [])
        processed_messages = []
        
        # 添加一条系统消息，说明消息历史上下文
        context_explanation = SystemMessage(content=f"""
下面是整个系统的对话历史和执行历史。这些历史仅供参考，帮助你了解当前任务的上下文。
你是{agent_type}，仅需关注与你相关的任务和信息，不要被其他智能体的对话影响你的决策逻辑。
专注于当前分配给你的具体任务，完成后不要反复重复调用工具。
所有工具执行结果显示在下方，可能包括其他智能体调用的工具结果，请充分利用这些信息。
""")
        processed_messages.append(context_explanation)
        
        # 处理每条消息，添加来源标记
        for message in messages:
            if isinstance(message, HumanMessage):
                # 用户消息保持不变
                processed_messages.append(message)
            elif isinstance(message, AIMessage):
                # 检查消息是否有元数据指示来源
                metadata = getattr(message, "additional_kwargs", {})
                source = metadata.get("source", "supervisor")  # 默认为supervisor
                
                # 在内容前添加标记
                marked_content = f"{source}: {message.content}"
                
                # 创建新消息
                new_message = AIMessage(content=marked_content, additional_kwargs=metadata)
                processed_messages.append(new_message)
            elif isinstance(message, ToolMessage):
                # 工具消息添加标记，确保工具名称被显示
                tool_name = getattr(message, "name", "未知工具")
                tool_call_id = getattr(message, "tool_call_id", f"tool_call_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}")
                
                # 检查工具消息内容是否已包含工具名称
                content = message.content
                if not content.startswith("【") and "工具执行结果】" not in content:
                    marked_content = f"【{tool_name}工具执行结果】: {content}"
                else:
                    marked_content = content  # 内容已经包含工具名称
                
                # 创建新的工具消息
                new_message = ToolMessage(
                    content=marked_content, 
                    tool_call_id=tool_call_id,
                    name=tool_name  # 确保name字段被正确设置
                )
                processed_messages.append(new_message)
            else:
                # 其他类型消息保持不变
                processed_messages.append(message)
        
        # 确保所有消息都有唯一的ID以便追踪
        for idx, msg in enumerate(processed_messages):
            if not hasattr(msg, "id") or not msg.id:
                # 为消息添加一个临时ID
                timestamp = int(time.time() * 1000)
                setattr(msg, "id", f"msg_{timestamp}_{idx}")
        
        return processed_messages 