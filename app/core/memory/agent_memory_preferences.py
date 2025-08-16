"""
智能体记忆偏好配置系统

本模块实现了智能体记忆偏好的配置和管理，包括：
1. 智能体角色的记忆偏好定义
2. 基于偏好的记忆筛选权重
3. 动态记忆偏好调整机制
4. 记忆使用效果的反馈学习
"""

import logging
import json
import time
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import numpy as np

from app.core.memory.enhanced_memory_namespace import (
    AgentRole, DomainTag, MemoryType
)

logger = logging.getLogger(__name__)


class MemoryUsagePattern(str, Enum):
    """记忆使用模式"""
    HEAVY_SEMANTIC = "heavy_semantic"      # 偏重语义记忆
    HEAVY_EPISODIC = "heavy_episodic"      # 偏重情节记忆
    HEAVY_PROCEDURAL = "heavy_procedural"  # 偏重程序记忆
    BALANCED = "balanced"                  # 平衡使用
    DYNAMIC = "dynamic"                    # 动态调整


@dataclass
class MemoryPreference:
    """记忆偏好配置"""
    # 记忆类型偏好权重
    semantic_weight: float = 1.0
    episodic_weight: float = 1.0
    procedural_weight: float = 1.0
    
    # 记忆数量偏好
    max_semantic_memories: int = 3
    max_episodic_memories: int = 2
    max_procedural_memories: int = 2
    
    # 记忆质量偏好
    min_importance_threshold: float = 0.3
    min_relevance_threshold: float = 0.2
    
    # 记忆新鲜度偏好
    recency_weight: float = 0.1
    max_age_days: int = 30
    
    # 专业领域偏好
    preferred_domains: List[str] = field(default_factory=list)
    domain_boost_factor: float = 1.2
    
    # 跨智能体记忆偏好
    enable_cross_agent_memories: bool = True
    cross_agent_weight: float = 0.5
    
    # 记忆使用模式
    usage_pattern: MemoryUsagePattern = MemoryUsagePattern.BALANCED
    
    # 动态调整参数
    enable_dynamic_adjustment: bool = True
    learning_rate: float = 0.1
    adjustment_window: int = 10  # 最近N次交互的反馈窗口


@dataclass
class MemoryFeedback:
    """记忆使用反馈"""
    session_id: str
    agent_role: str
    memory_ids: List[str]
    memory_types: List[str]
    domains: List[str]
    
    # 反馈指标
    usefulness_score: float      # 有用性评分 (0-1)
    relevance_score: float       # 相关性评分 (0-1)
    accuracy_score: float        # 准确性评分 (0-1)
    completeness_score: float    # 完整性评分 (0-1)
    
    # 时间信息
    timestamp: float
    interaction_duration: float
    
    # 额外信息
    user_satisfaction: Optional[float] = None
    task_completion: Optional[bool] = None
    notes: Optional[str] = None


