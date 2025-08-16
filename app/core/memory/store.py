"""
长期记忆存储管理模块 - 基于LangGraph的Store API实现
"""

import os
import time
import uuid
import json
import logging
from typing import List, Dict, Any, Optional, Tuple, Union
from pydantic import BaseModel, Field

# 配置日志
logger = logging.getLogger(__name__)

class MemoryItem(BaseModel):
    """记忆项类型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    type: str = "semantic"  # 'semantic', 'episodic', 'procedural'
    created_at: float = Field(default_factory=lambda: time.time())
    modified_at: float = Field(default_factory=lambda: time.time())
    metadata: Dict[str, Any] = Field(default_factory=dict)

# 为了与LangGraph API兼容的结果对象
class StoreResult:
    """存储结果包装器，模拟LangGraph的存储结果格式"""
    
    def __init__(self, value: Dict[str, Any]):
        self.value = value
    
    def __str__(self) -> str:
        return str(self.value)

# 实现自定义的JSON文件存储，作为备选
class JsonFileStore:
    """基于JSON文件的简单存储实现"""
    
    def __init__(self, root_path: str = "./memories"):
        """初始化JSON文件存储
        
        Args:
            root_path: 存储文件的根目录
        """
        self.root_path = root_path
        os.makedirs(root_path, exist_ok=True)
    
    def _get_namespace_dir(self, namespace: Tuple[str, ...]) -> str:
        """获取命名空间对应的目录路径"""
        # 使用命名空间的第一个元素作为目录名
        namespace_dir = os.path.join(self.root_path, namespace[0])
        os.makedirs(namespace_dir, exist_ok=True)
        return namespace_dir
    
    def _get_file_path(self, namespace: Tuple[str, ...], key: str) -> str:
        """获取键对应的文件路径"""
        namespace_dir = self._get_namespace_dir(namespace)
        return os.path.join(namespace_dir, f"{key}.json")
    
    def put(self, namespace: Tuple[str, ...], key: str, value: Dict) -> None:
        """存储键值对
        
        Args:
            namespace: 命名空间
            key: 键
            value: 值
        """
        file_path = self._get_file_path(namespace, key)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
    
    def get(self, namespace: Tuple[str, ...], key: str) -> List[StoreResult]:
        """获取键对应的值
        
        Args:
            namespace: 命名空间
            key: 键
            
        Returns:
            包含值的列表，每个值是一个StoreResult对象，符合LangGraph格式
        """
        file_path = self._get_file_path(namespace, key)
        if not os.path.exists(file_path):
            return []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                value = json.load(f)
                # 返回格式保持与LangGraph一致
                return [StoreResult(value)]
        except Exception as e:
            logger.error(f"读取文件 {file_path} 失败: {str(e)}")
            return []
    
    def delete(self, namespace: Tuple[str, ...], key: str) -> None:
        """删除键值对
        
        Args:
            namespace: 命名空间
            key: 键
        """
        file_path = self._get_file_path(namespace, key)
        if os.path.exists(file_path):
            os.remove(file_path)
    
    def list_keys(self, namespace: Tuple[str, ...]) -> List[str]:
        """列出命名空间下的所有键
        
        Args:
            namespace: 命名空间
            
        Returns:
            键列表
        """
        namespace_dir = self._get_namespace_dir(namespace)
        if not os.path.exists(namespace_dir):
            return []
            
        files = [f for f in os.listdir(namespace_dir) if f.endswith('.json')]
        return [os.path.splitext(f)[0] for f in files]  # 去掉.json后缀
    
    def search(self, namespace: Tuple[str, ...], query: str, limit: int = 5) -> List[StoreResult]:
        """搜索命名空间下匹配查询的值
        
        这是一个简单的实现，只检查内容中是否包含查询字符串
        
        Args:
            namespace: 命名空间
            query: 搜索查询
            limit: 结果数量限制
            
        Returns:
            匹配的值列表，使用StoreResult包装，符合LangGraph格式
        """
        keys = self.list_keys(namespace)
        results = []
        
        for key in keys:
            result = self.get(namespace, key)
            if result:
                # 检查内容是否包含查询字符串
                content = result[0].value.get("content", "")
                if query.lower() in content.lower():
                    results.append(result[0])
                    if len(results) >= limit:
                        break
        
        return results

class _SimpleDictStore:
    """简单的内存字典存储类，作为最后的回退选项"""
    
    def __init__(self):
        """初始化内存字典存储"""
        self.data = {}
        logger.info("使用简单内存字典存储")
    
    def put(self, namespace, key, value):
        """存储键值对"""
        namespace_str = self._namespace_to_str(namespace)
        if namespace_str not in self.data:
            self.data[namespace_str] = {}
        self.data[namespace_str][key] = value
    
    def get(self, namespace, key):
        """获取键值对"""
        namespace_str = self._namespace_to_str(namespace)
        if namespace_str not in self.data or key not in self.data[namespace_str]:
            return []
        # 包装为与LangGraph相同的格式
        return [StoreResult(self.data[namespace_str][key])]
    
    def delete(self, namespace, key):
        """删除键值对"""
        namespace_str = self._namespace_to_str(namespace)
        if namespace_str in self.data and key in self.data[namespace_str]:
            del self.data[namespace_str][key]
    
    def list_keys(self, namespace):
        """列出命名空间下的所有键"""
        namespace_str = self._namespace_to_str(namespace)
        if namespace_str not in self.data:
            return []
        return list(self.data[namespace_str].keys())
    
    def search(self, namespace, query, limit=5):
        """搜索匹配查询的值"""
        namespace_str = self._namespace_to_str(namespace)
        if namespace_str not in self.data:
            logger.info(f"命名空间 {namespace_str} 不存在，返回空结果")
            return []
        
        logger.info(f"搜索记忆: 命名空间={namespace_str}, 查询={query}, 限制={limit}")
        logger.info(f"数据存储中已有 {len(self.data[namespace_str])} 条记忆项")
        
        results = []
        for key, value in self.data[namespace_str].items():
            # 简单的文本匹配搜索
            if "content" in value and isinstance(value["content"], str):
                content = value["content"].lower()
                if query.lower() in content:
                    logger.info(f"找到匹配项: key={key}, content前30个字符: {value['content'][:30]}...")
                    results.append(StoreResult(value))
                    if len(results) >= limit:
                        logger.info(f"已达到结果限制 {limit}，停止搜索")
                        break
        
        logger.info(f"搜索完成，找到 {len(results)} 条结果")
        return results
    
    def _namespace_to_str(self, namespace):
        """将命名空间元组转换为字符串"""
        return "_".join(str(item) for item in namespace)

class MemoryStore:
    """长期记忆存储管理器"""
    
    def __init__(self, store_type: str = "file", connection_string: Optional[str] = None):
        """初始化长期记忆存储
        
        Args:
            store_type: 存储类型，可选 'file', 'postgres', 'mongodb'
            connection_string: 数据库连接字符串，仅在使用数据库时需要
        """
        self.store_type = store_type
        self.connection_string = connection_string
        self.store = _SimpleDictStore()  # 默认使用简单字典存储
        self._init_store()
    
    def _init_store(self):
        """初始化存储"""
        # 添加更多调试日志
        logger.info(f"初始化记忆存储，类型: {self.store_type}")
        
        # 根据存储类型初始化不同的存储后端
        if self.store_type == "memory":
            try:
                # 对于内存存储，我们使用自己实现的简单字典存储
                logger.info("使用内存字典存储作为记忆存储")
                self.store = _SimpleDictStore()
            except Exception as e:
                logger.error(f"初始化内存存储出错: {str(e)}")
                self.store = _SimpleDictStore()  # 确保有回退方案
        elif self.store_type == "file":
            try:
                # 对于文件存储，尝试使用JsonFileStore
                logger.info("使用JSON文件存储作为记忆存储")
                memories_dir = os.path.join("./memories", str(uuid.uuid4())[:8])
                os.makedirs(memories_dir, exist_ok=True)
                self.store = JsonFileStore(root_path=memories_dir)
            except Exception as e:
                logger.error(f"初始化文件存储出错: {str(e)}")
                self.store = _SimpleDictStore()  # 回退到内存存储
        # PostgreSQL存储
        elif self.store_type == "postgres":
            if not self.connection_string:
                # 尝试从配置管理器获取PostgreSQL配置
                try:
                    from app.core.config import get_config
                    config_manager = get_config()
                    pg_config = config_manager.get_postgresql_config()
                    self.connection_string = (
                        f"postgresql://{pg_config['user']}:{pg_config['password']}@"
                        f"{pg_config['host']}:{pg_config['port']}/{pg_config['database']}"
                    )
                    logger.info(f"从配置管理器获取PostgreSQL连接字符串成功")
                except Exception as e:
                    logger.warning(f"无法获取PostgreSQL配置: {e}")
                    
            if self.connection_string:
                logger.info(f"使用PostgreSQL存储: {self.connection_string}")
                # 目前使用内存存储代替，未实现PostgreSQL存储
                self.store = _SimpleDictStore()
            else:
                logger.warning("PostgreSQL需要连接字符串，使用内存存储代替")
                self.store = _SimpleDictStore()
        # MongoDB存储
        elif self.store_type == "mongodb":
            if self.connection_string:
                logger.info(f"使用MongoDB存储: {self.connection_string}")
                # 目前使用内存存储代替，未实现MongoDB存储
                self.store = _SimpleDictStore()
            else:
                logger.warning("MongoDB需要连接字符串，使用内存存储代替")
                self.store = _SimpleDictStore()
        else:
            logger.warning(f"未知的存储类型: {self.store_type}，使用内存存储")
            self.store = _SimpleDictStore()
            
        # 确保我们总是有一个可用的存储，并记录存储类型
        if not hasattr(self, 'store') or self.store is None:
            logger.error("存储初始化失败，使用默认内存存储")
            self.store = _SimpleDictStore()
        
        logger.info(f"记忆存储初始化完成，使用类型: {type(self.store).__name__}")
    
    def save_memory(self, user_id: str, memory_item: MemoryItem) -> str:
        """保存记忆项
        
        Args:
            user_id: 用户ID或命名空间
            memory_item: 要保存的记忆项
            
        Returns:
            记忆项ID
        """
        namespace = (user_id,)
        key = memory_item.id
        value = memory_item.model_dump()
        
        logger.info(f"保存记忆: 用户={user_id}, ID={key}, 类型={memory_item.type}, 内容前50字符: {memory_item.content[:50]}...")
        
        # 确保内容存在并且非空
        if not memory_item.content or not isinstance(memory_item.content, str) or memory_item.content.strip() == "":
            logger.warning(f"记忆内容为空或无效，设置默认值")
            value["content"] = "空记忆项"
        
        # 保存到存储
        self.store.put(namespace, key, value)
        
        # 验证是否成功保存
        verification = self.store.get(namespace, key)
        if verification:
            logger.info(f"记忆保存成功: ID={key}")
        else:
            logger.error(f"记忆保存失败: ID={key}")
        
        return key
    
    def get_memory(self, user_id: str, memory_id: str) -> Optional[MemoryItem]:
        """获取特定记忆项
        
        Args:
            user_id: 用户ID或命名空间
            memory_id: 记忆项ID
            
        Returns:
            记忆项或None
        """
        namespace = (user_id,)
        try:
            result = self.store.get(namespace, memory_id)
            if result:
                return MemoryItem(**result[0].value)
        except Exception as e:
            logger.error(f"获取记忆失败: {str(e)}")
        return None
    
    def search_memories(self, user_id: str, query: str, limit: int = 5) -> List[MemoryItem]:
        """搜索记忆
        
        Args:
            user_id: 用户ID或命名空间
            query: 搜索查询
            limit: 结果数量限制
            
        Returns:
            匹配的记忆项列表
        """
        namespace = (user_id,)
        logger.info(f"搜索记忆: 用户={user_id}, 查询={query}, 限制={limit}")
        
        # 记录当前存储的所有键
        all_keys = self.store.list_keys(namespace)
        logger.info(f"用户 {user_id} 当前有 {len(all_keys)} 条记忆项")
        
        try:
            results = self.store.search(namespace, query=query, limit=limit)
            memory_items = [MemoryItem(**item.value) for item in results]
            
            logger.info(f"搜索结果: 找到 {len(memory_items)} 条记忆项")
            for i, item in enumerate(memory_items):
                logger.info(f"  结果 {i+1}: ID={item.id}, 类型={item.type}, 内容前30字符: {item.content[:30]}...")
                
            return memory_items
        except Exception as e:
            logger.error(f"搜索记忆失败: {str(e)}")
            return []
    
    def list_memories(self, user_id: str, memory_type: Optional[str] = None, limit: int = 50) -> List[MemoryItem]:
        """列出用户的记忆项
        
        Args:
            user_id: 用户ID或命名空间
            memory_type: 可选的记忆类型过滤
            limit: 结果数量限制
            
        Returns:
            记忆项列表
        """
        namespace = (user_id,)
        try:
            # 获取所有键
            keys = self.store.list_keys(namespace)
            
            # 逐个检索记忆项
            memories = []
            for key in keys[:limit]:
                result = self.store.get(namespace, key)
                if result:
                    memory = MemoryItem(**result[0].value)
                    if memory_type is None or memory.type == memory_type:
                        memories.append(memory)
            
            # 按创建时间排序
            memories.sort(key=lambda x: x.created_at, reverse=True)
            return memories
        except Exception as e:
            logger.error(f"列出记忆失败: {str(e)}")
            return []
    
    def delete_memory(self, user_id: str, memory_id: str) -> bool:
        """删除特定记忆项
        
        Args:
            user_id: 用户ID或命名空间
            memory_id: 记忆项ID
            
        Returns:
            是否成功删除
        """
        namespace = (user_id,)
        try:
            self.store.delete(namespace, memory_id)
            return True
        except Exception as e:
            logger.error(f"删除记忆失败: {str(e)}")
            return False
    
    def clear_memories(self, user_id: str) -> bool:
        """清空用户的所有记忆
        
        Args:
            user_id: 用户ID或命名空间
            
        Returns:
            是否成功清空
        """
        namespace = (user_id,)
        try:
            # 获取所有键
            keys = self.store.list_keys(namespace)
            
            # 逐个删除
            for key in keys:
                self.store.delete(namespace, key)
            
            return True
        except Exception as e:
            logger.error(f"清空记忆失败: {str(e)}")
            return False 