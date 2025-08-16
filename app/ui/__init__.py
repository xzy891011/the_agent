"""
用户界面和流式处理模块

提供Gradio界面、React前端、流式处理等功能
"""

# 导入主要的流式处理组件
from .streaming import (
    LangGraphStreamer,
    StreamMode,
    get_stream_writer,
    create_stream_processor,
    DEFAULT_STREAM_MODES,
    ALL_STREAM_MODES
)

from .streaming_types import (
    StreamMessageType,
    StreamMessage,
    NodeStatusMessage,
    RouterMessage,
    LLMTokenMessage,
    LLMCompleteMessage,
    ToolExecutionMessage,
    FileGeneratedMessage,
    AgentThinkingMessage,
    SystemMessage
)

from .streaming_processor import LangGraphStreamingProcessor

# 版本信息
__version__ = "2.0.0"

# 导出列表
__all__ = [
    # 主要流式处理类
    "LangGraphStreamer",
    "LangGraphStreamingProcessor",
    
    # 流模式和配置
    "StreamMode",
    "DEFAULT_STREAM_MODES",
    "ALL_STREAM_MODES",
    
    # 工厂函数
    "get_stream_writer",
    "create_stream_processor",
    
    # 消息类型
    "StreamMessageType",
    "StreamMessage",
    "NodeStatusMessage",
    "RouterMessage",
    "LLMTokenMessage",
    "LLMCompleteMessage",
    "ToolExecutionMessage",
    "FileGeneratedMessage",
    "AgentThinkingMessage",
    "SystemMessage"
] 