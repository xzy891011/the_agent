"""
自适应记忆优化器 - 阶段4.2：基于反馈优化记忆筛选算法

该模块负责：
1. 收集和分析用户反馈
2. 监控记忆筛选效果
3. 动态调整筛选参数
4. 实现自适应学习算法
5. 优化记忆质量评估
"""

import logging
import json
import math
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
from collections import defaultdict, deque
import statistics

from .enhanced_memory_namespace import AgentRole, DomainTag, MemoryType
from .enhanced_langgraph_store import EnhancedMemoryEntry
from .agent_memory_preferences import MemoryPreference, MemoryFeedback, MemoryUsagePattern
from .memory_relevance_scorer import RelevanceScore, ScoringStrategy, ScoringContext
from .memory_usage_monitor import MemoryUsageEvent, AgentMetrics

logger = logging.getLogger(__name__)

class FeedbackType(str, Enum):
    """反馈类型枚举"""
    USER_EXPLICIT = "user_explicit"           # 用户明确反馈
    USER_IMPLICIT = "user_implicit"           # 用户隐式反馈
    SYSTEM_PERFORMANCE = "system_performance" # 系统性能反馈
    TASK_COMPLETION = "task_completion"       # 任务完成反馈
    QUALITY_ASSESSMENT = "quality_assessment" # 质量评估反馈

class FeedbackSignal(str, Enum):
    """反馈信号枚举"""
    POSITIVE = "positive"     # 正面反馈
    NEGATIVE = "negative"     # 负面反馈
    NEUTRAL = "neutral"       # 中性反馈
    MIXED = "mixed"          # 混合反馈

class OptimizationStrategy(str, Enum):
    """优化策略枚举"""
    CONSERVATIVE = "conservative"   # 保守策略
    AGGRESSIVE = "aggressive"      # 激进策略
    BALANCED = "balanced"          # 平衡策略
    ADAPTIVE = "adaptive"          # 自适应策略

@dataclass
class FeedbackEvent:
    """反馈事件"""
    event_id: str
    timestamp: datetime
    session_id: str
    agent_role: str
    memory_ids: List[str]
    feedback_type: FeedbackType
    feedback_signal: FeedbackSignal
    feedback_score: float  # 0.0 - 1.0
    feedback_details: Dict[str, Any]
    context: Dict[str, Any]
    source: str  # "user", "system", "automatic"

@dataclass
class OptimizationResult:
    """优化结果"""
    optimization_id: str
    timestamp: datetime
    agent_role: str
    parameters_before: Dict[str, Any]
    parameters_after: Dict[str, Any]
    improvement_metrics: Dict[str, float]
    confidence_score: float
    applied: bool
    rollback_available: bool

@dataclass
class LearningState:
    """学习状态"""
    agent_role: str
    learning_rate: float
    momentum: float
    experience_count: int
    performance_history: List[float]
    parameter_adjustments: List[Dict[str, Any]]
    last_optimization: Optional[datetime] = None
    stability_score: float = 0.5

