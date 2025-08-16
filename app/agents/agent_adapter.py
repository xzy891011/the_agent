"""
Agent Adapter for Architecture Migration (过渡期使用)
智能体适配器，支持向新架构迁移
注意：此文件仅用于过渡期，新项目请直接使用专业智能体架构
"""

import logging
from typing import Dict, Any, Optional, Union, List
from datetime import datetime

from app.core.state import IsotopeSystemState
from app.agents.langgraph_agent import LangGraphAgent, create_langgraph_agent

logger = logging.getLogger(__name__)


class AgentAdapter:
    """
    智能体适配器，用于迁移到新架构
    注意：此类将在迁移完成后废弃
    """
    
    def __init__(self, use_new_architecture: bool = True):
        """
        初始化适配器
        
        Args:
            use_new_architecture: 是否使用新架构，默认True（推荐）
        """
        self.use_new_architecture = use_new_architecture
        if not use_new_architecture:
            logger.warning("旧架构已废弃，建议使用新的专业智能体架构")
        logger.info(f"AgentAdapter初始化，使用{'新' if use_new_architecture else '已废弃的旧'}架构")
    
    def create_agent(
        self,
        name: str,
        role: str,
        llm: Any,
        tools: Optional[List[Any]] = None,
        capabilities: Optional[List[str]] = None,
        config: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> LangGraphAgent:
        """
        创建智能体，现在只支持新架构
        
        Args:
            name: 智能体名称
            role: 智能体角色
            llm: 语言模型
            tools: 工具列表（已废弃，请使用capabilities）
            capabilities: 能力列表（新架构使用）
            config: 配置参数
            **kwargs: 其他参数
            
        Returns:
            LangGraphAgent实例
        """
        if not self.use_new_architecture:
            logger.error("旧架构已完全移除，强制使用新架构")
            self.use_new_architecture = True
        
        # 使用新的LangGraph架构
        logger.info(f"创建新架构LangGraphAgent: {name}")
        return create_langgraph_agent(
            name=name,
            role=role,
            llm=llm,
            capabilities=capabilities,
            config=config
        )
    
    def migrate_agent(self, old_agent: Any) -> LangGraphAgent:
        """
        将旧架构智能体迁移到新架构
        注意：旧架构已移除，此方法仅做兼容性保留
        
        Args:
            old_agent: 旧架构智能体（已废弃）
            
        Returns:
            新架构智能体
        """
        logger.warning("旧架构已移除，无法迁移。请使用create_specialized_agent创建新智能体")
        
        # 提取基本信息
        name = getattr(old_agent, 'name', 'migrated_agent')
        role = getattr(old_agent, 'agent_role', 'general_analysis')
        
        # 获取LLM（如果有）
        llm = getattr(old_agent, 'llm', None)
        if llm is None:
            from app.utils.qwen_chat import SFChatOpenAI
            llm = SFChatOpenAI(model="Qwen/Qwen2.5-72B-Instruct", temperature=0.1)
        
        # 创建新架构智能体
        new_agent = create_langgraph_agent(
            name=name,
            role=role,
            llm=llm,
            capabilities=[],
            config={}
        )
        
        logger.info(f"已创建新架构智能体替代: {name}")
        return new_agent


class UnifiedAgent:
    """
    统一智能体接口，现在只支持新架构
    注意：此类将在迁移完成后废弃
    """
    
    def __init__(
        self,
        agent: LangGraphAgent,
        adapter: Optional[AgentAdapter] = None
    ):
        """
        初始化统一智能体
        
        Args:
            agent: 新架构智能体实例
            adapter: 适配器实例
        """
        self.agent = agent
        self.adapter = adapter or AgentAdapter()
        self.is_new_architecture = True  # 现在只支持新架构
        
        logger.info(f"创建UnifiedAgent: {agent.name}, 架构: 新架构")
    
    def run(self, state: IsotopeSystemState) -> IsotopeSystemState:
        """
        运行智能体
        
        Args:
            state: 系统状态
            
        Returns:
            更新后的状态
        """
        start_time = datetime.now()
        
        try:
            # 记录开始
            logger.info(f"UnifiedAgent {self.agent.name} 开始运行")
            
            # 调用新架构智能体的run方法
            result = self.agent.run(state)
            
            # 记录完成
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(f"UnifiedAgent {self.agent.name} 运行完成，耗时: {elapsed:.2f}秒")
            
            return result
            
        except Exception as e:
            logger.error(f"UnifiedAgent {self.agent.name} 运行失败: {e}")
            raise
    
    def migrate_to_new_architecture(self) -> 'UnifiedAgent':
        """
        迁移到新架构（现在已经是新架构）
        
        Returns:
            自身（已经是新架构）
        """
        logger.info(f"智能体 {self.agent.name} 已经是新架构")
        return self
    
    @property
    def name(self) -> str:
        """获取智能体名称"""
        return self.agent.name
    
    @property
    def role(self) -> str:
        """获取智能体角色"""
        return getattr(self.agent, 'role', 'unknown')


def create_unified_agent(
    name: str,
    role: str,
    llm: Any,
    use_new_architecture: bool = True,
    **kwargs
) -> UnifiedAgent:
    """
    工厂函数：创建统一智能体（现在只支持新架构）
    
    Args:
        name: 智能体名称
        role: 智能体角色
        llm: 语言模型
        use_new_architecture: 是否使用新架构（现在强制为True）
        **kwargs: 其他参数
        
    Returns:
        UnifiedAgent实例
    """
    if not use_new_architecture:
        logger.warning("旧架构已移除，强制使用新架构")
        use_new_architecture = True
        
    adapter = AgentAdapter(use_new_architecture=use_new_architecture)
    
    agent = adapter.create_agent(
        name=name,
        role=role,
        llm=llm,
        **kwargs
    )
    
    return UnifiedAgent(agent, adapter) 