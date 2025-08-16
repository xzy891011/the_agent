"""
API数据模型 - 定义请求和响应的数据结构

功能包括：
1. 通用API响应格式
2. 聊天相关数据模型
3. 会话管理数据模型
4. 文件管理数据模型
5. 多模态数据模型
"""

from typing import Dict, Any, Optional, List, Union
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

# ==================== 通用响应模型 ====================

class APIResponse(BaseModel):
    """通用API响应格式"""
    success: bool = Field(description="操作是否成功")
    message: str = Field(description="响应消息")
    data: Optional[Dict[str, Any]] = Field(None, description="响应数据")
    timestamp: datetime = Field(default_factory=datetime.now, description="响应时间戳")

class ErrorResponse(APIResponse):
    """错误响应格式"""
    success: bool = Field(default=False, description="操作失败")
    error: str = Field(description="错误详情")
    error_code: Optional[str] = Field(None, description="错误代码")

class StreamResponse(BaseModel):
    """流式响应格式"""
    type: str = Field(description="消息类型")
    data: Dict[str, Any] = Field(description="消息数据")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")

# ==================== 聊天相关模型 ====================

class MessageType(str, Enum):
    """消息类型枚举"""
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    TOOL_RESULT = "tool_result"
    SYSTEM = "system"
    ERROR = "error"
    INTERRUPT = "interrupt"

class MessageRole(str, Enum):
    """消息角色枚举"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"

class ChatMessage(BaseModel):
    """聊天消息模型"""
    role: MessageRole = Field(description="消息角色")
    content: str = Field(description="消息内容")
    type: MessageType = Field(default=MessageType.TEXT, description="消息类型")
    metadata: Optional[Dict[str, Any]] = Field(None, description="消息元数据")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")

class ChatRequest(BaseModel):
    """聊天请求模型"""
    message: str = Field(description="用户消息")
    session_id: Optional[str] = Field(None, description="会话ID")
    stream: bool = Field(default=True, description="是否使用流式输出")
    context: Optional[Dict[str, Any]] = Field(None, description="额外上下文")

class ChatResponse(APIResponse):
    """聊天响应模型"""
    chat_message: ChatMessage = Field(description="回复消息")
    session_id: str = Field(description="会话ID")

# ==================== 会话管理模型 ====================

class SessionStatus(str, Enum):
    """会话状态枚举"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    INTERRUPTED = "interrupted"
    ERROR = "error"

class SessionInfo(BaseModel):
    """会话信息模型"""
    session_id: str = Field(description="会话ID")
    status: SessionStatus = Field(description="会话状态")
    created_at: datetime = Field(description="创建时间")
    last_updated: datetime = Field(description="最后更新时间")
    message_count: int = Field(default=0, description="消息数量")
    metadata: Optional[Dict[str, Any]] = Field(None, description="会话元数据")

class CreateSessionRequest(BaseModel):
    """创建会话请求"""
    session_name: Optional[str] = Field(None, description="会话名称")
    session_description: Optional[str] = Field(None, description="会话描述")
    initial_message: Optional[str] = Field(None, description="初始消息")
    metadata: Optional[Dict[str, Any]] = Field(None, description="会话元数据")

class SessionListResponse(APIResponse):
    """会话列表响应"""
    sessions: List[SessionInfo] = Field(description="会话列表")

# ==================== 文件管理模型 ====================

class FileType(str, Enum):
    """文件类型枚举"""
    IMAGE = "image"
    DOCUMENT = "document"
    DATA = "data"
    ARCHIVE = "archive"
    TEXT = "text"
    CODE = "code"
    SPREADSHEET = "spreadsheet"
    PRESENTATION = "presentation"
    OTHER = "other"

class FileInfo(BaseModel):
    """文件信息模型"""
    file_id: str = Field(description="文件ID")
    file_name: str = Field(description="文件名")
    file_type: FileType = Field(description="文件类型")
    file_size: int = Field(description="文件大小（字节）")
    content_type: str = Field(description="MIME类型")
    upload_time: datetime = Field(description="上传时间")
    session_id: Optional[str] = Field(None, description="关联会话ID")
    url: Optional[str] = Field(None, description="文件访问URL")
    file_path: Optional[str] = Field(None, description="文件路径/文件夹路径")
    metadata: Optional[Dict[str, Any]] = Field(None, description="文件元数据")

