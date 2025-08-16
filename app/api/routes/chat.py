"""
聊天API路由 - 处理聊天相关的HTTP请求

功能包括：
1. 发送消息（同步和流式）
2. 获取对话历史
3. 处理多模态输入
4. 中断和恢复处理
"""

import logging
import uuid
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
import json
import time
from datetime import datetime

from app.core.engine import IsotopeEngine
from app.api.dependencies import get_engine
from app.api.models import (
    ChatRequest, 
    ChatResponse, 
    ChatMessage, 
    MessageRole, 
    MessageType,
    APIResponse,
    ErrorResponse
)

# 导入 StreamMessageType 枚举
from app.ui.streaming_types import StreamMessageType

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/send", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    engine: IsotopeEngine = Depends(get_engine)
):
    """发送聊天消息（同步模式）
    
    Args:
        request: 聊天请求
        engine: 引擎实例
        
    Returns:
        聊天响应
    """
    try:
        logger.info(f"开始处理聊天消息: {request.message[:50]}...")
        
        # 确保有会话ID
        session_id = request.session_id
        if not session_id:
            session_id = engine.create_session()
            logger.info(f"创建新会话: {session_id}")
        
        # 检查会话是否存在
        session = engine.get_session_by_id(session_id)
        logger.info(f"会话检查结果: {type(session)}")
        
        if not session:
            session_id = engine.create_session(session_id)
            logger.info(f"重新创建会话: {session_id}")
        
        # 检查流模式
        if request.stream:
            raise HTTPException(
                status_code=400, 
                detail="流式模式建议使用WebSocket连接（/ws/{session_id}）"
            )
        
        logger.info("准备调用process_message_streaming...")
        
        # 处理消息（同步模式） - 使用流式方法然后消费所有结果
        stream_generator = engine.process_message_streaming(
            message=request.message,
            session_id=session_id,
            stream_mode=engine.config.get("ui", {}).get("stream_mode", ["messages", "custom", "updates", "values"])
        )
        
        # 添加调试信息
        logger.info(f"stream_generator类型: {type(stream_generator)}")
        
        # 消费流并收集AI回复
        ai_responses = []
        
        for chunk in stream_generator:
            # 添加调试信息
            logger.info(f"收到chunk类型: {type(chunk)}, 内容: {chunk}")
            
            # 检查是否包含AI消息 - 格式是 {"role": "assistant", "content": "..."}
            if isinstance(chunk, dict):
                role = chunk.get("role")
                content = chunk.get("content", "")
                
                if role == "assistant" and content:
                    ai_responses.append(content)
            else:
                # 如果不是字典，记录警告
                logger.warning(f"收到非字典类型的chunk: {type(chunk)}")
                
                # 尝试处理其他可能的格式
                if hasattr(chunk, 'content'):
                    ai_responses.append(str(chunk.content))
                elif hasattr(chunk, '__str__'):
                    ai_responses.append(str(chunk))
        
        # 如果有AI回复，取合并结果；否则使用默认消息
        if ai_responses:
            content = "".join(ai_responses)
        else:
            # 尝试从最终会话状态获取
            final_state = engine.get_session_state(session_id)
            content = "我已经处理了您的请求。"
            
            if final_state and "messages" in final_state:
                messages = final_state["messages"]
                for msg in reversed(messages):
                    if hasattr(msg, "type") and msg.type == "ai":
                        content = msg.content
                        break
                    elif hasattr(msg, "__class__") and "AIMessage" in str(msg.__class__):
                        content = msg.content if hasattr(msg, "content") else str(msg)
                        break
                    elif isinstance(msg, dict) and msg.get("type") == "ai":
                        content = msg.get("content", "")
                        break
        
        if not content or not content.strip():
            content = "我已经处理了您的请求。"
        
        # 构建响应 - 兼容测试脚本的期望格式
        response_message = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=content,
            type=MessageType.TEXT
        )
        
        return ChatResponse(
            success=True,
            message="消息处理完成",
            data={
                "session_id": session_id,
                "message": {  # 保留这个字段以兼容测试脚本
                    "content": content,
                    "role": "assistant",
                    "type": "text"
                }
            },
            chat_message=response_message,
            session_id=session_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"发送消息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理消息时出错: {str(e)}")

