"""
增强记忆集成模块 - 支持智能体感知的记忆系统

本模块扩展了原有的MemoryIntegration，增加了：
1. 智能体角色感知的记忆提取和增强
2. 智能体特定的记忆筛选机制
3. 基于角色的记忆访问控制
4. 动态记忆相关性评分
"""

import logging
import time
import uuid
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass

from app.core.memory.enhanced_langgraph_store import (
    EnhancedLangGraphMemoryStore, 
    EnhancedMemoryEntry,
    create_enhanced_langgraph_store
)
from app.core.memory.enhanced_memory_namespace import (
    get_namespace_manager,
    AgentRole,
    DomainTag,
    MemoryType
)
from app.core.state import IsotopeSystemState
from app.core.config import ConfigManager

logger = logging.getLogger(__name__)


@dataclass
class AgentMemoryContext:
    """智能体记忆上下文 - 为特定智能体提供相关记忆信息"""
    agent_role: str
    semantic_memories: List[EnhancedMemoryEntry]
    episodic_memories: List[EnhancedMemoryEntry]
    procedural_memories: List[EnhancedMemoryEntry]
    memory_summary: str
    confidence_score: float
    access_permissions: List[str]
    domain_coverage: List[str]  # 涵盖的专业领域
    relevance_scores: Dict[str, float]  # 各类记忆的相关性分数