class AdaptiveMemoryOptimizer:
    """自适应记忆优化器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        
        # 数据存储
        self.feedback_events: deque = deque(maxlen=5000)
        self.optimization_history: deque = deque(maxlen=1000)
        self.learning_states: Dict[str, LearningState] = {}
        
        # 优化配置
        self.optimization_config = self._init_optimization_config()
        self.feedback_analyzers = self._init_feedback_analyzers()
        self.parameter_optimizers = self._init_parameter_optimizers()
        self.learning_algorithms = self._init_learning_algorithms()
        
        # 当前参数状态
        self.current_parameters: Dict[str, Dict[str, Any]] = {}
        self.parameter_bounds: Dict[str, Dict[str, Tuple[float, float]]] = {}
        
        # 统计信息
        self.optimizer_stats = {
            "total_feedback_events": 0,
            "optimizations_performed": 0,
            "successful_optimizations": 0,
            "rollbacks_performed": 0,
            "average_improvement": 0.0,
            "learning_sessions": 0
        }
        
        # 初始化
        self._initialize_default_parameters()
        self._initialize_parameter_bounds()
    
    def record_feedback(
        self,
        session_id: str,
        agent_role: str,
        memory_ids: List[str],
        feedback_type: FeedbackType,
        feedback_signal: FeedbackSignal,
        feedback_score: float,
        feedback_details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        source: str = "system"
    ) -> str:
        """记录反馈事件"""
        event_id = f"feedback_{datetime.now().timestamp()}_{agent_role}"
        
        event = FeedbackEvent(
            event_id=event_id,
            timestamp=datetime.now(),
            session_id=session_id,
            agent_role=agent_role,
            memory_ids=memory_ids,
            feedback_type=feedback_type,
            feedback_signal=feedback_signal,
            feedback_score=feedback_score,
            feedback_details=feedback_details or {},
            context=context or {},
            source=source
        )
        
        # 存储反馈事件
        self.feedback_events.append(event)
        self.optimizer_stats["total_feedback_events"] += 1
        
        # 更新学习状态
        self._update_learning_state(event)
        
        # 检查是否触发优化
        if self._should_trigger_optimization(agent_role):
            self._trigger_optimization(agent_role)
        
        return event_id
    
    def optimize_agent_parameters(
        self,
        agent_role: str,
        strategy: OptimizationStrategy = OptimizationStrategy.ADAPTIVE
    ) -> OptimizationResult:
        """优化智能体参数"""
        self.logger.info(f"开始优化智能体 {agent_role} 的参数")
        
        # 获取当前参数
        current_params = self.current_parameters.get(agent_role, {})
        
        # 分析反馈数据
        feedback_analysis = self._analyze_agent_feedback(agent_role)
        
        # 计算参数调整
        parameter_adjustments = self._calculate_parameter_adjustments(
            agent_role, feedback_analysis, strategy
        )
        
        # 应用优化策略
        new_params = self._apply_parameter_adjustments(
            current_params, parameter_adjustments, agent_role
        )
        
        # 验证参数有效性
        validated_params = self._validate_parameters(new_params, agent_role)
        
        # 计算预期改进
        improvement_metrics = self._estimate_improvement(
            current_params, validated_params, feedback_analysis
        )
        
        # 计算置信度
        confidence_score = self._calculate_optimization_confidence(
            feedback_analysis, parameter_adjustments, agent_role
        )
        
        # 创建优化结果
        optimization_result = OptimizationResult(
            optimization_id=f"opt_{agent_role}_{datetime.now().timestamp()}",
            timestamp=datetime.now(),
            agent_role=agent_role,
            parameters_before=current_params.copy(),
            parameters_after=validated_params.copy(),
            improvement_metrics=improvement_metrics,
            confidence_score=confidence_score,
            applied=False,
            rollback_available=True
        )
        
        # 决定是否应用优化
        if self._should_apply_optimization(optimization_result):
            self._apply_optimization(optimization_result)
            optimization_result.applied = True
            self.optimizer_stats["successful_optimizations"] += 1
        
        # 记录优化历史
        self.optimization_history.append(optimization_result)
        self.optimizer_stats["optimizations_performed"] += 1
        
        # 更新学习状态
        learning_state = self.learning_states.get(agent_role)
        if learning_state:
            learning_state.last_optimization = datetime.now()
            learning_state.parameter_adjustments.append(parameter_adjustments)
        
        return optimization_result
    
    def get_optimal_memory_preferences(
        self,
        agent_role: str,
        context: Optional[Dict[str, Any]] = None
    ) -> MemoryPreference:
        """获取优化后的记忆偏好设置"""
        # 获取当前优化参数
        current_params = self.current_parameters.get(agent_role, {})
        
        # 基于上下文调整参数
        if context:
            adjusted_params = self._adjust_parameters_by_context(current_params, context)
        else:
            adjusted_params = current_params
        
        # 转换为MemoryPreference对象
        return self._convert_to_memory_preference(adjusted_params, agent_role)
    
    def analyze_optimization_impact(
        self,
        optimization_id: str,
        time_window: timedelta = timedelta(hours=24)
    ) -> Dict[str, Any]:
        """分析优化效果"""
        # 查找优化记录
        optimization = None
        for opt in self.optimization_history:
            if opt.optimization_id == optimization_id:
                optimization = opt
                break
        
        if not optimization:
            return {"error": "Optimization not found"}
        
        # 分析时间窗口内的性能变化
        analysis_start = optimization.timestamp
        analysis_end = analysis_start + time_window
        
        # 获取优化前后的反馈数据
        before_feedback = self._get_feedback_in_range(
            optimization.agent_role,
            analysis_start - time_window,
            analysis_start
        )
        
        after_feedback = self._get_feedback_in_range(
            optimization.agent_role,
            analysis_start,
            analysis_end
        )
        
        # 计算性能指标变化
        performance_change = self._calculate_performance_change(
            before_feedback, after_feedback
        )
        
        # 分析参数影响
        parameter_impact = self._analyze_parameter_impact(
            optimization.parameters_before,
            optimization.parameters_after,
            performance_change
        )
        
        return {
            "optimization_id": optimization_id,
            "agent_role": optimization.agent_role,
            "time_window": time_window.total_seconds(),
            "performance_change": performance_change,
            "parameter_impact": parameter_impact,
            "overall_impact": self._calculate_overall_impact(performance_change),
            "confidence": self._calculate_impact_confidence(before_feedback, after_feedback)
        }
    
    def rollback_optimization(
        self,
        optimization_id: str,
        reason: str = "Performance degradation"
    ) -> bool:
        """回滚优化"""
        # 查找优化记录
        optimization = None
        for opt in self.optimization_history:
            if opt.optimization_id == optimization_id:
                optimization = opt
                break
        
        if not optimization or not optimization.rollback_available:
            return False
        
        # 恢复之前的参数
        self.current_parameters[optimization.agent_role] = optimization.parameters_before.copy()
        
        # 记录回滚事件
        rollback_event = {
            "rollback_id": f"rollback_{datetime.now().timestamp()}",
            "optimization_id": optimization_id,
            "agent_role": optimization.agent_role,
            "reason": reason,
            "timestamp": datetime.now()
        }
        
        self.optimizer_stats["rollbacks_performed"] += 1
        self.logger.info(f"回滚优化 {optimization_id}: {reason}")
        
        return True
    
    def _analyze_agent_feedback(self, agent_role: str) -> Dict[str, Any]:
        """分析智能体的反馈数据"""
        # 获取相关反馈事件
        agent_feedback = [f for f in self.feedback_events if f.agent_role == agent_role]
        
        if not agent_feedback:
            return {"no_data": True}
        
        # 按反馈类型分组分析
        analysis = {
            "total_feedback": len(agent_feedback),
            "feedback_by_type": defaultdict(list),
            "feedback_by_signal": defaultdict(list),
            "average_score": 0.0,
            "trend_analysis": {},
            "problem_areas": [],
            "improvement_opportunities": []
        }
        
        # 分类统计
        for feedback in agent_feedback:
            analysis["feedback_by_type"][feedback.feedback_type.value].append(feedback)
            analysis["feedback_by_signal"][feedback.feedback_signal.value].append(feedback)
        
        # 计算平均分数
        scores = [f.feedback_score for f in agent_feedback]
        analysis["average_score"] = statistics.mean(scores) if scores else 0.0
        
        # 趋势分析
        analysis["trend_analysis"] = self._analyze_feedback_trend(agent_feedback)
        
        # 问题识别
        analysis["problem_areas"] = self._identify_problem_areas(agent_feedback)
        
        # 改进机会识别
        analysis["improvement_opportunities"] = self._identify_improvement_opportunities(agent_feedback)
        
        return analysis
    
    def _calculate_parameter_adjustments(
        self,
        agent_role: str,
        feedback_analysis: Dict[str, Any],
        strategy: OptimizationStrategy
    ) -> Dict[str, float]:
        """计算参数调整"""
        adjustments = {}
        
        if feedback_analysis.get("no_data", False):
            return adjustments
        
        # 获取学习状态
        learning_state = self.learning_states.get(agent_role)
        if not learning_state:
            learning_state = self._create_learning_state(agent_role)
        
        # 基于反馈分析计算调整
        average_score = feedback_analysis.get("average_score", 0.5)
        problem_areas = feedback_analysis.get("problem_areas", [])
        
        # 基础调整策略
        if average_score < 0.6:  # 需要改进
            # 增加语义权重，提高准确性
            adjustments["semantic_weight"] = 0.1 * learning_state.learning_rate
            
            # 提高相关性阈值
            adjustments["min_relevance_threshold"] = 0.05 * learning_state.learning_rate
            
            # 减少记忆数量，提高质量
            adjustments["max_semantic_memories"] = -0.5 * learning_state.learning_rate
        
        elif average_score > 0.8:  # 表现良好，可以尝试更多记忆
            adjustments["max_semantic_memories"] = 0.3 * learning_state.learning_rate
            adjustments["max_episodic_memories"] = 0.2 * learning_state.learning_rate
        
        # 基于具体问题调整
        for problem in problem_areas:
            if "relevance" in problem.lower():
                adjustments["min_relevance_threshold"] = adjustments.get("min_relevance_threshold", 0) + 0.03
            elif "freshness" in problem.lower():
                adjustments["recency_weight"] = adjustments.get("recency_weight", 0) + 0.05
            elif "diversity" in problem.lower():
                adjustments["domain_boost_factor"] = adjustments.get("domain_boost_factor", 0) + 0.02
        
        # 应用策略修正
        strategy_multiplier = {
            OptimizationStrategy.CONSERVATIVE: 0.5,
            OptimizationStrategy.BALANCED: 1.0,
            OptimizationStrategy.AGGRESSIVE: 1.5,
            OptimizationStrategy.ADAPTIVE: self._calculate_adaptive_multiplier(learning_state)
        }
        
        multiplier = strategy_multiplier.get(strategy, 1.0)
        for key in adjustments:
            adjustments[key] *= multiplier
        
        return adjustments
    
    def _apply_parameter_adjustments(
        self,
        current_params: Dict[str, Any],
        adjustments: Dict[str, float],
        agent_role: str
    ) -> Dict[str, Any]:
        """应用参数调整"""
        new_params = current_params.copy()
        bounds = self.parameter_bounds.get(agent_role, {})
        
        for param_name, adjustment in adjustments.items():
            if param_name in new_params:
                old_value = new_params[param_name]
                new_value = old_value + adjustment
                
                # 应用边界约束
                if param_name in bounds:
                    min_val, max_val = bounds[param_name]
                    new_value = max(min_val, min(max_val, new_value))
                
                new_params[param_name] = new_value
                
                self.logger.debug(f"调整参数 {param_name}: {old_value:.3f} -> {new_value:.3f}")
        
        return new_params
    
    def _validate_parameters(
        self,
        params: Dict[str, Any],
        agent_role: str
    ) -> Dict[str, Any]:
        """验证参数有效性"""
        validated_params = params.copy()
        bounds = self.parameter_bounds.get(agent_role, {})
        
        # 检查边界约束
        for param_name, value in params.items():
            if param_name in bounds:
                min_val, max_val = bounds[param_name]
                if value < min_val or value > max_val:
                    validated_params[param_name] = max(min_val, min(max_val, value))
                    self.logger.warning(f"参数 {param_name} 超出边界，已调整为 {validated_params[param_name]}")
        
        # 检查逻辑约束
        # 例如：确保权重之和合理
        weights = ["semantic_weight", "episodic_weight", "procedural_weight"]
        if all(w in validated_params for w in weights):
            total_weight = sum(validated_params[w] for w in weights)
            if total_weight > 3.0:  # 总权重过大
                scale_factor = 3.0 / total_weight
                for w in weights:
                    validated_params[w] *= scale_factor
        
        return validated_params
    
    def _estimate_improvement(
        self,
        old_params: Dict[str, Any],
        new_params: Dict[str, Any],
        feedback_analysis: Dict[str, Any]
    ) -> Dict[str, float]:
        """估算改进效果"""
        metrics = {}
        
        # 基于参数变化估算改进
        param_changes = {}
        for param in new_params:
            if param in old_params:
                change = abs(new_params[param] - old_params[param])
                param_changes[param] = change
        
        # 估算相关性改进
        relevance_improvement = 0.0
        if "min_relevance_threshold" in param_changes:
            relevance_improvement = param_changes["min_relevance_threshold"] * 0.5
        
        metrics["estimated_relevance_improvement"] = relevance_improvement
        
        # 估算记忆质量改进
        quality_improvement = 0.0
        if "semantic_weight" in param_changes:
            quality_improvement += param_changes["semantic_weight"] * 0.3
        
        metrics["estimated_quality_improvement"] = quality_improvement
        
        # 基于历史数据估算总体改进
        historical_improvement = self._estimate_historical_improvement(param_changes)
        metrics["estimated_overall_improvement"] = historical_improvement
        
        return metrics
    
    def _calculate_optimization_confidence(
        self,
        feedback_analysis: Dict[str, Any],
        parameter_adjustments: Dict[str, float],
        agent_role: str
    ) -> float:
        """计算优化置信度"""
        confidence_factors = []
        
        # 基于反馈数据量
        feedback_count = feedback_analysis.get("total_feedback", 0)
        data_confidence = min(1.0, feedback_count / 50.0)  # 50个反馈为满分
        confidence_factors.append(data_confidence)
        
        # 基于反馈质量
        average_score = feedback_analysis.get("average_score", 0.5)
        if 0.3 <= average_score <= 0.7:  # 中等分数，调整空间大
            quality_confidence = 0.8
        elif average_score < 0.3 or average_score > 0.9:  # 极端分数，调整风险大
            quality_confidence = 0.4
        else:
            quality_confidence = 0.6
        confidence_factors.append(quality_confidence)
        
        # 基于学习状态
        learning_state = self.learning_states.get(agent_role)
        if learning_state and learning_state.experience_count > 10:
            experience_confidence = min(1.0, learning_state.experience_count / 100.0)
            confidence_factors.append(experience_confidence)
        
        # 基于参数调整幅度
        adjustment_magnitude = sum(abs(adj) for adj in parameter_adjustments.values())
        if adjustment_magnitude < 0.1:  # 小幅调整
            adjustment_confidence = 0.9
        elif adjustment_magnitude > 0.5:  # 大幅调整
            adjustment_confidence = 0.3
        else:
            adjustment_confidence = 0.7
        confidence_factors.append(adjustment_confidence)
        
        return statistics.mean(confidence_factors) if confidence_factors else 0.5
    
    def _should_apply_optimization(self, optimization_result: OptimizationResult) -> bool:
        """判断是否应该应用优化"""
        # 检查置信度阈值
        if optimization_result.confidence_score < 0.6:
            return False
        
        # 检查预期改进
        overall_improvement = optimization_result.improvement_metrics.get("estimated_overall_improvement", 0)
        if overall_improvement < 0.05:  # 改进太小
            return False
        
        # 检查最近是否有过多优化
        recent_optimizations = [
            opt for opt in self.optimization_history
            if opt.agent_role == optimization_result.agent_role
            and (datetime.now() - opt.timestamp) < timedelta(hours=6)
        ]
        
        if len(recent_optimizations) > 2:  # 6小时内超过2次优化
            return False
        
        return True
    
    def _apply_optimization(self, optimization_result: OptimizationResult):
        """应用优化"""
        self.current_parameters[optimization_result.agent_role] = optimization_result.parameters_after.copy()
        
        self.logger.info(f"应用优化 {optimization_result.optimization_id} 到智能体 {optimization_result.agent_role}")
    
    def _update_learning_state(self, feedback_event: FeedbackEvent):
        """更新学习状态"""
        agent_role = feedback_event.agent_role
        
        if agent_role not in self.learning_states:
            self.learning_states[agent_role] = self._create_learning_state(agent_role)
        
        learning_state = self.learning_states[agent_role]
        learning_state.experience_count += 1
        
        # 更新性能历史
        learning_state.performance_history.append(feedback_event.feedback_score)
        if len(learning_state.performance_history) > 100:
            learning_state.performance_history.pop(0)
        
        # 调整学习率
        self._adjust_learning_rate(learning_state)
        
        # 更新稳定性分数
        self._update_stability_score(learning_state)
    
    def _create_learning_state(self, agent_role: str) -> LearningState:
        """创建学习状态"""
        return LearningState(
            agent_role=agent_role,
            learning_rate=0.1,
            momentum=0.9,
            experience_count=0,
            performance_history=[],
            parameter_adjustments=[]
        )
    
    def _should_trigger_optimization(self, agent_role: str) -> bool:
        """判断是否应该触发优化"""
        learning_state = self.learning_states.get(agent_role)
        if not learning_state:
            return False
        
        # 检查经验数量
        if learning_state.experience_count < 10:
            return False
        
        # 检查最近优化时间
        if learning_state.last_optimization:
            time_since_last = datetime.now() - learning_state.last_optimization
            if time_since_last < timedelta(hours=2):
                return False
        
        # 检查性能趋势
        if len(learning_state.performance_history) >= 5:
            recent_avg = statistics.mean(learning_state.performance_history[-5:])
            if recent_avg < 0.6:  # 性能下降，需要优化
                return True
        
        # 定期优化
        if learning_state.experience_count % 50 == 0:
            return True
        
        return False
    
    def _trigger_optimization(self, agent_role: str):
        """触发优化"""
        try:
            optimization_result = self.optimize_agent_parameters(agent_role)
            self.logger.info(f"自动触发的优化完成: {optimization_result.optimization_id}")
        except Exception as e:
            self.logger.error(f"自动优化失败: {str(e)}")
    
    def _analyze_feedback_trend(self, feedback_events: List[FeedbackEvent]) -> Dict[str, Any]:
        """分析反馈趋势"""
        if len(feedback_events) < 3:
            return {"trend": "insufficient_data"}
        
        # 按时间排序
        sorted_events = sorted(feedback_events, key=lambda x: x.timestamp)
        
        # 计算移动平均
        window_size = min(5, len(sorted_events))
        moving_averages = []
        
        for i in range(window_size - 1, len(sorted_events)):
            window_events = sorted_events[i - window_size + 1:i + 1]
            avg_score = statistics.mean([e.feedback_score for e in window_events])
            moving_averages.append(avg_score)
        
        # 分析趋势
        if len(moving_averages) >= 2:
            if moving_averages[-1] > moving_averages[0] + 0.1:
                trend = "improving"
            elif moving_averages[-1] < moving_averages[0] - 0.1:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "stable"
        
        return {
            "trend": trend,
            "moving_averages": moving_averages,
            "current_average": moving_averages[-1] if moving_averages else 0.5,
            "trend_strength": abs(moving_averages[-1] - moving_averages[0]) if len(moving_averages) >= 2 else 0
        }
    
    def _identify_problem_areas(self, feedback_events: List[FeedbackEvent]) -> List[str]:
        """识别问题区域"""
        problems = []
        
        # 分析负面反馈
        negative_feedback = [f for f in feedback_events if f.feedback_signal == FeedbackSignal.NEGATIVE]
        
        if len(negative_feedback) > len(feedback_events) * 0.3:  # 超过30%负面反馈
            problems.append("high_negative_feedback_ratio")
        
        # 分析低分反馈
        low_score_feedback = [f for f in feedback_events if f.feedback_score < 0.4]
        
        if len(low_score_feedback) > len(feedback_events) * 0.25:  # 超过25%低分
            problems.append("high_low_score_ratio")
        
        # 分析反馈细节中的问题
        detail_problems = defaultdict(int)
        for feedback in feedback_events:
            details = feedback.feedback_details
            if "relevance" in details and details["relevance"] < 0.5:
                detail_problems["poor_relevance"] += 1
            if "freshness" in details and details["freshness"] < 0.5:
                detail_problems["poor_freshness"] += 1
            if "diversity" in details and details["diversity"] < 0.5:
                detail_problems["poor_diversity"] += 1
        
        # 如果某个问题出现频率超过20%，认为是问题区域
        threshold = len(feedback_events) * 0.2
        for problem, count in detail_problems.items():
            if count > threshold:
                problems.append(problem)
        
        return problems
    
    def _identify_improvement_opportunities(self, feedback_events: List[FeedbackEvent]) -> List[str]:
        """识别改进机会"""
        opportunities = []
        
        # 分析正面反馈模式
        positive_feedback = [f for f in feedback_events if f.feedback_signal == FeedbackSignal.POSITIVE]
        
        if positive_feedback:
            # 分析正面反馈的共同特征
            positive_details = [f.feedback_details for f in positive_feedback]
            
            # 如果某个特征在正面反馈中频繁出现，可以加强
            feature_counts = defaultdict(int)
            for details in positive_details:
                for feature, value in details.items():
                    if isinstance(value, (int, float)) and value > 0.7:
                        feature_counts[f"enhance_{feature}"] += 1
            
            threshold = len(positive_feedback) * 0.6
            for feature, count in feature_counts.items():
                if count > threshold:
                    opportunities.append(feature)
        
        # 分析改进空间
        average_score = statistics.mean([f.feedback_score for f in feedback_events])
        if 0.6 <= average_score <= 0.8:
            opportunities.append("moderate_improvement_potential")
        elif average_score < 0.6:
            opportunities.append("high_improvement_potential")
        
        return opportunities
    
    def _calculate_adaptive_multiplier(self, learning_state: LearningState) -> float:
        """计算自适应乘数"""
        # 基于稳定性和经验计算
        stability_factor = learning_state.stability_score
        experience_factor = min(1.0, learning_state.experience_count / 100.0)
        
        # 如果稳定性高且经验丰富，使用较小的调整幅度
        if stability_factor > 0.8 and experience_factor > 0.8:
            return 0.3
        elif stability_factor < 0.3:  # 不稳定，需要较大调整
            return 1.5
        else:
            return 1.0
    
    def _adjust_learning_rate(self, learning_state: LearningState):
        """调整学习率"""
        if len(learning_state.performance_history) >= 5:
            recent_performance = learning_state.performance_history[-5:]
            variance = statistics.variance(recent_performance) if len(recent_performance) > 1 else 0
            
            # 如果性能变化很大，降低学习率
            if variance > 0.1:
                learning_state.learning_rate *= 0.9
            # 如果性能稳定，可以稍微提高学习率
            elif variance < 0.02:
                learning_state.learning_rate *= 1.05
            
            # 限制学习率范围
            learning_state.learning_rate = max(0.01, min(0.3, learning_state.learning_rate))
    
    def _update_stability_score(self, learning_state: LearningState):
        """更新稳定性分数"""
        if len(learning_state.performance_history) >= 10:
            recent_performance = learning_state.performance_history[-10:]
            variance = statistics.variance(recent_performance)
            
            # 基于方差计算稳定性（方差越小越稳定）
            stability = max(0.0, 1.0 - variance * 5.0)
            
            # 使用指数移动平均更新稳定性分数
            alpha = 0.1
            learning_state.stability_score = (1 - alpha) * learning_state.stability_score + alpha * stability
    
    def _get_feedback_in_range(
        self,
        agent_role: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[FeedbackEvent]:
        """获取时间范围内的反馈"""
        return [
            f for f in self.feedback_events
            if f.agent_role == agent_role and start_time <= f.timestamp <= end_time
        ]
    
    def _calculate_performance_change(
        self,
        before_feedback: List[FeedbackEvent],
        after_feedback: List[FeedbackEvent]
    ) -> Dict[str, float]:
        """计算性能变化"""
        change = {}
        
        if before_feedback and after_feedback:
            before_avg = statistics.mean([f.feedback_score for f in before_feedback])
            after_avg = statistics.mean([f.feedback_score for f in after_feedback])
            
            change["score_change"] = after_avg - before_avg
            change["relative_change"] = (after_avg - before_avg) / before_avg if before_avg > 0 else 0
            
            # 分析反馈信号变化
            before_positive = len([f for f in before_feedback if f.feedback_signal == FeedbackSignal.POSITIVE])
            after_positive = len([f for f in after_feedback if f.feedback_signal == FeedbackSignal.POSITIVE])
            
            change["positive_feedback_change"] = after_positive - before_positive
        
        return change
    
    def _analyze_parameter_impact(
        self,
        before_params: Dict[str, Any],
        after_params: Dict[str, Any],
        performance_change: Dict[str, Any]
    ) -> Dict[str, Any]:
        """分析参数影响"""
        impact = {}
        
        score_change = performance_change.get("score_change", 0)
        
        for param_name in after_params:
            if param_name in before_params:
                param_change = after_params[param_name] - before_params[param_name]
                if param_change != 0:
                    # 简单的相关性分析
                    impact[param_name] = {
                        "parameter_change": param_change,
                        "correlation_with_performance": score_change / param_change if param_change != 0 else 0
                    }
        
        return impact
    
    def _calculate_overall_impact(self, performance_change: Dict[str, Any]) -> str:
        """计算总体影响"""
        score_change = performance_change.get("score_change", 0)
        
        if score_change > 0.1:
            return "significantly_positive"
        elif score_change > 0.05:
            return "moderately_positive"
        elif score_change > -0.05:
            return "neutral"
        elif score_change > -0.1:
            return "moderately_negative"
        else:
            return "significantly_negative"
    
    def _calculate_impact_confidence(
        self,
        before_feedback: List[FeedbackEvent],
        after_feedback: List[FeedbackEvent]
    ) -> float:
        """计算影响置信度"""
        # 基于样本数量
        sample_confidence = min(1.0, (len(before_feedback) + len(after_feedback)) / 20.0)
        
        # 基于时间分布均匀性
        time_confidence = 0.8  # 简化假设
        
        return (sample_confidence + time_confidence) / 2
    
    def _estimate_historical_improvement(self, param_changes: Dict[str, float]) -> float:
        """基于历史数据估算改进"""
        # 简化实现：基于参数变化幅度估算
        total_change = sum(abs(change) for change in param_changes.values())
        
        # 假设适度的参数变化能带来适度的改进
        return min(0.2, total_change * 0.5)
    
    def _convert_to_memory_preference(
        self,
        params: Dict[str, Any],
        agent_role: str
    ) -> MemoryPreference:
        """转换为记忆偏好对象"""
        # 设置默认值
        default_preference = MemoryPreference(
            semantic_weight=1.0,
            episodic_weight=1.0,
            procedural_weight=1.0,
            max_semantic_memories=3,
            max_episodic_memories=2,
            max_procedural_memories=2,
            min_importance_threshold=0.3,
            min_relevance_threshold=0.2,
            usage_pattern=MemoryUsagePattern.BALANCED
        )
        
        # 用优化参数覆盖默认值
        for attr in default_preference.__dataclass_fields__:
            if attr in params:
                setattr(default_preference, attr, params[attr])
        
        return default_preference
    
    def _adjust_parameters_by_context(
        self,
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """基于上下文调整参数"""
        adjusted_params = params.copy()
        
        # 基于任务紧急程度调整
        if context.get("urgent", False):
            adjusted_params["max_semantic_memories"] = max(1, adjusted_params.get("max_semantic_memories", 3) - 1)
            adjusted_params["min_relevance_threshold"] = adjusted_params.get("min_relevance_threshold", 0.2) + 0.1
        
        # 基于复杂度调整
        complexity = context.get("complexity", "medium")
        if complexity == "high":
            adjusted_params["max_semantic_memories"] = adjusted_params.get("max_semantic_memories", 3) + 1
            adjusted_params["max_episodic_memories"] = adjusted_params.get("max_episodic_memories", 2) + 1
        elif complexity == "low":
            adjusted_params["max_semantic_memories"] = max(1, adjusted_params.get("max_semantic_memories", 3) - 1)
        
        return adjusted_params
    
    def _initialize_default_parameters(self):
        """初始化默认参数"""
        default_params = {
            "semantic_weight": 1.0,
            "episodic_weight": 1.0,
            "procedural_weight": 1.0,
            "max_semantic_memories": 3,
            "max_episodic_memories": 2,
            "max_procedural_memories": 2,
            "min_importance_threshold": 0.3,
            "min_relevance_threshold": 0.2,
            "recency_weight": 0.1,
            "domain_boost_factor": 1.2
        }
        
        # 为所有智能体角色设置默认参数
        for agent_role in AgentRole:
            self.current_parameters[agent_role.value] = default_params.copy()
    
    def _initialize_parameter_bounds(self):
        """初始化参数边界"""
        bounds = {
            "semantic_weight": (0.1, 3.0),
            "episodic_weight": (0.1, 3.0),
            "procedural_weight": (0.1, 3.0),
            "max_semantic_memories": (1, 10),
            "max_episodic_memories": (1, 8),
            "max_procedural_memories": (1, 8),
            "min_importance_threshold": (0.0, 1.0),
            "min_relevance_threshold": (0.0, 1.0),
            "recency_weight": (0.0, 1.0),
            "domain_boost_factor": (1.0, 2.0)
        }
        
        # 为所有智能体角色设置相同的边界
        for agent_role in AgentRole:
            self.parameter_bounds[agent_role.value] = bounds.copy()
    
    def _init_optimization_config(self) -> Dict[str, Any]:
        """初始化优化配置"""
        return {
            "min_feedback_count": 10,
            "optimization_interval": timedelta(hours=2),
            "confidence_threshold": 0.6,
            "improvement_threshold": 0.05,
            "max_optimizations_per_period": 3
        }
    
    def _init_feedback_analyzers(self) -> Dict[str, callable]:
        """初始化反馈分析器"""
        return {
            "trend_analyzer": self._analyze_feedback_trend,
            "problem_identifier": self._identify_problem_areas,
            "opportunity_finder": self._identify_improvement_opportunities
        }
    
    def _init_parameter_optimizers(self) -> Dict[str, callable]:
        """初始化参数优化器"""
        return {
            "gradient_descent": self._gradient_descent_optimization,
            "random_search": self._random_search_optimization,
            "bayesian_optimization": self._bayesian_optimization
        }
    
    def _init_learning_algorithms(self) -> Dict[str, callable]:
        """初始化学习算法"""
        return {
            "adaptive_learning_rate": self._adjust_learning_rate,
            "momentum_update": self._momentum_update,
            "stability_tracking": self._update_stability_score
        }
    
    def get_optimizer_statistics(self) -> Dict[str, Any]:
        """获取优化器统计信息"""
        return {
            "optimizer_stats": self.optimizer_stats,
            "active_agents": len(self.learning_states),
            "total_feedback_events": len(self.feedback_events),
            "total_optimizations": len(self.optimization_history),
            "average_improvement": self.optimizer_stats.get("average_improvement", 0.0),
            "learning_sessions": self.optimizer_stats.get("learning_sessions", 0)
        }

    def _gradient_descent_optimization(
        self,
        agent_role: str,
        current_params: Dict[str, Any],
        feedback_gradients: Dict[str, float],
        learning_rate: float = 0.01
    ) -> Dict[str, Any]:
        """使用梯度下降优化参数"""
        optimized_params = current_params.copy()
        
        # 获取学习状态
        learning_state = self.learning_states.get(agent_role)
        if not learning_state:
            return optimized_params
        
        # 应用梯度下降更新
        for param_name, gradient in feedback_gradients.items():
            if param_name in optimized_params:
                # 获取当前值
                current_value = optimized_params[param_name]
                
                # 计算更新量（包含动量）
                momentum = learning_state.momentum
                update = learning_rate * gradient
                
                # 如果有历史调整，应用动量
                if learning_state.parameter_adjustments:
                    last_adjustment = learning_state.parameter_adjustments[-1]
                    if param_name in last_adjustment:
                        momentum_update = momentum * last_adjustment[param_name]
                        update += momentum_update
                
                # 更新参数
                if isinstance(current_value, (int, float)):
                    new_value = current_value + update
                    
                    # 应用边界约束
                    if agent_role in self.parameter_bounds:
                        bounds = self.parameter_bounds[agent_role]
                        if param_name in bounds:
                            min_val, max_val = bounds[param_name]
                            new_value = max(min_val, min(max_val, new_value))
                    
                    optimized_params[param_name] = new_value
                elif isinstance(current_value, dict):
                    # 处理嵌套字典参数
                    for key, value in current_value.items():
                        if isinstance(value, (int, float)):
                            sub_gradient = gradient * 0.1  # 对子参数使用较小的学习率
                            optimized_params[param_name][key] = value + sub_gradient
        
        # 记录参数调整
        adjustment_record = {
            param_name: optimized_params[param_name] - current_params.get(param_name, 0)
            for param_name in optimized_params
            if param_name in current_params
        }
        
        if learning_state:
            learning_state.parameter_adjustments.append(adjustment_record)
            # 保持历史记录在合理范围内
            if len(learning_state.parameter_adjustments) > 100:
                learning_state.parameter_adjustments.pop(0)
        
        return optimized_params
    
    def _random_search_optimization(
        self,
        agent_role: str,
        current_params: Dict[str, Any],
        feedback_analysis: Dict[str, Any],
        num_samples: int = 50
    ) -> Dict[str, Any]:
        """使用随机搜索优化参数"""
        best_params = current_params.copy()
        best_score = feedback_analysis.get("overall_score", 0.0)
        
        # 获取参数边界
        bounds = self.parameter_bounds.get(agent_role, {})
        
        # 随机搜索
        for _ in range(num_samples):
            test_params = current_params.copy()
            
            # 为每个参数生成随机值
            for param_name, current_value in current_params.items():
                if param_name in bounds:
                    min_val, max_val = bounds[param_name]
                    # 在边界内生成随机值
                    if isinstance(current_value, (int, float)):
                        import random
                        test_params[param_name] = random.uniform(min_val, max_val)
                elif isinstance(current_value, (int, float)):
                    # 没有边界约束时，在当前值附近随机变化
                    import random
                    variation = current_value * 0.2  # 20%的变化范围
                    test_params[param_name] = current_value + random.uniform(-variation, variation)
            
            # 评估测试参数（简化版本）
            test_score = self._evaluate_parameter_set(test_params, feedback_analysis)
            
            # 如果更好，更新最佳参数
            if test_score > best_score:
                best_params = test_params.copy()
                best_score = test_score
        
        return best_params
    
    def _bayesian_optimization(
        self,
        agent_role: str,
        current_params: Dict[str, Any],
        feedback_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """使用贝叶斯优化（简化版本）"""
        # 这是一个简化的贝叶斯优化实现
        # 在实际应用中，可能需要使用专门的库如scikit-optimize
        
        # 对于简化版本，我们使用历史数据来指导搜索
        best_params = current_params.copy()
        
        # 基于历史性能数据选择最有希望的参数组合
        learning_state = self.learning_states.get(agent_role)
        if learning_state and learning_state.performance_history:
            # 找出表现最好的历史记录
            best_performance_idx = learning_state.performance_history.index(
                max(learning_state.performance_history)
            )
            
            # 如果有对应的参数调整记录，使用它
            if (best_performance_idx < len(learning_state.parameter_adjustments) and
                learning_state.parameter_adjustments):
                best_adjustment = learning_state.parameter_adjustments[best_performance_idx]
                
                # 应用历史最佳调整的变体
                for param_name, adjustment in best_adjustment.items():
                    if param_name in current_params:
                        # 在最佳调整附近搜索
                        current_value = current_params[param_name]
                        if isinstance(current_value, (int, float)):
                            # 在最佳调整值附近小幅变化
                            import random
                            noise = random.uniform(-0.1, 0.1) * abs(adjustment)
                            best_params[param_name] = current_value + adjustment + noise
        
        return best_params
    
    def _momentum_update(self, learning_state: LearningState):
        """动量更新"""
        # 简化的动量更新逻辑
        if len(learning_state.performance_history) >= 2:
            # 基于最近的性能变化调整动量
            recent_change = (learning_state.performance_history[-1] - 
                           learning_state.performance_history[-2])
            
            if recent_change > 0:
                # 性能提升，增加动量
                learning_state.momentum = min(0.9, learning_state.momentum + 0.1)
            else:
                # 性能下降，减少动量
                learning_state.momentum = max(0.1, learning_state.momentum - 0.1)
    
    def _evaluate_parameter_set(
        self,
        params: Dict[str, Any],
        feedback_analysis: Dict[str, Any]
    ) -> float:
        """评估参数集的质量"""
        # 简化的评估函数
        score = 0.0
        weight_sum = 0.0
        
        # 基于反馈分析计算评分
        for param_name, value in params.items():
            if isinstance(value, (int, float)):
                # 简化的评分逻辑
                if param_name in ["importance_weight", "relevance_threshold"]:
                    # 这些参数通常在0.3-0.9之间效果最好
                    optimal_score = 1.0 - abs(value - 0.6) / 0.6
                    score += optimal_score
                    weight_sum += 1.0
                elif param_name in ["memory_limit", "max_memories"]:
                    # 这些参数通常在适中范围效果最好
                    if isinstance(value, int):
                        optimal_score = 1.0 - abs(value - 20) / 20
                        optimal_score = max(0.0, optimal_score)
                        score += optimal_score
                        weight_sum += 1.0
        
        # 添加多样性奖励
        diversity_bonus = feedback_analysis.get("diversity_score", 0.0) * 0.1
        score += diversity_bonus
        weight_sum += 0.1
        
        return score / max(weight_sum, 1.0)


def create_adaptive_memory_optimizer(config: Optional[Dict[str, Any]] = None) -> AdaptiveMemoryOptimizer:
    """创建自适应记忆优化器"""
    return AdaptiveMemoryOptimizer(config) 