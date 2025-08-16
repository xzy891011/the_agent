"""
记忆相关性评分系统 - 阶段3.2：实现记忆内容的相关性评分

该模块负责：
1. 多维度记忆相关性评估
2. 语义相似性计算
3. 任务相关性分析
4. 时间衰减因子计算
5. 领域匹配评分
6. 智能体偏好整合
"""

import logging
import math
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json
from collections import defaultdict

from .enhanced_memory_namespace import AgentRole, DomainTag, MemoryType
from .enhanced_langgraph_store import EnhancedMemoryEntry
from .agent_memory_preferences import MemoryPreference

logger = logging.getLogger(__name__)

class ScoringStrategy(str, Enum):
    """评分策略枚举"""
    SEMANTIC_FOCUSED = "semantic_focused"      # 语义导向
    TASK_FOCUSED = "task_focused"              # 任务导向
    TEMPORAL_FOCUSED = "temporal_focused"      # 时间导向
    DOMAIN_FOCUSED = "domain_focused"          # 领域导向
    BALANCED = "balanced"                      # 平衡评分
    AGENT_ADAPTIVE = "agent_adaptive"          # 智能体自适应


class RelevanceFactors(str, Enum):
    """相关性因子枚举"""
    SEMANTIC_SIMILARITY = "semantic_similarity"    # 语义相似性
    TASK_RELEVANCE = "task_relevance"              # 任务相关性
    TEMPORAL_DECAY = "temporal_decay"              # 时间衰减
    DOMAIN_MATCH = "domain_match"                  # 领域匹配
    AGENT_PREFERENCE = "agent_preference"          # 智能体偏好
    FREQUENCY_BOOST = "frequency_boost"            # 频率提升
    IMPORTANCE_WEIGHT = "importance_weight"        # 重要性权重
    CONTEXTUAL_RELEVANCE = "contextual_relevance"  # 上下文相关性


@dataclass
class ScoringContext:
    """评分上下文"""
    query: str
    agent_role: str
    current_task: Optional[str] = None
    session_id: Optional[str] = None
    domain_focus: Optional[DomainTag] = None
    conversation_history: List[str] = field(default_factory=list)
    available_tools: List[str] = field(default_factory=list)
    time_constraint: Optional[float] = None
    quality_requirement: str = "standard"
    user_preferences: Optional[Dict[str, Any]] = None


@dataclass
class RelevanceScore:
    """相关性评分结果"""
    total_score: float
    factor_scores: Dict[RelevanceFactors, float]
    confidence: float
    explanation: str
    calculation_details: Dict[str, Any]
    boosting_factors: List[str]
    penalty_factors: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_score": self.total_score,
            "factor_scores": {k.value: v for k, v in self.factor_scores.items()},
            "confidence": self.confidence,
            "explanation": self.explanation,
            "calculation_details": self.calculation_details,
            "boosting_factors": self.boosting_factors,
            "penalty_factors": self.penalty_factors
        }


@dataclass
class BatchScoringResult:
    """批量评分结果"""
    memory_scores: Dict[str, RelevanceScore]  # memory_id -> score
    total_memories: int
    average_score: float
    score_distribution: Dict[str, int]  # 分数区间分布
    top_memories: List[Tuple[str, float]]  # 前N个记忆
    scoring_time: float
    strategy_used: ScoringStrategy


