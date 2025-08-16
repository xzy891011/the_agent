"""
流式消息类型定义模块
基于LangGraph和Vercel AI SDK设计的统一流式消息架构
"""

from enum import Enum
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


class StreamMessageType(str, Enum):
    """流式消息类型枚举"""
    # 节点状态相关
    NODE_START = "node_start"           # 节点开始执行
    NODE_COMPLETE = "node_complete"     # 节点执行完成
    NODE_ERROR = "node_error"           # 节点执行错误
    
    # 路由相关
    ROUTE_DECISION = "route_decision"   # 路由决策
    ROUTE_CHANGE = "route_change"       # 路由变化
    
    # LLM相关
    LLM_TOKEN = "llm_token"            # LLM token流
    LLM_COMPLETE = "llm_complete"      # LLM回答完成
    
    # 工具执行相关
    TOOL_START = "tool_start"          # 工具开始执行
    TOOL_PROGRESS = "tool_progress"    # 工具执行进度
    TOOL_COMPLETE = "tool_complete"    # 工具执行完成
    TOOL_ERROR = "tool_error"          # 工具执行错误
    
    # 文件相关
    FILE_GENERATED = "file_generated"  # 文件生成
    FILE_UPLOADED = "file_uploaded"    # 文件上传
    
    # Agent思考相关
    AGENT_THINKING = "agent_thinking"  # Agent思考过程
    AGENT_ANALYSIS = "agent_analysis" # Agent分析结果
    
    # 系统状态相关
    SESSION_START = "session_start"    # 会话开始
    SESSION_END = "session_end"        # 会话结束
    ERROR = "error"                    # 通用错误
    INFO = "info"                      # 通用信息
    DEBUG = "debug"                    # 调试信息


class MessagePriority(str, Enum):
    """消息优先级"""
    LOW = "low"
    NORMAL = "normal" 
    HIGH = "high"
    URGENT = "urgent"


