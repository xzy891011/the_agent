"""
智能体记忆筛选器 - 基于偏好的智能记忆筛选

本模块实现了智能体特定的记忆筛选机制，包括：
1. 基于偏好的记忆筛选和排序
2. 动态权重计算和相关性评分
3. 记忆质量评估和去重
4. 上下文感知的记忆选择
"""

import logging
import time
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass
import math

from app.core.memory.enhanced_langgraph_store import EnhancedMemoryEntry
from app.core.memory.agent_memory_preferences import (
    AgentMemoryPreferenceManager,
    MemoryPreference,
    MemoryFeedback,
    get_preference_manager
)
from app.core.memory.enhanced_memory_namespace import (
    AgentRole, DomainTag, MemoryType
)

logger = logging.getLogger(__name__)


@dataclass
class MemoryFilterContext:
    """记忆筛选上下文"""
    user_id: str
    session_id: str
    agent_role: str
    query: str
    current_task: Optional[str] = None
    conversation_history: Optional[List[str]] = None
    available_tools: Optional[List[str]] = None
    time_constraint: Optional[float] = None
    quality_requirement: Optional[str] = "standard"  # "low", "standard", "high"


@dataclass
class FilteredMemoryResult:
    """筛选后的记忆结果"""
    memories: List[EnhancedMemoryEntry]
    total_score: float
    confidence: float
    coverage_domains: List[str]
    memory_distribution: Dict[str, int]  # 各类型记忆的数量分布
    filter_summary: str
    execution_time: float


