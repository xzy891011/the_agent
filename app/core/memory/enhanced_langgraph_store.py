"""
增强的LangGraph记忆存储实现 - 支持智能体感知的记忆系统

本模块提供了完整的增强记忆存储功能，包括：
1. 智能体角色感知的记忆存储
2. 专业领域标签支持
3. 角色权限控制的记忆检索
4. 传统命名空间的兼容性
5. 自包含的基础存储实现
"""

import logging
import time
import uuid
import json
from typing import Dict, List, Tuple, Optional, Any, Union
from dataclasses import dataclass, asdict
from elasticsearch import Elasticsearch
from app.utils.silicon_embeddings import SiliconFlowEmbeddings

from app.core.memory.enhanced_memory_namespace import (
    EnhancedMemoryNamespace, 
    MemoryNamespaceManager, 
    AgentRole, 
    DomainTag, 
    MemoryType,
    get_namespace_manager
)

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """基础记忆条目"""
    id: str
    content: str
    memory_type: str
    namespace: Tuple[str, ...]
    created_at: float
    last_accessed: float
    access_count: int
    importance_score: float
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'id': self.id,
            'content': self.content,
            'memory_type': self.memory_type,
            'namespace': list(self.namespace),
            'created_at': self.created_at,
            'last_accessed': self.last_accessed,
            'access_count': self.access_count,
            'importance_score': self.importance_score,
            'metadata': self.metadata
        }


