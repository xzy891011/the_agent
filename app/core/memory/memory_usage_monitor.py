"""
记忆使用监控系统 - 阶段4.1：监控不同智能体的记忆使用效果

该模块负责：
1. 监控智能体记忆使用统计
2. 评估记忆使用效果
3. 分析记忆性能指标
4. 提供优化建议
5. 生成监控报告
"""

import logging
import json
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
from collections import defaultdict, deque
import statistics

from .enhanced_memory_namespace import AgentRole, DomainTag, MemoryType
from .enhanced_langgraph_store import EnhancedMemoryEntry
from .agent_memory_preferences import MemoryPreference, MemoryFeedback
from .memory_relevance_scorer import RelevanceScore, ScoringContext

logger = logging.getLogger(__name__)

class MetricType(str, Enum):
    """指标类型枚举"""
    USAGE_FREQUENCY = "usage_frequency"        # 使用频率
    RELEVANCE_ACCURACY = "relevance_accuracy"  # 相关性准确度
    RESPONSE_QUALITY = "response_quality"      # 响应质量
    TASK_COMPLETION = "task_completion"        # 任务完成度
    USER_SATISFACTION = "user_satisfaction"   # 用户满意度
    MEMORY_FRESHNESS = "memory_freshness"     # 记忆新鲜度
    CROSS_AGENT_SHARING = "cross_agent_sharing"  # 跨智能体共享
    ERROR_RATE = "error_rate"                 # 错误率

class PerformanceLevel(str, Enum):
    """性能级别枚举"""
    EXCELLENT = "excellent"    # 优秀
    GOOD = "good"             # 良好
    AVERAGE = "average"       # 一般
    POOR = "poor"            # 较差
    CRITICAL = "critical"    # 严重

@dataclass
class MemoryUsageEvent:
    """记忆使用事件"""
    event_id: str
    timestamp: datetime
    session_id: str
    agent_role: str
    memory_id: str
    memory_type: str
    event_type: str  # "access", "create", "update", "delete"
    context: Dict[str, Any]
    relevance_score: Optional[float] = None
    usage_result: Optional[Dict[str, Any]] = None
    performance_metrics: Dict[str, float] = field(default_factory=dict)

@dataclass
class AgentMetrics:
    """智能体指标"""
    agent_role: str
    total_memory_accesses: int = 0
    unique_memories_used: int = 0
    average_relevance_score: float = 0.0
    memory_hit_rate: float = 0.0
    task_completion_rate: float = 0.0
    average_response_quality: float = 0.0
    memory_freshness_score: float = 0.0
    cross_agent_usage_ratio: float = 0.0
    error_rate: float = 0.0
    performance_trend: str = "stable"  # "improving", "declining", "stable"
    last_updated: datetime = field(default_factory=datetime.now)

@dataclass
class MemoryPerformanceReport:
    """记忆性能报告"""
    report_id: str
    generation_time: datetime
    time_range: Tuple[datetime, datetime]
    agent_metrics: Dict[str, AgentMetrics]
    overall_statistics: Dict[str, Any]
    performance_insights: List[str]
    optimization_recommendations: List[str]
    detailed_analysis: Dict[str, Any]

