"""
后端API模块 - 为前后端分离提供RESTful API和WebSocket服务

该模块负责：
1. RESTful API接口 - 提供HTTP API服务
2. WebSocket流式服务 - 实现实时双向通信
3. 多模态数据传输 - 支持文本、图片、文件、DAG等
4. 会话管理 - 处理用户会话和状态
"""

from app.api.main import create_app, run_api_server

__all__ = [
    "create_app",
    "run_api_server"
] 