class AgentMemoryPreferenceManager:
    """智能体记忆偏好管理器"""
    
    def __init__(self, config_file: Optional[str] = None):
        """初始化记忆偏好管理器"""
        self.config_file = config_file
        self.preferences: Dict[str, MemoryPreference] = {}
        self.feedback_history: Dict[str, List[MemoryFeedback]] = {}
        self.adjustment_stats: Dict[str, Dict[str, float]] = {}
        
        # 加载默认偏好配置
        self._load_default_preferences()
        
        # 如果有配置文件，加载用户定义的偏好
        if config_file:
            self._load_preferences_from_file(config_file)
        
        logger.info("智能体记忆偏好管理器初始化完成")
    
    def _load_default_preferences(self):
        """加载默认的智能体记忆偏好"""
        
        # 地球物理分析智能体
        self.preferences[AgentRole.GEOPHYSICS_ANALYSIS.value] = MemoryPreference(
            semantic_weight=1.5,           # 偏重语义记忆（专业知识）
            episodic_weight=1.0,
            procedural_weight=1.2,
            max_semantic_memories=4,
            max_episodic_memories=2,
            max_procedural_memories=3,
            min_importance_threshold=0.4,
            preferred_domains=[
                DomainTag.SEISMIC_DATA.value,
                DomainTag.WELL_LOG.value,
                DomainTag.GEOLOGY.value,
                DomainTag.FORMATION_EVAL.value
            ],
            domain_boost_factor=1.3,
            usage_pattern=MemoryUsagePattern.HEAVY_SEMANTIC,
            enable_cross_agent_memories=True,
            cross_agent_weight=0.6
        )
        
        # 油藏工程智能体
        self.preferences[AgentRole.RESERVOIR_ENGINEERING.value] = MemoryPreference(
            semantic_weight=1.2,
            episodic_weight=1.3,           # 偏重情节记忆（历史案例）
            procedural_weight=1.4,         # 偏重程序记忆（工程流程）
            max_semantic_memories=3,
            max_episodic_memories=3,
            max_procedural_memories=4,
            min_importance_threshold=0.3,
            preferred_domains=[
                DomainTag.RESERVOIR_SIM.value,
                DomainTag.PRODUCTION_OPT.value,
                DomainTag.PRESSURE_ANALYSIS.value,
                DomainTag.RECOVERY_FACTOR.value
            ],
            domain_boost_factor=1.4,
            usage_pattern=MemoryUsagePattern.HEAVY_PROCEDURAL,
            enable_cross_agent_memories=True,
            cross_agent_weight=0.7
        )
        
        # 经济评价智能体
        self.preferences[AgentRole.ECONOMIC_EVALUATION.value] = MemoryPreference(
            semantic_weight=1.3,
            episodic_weight=1.5,           # 偏重情节记忆（历史项目）
            procedural_weight=1.1,
            max_semantic_memories=3,
            max_episodic_memories=4,
            max_procedural_memories=2,
            min_importance_threshold=0.4,
            preferred_domains=[
                DomainTag.NPV_CALCULATION.value,
                DomainTag.IRR_ANALYSIS.value,
                DomainTag.RISK_ASSESSMENT.value,
                DomainTag.COST_BENEFIT.value
            ],
            domain_boost_factor=1.5,
            usage_pattern=MemoryUsagePattern.HEAVY_EPISODIC,
            enable_cross_agent_memories=True,
            cross_agent_weight=0.8
        )
        
        # 质量保证智能体
        self.preferences[AgentRole.QUALITY_ASSURANCE.value] = MemoryPreference(
            semantic_weight=1.1,
            episodic_weight=1.2,
            procedural_weight=1.6,         # 偏重程序记忆（检查流程）
            max_semantic_memories=2,
            max_episodic_memories=3,
            max_procedural_memories=4,
            min_importance_threshold=0.5,  # 更高的质量要求
            preferred_domains=[
                DomainTag.DATA_VALIDATION.value,
                DomainTag.STATISTICAL_ANALYSIS.value
            ],
            domain_boost_factor=1.3,
            usage_pattern=MemoryUsagePattern.HEAVY_PROCEDURAL,
            enable_cross_agent_memories=True,
            cross_agent_weight=0.9         # 需要全面了解各智能体的工作
        )
        
        # 通用分析智能体
        self.preferences[AgentRole.GENERAL_ANALYSIS.value] = MemoryPreference(
            semantic_weight=1.0,
            episodic_weight=1.0,
            procedural_weight=1.0,
            max_semantic_memories=3,
            max_episodic_memories=2,
            max_procedural_memories=2,
            min_importance_threshold=0.3,
            preferred_domains=[
                DomainTag.GENERAL_KNOWLEDGE.value,
                DomainTag.CROSS_DOMAIN.value
            ],
            domain_boost_factor=1.1,
            usage_pattern=MemoryUsagePattern.BALANCED,
            enable_cross_agent_memories=True,
            cross_agent_weight=0.8
        )
        
        # 数据处理智能体
        self.preferences[AgentRole.DATA_PROCESSING.value] = MemoryPreference(
            semantic_weight=1.1,
            episodic_weight=0.9,
            procedural_weight=1.5,         # 偏重程序记忆（数据处理流程）
            max_semantic_memories=2,
            max_episodic_memories=1,
            max_procedural_memories=4,
            min_importance_threshold=0.3,
            preferred_domains=[
                DomainTag.DATA_VALIDATION.value,
                DomainTag.STATISTICAL_ANALYSIS.value,
                DomainTag.DATA_VISUALIZATION.value
            ],
            domain_boost_factor=1.3,
            usage_pattern=MemoryUsagePattern.HEAVY_PROCEDURAL,
            enable_cross_agent_memories=False,  # 专注于数据处理
            cross_agent_weight=0.3
        )
        
        # 专家分析智能体
        self.preferences[AgentRole.EXPERT_ANALYSIS.value] = MemoryPreference(
            semantic_weight=1.4,           # 偏重语义记忆（专家知识）
            episodic_weight=1.3,
            procedural_weight=1.1,
            max_semantic_memories=5,       # 更多的专业知识
            max_episodic_memories=3,
            max_procedural_memories=2,
            min_importance_threshold=0.4,
            preferred_domains=[
                DomainTag.CROSS_DOMAIN.value,
                DomainTag.GENERAL_KNOWLEDGE.value
            ],
            domain_boost_factor=1.2,
            usage_pattern=MemoryUsagePattern.HEAVY_SEMANTIC,
            enable_cross_agent_memories=True,
            cross_agent_weight=0.9         # 需要整合各领域知识
        )
        
        # 可视化智能体
        self.preferences[AgentRole.VISUALIZATION.value] = MemoryPreference(
            semantic_weight=1.0,
            episodic_weight=1.1,
            procedural_weight=1.4,         # 偏重程序记忆（可视化流程）
            max_semantic_memories=2,
            max_episodic_memories=2,
            max_procedural_memories=3,
            min_importance_threshold=0.3,
            preferred_domains=[
                DomainTag.DATA_VISUALIZATION.value
            ],
            domain_boost_factor=1.4,
            usage_pattern=MemoryUsagePattern.HEAVY_PROCEDURAL,
            enable_cross_agent_memories=True,
            cross_agent_weight=0.6
        )
        
        # 监督者智能体
        self.preferences[AgentRole.SUPERVISOR.value] = MemoryPreference(
            semantic_weight=1.2,
            episodic_weight=1.4,           # 偏重情节记忆（监督历史）
            procedural_weight=1.3,
            max_semantic_memories=4,
            max_episodic_memories=4,
            max_procedural_memories=3,
            min_importance_threshold=0.4,
            preferred_domains=[
                DomainTag.PROCEDURAL_KNOWLEDGE.value,
                DomainTag.CROSS_DOMAIN.value
            ],
            domain_boost_factor=1.3,
            usage_pattern=MemoryUsagePattern.HEAVY_EPISODIC,
            enable_cross_agent_memories=True,
            cross_agent_weight=1.0         # 需要全面了解
        )
        
        # 系统智能体
        self.preferences[AgentRole.SYSTEM.value] = MemoryPreference(
            semantic_weight=1.0,
            episodic_weight=1.0,
            procedural_weight=1.5,         # 偏重程序记忆（系统流程）
            max_semantic_memories=3,
            max_episodic_memories=2,
            max_procedural_memories=4,
            min_importance_threshold=0.3,
            preferred_domains=[
                DomainTag.PROCEDURAL_KNOWLEDGE.value,
                DomainTag.GENERAL_KNOWLEDGE.value
            ],
            domain_boost_factor=1.2,
            usage_pattern=MemoryUsagePattern.HEAVY_PROCEDURAL,
            enable_cross_agent_memories=True,
            cross_agent_weight=0.5
        )
        
        # 共享记忆空间
        self.preferences[AgentRole.SHARED.value] = MemoryPreference(
            semantic_weight=1.0,
            episodic_weight=1.0,
            procedural_weight=1.0,
            max_semantic_memories=5,
            max_episodic_memories=3,
            max_procedural_memories=3,
            min_importance_threshold=0.2,  # 更宽泛的共享标准
            preferred_domains=[
                DomainTag.GENERAL_KNOWLEDGE.value,
                DomainTag.CROSS_DOMAIN.value
            ],
            domain_boost_factor=1.1,
            usage_pattern=MemoryUsagePattern.BALANCED,
            enable_cross_agent_memories=True,
            cross_agent_weight=1.0
        )
    
    def get_agent_preference(self, agent_role: str) -> MemoryPreference:
        """获取智能体的记忆偏好"""
        return self.preferences.get(agent_role, self.preferences[AgentRole.GENERAL_ANALYSIS.value])
    
    def update_agent_preference(self, agent_role: str, preference: MemoryPreference):
        """更新智能体的记忆偏好"""
        self.preferences[agent_role] = preference
        logger.info(f"更新智能体 {agent_role} 的记忆偏好")
    
    def calculate_memory_weights(
        self, 
        agent_role: str, 
        memory_type: str, 
        domain: str, 
        importance_score: float,
        relevance_score: float,
        age_days: float
    ) -> float:
        """计算记忆的综合权重"""
        preference = self.get_agent_preference(agent_role)
        
        # 基础权重（基于记忆类型）
        if memory_type == 'semantic':
            base_weight = preference.semantic_weight
        elif memory_type == 'episodic':
            base_weight = preference.episodic_weight
        elif memory_type == 'procedural':
            base_weight = preference.procedural_weight
        else:
            base_weight = 1.0
        
        # 领域权重
        domain_weight = preference.domain_boost_factor if domain in preference.preferred_domains else 1.0
        
        # 重要性权重
        importance_weight = max(importance_score, preference.min_importance_threshold)
        
        # 相关性权重
        relevance_weight = max(relevance_score, preference.min_relevance_threshold)
        
        # 新鲜度权重
        recency_weight = max(0.1, 1.0 - (age_days / preference.max_age_days) * preference.recency_weight)
        
        # 综合权重
        final_weight = (
            base_weight * 0.3 +
            domain_weight * 0.2 +
            importance_weight * 0.2 +
            relevance_weight * 0.2 +
            recency_weight * 0.1
        )
        
        return final_weight
    
    def should_include_memory(
        self, 
        agent_role: str, 
        memory_type: str, 
        domain: str, 
        importance_score: float,
        relevance_score: float,
        age_days: float
    ) -> bool:
        """判断是否应该包含某个记忆"""
        preference = self.get_agent_preference(agent_role)
        
        # 基础筛选条件
        if importance_score < preference.min_importance_threshold:
            return False
        
        if relevance_score < preference.min_relevance_threshold:
            return False
        
        if age_days > preference.max_age_days:
            return False
        
        # 计算综合权重
        weight = self.calculate_memory_weights(
            agent_role, memory_type, domain, importance_score, relevance_score, age_days
        )
        
        # 设置动态阈值
        threshold = self._get_dynamic_threshold(agent_role, memory_type)
        
        return weight >= threshold
    
    def get_memory_limits(self, agent_role: str) -> Dict[str, int]:
        """获取智能体的记忆数量限制"""
        preference = self.get_agent_preference(agent_role)
        return {
            'semantic': preference.max_semantic_memories,
            'episodic': preference.max_episodic_memories,
            'procedural': preference.max_procedural_memories
        }
    
    def record_memory_feedback(self, feedback: MemoryFeedback):
        """记录记忆使用反馈"""
        agent_role = feedback.agent_role
        
        if agent_role not in self.feedback_history:
            self.feedback_history[agent_role] = []
        
        self.feedback_history[agent_role].append(feedback)
        
        # 保持反馈历史在合理范围内
        max_history = 100
        if len(self.feedback_history[agent_role]) > max_history:
            self.feedback_history[agent_role] = self.feedback_history[agent_role][-max_history:]
        
        # 如果启用了动态调整，进行偏好调整
        preference = self.get_agent_preference(agent_role)
        if preference.enable_dynamic_adjustment:
            self._adjust_preference_based_on_feedback(agent_role, feedback)
        
        logger.info(f"记录智能体 {agent_role} 的记忆反馈")
    
    def _adjust_preference_based_on_feedback(self, agent_role: str, feedback: MemoryFeedback):
        """基于反馈调整智能体偏好"""
        preference = self.get_agent_preference(agent_role)
        
        # 获取最近的反馈
        recent_feedbacks = self.feedback_history[agent_role][-preference.adjustment_window:]
        
        if len(recent_feedbacks) < preference.adjustment_window:
            return  # 反馈数量不足，不进行调整
        
        # 计算各类记忆的平均表现
        type_performance = {'semantic': [], 'episodic': [], 'procedural': []}
        
        for fb in recent_feedbacks:
            for mem_type in fb.memory_types:
                if mem_type in type_performance:
                    # 综合评分
                    score = (fb.usefulness_score + fb.relevance_score + fb.accuracy_score) / 3
                    type_performance[mem_type].append(score)
        
        # 计算平均表现
        avg_performance = {}
        for mem_type, scores in type_performance.items():
            if scores:
                avg_performance[mem_type] = sum(scores) / len(scores)
            else:
                avg_performance[mem_type] = 0.5  # 默认值
        
        # 调整权重
        learning_rate = preference.learning_rate
        
        # 如果某类记忆表现好，增加权重
        if avg_performance['semantic'] > 0.7:
            preference.semantic_weight = min(2.0, preference.semantic_weight + learning_rate)
        elif avg_performance['semantic'] < 0.3:
            preference.semantic_weight = max(0.5, preference.semantic_weight - learning_rate)
        
        if avg_performance['episodic'] > 0.7:
            preference.episodic_weight = min(2.0, preference.episodic_weight + learning_rate)
        elif avg_performance['episodic'] < 0.3:
            preference.episodic_weight = max(0.5, preference.episodic_weight - learning_rate)
        
        if avg_performance['procedural'] > 0.7:
            preference.procedural_weight = min(2.0, preference.procedural_weight + learning_rate)
        elif avg_performance['procedural'] < 0.3:
            preference.procedural_weight = max(0.5, preference.procedural_weight - learning_rate)
        
        # 更新偏好
        self.preferences[agent_role] = preference
        
        logger.info(f"基于反馈调整智能体 {agent_role} 的记忆偏好")
    
    def _get_dynamic_threshold(self, agent_role: str, memory_type: str) -> float:
        """获取动态阈值"""
        preference = self.get_agent_preference(agent_role)
        
        # 基础阈值
        base_threshold = 0.5
        
        # 根据使用模式调整
        if preference.usage_pattern == MemoryUsagePattern.HEAVY_SEMANTIC and memory_type == 'semantic':
            return base_threshold * 0.8
        elif preference.usage_pattern == MemoryUsagePattern.HEAVY_EPISODIC and memory_type == 'episodic':
            return base_threshold * 0.8
        elif preference.usage_pattern == MemoryUsagePattern.HEAVY_PROCEDURAL and memory_type == 'procedural':
            return base_threshold * 0.8
        
        return base_threshold
    
    def get_preference_statistics(self, agent_role: str) -> Dict[str, Any]:
        """获取智能体偏好统计信息"""
        preference = self.get_agent_preference(agent_role)
        feedback_count = len(self.feedback_history.get(agent_role, []))
        
        # 计算最近反馈的平均表现
        recent_feedbacks = self.feedback_history.get(agent_role, [])[-10:]
        avg_performance = 0.0
        if recent_feedbacks:
            scores = []
            for fb in recent_feedbacks:
                score = (fb.usefulness_score + fb.relevance_score + fb.accuracy_score) / 3
                scores.append(score)
            avg_performance = sum(scores) / len(scores)
        
        return {
            'agent_role': agent_role,
            'preference': {
                'semantic_weight': preference.semantic_weight,
                'episodic_weight': preference.episodic_weight,
                'procedural_weight': preference.procedural_weight,
                'usage_pattern': preference.usage_pattern.value,
                'preferred_domains': preference.preferred_domains,
                'enable_dynamic_adjustment': preference.enable_dynamic_adjustment
            },
            'feedback_stats': {
                'total_feedbacks': feedback_count,
                'avg_performance': avg_performance,
                'recent_adjustment': preference.enable_dynamic_adjustment
            }
        }
    
    def _load_preferences_from_file(self, config_file: str):
        """从文件加载偏好配置"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            for agent_role, pref_data in config_data.items():
                preference = MemoryPreference(**pref_data)
                self.preferences[agent_role] = preference
            
            logger.info(f"从文件 {config_file} 加载偏好配置")
            
        except Exception as e:
            logger.error(f"加载偏好配置文件失败: {e}")
    
    def save_preferences_to_file(self, config_file: str):
        """保存偏好配置到文件"""
        try:
            config_data = {}
            for agent_role, preference in self.preferences.items():
                config_data[agent_role] = {
                    'semantic_weight': preference.semantic_weight,
                    'episodic_weight': preference.episodic_weight,
                    'procedural_weight': preference.procedural_weight,
                    'max_semantic_memories': preference.max_semantic_memories,
                    'max_episodic_memories': preference.max_episodic_memories,
                    'max_procedural_memories': preference.max_procedural_memories,
                    'min_importance_threshold': preference.min_importance_threshold,
                    'min_relevance_threshold': preference.min_relevance_threshold,
                    'recency_weight': preference.recency_weight,
                    'max_age_days': preference.max_age_days,
                    'preferred_domains': preference.preferred_domains,
                    'domain_boost_factor': preference.domain_boost_factor,
                    'enable_cross_agent_memories': preference.enable_cross_agent_memories,
                    'cross_agent_weight': preference.cross_agent_weight,
                    'usage_pattern': preference.usage_pattern.value,
                    'enable_dynamic_adjustment': preference.enable_dynamic_adjustment,
                    'learning_rate': preference.learning_rate,
                    'adjustment_window': preference.adjustment_window
                }
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"保存偏好配置到文件 {config_file}")
            
        except Exception as e:
            logger.error(f"保存偏好配置文件失败: {e}")


# 全局偏好管理器实例
_preference_manager = None

def get_preference_manager() -> AgentMemoryPreferenceManager:
    """获取全局偏好管理器实例"""
    global _preference_manager
    if _preference_manager is None:
        _preference_manager = AgentMemoryPreferenceManager()
    return _preference_manager 