@dataclass
class EnhancedMemoryEntry(MemoryEntry):
    """增强的记忆条目，支持智能体角色和领域信息"""
    agent_role: Optional[str] = None
    domain: Optional[str] = None
    relevance_score: float = 1.0
    access_permissions: Optional[List[str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        base_dict = super().to_dict()
        base_dict.update({
            'agent_role': self.agent_role,
            'domain': self.domain,
            'relevance_score': self.relevance_score,
            'access_permissions': self.access_permissions or []
        })
        return base_dict
    
    @classmethod
    def from_memory_entry(cls, memory_entry: MemoryEntry, 
                         agent_role: Optional[str] = None,
                         domain: Optional[str] = None) -> 'EnhancedMemoryEntry':
        """从基础记忆条目创建增强记忆条目"""
        return cls(
            id=memory_entry.id,
            content=memory_entry.content,
            memory_type=memory_entry.memory_type,
            namespace=memory_entry.namespace,
            created_at=memory_entry.created_at,
            last_accessed=memory_entry.last_accessed,
            access_count=memory_entry.access_count,
            importance_score=memory_entry.importance_score,
            metadata=memory_entry.metadata,
            agent_role=agent_role,
            domain=domain
        )


class ElasticsearchVectorStore:
    """Elasticsearch向量存储实现"""
    
    def __init__(self, es_config: Dict[str, Any], index_name: str = "isotope-memory-vectors"):
        """初始化Elasticsearch向量存储"""
        self.es_config = es_config
        self.index_name = index_name
        self.es = None
        self.encoder = None
        
        try:
            # 初始化Elasticsearch客户端
            username = es_config.get("username")
            password = es_config.get("password")
            
            # 构建连接参数
            es_params = {
                "hosts": es_config.get("hosts", ["http://localhost:9200"]),
                "verify_certs": es_config.get("verify_certs", False),
                "request_timeout": 30
            }
            
            # 如果有用户名和密码，使用 basic_auth
            if username and password:
                es_params["basic_auth"] = (username, password)
            
            self.es = Elasticsearch(**es_params)
            
            # 初始化文本编码器
            self.encoder = SiliconFlowEmbeddings(model="BAAI/bge-m3")
            
            # 创建索引
            self._create_index()
            
            logger.info(f"Elasticsearch向量存储初始化成功，索引: {index_name}")
            
        except Exception as e:
            logger.error(f"Elasticsearch向量存储初始化失败: {e}")
            self.es = None
            self.encoder = None
    
    def _format_timestamp(self, timestamp: float) -> str:
        """将Unix时间戳转换为ISO 8601格式"""
        from datetime import datetime
        try:
            # 转换为datetime对象
            dt = datetime.fromtimestamp(timestamp)
            # 转换为ISO 8601格式
            return dt.isoformat()
        except Exception as e:
            logger.error(f"时间戳格式化失败: {e}")
            # 返回当前时间的ISO格式作为后备
            return datetime.now().isoformat()
    
    def _create_index(self):
        """创建Elasticsearch索引"""
        if not self.es:
            return
            
        index_mapping = {
            "mappings": {
                "properties": {
                    "content": {"type": "text"},
                    "vector": {"type": "dense_vector", "dims": 1024},
                    "memory_type": {"type": "keyword"},
                    "namespace": {"type": "keyword"},
                    "agent_role": {"type": "keyword"},
                    "domain": {"type": "keyword"},
                    "importance_score": {"type": "float"},
                    "created_at": {"type": "date"},
                    "metadata": {"type": "object"}
                }
            }
        }
        
        try:
            if not self.es.indices.exists(index=self.index_name):
                self.es.indices.create(index=self.index_name, body=index_mapping)
                logger.info(f"创建Elasticsearch索引: {self.index_name}")
        except Exception as e:
            logger.error(f"创建Elasticsearch索引失败: {e}")
    
    def add_memory(self, memory: EnhancedMemoryEntry) -> bool:
        """添加记忆到向量存储"""
        if not self.es or not self.encoder:
            return False
            
        try:
            # 生成向量
            vector = self.encoder.embed_query(memory.content)
            
            # 构建文档
            doc = {
                "content": memory.content,
                "vector": vector,
                "memory_type": memory.memory_type,
                "namespace": "/".join(memory.namespace),
                "agent_role": memory.agent_role,
                "domain": memory.domain,
                "importance_score": memory.importance_score,
                "created_at": self._format_timestamp(memory.created_at),
                "metadata": memory.metadata
            }
            
            # 存储到Elasticsearch
            self.es.index(index=self.index_name, id=memory.id, body=doc)
            return True
            
        except Exception as e:
            logger.error(f"向量存储添加记忆失败: {e}")
            return False
    
    def search_similar(self, query: str, agent_role: Optional[str] = None, 
                      limit: int = 10) -> List[Dict[str, Any]]:
        """搜索相似记忆"""
        if not self.es or not self.encoder:
            return []
            
        try:
            # 生成查询向量
            query_vector = self.encoder.embed_query(query)
            
            # 构建搜索查询
            search_query = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "script_score": {
                                    "query": {"match_all": {}},
                                    "script": {
                                        "source": "cosineSimilarity(params.query_vector, 'vector') + 1.0",
                                        "params": {"query_vector": query_vector}
                                    }
                                }
                            }
                        ]
                    }
                },
                "size": limit
            }
            
            # 添加智能体角色过滤
            if agent_role:
                search_query["query"]["bool"]["filter"] = [
                    {"term": {"agent_role": agent_role}}
                ]
            
            # 执行搜索
            response = self.es.search(index=self.index_name, body=search_query)
            
            # 处理结果
            results = []
            for hit in response["hits"]["hits"]:
                result = {
                    "id": hit["_id"],
                    "score": hit["_score"],
                    "content": hit["_source"]["content"],
                    "memory_type": hit["_source"]["memory_type"],
                    "namespace": hit["_source"]["namespace"].split("/"),
                    "agent_role": hit["_source"]["agent_role"],
                    "domain": hit["_source"]["domain"],
                    "importance_score": hit["_source"]["importance_score"],
                    "created_at": hit["_source"]["created_at"],
                    "metadata": hit["_source"]["metadata"]
                }
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"向量搜索失败: {e}")
            return []


