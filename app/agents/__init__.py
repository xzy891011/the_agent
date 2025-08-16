"""智能体模块包 - 新架构专业智能体系统"""

# 新的专业智能体系统
from app.agents.langgraph_agent import LangGraphAgent
from app.agents.specialized_agents import (
    GeophysicsAgent,
    ReservoirAgent,
    EconomicsAgent,
    QualityControlAgent,
    GeneralAnalysisAgent,
    create_specialized_agent,
    get_available_agent_types,
    recommend_agent_for_request
)

# 智能体适配器用于新旧架构过渡（将逐步废弃）
from app.agents.agent_adapter import UnifiedAgent, AgentAdapter

__all__ = [
    # 新的专业智能体架构
    'LangGraphAgent',
    'GeophysicsAgent',
    'ReservoirAgent', 
    'EconomicsAgent',
    'QualityControlAgent',
    'GeneralAnalysisAgent',
    'create_specialized_agent',
    'get_available_agent_types',
    'recommend_agent_for_request',
    
    # 适配器（过渡期使用）
    'UnifiedAgent',
    'AgentAdapter',
] 