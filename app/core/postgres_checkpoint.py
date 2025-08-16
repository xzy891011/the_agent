"""
PostgreSQL Checkpoint 管理器

该模块提供了基于PostgreSQL的LangGraph检查点持久化功能，支持：
1. 会话状态的持久化存储
2. 失败节点的重播和恢复
3. 子图级别的检查点
4. 分布式环境下的状态共享

使用 LangGraph 官方的 PostgresSaver 实现
"""

import logging
try:
    import psycopg2
except ImportError:
    try:
        import psycopg2
    except ImportError:
        psycopg2 = None
from typing import Dict, Any, Optional, List
from datetime import datetime
import time
import uuid

try:
    from langgraph.checkpoint.postgres import PostgresSaver
    POSTGRES_CHECKPOINT_AVAILABLE = True
except ImportError:
    POSTGRES_CHECKPOINT_AVAILABLE = False
    PostgresSaver = None

try:
    from langgraph.checkpoint.memory import MemorySaver
    MEMORY_SAVER_AVAILABLE = True
except ImportError:
    MEMORY_SAVER_AVAILABLE = False
    MemorySaver = None

from app.core.config import ConfigManager

logger = logging.getLogger(__name__)

class PostgreSQLCheckpointManager:
    """PostgreSQL检查点管理器
    
    提供基于PostgreSQL的LangGraph检查点持久化功能，支持：
    - 自动故障恢复
    - 会话状态持久化
    - 多级检查点
    - 分布式部署支持
    """
    
    def __init__(self, config: Optional[ConfigManager] = None):
        """初始化PostgreSQL检查点管理器
        
        Args:
            config: 系统配置对象
        """
        self.config = config or ConfigManager()
        self._checkpointer = None
        self._postgres_context = None  # 添加postgres_context属性
        self._postgres_config = self.config.get_postgresql_config()
        self._connection_string = self._build_connection_string()
        
        # 初始化检查点器
        self._init_checkpointer()
    
    def _build_connection_string(self) -> str:
        """构建PostgreSQL连接字符串"""
        postgres_config = self._postgres_config
        user = postgres_config.get("user", "sweet")
        password = postgres_config.get("password", "")
        host = postgres_config.get("host", "localhost")
        port = postgres_config.get("port", 5432)
        database = postgres_config.get("database", "isotope")
        
        # 构建PostgreSQL连接字符串，添加字符编码参数
        connection_string = f"postgresql://{user}:{password}@{host}:{port}/{database}?client_encoding=utf8"
        
        logger.info(f"构建PostgreSQL连接字符串: postgresql://{user}:***@{host}:{port}/{database}?client_encoding=utf8")
        return connection_string
    
    def _init_checkpointer(self):
        """初始化检查点器"""
        try:
            if POSTGRES_CHECKPOINT_AVAILABLE:
                logger.info("尝试使用PostgreSQL检查点器...")
                
                # 测试数据库连接
                if not self._test_postgres_connection():
                    logger.warning("PostgreSQL连接测试失败，回退到内存检查点器")
                    self._fallback_to_memory()
                    return
                
                # 创建PostgreSQL检查点器
                try:
                    logger.info("创建PostgresSaver检查点器...")
                    
                    # PostgresSaver.from_conn_string 返回一个上下文管理器
                    # 我们需要正确地使用它
                    postgres_context = PostgresSaver.from_conn_string(self._connection_string)
                    
                    # 检查是否需要设置表结构
                    try:
                        # 尝试进入上下文管理器获取实际的checkpointer
                        actual_checkpointer = postgres_context.__enter__()
                        
                        # 保存上下文管理器和实际的checkpointer
                        self._postgres_context = postgres_context
                        self._checkpointer = actual_checkpointer
                        
                        logger.info(f"PostgreSQL检查点器类型: {type(actual_checkpointer).__name__}")
                        
                        # 必须调用setup方法来创建数据库表结构 - 根据官方文档这是必需的
                        actual_checkpointer.setup()
                        logger.info("PostgreSQL检查点器表结构设置成功")
                        
                    except Exception as setup_error:
                        logger.warning(f"设置表结构时出现问题，但将继续使用: {str(setup_error)}")
                    
                    # 验证检查点器是否真正可用
                    if self._validate_postgres_checkpointer():
                        logger.info("成功创建并验证PostgreSQL检查点器")
                        return
                    else:
                        logger.warning("PostgreSQL检查点器验证失败，回退到内存检查点器")
                        self._cleanup_postgres_context()
                        self._fallback_to_memory()
                        return
                    
                except Exception as e:
                    logger.error(f"创建PostgreSQL检查点器失败: {str(e)}")
                    self._cleanup_postgres_context()
                    self._fallback_to_memory()
                    
            else:
                logger.warning("LangGraph PostgresSaver 不可用，回退到内存检查点器")
                self._fallback_to_memory()
                
        except Exception as e:
            logger.error(f"初始化检查点器时发生错误: {str(e)}")
            self._cleanup_postgres_context()
            self._fallback_to_memory()
    
    def _cleanup_postgres_context(self):
        """清理PostgreSQL上下文管理器"""
        try:
            if hasattr(self, '_postgres_context') and self._postgres_context:
                self._postgres_context.__exit__(None, None, None)
                self._postgres_context = None
                logger.debug("PostgreSQL上下文管理器已清理")
        except Exception as e:
            logger.warning(f"清理PostgreSQL上下文管理器时出错: {str(e)}")
    
    def __del__(self):
        """析构函数，确保清理资源"""
        self._cleanup_postgres_context()
    
    def _test_postgres_connection(self) -> bool:
        """测试PostgreSQL连接"""
        try:
            postgres_config = self._postgres_config
            user = postgres_config.get("user", "sweet")
            password = postgres_config.get("password", "")
            host = postgres_config.get("host", "localhost")
            port = postgres_config.get("port", 5432)
            database = postgres_config.get("database", "isotope")
            
            logger.info(f"测试PostgreSQL连接: {host}:{port}/{database}")
            
            # 使用psycopg2直接连接测试，添加字符编码参数
            conn = psycopg2.connect(
                host=host,
                user=user,
                password=password,
                database=database,
                port=port,
                connect_timeout=10,
                client_encoding='utf8'  # 明确设置UTF-8编码
            )
            
            logger.info("PostgreSQL直接连接测试成功")
            
            # 简单验证表是否可访问
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT tablename FROM pg_tables 
                    WHERE schemaname = 'public'
                """)
                tables = [t[0] for t in cursor.fetchall()]
                logger.info(f"数据库中的表: {tables}")
                
                # 简单测试写入能力，使用英文字符避免编码问题
                test_id = f"test_{int(time.time())}"
                try:
                    # 创建测试表
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS test_connection (
                            id VARCHAR(255) PRIMARY KEY, 
                            data TEXT
                        )
                    """)
                    
                    # 执行简单的写入和读取测试，使用英文字符
                    cursor.execute(
                        "INSERT INTO test_connection (id, data) VALUES (%s, %s)",
                        (test_id, "connection_test_data")  # 使用英文避免编码问题
                    )
                    cursor.execute("SELECT * FROM test_connection WHERE id = %s", (test_id,))
                    test_result = cursor.fetchone()
                    if test_result:
                        logger.info("PostgreSQL写入和读取测试成功")
                    else:
                        logger.warning("PostgreSQL写入成功但读取失败")
                    
                    # 清理测试数据
                    cursor.execute("DELETE FROM test_connection WHERE id = %s", (test_id,))
                    conn.commit()
                    
                except Exception as test_error:
                    logger.warning(f"PostgreSQL写入测试失败: {str(test_error)}")
            
            # 关闭连接
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"PostgreSQL连接测试失败: {str(e)}")
            return False
    
    def _fallback_to_memory(self):
        """回退到内存检查点器"""
        if MEMORY_SAVER_AVAILABLE:
            logger.warning("回退到内存检查点器")
            self._checkpointer = MemorySaver()
            logger.info("成功回退到内存检查点器")
        else:
            raise ValueError("PostgreSQL不可用且内存检查点器也不可用")
    
    def get_checkpointer(self):
        """获取检查点器实例
        
        Returns:
            PostgresSaver或MemorySaver实例
        """
        return self._checkpointer
    
    def is_postgres_available(self) -> bool:
        """检查PostgreSQL是否可用
        
        Returns:
            bool: PostgreSQL是否可用
        """
        if not POSTGRES_CHECKPOINT_AVAILABLE:
            logger.debug("LangGraph PostgresSaver不可用")
            return False
            
        if not self._checkpointer:
            logger.debug("检查点器未初始化")
            return False
        
        # 检查是否为真正的PostgresSaver实例
        try:
            # 如果是MemorySaver，则PostgreSQL不可用
            if isinstance(self._checkpointer, MemorySaver):
                logger.debug("当前使用内存检查点器")
                return False
            
            # 检查是否是PostgresSaver类型
            checkpointer_type = type(self._checkpointer).__name__
            checkpointer_module = type(self._checkpointer).__module__
            
            # 更严格的检查
            is_postgres_type = (
                "Postgres" in checkpointer_type or 
                "PostgresSaver" in checkpointer_type or
                "postgres" in checkpointer_module.lower()
            )
            
            if is_postgres_type:
                # 额外测试数据库连接
                connection_ok = self._test_postgres_connection()
                logger.debug(f"PostgreSQL连接测试结果: {connection_ok}")
                return connection_ok
            else:
                logger.debug(f"检查点器类型不是PostgreSQL: {checkpointer_type} (模块: {checkpointer_module})")
                return False
                
        except Exception as e:
            logger.debug(f"检查PostgreSQL可用性时出错: {str(e)}")
            return False
    
    def test_connection(self) -> bool:
        """测试数据库连接
        
        Returns:
            bool: 连接是否成功
        """
        if not self._checkpointer:
            return False
            
        if isinstance(self._checkpointer, MemorySaver):
            logger.info("使用内存检查点器，连接测试通过")
            return True
            
        # 对于PostgreSQL检查点器，进行实际连接测试
        return self._test_postgres_connection()
    
    def list_checkpoints(
        self, 
        thread_id: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """列出检查点
        
        Args:
            thread_id: 线程ID，如果为None则列出所有线程的检查点
            limit: 限制返回的检查点数量
            
        Returns:
            检查点列表
        """
        if not self._checkpointer:
            logger.warning("检查点器未初始化")
            return []
        
        try:
            checkpoints = []
            
            if isinstance(self._checkpointer, MemorySaver):
                # 内存检查点器的处理
                logger.info("从内存检查点器获取检查点列表")
                # 内存检查点器通常没有持久化的检查点列表
                return []
            
            # PostgreSQL检查点器的处理
            logger.info(f"列出检查点: thread_id={thread_id or 'all'}, limit={limit}")
            
            # 使用PostgresSaver的list方法，需要正确构造参数
            try:
                # 根据官方文档，config必须包含checkpoint_ns字段
                if thread_id:
                    config = {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": ""  # 默认为空字符串
                        }
                    }
                else:
                    config = None  # 对于列出所有检查点的情况
                
                # 检查checkpointer是否有list方法
                if hasattr(self._checkpointer, 'list') and callable(getattr(self._checkpointer, 'list')):
                    # 尝试直接调用list方法
                    checkpoint_tuples = list(self._checkpointer.list(config, limit=limit))
                    
                    for checkpoint_tuple in checkpoint_tuples:
                        try:
                            # 根据LangGraph的API解析checkpoint tuple
                            if hasattr(checkpoint_tuple, 'config') and hasattr(checkpoint_tuple, 'checkpoint'):
                                checkpoint_info = {
                                    "thread_id": checkpoint_tuple.config.get("configurable", {}).get("thread_id"),
                                    "checkpoint_id": checkpoint_tuple.checkpoint.get("id"),
                                    "timestamp": checkpoint_tuple.checkpoint.get("ts"),
                                    "metadata": getattr(checkpoint_tuple, 'metadata', {})
                                }
                                checkpoints.append(checkpoint_info)
                            else:
                                # 处理其他格式的checkpoint数据
                                logger.debug(f"未知的checkpoint格式: {type(checkpoint_tuple)}")
                                continue
                        except Exception as parse_error:
                            logger.warning(f"解析检查点信息失败: {str(parse_error)}")
                            continue
                else:
                    logger.info("检查点器支持list方法，但可能需要特殊配置")
                    return []
                
            except Exception as api_error:
                logger.info(f"PostgreSQL检查点器list调用: {str(api_error)}")
                # 不再视为错误，可能是正常的空结果
                return []
            
            logger.info(f"获取到 {len(checkpoints)} 个检查点")
            return checkpoints
            
        except Exception as e:
            logger.warning(f"列出检查点时出现问题: {str(e)}")
            return []
    
    def get_checkpoint(
        self, 
        thread_id: str, 
        checkpoint_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """获取特定检查点
        
        Args:
            thread_id: 线程ID
            checkpoint_id: 检查点ID，如果为None则获取最新检查点
            
        Returns:
            检查点数据，如果不存在则返回None
        """
        if not self._checkpointer:
            logger.warning("检查点器未初始化")
            return None
        
        try:
            logger.info(f"获取检查点: thread_id={thread_id}, checkpoint_id={checkpoint_id or '最新'}")
            
            # 根据官方文档，config必须包含checkpoint_ns字段
            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": ""  # 默认为空字符串
                }
            }
            
            if checkpoint_id:
                config["configurable"]["checkpoint_id"] = checkpoint_id
            
            # 检查checkpointer是否有get方法
            if hasattr(self._checkpointer, 'get') and callable(getattr(self._checkpointer, 'get')):
                try:
                    checkpoint = self._checkpointer.get(config)
                    
                    if checkpoint:
                        logger.info(f"成功获取检查点: {thread_id}")
                        return {
                            "checkpoint": checkpoint,
                            "thread_id": thread_id,
                            "checkpoint_id": checkpoint_id
                        }
                    else:
                        logger.info(f"未找到检查点: thread_id={thread_id}, checkpoint_id={checkpoint_id}")
                        return None
                except Exception as get_error:
                    logger.info(f"PostgreSQL检查点器get调用: {str(get_error)}")
                    return None
            else:
                logger.info("检查点器支持get方法，但可能需要特殊配置")
                return None
                
        except Exception as e:
            logger.warning(f"获取检查点时出现问题: {str(e)}")
            return None
    
    def put_checkpoint(
        self, 
        config: Dict[str, Any], 
        checkpoint: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """保存检查点
        
        Args:
            config: 配置信息
            checkpoint: 检查点数据
            metadata: 元数据
            
        Returns:
            bool: 保存是否成功
        """
        if not self._checkpointer:
            logger.warning("检查点器未初始化")
            return False
        
        try:
            thread_id = config.get("configurable", {}).get("thread_id")
            logger.info(f"保存检查点: thread_id={thread_id}")
            
            # 根据官方文档，config必须包含checkpoint_ns字段
            complete_config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": config.get("configurable", {}).get("checkpoint_ns", "")  # 默认为空字符串
                }
            }
            
            # 如果原始config中有checkpoint_id，也要包含
            if "checkpoint_id" in config.get("configurable", {}):
                complete_config["configurable"]["checkpoint_id"] = config["configurable"]["checkpoint_id"]
            
            # PostgresSaver.put() 需要 config, checkpoint, metadata, new_versions 四个参数
            # new_versions 通常是一个空字典，用于版本控制
            new_versions = {}
            
            result = self._checkpointer.put(complete_config, checkpoint, metadata or {}, new_versions)
            logger.info(f"成功保存检查点: {thread_id}")
            return True
            
        except Exception as e:
            logger.error(f"保存检查点失败: {str(e)}")
            return False
    
    def delete_checkpoint(
        self, 
        thread_id: str, 
        checkpoint_id: Optional[str] = None
    ) -> bool:
        """删除检查点
        
        Args:
            thread_id: 线程ID
            checkpoint_id: 检查点ID，如果为None则删除线程的所有检查点
            
        Returns:
            bool: 删除是否成功
        """
        if not self._checkpointer:
            logger.warning("检查点器未初始化")
            return False
        
        try:
            logger.info(f"删除检查点: thread_id={thread_id}, checkpoint_id={checkpoint_id or 'all'}")
            
            if hasattr(self._checkpointer, 'delete_thread'):
                # 删除整个线程的检查点
                self._checkpointer.delete_thread(thread_id)
                logger.info(f"成功删除线程检查点: {thread_id}")
                return True
            else:
                logger.warning("检查点器不支持删除操作")
                return False
                
        except Exception as e:
            logger.error(f"删除检查点失败: {str(e)}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取检查点统计信息
        
        Returns:
            统计信息字典
        """
        if not self._checkpointer:
            return {"status": "未初始化", "type": "无"}
        
        try:
            stats = {
                "status": "可用",
                "type": "PostgreSQL" if isinstance(self._checkpointer, PostgresSaver) else "内存",
                "connection_available": self.test_connection(),
                "timestamp": datetime.now().isoformat()
            }
            
            # 尝试获取更多统计信息
            try:
                all_checkpoints = self.list_checkpoints(limit=1000)
                stats["total_checkpoints"] = len(all_checkpoints)
                
                # 统计不同线程的数量
                thread_ids = set()
                for cp in all_checkpoints:
                    if cp.get("thread_id"):
                        thread_ids.add(cp["thread_id"])
                stats["unique_threads"] = len(thread_ids)
                
            except Exception as e:
                logger.warning(f"获取详细统计信息失败: {str(e)}")
                stats["total_checkpoints"] = "未知"
                stats["unique_threads"] = "未知"
            
            return stats
            
        except Exception as e:
            logger.error(f"获取统计信息失败: {str(e)}")
            return {"status": "错误", "error": str(e)}
    
    def _validate_postgres_checkpointer(self) -> bool:
        """验证PostgreSQL检查点器是否真正可用
        
        Returns:
            bool: 检查点器是否真正可用
        """
        try:
            if not self._checkpointer:
                return False
            
            # 检查是否为PostgresSaver实例
            checkpointer_type = type(self._checkpointer).__name__
            if "Postgres" not in checkpointer_type and "PostgresSaver" not in checkpointer_type:
                logger.warning(f"检查点器类型不是PostgresSaver: {checkpointer_type}")
                return False
            
            # 检查基本方法是否存在
            required_methods = ['put', 'get', 'list']
            for method_name in required_methods:
                if not hasattr(self._checkpointer, method_name):
                    logger.warning(f"检查点器缺少必需方法: {method_name}")
                    return False
            
            logger.info("PostgreSQL检查点器验证通过")
            return True
            
        except Exception as e:
            logger.error(f"验证PostgreSQL检查点器时出错: {str(e)}")
            return False


# 全局实例管理
_postgres_checkpoint_manager = None

def get_postgres_checkpoint_manager(config: Optional[ConfigManager] = None) -> PostgreSQLCheckpointManager:
    """获取PostgreSQL检查点管理器单例
    
    Args:
        config: 配置管理器实例
        
    Returns:
        PostgreSQL检查点管理器实例
    """
    global _postgres_checkpoint_manager
    
    if _postgres_checkpoint_manager is None:
        _postgres_checkpoint_manager = PostgreSQLCheckpointManager(config)
    
    return _postgres_checkpoint_manager

def init_postgres_checkpoint(config: Optional[ConfigManager] = None) -> PostgreSQLCheckpointManager:
    """初始化PostgreSQL检查点管理器
    
    Args:
        config: 配置管理器实例
        
    Returns:
        PostgreSQL检查点管理器实例
    """
    manager = get_postgres_checkpoint_manager(config)
    logger.info("PostgreSQL检查点管理器初始化完成")
    return manager 