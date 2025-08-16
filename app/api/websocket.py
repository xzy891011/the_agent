"""
WebSocket管理器 - 处理实时双向通信和流式数据传输

功能包括：
1. WebSocket连接管理
2. 实时消息处理
3. 流式数据传输
4. 多模态数据支持
5. 会话状态同步
"""

import json
import asyncio
import logging
from typing import Dict, List, Set, Optional, Any
from datetime import datetime
import uuid

from fastapi import WebSocket, WebSocketDisconnect
from app.core.engine import IsotopeEngine
from app.api.models import (
    WebSocketMessage, 
    WebSocketMessageType, 
    StreamResponse,
    MediaType,
    MediaContent
)

logger = logging.getLogger(__name__)

class WebSocketManager:
    """WebSocket连接和消息管理器"""
    
    def __init__(self, engine: IsotopeEngine):
        """初始化WebSocket管理器
        
        Args:
            engine: 引擎实例
        """
        self.engine = engine
        
        # 连接管理
        self.active_connections: Dict[str, Set[WebSocket]] = {}  # session_id -> websockets
        self.connection_sessions: Dict[WebSocket, str] = {}  # websocket -> session_id
        
        # 消息缓冲
        self.message_buffer: Dict[str, List[Dict[str, Any]]] = {}  # session_id -> messages
        
        logger.info("WebSocket管理器初始化完成")
    
    async def connect(self, websocket: WebSocket, session_id: str):
        """建立WebSocket连接
        
        Args:
            websocket: WebSocket连接
            session_id: 会话ID
        """
        await websocket.accept()
        
        # 将连接添加到管理器
        if session_id not in self.active_connections:
            self.active_connections[session_id] = set()
        self.active_connections[session_id].add(websocket)
        self.connection_sessions[websocket] = session_id
        
        # 初始化消息缓冲
        if session_id not in self.message_buffer:
            self.message_buffer[session_id] = []
        
        logger.info(f"WebSocket连接建立: session_id={session_id}, 总连接数={self.get_connection_count()}")
        
        # 发送连接确认消息
        await self.send_to_connection(
            websocket,
            WebSocketMessage(
                type=WebSocketMessageType.CONNECT,
                data={
                    "status": "connected",
                    "session_id": session_id,
                    "message": "WebSocket连接已建立"
                },
                session_id=session_id
            )
        )
        
        # 如果会话不存在，创建新会话
        if not self.engine.get_session_by_id(session_id):
            self.engine.create_session(session_id)
            logger.info(f"为WebSocket连接创建新会话: {session_id}")
    
    def disconnect(self, websocket: WebSocket, session_id: str):
        """断开WebSocket连接
        
        Args:
            websocket: WebSocket连接
            session_id: 会话ID
        """
        # 从连接管理器中移除
        if session_id in self.active_connections:
            self.active_connections[session_id].discard(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
        
        if websocket in self.connection_sessions:
            del self.connection_sessions[websocket]
        
        logger.info(f"WebSocket连接断开: session_id={session_id}, 剩余连接数={self.get_connection_count()}")
    
    async def handle_message(self, websocket: WebSocket, session_id: str, data: str):
        """处理接收到的WebSocket消息
        
        Args:
            websocket: WebSocket连接
            session_id: 会话ID
            data: 消息数据
        """
        try:
            # 解析消息
            message_data = json.loads(data)
            message_type = message_data.get("type", "chat")
            content = message_data.get("data", {})
            
            if message_type == "chat":
                await self._handle_chat_message(websocket, session_id, content)
            elif message_type == "ping":
                await self._handle_ping(websocket, session_id)
            elif message_type == "system":
                await self._handle_system_message(websocket, session_id, content)
            else:
                logger.warning(f"未知消息类型: {message_type}")
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误: {str(e)}")
            await self.send_error(websocket, "消息格式错误", "JSON_PARSE_ERROR")
        except Exception as e:
            logger.error(f"处理WebSocket消息错误: {str(e)}")
            await self.send_error(websocket, f"处理消息时出错: {str(e)}", "MESSAGE_PROCESSING_ERROR")
    
    async def _handle_chat_message(self, websocket: WebSocket, session_id: str, content: Dict[str, Any]):
        """处理聊天消息
        
        Args:
            websocket: WebSocket连接
            session_id: 会话ID
            content: 消息内容
        """
        user_message = content.get("message", "")
        if not user_message.strip():
            await self.send_error(websocket, "消息内容不能为空", "EMPTY_MESSAGE")
            return
        
        # 发送流开始通知
        await self.send_to_connection(
            websocket,
            WebSocketMessage(
                type=WebSocketMessageType.STREAM_START,
                data={
                    "message": "开始处理您的消息...",
                    "user_message": user_message
                },
                session_id=session_id
            )
        )
        
        try:
            # 使用引擎的流式处理方法
            stream_generator = self.engine.process_message_streaming(
                message=user_message,
                session_id=session_id,
                stream_mode=self.engine.config.get("ui", {}).get("stream_mode", ["messages", "custom", "updates", "events"])
            )
            
            # 处理流式响应
            message_count = 0
            for stream_chunk in stream_generator:
                message_count += 1
                
                # 将流数据转换为WebSocket消息
                ws_message = await self._convert_stream_to_websocket(stream_chunk, session_id)
                if ws_message:
                    await self.send_to_connection(websocket, ws_message)
            
            # 发送流结束通知
            await self.send_to_connection(
                websocket,
                WebSocketMessage(
                    type=WebSocketMessageType.STREAM_END,
                    data={
                        "message": "消息处理完成",
                        "total_chunks": message_count
                    },
                    session_id=session_id
                )
            )
            
            logger.info(f"完成流式处理: session_id={session_id}, 处理了{message_count}个数据块")
            
        except Exception as e:
            logger.error(f"流式处理错误: {str(e)}")
            await self.send_error(websocket, f"处理消息时出错: {str(e)}", "STREAM_PROCESSING_ERROR")
    
    async def _convert_stream_to_websocket(
        self, 
        stream_chunk: Dict[str, Any], 
        session_id: str
    ) -> Optional[WebSocketMessage]:
        """将流数据转换为WebSocket消息
        
        Args:
            stream_chunk: 流数据块
            session_id: 会话ID
            
        Returns:
            WebSocket消息或None
        """
        if not stream_chunk:
            return None
        
        try:
            # 检测消息类型和内容
            chunk_type = stream_chunk.get("type", "unknown")
            role = stream_chunk.get("role", "unknown")
            content = stream_chunk.get("content", "")
            
            # 构建WebSocket消息数据
            ws_data = {
                "role": role,
                "content": content,
                "type": chunk_type
            }
            
            # 处理多模态内容
            if "image_path" in stream_chunk:
                ws_data["media"] = {
                    "type": "image",
                    "url": f"/static/{stream_chunk['image_path'].split('/')[-1]}",
                    "metadata": stream_chunk.get("metadata", {})
                }
            
            if "file_id" in stream_chunk:
                ws_data["media"] = {
                    "type": "file",
                    "file_id": stream_chunk["file_id"],
                    "metadata": stream_chunk.get("metadata", {})
                }
            
            # 处理工具执行结果
            if "tool_name" in stream_chunk:
                ws_data["tool_execution"] = {
                    "tool_name": stream_chunk["tool_name"],
                    "status": stream_chunk.get("status", "completed"),
                    "result": stream_chunk.get("result")
                }
            
            # 处理DAG信息
            if "dag" in stream_chunk:
                ws_data["dag"] = stream_chunk["dag"]
            
            # 复制其他元数据
            for key in ["timestamp", "message_id", "agent_name"]:
                if key in stream_chunk:
                    ws_data[key] = stream_chunk[key]
            
            return WebSocketMessage(
                type=WebSocketMessageType.STREAM_DATA,
                data=ws_data,
                session_id=session_id
            )
            
        except Exception as e:
            logger.error(f"转换流数据为WebSocket消息失败: {str(e)}")
            return None
    
    async def _handle_ping(self, websocket: WebSocket, session_id: str):
        """处理ping消息
        
        Args:
            websocket: WebSocket连接
            session_id: 会话ID
        """
        await self.send_to_connection(
            websocket,
            WebSocketMessage(
                type=WebSocketMessageType.PONG,
                data={"message": "pong"},
                session_id=session_id
            )
        )
    
    async def _handle_system_message(self, websocket: WebSocket, session_id: str, content: Dict[str, Any]):
        """处理系统消息
        
        Args:
            websocket: WebSocket连接
            session_id: 会话ID
            content: 消息内容
        """
        command = content.get("command")
        
        if command == "get_session_info":
            # 获取会话信息
            session_state = self.engine.get_session_state(session_id)
            if session_state:
                await self.send_to_connection(
                    websocket,
                    WebSocketMessage(
                        type=WebSocketMessageType.STREAM_DATA,
                        data={
                            "type": "session_info",
                            "session_id": session_id,
                            "message_count": len(session_state.get("messages", [])),
                            "files_count": len(session_state.get("files", {}))
                        },
                        session_id=session_id
                    )
                )
        
        elif command == "get_dag_visualization":
            # 获取DAG可视化
            try:
                dag_image = self.engine.generate_graph_image()
                if dag_image:
                    await self.send_to_connection(
                        websocket,
                        WebSocketMessage(
                            type=WebSocketMessageType.STREAM_DATA,
                            data={
                                "type": "dag_visualization",
                                "image_data": dag_image,
                                "format": "base64"
                            },
                            session_id=session_id
                        )
                    )
            except Exception as e:
                logger.error(f"生成DAG可视化失败: {str(e)}")
                await self.send_error(websocket, "生成DAG可视化失败", "DAG_GENERATION_ERROR")
    
    async def send_to_connection(self, websocket: WebSocket, message: WebSocketMessage):
        """向特定连接发送消息
        
        Args:
            websocket: WebSocket连接
            message: 要发送的消息
        """
        try:
            message_json = message.model_dump_json()
            await websocket.send_text(message_json)
        except Exception as e:
            logger.error(f"发送WebSocket消息失败: {str(e)}")
    
    async def send_to_session(self, session_id: str, message: WebSocketMessage):
        """向会话的所有连接发送消息
        
        Args:
            session_id: 会话ID
            message: 要发送的消息
        """
        if session_id in self.active_connections:
            disconnected_connections = []
            
            for websocket in self.active_connections[session_id]:
                try:
                    await self.send_to_connection(websocket, message)
                except Exception as e:
                    logger.error(f"发送消息到连接失败: {str(e)}")
                    disconnected_connections.append(websocket)
            
            # 清理断开的连接
            for websocket in disconnected_connections:
                self.disconnect(websocket, session_id)
    
    async def send_error(self, websocket: WebSocket, message: str, error_code: str):
        """发送错误消息
        
        Args:
            websocket: WebSocket连接
            message: 错误消息
            error_code: 错误代码
        """
        session_id = self.connection_sessions.get(websocket)
        error_message = WebSocketMessage(
            type=WebSocketMessageType.ERROR,
            data={
                "error": message,
                "error_code": error_code
            },
            session_id=session_id
        )
        await self.send_to_connection(websocket, error_message)
    
    def get_connection_count(self) -> int:
        """获取活跃连接数
        
        Returns:
            活跃连接总数
        """
        return sum(len(connections) for connections in self.active_connections.values())
    
    def get_session_connection_count(self, session_id: str) -> int:
        """获取特定会话的连接数
        
        Args:
            session_id: 会话ID
            
        Returns:
            会话连接数
        """
        return len(self.active_connections.get(session_id, set()))
    
    async def broadcast_to_all(self, message: WebSocketMessage):
        """向所有连接广播消息
        
        Args:
            message: 要广播的消息
        """
        for session_id in self.active_connections:
            await self.send_to_session(session_id, message) 