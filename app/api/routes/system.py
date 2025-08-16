"""
系统管理API路由 - 处理系统管理相关的HTTP请求

功能包括：
1. 系统状态监控
2. 配置信息获取
3. 日志管理
4. 性能指标
5. 系统维护操作
"""

import logging
import os
import psutil
import platform
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends

from app.core.engine import IsotopeEngine
from app.api.dependencies import get_engine
from app.api.models import (
    SystemStatus,
    SystemStatusResponse,
    APIResponse,
    ErrorResponse
)

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status(
    engine: IsotopeEngine = Depends(get_engine)
):
    """获取系统状态
    
    Args:
        engine: 引擎实例
        
    Returns:
        系统状态信息
    """
    try:
        # 获取系统基本信息
        memory_info = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=1)
        disk_usage = psutil.disk_usage('/')
        
        # 计算系统运行时间（简化实现）
        boot_time = psutil.boot_time()
        uptime = datetime.now() - datetime.fromtimestamp(boot_time)
        uptime_str = str(timedelta(seconds=int(uptime.total_seconds())))
        
        # 构建系统状态
        system_status = SystemStatus(
            engine_status="ready" if engine else "not_initialized",
            memory_usage={
                "total": memory_info.total,
                "available": memory_info.available,
                "percent": memory_info.percent,
                "used": memory_info.used
            },
            active_sessions=len(engine.sessions) if engine else 0,
            active_connections=0,  # 将在后续与WebSocket管理器集成
            uptime=uptime_str
        )
        
        return SystemStatusResponse(
            success=True,
            message="系统状态获取成功",
            data={
                "cpu_percent": cpu_percent,
                "disk_usage": {
                    "total": disk_usage.total,
                    "used": disk_usage.used,
                    "free": disk_usage.free,
                    "percent": (disk_usage.used / disk_usage.total) * 100
                },
                "platform": {
                    "system": platform.system(),
                    "node": platform.node(),
                    "release": platform.release(),
                    "version": platform.version(),
                    "machine": platform.machine(),
                    "processor": platform.processor()
                }
            },
            status=system_status
        )
        
    except Exception as e:
        logger.error(f"获取系统状态失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取系统状态失败: {str(e)}")

@router.get("/info", response_model=APIResponse)
async def get_system_info():
    """获取系统基本信息
    
    Returns:
        系统基本信息
    """
    try:
        info = {
            "api_version": "2.0.0",
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "hostname": platform.node(),
            "timezone": str(datetime.now().astimezone().tzinfo),
            "current_time": datetime.now().isoformat()
        }
        
        return APIResponse(
            success=True,
            message="系统信息获取成功",
            data=info
        )
        
    except Exception as e:
        logger.error(f"获取系统信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取系统信息失败: {str(e)}")

@router.get("/config", response_model=APIResponse)
async def get_system_config(
    engine: IsotopeEngine = Depends(get_engine)
):
    """获取系统配置信息
    
    Args:
        engine: 引擎实例
        
    Returns:
        系统配置信息
    """
    try:
        # 获取非敏感的配置信息
        config_info = {
            "use_enhanced_graph": getattr(engine, 'use_enhanced_graph', False),
            "verbose": getattr(engine, 'verbose', False),
            "checkpoint_dir": getattr(engine, 'checkpoint_dir', None),
            "tools_count": len(engine.get_available_tools()) if engine else 0,
            "supported_models": ["ollama", "openai"],  # 根据实际情况调整
            "features": {
                "streaming": True,
                "websocket": True,
                "file_upload": True,
                "dag_visualization": True,
                "memory_integration": True
            }
        }
        
        return APIResponse(
            success=True,
            message="系统配置获取成功",
            data=config_info
        )
        
    except Exception as e:
        logger.error(f"获取系统配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取系统配置失败: {str(e)}")

@router.get("/metrics", response_model=APIResponse)
async def get_system_metrics(
    engine: IsotopeEngine = Depends(get_engine)
):
    """获取系统性能指标
    
    Args:
        engine: 引擎实例
        
    Returns:
        系统性能指标
    """
    try:
        # 收集性能指标
        metrics = {
            "sessions": {
                "total": len(engine.sessions) if engine else 0,
                "active": len([s for s in engine.sessions.values() if s.get("active", False)]) if engine else 0
            },
            "memory": {
                "process_memory": psutil.Process().memory_info().rss,
                "system_memory_percent": psutil.virtual_memory().percent
            },
            "cpu": {
                "process_cpu_percent": psutil.Process().cpu_percent(),
                "system_cpu_percent": psutil.cpu_percent()
            },
            "io": {
                "read_count": psutil.disk_io_counters().read_count if psutil.disk_io_counters() else 0,
                "write_count": psutil.disk_io_counters().write_count if psutil.disk_io_counters() else 0
            }
        }
        
        return APIResponse(
            success=True,
            message="系统指标获取成功",
            data=metrics
        )
        
    except Exception as e:
        logger.error(f"获取系统指标失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取系统指标失败: {str(e)}")

@router.get("/sessions/restored", response_model=APIResponse)
async def get_restored_sessions_info(
    engine: IsotopeEngine = Depends(get_engine)
):
    """获取已恢复会话的统计信息
    
    Args:
        engine: 引擎实例
        
    Returns:
        已恢复会话的详细统计信息
    """
    try:
        if not engine:
            raise HTTPException(status_code=503, detail="引擎未初始化")
        
        # 获取恢复会话的统计信息
        sessions_info = engine.get_restored_sessions_info()
        
        return APIResponse(
            success=True,
            message=f"获取到 {sessions_info['total_sessions']} 个已恢复会话的信息",
            data=sessions_info
        )
        
    except Exception as e:
        logger.error(f"获取恢复会话信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取恢复会话信息失败: {str(e)}")