class LangGraphMemoryStore:
    """基础LangGraph记忆存储实现"""
    
    def __init__(self, es_config: Dict[str, Any], index_name: str = "isotope-memory-store"):
        """初始化LangGraph记忆存储"""
        self.es_config = es_config
        self.index_name = index_name
        self.vector_store = ElasticsearchVectorStore(es_config, f"{index_name}-vectors")
        self.memories: Dict[str, Dict[str, Any]] = {}
        
        logger.info("LangGraph记忆存储初始化完成")
    
    def put(self, namespace: Tuple[str, ...], key: str, value: Dict[str, Any]) -> None:
        """存储记忆"""
        namespace_str = "/".join(namespace)
        memory_key = f"{namespace_str}/{key}"
        
        # 添加时间戳
        if 'created_at' not in value:
            value['created_at'] = time.time()
        if 'last_accessed' not in value:
            value['last_accessed'] = time.time()
        if 'access_count' not in value:
            value['access_count'] = 0
        
        # 如果有向量存储，也保存到向量存储
        if hasattr(self, 'vector_store') and self.vector_store:
            try:
                # 创建增强记忆条目
                enhanced_memory = EnhancedMemoryEntry(
                    id=value.get('id', key),
                    content=value.get('content', ''),
                    memory_type=value.get('memory_type', 'semantic'),
                    namespace=namespace,
                    created_at=value['created_at'],
                    last_accessed=value['last_accessed'],
                    access_count=value['access_count'],
                    importance_score=value.get('importance_score', 1.0),
                    metadata=value.get('metadata', {}),
                    agent_role=value.get('agent_role', None),
                    domain=value.get('domain', None)
                )
                self.vector_store.add_memory(enhanced_memory)
            except Exception as e:
                logger.warning(f"添加记忆到向量存储失败: {e}")
        
        # 存储到内存
        self.memories[memory_key] = value
        
        logger.debug(f"存储记忆: {memory_key}")
    
    def get(self, namespace: Tuple[str, ...], key: str) -> List[Dict[str, Any]]:
        """获取记忆"""
        namespace_str = "/".join(namespace)
        memory_key = f"{namespace_str}/{key}"
        
        if memory_key in self.memories:
            memory = self.memories[memory_key]
            # 更新访问信息
            memory['last_accessed'] = time.time()
            memory['access_count'] = memory.get('access_count', 0) + 1
            
            return [{"key": key, "value": memory, "namespace": list(namespace)}]
        
        return []
    
    def search(self, namespace_prefix: Tuple[str, ...], query: str, 
               limit: int = 10) -> List[Dict[str, Any]]:
        """搜索记忆"""
        namespace_prefix_str = "/".join(namespace_prefix)
        results = []
        
        # 简单的文本匹配搜索
        for memory_key, memory_value in self.memories.items():
            if memory_key.startswith(namespace_prefix_str):
                content = memory_value.get('content', '')
                if query.lower() in content.lower():
                    # 解析命名空间和键
                    parts = memory_key.split('/')
                    key = parts[-1]
                    namespace = parts[:-1]
                    
                    results.append({
                        "key": key,
                        "value": memory_value,
                        "namespace": namespace
                    })
                    
                    if len(results) >= limit:
                        break
        
        return results
    
    def delete(self, namespace: Tuple[str, ...], key: str) -> None:
        """删除记忆"""
        namespace_str = "/".join(namespace)
        memory_key = f"{namespace_str}/{key}"
        
        if memory_key in self.memories:
            del self.memories[memory_key]
            logger.debug(f"删除记忆: {memory_key}")


