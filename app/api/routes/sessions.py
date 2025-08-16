"""
会话管理API路由 - 处理会话相关的HTTP请求

功能包括：
1. 创建和删除会话
2. 获取会话列表
3. 会话状态管理
4. 会话数据导出导入
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query

from app.core.engine import IsotopeEngine
from app.api.dependencies import get_engine
from app.api.models import (
    CreateSessionRequest,
    SessionInfo,
    SessionStatus,
    SessionListResponse,
    APIResponse,
    ErrorResponse
)
from app.core.postgres_session_manager import get_postgres_session_manager

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/create", response_model=APIResponse)
async def create_session(
    request: CreateSessionRequest,
    engine: IsotopeEngine = Depends(get_engine)
):
    """创建新会话
    
    Args:
        request: 创建会话请求
        engine: 引擎实例
        
    Returns:
        新会话信息
    """
    try:
        # 准备会话元数据
        session_metadata = request.metadata or {}
        logger.info(f"初始metadata: {session_metadata}")
        
        # 添加用户输入的名称和描述到元数据
        if request.session_name:
            session_metadata["name"] = request.session_name
            logger.info(f"添加会话名称: {request.session_name}")
        else:
            session_metadata["name"] = "未命名会话"
            
        if request.session_description:
            session_metadata["description"] = request.session_description
            logger.info(f"添加会话描述: {request.session_description}")
        
        logger.info(f"最终传递给引擎的metadata: {session_metadata}")
        
        # 创建新会话，传递元数据
        session_id = engine.create_session(metadata=session_metadata)
        
        # 如果有初始消息，处理它
        if request.initial_message:
            try:
                engine.resume_workflow(
                    user_input=request.initial_message,
                    session_id=session_id,
                    stream=False
                )
            except Exception as e:
                logger.warning(f"处理初始消息失败: {str(e)}")
        
        # 获取会话信息
        session = engine.get_session_by_id(session_id)
        session_state = engine.get_session_state(session_id)
        
        # 获取元数据
        session_level_metadata = session.get("metadata", {}) if session else {}
        state_metadata = session_state.get("metadata", {}) if session_state else {}
        
        # 正确合并元数据：会话级别元数据优先（包含用户输入的name和description）
        merged_metadata = {**state_metadata, **session_level_metadata}
        
        # 确保name和description字段存在
        if "name" not in merged_metadata and request.session_name:
            merged_metadata["name"] = request.session_name
        if "description" not in merged_metadata and request.session_description:
            merged_metadata["description"] = request.session_description
        
        session_info = {
            "session_id": session_id,
            "status": "active",
            "created_at": session.get("created_at") if session else datetime.now().isoformat(),
            "last_updated": session.get("last_updated") if session else datetime.now().isoformat(),
            "message_count": len(session_state.get("messages", [])) if session_state else 0,
            "metadata": merged_metadata
        }
        
        return APIResponse(
            success=True,
            message="会话创建成功",
            data=session_info
        )
        
    except Exception as e:
        logger.error(f"创建会话失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建会话失败: {str(e)}")

@router.get("/list", response_model=SessionListResponse)
async def list_sessions(
    limit: Optional[int] = 50,
    offset: Optional[int] = 0,
    engine: IsotopeEngine = Depends(get_engine),
    include_metadata: bool = Query(default=True, description="是否包含会话元数据")
):
    """获取会话列表
    
    Args:
        limit: 返回数量限制
        offset: 偏移量
        engine: 引擎实例
        include_metadata: 是否包含会话元数据
        
    Returns:
        会话列表
    """
    try:
        # 获取所有会话
        all_sessions = []
        
        # 安全地解析时间字符串，处理时区问题
        def safe_parse_datetime(dt_str, default_dt=None, session_id=None):
            if not dt_str:
                return default_dt or datetime.now()
            try:
                # 如果是datetime对象，直接处理
                if isinstance(dt_str, datetime):
                    # 如果是带时区的时间，转换为本地时间（去掉时区信息）
                    if dt_str.tzinfo is not None:
                        dt_str = dt_str.replace(tzinfo=None)
                    return dt_str
                
                # 如果是字符串，解析ISO格式时间
                dt = datetime.fromisoformat(str(dt_str).replace('Z', '+00:00'))
                # 如果是带时区的时间，转换为本地时间（去掉时区信息）
                if dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)
                return dt
            except (ValueError, AttributeError) as e:
                logger.warning(f"解析时间失败 (会话 {session_id}): {dt_str}, 错误: {e}")
                # 如果解析失败，返回默认时间
                return default_dt or datetime.now()
        
        for session_id, session_data in engine.sessions.items():
            try:
                state = session_data.get("state", {})
                
                # 合并会话级别的元数据和状态中的元数据
                session_metadata = session_data.get("metadata", {})
                state_metadata = state.get("metadata", {})
                merged_metadata = {**state_metadata, **session_metadata}
                
                created_at = safe_parse_datetime(session_data.get("created_at"), session_id=session_id)
                last_updated = safe_parse_datetime(session_data.get("last_updated"), session_id=session_id)
                
                session_info = SessionInfo(
                    session_id=session_id,
                    status=SessionStatus.ACTIVE,
                    created_at=created_at,
                    last_updated=last_updated,
                    message_count=len(state.get("messages", [])),
                    metadata=merged_metadata  # 使用合并后的元数据
                )
                
                if include_metadata:
                    session_info.metadata = merged_metadata
                
                all_sessions.append(session_info)
            except Exception as e:
                logger.error(f"处理会话 {session_id} 时出错: {str(e)}")
                continue
        
        # 按最后更新时间排序
        all_sessions.sort(key=lambda x: x.last_updated, reverse=True)
        
        # 应用分页
        if offset:
            all_sessions = all_sessions[offset:]
        if limit:
            all_sessions = all_sessions[:limit]
        
        return SessionListResponse(
            success=True,
            message=f"获取到{len(all_sessions)}个会话",
            data={"total": len(engine.sessions)},
            sessions=all_sessions
        )
        
    except Exception as e:
        logger.error(f"获取会话列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取会话列表失败: {str(e)}")

@router.get("/{session_id}", response_model=APIResponse)
async def get_session(
    session_id: str,
    engine: IsotopeEngine = Depends(get_engine),
    include_messages: bool = Query(default=False, description="是否包含消息历史")
):
    """获取特定会话信息
    
    Args:
        session_id: 会话ID
        engine: 引擎实例
        include_messages: 是否包含消息历史
        
    Returns:
        会话详细信息
    """
    try:
        # 检查会话是否存在
        session = engine.get_session_by_id(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        state = engine.get_session_state(session_id)
        
        session_detail = {
            "session_id": session_id,
            "status": "active",
            "created_at": session.get("created_at"),
            "last_updated": session.get("last_updated"),
            "message_count": len(state.get("messages", [])) if state else 0,
            "files_count": len(state.get("files", {})) if state else 0,
            "current_task": state.get("current_task") if state else None,
            "metadata": state.get("metadata", {}) if state else {}
        }
        
        if include_messages:
            messages = state.get("messages", [])
            # 转换消息为可序列化格式
            serializable_messages = []
            for msg in messages:
                if hasattr(msg, 'type') and hasattr(msg, 'content'):
                    serializable_messages.append({
                        "type": msg.type,
                        "content": msg.content,
                        "timestamp": getattr(msg, 'timestamp', None)
                    })
                else:
                    serializable_messages.append(str(msg))
            
            session_detail["messages"] = serializable_messages
        
        return APIResponse(
            success=True,
            message="会话信息获取成功",
            data=session_detail
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取会话信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取会话信息失败: {str(e)}")

@router.delete("/{session_id}", response_model=APIResponse)
async def delete_session(
    session_id: str,
    engine: IsotopeEngine = Depends(get_engine),
    soft_delete: bool = Query(default=True, description="是否软删除")
):
    """删除会话
    
    Args:
        session_id: 会话ID
        engine: 引擎实例
        soft_delete: 是否软删除
        
    Returns:
        删除结果
    """
    try:
        # 检查会话是否存在
        if not engine.get_session_by_id(session_id):
            raise HTTPException(status_code=404, detail="会话不存在")
        
        # 删除会话
        success = engine.delete_session(session_id)
        
        if success:
            return APIResponse(
                success=True,
                message="会话删除成功",
                data={"session_id": session_id}
            )
        else:
            raise HTTPException(status_code=500, detail="删除会话失败")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除会话失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除会话失败: {str(e)}")

@router.post("/{session_id}/reset", response_model=APIResponse)
async def reset_session(
    session_id: str,
    engine: IsotopeEngine = Depends(get_engine)
):
    """重置会话
    
    Args:
        session_id: 会话ID
        engine: 引擎实例
        
    Returns:
        重置结果
    """
    try:
        # 检查会话是否存在
        if not engine.get_session_by_id(session_id):
            raise HTTPException(status_code=404, detail="会话不存在")
        
        # 重置会话
        success = engine.reset_session(session_id)
        
        if success:
            return APIResponse(
                success=True,
                message="会话重置成功",
                data={"session_id": session_id}
            )
        else:
            raise HTTPException(status_code=500, detail="重置会话失败")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重置会话失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"重置会话失败: {str(e)}")

@router.get("/{session_id}/export", response_model=APIResponse)
async def export_session(
    session_id: str,
    format: str = "json",
    engine: IsotopeEngine = Depends(get_engine)
):
    """导出会话数据
    
    Args:
        session_id: 会话ID
        format: 导出格式（json, csv等）
        engine: 引擎实例
        
    Returns:
        导出的会话数据
    """
    try:
        # 检查会话是否存在
        state = engine.get_session_state(session_id)
        if not state:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        session = engine.get_session_by_id(session_id)
        
        if format.lower() == "json":
            # JSON格式导出
            export_data = {
                "session_id": session_id,
                "created_at": session.get("created_at"),
                "last_updated": session.get("last_updated"),
                "messages": engine.get_session_history(session_id),
                "files": list(state.get("files", {}).values()),
                "metadata": state.get("metadata", {})
            }
            
            return APIResponse(
                success=True,
                message="会话数据导出成功",
                data={
                    "format": "json",
                    "session_data": export_data
                }
            )
        else:
            raise HTTPException(status_code=400, detail=f"不支持的导出格式: {format}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导出会话数据失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"导出会话数据失败: {str(e)}")

@router.post("/import", response_model=APIResponse)
async def import_session(
    session_data: Dict[str, Any],
    engine: IsotopeEngine = Depends(get_engine)
):
    """导入会话数据
    
    Args:
        session_data: 会话数据
        engine: 引擎实例
        
    Returns:
        导入结果
    """
    try:
        # 检查数据格式
        if "session_id" not in session_data:
            raise HTTPException(status_code=400, detail="缺少session_id字段")
        
        session_id = session_data["session_id"]
        
        # 检查会话是否已存在
        if engine.get_session_by_id(session_id):
            raise HTTPException(status_code=409, detail="会话已存在")
        
        # 创建新会话
        engine.create_session(session_id)
        
        # 这里可以实现具体的数据导入逻辑
        # 例如恢复消息、文件等
        
        return APIResponse(
            success=True,
            message="会话数据导入成功",
            data={"session_id": session_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导入会话数据失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"导入会话数据失败: {str(e)}")

@router.get("/{session_id}/summary", response_model=APIResponse)
async def get_session_summary(
    session_id: str,
    engine: IsotopeEngine = Depends(get_engine)
):
    """获取会话摘要
    
    Args:
        session_id: 会话ID
        engine: 引擎实例
        
    Returns:
        会话摘要
    """
    try:
        # 检查会话是否存在
        if not engine.get_session_by_id(session_id):
            raise HTTPException(status_code=404, detail="会话不存在")
        
        # 生成会话摘要
        summary = engine.summarize_history(session_id)
        
        if summary:
            return APIResponse(
                success=True,
                message="会话摘要生成成功",
                data={
                    "session_id": session_id,
                    "summary": summary
                }
            )
        else:
            return APIResponse(
                success=True,
                message="会话内容不足，无法生成摘要",
                data={
                    "session_id": session_id,
                    "summary": None
                }
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成会话摘要失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"生成会话摘要失败: {str(e)}")

@router.get("/sessions", response_model=List[Dict[str, Any]])
async def list_sessions(
    engine: IsotopeEngine = Depends(get_engine),
    include_metadata: bool = Query(default=True, description="是否包含会话元数据")
):
    """获取所有会话列表"""
    try:
        sessions = []
        for session_id, session_data in engine.sessions.items():
            session_info = {
                "session_id": session_id,
                "created_at": session_data.get("created_at"),
                "last_updated": session_data.get("last_updated"),
                "message_count": len(session_data.get("state", {}).get("messages", []))
            }
            
            if include_metadata:
                session_info["metadata"] = session_data.get("metadata", {})
            
            sessions.append(session_info)
        
        return sessions
    except Exception as e:
        logger.error(f"获取会话列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取会话列表失败: {str(e)}")

@router.get("/sessions/{session_id}", response_model=Dict[str, Any])
async def get_session(
    session_id: str,
    engine: IsotopeEngine = Depends(get_engine),
    include_messages: bool = Query(default=False, description="是否包含消息历史")
):
    """获取特定会话信息"""
    try:
        session = engine.sessions.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在")
        
        session_info = {
            "session_id": session_id,
            "created_at": session.get("created_at"),
            "last_updated": session.get("last_updated"),
            "metadata": session.get("metadata", {}),
            "message_count": len(session.get("state", {}).get("messages", []))
        }
        
        if include_messages:
            messages = session.get("state", {}).get("messages", [])
            # 转换消息为可序列化格式
            serializable_messages = []
            for msg in messages:
                if hasattr(msg, 'type') and hasattr(msg, 'content'):
                    serializable_messages.append({
                        "type": msg.type,
                        "content": msg.content,
                        "timestamp": getattr(msg, 'timestamp', None)
                    })
                else:
                    serializable_messages.append(str(msg))
            
            session_info["messages"] = serializable_messages
        
        return session_info
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取会话信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取会话信息失败: {str(e)}")

@router.post("/sessions", response_model=Dict[str, str])
async def create_session(
    session_data: Dict[str, Any],
    engine: IsotopeEngine = Depends(get_engine)
):
    """创建新会话"""
    try:
        session_id = session_data.get("session_id")
        metadata = session_data.get("metadata", {})
        
        new_session_id = engine.create_session(session_id, metadata)
        
        return {
            "session_id": new_session_id,
            "message": "会话创建成功"
        }
    except Exception as e:
        logger.error(f"创建会话失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建会话失败: {str(e)}")

@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    engine: IsotopeEngine = Depends(get_engine),
    soft_delete: bool = Query(default=True, description="是否软删除")
):
    """删除会话"""
    try:
        # 从内存中删除
        if session_id in engine.sessions:
            del engine.sessions[session_id]
            logger.info(f"会话 {session_id} 已从内存中删除")
        
        # 如果启用了PostgreSQL会话持久化，也从数据库中删除
        if engine.session_persistence_enabled and engine.postgres_session_manager:
            success = engine.postgres_session_manager.delete_session(session_id, soft_delete)
            if success:
                logger.info(f"会话 {session_id} 已从PostgreSQL中删除")
            else:
                logger.warning(f"从PostgreSQL删除会话 {session_id} 失败")
        
        return {"message": f"会话 {session_id} 删除成功"}
    except Exception as e:
        logger.error(f"删除会话失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除会话失败: {str(e)}")

# PostgreSQL会话管理端点
@router.get("/postgres/sessions", response_model=List[Dict[str, Any]])
async def list_postgres_sessions(
    limit: int = Query(default=50, description="返回数量限制"),
    offset: int = Query(default=0, description="偏移量"),
    include_inactive: bool = Query(default=False, description="是否包含非活跃会话")
):
    """获取PostgreSQL中的会话列表"""
    try:
        postgres_manager = get_postgres_session_manager()
        sessions = postgres_manager.list_sessions(
            limit=limit,
            offset=offset,
            include_inactive=include_inactive
        )
        return sessions
    except Exception as e:
        logger.error(f"获取PostgreSQL会话列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取PostgreSQL会话列表失败: {str(e)}")

@router.get("/postgres/sessions/{session_id}", response_model=Dict[str, Any])
async def get_postgres_session(session_id: str):
    """获取PostgreSQL中的特定会话"""
    try:
        postgres_manager = get_postgres_session_manager()
        session_data = postgres_manager.load_session(session_id)
        
        if not session_data:
            raise HTTPException(status_code=404, detail=f"PostgreSQL中不存在会话 {session_id}")
        
        return session_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取PostgreSQL会话失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取PostgreSQL会话失败: {str(e)}")

@router.get("/postgres/statistics", response_model=Dict[str, Any])
async def get_postgres_session_statistics():
    """获取PostgreSQL会话统计信息"""
    try:
        postgres_manager = get_postgres_session_manager()
        stats = postgres_manager.get_session_statistics()
        return stats
    except Exception as e:
        logger.error(f"获取PostgreSQL会话统计信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取PostgreSQL会话统计信息失败: {str(e)}")

@router.post("/postgres/restore", response_model=Dict[str, Any])
async def restore_postgres_sessions(
    engine: IsotopeEngine = Depends(get_engine)
):
    """从PostgreSQL恢复所有会话到内存"""
    try:
        if not engine.session_persistence_enabled or not engine.postgres_session_manager:
            raise HTTPException(
                status_code=400, 
                detail="PostgreSQL会话持久化未启用"
            )
        
        # 恢复会话
        restore_result = engine.postgres_session_manager.restore_all_sessions()
        
        if restore_result.get("success", False):
            # 将恢复的会话加载到引擎内存中
            postgres_sessions = restore_result.get("sessions", {})
            restored_count = 0
            
            for session_id, session_data in postgres_sessions.items():
                try:
                    engine.sessions[session_id] = {
                        "state": session_data["state"],
                        "created_at": session_data["created_at"],
                        "last_updated": session_data["last_updated"],
                        "metadata": session_data["metadata"]
                    }
                    restored_count += 1
                except Exception as e:
                    logger.error(f"恢复会话 {session_id} 到内存失败: {str(e)}")
            
            return {
                "success": True,
                "restored_count": restored_count,
                "total_found": restore_result.get("total_found", 0),
                "failed_count": restore_result.get("failed_count", 0),
                "message": f"成功恢复 {restored_count} 个会话到内存"
            }
        else:
            return {
                "success": False,
                "error": restore_result.get("error", "未知错误"),
                "message": "PostgreSQL会话恢复失败"
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"恢复PostgreSQL会话失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"恢复PostgreSQL会话失败: {str(e)}")

@router.post("/postgres/cleanup", response_model=Dict[str, Any])
async def cleanup_expired_sessions():
    """清理过期的PostgreSQL会话"""
    try:
        postgres_manager = get_postgres_session_manager()
        cleaned_count = postgres_manager.cleanup_expired_sessions()
        
        return {
            "success": True,
            "cleaned_count": cleaned_count,
            "message": f"成功清理 {cleaned_count} 个过期会话"
        }
    except Exception as e:
        logger.error(f"清理过期会话失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"清理过期会话失败: {str(e)}")

@router.get("/postgres/connection/test", response_model=Dict[str, Any])
async def test_postgres_connection():
    """测试PostgreSQL连接"""
    try:
        postgres_manager = get_postgres_session_manager()
        is_connected = postgres_manager.test_connection()
        
        return {
            "connected": is_connected,
            "message": "PostgreSQL连接正常" if is_connected else "PostgreSQL连接失败"
        }
    except Exception as e:
        logger.error(f"测试PostgreSQL连接失败: {str(e)}")
        return {
            "connected": False,
            "error": str(e),
            "message": "PostgreSQL连接测试失败"
        }

# 兼容性端点（保持向后兼容）
@router.get("/restored", response_model=Dict[str, Any])
async def get_restored_sessions_info(engine: IsotopeEngine = Depends(get_engine)):
    """获取已恢复会话的统计信息（兼容性端点）"""
    try:
        # 如果启用了PostgreSQL会话持久化，返回PostgreSQL统计信息
        if engine.session_persistence_enabled and engine.postgres_session_manager:
            stats = engine.postgres_session_manager.get_session_statistics()
            return {
                "source": "postgresql",
                "statistics": stats,
                "current_memory_sessions": len(engine.sessions)
            }
        else:
            # 否则返回内存会话统计
            return {
                "source": "memory",
                "total_sessions": len(engine.sessions),
                "current_memory_sessions": len(engine.sessions),
                "sessions": [
                    {
                        "session_id": session_id,
                        "created_at": session_data.get("created_at"),
                        "last_updated": session_data.get("last_updated"),
                        "message_count": len(session_data.get("state", {}).get("messages", []))
                    }
                    for session_id, session_data in engine.sessions.items()
                ]
            }
    except Exception as e:
        logger.error(f"获取恢复会话信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取恢复会话信息失败: {str(e)}")

@router.post("/restore", response_model=Dict[str, Any])
async def restore_sessions(engine: IsotopeEngine = Depends(get_engine)):
    """手动触发会话恢复（兼容性端点）"""
    try:
        # 调用引擎的会话恢复方法
        engine._restore_existing_sessions()
        
        return {
            "success": True,
            "message": "会话恢复完成",
            "current_sessions": len(engine.sessions)
        }
    except Exception as e:
        logger.error(f"手动恢复会话失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"手动恢复会话失败: {str(e)}") 