class FileUploadResponse(APIResponse):
    """文件上传响应"""
    file_info: FileInfo = Field(description="文件信息")

class FileListResponse(APIResponse):
    """文件列表响应"""
    files: List[FileInfo] = Field(description="文件列表")

class FileAssociateRequest(BaseModel):
    """文件关联请求"""
    target_session_id: str = Field(description="目标会话ID")

# ==================== 多模态数据模型 ====================

class MediaType(str, Enum):
    """媒体类型枚举"""
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"
    CHART = "chart"
    TABLE = "table"
    CODE = "code"
    DAG = "dag"

class MediaContent(BaseModel):
    """多媒体内容模型"""
    type: MediaType = Field(description="媒体类型")
    content: Union[str, Dict[str, Any]] = Field(description="内容数据")
    metadata: Optional[Dict[str, Any]] = Field(None, description="媒体元数据")
    url: Optional[str] = Field(None, description="媒体URL")

class MultimodalMessage(BaseModel):
    """多模态消息模型"""
    role: MessageRole = Field(description="消息角色")
    contents: List[MediaContent] = Field(description="多媒体内容列表")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")

# ==================== 系统管理模型 ====================

class SystemStatus(BaseModel):
    """系统状态模型"""
    engine_status: str = Field(description="引擎状态")
    memory_usage: Optional[Dict[str, Any]] = Field(None, description="内存使用情况")
    active_sessions: int = Field(description="活跃会话数")
    active_connections: int = Field(description="活跃连接数")
    uptime: Optional[str] = Field(None, description="运行时间")

class SystemStatusResponse(APIResponse):
    """系统状态响应"""
    status: SystemStatus = Field(description="系统状态")

# ==================== WebSocket消息模型 ====================

class WebSocketMessageType(str, Enum):
    """WebSocket消息类型"""
    CHAT = "chat"
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    PING = "ping"
    PONG = "pong"
    ERROR = "error"
    STREAM_START = "stream_start"
    STREAM_DATA = "stream_data"
    STREAM_END = "stream_end"

class WebSocketMessage(BaseModel):
    """WebSocket消息模型"""
    type: WebSocketMessageType = Field(description="消息类型")
    data: Dict[str, Any] = Field(description="消息数据")
    session_id: Optional[str] = Field(None, description="会话ID")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")

# ==================== 工具执行模型 ====================

class ToolExecutionStatus(str, Enum):
    """工具执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class ToolExecution(BaseModel):
    """工具执行模型"""
    tool_name: str = Field(description="工具名称")
    input_params: Dict[str, Any] = Field(description="输入参数")
    output: Optional[Any] = Field(None, description="输出结果")
    status: ToolExecutionStatus = Field(description="执行状态")
    error: Optional[str] = Field(None, description="错误信息")
    start_time: datetime = Field(default_factory=datetime.now, description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")

# ==================== DAG可视化模型 ====================

class DAGNode(BaseModel):
    """DAG节点模型"""
    id: str = Field(description="节点ID")
    label: str = Field(description="节点标签")
    type: str = Field(description="节点类型")
    status: str = Field(description="节点状态")
    metadata: Optional[Dict[str, Any]] = Field(None, description="节点元数据")

class DAGEdge(BaseModel):
    """DAG边模型"""
    from_node: str = Field(description="起始节点")
    to_node: str = Field(description="目标节点")
    label: Optional[str] = Field(None, description="边标签")

class DAGVisualization(BaseModel):
    """DAG可视化模型"""
    nodes: List[DAGNode] = Field(description="节点列表")
    edges: List[DAGEdge] = Field(description="边列表")
    layout: Optional[str] = Field(None, description="布局类型")
    metadata: Optional[Dict[str, Any]] = Field(None, description="图元数据") 