class MemoryRelevanceScorer:
    """记忆相关性评分器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        
        # 评分策略配置
        self.scoring_strategies = self._init_scoring_strategies()
        self.factor_calculators = self._init_factor_calculators()
        
        # 预处理工具
        self.keyword_extractor = KeywordExtractor()
        self.semantic_analyzer = SemanticAnalyzer(self.config.get("semantic_config", {}))
        
        # 缓存系统
        self.score_cache = {}
        self.cache_ttl = timedelta(hours=1)
        
        # 统计信息
        self.scoring_stats = {
            "total_scored": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "average_scoring_time": 0.0,
            "strategy_usage": defaultdict(int)
        }
    
    def score_memory_relevance(
        self,
        memory: EnhancedMemoryEntry,
        context: ScoringContext,
        strategy: ScoringStrategy = ScoringStrategy.BALANCED,
        agent_preference: Optional[MemoryPreference] = None
    ) -> RelevanceScore:
        """计算单个记忆的相关性分数"""
        start_time = datetime.now()
        
        try:
            # 检查缓存
            cache_key = self._generate_cache_key(memory, context, strategy)
            cached_score = self._get_cached_score(cache_key)
            if cached_score:
                self.scoring_stats["cache_hits"] += 1
                return cached_score
            
            self.scoring_stats["cache_misses"] += 1
            
            # 计算各个因子分数
            factor_scores = self._calculate_factor_scores(memory, context, agent_preference)
            
            # 应用评分策略
            strategy_config = self.scoring_strategies[strategy]
            weighted_scores = self._apply_strategy_weights(factor_scores, strategy_config, context)
            
            # 计算总分
            total_score = self._calculate_total_score(weighted_scores, strategy_config)
            
            # 应用调整因子
            adjusted_score, boosting_factors, penalty_factors = self._apply_adjustment_factors(
                total_score, memory, context, agent_preference
            )
            
            # 计算置信度
            confidence = self._calculate_confidence(
                factor_scores, memory, context, strategy_config
            )
            
            # 生成解释
            explanation = self._generate_explanation(
                factor_scores, weighted_scores, adjusted_score, boosting_factors, penalty_factors
            )
            
            # 创建结果
            result = RelevanceScore(
                total_score=adjusted_score,
                factor_scores=factor_scores,
                confidence=confidence,
                explanation=explanation,
                calculation_details=self._create_calculation_details(
                    factor_scores, weighted_scores, strategy_config, memory, context
                ),
                boosting_factors=boosting_factors,
                penalty_factors=penalty_factors
            )
            
            # 更新缓存
            self._cache_score(cache_key, result)
            
            # 更新统计
            scoring_time = (datetime.now() - start_time).total_seconds()
            self._update_scoring_stats(scoring_time, strategy)
            
            return result
            
        except Exception as e:
            self.logger.error(f"记忆相关性评分失败: {str(e)}")
            return self._create_fallback_score(memory, context)
    
    def score_memory_batch(
        self,
        memories: List[EnhancedMemoryEntry],
        context: ScoringContext,
        strategy: ScoringStrategy = ScoringStrategy.BALANCED,
        agent_preference: Optional[MemoryPreference] = None
    ) -> BatchScoringResult:
        """批量计算记忆相关性分数"""
        start_time = datetime.now()
        
        memory_scores = {}
        for memory in memories:
            score = self.score_memory_relevance(memory, context, strategy, agent_preference)
            memory_scores[memory.id] = score
        
        # 计算统计信息
        scores = [score.total_score for score in memory_scores.values()]
        average_score = sum(scores) / len(scores) if scores else 0.0
        
        # 分数分布
        score_distribution = self._calculate_score_distribution(scores)
        
        # 最高分记忆
        top_memories = sorted(
            [(mem_id, score.total_score) for mem_id, score in memory_scores.items()],
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        scoring_time = (datetime.now() - start_time).total_seconds()
        
        return BatchScoringResult(
            memory_scores=memory_scores,
            total_memories=len(memories),
            average_score=average_score,
            score_distribution=score_distribution,
            top_memories=top_memories,
            scoring_time=scoring_time,
            strategy_used=strategy
        )
    
    def _calculate_factor_scores(
        self,
        memory: EnhancedMemoryEntry,
        context: ScoringContext,
        agent_preference: Optional[MemoryPreference]
    ) -> Dict[RelevanceFactors, float]:
        """计算各个因子的分数"""
        scores = {}
        
        for factor in RelevanceFactors:
            calculator = self.factor_calculators.get(factor)
            if calculator:
                try:
                    score = calculator(memory, context, agent_preference)
                    scores[factor] = max(0.0, min(1.0, score))  # 限制在0-1范围
                except Exception as e:
                    self.logger.warning(f"计算因子 {factor} 失败: {str(e)}")
                    scores[factor] = 0.0
        
        return scores
    
    def _apply_strategy_weights(
        self,
        factor_scores: Dict[RelevanceFactors, float],
        strategy_config: Dict[str, Any],
        context: ScoringContext
    ) -> Dict[RelevanceFactors, float]:
        """应用策略权重"""
        weights = strategy_config.get("weights", {})
        weighted_scores = {}
        
        for factor, score in factor_scores.items():
            weight = weights.get(factor.value, 1.0)
            weighted_scores[factor] = score * weight
        
        return weighted_scores
    
    def _calculate_total_score(
        self,
        weighted_scores: Dict[RelevanceFactors, float],
        strategy_config: Dict[str, Any]
    ) -> float:
        """计算总分"""
        aggregation_method = strategy_config.get("aggregation", "weighted_average")
        
        if aggregation_method == "weighted_average":
            total_weight = sum(weighted_scores.values())
            return total_weight / len(weighted_scores) if weighted_scores else 0.0
        
        elif aggregation_method == "max":
            return max(weighted_scores.values()) if weighted_scores else 0.0
        
        elif aggregation_method == "min":
            return min(weighted_scores.values()) if weighted_scores else 0.0
        
        else:
            # 默认为加权平均
            return sum(weighted_scores.values()) / len(weighted_scores) if weighted_scores else 0.0
    
    def _apply_adjustment_factors(
        self,
        base_score: float,
        memory: EnhancedMemoryEntry,
        context: ScoringContext,
        agent_preference: Optional[MemoryPreference]
    ) -> Tuple[float, List[str], List[str]]:
        """应用调整因子"""
        adjusted_score = base_score
        boosting_factors = []
        penalty_factors = []
        
        # 重要性提升
        if memory.importance_score > 0.8:
            adjusted_score *= 1.2
            boosting_factors.append("high_importance")
        
        # 访问频率提升
        if memory.access_count > 5:
            adjusted_score *= 1.1
            boosting_factors.append("frequent_access")
        
        # 时间衰减惩罚
        if memory.created_at:
            days_old = (datetime.now() - memory.created_at).days
            if days_old > 30:
                decay_factor = math.exp(-0.1 * days_old / 30)
                adjusted_score *= decay_factor
                penalty_factors.append("time_decay")
        
        # 智能体偏好调整
        if agent_preference and memory.agent_role:
            if memory.agent_role == context.agent_role:
                adjusted_score *= 1.15
                boosting_factors.append("agent_match")
            else:
                # 跨智能体记忆稍微降权
                adjusted_score *= 0.9
                penalty_factors.append("cross_agent")
        
        # 领域匹配调整
        if context.domain_focus and memory.domain:
            if memory.domain == context.domain_focus.value:
                adjusted_score *= 1.1
                boosting_factors.append("domain_match")
        
        return max(0.0, min(1.0, adjusted_score)), boosting_factors, penalty_factors
    
    def _calculate_confidence(
        self,
        factor_scores: Dict[RelevanceFactors, float],
        memory: EnhancedMemoryEntry,
        context: ScoringContext,
        strategy_config: Dict[str, Any]
    ) -> float:
        """计算置信度"""
        confidence_factors = []
        
        # 基于因子分数的一致性
        scores = list(factor_scores.values())
        if scores:
            score_variance = sum((s - sum(scores)/len(scores))**2 for s in scores) / len(scores)
            consistency = 1.0 - min(1.0, score_variance)
            confidence_factors.append(consistency)
        
        # 基于记忆质量
        if memory.importance_score > 0:
            confidence_factors.append(memory.importance_score)
        
        # 基于访问历史
        if memory.access_count > 0:
            access_confidence = min(1.0, memory.access_count / 10.0)
            confidence_factors.append(access_confidence)
        
        # 基于内容长度（适中长度更可信）
        if memory.content:
            content_length = len(memory.content)
            if 50 <= content_length <= 1000:
                confidence_factors.append(0.9)
            elif 20 <= content_length < 50 or 1000 < content_length <= 2000:
                confidence_factors.append(0.7)
            else:
                confidence_factors.append(0.5)
        
        return sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.5
    
    def _generate_explanation(
        self,
        factor_scores: Dict[RelevanceFactors, float],
        weighted_scores: Dict[RelevanceFactors, float],
        total_score: float,
        boosting_factors: List[str],
        penalty_factors: List[str]
    ) -> str:
        """生成评分解释"""
        explanation_parts = []
        
        explanation_parts.append(f"总分: {total_score:.3f}")
        
        # 主要因子分析
        top_factors = sorted(
            factor_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]
        
        factor_names = {
            RelevanceFactors.SEMANTIC_SIMILARITY: "语义相似性",
            RelevanceFactors.TASK_RELEVANCE: "任务相关性",
            RelevanceFactors.TEMPORAL_DECAY: "时间新鲜度",
            RelevanceFactors.DOMAIN_MATCH: "领域匹配",
            RelevanceFactors.AGENT_PREFERENCE: "智能体偏好",
            RelevanceFactors.FREQUENCY_BOOST: "使用频率",
            RelevanceFactors.IMPORTANCE_WEIGHT: "重要性权重",
            RelevanceFactors.CONTEXTUAL_RELEVANCE: "上下文相关性"
        }
        
        explanation_parts.append("主要因子:")
        for factor, score in top_factors:
            factor_name = factor_names.get(factor, factor.value)
            explanation_parts.append(f"  {factor_name}: {score:.3f}")
        
        # 提升因子
        if boosting_factors:
            boost_names = {
                "high_importance": "高重要性",
                "frequent_access": "频繁访问",
                "agent_match": "智能体匹配",
                "domain_match": "领域匹配"
            }
            boosts = [boost_names.get(b, b) for b in boosting_factors]
            explanation_parts.append(f"提升因子: {', '.join(boosts)}")
        
        # 惩罚因子
        if penalty_factors:
            penalty_names = {
                "time_decay": "时间衰减",
                "cross_agent": "跨智能体",
                "low_quality": "质量较低"
            }
            penalties = [penalty_names.get(p, p) for p in penalty_factors]
            explanation_parts.append(f"惩罚因子: {', '.join(penalties)}")
        
        return "; ".join(explanation_parts)
    
    def _create_calculation_details(
        self,
        factor_scores: Dict[RelevanceFactors, float],
        weighted_scores: Dict[RelevanceFactors, float],
        strategy_config: Dict[str, Any],
        memory: EnhancedMemoryEntry,
        context: ScoringContext
    ) -> Dict[str, Any]:
        """创建计算细节"""
        return {
            "raw_factor_scores": {k.value: v for k, v in factor_scores.items()},
            "weighted_scores": {k.value: v for k, v in weighted_scores.items()},
            "strategy_weights": strategy_config.get("weights", {}),
            "aggregation_method": strategy_config.get("aggregation", "weighted_average"),
            "memory_metadata": {
                "id": memory.id,
                "type": memory.memory_type,
                "agent_role": memory.agent_role,
                "domain": memory.domain,
                "importance": memory.importance_score,
                "access_count": memory.access_count,
                "created_at": memory.created_at.isoformat() if memory.created_at else None
            },
            "context_info": {
                "agent_role": context.agent_role,
                "current_task": context.current_task,
                "domain_focus": context.domain_focus.value if context.domain_focus else None,
                "query_length": len(context.query),
                "has_conversation_history": len(context.conversation_history) > 0
            }
        }
    
    def _calculate_score_distribution(self, scores: List[float]) -> Dict[str, int]:
        """计算分数分布"""
        distribution = {
            "0.0-0.2": 0,
            "0.2-0.4": 0,
            "0.4-0.6": 0,
            "0.6-0.8": 0,
            "0.8-1.0": 0
        }
        
        for score in scores:
            if score < 0.2:
                distribution["0.0-0.2"] += 1
            elif score < 0.4:
                distribution["0.2-0.4"] += 1
            elif score < 0.6:
                distribution["0.4-0.6"] += 1
            elif score < 0.8:
                distribution["0.6-0.8"] += 1
            else:
                distribution["0.8-1.0"] += 1
        
        return distribution
    
    def _generate_cache_key(
        self,
        memory: EnhancedMemoryEntry,
        context: ScoringContext,
        strategy: ScoringStrategy
    ) -> str:
        """生成缓存键"""
        key_parts = [
            memory.id,
            context.agent_role,
            context.query[:100],  # 限制查询长度
            context.current_task or "",
            context.domain_focus.value if context.domain_focus else "",
            strategy.value
        ]
        return hash("|".join(key_parts))
    
    def _get_cached_score(self, cache_key: str) -> Optional[RelevanceScore]:
        """获取缓存的分数"""
        if cache_key in self.score_cache:
            cached_item = self.score_cache[cache_key]
            if datetime.now() - cached_item["timestamp"] < self.cache_ttl:
                return cached_item["score"]
            else:
                del self.score_cache[cache_key]
        return None
    
    def _cache_score(self, cache_key: str, score: RelevanceScore):
        """缓存分数"""
        self.score_cache[cache_key] = {
            "score": score,
            "timestamp": datetime.now()
        }
        
        # 清理过期缓存
        if len(self.score_cache) > 1000:
            self._cleanup_cache()
    
    def _cleanup_cache(self):
        """清理过期缓存"""
        current_time = datetime.now()
        expired_keys = [
            key for key, item in self.score_cache.items()
            if current_time - item["timestamp"] > self.cache_ttl
        ]
        for key in expired_keys:
            del self.score_cache[key]
    
    def _update_scoring_stats(self, scoring_time: float, strategy: ScoringStrategy):
        """更新评分统计"""
        self.scoring_stats["total_scored"] += 1
        self.scoring_stats["strategy_usage"][strategy.value] += 1
        
        # 更新平均评分时间
        total_time = (self.scoring_stats["average_scoring_time"] * 
                     (self.scoring_stats["total_scored"] - 1) + scoring_time)
        self.scoring_stats["average_scoring_time"] = total_time / self.scoring_stats["total_scored"]
    
    def _create_fallback_score(
        self,
        memory: EnhancedMemoryEntry,
        context: ScoringContext
    ) -> RelevanceScore:
        """创建回退分数"""
        return RelevanceScore(
            total_score=0.3,
            factor_scores={factor: 0.3 for factor in RelevanceFactors},
            confidence=0.2,
            explanation="评分失败，使用回退分数",
            calculation_details={"fallback": True},
            boosting_factors=[],
            penalty_factors=["scoring_error"]
        )
    
    def _init_scoring_strategies(self) -> Dict[ScoringStrategy, Dict[str, Any]]:
        """初始化评分策略"""
        strategies = {}
        
        # 语义导向策略
        strategies[ScoringStrategy.SEMANTIC_FOCUSED] = {
            "weights": {
                "semantic_similarity": 2.0,
                "contextual_relevance": 1.5,
                "task_relevance": 1.0,
                "domain_match": 1.0,
                "temporal_decay": 0.5,
                "agent_preference": 0.8,
                "frequency_boost": 0.5,
                "importance_weight": 0.8
            },
            "aggregation": "weighted_average",
            "description": "重点关注语义相似性和上下文相关性"
        }
        
        # 任务导向策略
        strategies[ScoringStrategy.TASK_FOCUSED] = {
            "weights": {
                "task_relevance": 2.0,
                "contextual_relevance": 1.5,
                "domain_match": 1.5,
                "semantic_similarity": 1.0,
                "agent_preference": 1.0,
                "importance_weight": 1.0,
                "temporal_decay": 0.8,
                "frequency_boost": 0.5
            },
            "aggregation": "weighted_average",
            "description": "重点关注任务相关性和专业领域匹配"
        }
        
        # 时间导向策略
        strategies[ScoringStrategy.TEMPORAL_FOCUSED] = {
            "weights": {
                "temporal_decay": 2.0,
                "frequency_boost": 1.5,
                "semantic_similarity": 1.0,
                "task_relevance": 1.0,
                "contextual_relevance": 1.0,
                "domain_match": 0.8,
                "agent_preference": 0.8,
                "importance_weight": 0.8
            },
            "aggregation": "weighted_average",
            "description": "重点关注时间新鲜度和使用频率"
        }
        
        # 领域导向策略
        strategies[ScoringStrategy.DOMAIN_FOCUSED] = {
            "weights": {
                "domain_match": 2.0,
                "agent_preference": 1.5,
                "task_relevance": 1.5,
                "semantic_similarity": 1.0,
                "contextual_relevance": 1.0,
                "importance_weight": 1.0,
                "temporal_decay": 0.8,
                "frequency_boost": 0.5
            },
            "aggregation": "weighted_average",
            "description": "重点关注专业领域匹配和智能体偏好"
        }
        
        # 平衡策略
        strategies[ScoringStrategy.BALANCED] = {
            "weights": {
                "semantic_similarity": 1.0,
                "task_relevance": 1.0,
                "contextual_relevance": 1.0,
                "domain_match": 1.0,
                "agent_preference": 1.0,
                "temporal_decay": 1.0,
                "frequency_boost": 1.0,
                "importance_weight": 1.0
            },
            "aggregation": "weighted_average",
            "description": "各因子平衡权重的综合评分"
        }
        
        # 智能体自适应策略
        strategies[ScoringStrategy.AGENT_ADAPTIVE] = {
            "weights": {
                "agent_preference": 1.8,
                "domain_match": 1.5,
                "task_relevance": 1.2,
                "semantic_similarity": 1.0,
                "contextual_relevance": 1.0,
                "importance_weight": 1.0,
                "temporal_decay": 0.9,
                "frequency_boost": 0.8
            },
            "aggregation": "weighted_average",
            "description": "根据智能体偏好自适应调整权重"
        }
        
        return strategies
    
    def _init_factor_calculators(self) -> Dict[RelevanceFactors, callable]:
        """初始化因子计算器"""
        calculators = {}
        
        def calculate_semantic_similarity(memory, context, agent_preference):
            return self.semantic_analyzer.calculate_similarity(
                memory.content, context.query
            )
        
        def calculate_task_relevance(memory, context, agent_preference):
            if not context.current_task:
                return 0.5
            
            task_keywords = self.keyword_extractor.extract_keywords(context.current_task)
            memory_keywords = self.keyword_extractor.extract_keywords(memory.content)
            
            # 计算关键词重叠度
            overlap = len(set(task_keywords) & set(memory_keywords))
            total_keywords = len(set(task_keywords) | set(memory_keywords))
            
            return overlap / total_keywords if total_keywords > 0 else 0.0
        
        def calculate_temporal_decay(memory, context, agent_preference):
            if not memory.created_at:
                return 0.5
            
            days_old = (datetime.now() - memory.created_at).days
            # 使用指数衰减，半衰期为30天
            return math.exp(-0.023 * days_old)
        
        def calculate_domain_match(memory, context, agent_preference):
            if not memory.domain or not context.domain_focus:
                return 0.5
            
            if memory.domain == context.domain_focus.value:
                return 1.0
            
            # 检查领域相关性
            domain_similarity = self._calculate_domain_similarity(
                memory.domain, context.domain_focus.value
            )
            return domain_similarity
        
        def calculate_agent_preference(memory, context, agent_preference):
            if not agent_preference:
                return 0.5
            
            # 基于智能体偏好计算权重
            memory_type = memory.memory_type
            if memory_type == "semantic":
                return agent_preference.semantic_weight
            elif memory_type == "episodic":
                return agent_preference.episodic_weight
            elif memory_type == "procedural":
                return agent_preference.procedural_weight
            else:
                return 0.5
        
        def calculate_frequency_boost(memory, context, agent_preference):
            if memory.access_count == 0:
                return 0.0
            
            # 对数缩放访问次数
            return min(1.0, math.log(memory.access_count + 1) / math.log(10))
        
        def calculate_importance_weight(memory, context, agent_preference):
            return memory.importance_score
        
        def calculate_contextual_relevance(memory, context, agent_preference):
            relevance_score = 0.0
            
            # 与对话历史的相关性
            if context.conversation_history:
                for hist_msg in context.conversation_history[-3:]:  # 最近3条
                    similarity = self.semantic_analyzer.calculate_similarity(
                        memory.content, hist_msg
                    )
                    relevance_score = max(relevance_score, similarity)
            
            # 与可用工具的相关性
            if context.available_tools:
                for tool in context.available_tools:
                    if tool.lower() in memory.content.lower():
                        relevance_score = max(relevance_score, 0.8)
            
            return relevance_score
        
        calculators[RelevanceFactors.SEMANTIC_SIMILARITY] = calculate_semantic_similarity
        calculators[RelevanceFactors.TASK_RELEVANCE] = calculate_task_relevance
        calculators[RelevanceFactors.TEMPORAL_DECAY] = calculate_temporal_decay
        calculators[RelevanceFactors.DOMAIN_MATCH] = calculate_domain_match
        calculators[RelevanceFactors.AGENT_PREFERENCE] = calculate_agent_preference
        calculators[RelevanceFactors.FREQUENCY_BOOST] = calculate_frequency_boost
        calculators[RelevanceFactors.IMPORTANCE_WEIGHT] = calculate_importance_weight
        calculators[RelevanceFactors.CONTEXTUAL_RELEVANCE] = calculate_contextual_relevance
        
        return calculators
    
    def _calculate_domain_similarity(self, domain1: str, domain2: str) -> float:
        """计算领域相似性"""
        # 简化的领域相似性计算
        domain_groups = {
            "seismic": ["seismic_data", "geology", "formation_eval"],
            "reservoir": ["reservoir_sim", "production_opt", "pressure_analysis"],
            "economic": ["npv_calculation", "irr_analysis", "risk_assessment"],
            "data": ["data_validation", "statistical_analysis", "data_visualization"]
        }
        
        for group, domains in domain_groups.items():
            if domain1 in domains and domain2 in domains:
                return 0.8
        
        return 0.2
    
    def get_scoring_statistics(self) -> Dict[str, Any]:
        """获取评分统计信息"""
        return {
            "scoring_stats": self.scoring_stats,
            "cache_stats": {
                "cache_size": len(self.score_cache),
                "hit_rate": (self.scoring_stats["cache_hits"] / 
                           max(1, self.scoring_stats["cache_hits"] + self.scoring_stats["cache_misses"]))
            },
            "available_strategies": [s.value for s in ScoringStrategy],
            "available_factors": [f.value for f in RelevanceFactors]
        }


class KeywordExtractor:
    """关键词提取器"""
    
    def __init__(self):
        self.stop_words = {
            "的", "是", "在", "和", "与", "对", "为", "了", "到", "从", "中", "上", "下",
            "一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "个", "种", "类"
        }
    
    def extract_keywords(self, text: str, max_keywords: int = 10) -> List[str]:
        """提取关键词"""
        if not text:
            return []
        
        # 简单的关键词提取：按词频和长度
        words = re.findall(r'[\w]+', text.lower())
        words = [w for w in words if w not in self.stop_words and len(w) > 1]
        
        # 计算词频
        word_freq = {}
        for word in words:
            word_freq[word] = word_freq.get(word, 0) + 1
        
        # 按频率和长度排序
        sorted_words = sorted(
            word_freq.items(),
            key=lambda x: (x[1], len(x[0])),
            reverse=True
        )
        
        return [word for word, freq in sorted_words[:max_keywords]]


class SemanticAnalyzer:
    """语义分析器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        # 这里可以集成更高级的语义分析工具
        
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """计算语义相似性"""
        if not text1 or not text2:
            return 0.0
        
        # 简化的相似性计算：基于词汇重叠
        words1 = set(re.findall(r'[\w]+', text1.lower()))
        words2 = set(re.findall(r'[\w]+', text2.lower()))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        # Jaccard相似性
        jaccard = len(intersection) / len(union)
        
        # 考虑长度差异
        length_ratio = min(len(text1), len(text2)) / max(len(text1), len(text2))
        
        return jaccard * length_ratio


def create_memory_relevance_scorer(config: Optional[Dict[str, Any]] = None) -> MemoryRelevanceScorer:
    """创建记忆相关性评分器"""
    return MemoryRelevanceScorer(config) 