class EnhancedMemoryIntegration:
    """增强记忆集成 - 支持智能体感知的记忆管理"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化增强记忆集成"""
        self.config = config or {}
        
        # 获取Elasticsearch配置
        if isinstance(config, ConfigManager):
            es_config = config.get_es_config()
        else:
            # 从字典配置中获取ES配置，支持多种键名
            es_config = config.get('es', config.get('elasticsearch', {}))
            
            # 如果仍然为空，使用默认配置
            if not es_config:
                es_config = {
                    "hosts": ["http://localhost:9200"],
                    "username": "elastic", 
                    "password": "",
                    "verify_certs": False
                }
        
        # 创建增强记忆存储
        self.enhanced_store = create_enhanced_langgraph_store(es_config)
        self.namespace_manager = get_namespace_manager()
        
        # 记忆提取配置
        self.extraction_config = {
            'min_content_length': 10,
            'max_importance_threshold': 0.9,
            'auto_classify_domain': True,
            'enable_cross_agent_sharing': True
        }
        
        logger.info("增强记忆集成初始化完成")
    
    def extract_memories_from_state(
        self, 
        state: IsotopeSystemState, 
        agent_role: str,
        session_id: Optional[str] = None
    ) -> List[str]:
        """从系统状态中提取智能体特定的记忆"""
        try:
            extracted_memories = []
            
            # 获取用户信息
            user_id = state.get('metadata', {}).get('user_id', 'default_user')
            if not session_id:
                session_id = state.get('metadata', {}).get('session_id', str(uuid.uuid4()))
            
            # 从消息历史中提取记忆
            messages = state.get('messages', [])
            for i, msg in enumerate(messages):
                content = self._extract_content_from_message(msg)
                if not content or len(content) < self.extraction_config['min_content_length']:
                    continue
                
                # 分析内容类型并确定记忆类型
                memory_type, importance = self._analyze_content_for_memory(content, agent_role)
                if memory_type and importance > 0.3:  # 只保存重要的记忆
                    
                    # 推断专业领域
                    domain_hint = self._infer_domain_from_content(content, agent_role)
                    
                    # 保存智能体特定的记忆
                    memory_id = self.enhanced_store.put_agent_memory(
                        user_id=user_id,
                        agent_role=agent_role,
                        content=content,
                        memory_type=memory_type,
                        domain_hint=domain_hint,
                        importance_score=importance,
                        metadata={
                            'session_id': session_id,
                            'message_index': i,
                            'extracted_at': time.time(),
                            'source': 'message_history'
                        }
                    )
                    
                    if memory_id:
                        extracted_memories.append(memory_id)
            
            # 从工具执行结果中提取记忆
            tool_results = state.get('tool_results', [])
            for tool_result in tool_results:
                content = self._extract_content_from_tool_result(tool_result)
                if content:
                    # 工具结果通常是程序性记忆
                    tool_name = tool_result.get('tool_name', 'unknown')
                    
                    # 推断工具相关的领域
                    domain_hint = self._infer_domain_from_tool(tool_name, agent_role)
                    
                    memory_id = self.enhanced_store.put_agent_memory(
                        user_id=user_id,
                        agent_role=agent_role,
                        content=content,
                        memory_type='procedural',
                        domain_hint=domain_hint,
                        importance_score=0.7,  # 工具结果相对重要
                        metadata={
                            'session_id': session_id,
                            'source': 'tool_result',
                            'tool_name': tool_name,
                            'extracted_at': time.time()
                        }
                    )
                    
                    if memory_id:
                        extracted_memories.append(memory_id)
            
            logger.info(f"智能体 {agent_role} 从状态中提取了 {len(extracted_memories)} 条记忆")
            return extracted_memories
            
        except Exception as e:
            logger.error(f"智能体记忆提取失败: {e}")
            return []
    
    def enhance_state_with_agent_memories(
        self, 
        state: IsotopeSystemState, 
        agent_role: str,
        query: Optional[str] = None,
        max_memories: Dict[str, int] = None
    ) -> AgentMemoryContext:
        """使用智能体相关记忆增强系统状态"""
        try:
            user_id = state.get('metadata', {}).get('user_id', 'default_user')
            
            # 默认记忆数量限制
            if max_memories is None:
                max_memories = {'semantic': 3, 'episodic': 2, 'procedural': 2}
            
            # 如果没有提供查询，从最新消息中提取
            if not query:
                messages = state.get('messages', [])
                if messages:
                    latest_msg = messages[-1]
                    query = self._extract_content_from_message(latest_msg)
            
            if not query:
                logger.warning("无法提取查询内容，返回空记忆上下文")
                return self._empty_agent_memory_context(agent_role)
            
            # 获取智能体记忆上下文
            memory_context = self.enhanced_store.get_agent_memory_context(
                user_id=user_id,
                agent_role=agent_role,
                query=query,
                max_semantic=max_memories.get('semantic', 3),
                max_episodic=max_memories.get('episodic', 2),
                max_procedural=max_memories.get('procedural', 2)
            )
            
            # 生成记忆摘要
            memory_summary = self._generate_agent_memory_summary(memory_context, agent_role)
            
            # 计算置信度
            confidence_score = self._calculate_agent_memory_confidence(memory_context, agent_role)
            
            # 获取访问权限
            access_permissions = self._get_agent_access_permissions(agent_role)
            
            # 获取领域覆盖
            domain_coverage = self._get_agent_domain_coverage(memory_context)
            
            # 计算相关性分数
            relevance_scores = self._calculate_memory_relevance_scores(memory_context, query)
            
            agent_memory_context = AgentMemoryContext(
                agent_role=agent_role,
                semantic_memories=memory_context['semantic'],
                episodic_memories=memory_context['episodic'],
                procedural_memories=memory_context['procedural'],
                memory_summary=memory_summary,
                confidence_score=confidence_score,
                access_permissions=access_permissions,
                domain_coverage=domain_coverage,
                relevance_scores=relevance_scores
            )
            
            logger.info(f"智能体 {agent_role} 记忆增强完成: "
                       f"语义={len(memory_context['semantic'])}, "
                       f"情节={len(memory_context['episodic'])}, "
                       f"程序={len(memory_context['procedural'])}, "
                       f"置信度={confidence_score:.2f}")
            
            return agent_memory_context
            
        except Exception as e:
            logger.error(f"智能体记忆增强失败: {e}")
            return self._empty_agent_memory_context(agent_role)
    
    def save_agent_interaction_memory(
        self, 
        state: IsotopeSystemState, 
        agent_role: str,
        interaction_summary: str,
        session_id: Optional[str] = None
    ) -> Optional[str]:
        """保存智能体交互记忆"""
        try:
            user_id = state.get('metadata', {}).get('user_id', 'default_user')
            if not session_id:
                session_id = state.get('metadata', {}).get('session_id', str(uuid.uuid4()))
            
            # 构建交互记忆内容
            content = f"[{agent_role}] 交互摘要: {interaction_summary}\n"
            
            # 添加上下文信息
            messages = state.get('messages', [])
            if messages:
                content += f"消息数量: {len(messages)}\n"
            
            tool_results = state.get('tool_results', [])
            if tool_results:
                tool_names = [tr.get('tool_name', 'unknown') for tr in tool_results]
                content += f"使用工具: {', '.join(set(tool_names))}\n"
            
            # 推断交互相关的领域
            domain_hint = self._infer_domain_from_content(interaction_summary, agent_role)
            
            # 保存为情节记忆
            memory_id = self.enhanced_store.put_agent_memory(
                user_id=user_id,
                agent_role=agent_role,
                content=content,
                memory_type='episodic',
                domain_hint=domain_hint,
                importance_score=0.8,  # 交互摘要比较重要
                metadata={
                    'session_id': session_id,
                    'interaction_type': 'session_summary',
                    'created_at': time.time()
                }
            )
            
            logger.info(f"智能体 {agent_role} 交互记忆保存成功: {memory_id}")
            return memory_id
            
        except Exception as e:
            logger.error(f"保存智能体交互记忆失败: {e}")
            return None
    
    def get_cross_agent_shared_memories(
        self,
        user_id: str,
        requesting_agent_role: str,
        query: str,
        limit: int = 5
    ) -> List[EnhancedMemoryEntry]:
        """获取跨智能体共享的记忆"""
        try:
            # 搜索共享记忆
            shared_memories = self.enhanced_store.search_agent_memories(
                user_id=user_id,
                requesting_agent_role=AgentRole.SHARED.value,
                query=query,
                limit=limit,
                include_shared=True
            )
            
            # 过滤出真正的共享记忆
            filtered_memories = [
                memory for memory in shared_memories
                if memory.agent_role == AgentRole.SHARED.value or
                   memory.domain in [DomainTag.GENERAL_KNOWLEDGE.value, DomainTag.CROSS_DOMAIN.value]
            ]
            
            logger.debug(f"获取到 {len(filtered_memories)} 条跨智能体共享记忆")
            return filtered_memories
            
        except Exception as e:
            logger.error(f"获取跨智能体共享记忆失败: {e}")
            return []
    
    def migrate_legacy_memories_for_agent(self, user_id: str, agent_role: str) -> int:
        """为特定智能体迁移传统记忆"""
        try:
            return self.enhanced_store.migrate_legacy_memories(user_id)
        except Exception as e:
            logger.error(f"智能体记忆迁移失败: {e}")
            return 0
    
    def _analyze_content_for_memory(self, content: str, agent_role: str) -> Tuple[Optional[str], float]:
        """分析内容确定记忆类型和重要性"""
        content_lower = content.lower()
        
        # 确定记忆类型
        memory_type = None
        importance = 0.5
        
        # 情节记忆关键词
        episodic_keywords = ['发生', '经历', '过程', '结果', '时间', '事件']
        # 程序记忆关键词
        procedural_keywords = ['步骤', '方法', '流程', '操作', '执行', '处理']
        # 语义记忆关键词
        semantic_keywords = ['定义', '概念', '原理', '知识', '理论', '规律']
        
        episodic_score = sum(1 for kw in episodic_keywords if kw in content_lower)
        procedural_score = sum(1 for kw in procedural_keywords if kw in content_lower)
        semantic_score = sum(1 for kw in semantic_keywords if kw in content_lower)
        
        # 确定主要类型
        max_score = max(episodic_score, procedural_score, semantic_score)
        if max_score > 0:
            if episodic_score == max_score:
                memory_type = 'episodic'
                importance += 0.2
            elif procedural_score == max_score:
                memory_type = 'procedural'
                importance += 0.3
            else:
                memory_type = 'semantic'
                importance += 0.1
        else:
            memory_type = 'semantic'  # 默认为语义记忆
        
        # 根据内容长度调整重要性
        if len(content) > 100:
            importance += 0.1
        if len(content) > 500:
            importance += 0.1
        
        # 根据智能体角色调整重要性
        role_domains = self.namespace_manager.agent_domain_mapping.get(
            AgentRole(agent_role), []
        )
        domain_keywords = []
        for domain in role_domains:
            domain_keywords.extend(
                self.namespace_manager.domain_keyword_mapping.get(domain, [])
            )
        
        # 内容与智能体专业领域的匹配度
        domain_match_count = sum(1 for kw in domain_keywords if kw in content_lower)
        if domain_match_count > 0:
            importance += min(domain_match_count * 0.1, 0.3)
        
        importance = min(importance, 1.0)  # 确保不超过1.0
        
        return memory_type, importance
    
    def _infer_domain_from_content(self, content: str, agent_role: str) -> Optional[str]:
        """从内容推断专业领域"""
        content_lower = content.lower()
        
        # 获取智能体可能的领域
        role_domains = self.namespace_manager.agent_domain_mapping.get(
            AgentRole(agent_role), []
        )
        
        # 计算每个领域的匹配分数
        domain_scores = {}
        for domain in role_domains:
            keywords = self.namespace_manager.domain_keyword_mapping.get(domain, [])
            score = sum(1 for keyword in keywords if keyword in content_lower)
            if score > 0:
                domain_scores[domain] = score
        
        # 选择得分最高的领域
        if domain_scores:
            best_domain = max(domain_scores, key=domain_scores.get)
            return best_domain.value
        
        return None
    
    def _infer_domain_from_tool(self, tool_name: str, agent_role: str) -> Optional[str]:
        """从工具名称推断专业领域"""
        tool_name_lower = tool_name.lower()
        
        # 工具名称到领域的映射
        tool_domain_mapping = {
            'seismic': DomainTag.SEISMIC_DATA,
            'well': DomainTag.WELL_LOG,
            'geology': DomainTag.GEOLOGY,
            'reservoir': DomainTag.RESERVOIR_SIM,
            'production': DomainTag.PRODUCTION_OPT,
            'economic': DomainTag.NPV_CALCULATION,
            'npv': DomainTag.NPV_CALCULATION,
            'irr': DomainTag.IRR_ANALYSIS,
            'validation': DomainTag.DATA_VALIDATION,
            'visualization': DomainTag.DATA_VISUALIZATION,
            'statistics': DomainTag.STATISTICAL_ANALYSIS
        }
        
        for tool_keyword, domain in tool_domain_mapping.items():
            if tool_keyword in tool_name_lower:
                return domain.value
        
        return None
    
    def _generate_agent_memory_summary(
        self, 
        memory_context: Dict[str, List[EnhancedMemoryEntry]], 
        agent_role: str
    ) -> str:
        """生成智能体记忆摘要"""
        try:
            summary_parts = []
            
            # 智能体角色信息
            summary_parts.append(f"智能体 {agent_role} 的相关记忆:")
            
            # 语义记忆摘要
            semantic_memories = memory_context.get('semantic', [])
            if semantic_memories:
                summary_parts.append(f"\n【专业知识】({len(semantic_memories)}条):")
                for i, memory in enumerate(semantic_memories[:3], 1):
                    content_preview = memory.content[:100] + "..." if len(memory.content) > 100 else memory.content
                    summary_parts.append(f"  {i}. [{memory.domain}] {content_preview}")
            
            # 情节记忆摘要
            episodic_memories = memory_context.get('episodic', [])
            if episodic_memories:
                summary_parts.append(f"\n【历史经验】({len(episodic_memories)}条):")
                for i, memory in enumerate(episodic_memories[:2], 1):
                    content_preview = memory.content[:100] + "..." if len(memory.content) > 100 else memory.content
                    summary_parts.append(f"  {i}. {content_preview}")
            
            # 程序记忆摘要
            procedural_memories = memory_context.get('procedural', [])
            if procedural_memories:
                summary_parts.append(f"\n【操作流程】({len(procedural_memories)}条):")
                for i, memory in enumerate(procedural_memories[:2], 1):
                    content_preview = memory.content[:100] + "..." if len(memory.content) > 100 else memory.content
                    summary_parts.append(f"  {i}. {content_preview}")
            
            return "\n".join(summary_parts)
            
        except Exception as e:
            logger.error(f"生成智能体记忆摘要失败: {e}")
            return f"智能体 {agent_role} 记忆摘要生成失败"
    
    def _calculate_agent_memory_confidence(
        self, 
        memory_context: Dict[str, List[EnhancedMemoryEntry]], 
        agent_role: str
    ) -> float:
        """计算智能体记忆的置信度"""
        try:
            total_memories = sum(len(memories) for memories in memory_context.values())
            if total_memories == 0:
                return 0.0
            
            # 基础置信度（基于记忆数量）
            base_confidence = min(total_memories / 10.0, 0.6)
            
            # 相关性置信度（基于相关性分数）
            relevance_sum = 0.0
            relevance_count = 0
            for memories in memory_context.values():
                for memory in memories:
                    relevance_sum += memory.relevance_score
                    relevance_count += 1
            
            relevance_confidence = relevance_sum / relevance_count if relevance_count > 0 else 0.0
            
            # 重要性置信度（基于重要性分数）
            importance_sum = 0.0
            importance_count = 0
            for memories in memory_context.values():
                for memory in memories:
                    importance_sum += memory.importance_score
                    importance_count += 1
            
            importance_confidence = importance_sum / importance_count if importance_count > 0 else 0.0
            
            # 综合置信度
            final_confidence = (
                base_confidence * 0.3 +
                relevance_confidence * 0.4 +
                importance_confidence * 0.3
            )
            
            return min(final_confidence, 1.0)
            
        except Exception as e:
            logger.error(f"计算智能体记忆置信度失败: {e}")
            return 0.0
    
    def _get_agent_access_permissions(self, agent_role: str) -> List[str]:
        """获取智能体的访问权限"""
        try:
            role_enum = AgentRole(agent_role)
            role_level = self.namespace_manager.role_hierarchy.get(role_enum, 1)
            
            permissions = [agent_role]  # 自己的记忆
            
            if role_level >= 3:  # 高权限
                permissions.extend(['shared', 'cross_domain'])
            elif role_level >= 2:  # 专业权限
                permissions.append('shared')
            
            return permissions
            
        except Exception:
            return [agent_role]
    
    def _get_agent_domain_coverage(
        self, 
        memory_context: Dict[str, List[EnhancedMemoryEntry]]
    ) -> List[str]:
        """获取记忆覆盖的专业领域"""
        domains = set()
        for memories in memory_context.values():
            for memory in memories:
                if memory.domain:
                    domains.add(memory.domain)
        return list(domains)
    
    def _calculate_memory_relevance_scores(
        self, 
        memory_context: Dict[str, List[EnhancedMemoryEntry]], 
        query: str
    ) -> Dict[str, float]:
        """计算各类记忆的相关性分数"""
        scores = {}
        for memory_type, memories in memory_context.items():
            if memories:
                avg_relevance = sum(memory.relevance_score for memory in memories) / len(memories)
                scores[memory_type] = avg_relevance
            else:
                scores[memory_type] = 0.0
        return scores
    
    def _empty_agent_memory_context(self, agent_role: str) -> AgentMemoryContext:
        """创建空的智能体记忆上下文"""
        return AgentMemoryContext(
            agent_role=agent_role,
            semantic_memories=[],
            episodic_memories=[],
            procedural_memories=[],
            memory_summary=f"智能体 {agent_role} 暂无相关记忆",
            confidence_score=0.0,
            access_permissions=[agent_role],
            domain_coverage=[],
            relevance_scores={'semantic': 0.0, 'episodic': 0.0, 'procedural': 0.0}
        )
    
    def _extract_content_from_message(self, msg) -> Optional[str]:
        """从消息中提取内容"""
        if hasattr(msg, 'content'):
            return msg.content
        elif isinstance(msg, dict):
            return msg.get('content', '')
        else:
            return str(msg)
    
    def _extract_content_from_tool_result(self, tool_result: Dict[str, Any]) -> Optional[str]:
        """从工具结果中提取内容"""
        if 'output' in tool_result:
            output = tool_result['output']
            if isinstance(output, str):
                return output
            elif isinstance(output, dict):
                return str(output)
        return None


def create_enhanced_memory_integration(config: Optional[Dict[str, Any]] = None) -> EnhancedMemoryIntegration:
    """创建增强记忆集成实例"""
    return EnhancedMemoryIntegration(config) 