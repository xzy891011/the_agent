"""
LangGraph流式处理器主入口模块

提供统一的流式处理接口，兼容现有系统
"""

import logging
import time
from typing import Dict, Any, Generator, List, Optional, Union
from enum import Enum

# 导入流式处理器和类型
from app.ui.streaming_processor import LangGraphStreamingProcessor
from app.ui.streaming_types import (
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

logger = logging.getLogger(__name__)

class StreamMode(str, Enum):
    """流模式枚举 - 兼容现有代码"""
    MESSAGES = "messages"
    CUSTOM = "custom"
    UPDATES = "updates"
    VALUES = "values"
    EVENTS = "events"
    DEBUG = "debug"

# 为了兼容性，提供多种流模式组合
DEFAULT_STREAM_MODES = ["messages", "custom", "updates", "values"]
ALL_STREAM_MODES = ["messages", "custom", "updates", "values", "events", "debug"]

class LangGraphStreamer:
    """
    LangGraph流处理器 - 兼容现有代码接口
    
    这是一个适配器类，内部使用新的LangGraphStreamingProcessor
    """
    
    def __init__(
        self,
        stream_modes: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        初始化流处理器
        
        Args:
            stream_modes: 流模式列表
            session_id: 会话ID
            config: 配置参数
        """
        self.stream_modes = stream_modes or DEFAULT_STREAM_MODES
        self.session_id = session_id
        self.config = config or {}
        
        # 内部使用新的流处理器
        self.processor = LangGraphStreamingProcessor(session_id=session_id)
        
        logger.info(f"LangGraph流处理器初始化，使用流模式: {self.stream_modes}")
    
    def process_stream(
        self, 
        stream_generator: Generator[Dict[str, Any], None, None]
    ) -> Generator[Dict[str, Any], None, None]:
        """
        处理LangGraph流输出 - 兼容原有接口
        
        Args:
            stream_generator: LangGraph的流生成器
            
        Yields:
            Dict[str, Any]: 处理后的流数据
        """
        logger.info("开始处理LangGraph流输出")
        logger.info("已重置token_buffer，确保不会累积上一轮对话内容")
        
        chunk_count = 0
        try:
            for chunk in stream_generator:
                chunk_count += 1
                logger.debug(f"[DEBUG] 原始chunk消息内容: {chunk}")
                # 使用新的处理器处理数据块
                processed_chunks = self.processor._process_stream_chunk(chunk)
                
                # 向后兼容：如果没有处理结果，尝试转换原始chunk格式
                if not processed_chunks:
                    # 处理原始chunk，确保有role和content字段
                    converted_chunk = self._handle_raw_chunk(chunk)
                    if converted_chunk:
                        yield converted_chunk
                else:
                    # 返回处理后的消息
                    for processed_chunk in processed_chunks:
                        yield self._convert_to_legacy_format(processed_chunk)
                        
        except Exception as e:
            logger.error(f"流处理过程中出现错误: {e}")
            raise
        finally:
            logger.info(f"流处理完成，共处理 {chunk_count} 个数据块")
    
    def _convert_to_legacy_format(self, stream_message: StreamMessage) -> Dict[str, Any]:
        """
        将新格式的流消息转换为旧格式以保持兼容性
        
        Args:
            stream_message: 新格式的流消息
            
        Returns:
            Dict[str, Any]: 旧格式的数据，包含role和content字段
        """
        # 基本格式转换
        result = {
            "type": stream_message.type.value,
            "timestamp": stream_message.timestamp.isoformat(),
            "session_id": stream_message.session_id,
            "source": getattr(stream_message, "source", None) or "unknown"
        }
        
        # 添加元数据
        metadata = getattr(stream_message, "metadata", None)
        if metadata:
            result["metadata"] = metadata
        
        # 根据消息类型添加role和content字段以及特定字段
        if stream_message.type == StreamMessageType.LLM_TOKEN:
            # LLM消息作为assistant角色
            result["role"] = "assistant"
            result["content"] = getattr(stream_message, "content", "")
            result["is_token"] = True
            result["is_complete"] = getattr(stream_message, "is_complete", False)
            result["token"] = getattr(stream_message, "content", "")  # token就是content
            result["llm_model"] = getattr(stream_message, "llm_model", "")
            
        elif stream_message.type == StreamMessageType.LLM_COMPLETE:
            # LLM完成消息作为assistant角色
            result["role"] = "assistant"
            result["content"] = getattr(stream_message, "content", "")
            result["is_token"] = False
            result["is_complete"] = True
            result["llm_model"] = getattr(stream_message, "llm_model", "")
            
        elif stream_message.type in [StreamMessageType.TOOL_START, StreamMessageType.TOOL_COMPLETE, StreamMessageType.TOOL_PROGRESS, StreamMessageType.TOOL_ERROR]:
            # 工具消息作为tool角色
            result["role"] = "tool"
            result["content"] = getattr(stream_message, "output", "") or getattr(stream_message, "error_message", "")
            result["tool_name"] = getattr(stream_message, "tool_name", "")
            result["status"] = getattr(stream_message, "action", "")  # action字段映射为status
            result["action"] = getattr(stream_message, "action", "")
            execution_time = getattr(stream_message, "execution_time", None)
            if execution_time is not None:
                result["execution_time"] = execution_time
                
        elif stream_message.type == StreamMessageType.FILE_GENERATED:
            # 文件生成消息作为system角色
            result["role"] = "system"
            file_name = getattr(stream_message, "file_name", "unknown")
            result["content"] = f"已生成文件: {file_name}"
            result["file_id"] = getattr(stream_message, "file_id", "")
            result["file_name"] = file_name
            result["file_path"] = getattr(stream_message, "file_path", "")
            result["file_type"] = getattr(stream_message, "file_type", "")
            result["category"] = getattr(stream_message, "category", "generated")
            
        elif stream_message.type == StreamMessageType.AGENT_THINKING:
            # Agent思考消息作为system角色
            result["role"] = "system"
            agent_name = getattr(stream_message, "agent_name", "Agent")
            content = getattr(stream_message, "content", "")
            result["content"] = f"🤔 {agent_name} 正在思考: {content}"
            result["agent_name"] = agent_name
            result["thinking_type"] = getattr(stream_message, "thinking_type", "")
            
        elif stream_message.type in [StreamMessageType.NODE_START, StreamMessageType.NODE_COMPLETE, StreamMessageType.NODE_ERROR]:
            # 节点状态消息作为system角色
            result["role"] = "system"
            node_name = getattr(stream_message, "node_name", "unknown")
            status = getattr(stream_message, "status", "")
            result["content"] = f"节点 {node_name} 状态: {status}"
            result["node_name"] = node_name
            result["status"] = status
            result["details"] = getattr(stream_message, "details", "")
            
        elif stream_message.type in [StreamMessageType.ROUTE_DECISION, StreamMessageType.ROUTE_CHANGE]:
            # 路由消息作为system角色
            result["role"] = "system"
            to_node = getattr(stream_message, "to_node", "unknown")
            reason = getattr(stream_message, "reason", "")
            result["content"] = f"路由决策: 转向 {to_node} - {reason}"
            result["to_node"] = to_node
            result["reason"] = reason
            
        elif stream_message.type in [StreamMessageType.ERROR, StreamMessageType.INFO]:
            # 错误和信息消息作为system角色
            result["role"] = "system"
            result["content"] = getattr(stream_message, "content", "")
            result["level"] = getattr(stream_message, "level", "info")
            if stream_message.type == StreamMessageType.ERROR:
                result["error_message"] = getattr(stream_message, "error_message", "")
                
        else:
            # 默认处理
            result["role"] = "system"
            result["content"] = str(getattr(stream_message, "content", "") or str(stream_message))
        
        # 构建data字段用于向后兼容性
        result["data"] = {
            key: value for key, value in result.items() 
            if key not in ["type", "timestamp", "session_id", "role", "content"]
        }
        
        return result
    
    def _handle_raw_chunk(self, chunk: Any) -> Optional[Dict[str, Any]]:
        """
        处理原始chunk，转换为包含role和content的格式
        
        Args:
            chunk: 原始chunk数据
            
        Returns:
            Dict[str, Any]: 包含role和content字段的数据，或None
        """
        try:
            # 处理tuple格式的消息chunk（LangGraph消息流格式）
            if isinstance(chunk, tuple) and len(chunk) == 2:
                node_name, message = chunk
                
                from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage, SystemMessage, HumanMessage
                
                if isinstance(message, (AIMessage, AIMessageChunk)):
                    # 对于AIMessageChunk，检查finish_reason来判断是否是完整消息
                    is_complete = False
                    if hasattr(message, 'response_metadata') and message.response_metadata:
                        is_complete = message.response_metadata.get('finish_reason') is not None
                    
                    return {
                        "role": "assistant",
                        "content": message.content or "",
                        "source": node_name,
                        "type": "ai_message_chunk" if isinstance(message, AIMessageChunk) else "ai_message",
                        "is_token": isinstance(message, AIMessageChunk),
                        "is_complete": is_complete,
                        "timestamp": time.time()
                    }
                elif isinstance(message, ToolMessage):
                    return {
                        "role": "tool",
                        "content": message.content or "",
                        "source": node_name,
                        "type": "tool_message",
                        "tool_name": getattr(message, 'name', 'unknown'),
                        "timestamp": time.time()
                    }
                elif isinstance(message, SystemMessage):
                    return {
                        "role": "system",
                        "content": message.content or "",
                        "source": node_name,
                        "type": "system_message",
                        "timestamp": time.time()
                    }
                elif isinstance(message, HumanMessage):
                    return {
                        "role": "user",
                        "content": message.content or "",
                        "source": node_name,
                        "type": "human_message",
                        "timestamp": time.time()
                    }
            
            # 处理已经是字典格式的chunk
            elif isinstance(chunk, dict):
                # 如果已经有role字段，直接返回
                if "role" in chunk:
                    return chunk
                
                # 否则尝试从类型推断role
                chunk_type = chunk.get("type", "")
                content = chunk.get("content", "")
                
                if "ai" in chunk_type.lower() or "assistant" in chunk_type.lower():
                    role = "assistant"
                elif "tool" in chunk_type.lower():
                    role = "tool"
                elif "system" in chunk_type.lower():
                    role = "system"
                elif "human" in chunk_type.lower() or "user" in chunk_type.lower():
                    role = "user"
                else:
                    role = "system"  # 默认为system
                
                result = chunk.copy()
                result["role"] = role
                if "content" not in result:
                    result["content"] = str(content)
                if "timestamp" not in result:
                    result["timestamp"] = time.time()
                
                return result
            
            # 处理其他格式
            else:
                return {
                    "role": "system",
                    "content": str(chunk),
                    "type": "raw_data",
                    "timestamp": time.time()
                }
                
        except Exception as e:
            logger.error(f"处理原始chunk时出错: {str(e)}")
            return {
                "role": "system",
                "content": f"处理数据时出错: {str(e)}",
                "type": "error",
                "timestamp": time.time()
            }
    
    def reset(self):
        """重置流处理器状态"""
        self.processor.reset()
        logger.info("流处理器状态已重置")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取流处理统计信息"""
        # 返回基本统计信息
        return {
            "session_id": self.session_id,
            "stream_modes": self.stream_modes,
            "message_buffer_size": len(getattr(self.processor, 'message_buffer', [])),
            "active_nodes": len(getattr(self.processor, 'active_nodes', {}))
        }


def get_stream_writer(session_id: Optional[str] = None) -> LangGraphStreamingProcessor:
    """
    获取流处理器实例 - 兼容现有代码
    
    ⚠️ 注意：此函数返回的是流数据处理器，不是推送器。
    如需推送流式消息，请使用 app.core.stream_writer_helper 中的推送函数。
    
    Args:
        session_id: 会话ID
        
    Returns:
        LangGraphStreamingProcessor: 流处理器实例（仅用于处理流数据）
    """
    return LangGraphStreamingProcessor(session_id=session_id)


def create_stream_processor(
    stream_modes: Optional[List[str]] = None,
    session_id: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None
) -> LangGraphStreamer:
    """
    创建流处理器的工厂函数
    
    Args:
        stream_modes: 流模式列表
        session_id: 会话ID
        config: 配置参数
        
    Returns:
        LangGraphStreamer: 流处理器实例
    """
    return LangGraphStreamer(
        stream_modes=stream_modes,
        session_id=session_id,
        config=config
    )


# 导出主要类和函数供外部使用
__all__ = [
    "LangGraphStreamer",
    "StreamMode",
    "get_stream_writer",
    "create_stream_processor",
    "DEFAULT_STREAM_MODES",
    "ALL_STREAM_MODES",
    # 从streaming_types模块导出
    "StreamMessageType",
    "StreamMessage",
    "NodeStatusMessage",
    "RouterMessage", 
    "LLMTokenMessage",
    "LLMCompleteMessage",
    "ToolExecutionMessage",
    "FileGeneratedMessage",
    "AgentThinkingMessage",
    "SystemMessage",
    # 从streaming_processor模块导出
    "LangGraphStreamingProcessor"
] 