class MemoryUsageMonitor:
    """记忆使用监控器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        
        # 数据存储
        self.usage_events: deque = deque(maxlen=10000)  # 保留最近1万个事件
        self.agent_metrics: Dict[str, AgentMetrics] = {}
        self.daily_summaries: Dict[str, Dict[str, Any]] = {}  # date -> summary
        
        # 监控配置
        self.monitoring_config = self._init_monitoring_config()
        self.metric_calculators = self._init_metric_calculators()
        self.performance_analyzers = self._init_performance_analyzers()
        
        # 缓存和优化
        self.metrics_cache: Dict[str, Any] = {}
        self.cache_ttl = timedelta(minutes=5)
        
        # 统计信息
        self.monitor_stats = {
            "total_events_recorded": 0,
            "reports_generated": 0,
            "monitoring_start_time": datetime.now(),
            "last_analysis_time": None
        }
    
    def record_memory_usage(
        self,
        session_id: str,
        agent_role: str,
        memory: EnhancedMemoryEntry,
        event_type: str,
        context: Dict[str, Any],
        relevance_score: Optional[float] = None,
        usage_result: Optional[Dict[str, Any]] = None
    ) -> str:
        """记录记忆使用事件"""
        event_id = f"{session_id}_{agent_role}_{memory.id}_{datetime.now().timestamp()}"
        
        event = MemoryUsageEvent(
            event_id=event_id,
            timestamp=datetime.now(),
            session_id=session_id,
            agent_role=agent_role,
            memory_id=memory.id,
            memory_type=memory.memory_type,
            event_type=event_type,
            context=context,
            relevance_score=relevance_score,
            usage_result=usage_result
        )
        
        # 计算性能指标
        event.performance_metrics = self._calculate_event_metrics(event, memory)
        
        # 存储事件
        self.usage_events.append(event)
        self.monitor_stats["total_events_recorded"] += 1
        
        # 更新智能体指标
        self._update_agent_metrics(event)
        
        # 检查是否需要生成告警
        self._check_performance_alerts(agent_role, event)
        
        return event_id
    
    def get_agent_performance(
        self,
        agent_role: str,
        time_range: Optional[Tuple[datetime, datetime]] = None
    ) -> AgentMetrics:
        """获取智能体性能指标"""
        if time_range:
            # 基于时间范围计算实时指标
            return self._calculate_agent_metrics_for_period(agent_role, time_range)
        else:
            # 返回缓存的指标
            return self.agent_metrics.get(agent_role, AgentMetrics(agent_role=agent_role))
    
    def generate_performance_report(
        self,
        time_range: Optional[Tuple[datetime, datetime]] = None,
        agent_roles: Optional[List[str]] = None
    ) -> MemoryPerformanceReport:
        """生成性能报告"""
        if not time_range:
            end_time = datetime.now()
            start_time = end_time - timedelta(days=7)  # 默认最近7天
            time_range = (start_time, end_time)
        
        # 筛选相关事件
        relevant_events = self._filter_events_by_time_range(time_range)
        if agent_roles:
            relevant_events = [e for e in relevant_events if e.agent_role in agent_roles]
        
        # 计算智能体指标
        agent_metrics = {}
        target_agents = agent_roles or list(set(e.agent_role for e in relevant_events))
        
        for agent_role in target_agents:
            agent_metrics[agent_role] = self._calculate_agent_metrics_for_period(
                agent_role, time_range
            )
        
        # 计算整体统计
        overall_stats = self._calculate_overall_statistics(relevant_events)
        
        # 生成洞察和建议
        insights = self._generate_performance_insights(agent_metrics, overall_stats)
        recommendations = self._generate_optimization_recommendations(agent_metrics, overall_stats)
        
        # 详细分析
        detailed_analysis = self._perform_detailed_analysis(relevant_events, agent_metrics)
        
        report = MemoryPerformanceReport(
            report_id=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            generation_time=datetime.now(),
            time_range=time_range,
            agent_metrics=agent_metrics,
            overall_statistics=overall_stats,
            performance_insights=insights,
            optimization_recommendations=recommendations,
            detailed_analysis=detailed_analysis
        )
        
        self.monitor_stats["reports_generated"] += 1
        self.monitor_stats["last_analysis_time"] = datetime.now()
        
        return report
    
    def analyze_memory_effectiveness(
        self,
        memory_id: str,
        time_range: Optional[Tuple[datetime, datetime]] = None
    ) -> Dict[str, Any]:
        """分析特定记忆的有效性"""
        relevant_events = [e for e in self.usage_events if e.memory_id == memory_id]
        
        if time_range:
            relevant_events = [e for e in relevant_events 
                             if time_range[0] <= e.timestamp <= time_range[1]]
        
        if not relevant_events:
            return {
                "memory_id": memory_id,
                "usage_count": 0,
                "effectiveness": "no_data",
                "analysis": "No usage data available for this memory"
            }
        
        # 计算有效性指标
        usage_count = len(relevant_events)
        average_relevance = statistics.mean([e.relevance_score for e in relevant_events 
                                           if e.relevance_score is not None])
        
        # 分析使用模式
        agent_usage = defaultdict(int)
        for event in relevant_events:
            agent_usage[event.agent_role] += 1
        
        # 时间分布分析
        time_distribution = self._analyze_time_distribution(relevant_events)
        
        # 效果评估
        effectiveness_score = self._calculate_memory_effectiveness(relevant_events)
        effectiveness_level = self._categorize_effectiveness(effectiveness_score)
        
        return {
            "memory_id": memory_id,
            "usage_count": usage_count,
            "average_relevance": average_relevance,
            "effectiveness_score": effectiveness_score,
            "effectiveness_level": effectiveness_level,
            "agent_usage_distribution": dict(agent_usage),
            "time_distribution": time_distribution,
            "recommendations": self._generate_memory_recommendations(
                effectiveness_score, agent_usage, relevant_events
            )
        }
    
    def detect_performance_anomalies(
        self,
        agent_role: Optional[str] = None,
        threshold: float = 2.0
    ) -> List[Dict[str, Any]]:
        """检测性能异常"""
        anomalies = []
        
        # 获取目标智能体
        target_agents = [agent_role] if agent_role else list(self.agent_metrics.keys())
        
        for agent in target_agents:
            agent_metrics = self.agent_metrics.get(agent)
            if not agent_metrics:
                continue
            
            # 检查各项指标的异常
            anomaly_checks = [
                ("relevance_accuracy", agent_metrics.average_relevance_score, 0.7),
                ("task_completion", agent_metrics.task_completion_rate, 0.8),
                ("error_rate", agent_metrics.error_rate, 0.1),
                ("memory_hit_rate", agent_metrics.memory_hit_rate, 0.5)
            ]
            
            for metric_name, current_value, normal_threshold in anomaly_checks:
                if metric_name == "error_rate":
                    # 错误率：值越高越异常
                    if current_value > normal_threshold:
                        anomalies.append({
                            "agent_role": agent,
                            "metric": metric_name,
                            "current_value": current_value,
                            "threshold": normal_threshold,
                            "severity": "high" if current_value > normal_threshold * 2 else "medium",
                            "description": f"{agent} error rate is {current_value:.2f}, above threshold {normal_threshold}"
                        })
                else:
                    # 其他指标：值越低越异常
                    if current_value < normal_threshold:
                        anomalies.append({
                            "agent_role": agent,
                            "metric": metric_name,
                            "current_value": current_value,
                            "threshold": normal_threshold,
                            "severity": "high" if current_value < normal_threshold * 0.5 else "medium",
                            "description": f"{agent} {metric_name} is {current_value:.2f}, below threshold {normal_threshold}"
                        })
        
        return anomalies
    
    def _calculate_event_metrics(
        self,
        event: MemoryUsageEvent,
        memory: EnhancedMemoryEntry
    ) -> Dict[str, float]:
        """计算事件的性能指标"""
        metrics = {}
        
        # 记忆新鲜度（基于最后访问时间）
        if memory.last_accessed:
            # 处理时间戳格式的转换
            if isinstance(memory.last_accessed, (int, float)):
                last_accessed_dt = datetime.fromtimestamp(memory.last_accessed)
            else:
                last_accessed_dt = memory.last_accessed
            
            days_since_access = (datetime.now() - last_accessed_dt).total_seconds() / (24 * 3600)
            freshness = 1.0 - min(1.0, days_since_access / 30)
            metrics["freshness"] = freshness
        
        # 使用频率评分
        if memory.access_count > 0:
            frequency_score = min(1.0, memory.access_count / 10.0)
            metrics["frequency_score"] = frequency_score
        
        # 相关性评分（如果提供）
        if event.relevance_score is not None:
            metrics["relevance"] = event.relevance_score
        
        return metrics
    
    def _update_agent_metrics(self, event: MemoryUsageEvent):
        """更新智能体指标"""
        agent_role = event.agent_role
        
        if agent_role not in self.agent_metrics:
            self.agent_metrics[agent_role] = AgentMetrics(agent_role=agent_role)
        
        metrics = self.agent_metrics[agent_role]
        
        # 更新访问计数
        metrics.total_memory_accesses += 1
        
        # 更新相关性分数
        if event.relevance_score is not None:
            current_avg = metrics.average_relevance_score
            total_accesses = metrics.total_memory_accesses
            metrics.average_relevance_score = (
                (current_avg * (total_accesses - 1) + event.relevance_score) / total_accesses
            )
        
        # 更新时间戳
        metrics.last_updated = datetime.now()
        
        # 定期重新计算复杂指标
        if metrics.total_memory_accesses % 10 == 0:
            self._recalculate_complex_metrics(agent_role)
    
    def _recalculate_complex_metrics(self, agent_role: str):
        """重新计算复杂指标"""
        # 获取该智能体的最近事件
        recent_events = [e for e in list(self.usage_events)[-1000:] 
                        if e.agent_role == agent_role]
        
        if not recent_events:
            return
        
        metrics = self.agent_metrics[agent_role]
        
        # 计算独特记忆使用数量
        unique_memories = len(set(e.memory_id for e in recent_events))
        metrics.unique_memories_used = unique_memories
        
        # 计算记忆命中率
        access_events = [e for e in recent_events if e.event_type == "access"]
        successful_accesses = [e for e in access_events 
                             if e.usage_result and e.usage_result.get("success", False)]
        if access_events:
            metrics.memory_hit_rate = len(successful_accesses) / len(access_events)
        
        # 计算新鲜度分数
        freshness_scores = [e.performance_metrics.get("freshness", 0.5) for e in recent_events]
        if freshness_scores:
            metrics.memory_freshness_score = statistics.mean(freshness_scores)
    
    def _calculate_agent_metrics_for_period(
        self,
        agent_role: str,
        time_range: Tuple[datetime, datetime]
    ) -> AgentMetrics:
        """计算指定时间段的智能体指标"""
        # 筛选相关事件
        relevant_events = [
            e for e in self.usage_events
            if e.agent_role == agent_role and time_range[0] <= e.timestamp <= time_range[1]
        ]
        
        if not relevant_events:
            return AgentMetrics(agent_role=agent_role)
        
        metrics = AgentMetrics(agent_role=agent_role)
        
        # 基础计数
        metrics.total_memory_accesses = len(relevant_events)
        metrics.unique_memories_used = len(set(e.memory_id for e in relevant_events))
        
        # 平均相关性分数
        relevance_scores = [e.relevance_score for e in relevant_events 
                          if e.relevance_score is not None]
        if relevance_scores:
            metrics.average_relevance_score = statistics.mean(relevance_scores)
        
        # 记忆命中率
        access_events = [e for e in relevant_events if e.event_type == "access"]
        successful_accesses = [e for e in access_events 
                             if e.usage_result and e.usage_result.get("success", False)]
        if access_events:
            metrics.memory_hit_rate = len(successful_accesses) / len(access_events)
        
        # 任务完成率
        task_events = [e for e in relevant_events 
                      if e.usage_result and "task_completed" in e.usage_result]
        if task_events:
            completed_tasks = sum(1 for e in task_events 
                                if e.usage_result.get("task_completed", False))
            metrics.task_completion_rate = completed_tasks / len(task_events)
        
        # 错误率
        error_events = [e for e in relevant_events 
                       if e.usage_result and e.usage_result.get("error", False)]
        metrics.error_rate = len(error_events) / len(relevant_events)
        
        # 新鲜度分数
        freshness_scores = [e.performance_metrics.get("freshness", 0.5) for e in relevant_events]
        if freshness_scores:
            metrics.memory_freshness_score = statistics.mean(freshness_scores)
        
        # 跨智能体使用比例
        cross_agent_events = [e for e in relevant_events 
                            if e.context.get("cross_agent_memory", False)]
        metrics.cross_agent_usage_ratio = len(cross_agent_events) / len(relevant_events)
        
        metrics.last_updated = datetime.now()
        return metrics
    
    def _filter_events_by_time_range(
        self,
        time_range: Tuple[datetime, datetime]
    ) -> List[MemoryUsageEvent]:
        """按时间范围筛选事件"""
        return [e for e in self.usage_events 
                if time_range[0] <= e.timestamp <= time_range[1]]
    
    def _calculate_overall_statistics(
        self,
        events: List[MemoryUsageEvent]
    ) -> Dict[str, Any]:
        """计算整体统计信息"""
        if not events:
            return {}
        
        stats = {
            "total_events": len(events),
            "unique_agents": len(set(e.agent_role for e in events)),
            "unique_memories": len(set(e.memory_id for e in events)),
            "unique_sessions": len(set(e.session_id for e in events)),
            "event_types": dict(defaultdict(int))
        }
        
        # 事件类型分布
        for event in events:
            stats["event_types"][event.event_type] = stats["event_types"].get(event.event_type, 0) + 1
        
        # 平均相关性分数
        relevance_scores = [e.relevance_score for e in events if e.relevance_score is not None]
        if relevance_scores:
            stats["average_relevance"] = statistics.mean(relevance_scores)
            stats["relevance_std"] = statistics.stdev(relevance_scores) if len(relevance_scores) > 1 else 0
        
        # 时间分析
        time_distribution = self._analyze_time_distribution(events)
        stats["time_distribution"] = time_distribution
        
        return stats
    
    def _analyze_time_distribution(self, events: List[MemoryUsageEvent]) -> Dict[str, Any]:
        """分析时间分布"""
        if not events:
            return {}
        
        # 按小时分组
        hourly_distribution = defaultdict(int)
        for event in events:
            hour = event.timestamp.hour
            hourly_distribution[hour] += 1
        
        # 按天分组
        daily_distribution = defaultdict(int)
        for event in events:
            day = event.timestamp.strftime("%Y-%m-%d")
            daily_distribution[day] += 1
        
        return {
            "hourly_distribution": dict(hourly_distribution),
            "daily_distribution": dict(daily_distribution),
            "peak_hour": max(hourly_distribution.items(), key=lambda x: x[1])[0] if hourly_distribution else None,
            "peak_day": max(daily_distribution.items(), key=lambda x: x[1])[0] if daily_distribution else None
        }
    
    def _generate_performance_insights(
        self,
        agent_metrics: Dict[str, AgentMetrics],
        overall_stats: Dict[str, Any]
    ) -> List[str]:
        """生成性能洞察"""
        insights = []
        
        if not agent_metrics:
            return ["No agent performance data available"]
        
        # 最佳和最差表现智能体
        best_performer = max(agent_metrics.values(), 
                           key=lambda m: m.average_relevance_score)
        worst_performer = min(agent_metrics.values(), 
                            key=lambda m: m.average_relevance_score)
        
        insights.append(f"最佳表现智能体: {best_performer.agent_role} "
                       f"(平均相关性: {best_performer.average_relevance_score:.3f})")
        insights.append(f"需要关注的智能体: {worst_performer.agent_role} "
                       f"(平均相关性: {worst_performer.average_relevance_score:.3f})")
        
        # 记忆使用效率分析
        efficient_agents = [m for m in agent_metrics.values() 
                          if m.memory_hit_rate > 0.8]
        if efficient_agents:
            agent_names = ", ".join([m.agent_role for m in efficient_agents])
            insights.append(f"记忆使用效率高的智能体: {agent_names}")
        
        # 跨智能体共享分析
        sharing_agents = [m for m in agent_metrics.values() 
                         if m.cross_agent_usage_ratio > 0.2]
        if sharing_agents:
            agent_names = ", ".join([m.agent_role for m in sharing_agents])
            insights.append(f"跨智能体记忆共享活跃: {agent_names}")
        
        # 整体趋势分析
        if overall_stats.get("average_relevance", 0) > 0.7:
            insights.append("整体记忆相关性表现良好")
        elif overall_stats.get("average_relevance", 0) < 0.5:
            insights.append("整体记忆相关性需要改进")
        
        return insights
    
    def _generate_optimization_recommendations(
        self,
        agent_metrics: Dict[str, AgentMetrics],
        overall_stats: Dict[str, Any]
    ) -> List[str]:
        """生成优化建议"""
        recommendations = []
        
        # 针对低效智能体的建议
        low_performance_agents = [m for m in agent_metrics.values() 
                                if m.average_relevance_score < 0.6]
        for agent in low_performance_agents:
            recommendations.append(
                f"建议优化 {agent.agent_role} 的记忆筛选策略，"
                f"当前平均相关性仅为 {agent.average_relevance_score:.3f}"
            )
        
        # 针对高错误率的建议
        high_error_agents = [m for m in agent_metrics.values() if m.error_rate > 0.1]
        for agent in high_error_agents:
            recommendations.append(
                f"建议检查 {agent.agent_role} 的记忆访问逻辑，"
                f"当前错误率为 {agent.error_rate:.3f}"
            )
        
        # 针对低记忆命中率的建议
        low_hit_rate_agents = [m for m in agent_metrics.values() if m.memory_hit_rate < 0.5]
        for agent in low_hit_rate_agents:
            recommendations.append(
                f"建议改进 {agent.agent_role} 的记忆索引策略，"
                f"当前命中率仅为 {agent.memory_hit_rate:.3f}"
            )
        
        # 整体优化建议
        if overall_stats.get("average_relevance", 0) < 0.7:
            recommendations.append("建议整体优化记忆相关性评分算法")
        
        if len(set(m.agent_role for m in agent_metrics.values() 
                  if m.cross_agent_usage_ratio > 0)) < 2:
            recommendations.append("建议增强跨智能体记忆共享机制")
        
        return recommendations
    
    def _perform_detailed_analysis(
        self,
        events: List[MemoryUsageEvent],
        agent_metrics: Dict[str, AgentMetrics]
    ) -> Dict[str, Any]:
        """执行详细分析"""
        analysis = {}
        
        # 记忆类型使用分析
        memory_type_usage = defaultdict(int)
        for event in events:
            memory_type_usage[event.memory_type] += 1
        analysis["memory_type_usage"] = dict(memory_type_usage)
        
        # 会话分析
        session_analysis = defaultdict(lambda: {"events": 0, "agents": set(), "unique_memories": set()})
        for event in events:
            session_analysis[event.session_id]["events"] += 1
            session_analysis[event.session_id]["agents"].add(event.agent_role)
            session_analysis[event.session_id]["unique_memories"].add(event.memory_id)
        
        # 转换为可序列化格式
        session_stats = {}
        for session_id, stats in session_analysis.items():
            session_stats[session_id] = {
                "events": stats["events"],
                "agent_count": len(stats["agents"]),
                "memory_count": len(stats["unique_memories"])
            }
        analysis["session_analysis"] = session_stats
        
        # 性能趋势分析
        performance_trends = {}
        for agent_role, metrics in agent_metrics.items():
            # 简化的趋势分析
            if metrics.average_relevance_score > 0.7:
                trend = "positive"
            elif metrics.average_relevance_score < 0.5:
                trend = "negative"
            else:
                trend = "stable"
            performance_trends[agent_role] = trend
        analysis["performance_trends"] = performance_trends
        
        return analysis
    
    def _calculate_memory_effectiveness(self, events: List[MemoryUsageEvent]) -> float:
        """计算记忆有效性分数"""
        if not events:
            return 0.0
        
        # 基于多个因素计算
        factors = []
        
        # 使用频率因子
        usage_frequency = len(events) / max(1, (events[-1].timestamp - events[0].timestamp).days)
        frequency_score = min(1.0, usage_frequency / 5.0)  # 假设每天5次使用为满分
        factors.append(frequency_score)
        
        # 相关性因子
        relevance_scores = [e.relevance_score for e in events if e.relevance_score is not None]
        if relevance_scores:
            avg_relevance = statistics.mean(relevance_scores)
            factors.append(avg_relevance)
        
        # 成功使用因子
        successful_uses = [e for e in events 
                          if e.usage_result and e.usage_result.get("success", False)]
        success_rate = len(successful_uses) / len(events)
        factors.append(success_rate)
        
        return statistics.mean(factors) if factors else 0.0
    
    def _categorize_effectiveness(self, effectiveness_score: float) -> str:
        """分类有效性级别"""
        if effectiveness_score >= 0.8:
            return "excellent"
        elif effectiveness_score >= 0.6:
            return "good"
        elif effectiveness_score >= 0.4:
            return "average"
        elif effectiveness_score >= 0.2:
            return "poor"
        else:
            return "critical"
    
    def _generate_memory_recommendations(
        self,
        effectiveness_score: float,
        agent_usage: Dict[str, int],
        events: List[MemoryUsageEvent]
    ) -> List[str]:
        """为特定记忆生成建议"""
        recommendations = []
        
        if effectiveness_score < 0.3:
            recommendations.append("建议考虑删除此记忆，有效性较低")
        elif effectiveness_score < 0.6:
            recommendations.append("建议更新记忆内容，提高相关性")
        
        # 基于使用模式的建议
        if len(agent_usage) == 1:
            recommendations.append("记忆仅被单一智能体使用，可考虑增强跨智能体共享")
        elif len(agent_usage) > 3:
            recommendations.append("记忆被多个智能体使用，可考虑提升为通用知识")
        
        # 基于时间模式的建议
        recent_events = [e for e in events 
                        if (datetime.now() - e.timestamp).days <= 7]
        if len(recent_events) == 0:
            recommendations.append("记忆最近未被使用，可考虑归档")
        
        return recommendations
    
    def _check_performance_alerts(self, agent_role: str, event: MemoryUsageEvent):
        """检查性能告警"""
        # 这里可以实现实时告警逻辑
        if event.relevance_score is not None and event.relevance_score < 0.3:
            self.logger.warning(f"Low relevance score detected for {agent_role}: {event.relevance_score}")
        
        if event.usage_result and event.usage_result.get("error", False):
            self.logger.warning(f"Memory usage error for {agent_role}: {event.usage_result.get('error_message', 'Unknown error')}")
    
    def _init_monitoring_config(self) -> Dict[str, Any]:
        """初始化监控配置"""
        return {
            "alert_thresholds": {
                "low_relevance": 0.3,
                "high_error_rate": 0.1,
                "low_hit_rate": 0.5
            },
            "analysis_intervals": {
                "real_time": timedelta(minutes=1),
                "short_term": timedelta(hours=1),
                "daily": timedelta(days=1),
                "weekly": timedelta(weeks=1)
            },
            "retention_policy": {
                "events": timedelta(days=30),
                "summaries": timedelta(days=90),
                "reports": timedelta(days=365)
            }
        }
    
    def _init_metric_calculators(self) -> Dict[str, callable]:
        """初始化指标计算器"""
        return {
            "relevance_accuracy": self._calculate_relevance_accuracy,
            "memory_freshness": self._calculate_memory_freshness,
            "cross_agent_sharing": self._calculate_cross_agent_sharing,
            "task_completion": self._calculate_task_completion
        }
    
    def _init_performance_analyzers(self) -> Dict[str, callable]:
        """初始化性能分析器"""
        return {
            "trend_analyzer": self._analyze_trends,
            "anomaly_detector": self._detect_anomalies,
            "efficiency_calculator": self._calculate_efficiency
        }
    
    def get_monitoring_statistics(self) -> Dict[str, Any]:
        """获取监控统计信息"""
        return {
            "monitor_stats": self.monitor_stats,
            "active_agents": len(self.agent_metrics),
            "total_events": len(self.usage_events),
            "cache_size": len(self.metrics_cache),
            "uptime": (datetime.now() - self.monitor_stats["monitoring_start_time"]).total_seconds()
        }

    def _calculate_relevance_accuracy(self, agent_role: str, events: List[MemoryUsageEvent]) -> float:
        """计算相关性准确度"""
        if not events:
            return 0.0
        
        # 获取有相关性评分的事件
        scored_events = [e for e in events if e.relevance_score is not None]
        if not scored_events:
            return 0.0
        
        # 计算平均相关性评分
        avg_relevance = statistics.mean([e.relevance_score for e in scored_events])
        
        # 计算使用成功率
        successful_events = [e for e in scored_events 
                           if e.usage_result and e.usage_result.get("success", False)]
        success_rate = len(successful_events) / len(scored_events)
        
        # 综合评分（相关性评分权重0.7，成功率权重0.3）
        accuracy = avg_relevance * 0.7 + success_rate * 0.3
        
        return min(1.0, max(0.0, accuracy))
    
    def _calculate_memory_freshness(self, agent_role: str, events: List[MemoryUsageEvent]) -> float:
        """计算记忆新鲜度"""
        if not events:
            return 0.0
        
        # 计算最近使用的事件比例
        now = datetime.now()
        recent_events = [e for e in events if (now - e.timestamp).total_seconds() <= 7 * 24 * 3600]
        
        if not events:
            return 0.0
        
        freshness_score = len(recent_events) / len(events)
        return min(1.0, max(0.0, freshness_score))
    
    def _calculate_cross_agent_sharing(self, agent_role: str, events: List[MemoryUsageEvent]) -> float:
        """计算跨智能体共享指标"""
        if not events:
            return 0.0
        
        # 计算该智能体使用的记忆被其他智能体使用的比例
        memory_ids = set(e.memory_id for e in events)
        
        if not memory_ids:
            return 0.0
        
        # 统计这些记忆被多少不同智能体使用
        all_events = list(self.usage_events)
        shared_memories = 0
        
        for memory_id in memory_ids:
            agents_using_memory = set(e.agent_role for e in all_events 
                                    if e.memory_id == memory_id)
            if len(agents_using_memory) > 1:
                shared_memories += 1
        
        sharing_ratio = shared_memories / len(memory_ids)
        return min(1.0, max(0.0, sharing_ratio))
    
    def _calculate_task_completion(self, agent_role: str, events: List[MemoryUsageEvent]) -> float:
        """计算任务完成度"""
        if not events:
            return 0.0
        
        # 计算成功完成的任务比例
        completion_events = [e for e in events 
                           if e.usage_result and e.usage_result.get("task_completed", False)]
        
        if not events:
            return 0.0
        
        completion_rate = len(completion_events) / len(events)
        return min(1.0, max(0.0, completion_rate))
    
    def _analyze_trends(self, agent_role: str, events: List[MemoryUsageEvent]) -> Dict[str, Any]:
        """分析趋势"""
        if len(events) < 2:
            return {"trend": "stable", "confidence": 0.0}
        
        # 计算最近和历史的表现
        sorted_events = sorted(events, key=lambda e: e.timestamp)
        mid_point = len(sorted_events) // 2
        
        historical_events = sorted_events[:mid_point]
        recent_events = sorted_events[mid_point:]
        
        # 计算两个时期的平均相关性
        hist_relevance = statistics.mean([e.relevance_score for e in historical_events 
                                        if e.relevance_score is not None]) or 0.0
        recent_relevance = statistics.mean([e.relevance_score for e in recent_events 
                                          if e.relevance_score is not None]) or 0.0
        
        # 判断趋势
        if recent_relevance > hist_relevance + 0.05:
            trend = "improving"
        elif recent_relevance < hist_relevance - 0.05:
            trend = "declining"
        else:
            trend = "stable"
        
        confidence = abs(recent_relevance - hist_relevance) * 2
        confidence = min(1.0, max(0.0, confidence))
        
        return {
            "trend": trend,
            "confidence": confidence,
            "historical_score": hist_relevance,
            "recent_score": recent_relevance
        }
    
    def _detect_anomalies(self, agent_role: str, events: List[MemoryUsageEvent]) -> List[Dict[str, Any]]:
        """检测异常"""
        if len(events) < 5:
            return []
        
        anomalies = []
        
        # 检测相关性异常
        relevance_scores = [e.relevance_score for e in events if e.relevance_score is not None]
        if relevance_scores:
            avg_relevance = statistics.mean(relevance_scores)
            std_relevance = statistics.stdev(relevance_scores) if len(relevance_scores) > 1 else 0
            
            for event in events:
                if event.relevance_score is not None:
                    if abs(event.relevance_score - avg_relevance) > 2 * std_relevance:
                        anomalies.append({
                            "type": "relevance_anomaly",
                            "event_id": event.event_id,
                            "timestamp": event.timestamp,
                            "score": event.relevance_score,
                            "expected_range": (avg_relevance - std_relevance, avg_relevance + std_relevance)
                        })
        
        return anomalies
    
    def _calculate_efficiency(self, agent_role: str, events: List[MemoryUsageEvent]) -> float:
        """计算效率"""
        if not events:
            return 0.0
        
        # 计算成功率
        successful_events = [e for e in events 
                           if e.usage_result and e.usage_result.get("success", False)]
        success_rate = len(successful_events) / len(events)
        
        # 计算平均相关性
        relevance_scores = [e.relevance_score for e in events if e.relevance_score is not None]
        avg_relevance = statistics.mean(relevance_scores) if relevance_scores else 0.0
        
        # 综合效率评分
        efficiency = (success_rate * 0.6) + (avg_relevance * 0.4)
        return min(1.0, max(0.0, efficiency))


def create_memory_usage_monitor(config: Optional[Dict[str, Any]] = None) -> MemoryUsageMonitor:
    """创建记忆使用监控器"""
    return MemoryUsageMonitor(config) 