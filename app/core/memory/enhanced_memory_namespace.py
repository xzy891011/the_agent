"""
增强记忆命名空间管理器 - 支持智能体感知的记忆系统

本模块扩展了原有的简单命名空间设计，引入了：
1. 智能体角色维度
2. 专业领域标签
3. 复合命名空间规则
4. 智能体间记忆隔离机制

命名空间设计：
原始：("memories", user_id, memory_type)
增强：("memories", user_id, agent_role, domain, memory_type)
"""

import logging
from typing import Dict, List, Tuple, Optional, Set, Any
from enum import Enum
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)


class AgentRole(str, Enum):
    """智能体角色枚举"""
    # 基础角色
    GEOPHYSICS_ANALYSIS = "geophysics_analysis"
    RESERVOIR_ENGINEERING = "reservoir_engineering"
    ECONOMIC_EVALUATION = "economic_evaluation"
    QUALITY_ASSURANCE = "quality_assurance"
    GENERAL_ANALYSIS = "general_analysis"
    
    # 扩展角色
    DATA_PROCESSING = "data_processing"
    EXPERT_ANALYSIS = "expert_analysis"
    VISUALIZATION = "visualization"
    SUPERVISOR = "supervisor"
    
    # 特殊角色
    SYSTEM = "system"
    SHARED = "shared"  # 跨智能体共享记忆


class DomainTag(str, Enum):
    """专业领域标签枚举"""
    # 地球物理领域
    SEISMIC_DATA = "seismic_data"
    WELL_LOG = "well_log"
    GEOLOGY = "geology"
    FORMATION_EVAL = "formation_eval"
    
    # 油藏工程领域
    RESERVOIR_SIM = "reservoir_sim"
    PRODUCTION_OPT = "production_opt"
    PRESSURE_ANALYSIS = "pressure_analysis"
    RECOVERY_FACTOR = "recovery_factor"
    
    # 经济评价领域
    NPV_CALCULATION = "npv_calculation"
    IRR_ANALYSIS = "irr_analysis"
    RISK_ASSESSMENT = "risk_assessment"
    COST_BENEFIT = "cost_benefit"
    
    # 数据处理领域
    DATA_VALIDATION = "data_validation"
    STATISTICAL_ANALYSIS = "statistical_analysis"
    DATA_VISUALIZATION = "data_visualization"
    
    # 通用领域
    GENERAL_KNOWLEDGE = "general_knowledge"
    PROCEDURAL_KNOWLEDGE = "procedural_knowledge"
    CROSS_DOMAIN = "cross_domain"


class MemoryType(str, Enum):
    """记忆类型枚举（与原有系统兼容）"""
    SEMANTIC = "semantic"      # 语义记忆（事实和概念）
    EPISODIC = "episodic"      # 情节记忆（特定事件）
    PROCEDURAL = "procedural"  # 程序记忆（技能和流程）


@dataclass
class EnhancedMemoryNamespace:
    """增强记忆命名空间数据类"""
    user_id: str
    agent_role: AgentRole
    domain: DomainTag
    memory_type: MemoryType
    sub_category: Optional[str] = None
    
    def to_tuple(self) -> Tuple[str, ...]:
        """转换为元组格式的命名空间"""
        base = ("memories", self.user_id, self.agent_role.value, self.domain.value, self.memory_type.value)
        if self.sub_category:
            return base + (self.sub_category,)
        return base
    
    def to_string(self) -> str:
        """转换为字符串格式"""
        return "/".join(self.to_tuple())
    
    @classmethod
    def from_tuple(cls, namespace_tuple: Tuple[str, ...]) -> 'EnhancedMemoryNamespace':
        """从元组创建命名空间对象"""
        if len(namespace_tuple) < 5:
            raise ValueError(f"命名空间元组长度不足: {namespace_tuple}")
        
        return cls(
            user_id=namespace_tuple[1],
            agent_role=AgentRole(namespace_tuple[2]),
            domain=DomainTag(namespace_tuple[3]),
            memory_type=MemoryType(namespace_tuple[4]),
            sub_category=namespace_tuple[5] if len(namespace_tuple) > 5 else None
        )
    
    @classmethod
    def from_legacy(cls, legacy_namespace: Tuple[str, ...]) -> 'EnhancedMemoryNamespace':
        """从传统命名空间转换为增强命名空间"""
        if len(legacy_namespace) == 3:
            # 原始格式：("memories", user_id, memory_type)
            return cls(
                user_id=legacy_namespace[1],
                agent_role=AgentRole.GENERAL_ANALYSIS,  # 默认角色
                domain=DomainTag.GENERAL_KNOWLEDGE,     # 默认领域
                memory_type=MemoryType(legacy_namespace[2])
            )
        else:
            raise ValueError(f"无法解析传统命名空间: {legacy_namespace}")


