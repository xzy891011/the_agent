"""
API路由模块 - 定义各种API端点

包含以下路由：
1. chat - 聊天相关API
2. sessions - 会话管理API
3. files - 文件管理API
4. system - 系统管理API
"""

from .system import router as system_router
from .files import router as files_router
from .chat import router as chat_router
from .sessions import router as sessions_router
from .visualization import router as visualization_router
from .data import router as data_router

__all__ = [
    "system_router",
    "files_router", 
    "chat_router",
    "sessions_router",
    "visualization_router",
    "data_router"
] 