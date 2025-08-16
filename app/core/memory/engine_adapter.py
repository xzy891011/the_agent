"""
Engine内存层适配器 - 将增强记忆系统集成到现有Engine

本模块负责：
1. 在Engine初始化时集成增强记忆系统
2. 在消息处理过程中自动提取和利用智能体记忆
3. 提供记忆感知的智能体执行环境
4. 确保向下兼容现有功能
"""

import logging
from typing import Dict, List, Any, Optional, Callable
from dataclasses import asdict

from app.core.memory.enhanced_memory_integration import (
    EnhancedMemoryIntegration, 
    AgentMemoryContext, 
    create_enhanced_memory_integration
)
from app.core.state import IsotopeSystemState
from langchain.schema import SystemMessage

logger = logging.getLogger(__name__)

class MemoryAwareEngineAdapter:
    """内存感知的Engine适配器（增强版本）"""
    
    def __init__(self, enhanced_memory_integration: EnhancedMemoryIntegration):
        """
        初始化内存感知适配器
        
        Args:
            enhanced_memory_integration: 增强记忆集成实例
        """
        self.enhanced_memory_integration = enhanced_memory_integration
        self.enabled = True
        self.auto_extract = True
        self.auto_enhance = True
        
        logger.info("增强内存感知Engine适配器初始化完成")
    
    def pre_execution_hook(self, state: IsotopeSystemState, agent_role: str = "system") -> IsotopeSystemState:
        """执行前钩子 - 使用智能体记忆增强状态"""
        if not self.enabled or not self.auto_enhance:
            return state
        
        try:
            # 获取智能体记忆上下文
            memory_context = self.enhanced_memory_integration.enhance_state_with_agent_memories(
                state, 
                agent_role=agent_role,
                query=self._extract_query_from_state(state)
            )
            
            # 将记忆上下文添加到状态中
            if 'memory_context' not in state:
                state['memory_context'] = memory_context
            
            # 如果有相关记忆，将其添加到系统提示中
            if memory_context.confidence_score > 0.3:
                self._inject_memory_into_system_prompt(state, memory_context)
            
            logger.debug(f"智能体 {agent_role} 状态记忆增强完成，置信度: {memory_context.confidence_score:.2f}")
            return state
            
        except Exception as e:
            logger.error(f"执行前记忆增强失败: {e}")
            return state
    
    def post_execution_hook(self, state: IsotopeSystemState, agent_role: str = "system", result: Any = None) -> IsotopeSystemState:
        """执行后钩子 - 提取和保存智能体记忆"""
        if not self.enabled or not self.auto_extract:
            return state
        
        try:
            # 从状态中提取智能体特定的记忆
            session_id = state.get('metadata', {}).get('session_id')
            extracted_memories = self.enhanced_memory_integration.extract_memories_from_state(
                state, 
                agent_role=agent_role,
                session_id=session_id
            )
            
            # 记录提取的记忆数量
            if extracted_memories:
                if 'extracted_memories' not in state:
                    state['extracted_memories'] = []
                state['extracted_memories'].extend(extracted_memories)
                
                logger.debug(f"从智能体 {agent_role} 状态中提取了 {len(extracted_memories)} 条新记忆")
            
            return state
            
        except Exception as e:
            logger.error(f"执行后记忆提取失败: {e}")
            return state
    
    def session_end_hook(self, state: IsotopeSystemState, agent_role: str = "system", session_summary: str = "") -> Optional[str]:
        """会话结束钩子 - 保存智能体交互记忆"""
        if not self.enabled:
            return None
        
        try:
            # 生成会话摘要（如果没有提供）
            if not session_summary:
                session_summary = self._generate_session_summary(state)
            
            # 保存智能体交互记忆
            session_id = state.get('metadata', {}).get('session_id')
            memory_id = self.enhanced_memory_integration.save_agent_interaction_memory(
                state=state,
                agent_role=agent_role,
                interaction_summary=session_summary,
                session_id=session_id
            )
            
            if memory_id:
                logger.info(f"智能体 {agent_role} 会话记忆保存成功: {memory_id}")
            
            return memory_id
            
        except Exception as e:
            logger.error(f"会话结束记忆保存失败: {e}")
            return None
    
    def get_memory_context_for_agent(self, state: IsotopeSystemState, 
                                   agent_role: str = "system") -> Optional[AgentMemoryContext]:
        """为特定智能体获取记忆上下文"""
        try:
            if 'memory_context' not in state:
                # 动态生成智能体记忆上下文
                memory_context = self.enhanced_memory_integration.enhance_state_with_agent_memories(
                    state, 
                    agent_role=agent_role,
                    query=self._extract_query_from_state(state)
                )
                state['memory_context'] = memory_context
            
            return state['memory_context']
            
        except Exception as e:
            logger.error(f"获取智能体 {agent_role} 记忆上下文失败: {e}")
            return None
    
    def add_memory_to_prompt(self, base_prompt: str, memory_context: AgentMemoryContext) -> str:
        """将智能体记忆信息添加到提示中"""
        try:
            if memory_context.confidence_score < 0.2:
                return base_prompt  # 记忆置信度太低，不添加
            
            memory_section = f"\n## 相关记忆信息 (智能体: {memory_context.agent_role})\n"
            
            # 添加记忆摘要
            memory_section += f"记忆摘要: {memory_context.memory_summary}\n"
            
            # 添加具体记忆内容
            if memory_context.semantic_memories:
                memory_section += "\n### 相关知识:\n"
                for i, mem in enumerate(memory_context.semantic_memories[:2], 1):
                    content = mem.content[:200] if hasattr(mem, 'content') else str(mem)[:200]
                    memory_section += f"{i}. {content}\n"
            
            if memory_context.procedural_memories:
                memory_section += "\n### 相关方法:\n"
                for i, mem in enumerate(memory_context.procedural_memories[:1], 1):
                    content = mem.content[:200] if hasattr(mem, 'content') else str(mem)[:200]
                    memory_section += f"{i}. {content}\n"
            
            if memory_context.episodic_memories:
                memory_section += "\n### 相关经验:\n"
                for i, mem in enumerate(memory_context.episodic_memories[:1], 1):
                    content = mem.content[:150] if hasattr(mem, 'content') else str(mem)[:150]
                    memory_section += f"{i}. {content}\n"
            
            # 添加领域覆盖信息
            if memory_context.domain_coverage:
                memory_section += f"\n### 覆盖领域: {', '.join(memory_context.domain_coverage)}\n"
            
            memory_section += f"\n(记忆置信度: {memory_context.confidence_score:.1%})\n"
            memory_section += "---\n"
            
            return memory_section + base_prompt
            
        except Exception as e:
            logger.error(f"添加记忆到提示失败: {e}")
            return base_prompt
    
    def manual_save_memory(self, user_id: str, content: str, agent_role: str = "system",
                          memory_type: str = "semantic", metadata: Optional[Dict] = None) -> Optional[str]:
        """手动保存智能体记忆"""
        try:
            # 构建状态用于保存
            state = {
                'metadata': {
                    'user_id': user_id,
                    'session_id': f"manual_{user_id}"
                },
                'messages': [],
                'tool_results': []
            }
            
            # 使用增强记忆系统保存
            memory_id = self.enhanced_memory_integration.save_agent_interaction_memory(
                state=state,
                agent_role=agent_role,
                interaction_summary=content,
                session_id=f"manual_{user_id}"
            )
            
            logger.info(f"手动保存智能体 {agent_role} 记忆成功: {memory_id}")
            return memory_id
                
        except Exception as e:
            logger.error(f"手动保存记忆失败: {e}")
            return None
    
    def search_memories(self, user_id: str, query: str, agent_role: str = "system",
                       memory_type: Optional[str] = None, limit: int = 5) -> List[Dict]:
        """搜索智能体记忆"""
        try:
            # 使用增强记忆系统搜索
            memories = self.enhanced_memory_integration.enhanced_store.search_agent_memories(
                user_id=user_id,
                requesting_agent_role=agent_role,
                query=query,
                limit=limit,
                memory_type=memory_type
            )
            
            # 转换为字典格式
            result = []
            for memory in memories:
                result.append({
                    'content': memory.content,
                    'memory_type': memory.memory_type,
                    'agent_role': memory.agent_role,
                    'domain': memory.domain,
                    'importance_score': memory.importance_score,
                    'created_at': memory.created_at
                })
            
            return result
            
        except Exception as e:
            logger.error(f"搜索记忆失败: {e}")
            return []
    
    def migrate_user_memories(self, user_id: str, agent_role: str = "system") -> int:
        """迁移用户的传统记忆到增强格式"""
        try:
            return self.enhanced_memory_integration.migrate_legacy_memories_for_agent(user_id, agent_role)
        except Exception as e:
            logger.error(f"迁移用户记忆失败: {e}")
            return 0
    
    def cleanup_user_memories(self, user_id: str, days: int = 90) -> int:
        """清理用户的旧记忆"""
        try:
            # 增强记忆系统的清理功能
            cleaned_count = 0
            # 这里可以调用增强存储的清理方法
            logger.info(f"清理了用户 {user_id} 的 {cleaned_count} 条旧记忆")
            return cleaned_count
        except Exception as e:
            logger.error(f"清理用户记忆失败: {e}")
            return 0
    
    def get_adapter_stats(self) -> Dict[str, Any]:
        """获取适配器统计信息"""
        try:
            base_stats = {
                "adapter_enabled": self.enabled,
                "auto_extract_enabled": self.auto_extract,
                "auto_enhance_enabled": self.auto_enhance,
                "adapter_version": "4.0.0",
                "memory_system": "enhanced"
            }
            
            # 添加增强记忆系统的统计信息
            if hasattr(self.enhanced_memory_integration, 'get_integration_stats'):
                enhanced_stats = self.enhanced_memory_integration.get_integration_stats()
                base_stats.update(enhanced_stats)
            
            return base_stats
            
        except Exception as e:
            logger.error(f"获取适配器统计失败: {e}")
            return {"error": str(e)}
    
    def enable_memory_features(self):
        """启用记忆功能"""
        self.enabled = True
        self.auto_extract = True
        self.auto_enhance = True
        logger.info("增强记忆功能已启用")
    
    def disable_memory_features(self):
        """禁用记忆功能"""
        self.enabled = False
        self.auto_extract = False
        self.auto_enhance = False
        logger.info("增强记忆功能已禁用")
    
    def _extract_query_from_state(self, state: IsotopeSystemState) -> Optional[str]:
        """从状态中提取查询文本"""
        try:
            messages = state.get('messages', [])
            if messages:
                latest_msg = messages[-1]
                if hasattr(latest_msg, 'content'):
                    return latest_msg.content
                elif isinstance(latest_msg, dict) and 'content' in latest_msg:
                    return latest_msg['content']
            return None
        except Exception as e:
            logger.debug(f"提取查询失败: {e}")
            return None
    
    def _inject_memory_into_system_prompt(self, state: IsotopeSystemState, memory_context: AgentMemoryContext):
        """将记忆上下文注入到系统提示中"""
        try:
            if not state.get("messages"):
                return
            
            # 构建记忆上下文文本
            memory_text = f"\n\n**相关记忆上下文 (智能体: {memory_context.agent_role})：**\n"
            
            # 添加语义记忆
            if memory_context.semantic_memories:
                memory_text += "**概念知识：**\n"
                for memory in memory_context.semantic_memories[:3]:  # 最多3条
                    content = memory.content if hasattr(memory, 'content') else str(memory)
                    memory_text += f"- {content}\n"
            
            # 添加情节记忆
            if memory_context.episodic_memories:
                memory_text += "**历史对话：**\n"
                for memory in memory_context.episodic_memories[:2]:  # 最多2条
                    content = memory.content if hasattr(memory, 'content') else str(memory)
                    memory_text += f"- {content}\n"
            
            # 添加程序记忆
            if memory_context.procedural_memories:
                memory_text += "**处理流程：**\n"
                for memory in memory_context.procedural_memories[:2]:  # 最多2条
                    content = memory.content if hasattr(memory, 'content') else str(memory)
                    memory_text += f"- {content}\n"
            
            # 将记忆上下文添加到系统消息中
            messages = state["messages"]
            if messages and isinstance(messages[0], SystemMessage):
                # 如果第一条是系统消息，追加记忆内容
                messages[0].content += memory_text
            else:
                # 否则插入新的系统消息
                system_msg = SystemMessage(content=f"系统记忆上下文：{memory_text}")
                messages.insert(0, system_msg)
            
            logger.debug(f"已将记忆上下文注入到系统提示中")
            
        except Exception as e:
            logger.error(f"注入记忆到系统提示失败: {e}")
    
    def _generate_session_summary(self, state: IsotopeSystemState) -> str:
        """生成会话摘要"""
        try:
            messages = state.get("messages", [])
            if not messages:
                return "空会话"
            
            # 简单的摘要生成逻辑
            user_messages = []
            assistant_messages = []
            
            for msg in messages:
                content = ""
                if hasattr(msg, 'content'):
                    content = msg.content
                elif isinstance(msg, dict) and 'content' in msg:
                    content = msg['content']
                
                if hasattr(msg, 'type'):
                    msg_type = msg.type
                elif isinstance(msg, dict) and 'type' in msg:
                    msg_type = msg['type']
                else:
                    continue
                
                if msg_type == "human":
                    user_messages.append(content[:100])
                elif msg_type == "ai":
                    assistant_messages.append(content[:100])
            
            summary = f"会话包含 {len(user_messages)} 条用户消息和 {len(assistant_messages)} 条助手回复"
            
            if user_messages:
                summary += f"。主要问题：{user_messages[-1]}"
            
            return summary
            
        except Exception as e:
            logger.error(f"生成会话摘要失败: {e}")
            return "会话摘要生成失败"


def create_memory_aware_adapter(config_manager=None) -> MemoryAwareEngineAdapter:
    """创建增强记忆感知适配器的工厂函数"""
    try:
        # 如果没有提供config_manager，创建默认的
        if config_manager is None:
            from app.core.config import ConfigManager
            config_manager = ConfigManager()
            try:
                config_manager.load_config()
                logger.debug("使用默认配置管理器")
            except Exception as config_e:
                logger.warning(f"加载默认配置失败: {config_e}，使用最小配置")
                # 使用最小配置
                config_manager.config = {
                    'memory': {
                        'enabled': True,
                        'es_config': {
                            'hosts': ['http://localhost:9200'],
                            'index_name': 'test_memories'
                        }
                    }
                }
        
        # 创建增强记忆集成
        enhanced_memory_integration = create_enhanced_memory_integration(config_manager)
        
        # 创建适配器
        adapter = MemoryAwareEngineAdapter(enhanced_memory_integration)
        
        logger.info("增强记忆感知适配器创建成功")
        return adapter
        
    except Exception as e:
        logger.error(f"创建增强记忆感知适配器失败: {e}")
        raise RuntimeError(f"无法创建记忆感知适配器: {str(e)}") 