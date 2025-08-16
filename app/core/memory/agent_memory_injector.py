"""
智能体记忆注入器 - 智能记忆注入与Prompt增强

本模块实现了智能体执行前的记忆注入机制，包括：
1. 根据智能体角色动态调整prompt结构
2. 智能记忆内容格式化和组织
3. Prompt长度控制和优化
4. 上下文感知的记忆摘要生成
"""

import logging
import time
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass
import json

from app.core.memory.enhanced_memory_integration import EnhancedMemoryIntegration, AgentMemoryContext
from app.core.memory.agent_memory_filter import AgentMemoryFilter, MemoryFilterContext, FilteredMemoryResult
from app.core.memory.enhanced_langgraph_store import EnhancedMemoryEntry
from app.core.memory.agent_memory_preferences import get_preference_manager
from app.core.memory.enhanced_memory_namespace import AgentRole, DomainTag
from app.core.state import IsotopeSystemState

logger = logging.getLogger(__name__)


@dataclass
class MemoryInjectionConfig:
    """记忆注入配置"""
    max_prompt_length: int = 8000          # 最大prompt长度
    memory_section_ratio: float = 0.3      # 记忆部分占prompt的比例
    enable_memory_summary: bool = True     # 是否启用记忆摘要
    summary_length_limit: int = 500        # 摘要长度限制
    enable_context_optimization: bool = True  # 是否启用上下文优化
    format_style: str = "structured"       # 格式样式：structured, narrative, bullet
    language: str = "zh-CN"                # 语言设置


@dataclass 
class InjectedPrompt:
    """注入记忆后的Prompt"""
    full_prompt: str                       # 完整的prompt
    memory_section: str                    # 记忆部分
    base_prompt: str                       # 基础prompt
    memory_count: int                      # 记忆数量
    prompt_length: int                     # 总长度
    memory_confidence: float               # 记忆置信度
    injection_metadata: Dict[str, Any]     # 注入元数据