@router.post("/sessions/restore", response_model=APIResponse)
async def restore_sessions_manually(
    engine: IsotopeEngine = Depends(get_engine)
):
    """手动触发会话恢复操作
    
    Args:
        engine: 引擎实例
        
    Returns:
        恢复操作结果
    """
    try:
        if not engine:
            raise HTTPException(status_code=503, detail="引擎未初始化")
        
        # 记录恢复前的会话数量
        sessions_before = len(engine.sessions)
        
        # 手动触发会话恢复
        engine._restore_existing_sessions()
        
        # 记录恢复后的会话数量
        sessions_after = len(engine.sessions)
        restored_count = sessions_after - sessions_before
        
        # 获取详细统计信息
        sessions_info = engine.get_restored_sessions_info()
        
        return APIResponse(
            success=True,
            message=f"会话恢复完成，新恢复 {restored_count} 个会话",
            data={
                "sessions_before": sessions_before,
                "sessions_after": sessions_after,
                "newly_restored": restored_count,
                "total_sessions": sessions_info["total_sessions"],
                "total_messages": sessions_info["total_messages"],
                "sessions_with_files": sessions_info["sessions_with_files"]
            }
        )
        
    except Exception as e:
        logger.error(f"手动恢复会话失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"手动恢复会话失败: {str(e)}")

@router.get("/logs", response_model=APIResponse)
async def get_system_logs(
    level: Optional[str] = "INFO",
    limit: Optional[int] = 100,
    offset: Optional[int] = 0
):
    """获取系统日志
    
    Args:
        level: 日志级别过滤
        limit: 返回数量限制
        offset: 偏移量
        
    Returns:
        系统日志
    """
    try:
        # 这里简化实现，实际应该从日志文件或日志系统读取
        logs = [
            {
                "timestamp": datetime.now().isoformat(),
                "level": "INFO",
                "message": "API服务运行正常",
                "module": "system"
            },
            {
                "timestamp": (datetime.now() - timedelta(minutes=5)).isoformat(),
                "level": "INFO", 
                "message": "引擎初始化完成",
                "module": "engine"
            }
        ]
        
        # 模拟分页
        total = len(logs)
        if offset:
            logs = logs[offset:]
        if limit:
            logs = logs[:limit]
        
        return APIResponse(
            success=True,
            message=f"获取到{len(logs)}条日志记录",
            data={
                "logs": logs,
                "total": total,
                "level": level,
                "limit": limit,
                "offset": offset
            }
        )
        
    except Exception as e:
        logger.error(f"获取系统日志失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取系统日志失败: {str(e)}")

@router.post("/cleanup", response_model=APIResponse)
async def cleanup_system(
    engine: IsotopeEngine = Depends(get_engine)
):
    """系统清理操作
    
    Args:
        engine: 引擎实例
        
    Returns:
        清理结果
    """
    try:
        cleaned_items = []
        
        # 清理过期会话（示例：超过24小时未活动的会话）
        if engine:
            current_time = datetime.now()
            expired_sessions = []
            
            for session_id, session_data in engine.sessions.items():
                last_updated = session_data.get("last_updated")
                if last_updated:
                    last_updated_time = datetime.fromisoformat(last_updated)
                    if (current_time - last_updated_time).days >= 1:
                        expired_sessions.append(session_id)
            
            # 删除过期会话
            for session_id in expired_sessions:
                if engine.delete_session(session_id):
                    cleaned_items.append(f"删除过期会话: {session_id}")
        
        # 清理临时文件（可以扩展）
        temp_dir = "data/temp"
        if os.path.exists(temp_dir):
            for file in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, file)
                if os.path.isfile(file_path):
                    file_age = datetime.now() - datetime.fromtimestamp(os.path.getctime(file_path))
                    if file_age.days >= 1:  # 删除1天前的临时文件
                        os.remove(file_path)
                        cleaned_items.append(f"删除临时文件: {file}")
        
        return APIResponse(
            success=True,
            message=f"系统清理完成，清理了{len(cleaned_items)}个项目",
            data={"cleaned_items": cleaned_items}
        )
        
    except Exception as e:
        logger.error(f"系统清理失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"系统清理失败: {str(e)}")

@router.post("/restart", response_model=APIResponse)
async def restart_system():
    """系统重启操作（仅返回指示信息，不实际重启）
    
    Returns:
        重启指示信息
    """
    try:
        return APIResponse(
            success=True,
            message="系统重启请求已接收，请手动重启服务",
            data={
                "restart_command": "建议使用 systemctl restart 或重新启动应用",
                "timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"处理重启请求失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理重启请求失败: {str(e)}")

@router.get("/database/status", response_model=APIResponse)
async def get_database_status():
    """获取数据库连接状态
    
    Returns:
        数据库状态信息
    """
    try:
        # 检查各种数据库连接状态
        db_status = {
            "postgresql": "未配置",
            "mysql": "未配置", 
            "redis": "未配置",
            "elasticsearch": "未配置"
        }
        
        # 这里可以实际检查数据库连接
        # 目前返回默认状态
        
        return APIResponse(
            success=True,
            message="数据库状态检查完成",
            data={"databases": db_status}
        )
        
    except Exception as e:
        logger.error(f"检查数据库状态失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"检查数据库状态失败: {str(e)}") 