class BaseStreamMessage(BaseModel):
    """流式消息基类"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: StreamMessageType
    timestamp: datetime = Field(default_factory=datetime.now)
    session_id: Optional[str] = None
    source: Optional[str] = None  # 来源节点/智能体名称
    priority: MessagePriority = MessagePriority.NORMAL
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NodeStatusMessage(BaseStreamMessage):
    """节点状态消息"""
    node_name: str
    node_type: Optional[str] = None  # supervisor, agent, tool等
    status: str  # started, completed, error
    progress: Optional[float] = None  # 0.0-1.0
    details: Optional[str] = None
    duration: Optional[float] = None  # 执行耗时（秒）


class RouterMessage(BaseStreamMessage):
    """路由消息"""
    from_node: Optional[str] = None
    to_node: str
    reason: Optional[str] = None  # 路由原因
    available_routes: Optional[List[str]] = None


class LLMTokenMessage(BaseStreamMessage):
    """LLM Token消息"""
    content: str  # token内容
    is_complete: bool = False  # 是否完整回答完成
    llm_model: Optional[str] = None  # 重命名避免model_命名空间冲突
    token_count: Optional[int] = None


class ToolExecutionMessage(BaseStreamMessage):
    """工具执行消息"""
    tool_name: str
    action: str  # start, progress, complete, error
    input_params: Optional[Dict[str, Any]] = None
    output: Optional[Any] = None
    progress: Optional[float] = None  # 0.0-1.0
    error_message: Optional[str] = None
    execution_time: Optional[float] = None


class FileGeneratedMessage(BaseStreamMessage):
    """文件生成消息"""
    file_id: str
    file_name: str
    file_type: str  # image, document, data等
    file_path: str
    file_size: Optional[int] = None
    category: str = "generated"  # upload, generated, temp
    folder_path: Optional[str] = None  # 在文件树中的路径
    preview_url: Optional[str] = None  # 预览URL
    download_url: Optional[str] = None  # 下载URL


class AgentThinkingMessage(BaseStreamMessage):
    """Agent思考消息"""
    agent_name: str
    thinking_type: str  # analysis, planning, reasoning等
    content: str
    confidence: Optional[float] = None  # 0.0-1.0
    step_number: Optional[int] = None


class ErrorMessage(BaseStreamMessage):
    """错误消息"""
    error_code: Optional[str] = None
    error_message: str
    error_details: Optional[Dict[str, Any]] = None
    recoverable: bool = True
    suggested_action: Optional[str] = None


class InfoMessage(BaseStreamMessage):
    """信息消息"""
    title: Optional[str] = None
    content: str
    level: str = "info"  # info, warning, success
    actionable: bool = False
    action_label: Optional[str] = None
    action_data: Optional[Dict[str, Any]] = None


# 消息类型映射
MESSAGE_TYPE_MAP = {
    StreamMessageType.NODE_START: NodeStatusMessage,
    StreamMessageType.NODE_COMPLETE: NodeStatusMessage,
    StreamMessageType.NODE_ERROR: NodeStatusMessage,
    StreamMessageType.ROUTE_DECISION: RouterMessage,
    StreamMessageType.ROUTE_CHANGE: RouterMessage,
    StreamMessageType.LLM_TOKEN: LLMTokenMessage,
    StreamMessageType.LLM_COMPLETE: LLMTokenMessage,
    StreamMessageType.TOOL_START: ToolExecutionMessage,
    StreamMessageType.TOOL_PROGRESS: ToolExecutionMessage,
    StreamMessageType.TOOL_COMPLETE: ToolExecutionMessage,
    StreamMessageType.TOOL_ERROR: ToolExecutionMessage,
    StreamMessageType.FILE_GENERATED: FileGeneratedMessage,
    StreamMessageType.FILE_UPLOADED: FileGeneratedMessage,
    StreamMessageType.AGENT_THINKING: AgentThinkingMessage,
    StreamMessageType.ERROR: ErrorMessage,
    StreamMessageType.INFO: InfoMessage,
}


def create_message(
    message_type: StreamMessageType,
    session_id: Optional[str] = None,
    source: Optional[str] = None,
    **kwargs
) -> BaseStreamMessage:
    """
    工厂函数：创建指定类型的流式消息
    
    Args:
        message_type: 消息类型
        session_id: 会话ID
        source: 消息来源
        **kwargs: 其他参数
        
    Returns:
        对应类型的消息实例
    """
    message_class = MESSAGE_TYPE_MAP.get(message_type, InfoMessage)
    
    return message_class(
        type=message_type,
        session_id=session_id,
        source=source,
        **kwargs
    )


def serialize_message(message: BaseStreamMessage) -> Dict[str, Any]:
    """
    序列化消息为字典格式，用于JSON传输
    
    Args:
        message: 消息实例
        
    Returns:
        序列化后的字典
    """
    data = message.model_dump()
    data["timestamp"] = message.timestamp.isoformat()
    return data


def deserialize_message(data: Dict[str, Any]) -> BaseStreamMessage:
    """
    从字典反序列化消息
    
    Args:
        data: 序列化的消息数据
        
    Returns:
        消息实例
    """
    message_type = StreamMessageType(data["type"])
    message_class = MESSAGE_TYPE_MAP.get(message_type, InfoMessage)
    
    # 转换时间戳
    if "timestamp" in data and isinstance(data["timestamp"], str):
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
    
    return message_class(**data)


# 类型别名，用于兼容性
StreamMessage = BaseStreamMessage  # 主要的流式消息类型
LLMCompleteMessage = LLMTokenMessage  # LLM完成消息，复用Token消息类
SystemMessage = InfoMessage  # 系统消息，复用Info消息类

# 导出列表
__all__ = [
    # 枚举
    "StreamMessageType",
    "MessagePriority",
    
    # 基础类
    "BaseStreamMessage",
    "StreamMessage",  # 类型别名
    
    # 具体消息类
    "NodeStatusMessage",
    "RouterMessage", 
    "LLMTokenMessage",
    "LLMCompleteMessage",  # 类型别名
    "ToolExecutionMessage",
    "FileGeneratedMessage",
    "AgentThinkingMessage",
    "ErrorMessage",
    "InfoMessage",
    "SystemMessage",  # 类型别名
    
    # 工具函数
    "create_message",
    "serialize_message",
    "deserialize_message",
    "MESSAGE_TYPE_MAP"
] 