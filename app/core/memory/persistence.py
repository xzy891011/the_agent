"""
持久化管理模块 - 提供会话状态持久化功能，基于LangGraph实现
"""

import os
import logging
from typing import Dict, Any, Optional, Union

# 配置日志
logger = logging.getLogger(__name__)

class IsotopeCheckpointer:
    """Isotope持久化管理器，包装LangGraph的持久化功能"""
    
    def __init__(
        self, 
        storage_type: str = "memory", 
        connection_string: Optional[str] = None,
        checkpoint_dir: Optional[str] = None
    ):
        """初始化持久化管理器
        
        Args:
            storage_type: 存储类型，可选 'memory', 'file', 'postgres', 'mongodb'
            connection_string: 数据库连接字符串
            checkpoint_dir: 文件存储目录
        """
        self.storage_type = storage_type
        self.connection_string = connection_string
        self.checkpoint_dir = checkpoint_dir or "./checkpoints"
        
    def get_checkpointer(self):
        """获取合适的持久化器
        
        Returns:
            LangGraph支持的持久化器
        """
        # 使用内存存储（不持久化）
        if self.storage_type == "memory":
            try:
                from langgraph.checkpoint.memory import MemorySaver
                logger.info("使用内存持久化器")
                return MemorySaver()
            except ImportError:
                logger.warning("无法导入MemorySaver，回退到其他存储")
                self.storage_type = "file"
        
        # 使用文件存储
        if self.storage_type == "file":
            try:
                # 注意：由于LangGraph在多线程环境中使用SQLite可能导致
                # "SQLite objects created in a thread can only be used in that same thread"错误，
                # 因此我们使用内存存储以避免此问题
                # 记忆存储功能不受此影响，因为记忆存储使用独立的存储机制
                from langgraph.checkpoint.memory import MemorySaver
                logger.info("由于多线程安全考虑，使用内存持久化器替代SQLite")
                return MemorySaver()
            except ImportError:
                logger.warning("无法导入MemorySaver，回退到内存存储")
                return self._fallback_to_memory()
        
        # 使用PostgreSQL
        if self.storage_type == "postgres":
            if not self.connection_string:
                logger.warning("PostgreSQL需要连接字符串，回退到内存存储")
                return self._fallback_to_memory()
                
            try:
                from langgraph.checkpoint.postgres import PostgresSaver
                logger.info("使用PostgreSQL持久化器")
                return PostgresSaver(conn_string=self.connection_string)
            except (ImportError, TypeError) as e:
                logger.warning(f"无法创建PostgresSaver: {str(e)}，回退到内存存储")
                return self._fallback_to_memory()
                
        # 使用MongoDB (如果LangGraph提供对MongoDB的支持)
        if self.storage_type == "mongodb":
            if not self.connection_string:
                logger.warning("MongoDB需要连接字符串，回退到内存存储")
                return self._fallback_to_memory()
                
            try:
                from langgraph.checkpoint.mongodb import MongoDBSaver
                logger.info("使用MongoDB持久化器")
                return MongoDBSaver(conn_string=self.connection_string)
            except (ImportError, TypeError) as e:
                logger.warning(f"无法创建MongoDBSaver: {str(e)}，回退到内存存储")
                return self._fallback_to_memory()
        
        # 默认使用内存存储
        return self._fallback_to_memory()
    
    def _fallback_to_memory(self):
        """回退到内存存储"""
        try:
            from langgraph.checkpoint.memory import MemorySaver
            logger.info("使用内存持久化器作为回退")
            return MemorySaver()
        except ImportError:
            logger.error("无法导入MemorySaver，无法创建持久化器")
            return None
    
    def list_checkpoints(self, thread_id: Optional[str] = None) -> Dict[str, Any]:
        """列出可用的检查点
        
        Args:
            thread_id: 可选的线程ID过滤
            
        Returns:
            检查点信息字典
        """
        checkpointer = self.get_checkpointer()
        if not hasattr(checkpointer, "list_checkpoints"):
            logger.warning("当前持久化器不支持列出检查点")
            return {}
            
        try:
            if thread_id:
                return checkpointer.list_checkpoints(thread_id)
            else:
                return checkpointer.list_checkpoints()
        except Exception as e:
            logger.error(f"列出检查点出错: {str(e)}")
            return {} 