class MemoryNamespaceManager:
    """记忆命名空间管理器"""
    
    def __init__(self):
        """初始化命名空间管理器"""
        self.agent_domain_mapping = self._build_agent_domain_mapping()
        self.domain_keyword_mapping = self._build_domain_keyword_mapping()
        self.role_hierarchy = self._build_role_hierarchy()
        
        logger.info("增强记忆命名空间管理器初始化完成")
    
    def _build_agent_domain_mapping(self) -> Dict[AgentRole, List[DomainTag]]:
        """构建智能体角色到专业领域的映射"""
        return {
            AgentRole.GEOPHYSICS_ANALYSIS: [
                DomainTag.SEISMIC_DATA,
                DomainTag.WELL_LOG,
                DomainTag.GEOLOGY,
                DomainTag.FORMATION_EVAL
            ],
            AgentRole.RESERVOIR_ENGINEERING: [
                DomainTag.RESERVOIR_SIM,
                DomainTag.PRODUCTION_OPT,
                DomainTag.PRESSURE_ANALYSIS,
                DomainTag.RECOVERY_FACTOR
            ],
            AgentRole.ECONOMIC_EVALUATION: [
                DomainTag.NPV_CALCULATION,
                DomainTag.IRR_ANALYSIS,
                DomainTag.RISK_ASSESSMENT,
                DomainTag.COST_BENEFIT
            ],
            AgentRole.QUALITY_ASSURANCE: [
                DomainTag.DATA_VALIDATION,
                DomainTag.STATISTICAL_ANALYSIS
            ],
            AgentRole.GENERAL_ANALYSIS: [
                DomainTag.GENERAL_KNOWLEDGE,
                DomainTag.STATISTICAL_ANALYSIS,
                DomainTag.DATA_VISUALIZATION,
                DomainTag.CROSS_DOMAIN
            ],
            AgentRole.DATA_PROCESSING: [
                DomainTag.DATA_VALIDATION,
                DomainTag.STATISTICAL_ANALYSIS,
                DomainTag.DATA_VISUALIZATION
            ],
            AgentRole.EXPERT_ANALYSIS: [
                DomainTag.CROSS_DOMAIN,
                DomainTag.GENERAL_KNOWLEDGE
            ],
            AgentRole.VISUALIZATION: [
                DomainTag.DATA_VISUALIZATION
            ],
            AgentRole.SUPERVISOR: [
                DomainTag.PROCEDURAL_KNOWLEDGE,
                DomainTag.CROSS_DOMAIN
            ],
            AgentRole.SYSTEM: [
                DomainTag.PROCEDURAL_KNOWLEDGE,
                DomainTag.GENERAL_KNOWLEDGE
            ],
            AgentRole.SHARED: [
                DomainTag.GENERAL_KNOWLEDGE,
                DomainTag.CROSS_DOMAIN
            ]
        }
    
    def _build_domain_keyword_mapping(self) -> Dict[DomainTag, List[str]]:
        """构建专业领域到关键词的映射"""
        return {
            # 地球物理领域关键词
            DomainTag.SEISMIC_DATA: ["地震", "震波", "反射", "地震资料", "地震解释"],
            DomainTag.WELL_LOG: ["测井", "电阻率", "自然伽马", "声波", "井径"],
            DomainTag.GEOLOGY: ["地质", "构造", "地层", "岩性", "沉积"],
            DomainTag.FORMATION_EVAL: ["地层评价", "储层评价", "孔隙度", "渗透率", "饱和度"],
            
            # 油藏工程领域关键词
            DomainTag.RESERVOIR_SIM: ["油藏模拟", "数值模拟", "历史拟合", "预测"],
            DomainTag.PRODUCTION_OPT: ["产量优化", "井网优化", "开发方案", "采油"],
            DomainTag.PRESSURE_ANALYSIS: ["压力", "试井", "压降", "压力恢复"],
            DomainTag.RECOVERY_FACTOR: ["采收率", "驱替", "提高采收率", "EOR"],
            
            # 经济评价领域关键词
            DomainTag.NPV_CALCULATION: ["净现值", "NPV", "现金流", "贴现"],
            DomainTag.IRR_ANALYSIS: ["内部收益率", "IRR", "投资回报"],
            DomainTag.RISK_ASSESSMENT: ["风险评估", "不确定性", "敏感性分析"],
            DomainTag.COST_BENEFIT: ["成本效益", "经济效益", "投资分析"],
            
            # 数据处理领域关键词
            DomainTag.DATA_VALIDATION: ["数据验证", "质量检查", "异常检测"],
            DomainTag.STATISTICAL_ANALYSIS: ["统计分析", "回归", "相关性", "分布"],
            DomainTag.DATA_VISUALIZATION: ["可视化", "图表", "绘图", "展示"],
            
            # 通用领域关键词
            DomainTag.GENERAL_KNOWLEDGE: ["基础知识", "概念", "定义", "原理"],
            DomainTag.PROCEDURAL_KNOWLEDGE: ["流程", "步骤", "方法", "程序"],
            DomainTag.CROSS_DOMAIN: ["综合", "跨领域", "整体", "全面"]
        }
    
    def _build_role_hierarchy(self) -> Dict[AgentRole, int]:
        """构建角色层次结构（用于记忆共享权限）"""
        return {
            AgentRole.SUPERVISOR: 4,         # 最高权限，可访问所有记忆
            AgentRole.EXPERT_ANALYSIS: 3,    # 高权限，可访问跨领域记忆
            AgentRole.GEOPHYSICS_ANALYSIS: 2, # 专业权限，可访问相关专业记忆
            AgentRole.RESERVOIR_ENGINEERING: 2,
            AgentRole.ECONOMIC_EVALUATION: 2,
            AgentRole.QUALITY_ASSURANCE: 2,
            AgentRole.DATA_PROCESSING: 1,    # 基础权限，主要访问自己的记忆
            AgentRole.VISUALIZATION: 1,
            AgentRole.GENERAL_ANALYSIS: 1,
            AgentRole.SYSTEM: 5,             # 系统权限，特殊处理
            AgentRole.SHARED: 0              # 共享记忆，所有角色都可访问
        }
    
    def create_namespace(
        self,
        user_id: str,
        agent_role: str,
        memory_type: str,
        content: Optional[str] = None,
        domain_hint: Optional[str] = None
    ) -> EnhancedMemoryNamespace:
        """创建增强记忆命名空间"""
        # 转换角色枚举
        try:
            role_enum = AgentRole(agent_role)
        except ValueError:
            logger.warning(f"未知智能体角色: {agent_role}，使用默认角色")
            role_enum = AgentRole.GENERAL_ANALYSIS
        
        # 转换记忆类型枚举
        try:
            memory_type_enum = MemoryType(memory_type)
        except ValueError:
            logger.warning(f"未知记忆类型: {memory_type}，使用语义记忆")
            memory_type_enum = MemoryType.SEMANTIC
        
        # 智能推断专业领域
        domain = self._infer_domain(role_enum, content, domain_hint)
        
        namespace = EnhancedMemoryNamespace(
            user_id=user_id,
            agent_role=role_enum,
            domain=domain,
            memory_type=memory_type_enum
        )
        
        logger.debug(f"创建命名空间: {namespace.to_string()}")
        return namespace
    
    def _infer_domain(
        self,
        agent_role: AgentRole,
        content: Optional[str] = None,
        domain_hint: Optional[str] = None
    ) -> DomainTag:
        """智能推断专业领域"""
        # 如果有明确的领域提示
        if domain_hint:
            try:
                return DomainTag(domain_hint)
            except ValueError:
                logger.warning(f"无效的领域提示: {domain_hint}")
        
        # 根据智能体角色的默认领域
        role_domains = self.agent_domain_mapping.get(agent_role, [])
        
        # 如果有内容，基于关键词匹配
        if content and role_domains:
            content_lower = content.lower()
            
            # 计算每个领域的匹配分数
            domain_scores = {}
            for domain in role_domains:
                keywords = self.domain_keyword_mapping.get(domain, [])
                score = sum(1 for keyword in keywords if keyword in content_lower)
                if score > 0:
                    domain_scores[domain] = score
            
            # 选择得分最高的领域
            if domain_scores:
                best_domain = max(domain_scores, key=domain_scores.get)
                logger.debug(f"基于内容匹配推断领域: {best_domain} (得分: {domain_scores[best_domain]})")
                return best_domain
        
        # 使用角色的第一个默认领域
        if role_domains:
            return role_domains[0]
        
        # 最后的兜底选择
        return DomainTag.GENERAL_KNOWLEDGE
    
    def get_accessible_namespaces(
        self,
        requesting_agent_role: str,
        user_id: str,
        memory_type: Optional[str] = None
    ) -> List[EnhancedMemoryNamespace]:
        """获取指定智能体可访问的命名空间列表"""
        try:
            role_enum = AgentRole(requesting_agent_role)
        except ValueError:
            logger.warning(f"未知智能体角色: {requesting_agent_role}")
            role_enum = AgentRole.GENERAL_ANALYSIS
        
        accessible_namespaces = []
        
        # 自己的专业记忆
        own_domains = self.agent_domain_mapping.get(role_enum, [])
        for domain in own_domains:
            if memory_type:
                namespace = EnhancedMemoryNamespace(
                    user_id=user_id,
                    agent_role=role_enum,
                    domain=domain,
                    memory_type=MemoryType(memory_type)
                )
                accessible_namespaces.append(namespace)
            else:
                for mem_type in MemoryType:
                    namespace = EnhancedMemoryNamespace(
                        user_id=user_id,
                        agent_role=role_enum,
                        domain=domain,
                        memory_type=mem_type
                    )
                    accessible_namespaces.append(namespace)
        
        # 共享记忆
        shared_domains = [DomainTag.GENERAL_KNOWLEDGE, DomainTag.CROSS_DOMAIN]
        for domain in shared_domains:
            if memory_type:
                namespace = EnhancedMemoryNamespace(
                    user_id=user_id,
                    agent_role=AgentRole.SHARED,
                    domain=domain,
                    memory_type=MemoryType(memory_type)
                )
                accessible_namespaces.append(namespace)
            else:
                for mem_type in MemoryType:
                    namespace = EnhancedMemoryNamespace(
                        user_id=user_id,
                        agent_role=AgentRole.SHARED,
                        domain=domain,
                        memory_type=mem_type
                    )
                    accessible_namespaces.append(namespace)
        
        # 根据权限层次添加其他角色的记忆
        requesting_level = self.role_hierarchy.get(role_enum, 1)
        if requesting_level >= 3:  # 高权限角色可访问跨领域记忆
            for other_role, other_domains in self.agent_domain_mapping.items():
                if other_role != role_enum and other_role not in [AgentRole.SYSTEM, AgentRole.SHARED]:
                    # 只访问跨领域相关的记忆
                    cross_domain_domains = [DomainTag.CROSS_DOMAIN, DomainTag.GENERAL_KNOWLEDGE]
                    for domain in cross_domain_domains:
                        if domain in other_domains:
                            if memory_type:
                                namespace = EnhancedMemoryNamespace(
                                    user_id=user_id,
                                    agent_role=other_role,
                                    domain=domain,
                                    memory_type=MemoryType(memory_type)
                                )
                                accessible_namespaces.append(namespace)
        
        logger.debug(f"智能体 {requesting_agent_role} 可访问 {len(accessible_namespaces)} 个命名空间")
        return accessible_namespaces
    
    def convert_legacy_namespace(self, legacy_namespace: Tuple[str, ...]) -> EnhancedMemoryNamespace:
        """转换传统命名空间为增强命名空间"""
        return EnhancedMemoryNamespace.from_legacy(legacy_namespace)
    
    def get_namespace_statistics(self) -> Dict[str, Any]:
        """获取命名空间统计信息"""
        return {
            "total_agent_roles": len(AgentRole),
            "total_domain_tags": len(DomainTag),
            "total_memory_types": len(MemoryType),
            "agent_domain_mappings": {
                role.value: [domain.value for domain in domains]
                for role, domains in self.agent_domain_mapping.items()
            },
            "role_hierarchy": {
                role.value: level
                for role, level in self.role_hierarchy.items()
            }
        }


# 全局命名空间管理器实例
_namespace_manager = None

def get_namespace_manager() -> MemoryNamespaceManager:
    """获取全局命名空间管理器实例"""
    global _namespace_manager
    if _namespace_manager is None:
        _namespace_manager = MemoryNamespaceManager()
    return _namespace_manager 