class AgentMemoryFilter:
    """智能体记忆筛选器"""
    
    def __init__(self):
        """初始化记忆筛选器"""
        self.preference_manager = get_preference_manager()
        self.filter_cache = {}  # 筛选结果缓存
        self.cache_ttl = 300    # 缓存生存时间（秒）
        
        logger.info("智能体记忆筛选器初始化完成")
    
    def filter_memories_for_agent(
        self,
        memories: List[EnhancedMemoryEntry],
        context: MemoryFilterContext
    ) -> FilteredMemoryResult:
        """为智能体筛选最相关的记忆"""
        start_time = time.time()
        
        try:
            # 检查缓存
            cache_key = self._generate_cache_key(memories, context)
            cached_result = self._get_cached_result(cache_key)
            if cached_result:
                logger.debug(f"使用缓存的筛选结果: {context.agent_role}")
                return cached_result
            
            # 获取智能体偏好
            preference = self.preference_manager.get_agent_preference(context.agent_role)
            
            # 第一步：基础筛选
            filtered_memories = self._basic_filter(memories, context, preference)
            logger.debug(f"基础筛选后剩余记忆: {len(filtered_memories)}")
            
            # 第二步：计算综合评分
            scored_memories = self._calculate_memory_scores(filtered_memories, context, preference)
            logger.debug(f"完成记忆评分计算")
            
            # 第三步：智能排序和选择
            selected_memories = self._intelligent_selection(scored_memories, context, preference)
            logger.debug(f"智能选择后的记忆数量: {len(selected_memories)}")
            
            # 第四步：记忆优化和去重
            optimized_memories = self._optimize_memories(selected_memories, context, preference)
            logger.debug(f"优化后的记忆数量: {len(optimized_memories)}")
            
            # 计算结果统计
            total_score = sum(memory.relevance_score for memory in optimized_memories)
            confidence = self._calculate_result_confidence(optimized_memories, context)
            coverage_domains = list(set(mem.domain for mem in optimized_memories if mem.domain))
            memory_distribution = self._calculate_memory_distribution(optimized_memories)
            filter_summary = self._generate_filter_summary(optimized_memories, context, preference)
            
            execution_time = time.time() - start_time
            
            result = FilteredMemoryResult(
                memories=optimized_memories,
                total_score=total_score,
                confidence=confidence,
                coverage_domains=coverage_domains,
                memory_distribution=memory_distribution,
                filter_summary=filter_summary,
                execution_time=execution_time
            )
            
            # 缓存结果
            self._cache_result(cache_key, result)
            
            logger.info(f"智能体 {context.agent_role} 记忆筛选完成: "
                       f"选择了 {len(optimized_memories)} 条记忆, "
                       f"置信度 {confidence:.2f}, 用时 {execution_time:.3f}s")
            
            return result
            
        except Exception as e:
            logger.error(f"记忆筛选失败: {e}")
            # 返回空结果
            return FilteredMemoryResult(
                memories=[],
                total_score=0.0,
                confidence=0.0,
                coverage_domains=[],
                memory_distribution={},
                filter_summary=f"筛选失败: {str(e)}",
                execution_time=time.time() - start_time
            )
    
    def _basic_filter(
        self,
        memories: List[EnhancedMemoryEntry],
        context: MemoryFilterContext,
        preference: MemoryPreference
    ) -> List[EnhancedMemoryEntry]:
        """基础筛选：过滤掉明显不相关的记忆"""
        filtered = []
        current_time = time.time()
        
        for memory in memories:
            # 检查年龄限制
            age_days = (current_time - memory.created_at) / (24 * 3600)
            if age_days > preference.max_age_days:
                continue
            
            # 检查重要性阈值
            if memory.importance_score < preference.min_importance_threshold:
                continue
            
            # 检查相关性阈值
            if hasattr(memory, 'relevance_score') and memory.relevance_score < preference.min_relevance_threshold:
                continue
            
            # 检查质量要求
            if not self._meets_quality_requirement(memory, context.quality_requirement):
                continue
            
            # 检查跨智能体记忆权限
            if memory.agent_role != context.agent_role and memory.agent_role != AgentRole.SHARED.value:
                if not preference.enable_cross_agent_memories:
                    continue
            
            filtered.append(memory)
        
        return filtered
    
    def _calculate_memory_scores(
        self,
        memories: List[EnhancedMemoryEntry],
        context: MemoryFilterContext,
        preference: MemoryPreference
    ) -> List[Tuple[EnhancedMemoryEntry, float]]:
        """计算每个记忆的综合评分"""
        scored_memories = []
        current_time = time.time()
        
        for memory in memories:
            # 计算年龄（天）
            age_days = (current_time - memory.created_at) / (24 * 3600)
            
            # 使用偏好管理器计算权重
            weight = self.preference_manager.calculate_memory_weights(
                agent_role=context.agent_role,
                memory_type=memory.memory_type,
                domain=memory.domain or "",
                importance_score=memory.importance_score,
                relevance_score=getattr(memory, 'relevance_score', 0.5),
                age_days=age_days
            )
            
            # 计算上下文相关性
            context_relevance = self._calculate_context_relevance(memory, context)
            
            # 计算语义相似度
            semantic_similarity = self._calculate_semantic_similarity(memory.content, context.query)
            
            # 计算任务相关性
            task_relevance = self._calculate_task_relevance(memory, context)
            
            # 综合评分
            final_score = (
                weight * 0.4 +
                context_relevance * 0.25 +
                semantic_similarity * 0.25 +
                task_relevance * 0.1
            )
            
            # 更新记忆的相关性分数
            memory.relevance_score = final_score
            
            scored_memories.append((memory, final_score))
        
        # 按评分排序
        scored_memories.sort(key=lambda x: x[1], reverse=True)
        
        return scored_memories
    
    def _intelligent_selection(
        self,
        scored_memories: List[Tuple[EnhancedMemoryEntry, float]],
        context: MemoryFilterContext,
        preference: MemoryPreference
    ) -> List[EnhancedMemoryEntry]:
        """智能选择：基于偏好和多样性选择记忆"""
        selected = []
        
        # 获取数量限制
        limits = self.preference_manager.get_memory_limits(context.agent_role)
        
        # 按类型分组
        type_groups = {
            'semantic': [],
            'episodic': [],
            'procedural': []
        }
        
        for memory, score in scored_memories:
            if memory.memory_type in type_groups:
                type_groups[memory.memory_type].append((memory, score))
        
        # 按偏好权重分配记忆
        for memory_type, limit in limits.items():
            group = type_groups.get(memory_type, [])
            
            # 选择最高分的记忆
            selected_from_type = []
            for memory, score in group[:limit]:
                # 检查多样性
                if self._should_include_for_diversity(memory, selected_from_type, context):
                    selected_from_type.append(memory)
                
                if len(selected_from_type) >= limit:
                    break
            
            selected.extend(selected_from_type)
        
        return selected
    
    def _optimize_memories(
        self,
        memories: List[EnhancedMemoryEntry],
        context: MemoryFilterContext,
        preference: MemoryPreference
    ) -> List[EnhancedMemoryEntry]:
        """优化记忆：去重、压缩和质量提升"""
        if not memories:
            return []
        
        # 第一步：去重
        deduplicated = self._remove_duplicates(memories)
        
        # 第二步：内容压缩（如果记忆太多）
        max_total_memories = sum(self.preference_manager.get_memory_limits(context.agent_role).values())
        if len(deduplicated) > max_total_memories:
            # 保留最高质量的记忆
            deduplicated.sort(key=lambda x: x.relevance_score, reverse=True)
            deduplicated = deduplicated[:max_total_memories]
        
        # 第三步：重新排序（按相关性和多样性）
        optimized = self._reorder_for_context(deduplicated, context)
        
        return optimized
    
    def _calculate_context_relevance(
        self,
        memory: EnhancedMemoryEntry,
        context: MemoryFilterContext
    ) -> float:
        """计算上下文相关性"""
        relevance = 0.0
        
        # 智能体角色匹配
        if memory.agent_role == context.agent_role:
            relevance += 0.3
        elif memory.agent_role == AgentRole.SHARED.value:
            relevance += 0.2
        
        # 会话相关性
        if hasattr(memory, 'metadata') and memory.metadata:
            if memory.metadata.get('session_id') == context.session_id:
                relevance += 0.2
        
        # 时间相关性
        if context.conversation_history:
            # 检查记忆内容是否与最近对话相关
            recent_content = ' '.join(context.conversation_history[-3:])  # 最近3条消息
            if self._has_content_overlap(memory.content, recent_content):
                relevance += 0.1
        
        # 工具相关性
        if context.available_tools and hasattr(memory, 'metadata'):
            tool_name = memory.metadata.get('tool_name')
            if tool_name in context.available_tools:
                relevance += 0.15
        
        # 任务相关性
        if context.current_task:
            if self._is_task_relevant(memory.content, context.current_task):
                relevance += 0.25
        
        return min(relevance, 1.0)
    
    def _calculate_semantic_similarity(self, memory_content: str, query: str) -> float:
        """计算语义相似度（简化版本）"""
        if not memory_content or not query:
            return 0.0
        
        # 简单的关键词匹配
        memory_words = set(memory_content.lower().split())
        query_words = set(query.lower().split())
        
        if not query_words:
            return 0.0
        
        # 计算词汇重叠度
        overlap = len(memory_words.intersection(query_words))
        similarity = overlap / len(query_words)
        
        # 考虑长度因子
        length_factor = min(len(memory_content) / 100, 1.0)  # 内容长度影响
        
        return min(similarity * length_factor, 1.0)
    
    def _calculate_task_relevance(
        self,
        memory: EnhancedMemoryEntry,
        context: MemoryFilterContext
    ) -> float:
        """计算任务相关性"""
        if not context.current_task:
            return 0.5  # 默认中等相关性
        
        task_lower = context.current_task.lower()
        content_lower = memory.content.lower()
        
        # 任务关键词匹配
        task_keywords = task_lower.split()
        relevance = 0.0
        
        for keyword in task_keywords:
            if keyword in content_lower:
                relevance += 0.1
        
        # 任务类型匹配
        if any(task_type in task_lower for task_type in ['分析', '计算', '评估', '优化']):
            if memory.memory_type == 'procedural':
                relevance += 0.2
        
        if any(task_type in task_lower for task_type in ['学习', '理解', '解释']):
            if memory.memory_type == 'semantic':
                relevance += 0.2
        
        if any(task_type in task_lower for task_type in ['经验', '案例', '历史']):
            if memory.memory_type == 'episodic':
                relevance += 0.2
        
        return min(relevance, 1.0)
    
    def _should_include_for_diversity(
        self,
        memory: EnhancedMemoryEntry,
        already_selected: List[EnhancedMemoryEntry],
        context: MemoryFilterContext
    ) -> bool:
        """判断是否应该为了多样性而包含这个记忆"""
        if not already_selected:
            return True
        
        # 检查领域多样性
        selected_domains = set(mem.domain for mem in already_selected if mem.domain)
        if memory.domain and memory.domain not in selected_domains:
            return True
        
        # 检查内容相似度
        for selected in already_selected:
            similarity = self._calculate_content_similarity(memory.content, selected.content)
            if similarity > 0.8:  # 内容过于相似
                return False
        
        return True
    
    def _remove_duplicates(self, memories: List[EnhancedMemoryEntry]) -> List[EnhancedMemoryEntry]:
        """去除重复记忆"""
        unique_memories = []
        seen_contents = set()
        
        for memory in memories:
            # 生成内容的简化版本用于比较
            content_hash = self._generate_content_hash(memory.content)
            
            if content_hash not in seen_contents:
                seen_contents.add(content_hash)
                unique_memories.append(memory)
        
        return unique_memories
    
    def _reorder_for_context(
        self,
        memories: List[EnhancedMemoryEntry],
        context: MemoryFilterContext
    ) -> List[EnhancedMemoryEntry]:
        """根据上下文重新排序记忆"""
        # 按相关性分数排序，但考虑类型多样性
        semantic_memories = [m for m in memories if m.memory_type == 'semantic']
        episodic_memories = [m for m in memories if m.memory_type == 'episodic']
        procedural_memories = [m for m in memories if m.memory_type == 'procedural']
        
        # 每种类型内部按相关性排序
        semantic_memories.sort(key=lambda x: x.relevance_score, reverse=True)
        episodic_memories.sort(key=lambda x: x.relevance_score, reverse=True)
        procedural_memories.sort(key=lambda x: x.relevance_score, reverse=True)
        
        # 交错排列以保持多样性
        reordered = []
        max_len = max(len(semantic_memories), len(episodic_memories), len(procedural_memories))
        
        for i in range(max_len):
            if i < len(semantic_memories):
                reordered.append(semantic_memories[i])
            if i < len(episodic_memories):
                reordered.append(episodic_memories[i])
            if i < len(procedural_memories):
                reordered.append(procedural_memories[i])
        
        return reordered
    
    def _meets_quality_requirement(self, memory: EnhancedMemoryEntry, quality_requirement: str) -> bool:
        """检查记忆是否满足质量要求"""
        if quality_requirement == "low":
            return memory.importance_score >= 0.1
        elif quality_requirement == "standard":
            return memory.importance_score >= 0.3
        elif quality_requirement == "high":
            return memory.importance_score >= 0.6
        else:
            return True
    
    def _has_content_overlap(self, content1: str, content2: str) -> bool:
        """检查两个内容是否有重叠"""
        words1 = set(content1.lower().split())
        words2 = set(content2.lower().split())
        overlap = len(words1.intersection(words2))
        return overlap >= 2  # 至少有2个共同词汇
    
    def _is_task_relevant(self, memory_content: str, task: str) -> bool:
        """检查记忆内容是否与任务相关"""
        memory_lower = memory_content.lower()
        task_lower = task.lower()
        
        # 提取任务关键词
        task_words = set(task_lower.split())
        memory_words = set(memory_lower.split())
        
        # 计算重叠度
        overlap = len(task_words.intersection(memory_words))
        return overlap >= 1
    
    def _calculate_content_similarity(self, content1: str, content2: str) -> float:
        """计算内容相似度"""
        words1 = set(content1.lower().split())
        words2 = set(content2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
    
    def _generate_content_hash(self, content: str) -> str:
        """生成内容的哈希值用于去重"""
        # 简化内容：去除标点符号，转换为小写，排序
        words = sorted(set(content.lower().split()))
        simplified = ' '.join(words[:10])  # 只取前10个不重复词汇
        return simplified
    
    def _calculate_result_confidence(
        self,
        memories: List[EnhancedMemoryEntry],
        context: MemoryFilterContext
    ) -> float:
        """计算结果置信度"""
        if not memories:
            return 0.0
        
        # 基于记忆数量的置信度
        memory_count_confidence = min(len(memories) / 5.0, 1.0)  # 5个记忆为满分
        
        # 基于平均相关性的置信度
        avg_relevance = sum(mem.relevance_score for mem in memories) / len(memories)
        
        # 基于记忆多样性的置信度
        unique_domains = len(set(mem.domain for mem in memories if mem.domain))
        unique_types = len(set(mem.memory_type for mem in memories))
        diversity_confidence = (unique_domains + unique_types) / 6.0  # 最多3种类型+3个领域
        
        # 综合置信度
        final_confidence = (
            memory_count_confidence * 0.3 +
            avg_relevance * 0.5 +
            diversity_confidence * 0.2
        )
        
        return min(final_confidence, 1.0)
    
    def _calculate_memory_distribution(self, memories: List[EnhancedMemoryEntry]) -> Dict[str, int]:
        """计算记忆类型分布"""
        distribution = {'semantic': 0, 'episodic': 0, 'procedural': 0}
        for memory in memories:
            if memory.memory_type in distribution:
                distribution[memory.memory_type] += 1
        return distribution
    
    def _generate_filter_summary(
        self,
        memories: List[EnhancedMemoryEntry],
        context: MemoryFilterContext,
        preference: MemoryPreference
    ) -> str:
        """生成筛选摘要"""
        if not memories:
            return f"智能体 {context.agent_role} 未找到相关记忆"
        
        distribution = self._calculate_memory_distribution(memories)
        avg_score = sum(mem.relevance_score for mem in memories) / len(memories)
        domains = list(set(mem.domain for mem in memories if mem.domain))
        
        summary = f"智能体 {context.agent_role} 筛选结果: "
        summary += f"共 {len(memories)} 条记忆 "
        summary += f"(语义:{distribution['semantic']}, 情节:{distribution['episodic']}, 程序:{distribution['procedural']}) "
        summary += f"平均相关性: {avg_score:.2f} "
        summary += f"涵盖领域: {', '.join(domains[:3])}{'...' if len(domains) > 3 else ''}"
        
        return summary
    
    def _generate_cache_key(
        self,
        memories: List[EnhancedMemoryEntry],
        context: MemoryFilterContext
    ) -> str:
        """生成缓存键"""
        # 简化的缓存键生成
        memory_ids = sorted([mem.id for mem in memories])
        key_components = [
            context.agent_role,
            context.query,
            str(len(memory_ids)),
            str(hash(tuple(memory_ids[:5])))  # 只使用前5个记忆的ID
        ]
        return '|'.join(key_components)
    
    def _get_cached_result(self, cache_key: str) -> Optional[FilteredMemoryResult]:
        """获取缓存结果"""
        if cache_key in self.filter_cache:
            cached_item = self.filter_cache[cache_key]
            if time.time() - cached_item['timestamp'] < self.cache_ttl:
                return cached_item['result']
            else:
                # 缓存过期，删除
                del self.filter_cache[cache_key]
        return None
    
    def _cache_result(self, cache_key: str, result: FilteredMemoryResult):
        """缓存结果"""
        self.filter_cache[cache_key] = {
            'result': result,
            'timestamp': time.time()
        }
        
        # 清理过期缓存
        current_time = time.time()
        expired_keys = [
            key for key, value in self.filter_cache.items()
            if current_time - value['timestamp'] > self.cache_ttl
        ]
        for key in expired_keys:
            del self.filter_cache[key]


def create_agent_memory_filter() -> AgentMemoryFilter:
    """创建智能体记忆筛选器实例"""
    return AgentMemoryFilter() 