class EnhancedLangGraphMemoryStore(LangGraphMemoryStore):
    """增强的LangGraph记忆存储，支持智能体感知的记忆管理"""
    
    def __init__(self, es_config: Dict[str, Any], index_name: str = "isotope-enhanced-memory-vectors"):
        """初始化增强记忆存储"""
        super().__init__(es_config, index_name)
        self.namespace_manager = get_namespace_manager()
        self.enhanced_memories: Dict[str, EnhancedMemoryEntry] = {}
        
        logger.info("增强LangGraph记忆存储初始化完成")
    
    def put_agent_memory(
        self,
        user_id: str,
        agent_role: str,
        content: str,
        memory_type: str = "semantic",
        domain_hint: Optional[str] = None,
        importance_score: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """为特定智能体存储记忆"""
        # 创建增强命名空间
        namespace = self.namespace_manager.create_namespace(
            user_id=user_id,
            agent_role=agent_role,
            memory_type=memory_type,
            content=content,
            domain_hint=domain_hint
        )
        
        # 生成记忆ID
        memory_id = str(uuid.uuid4())
        
        # 构建记忆值
        value = {
            'content': content,
            'memory_type': memory_type,
            'importance_score': importance_score,
            'metadata': metadata or {},
            'agent_role': agent_role,
            'domain': namespace.domain.value
        }
        
        # 存储记忆
        self.put(namespace.to_tuple(), memory_id, value)
        
        # 创建增强记忆条目
        enhanced_memory = EnhancedMemoryEntry(
            id=memory_id,
            content=content,
            memory_type=memory_type,
            namespace=namespace.to_tuple(),
            created_at=time.time(),
            last_accessed=time.time(),
            access_count=0,
            importance_score=importance_score,
            metadata=metadata or {},
            agent_role=agent_role,
            domain=namespace.domain.value
        )
        
        # 存储到增强缓存
        memory_key = f"{namespace.to_string()}/{memory_id}"
        self.enhanced_memories[memory_key] = enhanced_memory
        
        # 添加到向量存储
        self.vector_store.add_memory(enhanced_memory)
        
        logger.info(f"智能体记忆存储成功: {agent_role} -> {namespace.domain.value} -> {memory_id}")
        return memory_id
    
    def search_agent_memories(
        self,
        user_id: str,
        requesting_agent_role: str,
        query: str,
        memory_type: Optional[str] = None,
        limit: int = 10,
        include_shared: bool = True
    ) -> List[EnhancedMemoryEntry]:
        """搜索智能体相关的记忆"""
        # 获取可访问的命名空间
        accessible_namespaces = self.namespace_manager.get_accessible_namespaces(
            requesting_agent_role=requesting_agent_role,
            user_id=user_id,
            memory_type=memory_type
        )
        
        all_results = []
        
        # 在每个可访问的命名空间中搜索
        for namespace in accessible_namespaces:
            try:
                # 使用父类的搜索方法
                results = self.search(
                    namespace_prefix=namespace.to_tuple(),
                    query=query,
                    limit=limit
                )
                
                # 转换为增强记忆条目
                for result in results:
                    if 'value' in result:
                        value = result['value']
                        enhanced_memory = EnhancedMemoryEntry(
                            id=result['key'],
                            content=value.get('content', ''),
                            memory_type=value.get('memory_type', 'semantic'),
                            namespace=tuple(result['namespace']),
                            created_at=value.get('created_at', time.time()),
                            last_accessed=value.get('last_accessed', time.time()),
                            access_count=value.get('access_count', 0),
                            importance_score=value.get('importance_score', 1.0),
                            metadata=value.get('metadata', {}),
                            agent_role=value.get('agent_role'),
                            domain=value.get('domain')
                        )
                        
                        # 计算相关性分数
                        enhanced_memory.relevance_score = self._calculate_relevance_score(
                            enhanced_memory, query, requesting_agent_role
                        )
                        
                        all_results.append(enhanced_memory)
                        
            except Exception as e:
                logger.error(f"搜索命名空间 {namespace.to_string()} 失败: {e}")
        
        # 按相关性和重要性排序
        all_results.sort(
            key=lambda x: (x.relevance_score * x.importance_score), 
            reverse=True
        )
        
        return all_results[:limit]
    
    def get_agent_memory_context(
        self,
        user_id: str,
        agent_role: str,
        query: str,
        max_semantic: int = 3,
        max_episodic: int = 2,
        max_procedural: int = 2
    ) -> Dict[str, List[EnhancedMemoryEntry]]:
        """获取智能体记忆上下文"""
        context = {
            "semantic": [],
            "episodic": [],
            "procedural": []
        }
        
        # 搜索不同类型的记忆
        for memory_type in context.keys():
            max_count = locals()[f"max_{memory_type}"]
            if max_count > 0:
                memories = self.search_agent_memories(
                    user_id=user_id,
                    requesting_agent_role=agent_role,
                    query=query,
                    memory_type=memory_type,
                    limit=max_count
                )
                context[memory_type] = memories
        
        return context
    
    def _calculate_relevance_score(
        self,
        memory: EnhancedMemoryEntry,
        query: str,
        requesting_agent_role: str
    ) -> float:
        """计算记忆相关性分数"""
        score = 0.0
        
        # 基础文本相似性
        if query.lower() in memory.content.lower():
            score += 0.5
        
        # 智能体角色匹配
        if memory.agent_role == requesting_agent_role:
            score += 0.3
        elif memory.agent_role in ["shared", "system"]:
            score += 0.2
        
        # 重要性分数
        score += memory.importance_score * 0.2
        
        # 时间衰减
        age_days = (time.time() - memory.created_at) / (24 * 3600)
        time_decay = max(0.1, 1.0 - age_days / 30.0)  # 30天衰减
        score *= time_decay
        
        return min(1.0, score)
    
    def migrate_legacy_memories(self, user_id: str) -> int:
        """迁移传统记忆到增强格式"""
        migrated_count = 0
        
        try:
            # 搜索传统命名空间的记忆
            legacy_namespace = (user_id,)
            legacy_results = self.search(legacy_namespace, "", limit=1000)
            
            for result in legacy_results:
                try:
                    # 转换为增强记忆
                    value = result['value']
                    enhanced_memory = EnhancedMemoryEntry(
                        id=result['key'],
                        content=value.get('content', ''),
                        memory_type=value.get('memory_type', 'semantic'),
                        namespace=tuple(result['namespace']),
                        created_at=value.get('created_at', time.time()),
                        last_accessed=value.get('last_accessed', time.time()),
                        access_count=value.get('access_count', 0),
                        importance_score=value.get('importance_score', 1.0),
                        metadata=value.get('metadata', {}),
                        agent_role="general",  # 默认角色
                        domain="general"       # 默认领域
                    )
                    
                    # 存储增强记忆
                    memory_key = f"migrated/{enhanced_memory.id}"
                    self.enhanced_memories[memory_key] = enhanced_memory
                    
                    migrated_count += 1
                    
                except Exception as e:
                    logger.error(f"迁移记忆失败: {e}")
            
            logger.info(f"成功迁移 {migrated_count} 条传统记忆")
            
        except Exception as e:
            logger.error(f"记忆迁移过程失败: {e}")
        
        return migrated_count
    
    def get_agent_memory_statistics(self, user_id: str, agent_role: str) -> Dict[str, Any]:
        """获取智能体记忆统计信息"""
        stats = {
            "total_memories": 0,
            "by_type": {"semantic": 0, "episodic": 0, "procedural": 0},
            "by_domain": {},
            "average_importance": 0.0,
            "most_recent": None,
            "oldest": None
        }
        
        # 统计增强记忆
        agent_memories = []
        for memory in self.enhanced_memories.values():
            if (memory.agent_role == agent_role and 
                memory.namespace[0] == user_id):
                agent_memories.append(memory)
        
        if agent_memories:
            stats["total_memories"] = len(agent_memories)
            
            # 按类型统计
            for memory in agent_memories:
                stats["by_type"][memory.memory_type] += 1
            
            # 按领域统计
            for memory in agent_memories:
                domain = memory.domain or "unknown"
                stats["by_domain"][domain] = stats["by_domain"].get(domain, 0) + 1
            
            # 平均重要性
            stats["average_importance"] = sum(m.importance_score for m in agent_memories) / len(agent_memories)
            
            # 最新和最旧
            sorted_memories = sorted(agent_memories, key=lambda x: x.created_at)
            stats["oldest"] = sorted_memories[0].created_at
            stats["most_recent"] = sorted_memories[-1].created_at
        
        return stats
    
    def cleanup_agent_memories(
        self,
        user_id: str,
        agent_role: str,
        min_importance: float = 0.1,
        max_age_days: int = 30
    ) -> int:
        """清理智能体记忆"""
        cleaned_count = 0
        current_time = time.time()
        max_age_seconds = max_age_days * 24 * 3600
        
        # 收集要删除的记忆
        to_delete = []
        for memory_key, memory in self.enhanced_memories.items():
            if (memory.agent_role == agent_role and 
                memory.namespace[0] == user_id):
                
                # 检查重要性和年龄
                age = current_time - memory.created_at
                if (memory.importance_score < min_importance or 
                    age > max_age_seconds):
                    to_delete.append(memory_key)
        
        # 删除记忆
        for memory_key in to_delete:
            del self.enhanced_memories[memory_key]
            cleaned_count += 1
        
        logger.info(f"清理了 {cleaned_count} 条智能体记忆")
        return cleaned_count


def create_enhanced_langgraph_store(es_config: Dict[str, Any]) -> EnhancedLangGraphMemoryStore:
    """创建增强LangGraph记忆存储实例"""
    return EnhancedLangGraphMemoryStore(es_config) 