@router.post("/send-stream")
async def send_message_stream(
    request: ChatRequest,
    engine: IsotopeEngine = Depends(get_engine)
):
    """发送聊天消息（流式模式）
    
    Args:
        request: 聊天请求
        engine: 引擎实例
        
    Returns:
        流式响应
    """
    try:
        # 确保有会话ID
        session_id = request.session_id
        if not session_id:
            session_id = engine.create_session()
        
        # 检查会话是否存在
        if not engine.get_session_by_id(session_id):
            session_id = engine.create_session(session_id)
        
        def sync_stream_generator():
            """同步流式数据生成器 - 确保真正的实时输出"""
            import sys
            import os
            
            try:
                # 使用引擎的流式处理
                stream_iter = engine.process_message_streaming(
                    message=request.message,
                    session_id=session_id,
                    stream_mode=engine.config.get("ui", {}).get("stream_mode", ["messages", "custom", "updates", "values"])
                )
                
                # 发送开始标记
                start_data = json.dumps({'type': 'start', 'session_id': session_id}, ensure_ascii=False)
                yield f"data: {start_data}\n\n"
                
                # 强制刷新每一个输出
                sys.stdout.flush()
                
                # 处理流式数据
                chunk_count = 0
                for chunk in stream_iter:
                    chunk_count += 1
                    
                    if chunk:
                        # 提取消息的基本信息
                        msg_type = chunk.get("type")
                        role = chunk.get("role")
                        content = chunk.get("content", "")
                        source = chunk.get("source", "")
                        
                        # 调试：记录chunk结构
                        logger.debug(f"处理chunk: type={msg_type}, role={role}, source={source}, content_length={len(str(content))}")
                        
                        # 根据 StreamMessageType 枚举来处理不同类型的消息
                        if msg_type == StreamMessageType.LLM_TOKEN:
                            # LLM token 流 - 直接发送给前端用于文本流显示
                            if content:
                                token_data = {
                                    "type": "token",  # 前端期待的token类型
                                    "content": content,
                                    "session_id": session_id,
                                    "chunk_id": chunk_count,
                                    "timestamp": time.time(),
                                    "source": source,
                                    "llm_model": chunk.get("llm_model", "unknown")
                                }
                                
                                logger.debug(f"🔤 发送LLM Token: source={source}, content_length={len(content)}")
                                
                                # 生成JSON并立即输出
                                chunk_json = json.dumps(token_data, ensure_ascii=False)
                                sse_line = f"data: {chunk_json}\n\n"
                                yield sse_line
                                
                                # 立即刷新
                                sys.stdout.flush()
                                if hasattr(sys.stdout, 'buffer'):
                                    sys.stdout.buffer.flush()
                        
                        elif msg_type in [StreamMessageType.NODE_START, StreamMessageType.NODE_COMPLETE, StreamMessageType.NODE_ERROR]:
                            # 节点状态消息
                            node_data = {
                                "type": "data",
                                "content": {
                                    "type": msg_type,
                                    "node_name": chunk.get("node_name", "unknown"),
                                    "status": chunk.get("status", "unknown"),
                                    "details": chunk.get("details", ""),
                                    "source": source,
                                    "timestamp": chunk.get("timestamp", time.time())
                                },
                                "session_id": session_id,
                                "chunk_id": chunk_count,
                                "timestamp": time.time()
                            }
                            
                            logger.debug(f"🔧 发送节点状态: type={msg_type}, node={chunk.get('node_name', 'unknown')}")
                            
                            chunk_json = json.dumps(node_data, ensure_ascii=False)
                            sse_line = f"data: {chunk_json}\n\n"
                            yield sse_line
                            
                            sys.stdout.flush()
                            if hasattr(sys.stdout, 'buffer'):
                                sys.stdout.buffer.flush()
                        
                        elif msg_type == StreamMessageType.AGENT_THINKING:
                            # Agent 思考过程
                            thinking_data = {
                                "type": "data",
                                "content": {
                                    "type": msg_type,
                                    "agent_name": chunk.get("agent_name", "unknown"),
                                    "thinking_type": chunk.get("thinking_type", "analysis"),
                                    "content": content,
                                    "source": source,
                                    "timestamp": chunk.get("timestamp", time.time())
                                },
                                "session_id": session_id,
                                "chunk_id": chunk_count,
                                "timestamp": time.time()
                            }
                            
                            logger.debug(f"🤔 发送Agent思考: agent={chunk.get('agent_name', 'unknown')}, type={chunk.get('thinking_type', 'analysis')}")
                            
                            chunk_json = json.dumps(thinking_data, ensure_ascii=False)
                            sse_line = f"data: {chunk_json}\n\n"
                            yield sse_line
                            
                            sys.stdout.flush()
                            if hasattr(sys.stdout, 'buffer'):
                                sys.stdout.buffer.flush()
                        
                        elif msg_type in [StreamMessageType.TOOL_START, StreamMessageType.TOOL_PROGRESS, 
                                         StreamMessageType.TOOL_COMPLETE, StreamMessageType.TOOL_ERROR]:
                            # 工具执行相关消息
                            tool_data = {
                                "type": "data",
                                "content": {
                                    "type": msg_type,
                                    "tool_name": chunk.get("tool_name", "unknown"),
                                    "action": chunk.get("action", "unknown"),
                                    "progress": chunk.get("progress"),
                                    "output": chunk.get("output", ""),
                                    "error_message": chunk.get("error_message", ""),
                                    "source": source,
                                    "timestamp": chunk.get("timestamp", time.time())
                                },
                                "session_id": session_id,
                                "chunk_id": chunk_count,
                                "timestamp": time.time()
                            }
                            
                            logger.debug(f"🔧 发送工具消息: type={msg_type}, tool={chunk.get('tool_name', 'unknown')}")
                            
                            chunk_json = json.dumps(tool_data, ensure_ascii=False)
                            sse_line = f"data: {chunk_json}\n\n"
                            yield sse_line
                            
                            sys.stdout.flush()
                            if hasattr(sys.stdout, 'buffer'):
                                sys.stdout.buffer.flush()
                        
                        elif msg_type in [StreamMessageType.FILE_GENERATED, StreamMessageType.FILE_UPLOADED]:
                            # 文件相关消息
                            file_data = {
                                "type": "data",
                                "content": {
                                    "type": msg_type,
                                    "file_id": chunk.get("file_id", ""),
                                    "file_name": chunk.get("file_name", "unknown"),
                                    "file_type": chunk.get("file_type", "unknown"),
                                    "file_path": chunk.get("file_path", ""),
                                    "file_size": chunk.get("file_size"),
                                    "source": source,
                                    "timestamp": chunk.get("timestamp", time.time())
                                },
                                "session_id": session_id,
                                "chunk_id": chunk_count,
                                "timestamp": time.time()
                            }
                            
                            logger.debug(f"📁 发送文件消息: type={msg_type}, file={chunk.get('file_name', 'unknown')}")
                            
                            chunk_json = json.dumps(file_data, ensure_ascii=False)
                            sse_line = f"data: {chunk_json}\n\n"
                            yield sse_line
                            
                            sys.stdout.flush()
                            if hasattr(sys.stdout, 'buffer'):
                                sys.stdout.buffer.flush()
                        
                        elif msg_type in [StreamMessageType.ROUTE_DECISION, StreamMessageType.ROUTE_CHANGE]:
                            # 路由决策消息
                            route_data = {
                                "type": "data",
                                "content": {
                                    "type": msg_type,
                                    "from_node": chunk.get("from_node", ""),
                                    "to_node": chunk.get("to_node", ""),
                                    "reason": chunk.get("reason", ""),
                                    "source": source,
                                    "timestamp": chunk.get("timestamp", time.time())
                                },
                                "session_id": session_id,
                                "chunk_id": chunk_count,
                                "timestamp": time.time()
                            }
                            
                            logger.debug(f"🛣️ 发送路由消息: type={msg_type}, from={chunk.get('from_node', '')} to={chunk.get('to_node', '')}")
                            
                            chunk_json = json.dumps(route_data, ensure_ascii=False)
                            sse_line = f"data: {chunk_json}\n\n"
                            yield sse_line
                            
                            sys.stdout.flush()
                            if hasattr(sys.stdout, 'buffer'):
                                sys.stdout.buffer.flush()
                        
                        elif msg_type in [StreamMessageType.ERROR, StreamMessageType.INFO, StreamMessageType.DEBUG]:
                            # 系统消息
                            system_data = {
                                "type": "data",
                                "content": {
                                    "type": msg_type,
                                    "message": content,
                                    "error_code": chunk.get("error_code", ""),
                                    "level": chunk.get("level", "info"),
                                    "source": source,
                                    "timestamp": chunk.get("timestamp", time.time())
                                },
                                "session_id": session_id,
                                "chunk_id": chunk_count,
                                "timestamp": time.time()
                            }
                            
                            logger.debug(f"ℹ️ 发送系统消息: type={msg_type}, level={chunk.get('level', 'info')}")
                            
                            chunk_json = json.dumps(system_data, ensure_ascii=False)
                            sse_line = f"data: {chunk_json}\n\n"
                            yield sse_line
                            
                            sys.stdout.flush()
                            if hasattr(sys.stdout, 'buffer'):
                                sys.stdout.buffer.flush()
                        
                        else:
                            # 未知类型或兼容性处理
                            # 检查是否是旧格式的assistant消息
                            if role == "assistant" and content:
                                # 作为token流处理
                                token_data = {
                                    "type": "token",
                                    "content": content,
                                    "session_id": session_id,
                                    "chunk_id": chunk_count,
                                    "timestamp": time.time(),
                                    "source": source
                                }
                                
                                logger.debug(f"📝 发送兼容性Token: source={source}, content_length={len(content)}")
                                
                                chunk_json = json.dumps(token_data, ensure_ascii=False)
                                sse_line = f"data: {chunk_json}\n\n"
                                yield sse_line
                                
                                sys.stdout.flush()
                                if hasattr(sys.stdout, 'buffer'):
                                    sys.stdout.buffer.flush()
                            else:
                                # 其他未知消息类型，发送完整数据
                                unknown_data = {
                                    "type": "data",
                                    "content": chunk,
                                    "session_id": session_id,
                                    "chunk_id": chunk_count,
                                    "timestamp": time.time()
                                }
                                
                                logger.debug(f"❓ 发送未知消息: type={msg_type}, role={role}")
                                
                                chunk_json = json.dumps(unknown_data, ensure_ascii=False)
                                sse_line = f"data: {chunk_json}\n\n"
                                yield sse_line
                                
                                sys.stdout.flush()
                                if hasattr(sys.stdout, 'buffer'):
                                    sys.stdout.buffer.flush()
                
                # 发送结束标记
                end_data = json.dumps({
                    'type': 'end', 
                    'session_id': session_id, 
                    'total_chunks': chunk_count,
                    'timestamp': time.time()
                }, ensure_ascii=False)
                yield f"data: {end_data}\n\n"
                
                # 最终刷新
                sys.stdout.flush()
                if hasattr(sys.stdout, 'buffer'):
                    sys.stdout.buffer.flush()
                
            except Exception as e:
                logger.error(f"流式处理错误: {str(e)}")
                error_data = {
                    "type": "error",
                    "error": str(e),
                    "session_id": session_id,
                    "timestamp": time.time()
                }
                error_json = json.dumps(error_data, ensure_ascii=False)
                yield f"data: {error_json}\n\n"
                
                sys.stdout.flush()
                if hasattr(sys.stdout, 'buffer'):
                    sys.stdout.buffer.flush()
        
        # 返回SSE流响应 - 添加所有可能的无缓冲headers
        return StreamingResponse(
            sync_stream_generator(),
            media_type="text/event-stream",
            headers={
                # 基本的无缓冲设置
                "Cache-Control": "no-cache, no-store, must-revalidate, private",
                "Pragma": "no-cache",
                "Expires": "0",
                "Connection": "keep-alive",
                
                # CORS设置
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                
                # 关键的服务器无缓冲设置
                "X-Accel-Buffering": "no",        # 禁用nginx缓冲
                "X-Proxy-Buffering": "no",        # 禁用代理缓冲
                "Content-Encoding": "identity",   # 禁用gzip压缩缓冲
                
                # 额外的HTTP/1.1无缓冲设置
                "Transfer-Encoding": "chunked",   # 使用分块传输
                "X-Content-Type-Options": "nosniff",
                
                # 确保浏览器不缓冲
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Last-Modified": datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT"),
                "ETag": f'"{int(time.time())}"'
            }
        )
        
    except Exception as e:
        logger.error(f"流式发送消息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"流式处理失败: {str(e)}")

def _get_message_role(msg) -> str:
    """从消息对象中提取角色信息"""
    # 处理字典格式的消息
    if isinstance(msg, dict):
        # 优先使用role字段（对话轮次管理器设置的正确角色）
        if 'role' in msg:
            role = msg['role']
            # 已经是标准角色名称，直接返回
            if role in ['user', 'assistant', 'system', 'tool']:
                return role
        
        # 回退到type字段（兼容性处理）
        msg_type = msg.get('type', 'unknown')
        # 标准化角色名称，确保与AI SDK兼容
        if msg_type == 'human':
            return 'user'
        elif msg_type == 'ai':
            return 'assistant'
        elif msg_type == 'system':
            return 'system'
        elif msg_type == 'tool':
            return 'tool'
        else:
            return msg_type
    
    # 处理LangChain消息对象
    elif hasattr(msg, 'type'):
        msg_type = msg.type
        # 标准化角色名称，确保与AI SDK兼容
        if msg_type == 'human':
            return 'user'
        elif msg_type == 'ai':
            return 'assistant'
        elif msg_type == 'system':
            return 'system'
        elif msg_type == 'tool':
            return 'tool'
        else:
            return msg_type
    else:
        return 'unknown'

def _get_message_content(msg) -> str:
    """从消息对象中提取内容，确保不截断长消息"""
    if hasattr(msg, 'content'):
        content = msg.content
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            # 处理多模态内容
            text_parts = []
            for part in content:
                if isinstance(part, dict):
                    if part.get('type') == 'text':
                        text_parts.append(part.get('text', ''))
                    elif part.get('type') == 'image_url':
                        text_parts.append(f"[图片: {part.get('image_url', {}).get('url', 'unknown')}]")
                elif isinstance(part, str):
                    text_parts.append(part)
            return '\n'.join(text_parts)
        else:
            return str(content)
    elif isinstance(msg, dict):
        content = msg.get('content', '')
        if isinstance(content, str):
            return content
        else:
            return str(content)
    return ""

@router.get("/{session_id}/history", response_model=APIResponse)
async def get_chat_history(
    session_id: str,
    limit: Optional[int] = 50,
    engine: IsotopeEngine = Depends(get_engine)
):
    """获取聊天历史
    
    Args:
        session_id: 会话ID
        limit: 返回消息数量限制
        engine: 引擎实例
        
    Returns:
        聊天历史
    """
    try:
        logger.info(f"获取会话历史: {session_id}")
        
        # 首先检查会话是否存在
        session = engine.get_session_by_id(session_id)
        if not session:
            logger.warning(f"会话不存在: {session_id}")
            return APIResponse(
                success=True,
                message="会话不存在",
                data={"messages": [], "session_id": session_id}
            )
        
        # 获取会话历史
        history = engine.get_session_history(session_id)
        logger.info(f"从引擎获取到 {len(history) if history else 0} 条原始消息")
        
        if not history:
            logger.info("会话历史为空")
            return APIResponse(
                success=True,
                message="会话历史为空",
                data={"messages": [], "session_id": session_id}
            )
        
        # 转换消息格式为API标准格式
        api_messages = []
        for i, msg in enumerate(history):
            try:
                logger.debug(f"处理消息 {i+1}: 类型={type(msg)}, 内容={str(msg)[:100]}...")
                
                if isinstance(msg, dict):
                    # 字典格式的消息
                    content = _get_message_content(msg)
                    role = _get_message_role(msg)
                    
                    api_msg = {
                        "id": msg.get("id", str(uuid.uuid4())),
                        "role": role,
                        "content": content,
                        "timestamp": msg.get("timestamp", datetime.now().isoformat()),
                        "type": msg.get("message_type", "text"),
                        "metadata": msg.get("metadata", {})
                    }
                    
                    logger.debug(f"转换字典消息: role={role}, content_length={len(content)}")
                else:
                    # 其他格式的消息（可能是LangChain消息对象）
                    content = _get_message_content(msg)
                    role = _get_message_role(msg)
                    
                    api_msg = {
                        "id": getattr(msg, "id", str(uuid.uuid4())),
                        "role": role,
                        "content": content,
                        "timestamp": getattr(msg, "timestamp", datetime.now().isoformat()),
                        "type": "text",
                        "metadata": {}
                    }
                    
                    logger.debug(f"转换对象消息: role={role}, content_length={len(content)}")
                
                # 只添加有内容的消息
                if content and content.strip():
                    api_messages.append(api_msg)
                    logger.debug(f"消息 {i+1} 已添加到API结果")
                else:
                    logger.warning(f"消息 {i+1} 内容为空，跳过")
                    
            except Exception as msg_error:
                logger.error(f"处理消息 {i+1} 时出错: {str(msg_error)}")
                continue
        
        logger.info(f"成功转换 {len(api_messages)} 条消息")
        
        # 应用分页限制
        if limit and len(api_messages) > limit:
            api_messages = api_messages[-limit:]
            logger.info(f"应用分页限制，返回最后 {len(api_messages)} 条消息")
        
        return APIResponse(
            success=True,
            message=f"获取到{len(api_messages)}条消息",
            data={"messages": api_messages, "session_id": session_id}
        )
        
    except Exception as e:
        logger.error(f"获取会话历史失败: {str(e)}")
        import traceback
        logger.error(f"完整错误栈: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取会话历史失败: {str(e)}")

@router.post("/{session_id}/interrupt", response_model=APIResponse)
async def interrupt_session(
    session_id: str,
    engine: IsotopeEngine = Depends(get_engine)
):
    """中断会话处理
    
    Args:
        session_id: 会话ID
        engine: 引擎实例
        
    Returns:
        中断结果
    """
    try:
        # 检查会话是否存在
        session = engine.get_session_by_id(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        # 这里可以实现中断逻辑
        # 目前LangGraph的中断机制主要通过workflow本身实现
        logger.info(f"收到会话中断请求: {session_id}")
        
        return APIResponse(
            success=True,
            message="中断请求已发送",
            data={"session_id": session_id, "status": "interrupted"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"中断会话失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"中断会话失败: {str(e)}")

@router.post("/{session_id}/resume", response_model=APIResponse)
async def resume_session(
    session_id: str,
    request: Dict[str, Any],
    engine: IsotopeEngine = Depends(get_engine)
):
    """恢复会话处理
    
    Args:
        session_id: 会话ID
        request: 恢复请求（包含用户输入等）
        engine: 引擎实例
        
    Returns:
        恢复结果
    """
    try:
        # 检查会话是否存在
        session = engine.get_session_by_id(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        user_input = request.get("user_input", "")
        if not user_input:
            raise HTTPException(status_code=400, detail="需要提供用户输入")
        
        # 恢复工作流
        result_state = engine.resume_workflow(
            user_input=user_input,
            session_id=session_id,
            stream=False
        )
        
        return APIResponse(
            success=True,
            message="会话已恢复处理",
            data={
                "session_id": session_id,
                "status": "resumed",
                "message_count": len(result_state.get("messages", []))
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"恢复会话失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"恢复会话失败: {str(e)}")

@router.get("/{session_id}/status", response_model=APIResponse)
async def get_session_status(
    session_id: str,
    engine: IsotopeEngine = Depends(get_engine)
):
    """获取会话状态
    
    Args:
        session_id: 会话ID
        engine: 引擎实例
        
    Returns:
        会话状态信息
    """
    try:
        # 获取会话状态
        state = engine.get_session_state(session_id)
        if not state:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        session_info = engine.get_session_by_id(session_id)
        
        status_data = {
            "session_id": session_id,
            "status": "active",
            "message_count": len(state.get("messages", [])),
            "files_count": len(state.get("files", {})),
            "created_at": session_info.get("created_at"),
            "last_updated": session_info.get("last_updated"),
            "current_task": state.get("current_task")
        }
        
        return APIResponse(
            success=True,
            message="会话状态获取成功",
            data=status_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取会话状态失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取会话状态失败: {str(e)}")