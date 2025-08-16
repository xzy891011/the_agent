"""
内存管理包 - 提供长期记忆存储和会话历史管理功能

第四阶段升级：完整的增强记忆系统和智能体集成
"""

# 传统记忆存储组件（向下兼容）
from app.core.memory.store import MemoryStore, MemoryItem
from app.core.memory.history_manager import HistoryManager, RemoveMessage
from app.core.memory.persistence import IsotopeCheckpointer

# LangGraph原生内存机制（向下兼容保留）
# from app.core.memory.langgraph_store import (
#     LangGraphMemoryStore, 
#     MemoryEntry, 
#     ElasticsearchVectorStore,
#     create_langgraph_store
# )
# from app.core.memory.memory_integration import (
#     MemoryIntegration,
#     MemoryContext,
#     create_memory_integration
# )

# 增强记忆系统组件
from app.core.memory.enhanced_memory_integration import (
    EnhancedMemoryIntegration,
    create_enhanced_memory_integration
)

# 记忆系统核心组件
from app.core.memory.enhanced_memory_namespace import MemoryNamespaceManager
from app.core.memory.agent_memory_preferences import AgentMemoryPreferenceManager
from app.core.memory.agent_memory_filter import AgentMemoryFilter
from app.core.memory.agent_memory_injector import AgentMemoryInjector
from app.core.memory.dynamic_prompt_manager import DynamicPromptManager
from app.core.memory.memory_relevance_scorer import MemoryRelevanceScorer
from app.core.memory.prompt_length_controller import PromptLengthController
from app.core.memory.memory_usage_monitor import MemoryUsageMonitor
from app.core.memory.adaptive_memory_optimizer import AdaptiveMemoryOptimizer

# 引擎适配器
from app.core.memory.engine_adapter import (
    MemoryAwareEngineAdapter,
    create_memory_aware_adapter
)

# 增强LangGraph存储
from app.core.memory.enhanced_langgraph_store import (
    EnhancedLangGraphMemoryStore,
    create_enhanced_langgraph_store
)

__all__ = [
    # 传统记忆存储（向下兼容）
    'MemoryStore',
    'MemoryItem', 
    'HistoryManager',
    'RemoveMessage',
    'IsotopeCheckpointer',
    
    # LangGraph原生内存机制（已弃用，向下兼容保留）
    # 'LangGraphMemoryStore',
    # 'MemoryEntry',
    # 'ElasticsearchVectorStore', 
    # 'create_langgraph_store',
    
    # 记忆集成层（已弃用，向下兼容保留）
    # 'MemoryIntegration',
    # 'MemoryContext',
    # 'create_memory_integration',
    
    # 增强记忆系统
    'EnhancedMemoryIntegration',
    'create_enhanced_memory_integration',
    
    # 记忆系统核心组件
    'MemoryNamespaceManager',
    'AgentMemoryPreferenceManager',
    'AgentMemoryFilter',
    'AgentMemoryInjector',
    'DynamicPromptManager',
    'MemoryRelevanceScorer',
    'PromptLengthController',
    'MemoryUsageMonitor',
    'AdaptiveMemoryOptimizer',
    
    # 引擎适配器
    'MemoryAwareEngineAdapter',
    'create_memory_aware_adapter',
    
    # 增强LangGraph存储
    'EnhancedLangGraphMemoryStore',
    'create_enhanced_langgraph_store'
]

# 版本信息
__version__ = "4.0.0"
__stage__ = "Enhanced Memory System - Full Agent Integration"
