"""
基于PostgreSQL的会话持久化管理器

该模块提供了基于PostgreSQL的会话状态持久化功能，支持：
1. 会话状态的数据库存储
2. 会话状态的恢复和加载
3. 会话元数据管理
4. 自动清理过期会话
"""

import logging
import json
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import traceback

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    psycopg2 = None
    RealDictCursor = None
    PSYCOPG2_AVAILABLE = False

from app.core.config import ConfigManager

logger = logging.getLogger(__name__)

class PostgreSQLSessionManager:
    """PostgreSQL会话持久化管理器
    
    提供基于PostgreSQL的会话状态持久化功能，支持：
    - 会话状态的数据库存储
    - 会话状态的恢复和加载
    - 会话元数据管理
    - 自动清理过期会话
    """
    
    def __init__(self, config: Optional[ConfigManager] = None):
        """初始化PostgreSQL会话管理器
        
        Args:
            config: 系统配置对象
        """
        self.config = config or ConfigManager()
        self._postgres_config = self.config.get_postgresql_config()
        self._connection_string = self._build_connection_string()
        self._connection = None
        self._table_name = "isotope_sessions"
        
        # 初始化数据库连接和表结构
        self._init_database()
    
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
    
    def _init_database(self):
        """初始化数据库连接和表结构"""
        if not PSYCOPG2_AVAILABLE:
            raise ImportError("psycopg2 is required for PostgreSQL session management")
        
        try:
            # 建立数据库连接
            postgres_config = self._postgres_config
            self._connection = psycopg2.connect(
                host=postgres_config.get("host", "localhost"),
                user=postgres_config.get("user", "sweet"),
                password=postgres_config.get("password", ""),
                database=postgres_config.get("database", "isotope"),
                port=postgres_config.get("port", 5432),
                connect_timeout=10,
                client_encoding='utf8'
            )
            
            # 设置自动提交
            self._connection.autocommit = True
            
            logger.info("PostgreSQL会话管理器连接建立成功")
            
            # 创建会话表
            self._create_sessions_table()
            
        except Exception as e:
            logger.error(f"初始化PostgreSQL会话管理器失败: {str(e)}")
            raise
    
    def _create_sessions_table(self):
        """创建会话表结构"""
        try:
            with self._connection.cursor() as cursor:
                # 创建会话表
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self._table_name} (
                        session_id VARCHAR(255) PRIMARY KEY,
                        session_data JSONB NOT NULL,
                        metadata JSONB DEFAULT '{{}}',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP WITH TIME ZONE,
                        version INTEGER DEFAULT 1,
                        is_active BOOLEAN DEFAULT TRUE
                    )
                """)
                
                # 创建索引
                cursor.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{self._table_name}_last_updated 
                    ON {self._table_name}(last_updated)
                """)
                
                cursor.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{self._table_name}_created_at 
                    ON {self._table_name}(created_at)
                """)
                
                cursor.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{self._table_name}_is_active 
                    ON {self._table_name}(is_active)
                """)
                
                cursor.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{self._table_name}_expires_at 
                    ON {self._table_name}(expires_at)
                """)
                
                # 创建触发器更新 last_updated 字段
                cursor.execute(f"""
                    CREATE OR REPLACE FUNCTION update_{self._table_name}_timestamp()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        NEW.last_updated = CURRENT_TIMESTAMP;
                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql;
                """)
                
                cursor.execute(f"""
                    DROP TRIGGER IF EXISTS trigger_update_{self._table_name}_timestamp 
                    ON {self._table_name}
                """)
                
                cursor.execute(f"""
                    CREATE TRIGGER trigger_update_{self._table_name}_timestamp
                        BEFORE UPDATE ON {self._table_name}
                        FOR EACH ROW
                        EXECUTE FUNCTION update_{self._table_name}_timestamp()
                """)
                
                logger.info(f"会话表 {self._table_name} 创建成功")
                
        except Exception as e:
            logger.error(f"创建会话表失败: {str(e)}")
            raise
    
    def save_session(
        self, 
        session_id: str, 
        session_data: Dict[str, Any], 
        metadata: Optional[Dict[str, Any]] = None,
        expires_in_hours: Optional[int] = None
    ) -> bool:
        """保存会话状态到PostgreSQL
        
        Args:
            session_id: 会话ID
            session_data: 会话状态数据
            metadata: 会话元数据
            expires_in_hours: 会话过期时间（小时），None表示不过期
            
        Returns:
            是否保存成功
        """
        try:
            # 准备序列化的状态数据
            serializable_data = self._prepare_data_for_serialization(session_data)
            
            # 计算过期时间
            expires_at = None
            if expires_in_hours:
                expires_at = datetime.now() + timedelta(hours=expires_in_hours)
            
            with self._connection.cursor() as cursor:
                # 使用 UPSERT (INSERT ... ON CONFLICT) 语法
                cursor.execute(f"""
                    INSERT INTO {self._table_name} 
                    (session_id, session_data, metadata, expires_at, version)
                    VALUES (%s, %s, %s, %s, 1)
                    ON CONFLICT (session_id) 
                    DO UPDATE SET 
                        session_data = EXCLUDED.session_data,
                        metadata = EXCLUDED.metadata,
                        expires_at = EXCLUDED.expires_at,
                        version = {self._table_name}.version + 1,
                        is_active = TRUE
                """, (
                    session_id,
                    json.dumps(serializable_data, ensure_ascii=False),
                    json.dumps(metadata or {}, ensure_ascii=False),
                    expires_at
                ))
                
                logger.info(f"会话 {session_id} 已保存到PostgreSQL")
                return True
                
        except Exception as e:
            logger.error(f"保存会话 {session_id} 到PostgreSQL失败: {str(e)}")
            logger.error(f"错误详情: {traceback.format_exc()}")
            return False
    
    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """从PostgreSQL加载会话状态
        
        Args:
            session_id: 会话ID
            
        Returns:
            会话数据字典，如果不存在则返回None
        """
        try:
            with self._connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(f"""
                    SELECT session_id, session_data, metadata, created_at, last_updated, 
                           expires_at, version, is_active
                    FROM {self._table_name} 
                    WHERE session_id = %s AND is_active = TRUE
                """, (session_id,))
                
                row = cursor.fetchone()
                if not row:
                    logger.debug(f"会话 {session_id} 在PostgreSQL中不存在")
                    return None
                
                # 检查会话是否过期
                if row['expires_at']:
                    # 确保时区一致性
                    now = datetime.now()
                    expires_at = row['expires_at']
                    
                    # 如果expires_at是时区感知的，将now也转换为时区感知
                    if expires_at.tzinfo is not None and now.tzinfo is None:
                        from datetime import timezone
                        now = now.replace(tzinfo=timezone.utc)
                    # 如果expires_at是时区无感知的，将now也转换为时区无感知
                    elif expires_at.tzinfo is None and now.tzinfo is not None:
                        now = now.replace(tzinfo=None)
                    
                    if now > expires_at:
                        logger.warning(f"会话 {session_id} 已过期")
                        # 标记为非活跃
                        self._deactivate_session(session_id)
                        return None
                
                # 安全地转换时间格式，确保时区一致性
                def safe_datetime_to_isoformat(dt):
                    if dt is None:
                        return None
                    # 如果是时区感知的时间，转换为本地时间
                    if dt.tzinfo is not None:
                        dt = dt.replace(tzinfo=None)
                    return dt.isoformat()
                
                # 构建会话数据
                session_data = {
                    "session_id": row['session_id'],
                    "state": row['session_data'],
                    "metadata": row['metadata'],
                    "created_at": safe_datetime_to_isoformat(row['created_at']),
                    "last_updated": safe_datetime_to_isoformat(row['last_updated']),
                    "version": row['version']
                }
                
                logger.info(f"会话 {session_id} 已从PostgreSQL加载")
                return session_data
                
        except Exception as e:
            logger.error(f"从PostgreSQL加载会话 {session_id} 失败: {str(e)}")
            return None
    
    def list_sessions(
        self, 
        limit: Optional[int] = 50, 
        offset: Optional[int] = 0,
        include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """列出所有会话
        
        Args:
            limit: 返回数量限制
            offset: 偏移量
            include_inactive: 是否包含非活跃会话
            
        Returns:
            会话列表
        """
        try:
            with self._connection.cursor(cursor_factory=RealDictCursor) as cursor:
                # 构建查询条件
                where_clause = "WHERE is_active = TRUE" if not include_inactive else ""
                
                cursor.execute(f"""
                    SELECT session_id, metadata, created_at, last_updated, 
                           expires_at, version, is_active,
                           jsonb_array_length(session_data->'messages') as message_count
                    FROM {self._table_name} 
                    {where_clause}
                    ORDER BY last_updated DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
                
                # 安全地转换时间格式，确保时区一致性
                def safe_datetime_to_isoformat(dt):
                    if dt is None:
                        return None
                    # 如果是时区感知的时间，转换为本地时间
                    if dt.tzinfo is not None:
                        dt = dt.replace(tzinfo=None)
                    return dt.isoformat()
                
                sessions = []
                for row in cursor.fetchall():
                    session_info = {
                        "session_id": row['session_id'],
                        "metadata": row['metadata'],
                        "created_at": safe_datetime_to_isoformat(row['created_at']),
                        "last_updated": safe_datetime_to_isoformat(row['last_updated']),
                        "message_count": row['message_count'] or 0,
                        "version": row['version'],
                        "is_active": row['is_active'],
                        "status": "active" if row['is_active'] else "inactive"
                    }
                    
                    # 检查过期状态
                    if row['expires_at']:
                        session_info["expires_at"] = safe_datetime_to_isoformat(row['expires_at'])
                        
                        # 确保时区一致性
                        now = datetime.now()
                        expires_at = row['expires_at']
                        
                        # 如果expires_at是时区感知的，将now也转换为时区感知
                        if expires_at.tzinfo is not None and now.tzinfo is None:
                            from datetime import timezone
                            now = now.replace(tzinfo=timezone.utc)
                        # 如果expires_at是时区无感知的，将now也转换为时区无感知
                        elif expires_at.tzinfo is None and now.tzinfo is not None:
                            now = now.replace(tzinfo=None)
                        
                        if now > expires_at:
                            session_info["status"] = "expired"
                    
                    sessions.append(session_info)
                
                logger.info(f"从PostgreSQL获取到 {len(sessions)} 个会话")
                return sessions
                
        except Exception as e:
            logger.error(f"从PostgreSQL列出会话失败: {str(e)}")
            return []
    
    def delete_session(self, session_id: str, soft_delete: bool = True) -> bool:
        """删除会话
        
        Args:
            session_id: 会话ID
            soft_delete: 是否软删除（标记为非活跃）
            
        Returns:
            是否删除成功
        """
        try:
            with self._connection.cursor() as cursor:
                if soft_delete:
                    # 软删除：标记为非活跃
                    cursor.execute(f"""
                        UPDATE {self._table_name} 
                        SET is_active = FALSE 
                        WHERE session_id = %s
                    """, (session_id,))
                else:
                    # 硬删除：直接删除记录
                    cursor.execute(f"""
                        DELETE FROM {self._table_name} 
                        WHERE session_id = %s
                    """, (session_id,))
                
                affected_rows = cursor.rowcount
                if affected_rows > 0:
                    action = "软删除" if soft_delete else "硬删除"
                    logger.info(f"会话 {session_id} 已{action}")
                    return True
                else:
                    logger.warning(f"会话 {session_id} 不存在，无法删除")
                    return False
                    
        except Exception as e:
            logger.error(f"删除会话 {session_id} 失败: {str(e)}")
            return False
    
    def cleanup_expired_sessions(self) -> int:
        """清理过期会话
        
        Returns:
            清理的会话数量
        """
        try:
            with self._connection.cursor() as cursor:
                # 软删除过期会话
                cursor.execute(f"""
                    UPDATE {self._table_name} 
                    SET is_active = FALSE 
                    WHERE expires_at IS NOT NULL 
                    AND expires_at < CURRENT_TIMESTAMP 
                    AND is_active = TRUE
                """)
                
                cleaned_count = cursor.rowcount
                if cleaned_count > 0:
                    logger.info(f"清理了 {cleaned_count} 个过期会话")
                
                return cleaned_count
                
        except Exception as e:
            logger.error(f"清理过期会话失败: {str(e)}")
            return 0
    
    def get_session_statistics(self) -> Dict[str, Any]:
        """获取会话统计信息
        
        Returns:
            统计信息字典
        """
        try:
            with self._connection.cursor(cursor_factory=RealDictCursor) as cursor:
                # 获取基本统计
                cursor.execute(f"""
                    SELECT 
                        COUNT(*) as total_sessions,
                        COUNT(*) FILTER (WHERE is_active = TRUE) as active_sessions,
                        COUNT(*) FILTER (WHERE is_active = FALSE) as inactive_sessions,
                        COUNT(*) FILTER (WHERE expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP) as expired_sessions,
                        AVG(jsonb_array_length(session_data->'messages')) as avg_messages_per_session,
                        MAX(last_updated) as last_activity
                    FROM {self._table_name}
                """)
                
                stats = cursor.fetchone()
                
                # 获取每日创建统计
                cursor.execute(f"""
                    SELECT 
                        DATE(created_at) as date,
                        COUNT(*) as sessions_created
                    FROM {self._table_name}
                    WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
                    GROUP BY DATE(created_at)
                    ORDER BY date DESC
                """)
                
                daily_stats = cursor.fetchall()
                
                return {
                    "total_sessions": stats['total_sessions'],
                    "active_sessions": stats['active_sessions'],
                    "inactive_sessions": stats['inactive_sessions'],
                    "expired_sessions": stats['expired_sessions'],
                    "avg_messages_per_session": float(stats['avg_messages_per_session'] or 0),
                    "last_activity": stats['last_activity'].isoformat() if stats['last_activity'] else None,
                    "daily_creation_stats": [
                        {
                            "date": day['date'].isoformat(),
                            "sessions_created": day['sessions_created']
                        } for day in daily_stats
                    ]
                }
                
        except Exception as e:
            logger.error(f"获取会话统计信息失败: {str(e)}")
            return {}
    
    def restore_all_sessions(self) -> Dict[str, Any]:
        """恢复所有活跃会话到内存
        
        Returns:
            恢复结果统计
        """
        try:
            sessions = self.list_sessions(limit=None, include_inactive=False)
            
            restored_sessions = {}
            failed_count = 0
            
            for session_info in sessions:
                session_id = session_info['session_id']
                try:
                    session_data = self.load_session(session_id)
                    if session_data:
                        restored_sessions[session_id] = session_data
                    else:
                        failed_count += 1
                except Exception as e:
                    logger.error(f"恢复会话 {session_id} 失败: {str(e)}")
                    failed_count += 1
            
            result = {
                "success": True,
                "restored_count": len(restored_sessions),
                "failed_count": failed_count,
                "total_found": len(sessions),
                "sessions": restored_sessions
            }
            
            logger.info(f"从PostgreSQL恢复了 {len(restored_sessions)} 个会话，失败 {failed_count} 个")
            return result
            
        except Exception as e:
            logger.error(f"恢复所有会话失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "restored_count": 0,
                "failed_count": 0
            }
    
    def _deactivate_session(self, session_id: str):
        """标记会话为非活跃"""
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(f"""
                    UPDATE {self._table_name} 
                    SET is_active = FALSE 
                    WHERE session_id = %s
                """, (session_id,))
        except Exception as e:
            logger.error(f"标记会话 {session_id} 为非活跃失败: {str(e)}")
    
    def _prepare_data_for_serialization(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """准备数据进行序列化
        
        Args:
            data: 原始数据
            
        Returns:
            可序列化的数据
        """
        return self._make_serializable(data)
    
    def _make_serializable(self, obj):
        """递归地将对象转换为可序列化格式"""
        # 处理None
        if obj is None:
            return None
        
        # 处理基本类型
        if isinstance(obj, (str, int, float, bool)):
            return obj
        
        # 跳过不可序列化的已知类型
        from app.core.memory.store import MemoryStore
        if isinstance(obj, MemoryStore):
            return "<MemoryStore实例，已跳过序列化>"
        
        # 跳过新的记忆系统组件
        try:
            from app.core.memory.enhanced_memory_integration import EnhancedMemoryIntegration
            from app.core.memory.engine_adapter import MemoryAwareEngineAdapter
            if isinstance(obj, (EnhancedMemoryIntegration, MemoryAwareEngineAdapter)):
                return f"<{type(obj).__name__}实例，已跳过序列化>"
        except ImportError:
            pass
        
        # 处理LangChain消息对象
        try:
            from langchain_core.messages import BaseMessage
            if isinstance(obj, BaseMessage):
                msg_dict = {
                    "type": obj.type,
                    "content": self._make_serializable(obj.content)
                }
                # 添加额外属性
                if hasattr(obj, "name") and obj.name:
                    msg_dict["name"] = obj.name
                if hasattr(obj, "tool_calls") and obj.tool_calls:
                    msg_dict["tool_calls"] = obj.tool_calls
                if hasattr(obj, "additional_kwargs") and obj.additional_kwargs:
                    msg_dict["additional_kwargs"] = self._make_serializable(obj.additional_kwargs)
                return msg_dict
        except ImportError:
            pass
        
        # 处理列表
        if isinstance(obj, list):
            return [self._make_serializable(item) for item in obj]
        
        # 处理字典
        if isinstance(obj, dict):
            return {k: self._make_serializable(v) for k, v in obj.items()}
        
        # 处理其他类型
        try:
            # 尝试转换为字典
            if hasattr(obj, "__dict__"):
                return self._make_serializable(obj.__dict__)
            # 尝试转换为字符串
            return str(obj)
        except:
            # 如果无法序列化，则转换为字符串
            return f"<不可序列化的对象: {type(obj).__name__}>"
    
    def test_connection(self) -> bool:
        """测试数据库连接
        
        Returns:
            连接是否正常
        """
        try:
            with self._connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                return result is not None
        except Exception as e:
            logger.error(f"PostgreSQL连接测试失败: {str(e)}")
            return False
    
    def close(self):
        """关闭数据库连接"""
        if self._connection:
            try:
                self._connection.close()
                logger.info("PostgreSQL会话管理器连接已关闭")
            except Exception as e:
                logger.error(f"关闭PostgreSQL连接失败: {str(e)}")
    
    def __del__(self):
        """析构函数，确保关闭连接"""
        self.close()


# 全局实例管理
_postgres_session_manager = None

def get_postgres_session_manager(config: Optional[ConfigManager] = None) -> PostgreSQLSessionManager:
    """获取PostgreSQL会话管理器单例
    
    Args:
        config: 配置管理器实例
        
    Returns:
        PostgreSQL会话管理器实例
    """
    global _postgres_session_manager
    
    if _postgres_session_manager is None:
        _postgres_session_manager = PostgreSQLSessionManager(config)
    
    return _postgres_session_manager 