class AgentMemoryInjector:
    """智能体记忆注入器"""
    
    def __init__(self, memory_integration: Optional[EnhancedMemoryIntegration] = None):
        """初始化记忆注入器"""
        self.memory_integration = memory_integration or EnhancedMemoryIntegration()
        self.memory_filter = AgentMemoryFilter()
        self.preference_manager = get_preference_manager()
        
        # 默认注入配置
        self.default_config = MemoryInjectionConfig()
        
        # 智能体特定的prompt模板
        self.agent_prompt_templates = self._load_agent_prompt_templates()
        
        logger.info("智能体记忆注入器初始化完成")
    
    def inject_memories_to_prompt(
        self,
        base_prompt: str,
        state: IsotopeSystemState,
        agent_role: str,
        current_task: Optional[str] = None,
        config: Optional[MemoryInjectionConfig] = None
    ) -> InjectedPrompt:
        """为智能体注入记忆到prompt中"""
        try:
            config = config or self.default_config
            start_time = time.time()
            
            # 提取查询内容
            query = self._extract_query_from_state(state)
            if not query:
                logger.warning(f"无法从状态中提取查询内容，返回原始prompt")
                return self._create_empty_injection(base_prompt)
            
            # 获取用户和会话信息
            user_id = state.get('metadata', {}).get('user_id', 'default_user')
            session_id = state.get('metadata', {}).get('session_id', 'default_session')
            
            # 构建筛选上下文
            filter_context = MemoryFilterContext(
                user_id=user_id,
                session_id=session_id,
                agent_role=agent_role,
                query=query,
                current_task=current_task,
                conversation_history=self._extract_conversation_history(state),
                available_tools=self._extract_available_tools(state),
                quality_requirement="standard"
            )
            
            # 获取智能体的记忆上下文
            memory_context = self.memory_integration.enhance_state_with_agent_memories(
                state=state,
                agent_role=agent_role,
                query=query
            )
            
            # 如果没有相关记忆，返回原始prompt
            if not self._has_meaningful_memories(memory_context):
                logger.info(f"智能体 {agent_role} 没有相关记忆，使用原始prompt")
                return self._create_empty_injection(base_prompt)
            
            # 筛选和优化记忆
            all_memories = (
                memory_context.semantic_memories +
                memory_context.episodic_memories +
                memory_context.procedural_memories
            )
            
            filtered_result = self.memory_filter.filter_memories_for_agent(
                memories=all_memories,
                context=filter_context
            )
            
            # 生成记忆部分的内容
            memory_section = self._format_memory_section(
                filtered_result=filtered_result,
                agent_role=agent_role,
                config=config
            )
            
            # 组合完整的prompt
            full_prompt = self._combine_prompt_with_memories(
                base_prompt=base_prompt,
                memory_section=memory_section,
                agent_role=agent_role,
                config=config
            )
            
            # 长度控制和优化
            optimized_prompt = self._optimize_prompt_length(
                full_prompt=full_prompt,
                memory_section=memory_section,
                base_prompt=base_prompt,
                config=config
            )
            
            # 创建注入结果
            injection_result = InjectedPrompt(
                full_prompt=optimized_prompt,
                memory_section=memory_section,
                base_prompt=base_prompt,
                memory_count=len(filtered_result.memories),
                prompt_length=len(optimized_prompt),
                memory_confidence=filtered_result.confidence,
                injection_metadata={
                    'agent_role': agent_role,
                    'user_id': user_id,
                    'session_id': session_id,
                    'filter_summary': filtered_result.filter_summary,
                    'coverage_domains': filtered_result.coverage_domains,
                    'memory_distribution': filtered_result.memory_distribution,
                    'injection_time': time.time() - start_time
                }
            )
            
            logger.info(f"智能体 {agent_role} 记忆注入完成: "
                       f"注入了 {len(filtered_result.memories)} 条记忆, "
                       f"置信度 {filtered_result.confidence:.2f}, "
                       f"prompt长度 {len(optimized_prompt)}")
            
            return injection_result
            
        except Exception as e:
            logger.error(f"记忆注入失败: {e}")
            return self._create_empty_injection(base_prompt)
    
    def _format_memory_section(
        self,
        filtered_result: FilteredMemoryResult,
        agent_role: str,
        config: MemoryInjectionConfig
    ) -> str:
        """格式化记忆部分的内容"""
        if not filtered_result.memories:
            return ""
        
        memory_lines = []
        
        # 添加记忆部分标题
        if config.format_style == "structured":
            memory_lines.append("## 📋 相关记忆信息")
            memory_lines.append("")
        elif config.format_style == "narrative":
            memory_lines.append("根据以往的经验和知识：")
            memory_lines.append("")
        else:  # bullet
            memory_lines.append("相关记忆：")
            memory_lines.append("")
        
        # 分类组织记忆
        semantic_memories = [m for m in filtered_result.memories if m.memory_type == 'semantic']
        episodic_memories = [m for m in filtered_result.memories if m.memory_type == 'episodic']
        procedural_memories = [m for m in filtered_result.memories if m.memory_type == 'procedural']
        
        # 格式化语义记忆（专业知识）
        if semantic_memories:
            if config.format_style == "structured":
                memory_lines.append("### 🧠 专业知识")
            elif config.format_style == "narrative":
                memory_lines.append("在专业知识方面：")
            else:
                memory_lines.append("• 专业知识：")
            
            for i, memory in enumerate(semantic_memories[:3], 1):
                formatted_content = self._format_memory_content(memory, config)
                if config.format_style == "structured":
                    memory_lines.append(f"{i}. **{memory.domain or '通用'}**: {formatted_content}")
                else:
                    memory_lines.append(f"  - {formatted_content}")
            memory_lines.append("")
        
        # 格式化情节记忆（历史经验）
        if episodic_memories:
            if config.format_style == "structured":
                memory_lines.append("### 📚 历史经验")
            elif config.format_style == "narrative":
                memory_lines.append("从历史经验来看：")
            else:
                memory_lines.append("• 历史经验：")
            
            for i, memory in enumerate(episodic_memories[:2], 1):
                formatted_content = self._format_memory_content(memory, config)
                if config.format_style == "structured":
                    memory_lines.append(f"{i}. {formatted_content}")
                else:
                    memory_lines.append(f"  - {formatted_content}")
            memory_lines.append("")
        
        # 格式化程序记忆（操作流程）
        if procedural_memories:
            if config.format_style == "structured":
                memory_lines.append("### ⚙️ 操作流程")
            elif config.format_style == "narrative":
                memory_lines.append("在操作流程方面：")
            else:
                memory_lines.append("• 操作流程：")
            
            for i, memory in enumerate(procedural_memories[:2], 1):
                formatted_content = self._format_memory_content(memory, config)
                if config.format_style == "structured":
                    memory_lines.append(f"{i}. {formatted_content}")
                else:
                    memory_lines.append(f"  - {formatted_content}")
            memory_lines.append("")
        
        # 添加记忆摘要（如果启用）
        if config.enable_memory_summary and len(filtered_result.memories) > 3:
            summary = self._generate_memory_summary(filtered_result, agent_role, config)
            if summary:
                if config.format_style == "structured":
                    memory_lines.append("### 💡 记忆摘要")
                    memory_lines.append(summary)
                else:
                    memory_lines.append(f"综合来看: {summary}")
                memory_lines.append("")
        
        # 添加置信度信息（如果置信度较低）
        if filtered_result.confidence < 0.6:
            confidence_note = f"注意：当前记忆信息的置信度为 {filtered_result.confidence:.1%}，建议谨慎参考。"
            memory_lines.append(confidence_note)
            memory_lines.append("")
        
        return "\n".join(memory_lines)
    
    def _format_memory_content(self, memory: EnhancedMemoryEntry, config: MemoryInjectionConfig) -> str:
        """格式化单条记忆内容"""
        content = memory.content.strip()
        
        # 内容长度控制
        max_length = 200 if config.format_style == "structured" else 150
        if len(content) > max_length:
            content = content[:max_length] + "..."
        
        # 添加相关性指示（如果相关性很高）
        if hasattr(memory, 'relevance_score') and memory.relevance_score > 0.8:
            if config.format_style == "structured":
                content = f"⭐ {content}"
        
        # 添加时间信息（如果是最近的记忆）
        current_time = time.time()
        age_hours = (current_time - memory.created_at) / 3600
        if age_hours < 24:  # 24小时内的记忆
            if config.format_style == "structured":
                content = f"🔥 [最近] {content}"
        
        return content
    
    def _combine_prompt_with_memories(
        self,
        base_prompt: str,
        memory_section: str,
        agent_role: str,
        config: MemoryInjectionConfig
    ) -> str:
        """将基础prompt与记忆部分结合"""
        if not memory_section.strip():
            return base_prompt
        
        # 获取智能体特定的模板
        template = self.agent_prompt_templates.get(agent_role, self.agent_prompt_templates['default'])
        
        # 构建完整prompt
        if config.format_style == "structured":
            combined_prompt = template['structured'].format(
                memory_section=memory_section,
                base_prompt=base_prompt,
                agent_role=agent_role
            )
        elif config.format_style == "narrative":
            combined_prompt = template['narrative'].format(
                memory_section=memory_section,
                base_prompt=base_prompt,
                agent_role=agent_role
            )
        else:  # bullet
            combined_prompt = template['bullet'].format(
                memory_section=memory_section,
                base_prompt=base_prompt,
                agent_role=agent_role
            )
        
        return combined_prompt
    
    def _optimize_prompt_length(
        self,
        full_prompt: str,
        memory_section: str,
        base_prompt: str,
        config: MemoryInjectionConfig
    ) -> str:
        """优化prompt长度"""
        if len(full_prompt) <= config.max_prompt_length:
            return full_prompt
        
        logger.warning(f"Prompt长度 {len(full_prompt)} 超过限制 {config.max_prompt_length}，进行压缩")
        
        # 计算可用于记忆部分的长度
        base_length = len(base_prompt)
        available_memory_length = int(config.max_prompt_length * config.memory_section_ratio)
        
        # 如果基础prompt就太长，优先保证记忆部分
        if base_length > config.max_prompt_length - available_memory_length:
            base_prompt = base_prompt[:config.max_prompt_length - available_memory_length - 100] + "..."
        
        # 压缩记忆部分
        if len(memory_section) > available_memory_length:
            # 简化格式，保留核心内容
            compressed_memory = self._compress_memory_section(memory_section, available_memory_length)
            memory_section = compressed_memory
        
        # 重新组合
        optimized_prompt = f"{memory_section}\n\n{base_prompt}"
        
        # 确保不超过限制
        if len(optimized_prompt) > config.max_prompt_length:
            optimized_prompt = optimized_prompt[:config.max_prompt_length-3] + "..."
        
        logger.info(f"Prompt压缩完成: {len(full_prompt)} -> {len(optimized_prompt)}")
        return optimized_prompt
    
    def _compress_memory_section(self, memory_section: str, max_length: int) -> str:
        """压缩记忆部分"""
        lines = memory_section.split('\n')
        compressed_lines = []
        current_length = 0
        
        # 保留标题和重要内容
        for line in lines:
            if current_length + len(line) > max_length:
                break
            
            # 跳过空行
            if not line.strip():
                if compressed_lines and compressed_lines[-1].strip():
                    compressed_lines.append('')
                continue
            
            # 保留重要标记的行
            if any(marker in line for marker in ['###', '⭐', '🔥', '💡']):
                compressed_lines.append(line)
                current_length += len(line) + 1
            # 保留内容行，但可能截断
            elif line.strip().startswith(('1.', '2.', '3.', '-', '•')):
                if current_length + len(line) <= max_length:
                    compressed_lines.append(line)
                    current_length += len(line) + 1
                else:
                    # 截断内容
                    available = max_length - current_length - 3
                    if available > 20:
                        compressed_lines.append(line[:available] + "...")
                    break
        
        return '\n'.join(compressed_lines)
    
    def _generate_memory_summary(
        self,
        filtered_result: FilteredMemoryResult,
        agent_role: str,
        config: MemoryInjectionConfig
    ) -> str:
        """生成记忆摘要"""
        try:
            memories = filtered_result.memories
            if not memories:
                return ""
            
            # 提取关键信息
            domains = list(set(m.domain for m in memories if m.domain))
            high_importance_memories = [m for m in memories if m.importance_score > 0.7]
            recent_memories = [m for m in memories if (time.time() - m.created_at) < 86400]  # 24小时内
            
            summary_parts = []
            
            # 领域覆盖
            if domains:
                domain_text = "、".join(domains[:3])
                if len(domains) > 3:
                    domain_text += "等"
                summary_parts.append(f"涵盖了{domain_text}领域")
            
            # 重要记忆
            if high_importance_memories:
                summary_parts.append(f"包含{len(high_importance_memories)}条重要记忆")
            
            # 最近记忆
            if recent_memories:
                summary_parts.append(f"有{len(recent_memories)}条最新记忆")
            
            # 置信度描述
            confidence = filtered_result.confidence
            if confidence > 0.8:
                summary_parts.append("记忆可靠性高")
            elif confidence > 0.6:
                summary_parts.append("记忆可靠性中等")
            else:
                summary_parts.append("记忆可靠性较低")
            
            if summary_parts:
                summary = "，".join(summary_parts) + "。"
                
                # 长度控制
                if len(summary) > config.summary_length_limit:
                    summary = summary[:config.summary_length_limit-3] + "..."
                
                return summary
            
        except Exception as e:
            logger.error(f"生成记忆摘要失败: {e}")
        
        return ""
    
    def _load_agent_prompt_templates(self) -> Dict[str, Dict[str, str]]:
        """加载智能体特定的prompt模板"""
        templates = {
            'default': {
                'structured': """
{memory_section}

---

{base_prompt}
""",
                'narrative': """
{memory_section}

基于以上信息，{base_prompt}
""",
                'bullet': """
{memory_section}

请参考以上信息，{base_prompt}
"""
            },
            
            AgentRole.GEOPHYSICS_ANALYSIS.value: {
                'structured': """
{memory_section}

## 🔍 地球物理分析任务

作为地球物理分析专家，请结合以上专业记忆和经验，{base_prompt}

请特别注意地震、测井、地质构造等专业领域的相关信息。
""",
                'narrative': """
{memory_section}

作为地球物理分析专家，基于以上的专业知识和历史经验，{base_prompt}
""",
                'bullet': """
{memory_section}

地球物理分析要求：
• 结合以上专业记忆进行分析
• 重点关注地震、测井、地质等数据
• {base_prompt}
"""
            },
            
            AgentRole.RESERVOIR_ENGINEERING.value: {
                'structured': """
{memory_section}

## ⚙️ 油藏工程分析

作为油藏工程专家，请基于以上工程经验和程序性知识，{base_prompt}

请重点考虑油藏模拟、生产优化、压力分析等工程要素。
""",
                'narrative': """
{memory_section}

作为油藏工程专家，结合以上的工程实践经验和技术流程，{base_prompt}
""",
                'bullet': """
{memory_section}

油藏工程分析要点：
• 参考以上工程实践经验
• 重点关注生产优化和压力分析
• {base_prompt}
"""
            },
            
            AgentRole.ECONOMIC_EVALUATION.value: {
                'structured': """
{memory_section}

## 💰 经济评价分析

作为经济评价专家，请基于以上项目经验和评价案例，{base_prompt}

请特别关注NPV、IRR、风险评估等关键经济指标。
""",
                'narrative': """
{memory_section}

作为经济评价专家，根据以上的项目历史和评价经验，{base_prompt}
""",
                'bullet': """
{memory_section}

经济评价要求：
• 参考以上项目案例和评价经验
• 重点关注经济效益和风险评估
• {base_prompt}
"""
            },
            
            AgentRole.QUALITY_ASSURANCE.value: {
                'structured': """
{memory_section}

## ✅ 质量保证检查

作为质量保证专家，请基于以上检查流程和质量标准，{base_prompt}

请严格按照质量控制程序进行验证和检查。
""",
                'narrative': """
{memory_section}

作为质量保证专家，依据以上的检查标准和质量控制经验，{base_prompt}
""",
                'bullet': """
{memory_section}

质量保证要点：
• 遵循以上质量控制流程
• 严格执行检查标准
• {base_prompt}
"""
            }
        }
        
        return templates
    
    def _extract_query_from_state(self, state: IsotopeSystemState) -> Optional[str]:
        """从状态中提取查询内容"""
        messages = state.get('messages', [])
        if messages:
            # 获取最新的用户消息
            for msg in reversed(messages):
                if hasattr(msg, 'content'):
                    content = msg.content
                elif isinstance(msg, dict):
                    content = msg.get('content', '')
                else:
                    content = str(msg)
                
                if content and len(content.strip()) > 0:
                    return content.strip()
        
        return None
    
    def _extract_conversation_history(self, state: IsotopeSystemState) -> List[str]:
        """提取对话历史"""
        messages = state.get('messages', [])
        history = []
        
        for msg in messages[-5:]:  # 最近5条消息
            if hasattr(msg, 'content'):
                content = msg.content
            elif isinstance(msg, dict):
                content = msg.get('content', '')
            else:
                content = str(msg)
            
            if content:
                history.append(content[:200])  # 限制长度
        
        return history
    
    def _extract_available_tools(self, state: IsotopeSystemState) -> List[str]:
        """提取可用工具"""
        # 从状态中提取工具信息
        tools = []
        
        # 从工具结果中推断可用工具
        tool_results = state.get('tool_results', [])
        for result in tool_results:
            tool_name = result.get('tool_name')
            if tool_name:
                tools.append(tool_name)
        
        # 从元数据中获取工具信息
        metadata = state.get('metadata', {})
        available_tools = metadata.get('available_tools', [])
        tools.extend(available_tools)
        
        return list(set(tools))  # 去重
    
    def _has_meaningful_memories(self, memory_context: AgentMemoryContext) -> bool:
        """检查是否有有意义的记忆"""
        total_memories = (
            len(memory_context.semantic_memories) +
            len(memory_context.episodic_memories) +
            len(memory_context.procedural_memories)
        )
        
        return total_memories > 0 and memory_context.confidence_score > 0.1
    
    def _create_empty_injection(self, base_prompt: str) -> InjectedPrompt:
        """创建空的注入结果"""
        return InjectedPrompt(
            full_prompt=base_prompt,
            memory_section="",
            base_prompt=base_prompt,
            memory_count=0,
            prompt_length=len(base_prompt),
            memory_confidence=0.0,
            injection_metadata={
                'agent_role': 'unknown',
                'user_id': 'unknown',
                'session_id': 'unknown',
                'filter_summary': '没有相关记忆',
                'coverage_domains': [],
                'memory_distribution': {'semantic': 0, 'episodic': 0, 'procedural': 0},
                'injection_time': 0.0
            }
        )
    
    def get_injection_statistics(self, agent_role: str) -> Dict[str, Any]:
        """获取注入统计信息"""
        # 这里可以添加统计信息收集逻辑
        # 目前返回基本信息
        preference = self.preference_manager.get_agent_preference(agent_role)
        
        return {
            'agent_role': agent_role,
            'memory_limits': self.preference_manager.get_memory_limits(agent_role),
            'preference_summary': {
                'usage_pattern': preference.usage_pattern.value,
                'preferred_domains': preference.preferred_domains,
                'enable_cross_agent_memories': preference.enable_cross_agent_memories
            },
            'injection_config': {
                'max_prompt_length': self.default_config.max_prompt_length,
                'memory_section_ratio': self.default_config.memory_section_ratio,
                'format_style': self.default_config.format_style
            }
        }


def create_agent_memory_injector(
    memory_integration: Optional[EnhancedMemoryIntegration] = None
) -> AgentMemoryInjector:
    """创建智能体记忆注入器实例"""
    return AgentMemoryInjector(memory_integration) 