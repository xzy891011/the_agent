"""
动态Prompt管理器 - 阶段3.1：根据智能体角色动态调整prompt结构

该模块负责：
1. 根据智能体角色动态调整prompt结构
2. 优化记忆信息在prompt中的组织形式
3. 智能分配各部分在prompt中的占比
4. 提供上下文感知的prompt生成策略
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import json
import re

from .enhanced_memory_namespace import AgentRole, DomainTag, MemoryType
from .agent_memory_filter import FilteredMemoryResult
from .enhanced_langgraph_store import EnhancedMemoryEntry

logger = logging.getLogger(__name__)

class PromptSection(str, Enum):
    """Prompt部分枚举"""
    SYSTEM_IDENTITY = "system_identity"     # 系统身份
    ROLE_DESCRIPTION = "role_description"   # 角色描述
    TASK_CONTEXT = "task_context"          # 任务上下文
    MEMORY_SECTION = "memory_section"      # 记忆部分
    CURRENT_SITUATION = "current_situation" # 当前情况
    INSTRUCTIONS = "instructions"           # 指令
    OUTPUT_FORMAT = "output_format"        # 输出格式
    EXAMPLES = "examples"                  # 示例
    CONSTRAINTS = "constraints"            # 约束条件


class PromptStyle(str, Enum):
    """Prompt风格枚举"""
    PROFESSIONAL = "professional"         # 专业化
    CONVERSATIONAL = "conversational"     # 对话式
    ANALYTICAL = "analytical"             # 分析式
    INSTRUCTIONAL = "instructional"       # 指导式
    COLLABORATIVE = "collaborative"       # 协作式


@dataclass
class PromptTemplate:
    """Prompt模板配置"""
    agent_role: AgentRole
    style: PromptStyle
    sections: List[PromptSection]
    section_weights: Dict[PromptSection, float]  # 各部分权重
    memory_integration_strategy: str  # 记忆整合策略
    max_total_length: int = 8000
    memory_ratio: float = 0.25  # 记忆部分占比
    context_window: int = 4000  # 上下文窗口大小
    
    # 动态调整参数
    enable_dynamic_adjustment: bool = True
    adjustment_factors: Dict[str, float] = field(default_factory=dict)
    
    # 语言和格式
    language: str = "zh-CN"
    format_preferences: Dict[str, str] = field(default_factory=dict)


@dataclass
class PromptContext:
    """Prompt生成上下文"""
    current_task: Optional[str] = None
    conversation_history: List[str] = field(default_factory=list)
    available_tools: List[str] = field(default_factory=list)
    time_constraints: Optional[Dict[str, Any]] = None
    quality_requirements: Optional[Dict[str, Any]] = None
    user_preferences: Optional[Dict[str, Any]] = None
    domain_focus: Optional[DomainTag] = None
    complexity_level: str = "medium"  # low, medium, high
    interaction_mode: str = "standard"  # standard, debug, verbose, concise


@dataclass
class GeneratedPrompt:
    """生成的prompt结果"""
    full_prompt: str
    sections: Dict[PromptSection, str]
    metadata: Dict[str, Any]
    memory_integration_info: Dict[str, Any]
    optimization_applied: List[str]
    estimated_tokens: int
    confidence_score: float


class DynamicPromptManager:
    """动态Prompt管理器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.templates = self._load_agent_templates()
        self.section_builders = self._init_section_builders()
        self.memory_integrators = self._init_memory_integrators()
        self.optimization_strategies = self._init_optimization_strategies()
        
        # 性能统计
        self.generation_stats = {
            "total_generated": 0,
            "successful_generations": 0,
            "optimization_applied": 0,
            "average_generation_time": 0.0
        }
    
    def generate_dynamic_prompt(
        self,
        agent_role: str,
        base_prompt: str,
        memory_result: FilteredMemoryResult,
        context: PromptContext,
        custom_template: Optional[PromptTemplate] = None
    ) -> GeneratedPrompt:
        """生成动态调整的prompt"""
        start_time = datetime.now()
        
        try:
            # 1. 获取或创建模板
            template = custom_template or self._get_template_for_agent(agent_role)
            
            # 2. 分析上下文，调整模板参数
            adjusted_template = self._adjust_template_by_context(template, context)
            
            # 3. 构建各个部分
            sections = self._build_prompt_sections(
                adjusted_template, base_prompt, memory_result, context
            )
            
            # 4. 整合记忆信息
            memory_integration_info = self._integrate_memory_strategically(
                sections, memory_result, adjusted_template, context
            )
            
            # 5. 组装完整prompt
            full_prompt = self._assemble_prompt(sections, adjusted_template)
            
            # 6. 应用优化策略
            optimized_prompt, optimization_applied = self._apply_optimization_strategies(
                full_prompt, adjusted_template, context
            )
            
            # 7. 计算元数据
            metadata = self._calculate_prompt_metadata(
                optimized_prompt, sections, adjusted_template, context
            )
            
            generation_time = (datetime.now() - start_time).total_seconds()
            self._update_generation_stats(generation_time, True)
            
            return GeneratedPrompt(
                full_prompt=optimized_prompt,
                sections=sections,
                metadata=metadata,
                memory_integration_info=memory_integration_info,
                optimization_applied=optimization_applied,
                estimated_tokens=len(optimized_prompt.split()),
                confidence_score=self._calculate_confidence_score(
                    optimized_prompt, memory_result, context
                )
            )
            
        except Exception as e:
            self.logger.error(f"生成动态prompt失败: {str(e)}")
            self._update_generation_stats((datetime.now() - start_time).total_seconds(), False)
            # 回退到基础prompt
            return self._generate_fallback_prompt(base_prompt, memory_result)
    
    def _get_template_for_agent(self, agent_role: str) -> PromptTemplate:
        """获取智能体专用的prompt模板"""
        role_enum = AgentRole(agent_role) if agent_role in [r.value for r in AgentRole] else AgentRole.GENERAL_ANALYSIS
        
        return self.templates.get(role_enum, self.templates[AgentRole.GENERAL_ANALYSIS])
    
    def _adjust_template_by_context(self, template: PromptTemplate, context: PromptContext) -> PromptTemplate:
        """根据上下文调整模板参数"""
        if not template.enable_dynamic_adjustment:
            return template
        
        # 创建模板副本进行调整
        adjusted_template = PromptTemplate(
            agent_role=template.agent_role,
            style=template.style,
            sections=template.sections.copy(),
            section_weights=template.section_weights.copy(),
            memory_integration_strategy=template.memory_integration_strategy,
            max_total_length=template.max_total_length,
            memory_ratio=template.memory_ratio,
            context_window=template.context_window,
            enable_dynamic_adjustment=template.enable_dynamic_adjustment,
            adjustment_factors=template.adjustment_factors.copy(),
            language=template.language,
            format_preferences=template.format_preferences.copy()
        )
        
        # 根据复杂度调整
        if context.complexity_level == "high":
            adjusted_template.memory_ratio = min(0.35, adjusted_template.memory_ratio + 0.1)
            adjusted_template.max_total_length = min(12000, adjusted_template.max_total_length + 2000)
        elif context.complexity_level == "low":
            adjusted_template.memory_ratio = max(0.15, adjusted_template.memory_ratio - 0.1)
            adjusted_template.max_total_length = max(4000, adjusted_template.max_total_length - 2000)
        
        # 根据交互模式调整
        if context.interaction_mode == "debug":
            adjusted_template.sections.append(PromptSection.EXAMPLES)
            adjusted_template.section_weights[PromptSection.EXAMPLES] = 0.1
        elif context.interaction_mode == "concise":
            # 移除非核心部分
            non_essential = [PromptSection.EXAMPLES, PromptSection.CONSTRAINTS]
            adjusted_template.sections = [s for s in adjusted_template.sections if s not in non_essential]
        
        # 根据时间约束调整
        if context.time_constraints and context.time_constraints.get("urgent", False):
            adjusted_template.memory_ratio = max(0.1, adjusted_template.memory_ratio - 0.15)
            adjusted_template.max_total_length = max(3000, adjusted_template.max_total_length - 2000)
        
        return adjusted_template
    
    def _build_prompt_sections(
        self,
        template: PromptTemplate,
        base_prompt: str,
        memory_result: FilteredMemoryResult,
        context: PromptContext
    ) -> Dict[PromptSection, str]:
        """构建prompt各个部分"""
        sections = {}
        
        for section in template.sections:
            builder = self.section_builders.get(section)
            if builder:
                try:
                    section_content = builder(template, base_prompt, memory_result, context)
                    sections[section] = section_content
                except Exception as e:
                    self.logger.warning(f"构建section {section} 失败: {str(e)}")
                    sections[section] = ""
        
        return sections
    
    def _integrate_memory_strategically(
        self,
        sections: Dict[PromptSection, str],
        memory_result: FilteredMemoryResult,
        template: PromptTemplate,
        context: PromptContext
    ) -> Dict[str, Any]:
        """战略性地整合记忆信息"""
        strategy = template.memory_integration_strategy
        integrator = self.memory_integrators.get(strategy, self.memory_integrators["balanced"])
        
        return integrator(sections, memory_result, template, context)
    
    def _assemble_prompt(
        self,
        sections: Dict[PromptSection, str],
        template: PromptTemplate
    ) -> str:
        """组装完整的prompt"""
        prompt_parts = []
        
        # 按权重和优先级排序部分
        sorted_sections = sorted(
            sections.items(),
            key=lambda x: template.section_weights.get(x[0], 0.0),
            reverse=True
        )
        
        for section, content in sorted_sections:
            if content.strip():
                prompt_parts.append(content.strip())
        
        return "\n\n".join(prompt_parts)
    
    def _apply_optimization_strategies(
        self,
        prompt: str,
        template: PromptTemplate,
        context: PromptContext
    ) -> Tuple[str, List[str]]:
        """应用优化策略"""
        optimized_prompt = prompt
        applied_strategies = []
        
        # 长度优化
        if len(optimized_prompt) > template.max_total_length:
            optimized_prompt = self._optimize_length(optimized_prompt, template.max_total_length)
            applied_strategies.append("length_optimization")
        
        # 可读性优化
        if context.interaction_mode != "concise":
            optimized_prompt = self._optimize_readability(optimized_prompt)
            applied_strategies.append("readability_optimization")
        
        # 结构优化
        optimized_prompt = self._optimize_structure(optimized_prompt, template.style)
        applied_strategies.append("structure_optimization")
        
        return optimized_prompt, applied_strategies
    
    def _optimize_length(self, prompt: str, max_length: int) -> str:
        """优化prompt长度"""
        if len(prompt) <= max_length:
            return prompt
        
        # 分段处理
        sections = prompt.split("\n\n")
        
        # 计算每段的重要性分数
        section_scores = []
        for section in sections:
            score = self._calculate_section_importance(section)
            section_scores.append((section, score))
        
        # 按重要性排序
        section_scores.sort(key=lambda x: x[1], reverse=True)
        
        # 逐步添加部分，直到达到长度限制
        selected_sections = []
        current_length = 0
        
        for section, score in section_scores:
            if current_length + len(section) <= max_length:
                selected_sections.append(section)
                current_length += len(section)
            else:
                # 如果还有空间，尝试截取重要部分
                remaining_space = max_length - current_length
                if remaining_space > 100:  # 至少保留100字符
                    truncated_section = section[:remaining_space-10] + "..."
                    selected_sections.append(truncated_section)
                break
        
        return "\n\n".join(selected_sections)
    
    def _optimize_readability(self, prompt: str) -> str:
        """优化可读性"""
        # 添加适当的段落分隔
        optimized = re.sub(r'\n{3,}', '\n\n', prompt)
        
        # 确保标题和内容之间有适当的分隔
        optimized = re.sub(r'([：:])([^\n])', r'\1\n\2', optimized)
        
        # 优化列表格式
        optimized = re.sub(r'(\d+\.)([^\n])', r'\1 \2', optimized)
        optimized = re.sub(r'(-\s*)([^\n])', r'\1 \2', optimized)
        
        return optimized
    
    def _optimize_structure(self, prompt: str, style: PromptStyle) -> str:
        """优化结构"""
        if style == PromptStyle.PROFESSIONAL:
            # 专业化结构：清晰的层次结构
            return self._apply_professional_structure(prompt)
        elif style == PromptStyle.CONVERSATIONAL:
            # 对话式结构：更自然的语言流
            return self._apply_conversational_structure(prompt)
        elif style == PromptStyle.ANALYTICAL:
            # 分析式结构：逻辑清晰的分析框架
            return self._apply_analytical_structure(prompt)
        else:
            return prompt
    
    def _apply_professional_structure(self, prompt: str) -> str:
        """应用专业化结构"""
        # 确保有清晰的标题和分节
        sections = prompt.split("\n\n")
        structured_sections = []
        
        for i, section in enumerate(sections):
            if i == 0:
                # 第一部分作为总览
                structured_sections.append(f"## 系统概览\n{section}")
            elif "记忆" in section:
                structured_sections.append(f"## 相关记忆\n{section}")
            elif "任务" in section:
                structured_sections.append(f"## 当前任务\n{section}")
            elif "指令" in section:
                structured_sections.append(f"## 执行指令\n{section}")
            else:
                structured_sections.append(section)
        
        return "\n\n".join(structured_sections)
    
    def _apply_conversational_structure(self, prompt: str) -> str:
        """应用对话式结构"""
        # 使用更自然的语言连接
        prompt = prompt.replace("系统身份：", "你是")
        prompt = prompt.replace("任务描述：", "现在需要你")
        prompt = prompt.replace("相关记忆：", "根据之前的经验，")
        
        return prompt
    
    def _apply_analytical_structure(self, prompt: str) -> str:
        """应用分析式结构"""
        # 强调逻辑分析步骤
        if "分析" in prompt:
            analytical_framework = """
请按照以下分析框架进行思考：
1. 现状分析 - 当前情况的客观描述
2. 问题识别 - 核心问题的准确识别
3. 方案评估 - 可行解决方案的评估
4. 结论建议 - 基于分析的明确建议

"""
            prompt = analytical_framework + prompt
        
        return prompt
    
    def _calculate_section_importance(self, section: str) -> float:
        """计算段落重要性分数"""
        importance_keywords = {
            "系统": 0.9, "身份": 0.8, "任务": 0.9, "目标": 0.8,
            "记忆": 0.7, "经验": 0.6, "历史": 0.5,
            "指令": 0.9, "要求": 0.8, "约束": 0.7,
            "输出": 0.6, "格式": 0.5, "示例": 0.4
        }
        
        score = 0.0
        for keyword, weight in importance_keywords.items():
            if keyword in section:
                score += weight
        
        # 长度权重（适中的长度更重要）
        length_score = min(1.0, len(section) / 500)
        if length_score > 0.8:
            length_score = 0.8  # 避免过长段落得分过高
        
        return score + length_score
    
    def _calculate_confidence_score(
        self,
        prompt: str,
        memory_result: FilteredMemoryResult,
        context: PromptContext
    ) -> float:
        """计算prompt生成的置信度分数"""
        confidence_factors = []
        
        # 记忆相关性
        if memory_result.confidence > 0:
            confidence_factors.append(memory_result.confidence)
        
        # 模板匹配度
        template_match = self._calculate_template_match(prompt, context)
        confidence_factors.append(template_match)
        
        # 长度合理性
        length_reasonableness = self._calculate_length_reasonableness(prompt)
        confidence_factors.append(length_reasonableness)
        
        # 结构完整性
        structure_completeness = self._calculate_structure_completeness(prompt)
        confidence_factors.append(structure_completeness)
        
        return sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.5
    
    def _calculate_template_match(self, prompt: str, context: PromptContext) -> float:
        """计算模板匹配度"""
        # 基于关键词匹配
        expected_keywords = {
            "专业": 0.1, "分析": 0.2, "数据": 0.1, "结果": 0.1,
            "建议": 0.1, "评估": 0.1, "处理": 0.1, "优化": 0.1
        }
        
        match_score = 0.0
        for keyword, weight in expected_keywords.items():
            if keyword in prompt:
                match_score += weight
        
        return min(1.0, match_score)
    
    def _calculate_length_reasonableness(self, prompt: str) -> float:
        """计算长度合理性"""
        length = len(prompt)
        if 1000 <= length <= 8000:
            return 1.0
        elif 500 <= length < 1000 or 8000 < length <= 12000:
            return 0.8
        elif 200 <= length < 500 or 12000 < length <= 15000:
            return 0.6
        else:
            return 0.3
    
    def _calculate_structure_completeness(self, prompt: str) -> float:
        """计算结构完整性"""
        structure_indicators = [
            "身份", "任务", "目标", "要求", "输出"
        ]
        
        present_count = sum(1 for indicator in structure_indicators if indicator in prompt)
        return present_count / len(structure_indicators)
    
    def _calculate_prompt_metadata(
        self,
        prompt: str,
        sections: Dict[PromptSection, str],
        template: PromptTemplate,
        context: PromptContext
    ) -> Dict[str, Any]:
        """计算prompt元数据"""
        return {
            "total_length": len(prompt),
            "estimated_tokens": len(prompt.split()),
            "sections_count": len(sections),
            "template_used": template.agent_role.value,
            "style": template.style.value,
            "memory_ratio": template.memory_ratio,
            "context_complexity": context.complexity_level,
            "interaction_mode": context.interaction_mode,
            "generation_timestamp": datetime.now().isoformat()
        }
    
    def _update_generation_stats(self, generation_time: float, success: bool):
        """更新生成统计"""
        self.generation_stats["total_generated"] += 1
        if success:
            self.generation_stats["successful_generations"] += 1
        
        # 更新平均生成时间
        total_time = (self.generation_stats["average_generation_time"] * 
                     (self.generation_stats["total_generated"] - 1) + generation_time)
        self.generation_stats["average_generation_time"] = total_time / self.generation_stats["total_generated"]
    
    def _generate_fallback_prompt(
        self,
        base_prompt: str,
        memory_result: FilteredMemoryResult
    ) -> GeneratedPrompt:
        """生成回退prompt"""
        fallback_prompt = base_prompt
        if memory_result.memories:
            memory_section = "\n".join([f"- {memory.content}" for memory in memory_result.memories[:3]])
            fallback_prompt = f"{base_prompt}\n\n相关记忆：\n{memory_section}"
        
        return GeneratedPrompt(
            full_prompt=fallback_prompt,
            sections={PromptSection.INSTRUCTIONS: base_prompt},
            metadata={"fallback": True},
            memory_integration_info={"strategy": "simple"},
            optimization_applied=["fallback"],
            estimated_tokens=len(fallback_prompt.split()),
            confidence_score=0.3
        )
    
    def _load_agent_templates(self) -> Dict[AgentRole, PromptTemplate]:
        """加载智能体模板"""
        templates = {}
        
        # 地球物理分析智能体
        templates[AgentRole.GEOPHYSICS_ANALYSIS] = PromptTemplate(
            agent_role=AgentRole.GEOPHYSICS_ANALYSIS,
            style=PromptStyle.ANALYTICAL,
            sections=[
                PromptSection.SYSTEM_IDENTITY,
                PromptSection.ROLE_DESCRIPTION,
                PromptSection.MEMORY_SECTION,
                PromptSection.TASK_CONTEXT,
                PromptSection.INSTRUCTIONS,
                PromptSection.OUTPUT_FORMAT
            ],
            section_weights={
                PromptSection.SYSTEM_IDENTITY: 0.2,
                PromptSection.ROLE_DESCRIPTION: 0.15,
                PromptSection.MEMORY_SECTION: 0.25,
                PromptSection.TASK_CONTEXT: 0.2,
                PromptSection.INSTRUCTIONS: 0.15,
                PromptSection.OUTPUT_FORMAT: 0.05
            },
            memory_integration_strategy="domain_focused",
            memory_ratio=0.3
        )
        
        # 油藏工程智能体
        templates[AgentRole.RESERVOIR_ENGINEERING] = PromptTemplate(
            agent_role=AgentRole.RESERVOIR_ENGINEERING,
            style=PromptStyle.PROFESSIONAL,
            sections=[
                PromptSection.SYSTEM_IDENTITY,
                PromptSection.ROLE_DESCRIPTION,
                PromptSection.MEMORY_SECTION,
                PromptSection.TASK_CONTEXT,
                PromptSection.INSTRUCTIONS,
                PromptSection.CONSTRAINTS,
                PromptSection.OUTPUT_FORMAT
            ],
            section_weights={
                PromptSection.SYSTEM_IDENTITY: 0.15,
                PromptSection.ROLE_DESCRIPTION: 0.2,
                PromptSection.MEMORY_SECTION: 0.25,
                PromptSection.TASK_CONTEXT: 0.2,
                PromptSection.INSTRUCTIONS: 0.1,
                PromptSection.CONSTRAINTS: 0.05,
                PromptSection.OUTPUT_FORMAT: 0.05
            },
            memory_integration_strategy="technical_focused",
            memory_ratio=0.35
        )
        
        # 经济评价智能体
        templates[AgentRole.ECONOMIC_EVALUATION] = PromptTemplate(
            agent_role=AgentRole.ECONOMIC_EVALUATION,
            style=PromptStyle.ANALYTICAL,
            sections=[
                PromptSection.SYSTEM_IDENTITY,
                PromptSection.ROLE_DESCRIPTION,
                PromptSection.MEMORY_SECTION,
                PromptSection.TASK_CONTEXT,
                PromptSection.INSTRUCTIONS,
                PromptSection.OUTPUT_FORMAT,
                PromptSection.EXAMPLES
            ],
            section_weights={
                PromptSection.SYSTEM_IDENTITY: 0.15,
                PromptSection.ROLE_DESCRIPTION: 0.2,
                PromptSection.MEMORY_SECTION: 0.2,
                PromptSection.TASK_CONTEXT: 0.2,
                PromptSection.INSTRUCTIONS: 0.15,
                PromptSection.OUTPUT_FORMAT: 0.05,
                PromptSection.EXAMPLES: 0.05
            },
            memory_integration_strategy="quantitative_focused",
            memory_ratio=0.25
        )
        
        # 质量控制智能体
        templates[AgentRole.QUALITY_ASSURANCE] = PromptTemplate(
            agent_role=AgentRole.QUALITY_ASSURANCE,
            style=PromptStyle.INSTRUCTIONAL,
            sections=[
                PromptSection.SYSTEM_IDENTITY,
                PromptSection.ROLE_DESCRIPTION,
                PromptSection.MEMORY_SECTION,
                PromptSection.TASK_CONTEXT,
                PromptSection.INSTRUCTIONS,
                PromptSection.CONSTRAINTS,
                PromptSection.OUTPUT_FORMAT
            ],
            section_weights={
                PromptSection.SYSTEM_IDENTITY: 0.2,
                PromptSection.ROLE_DESCRIPTION: 0.2,
                PromptSection.MEMORY_SECTION: 0.2,
                PromptSection.TASK_CONTEXT: 0.15,
                PromptSection.INSTRUCTIONS: 0.15,
                PromptSection.CONSTRAINTS: 0.05,
                PromptSection.OUTPUT_FORMAT: 0.05
            },
            memory_integration_strategy="process_focused",
            memory_ratio=0.3
        )
        
        # 通用分析智能体（默认）
        templates[AgentRole.GENERAL_ANALYSIS] = PromptTemplate(
            agent_role=AgentRole.GENERAL_ANALYSIS,
            style=PromptStyle.CONVERSATIONAL,
            sections=[
                PromptSection.SYSTEM_IDENTITY,
                PromptSection.ROLE_DESCRIPTION,
                PromptSection.MEMORY_SECTION,
                PromptSection.TASK_CONTEXT,
                PromptSection.INSTRUCTIONS,
                PromptSection.OUTPUT_FORMAT
            ],
            section_weights={
                PromptSection.SYSTEM_IDENTITY: 0.2,
                PromptSection.ROLE_DESCRIPTION: 0.15,
                PromptSection.MEMORY_SECTION: 0.25,
                PromptSection.TASK_CONTEXT: 0.2,
                PromptSection.INSTRUCTIONS: 0.15,
                PromptSection.OUTPUT_FORMAT: 0.05
            },
            memory_integration_strategy="balanced",
            memory_ratio=0.25
        )
        
        return templates
    
    def _init_section_builders(self) -> Dict[PromptSection, callable]:
        """初始化各部分构建器"""
        builders = {}
        
        def build_system_identity(template, base_prompt, memory_result, context):
            role_names = {
                AgentRole.GEOPHYSICS_ANALYSIS: "地球物理分析专家",
                AgentRole.RESERVOIR_ENGINEERING: "油藏工程专家",
                AgentRole.ECONOMIC_EVALUATION: "经济评价专家",
                AgentRole.QUALITY_ASSURANCE: "质量控制专家",
                AgentRole.GENERAL_ANALYSIS: "智能分析助手"
            }
            role_name = role_names.get(template.agent_role, "智能助手")
            return f"你是一个专业的{role_name}，具有丰富的专业知识和实践经验。"
        
        def build_role_description(template, base_prompt, memory_result, context):
            descriptions = {
                AgentRole.GEOPHYSICS_ANALYSIS: "专门从事地球物理数据分析、地质构造解释、储层预测等工作。",
                AgentRole.RESERVOIR_ENGINEERING: "专注于油藏工程分析、生产优化、开发方案设计等技术工作。",
                AgentRole.ECONOMIC_EVALUATION: "负责项目经济评价、投资分析、风险评估等财务决策支持。",
                AgentRole.QUALITY_ASSURANCE: "确保数据质量、流程规范、结果可靠性等质量控制工作。",
                AgentRole.GENERAL_ANALYSIS: "提供全面的技术分析和专业建议，协助解决各类技术问题。"
            }
            return descriptions.get(template.agent_role, "提供专业的技术分析和建议。")
        
        def build_memory_section(template, base_prompt, memory_result, context):
            if not memory_result.memories:
                return ""
            
            memory_content = []
            for memory in memory_result.memories:
                memory_content.append(f"- {memory.content}")
            
            return f"基于以下相关经验和知识：\n" + "\n".join(memory_content)
        
        def build_task_context(template, base_prompt, memory_result, context):
            task_context = []
            
            if context.current_task:
                task_context.append(f"当前任务：{context.current_task}")
            
            if context.domain_focus:
                task_context.append(f"专业领域：{context.domain_focus.value}")
            
            if context.complexity_level:
                task_context.append(f"复杂度：{context.complexity_level}")
            
            return "\n".join(task_context) if task_context else ""
        
        def build_instructions(template, base_prompt, memory_result, context):
            return base_prompt
        
        def build_output_format(template, base_prompt, memory_result, context):
            if template.agent_role == AgentRole.ECONOMIC_EVALUATION:
                return "请提供结构化的经济评价结果，包括关键指标、风险分析和投资建议。"
            elif template.agent_role == AgentRole.QUALITY_ASSURANCE:
                return "请提供详细的质量检查报告，包括问题识别、严重程度评估和改进建议。"
            else:
                return "请提供清晰、专业的分析结果和建议。"
        
        def build_examples(template, base_prompt, memory_result, context):
            # 可以根据需要添加示例
            return ""
        
        def build_constraints(template, base_prompt, memory_result, context):
            constraints = []
            if context.time_constraints:
                constraints.append("请注意时间限制，优先处理关键问题。")
            if context.quality_requirements:
                constraints.append("请确保分析结果的准确性和可靠性。")
            return "\n".join(constraints) if constraints else ""
        
        builders[PromptSection.SYSTEM_IDENTITY] = build_system_identity
        builders[PromptSection.ROLE_DESCRIPTION] = build_role_description
        builders[PromptSection.MEMORY_SECTION] = build_memory_section
        builders[PromptSection.TASK_CONTEXT] = build_task_context
        builders[PromptSection.INSTRUCTIONS] = build_instructions
        builders[PromptSection.OUTPUT_FORMAT] = build_output_format
        builders[PromptSection.EXAMPLES] = build_examples
        builders[PromptSection.CONSTRAINTS] = build_constraints
        
        return builders
    
    def _init_memory_integrators(self) -> Dict[str, callable]:
        """初始化记忆整合器"""
        integrators = {}
        
        def balanced_integrator(sections, memory_result, template, context):
            return {
                "strategy": "balanced",
                "memories_used": len(memory_result.memories),
                "confidence": memory_result.confidence,
                "integration_method": "section_based"
            }
        
        def domain_focused_integrator(sections, memory_result, template, context):
            # 按领域分组记忆
            domain_groups = {}
            for memory in memory_result.memories:
                domain = memory.domain or "general"
                if domain not in domain_groups:
                    domain_groups[domain] = []
                domain_groups[domain].append(memory)
            
            return {
                "strategy": "domain_focused",
                "domain_groups": list(domain_groups.keys()),
                "memories_used": len(memory_result.memories),
                "confidence": memory_result.confidence,
                "integration_method": "domain_grouped"
            }
        
        def technical_focused_integrator(sections, memory_result, template, context):
            # 重点关注技术细节
            technical_memories = [m for m in memory_result.memories if m.memory_type == "procedural"]
            return {
                "strategy": "technical_focused",
                "technical_memories": len(technical_memories),
                "total_memories": len(memory_result.memories),
                "confidence": memory_result.confidence,
                "integration_method": "technical_prioritized"
            }
        
        def quantitative_focused_integrator(sections, memory_result, template, context):
            # 重点关注数据和定量分析
            quantitative_memories = [m for m in memory_result.memories 
                                   if any(keyword in m.content for keyword in ["数据", "计算", "分析", "评估"])]
            return {
                "strategy": "quantitative_focused",
                "quantitative_memories": len(quantitative_memories),
                "total_memories": len(memory_result.memories),
                "confidence": memory_result.confidence,
                "integration_method": "quantitative_prioritized"
            }
        
        def process_focused_integrator(sections, memory_result, template, context):
            # 重点关注流程和质量控制
            process_memories = [m for m in memory_result.memories 
                              if any(keyword in m.content for keyword in ["流程", "步骤", "检查", "验证"])]
            return {
                "strategy": "process_focused",
                "process_memories": len(process_memories),
                "total_memories": len(memory_result.memories),
                "confidence": memory_result.confidence,
                "integration_method": "process_prioritized"
            }
        
        integrators["balanced"] = balanced_integrator
        integrators["domain_focused"] = domain_focused_integrator
        integrators["technical_focused"] = technical_focused_integrator
        integrators["quantitative_focused"] = quantitative_focused_integrator
        integrators["process_focused"] = process_focused_integrator
        
        return integrators
    
    def _init_optimization_strategies(self) -> Dict[str, callable]:
        """初始化优化策略"""
        return {
            "length_optimization": self._optimize_length,
            "readability_optimization": self._optimize_readability,
            "structure_optimization": self._optimize_structure
        }
    
    def get_manager_statistics(self) -> Dict[str, Any]:
        """获取管理器统计信息"""
        return {
            "generation_stats": self.generation_stats,
            "templates_loaded": len(self.templates),
            "section_builders": list(self.section_builders.keys()),
            "memory_integrators": list(self.memory_integrators.keys()),
            "optimization_strategies": list(self.optimization_strategies.keys())
        }


def create_dynamic_prompt_manager() -> DynamicPromptManager:
    """创建动态Prompt管理器实例"""
    return DynamicPromptManager() 