"""
主要的FastAPI应用和服务器 - 阶段4前后端分离核心实现

功能包括：
1. FastAPI应用创建和配置
2. CORS支持和中间件配置
3. API路由注册
4. WebSocket端点配置
5. 错误处理和日志记录
"""

import os
import sys
import asyncio
import logging
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import uvicorn

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.core.engine import IsotopeEngine
from app.core.config import ConfigManager
from app.api.routes import chat, sessions, files, system
from app.api.websocket import WebSocketManager
from app.api.models import APIResponse, ErrorResponse
from app.api.dependencies import set_engine  # 导入依赖设置函数

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局变量
engine_instance: Optional[IsotopeEngine] = None
websocket_manager: Optional[WebSocketManager] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global engine_instance, websocket_manager
    
    logger.info("🚀 启动后端API服务...")
    
    try:
        # 1. 初始化配置
        config_manager = ConfigManager()
        config = config_manager.load_config()
        
        # 2. 创建引擎实例 - 使用增强图模式
        engine_instance = IsotopeEngine(
            config=config,
            verbose=True,
        )
        
        # 设置全局引擎实例供依赖注入使用
        set_engine(engine_instance)
        
        # 3. 初始化WebSocket管理器
        websocket_manager = WebSocketManager(engine=engine_instance)
        
        logger.info("✅ 后端API服务初始化完成")
        
        yield
        
    except Exception as e:
        logger.error(f"❌ 后端API服务初始化失败: {str(e)}")
        raise
    finally:
        logger.info("🛑 关闭后端API服务...")

def create_app() -> FastAPI:
    """创建FastAPI应用实例
    
    Returns:
        配置好的FastAPI应用
    """
    
    # 创建FastAPI应用
    app = FastAPI(
        title="天然气碳同位素智能分析系统 API",
        description="为前后端分离架构提供RESTful API和WebSocket服务",
        version="2.0.0",
        lifespan=lifespan
    )
    
    # 配置CORS中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 在生产环境中应该限制具体域名
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 注册API路由
    app.include_router(chat.router, prefix="/api/v1/chat", tags=["聊天"])
    app.include_router(sessions.router, prefix="/api/v1/sessions", tags=["会话管理"])
    app.include_router(files.router, prefix="/api/v1/files", tags=["文件管理"])
    app.include_router(system.router, prefix="/api/v1/system", tags=["系统管理"])
    
    # 阶段4新增：可视化路由
    from .routes.visualization import router as visualization_router
    app.include_router(visualization_router, prefix="/api/v1")
    
    # 新增：数据管理路由
    from .routes.data import router as data_router
    app.include_router(data_router, prefix="/api/v1/data", tags=["数据管理"])
    
    # 静态文件服务
    if os.path.exists("data/generated"):
        app.mount("/static", StaticFiles(directory="data/generated"), name="static")
    
    @app.get("/", response_model=APIResponse)
    async def root():
        """根路径 - API状态检查"""
        return APIResponse(
            success=True,
            message="天然气碳同位素智能分析系统API正在运行",
            data={
                "version": "2.0.0",
                "status": "running",
                "engine_ready": engine_instance is not None,
                "websocket_ready": websocket_manager is not None
            }
        )
    
    @app.get("/health", response_model=APIResponse)
    async def health_check():
        """健康检查端点"""
        try:
            # 检查引擎状态
            engine_status = "ready" if engine_instance else "not_initialized"
            
            # 检查WebSocket管理器状态
            ws_status = "ready" if websocket_manager else "not_initialized"
            
            return APIResponse(
                success=True,
                message="系统健康状况良好",
                data={
                    "engine_status": engine_status,
                    "websocket_status": ws_status,
                    "active_sessions": len(engine_instance.sessions) if engine_instance else 0,
                    "active_connections": websocket_manager.get_connection_count() if websocket_manager else 0
                }
            )
        except Exception as e:
            logger.error(f"健康检查失败: {str(e)}")
            return ErrorResponse(
                success=False,
                message="系统健康检查失败",
                error=str(e)
            )
    
    @app.websocket("/ws/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str):
        """WebSocket端点 - 实时双向通信"""
        if not websocket_manager:
            await websocket.close(code=1003, reason="WebSocket manager not initialized")
            return
        
        await websocket_manager.connect(websocket, session_id)
        
        try:
            while True:
                # 接收客户端消息
                data = await websocket.receive_text()
                
                # 处理消息并流式返回结果
                await websocket_manager.handle_message(websocket, session_id, data)
                
        except WebSocketDisconnect:
            logger.info(f"WebSocket连接断开: session_id={session_id}")
        except Exception as e:
            logger.error(f"WebSocket处理错误: {str(e)}")
        finally:
            websocket_manager.disconnect(websocket, session_id)
    
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        """全局异常处理器"""
        logger.error(f"API异常: {str(exc)}")
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                success=False,
                message="服务器内部错误",
                error=str(exc)
            ).dict()
        )
    
    return app

def get_websocket_manager() -> WebSocketManager:
    """依赖注入 - 获取WebSocket管理器"""
    if websocket_manager is None:
        raise HTTPException(status_code=503, detail="WebSocket管理器未初始化")
    return websocket_manager

def run_api_server(
    host: str = "0.0.0.0",
    port: int = 7102,
    reload: bool = False,
    log_level: str = "info"
):
    """运行API服务器
    
    Args:
        host: 监听主机
        port: 监听端口
        reload: 是否启用热重载
        log_level: 日志级别
    """
    logger.info(f"启动API服务器: http://{host}:{port}")
    
    # 优化的uvicorn配置 - 专门针对流式输出优化
    uvicorn.run(
        "app.api.main:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
        log_level=log_level,
        
        # WebSocket配置
        ws_ping_interval=30,
        ws_ping_timeout=30,
        
        # 关键的流式输出优化配置
        server_header=False,
        access_log=True,
        loop="asyncio",
        
        # 设置更小的缓冲区以提高流式响应速度
        backlog=2048,
        
        # HTTP/1.1优化配置，确保实时流式传输
        h11_max_incomplete_event_size=8192,     # 减小缓冲区
        
        # 启用更激进的无缓冲设置
        timeout_keep_alive=30,
        timeout_graceful_shutdown=10,
        
        # 连接相关优化
        limit_concurrency=1000,
        limit_max_requests=10000,
        
        # 关键：确保使用最新的http协议实现，支持更好的流式传输
        http="h11",  # 使用h11实现，对流式输出支持更好
        
        # 日志配置
        use_colors=True,
        
        # 额外的性能优化
        workers=1,  # 单进程模式，避免进程间通信延迟
    )

if __name__ == "__main__":
    run_api_server(reload=True)

# 创建app实例，供外部导入使用
app = create_app() 