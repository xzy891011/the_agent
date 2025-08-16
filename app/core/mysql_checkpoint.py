"""
MySQL Checkpoint 管理器 - 阶段2实现

该模块提供了基于MySQL的LangGraph检查点持久化功能，支持：
1. 会话状态的持久化存储
2. 失败节点的重播和恢复
3. 子图级别的检查点
4. 分布式环境下的状态共享
"""

import logging
import os
import pymysql
import contextlib
from typing import Dict, Any, Optional, List, Tuple, Union, Iterator
from datetime import datetime
import time
import uuid

try:
    from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
    MYSQL_CHECKPOINT_AVAILABLE = True
except ImportError:
    MYSQL_CHECKPOINT_AVAILABLE = False
    PyMySQLSaver = None

try:
    from langgraph.checkpoint.memory import MemorySaver
    MEMORY_SAVER_AVAILABLE = True
except ImportError:
    MEMORY_SAVER_AVAILABLE = False
    MemorySaver = None

from app.core.config import ConfigManager

logger = logging.getLogger(__name__)

class MySQLCheckpointManager:
    def _fix_connection_charset(self, conn):
        """修复连接字符集"""
        try:
            cursor = conn.cursor()
            # 强制设置连接使用utf8mb4_0900_ai_ci校对规则
            cursor.execute("SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci")
            cursor.execute("SET character_set_client = utf8mb4")
            cursor.execute("SET character_set_connection = utf8mb4")
            cursor.execute("SET character_set_results = utf8mb4")
            cursor.execute("SET collation_connection = utf8mb4_0900_ai_ci")
            cursor.close()
            logger.info("✅ 连接字符集修复成功")
        except Exception as e:
            logger.warning(f"连接字符集修复失败: {e}")

    """MySQL检查点管理器
    
    提供基于MySQL的LangGraph检查点持久化功能，支持：
    - 自动故障恢复
    - 会话状态持久化
    - 多级检查点
    - 分布式部署支持
    """
    
    def __init__(self, config: Optional[ConfigManager] = None):
        """初始化MySQL检查点管理器
        
        Args:
            config: 系统配置对象
        """
        self.config = config or ConfigManager()
        self._checkpointer = None
        self._mysql_config = self.config.get_mysql_config()
        self._connection_string = self._build_connection_string()
        
        # 初始化检查点器
        self._init_checkpointer()
    
    def _build_connection_string(self) -> str:
        """构建MySQL连接字符串"""
        mysql_config = self._mysql_config
        user = mysql_config.get("user", "root")
        password = mysql_config.get("password", "")
        host = mysql_config.get("host", "localhost")
        port = mysql_config.get("port", 3306)
        database = mysql_config.get("database", "isotope")
        
        # 构建基本连接字符串，不要在这里添加查询参数
        connection_string = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
        
        logger.info(f"构建MySQL连接字符串: mysql+pymysql://{user}:***@{host}:{port}/{database}")
        return connection_string
    
    def _init_checkpointer(self):
        """初始化检查点器"""
        try:
            if MYSQL_CHECKPOINT_AVAILABLE:
                logger.info("尝试使用MySQL检查点器...")
                
                try:
                    # 使用pymysql直接连接测试数据库可用性
                    import pymysql
                    mysql_config = self._mysql_config
                    user = mysql_config.get("user", "root")
                    password = mysql_config.get("password", "")
                    host = mysql_config.get("host", "localhost")
                    port = mysql_config.get("port", 3306)
                    database = mysql_config.get("database", "isotope")
                    
                    logger.info(f"测试MySQL连接: {host}:{port}/{database}")
                    try:
                        conn = pymysql.connect(
                            host=host,
                            user=user,
                            password=password,
                            database=database,
                            port=port,
                            autocommit=True,
                            connect_timeout=5  # 添加连接超时
                        )
                        logger.info("MySQL直接连接测试成功")
                        
                        # 简单验证表是否可访问
                        with conn.cursor() as cursor:
                            cursor.execute("SHOW TABLES")
                            tables = [t[0] for t in cursor.fetchall()]
                            logger.info(f"数据库中的表: {tables}")
                            
                            # 简单测试写入能力
                            test_id = f"test_{int(time.time())}"
                            try:
                                # 执行简单的写入和读取测试
                                cursor.execute(
                                    "CREATE TABLE IF NOT EXISTS test_connection (id VARCHAR(255) PRIMARY KEY, data TEXT)"
                                )
                                cursor.execute(
                                    "INSERT INTO test_connection (id, data) VALUES (%s, %s)",
                                    (test_id, "连接测试")
                                )
                                cursor.execute("SELECT * FROM test_connection WHERE id = %s", (test_id,))
                                test_result = cursor.fetchone()
                                if test_result:
                                    logger.info("MySQL写入和读取测试成功")
                                else:
                                    logger.warning("MySQL写入成功但读取失败")
                                # 清理测试数据
                                cursor.execute("DELETE FROM test_connection WHERE id = %s", (test_id,))
                            except Exception as test_error:
                                logger.warning(f"MySQL写入测试失败: {str(test_error)}")
                        
                        # 关闭连接
                        conn.close()
                        
                    except Exception as conn_error:
                        logger.error(f"MySQL连接测试失败: {str(conn_error)}")
                        logger.warning("回退到内存检查点器")
                        if MEMORY_SAVER_AVAILABLE:
                            self._checkpointer = MemorySaver()
                            logger.info("成功回退到内存检查点器")
                            return
                        else:
                            raise ValueError(f"MySQL不可用且内存检查点器也不可用")
                except Exception as e:
                    logger.error(f"MySQL测试过程中出错: {str(e)}")
                
                # 尝试创建真正的MySQL检查点器
                try:
                    logger.info("创建PyMySQLSaver检查点器...")
                    # 创建连接
                    conn = pymysql.connect(
                        host=host,
                        user=user,
                        password=password,
                        database=database,
                        port=port,
                        autocommit=True
                    )
                    
                    # 创建检查点器
                    self._checkpointer = PyMySQLSaver(conn=conn)
                    
                    # 应用字段名兼容性补丁
                    self._patch_pymysql_saver(self._checkpointer)
                    
                    # 初始化表结构
                    try:
                        self._checkpointer.setup()
                        logger.info("MySQL检查点器表结构设置成功")
                    except Exception as setup_error:
                        logger.warning(f"设置表结构失败，但将继续使用: {str(setup_error)}")
                    
                    logger.info("成功创建MySQL检查点器")
                    return
                except Exception as e:
                    logger.error(f"创建MySQL检查点器失败: {str(e)}")
                    
                    # 回退到内存检查点器
                    if MEMORY_SAVER_AVAILABLE:
                        logger.warning("回退到内存检查点器")
                        self._checkpointer = MemorySaver()
                        logger.info("成功回退到内存检查点器")
                        return
                    else:
                        logger.error("内存检查点器不可用")
                        self._checkpointer = None
                        return
                    
            elif MEMORY_SAVER_AVAILABLE:
                logger.warning("MySQL检查点器不可用，使用内存检查点器作为回退")
                self._checkpointer = MemorySaver()
                
            else:
                logger.error("没有可用的检查点器")
                self._checkpointer = None
                
        except Exception as e:
            logger.error(f"初始化MySQL检查点器失败: {str(e)}")
            
            # 回退到内存检查点器
            if MEMORY_SAVER_AVAILABLE:
                logger.warning("回退到内存检查点器")
                try:
                    self._checkpointer = MemorySaver()
                    logger.info("成功回退到内存检查点器")
                except Exception as fallback_error:
                    logger.error(f"回退到内存检查点器也失败: {str(fallback_error)}")
                    self._checkpointer = None
            else:
                self._checkpointer = None
    
    def _patch_pymysql_saver(self, checkpointer):
        """为PyMySQLSaver应用补丁，解决字段名兼容性问题"""
        import types
        
        logger.info("为PyMySQLSaver应用补丁...")
        
        # 补丁1: 修补setup方法 - 处理建表
        if hasattr(checkpointer, "setup"):
            original_setup = checkpointer.setup
            
            def patched_setup(self):
                """补丁版setup方法，处理表结构创建问题"""
                logger.info("应用setup方法补丁...")
                try:
                    # 检查连接
                    if not hasattr(self, "conn") or self.conn is None:
                        logger.error("连接对象不可用")
                        return False
                    
                    # 直接执行SQL创建表
                    with self.conn.cursor() as cursor:
                        # 检查表是否存在
                        cursor.execute("SHOW TABLES LIKE 'checkpoint_blobs'")
                        if cursor.fetchone():
                            logger.info("checkpoint_blobs表已存在")
                            
                            # 检查blob_data字段是否存在
                            cursor.execute("SHOW COLUMNS FROM checkpoint_blobs LIKE 'blob_data'")
                            if not cursor.fetchone():
                                logger.info("添加blob_data字段")
                                cursor.execute("ALTER TABLE checkpoint_blobs ADD COLUMN blob_data LONGBLOB")
                        else:
                            # 创建新表
                            logger.info("创建checkpoint_blobs表")
                            cursor.execute("""
                            CREATE TABLE IF NOT EXISTS checkpoint_blobs (
                                id VARCHAR(255) PRIMARY KEY,
                                thread_id VARCHAR(255) NOT NULL,
                                checkpoint_id VARCHAR(255) NOT NULL,
                                name VARCHAR(255) NOT NULL,
                                data LONGBLOB NOT NULL,
                                blob_data LONGBLOB,
                                checkpoint LONGBLOB,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            )
                            """)
                            cursor.execute("CREATE INDEX idx_thread_checkpoint ON checkpoint_blobs (thread_id, checkpoint_id)")
                    
                    return True
                except Exception as e:
                    logger.error(f"补丁版setup失败: {str(e)}")
                    # 尝试原始方法
                    try:
                        return original_setup()
                    except Exception as orig_error:
                        logger.error(f"原始setup也失败: {str(orig_error)}")
                        return False
            
            # 应用补丁
            checkpointer.setup = types.MethodType(patched_setup, checkpointer)
            logger.info("已应用setup方法补丁")
        
        # 补丁2: 修补put方法 - 处理保存
        if hasattr(checkpointer, "put"):
            original_put = checkpointer.put
            
            def patched_put(self, config, checkpoint, metadata=None, new_versions=None):
                """完全重写的补丁版put方法，直接使用SQL而不调用原始方法"""
                # 获取thread_id和checkpoint_id
                thread_id = None
                checkpoint_id = None
                
                try:
                    if isinstance(config, dict) and "configurable" in config:
                        configurable = config.get("configurable", {})
                        if isinstance(configurable, dict):
                            thread_id = configurable.get("thread_id")
                            checkpoint_id = configurable.get("checkpoint_id")
                    elif hasattr(config, "configurable"):
                        configurable = getattr(config, "configurable", {})
                        if hasattr(configurable, "thread_id"):
                            thread_id = configurable.thread_id
                        if hasattr(configurable, "checkpoint_id"):
                            checkpoint_id = configurable.checkpoint_id
                except Exception as e:
                    logger.warning(f"从配置中提取参数失败: {str(e)}")
                
                if not thread_id:
                    thread_id = "unknown_thread"
                    logger.warning(f"无法获取thread_id，使用默认值: {thread_id}")
                
                # 如果没有checkpoint_id，则生成一个
                if not checkpoint_id:
                    import hashlib
                    checkpoint_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
                    # 尝试更新配置
                    try:
                        if isinstance(config, dict) and isinstance(config.get("configurable"), dict):
                            config["configurable"]["checkpoint_id"] = checkpoint_id
                    except Exception:
                        pass
                
                logger.info(f"直接SQL方式保存检查点: thread_id={thread_id}, checkpoint_id={checkpoint_id}")
                
                # 检查连接
                if not hasattr(self, "conn") or self.conn is None:
                    logger.error("数据库连接不可用")
                    return False
                
                try:
                    # 查询表结构
                    with self.conn.cursor() as cursor:
                        cursor.execute("SHOW COLUMNS FROM checkpoint_blobs")
                        columns = [row[0] for row in cursor.fetchall()]
                    
                    # 序列化数据
                    import pickle
                    serialized_data = pickle.dumps(checkpoint)
                    
                    # 生成唯一ID
                    import uuid
                    import hashlib
                    unique_id = hashlib.md5(f"{thread_id}:{checkpoint_id}:{uuid.uuid4()}".encode()).hexdigest()
                    
                    # 准备字段和值
                    fields = ["id", "thread_id", "checkpoint_id", "name", "created_at"]
                    values = [unique_id, thread_id, checkpoint_id, "state", time.strftime('%Y-%m-%d %H:%M:%S')]
                    
                    # 添加数据字段
                    if "data" in columns:
                        fields.append("data")
                        values.append(serialized_data)
                    
                    if "blob_data" in columns:
                        fields.append("blob_data")
                        values.append(serialized_data)
                    
                    if "checkpoint" in columns:
                        fields.append("checkpoint")
                        values.append(serialized_data)
                    
                    # 添加元数据
                    if metadata and "metadata" in columns:
                        import json
                        fields.append("metadata")
                        values.append(json.dumps(metadata))
                    
                    # 构建SQL
                    fields_str = ", ".join(fields)
                    placeholders = ", ".join(["%s"] * len(fields))
                    
                    # 构建更新部分
                    update_parts = []
                    for field in ["data", "blob_data", "checkpoint"]:
                        if field in columns:
                            update_parts.append(f"{field} = VALUES({field})")
                    
                    update_str = ", ".join(update_parts)
                    if not update_str:
                        update_str = "id = VALUES(id)"  # 避免空的UPDATE部分
                    
                    # 执行SQL
                    with self.conn.cursor() as cursor:
                        sql = f"""
                        INSERT INTO checkpoint_blobs 
                        ({fields_str})
                        VALUES ({placeholders})
                        ON DUPLICATE KEY UPDATE
                        {update_str}
                        """
                        cursor.execute(sql, values)
                        self.conn.commit()
                    
                    logger.info(f"直接SQL保存成功: thread_id={thread_id}, checkpoint_id={checkpoint_id}")
                    return True
                    
                except Exception as e:
                    logger.error(f"SQL保存失败: {str(e)}")
                    return False
            
            # 应用补丁
            if hasattr(checkpointer, "put"):
                checkpointer.put = types.MethodType(patched_put, checkpointer)
                logger.info("已应用put方法补丁")
        
        # 补丁3: 修补get方法 - 处理获取
        if hasattr(checkpointer, "get"):
            original_get = checkpointer.get
            
            def patched_get(self, config):
                """完全重写的补丁版get方法，直接使用SQL而不调用原始方法"""
                # 直接从配置中获取thread_id
                thread_id = None
                checkpoint_id = None
                
                try:
                    if isinstance(config, dict) and "configurable" in config:
                        configurable = config.get("configurable", {})
                        if isinstance(configurable, dict):
                            thread_id = configurable.get("thread_id")
                            checkpoint_id = configurable.get("checkpoint_id")
                    elif hasattr(config, "configurable"):
                        configurable = getattr(config, "configurable", {})
                        if hasattr(configurable, "thread_id"):
                            thread_id = configurable.thread_id
                        if hasattr(configurable, "checkpoint_id"):
                            checkpoint_id = configurable.checkpoint_id
                except Exception as e:
                    logger.warning(f"从配置中提取参数失败: {str(e)}")
                
                if not thread_id:
                    thread_id = "unknown_thread"
                    logger.warning(f"无法获取thread_id，使用默认值: {thread_id}")
                
                logger.info(f"直接SQL方式获取检查点: thread_id={thread_id}, checkpoint_id={checkpoint_id or '最新'}")
                
                # 检查连接
                if not hasattr(self, "conn") or self.conn is None:
                    logger.error("数据库连接不可用")
                    return None
                
                try:
                    # 查询数据库
                    with self.conn.cursor() as cursor:
                        # 先检查表结构
                        cursor.execute("SHOW COLUMNS FROM checkpoint_blobs")
                        columns = [row[0] for row in cursor.fetchall()]
                        
                        # 确定要查询的字段
                        data_fields = []
                        for field in ["data", "blob_data", "checkpoint"]:
                            if field in columns:
                                data_fields.append(field)
                        
                        if not data_fields:
                            logger.error("表结构中没有有效的数据字段")
                            return None
                        
                        fields_str = ", ".join(data_fields)
                        
                        # 构建查询SQL
                        if checkpoint_id:
                            sql = f"SELECT {fields_str} FROM checkpoint_blobs WHERE thread_id = %s AND checkpoint_id = %s"
                            params = (thread_id, checkpoint_id)
                        else:
                            sql = f"SELECT {fields_str} FROM checkpoint_blobs WHERE thread_id = %s ORDER BY created_at DESC LIMIT 1"
                            params = (thread_id,)
                        
                        # 执行查询
                        cursor.execute(sql, params)
                        row = cursor.fetchone()
                        
                        if not row:
                            logger.warning(f"未找到检查点: thread_id={thread_id}, checkpoint_id={checkpoint_id}")
                            return None
                        
                        # 找到第一个非空数据
                        blob_data = None
                        for data in row:
                            if data:
                                blob_data = data
                                break
                        
                        if not blob_data:
                            logger.warning("检查点数据为空")
                            return None
                        
                        # 反序列化数据
                        try:
                            import pickle
                            try:
                                return pickle.loads(blob_data)
                            except Exception as pickle_error:
                                logger.warning(f"Pickle反序列化失败: {str(pickle_error)}")
                                
                                # 尝试JSON格式
                                import json
                                try:
                                    if isinstance(blob_data, bytes):
                                        return json.loads(blob_data.decode('utf-8'))
                                    else:
                                        return json.loads(blob_data)
                                except Exception as json_error:
                                    logger.warning(f"JSON反序列化失败: {str(json_error)}")
                                    
                                    # 最后一次尝试
                                    if hasattr(self, "serde"):
                                        return self.serde.deserialize(blob_data)
                                    
                                    raise ValueError("无法反序列化数据")
                        except Exception as e:
                            logger.error(f"反序列化失败: {str(e)}")
                            return None
                except Exception as e:
                    logger.error(f"SQL查询失败: {str(e)}")
                    return None
            
            # 应用补丁
            if hasattr(checkpointer, "get"):
                checkpointer.get = types.MethodType(patched_get, checkpointer)
                logger.info("已应用get方法补丁")
        
        # 补丁4: 修补list方法 - 处理列出检查点
        if hasattr(checkpointer, "list"):
            original_list = checkpointer.list
            
            def patched_list(self, config=None):
                """补丁版list方法，处理列出检查点问题"""
                logger.info(f"应用list方法补丁: {config}")
                
                # 直接使用直接查询方式获取检查点列表，避免API不兼容问题
                try:
                    # 检查连接
                    if not hasattr(self, "conn") or self.conn is None:
                        logger.error("连接对象不可用")
                        raise ValueError("连接对象不可用")
                    
                    thread_id = config.get("configurable", {}).get("thread_id") if config else None
                    
                    with self.conn.cursor() as cursor:
                        if thread_id and thread_id != "all_threads":
                            cursor.execute(
                                "SELECT DISTINCT thread_id, checkpoint_id FROM checkpoint_blobs WHERE thread_id = %s",
                                (thread_id,)
                            )
                        else:
                            cursor.execute("SELECT DISTINCT thread_id, checkpoint_id FROM checkpoint_blobs")
                        
                        results = cursor.fetchall()
                        
                        # 返回符合LangGraph格式的迭代器
                        def result_generator():
                            for row in results:
                                thread_id, checkpoint_id = row
                                config = {"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}}
                                metadata = {"created_at": datetime.now().isoformat()}
                                yield config, metadata
                        
                        logger.info(f"直接查询返回 {len(results)} 个检查点")
                        return result_generator()
                        
                except Exception as direct_error:
                    logger.error(f"直接查询失败: {str(direct_error)}")
                    
                    # 作为最后手段，尝试原始方法
                    try:
                        # 检查参数个数，适配不同版本的API
                        import inspect
                        sig = inspect.signature(original_list)
                        param_count = len(sig.parameters)
                        
                        try:
                            if param_count == 2:  # self + config
                                # 新版API格式：list(config)
                                return original_list(self, config)
                            elif param_count == 1:  # 只有self
                                # 旧版API格式：list()
                                return original_list(self)
                            else:
                                logger.warning(f"未知的API格式 (参数数: {param_count})，无法调用")
                                raise ValueError("未知API格式")
                        except TypeError as type_error:
                            error_str = str(type_error)
                            if "takes 2 positional arguments but 3 were given" in error_str:
                                # 特殊处理: BaseSyncMySQLSaver.list() takes 2 positional arguments but 3 were given
                                # 修正: 这可能是PyMySQLSaver继承了BaseSyncMySQLSaver但API不匹配的情况
                                try:
                                    # 尝试使用无参数调用
                                    return original_list(self)
                                except Exception as no_params_error:
                                    logger.warning(f"无参数调用也失败: {str(no_params_error)}")
                            # 继续向下执行，返回空列表
                    except Exception as original_error:
                        logger.warning(f"原始list方法最终失败: {str(original_error)}")
                    
                    # 返回空列表
                    def empty_generator():
                        yield from []
                    
                    return empty_generator()
            
            # 应用补丁
            if hasattr(checkpointer, "list"):
                checkpointer.list = types.MethodType(patched_list, checkpointer)
                logger.info("已应用list方法补丁")
        
        logger.info("PyMySQLSaver补丁应用完成")
    
    def get_checkpointer(self):
        """获取检查点器实例
        
        Returns:
            LangGraph检查点器实例
        """
        if self._checkpointer is None:
            logger.warning("检查点器未初始化，尝试重新初始化")
            self._init_checkpointer()
        
        return self._checkpointer
    
    def is_mysql_available(self) -> bool:
        """检查MySQL检查点器是否可用"""
        return (MYSQL_CHECKPOINT_AVAILABLE and 
                self._checkpointer is not None and 
                isinstance(self._checkpointer, PyMySQLSaver))
    
    def test_connection(self) -> bool:
        """测试MySQL连接是否正常
        
        Returns:
            连接测试结果
        """
        try:
            # 首先尝试获取检查点器
            checkpointer = self.get_checkpointer()
            if checkpointer is None:
                logger.error("检查点器不可用")
                return False
            
            # 如果是MySQL检查点器，使用两种方法测试连接
            if isinstance(checkpointer, PyMySQLSaver):
                # 方法1：获取PyMySQLSaver的底层连接并测试
                try:
                    # 尝试访问底层连接
                    if hasattr(checkpointer, "conn"):
                        conn = checkpointer.conn
                        if conn:
                            # 执行一个简单查询测试连接
                            try:
                                with conn.cursor() as cursor:
                                    cursor.execute("SELECT 1")
                                    result = cursor.fetchone()
                                    if result and result[0] == 1:
                                        logger.info("MySQL连接测试成功（直接查询）")
                                        return True
                            except Exception as query_error:
                                logger.warning(f"直接查询测试失败: {str(query_error)}")
                except Exception as conn_error:
                    logger.warning(f"获取底层连接失败: {str(conn_error)}")
                
                # 方法2：确保表结构存在
                try:
                    # 尝试设置表结构
                    checkpointer.setup()
                    logger.info("MySQL表结构设置成功")
                    return True
                except Exception as setup_error:
                    logger.error(f"设置MySQL表结构失败: {str(setup_error)}")
                    
                # 如果所有方法都失败，则连接测试失败
                return False
            else:
                # 对于其他类型的检查点器，假设连接正常
                logger.info("使用非MySQL检查点器，假设连接正常")
                return True
                
        except Exception as e:
            logger.error(f"MySQL检查点器连接测试失败: {str(e)}")
            return False
    
    def list_checkpoints(
        self, 
        thread_id: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """列出检查点
        
        Args:
            thread_id: 线程ID过滤
            limit: 限制返回数量
            
        Returns:
            检查点列表
        """
        try:
            checkpointer = self.get_checkpointer()
            if checkpointer is None:
                return []
            
            # 获取检查点迭代器 - 配置必须包含thread_id在configurable中
            config = {"configurable": {"thread_id": thread_id if thread_id else "all_threads"}}
            
            logger.info(f"列出检查点: thread_id={thread_id if thread_id else 'all'}, limit={limit}")
            
            # 尝试直接使用SQL查询 - 这是最可靠的方法
            if hasattr(checkpointer, "conn") and PyMySQLSaver and isinstance(checkpointer, PyMySQLSaver):
                logger.info("使用直接SQL方法列出检查点")
                
                # 构建SQL
                sql = "SELECT DISTINCT thread_id, checkpoint_id, created_at FROM checkpoint_blobs"
                params = []
                
                if thread_id:
                    sql += " WHERE thread_id = %s"
                    params.append(thread_id)
                
                sql += " ORDER BY created_at DESC"
                
                if limit:
                    sql += f" LIMIT {limit}"
                
                # 执行查询
                with checkpointer.conn.cursor() as cursor:
                    cursor.execute(sql, params)
                    rows = cursor.fetchall()
                    
                    checkpoints = []
                    for row in rows:
                        thread_id, checkpoint_id, created_at = row
                        checkpoints.append({
                            "config": {
                                "configurable": {
                                    "thread_id": thread_id,
                                    "checkpoint_id": checkpoint_id
                                }
                            },
                            "metadata": {
                                "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
                            },
                            "thread_id": thread_id,
                            "checkpoint_id": checkpoint_id,
                        })
                    
                    logger.info(f"通过SQL获取到 {len(checkpoints)} 个检查点")
                    return checkpoints
            
            # 如果直接SQL失败，尝试API方法
            # 获取检查点列表
            try:
                # 首先尝试使用现代版LangGraph API
                if hasattr(checkpointer, "list"):
                    try:
                        checkpoints_iter = checkpointer.list(config)
                        
                        # 转换为列表
                        checkpoints = []
                        for i, checkpoint_tuple in enumerate(checkpoints_iter):
                            if limit and i >= limit:
                                break
                                
                            config, metadata = checkpoint_tuple
                            checkpoints.append({
                                "config": config,
                                "metadata": metadata,
                                "thread_id": config.get("configurable", {}).get("thread_id"),
                                "checkpoint_id": config.get("configurable", {}).get("checkpoint_id"),
                            })
                        
                        logger.info(f"通过API列出检查点成功，共 {len(checkpoints)} 个")
                        return checkpoints
                    
                    except Exception as list_error:
                        logger.warning(f"使用list方法失败: {str(list_error)}")
                
                logger.warning("无法列出检查点，所有尝试都失败")
                return []
                    
            except (TypeError, AttributeError) as api_error:
                logger.warning(f"使用API列出检查点失败: {str(api_error)}")
                return []
            
        except Exception as e:
            logger.error(f"列出检查点失败: {str(e)}")
            return []
    
    def get_checkpoint(
        self, 
        thread_id: str, 
        checkpoint_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """获取特定检查点
        
        Args:
            thread_id: 线程ID
            checkpoint_id: 检查点ID，None表示最新的
            
        Returns:
            检查点数据
        """
        try:
            checkpointer = self.get_checkpointer()
            if checkpointer is None:
                return None
            
            # 创建正确的配置格式
            config = {"configurable": {"thread_id": thread_id}}
            if checkpoint_id:
                config["configurable"]["checkpoint_id"] = checkpoint_id
            
            logger.info(f"获取检查点: thread_id={thread_id}, checkpoint_id={checkpoint_id or '最新'}")
            
            # 首先尝试使用API方式获取
            try:
                # 检查是否有__call__方法(某些检查点器的特殊实现)
                if hasattr(checkpointer, "__call__"):
                    result = checkpointer(config)
                    if result:
                        logger.info(f"使用__call__方法获取检查点成功")
                        return {
                            "config": config,
                            "checkpoint": result
                        }
                
                # 检查是否有get方法
                if hasattr(checkpointer, "get"):
                    try:
                        checkpoint = checkpointer.get(config)
                        if checkpoint:
                            logger.info(f"使用get方法获取检查点成功")
                            return {
                                "config": config,
                                "checkpoint": checkpoint
                            }
                    except Exception as e:
                        logger.warning(f"get方法调用失败: {str(e)}")
                
                # 尝试直接SQL查询
                if hasattr(checkpointer, "conn") and PyMySQLSaver and isinstance(checkpointer, PyMySQLSaver):
                    logger.info("使用直接SQL方法获取检查点")
                    
                    # 构建SQL
                    sql = "SELECT id, data, blob_data FROM checkpoint_blobs WHERE thread_id = %s"
                    params = [thread_id]
                    
                    if checkpoint_id:
                        sql += " AND checkpoint_id = %s"
                        params.append(checkpoint_id)
                    else:
                        sql += " ORDER BY created_at DESC LIMIT 1"
                    
                    # 执行查询
                    with checkpointer.conn.cursor() as cursor:
                        cursor.execute(sql, params)
                        row = cursor.fetchone()
                        
                        if row:
                            checkpoint_id = row[0]
                            # 尝试使用data字段，如果为空则使用blob_data字段
                            blob_data = row[1] if row[1] else row[2]
                            
                            if blob_data:
                                # 尝试反序列化
                                try:
                                    import pickle
                                    checkpoint_data = pickle.loads(blob_data)
                                    logger.info(f"成功反序列化检查点: {checkpoint_id}")
                                    
                                    return {
                                        "config": config,
                                        "checkpoint": checkpoint_data
                                    }
                                except Exception as deserialize_error:
                                    logger.error(f"反序列化失败: {str(deserialize_error)}")
                            else:
                                logger.warning("检查点数据为空")
                        else:
                            logger.warning(f"未找到检查点: thread_id={thread_id}, checkpoint_id={checkpoint_id}")
                
                # 所有方法都失败
                logger.warning("无法获取检查点，尝试的所有方法都失败")
                return None
                
            except Exception as e:
                logger.error(f"获取检查点异常: {str(e)}")
                return None
                
        except Exception as e:
            logger.error(f"获取检查点失败: {str(e)}")
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
            保存是否成功
        """
        try:
            checkpointer = self.get_checkpointer()
            if checkpointer is None:
                return False
            
            # 添加时间戳
            if metadata is None:
                metadata = {}
            metadata["saved_at"] = datetime.now().isoformat()
            
            # 获取thread_id和checkpoint_id
            thread_id = config.get("configurable", {}).get("thread_id", "unknown")
            checkpoint_id = config.get("configurable", {}).get("checkpoint_id")
            if not checkpoint_id:
                import hashlib
                checkpoint_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
            
            logger.info(f"保存检查点: thread_id={thread_id}, checkpoint_id={checkpoint_id}")
            
            # 尝试使用现代API - 但有可能失败
            try:
                # 检查是否有__call__方法(某些检查点器的特殊实现)
                if hasattr(checkpointer, "__call__"):
                    checkpointer(config, checkpoint, metadata)
                    logger.info("使用__call__方法保存检查点成功")
                    return True
                
                # 检查是否有put方法
                if hasattr(checkpointer, "put"):
                    try:
                        # 尝试直接调用put方法
                        checkpointer.put(config, checkpoint, metadata)
                        logger.info("使用put方法保存检查点成功")
                        return True
                    except Exception as e:
                        logger.warning(f"调用put方法失败: {str(e)}")
                
                # 检查是否为PyMySQLSaver类型且有conn属性
                if hasattr(checkpointer, "conn") and PyMySQLSaver and isinstance(checkpointer, PyMySQLSaver):
                    logger.info("使用直接SQL方法保存检查点")
                    
                    # 序列化数据
                    import pickle
                    serialized_data = pickle.dumps(checkpoint)
                    
                    # 生成唯一ID
                    import hashlib
                    unique_id = hashlib.md5(f"{thread_id}:{checkpoint_id}".encode()).hexdigest()
                    
                    # 直接执行SQL插入
                    with checkpointer.conn.cursor() as cursor:
                        cursor.execute(
                            """
                            INSERT INTO checkpoint_blobs 
                            (id, thread_id, checkpoint_id, name, data, blob_data) 
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE 
                            data = VALUES(data),
                            blob_data = VALUES(blob_data)
                            """,
                            (unique_id, thread_id, checkpoint_id, "state", serialized_data, serialized_data)
                        )
                    
                    logger.info(f"直接SQL保存成功: thread_id={thread_id}, checkpoint_id={checkpoint_id}")
                    return True
                else:
                    logger.warning("无法识别的检查点器类型，无法保存")
                    return False
            
            except Exception as e:
                logger.error(f"保存检查点失败: {str(e)}")
                return False
            
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
            checkpoint_id: 检查点ID，None表示删除所有
            
        Returns:
            删除是否成功
        """
        try:
            checkpointer = self.get_checkpointer()
            if checkpointer is None:
                return False
            
            # 如果支持删除操作
            if hasattr(checkpointer, "delete"):
                config = {"configurable": {"thread_id": thread_id}}
                if checkpoint_id:
                    config["configurable"]["checkpoint_id"] = checkpoint_id
                
                try:
                    checkpointer.delete(config)
                    logger.info(f"删除检查点成功: {thread_id}/{checkpoint_id}")
                    return True
                except Exception as delete_error:
                    logger.error(f"删除检查点失败: {str(delete_error)}")
                    return False
            # 否则尝试直接操作数据库
            elif hasattr(checkpointer, "conn"):
                conn = checkpointer.conn
                with conn.cursor() as cursor:
                    if checkpoint_id:
                        cursor.execute(
                            "DELETE FROM checkpoint_blobs WHERE thread_id = %s AND checkpoint_id = %s",
                            (thread_id, checkpoint_id)
                        )
                    else:
                        cursor.execute(
                            "DELETE FROM checkpoint_blobs WHERE thread_id = %s",
                            (thread_id,)
                        )
                    conn.commit()
                    affected_rows = cursor.rowcount
                    logger.info(f"直接删除检查点成功: {thread_id}/{checkpoint_id}, 影响行数: {affected_rows}")
                    return affected_rows > 0
            else:
                logger.warning("检查点器不支持删除操作")
                return False
            
        except Exception as e:
            logger.error(f"删除检查点失败: {str(e)}")
            return False
    
    def cleanup_old_checkpoints(
        self, 
        days_old: int = 7,
        thread_id: Optional[str] = None
    ) -> int:
        """清理旧的检查点
        
        Args:
            days_old: 保留天数
            thread_id: 可选的线程ID过滤
            
        Returns:
            清理的检查点数量
        """
        try:
            # 对于MySQL检查点器，直接操作数据库
            if self.is_mysql_available() and hasattr(self._checkpointer, "conn"):
                logger.info(f"开始清理 {days_old} 天前的检查点")
                conn = self._checkpointer.conn
                with conn.cursor() as cursor:
                    # 构建SQL
                    sql = """
                    DELETE FROM checkpoint_blobs 
                    WHERE created_at < DATE_SUB(NOW(), INTERVAL %s DAY)
                    """
                    params = [days_old]
                    
                    if thread_id:
                        sql += " AND thread_id = %s"
                        params.append(thread_id)
                    
                    # 执行删除
                    cursor.execute(sql, params)
                    conn.commit()
                    cleaned_count = cursor.rowcount
                    
                    logger.info(f"清理完成，共清理 {cleaned_count} 个检查点")
                    return cleaned_count
            else:
                logger.warning("不支持清理非MySQL检查点器的旧检查点")
                return 0
            
        except Exception as e:
            logger.error(f"清理检查点失败: {str(e)}")
            return 0
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取检查点统计信息
        
        Returns:
            统计信息字典
        """
        try:
            stats = {
                "checkpointer_type": type(self._checkpointer).__name__ if self._checkpointer else "None",
                "mysql_available": self.is_mysql_available(),
                "connection_healthy": self.test_connection(),
                "total_checkpoints": 0,
                "unique_threads": 0,
            }
            
            # 获取检查点总数和线程数
            try:
                if self.is_mysql_available() and hasattr(self._checkpointer, "conn"):
                    conn = self._checkpointer.conn
                    with conn.cursor() as cursor:
                        # 获取总数
                        cursor.execute("SELECT COUNT(*) FROM checkpoint_blobs")
                        result = cursor.fetchone()
                        stats["total_checkpoints"] = result[0] if result else 0
                        
                        # 获取唯一线程数
                        cursor.execute("SELECT COUNT(DISTINCT thread_id) FROM checkpoint_blobs")
                        result = cursor.fetchone()
                        stats["unique_threads"] = result[0] if result else 0
                else:
                    checkpoints = self.list_checkpoints(limit=1000)  # 限制查询数量
                    stats["total_checkpoints"] = len(checkpoints)
                    
                    unique_threads = set()
                    for cp in checkpoints:
                        thread_id = cp.get("thread_id")
                        if thread_id:
                            unique_threads.add(thread_id)
                    stats["unique_threads"] = len(unique_threads)
                
            except Exception as e:
                logger.warning(f"获取检查点统计信息时出错: {str(e)}")
            
            return stats
            
        except Exception as e:
            logger.error(f"获取统计信息失败: {str(e)}")
            return {"error": str(e)}

# 全局MySQL检查点管理器实例
_mysql_checkpoint_manager = None

def get_mysql_checkpoint_manager(config: Optional[ConfigManager] = None) -> MySQLCheckpointManager:
    """获取全局MySQL检查点管理器实例
    
    Args:
        config: 可选的配置对象
        
    Returns:
        MySQL检查点管理器实例
    """
    global _mysql_checkpoint_manager
    
    if _mysql_checkpoint_manager is None:
        _mysql_checkpoint_manager = MySQLCheckpointManager(config)
    
    return _mysql_checkpoint_manager

def init_mysql_checkpoint(config: Optional[ConfigManager] = None) -> MySQLCheckpointManager:
    """初始化MySQL检查点管理器
    
    Args:
        config: 可选的配置对象
        
    Returns:
        初始化后的MySQL检查点管理器
    """
    manager = get_mysql_checkpoint_manager(config)
    
    # 测试连接
    if manager.test_connection():
        logger.info("MySQL检查点管理器初始化成功")
    else:
        logger.warning("MySQL检查点管理器初始化完成，但连接测试失败")
    
    return manager 