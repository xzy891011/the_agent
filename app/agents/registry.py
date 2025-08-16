"""
智能体注册表模块
统一管理智能体的创建、注册和生命周期
"""

import logging
from typing import Dict, Optional, Any, Protocol, runtime_checkable
from threading import Lock

logger = logging.getLogger(__name__)

@runtime_checkable
class AgentProtocol(Protocol):
    """智能体统一接口协议"""
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """运行智能体
        
        Args:
            state: 输入状态字典
            
        Returns:
            更新后的状态字典
        """
        ...
    
    def get_name(self) -> str:
        """获取智能体名称"""
        ...
    
    def get_description(self) -> str:
        """获取智能体描述"""
        ...


class AgentRegistry:
    """
    智能体注册表
    
    负责管理所有智能体的注册、获取和生命周期
    采用单例模式确保全局唯一
    """
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._agents: Dict[str, AgentProtocol] = {}
        self._agent_configs: Dict[str, Dict[str, Any]] = {}
        self._initialized = True
        logger.info("智能体注册表初始化完成")
    
    def register(
        self, 
        key: str, 
        agent: AgentProtocol,
        config: Optional[Dict[str, Any]] = None,
        override: bool = False
    ) -> None:
        """
        注册智能体
        
        Args:
            key: 智能体唯一标识
            agent: 智能体实例
            config: 智能体配置
            override: 是否覆盖已存在的智能体
        """
        if not isinstance(agent, AgentProtocol):
            raise TypeError(f"Agent must implement AgentProtocol, got {type(agent)}")
        
        if key in self._agents and not override:
            logger.warning(f"智能体 {key} 已存在，跳过注册。使用 override=True 强制覆盖")
            return
        
        self._agents[key] = agent
        if config:
            self._agent_configs[key] = config
        
        logger.info(f"成功注册智能体: {key} ({agent.get_name()})")
    
    def get(self, key: str) -> Optional[AgentProtocol]:
        """
        获取智能体
        
        Args:
            key: 智能体唯一标识
            
        Returns:
            智能体实例，如果不存在返回 None
        """
        agent = self._agents.get(key)
        if not agent:
            logger.warning(f"智能体 {key} 未注册")
        return agent
    
    def get_or_raise(self, key: str) -> AgentProtocol:
        """
        获取智能体，如果不存在则抛出异常
        
        Args:
            key: 智能体唯一标识
            
        Returns:
            智能体实例
            
        Raises:
            KeyError: 智能体未注册
        """
        agent = self.get(key)
        if agent is None:
            raise KeyError(f"智能体 {key} 未注册，请先在 Engine 中创建并注册")
        return agent
    
    def list_agents(self) -> Dict[str, str]:
        """
        列出所有已注册的智能体
        
        Returns:
            {key: name} 的字典
        """
        return {
            key: agent.get_name() 
            for key, agent in self._agents.items()
        }
    
    def get_config(self, key: str) -> Optional[Dict[str, Any]]:
        """
        获取智能体配置
        
        Args:
            key: 智能体唯一标识
            
        Returns:
            智能体配置字典
        """
        return self._agent_configs.get(key)
    
    def unregister(self, key: str) -> bool:
        """
        注销智能体
        
        Args:
            key: 智能体唯一标识
            
        Returns:
            是否成功注销
        """
        if key in self._agents:
            del self._agents[key]
            if key in self._agent_configs:
                del self._agent_configs[key]
            logger.info(f"成功注销智能体: {key}")
            return True
        return False
    
    def clear(self) -> None:
        """清空所有注册的智能体"""
        self._agents.clear()
        self._agent_configs.clear()
        logger.info("已清空所有智能体注册")
    
    def has_agent(self, key: str) -> bool:
        """
        检查智能体是否已注册
        
        Args:
            key: 智能体唯一标识
            
        Returns:
            是否已注册
        """
        return key in self._agents
    
    def get_all_agents(self) -> Dict[str, AgentProtocol]:
        """
        获取所有已注册的智能体
        
        Returns:
            包含所有智能体的字典副本
        """
        return self._agents.copy()


# 全局注册表实例
agent_registry = AgentRegistry()


def get_agent_registry() -> AgentRegistry:
    """获取全局智能体注册表实例"""
    return agent_registry
