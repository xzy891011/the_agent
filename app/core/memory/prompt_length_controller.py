"""
Prompt长度控制系统 - 阶段3.3：控制prompt长度，避免信息过载

该模块负责：
1. 智能控制prompt总长度
2. 自适应内容压缩
3. 重要性导向的内容保留
4. 多级压缩策略
5. 性能优化和缓存
"""

import logging
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import json

from .enhanced_langgraph_store import EnhancedMemoryEntry
from .agent_memory_filter import FilteredMemoryResult
from .dynamic_prompt_manager import GeneratedPrompt, PromptSection

logger = logging.getLogger(__name__)

class CompressionLevel(str, Enum):
    """压缩级别枚举"""
    NONE = "none"           # 无压缩
    LIGHT = "light"         # 轻度压缩
    MODERATE = "moderate"   # 中度压缩
    AGGRESSIVE = "aggressive"  # 激进压缩
    EXTREME = "extreme"     # 极度压缩

class ContentPriority(str, Enum):
    """内容优先级枚举"""
    CRITICAL = "critical"   # 关键内容
    HIGH = "high"          # 高优先级
    MEDIUM = "medium"      # 中等优先级
    LOW = "low"           # 低优先级
    OPTIONAL = "optional"  # 可选内容

@dataclass
class LengthConstraint:
    """长度约束配置"""
    max_total_length: int = 8000
    min_total_length: int = 1000
    max_memory_ratio: float = 0.4
    min_memory_ratio: float = 0.1
    section_limits: Dict[PromptSection, int] = field(default_factory=dict)
    compression_threshold: float = 0.8  # 触发压缩的阈值

@dataclass
class CompressionResult:
    """压缩结果"""
    original_length: int
    compressed_length: int
    compression_ratio: float
    sections_modified: List[PromptSection]
    compression_level: CompressionLevel
    content_preserved: float  # 内容保留率
    quality_score: float
    compression_time: float

class PromptLengthController:
    """Prompt长度控制器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        
        # 压缩策略配置
        self.compression_strategies = self._init_compression_strategies()
        self.content_analyzers = self._init_content_analyzers()
        self.section_optimizers = self._init_section_optimizers()
        
        # 统计信息
        self.compression_stats = {
            "total_compressions": 0,
            "successful_compressions": 0,
            "average_compression_ratio": 0.0,
            "average_compression_time": 0.0,
            "compression_level_usage": {level.value: 0 for level in CompressionLevel}
        }
    
    def control_prompt_length(
        self,
        generated_prompt: GeneratedPrompt,
        constraint: LengthConstraint,
        memory_result: FilteredMemoryResult,
        preserve_quality: bool = True
    ) -> Tuple[GeneratedPrompt, CompressionResult]:
        """控制prompt长度"""
        start_time = datetime.now()
        
        original_length = len(generated_prompt.full_prompt)
        
        # 如果不超过限制，直接返回
        if original_length <= constraint.max_total_length:
            no_compression_result = CompressionResult(
                original_length=original_length,
                compressed_length=original_length,
                compression_ratio=1.0,
                sections_modified=[],
                compression_level=CompressionLevel.NONE,
                content_preserved=1.0,
                quality_score=1.0,
                compression_time=0.0
            )
            return generated_prompt, no_compression_result
        
        # 确定压缩级别
        compression_level = self._determine_compression_level(
            original_length, constraint, preserve_quality
        )
        
        # 执行压缩
        compressed_prompt, compression_result = self._compress_prompt(
            generated_prompt, constraint, compression_level, memory_result
        )
        
        # 更新统计
        compression_time = (datetime.now() - start_time).total_seconds()
        compression_result.compression_time = compression_time
        self._update_compression_stats(compression_result)
        
        return compressed_prompt, compression_result
    
    def _determine_compression_level(
        self,
        original_length: int,
        constraint: LengthConstraint,
        preserve_quality: bool
    ) -> CompressionLevel:
        """确定压缩级别"""
        max_length = constraint.max_total_length
        overage_ratio = original_length / max_length
        
        if overage_ratio <= 1.2:
            return CompressionLevel.LIGHT
        elif overage_ratio <= 1.5:
            return CompressionLevel.MODERATE
        elif overage_ratio <= 2.0:
            return CompressionLevel.AGGRESSIVE
        else:
            return CompressionLevel.EXTREME if not preserve_quality else CompressionLevel.AGGRESSIVE
    
    def _compress_prompt(
        self,
        generated_prompt: GeneratedPrompt,
        constraint: LengthConstraint,
        compression_level: CompressionLevel,
        memory_result: FilteredMemoryResult
    ) -> Tuple[GeneratedPrompt, CompressionResult]:
        """执行prompt压缩"""
        original_length = len(generated_prompt.full_prompt)
        sections_modified = []
        
        # 分析各部分的重要性
        section_priorities = self._analyze_section_priorities(
            generated_prompt.sections, memory_result
        )
        
        # 创建副本进行修改
        compressed_sections = generated_prompt.sections.copy()
        
        # 按压缩级别应用不同策略
        if compression_level == CompressionLevel.LIGHT:
            compressed_sections, modified = self._apply_light_compression(
                compressed_sections, section_priorities, constraint
            )
            sections_modified.extend(modified)
        
        elif compression_level == CompressionLevel.MODERATE:
            compressed_sections, modified = self._apply_moderate_compression(
                compressed_sections, section_priorities, constraint
            )
            sections_modified.extend(modified)
        
        elif compression_level == CompressionLevel.AGGRESSIVE:
            compressed_sections, modified = self._apply_aggressive_compression(
                compressed_sections, section_priorities, constraint
            )
            sections_modified.extend(modified)
        
        elif compression_level == CompressionLevel.EXTREME:
            compressed_sections, modified = self._apply_extreme_compression(
                compressed_sections, section_priorities, constraint
            )
            sections_modified.extend(modified)
        
        # 重新组装prompt
        compressed_full_prompt = self._reassemble_prompt(compressed_sections)
        compressed_length = len(compressed_full_prompt)
        
        # 创建压缩后的prompt对象
        compressed_prompt = GeneratedPrompt(
            full_prompt=compressed_full_prompt,
            sections=compressed_sections,
            metadata=generated_prompt.metadata.copy(),
            memory_integration_info=generated_prompt.memory_integration_info.copy(),
            optimization_applied=generated_prompt.optimization_applied + [f"compression_{compression_level.value}"],
            estimated_tokens=len(compressed_full_prompt.split()),
            confidence_score=self._calculate_post_compression_confidence(
                generated_prompt.confidence_score, compression_level
            )
        )
        
        # 计算压缩指标
        compression_ratio = compressed_length / original_length
        content_preserved = self._calculate_content_preservation(
            generated_prompt.sections, compressed_sections
        )
        quality_score = self._calculate_compression_quality(
            compressed_prompt, compression_level, content_preserved
        )
        
        compression_result = CompressionResult(
            original_length=original_length,
            compressed_length=compressed_length,
            compression_ratio=compression_ratio,
            sections_modified=sections_modified,
            compression_level=compression_level,
            content_preserved=content_preserved,
            quality_score=quality_score,
            compression_time=0.0  # 会在外部设置
        )
        
        return compressed_prompt, compression_result
    
    def _analyze_section_priorities(
        self,
        sections: Dict[PromptSection, str],
        memory_result: FilteredMemoryResult
    ) -> Dict[PromptSection, ContentPriority]:
        """分析各部分的优先级"""
        priorities = {}
        
        # 基础优先级设置
        base_priorities = {
            PromptSection.SYSTEM_IDENTITY: ContentPriority.CRITICAL,
            PromptSection.INSTRUCTIONS: ContentPriority.CRITICAL,
            PromptSection.MEMORY_SECTION: ContentPriority.HIGH,
            PromptSection.TASK_CONTEXT: ContentPriority.HIGH,
            PromptSection.ROLE_DESCRIPTION: ContentPriority.MEDIUM,
            PromptSection.OUTPUT_FORMAT: ContentPriority.MEDIUM,
            PromptSection.CONSTRAINTS: ContentPriority.LOW,
            PromptSection.EXAMPLES: ContentPriority.OPTIONAL,
            PromptSection.CURRENT_SITUATION: ContentPriority.MEDIUM
        }
        
        for section, content in sections.items():
            base_priority = base_priorities.get(section, ContentPriority.MEDIUM)
            
            # 根据内容调整优先级
            adjusted_priority = self._adjust_priority_by_content(
                base_priority, content, memory_result
            )
            priorities[section] = adjusted_priority
        
        return priorities
    
    def _adjust_priority_by_content(
        self,
        base_priority: ContentPriority,
        content: str,
        memory_result: FilteredMemoryResult
    ) -> ContentPriority:
        """根据内容调整优先级"""
        if not content.strip():
            return ContentPriority.OPTIONAL
        
        # 如果内容很短，可能不是很重要
        if len(content) < 50:
            if base_priority == ContentPriority.CRITICAL:
                return ContentPriority.HIGH
            elif base_priority == ContentPriority.HIGH:
                return ContentPriority.MEDIUM
        
        # 如果记忆相关性很高，提升记忆部分优先级
        if "记忆" in content and memory_result.confidence > 0.8:
            if base_priority in [ContentPriority.MEDIUM, ContentPriority.HIGH]:
                return ContentPriority.HIGH
        
        return base_priority
    
    def _apply_light_compression(
        self,
        sections: Dict[PromptSection, str],
        priorities: Dict[PromptSection, ContentPriority],
        constraint: LengthConstraint
    ) -> Tuple[Dict[PromptSection, str], List[PromptSection]]:
        """应用轻度压缩"""
        modified_sections = []
        
        for section, content in sections.items():
            priority = priorities.get(section, ContentPriority.MEDIUM)
            
            if priority == ContentPriority.OPTIONAL and len(content) > 200:
                # 删除可选的长内容
                sections[section] = ""
                modified_sections.append(section)
            elif priority == ContentPriority.LOW and len(content) > 300:
                # 压缩低优先级的长内容
                sections[section] = self._compress_text_light(content)
                modified_sections.append(section)
        
        return sections, modified_sections
    
    def _apply_moderate_compression(
        self,
        sections: Dict[PromptSection, str],
        priorities: Dict[PromptSection, ContentPriority],
        constraint: LengthConstraint
    ) -> Tuple[Dict[PromptSection, str], List[PromptSection]]:
        """应用中度压缩"""
        modified_sections = []
        
        for section, content in sections.items():
            priority = priorities.get(section, ContentPriority.MEDIUM)
            
            if priority == ContentPriority.OPTIONAL:
                sections[section] = ""
                modified_sections.append(section)
            elif priority == ContentPriority.LOW:
                sections[section] = self._compress_text_moderate(content)
                modified_sections.append(section)
            elif priority == ContentPriority.MEDIUM and len(content) > 400:
                sections[section] = self._compress_text_light(content)
                modified_sections.append(section)
        
        return sections, modified_sections
    
    def _apply_aggressive_compression(
        self,
        sections: Dict[PromptSection, str],
        priorities: Dict[PromptSection, ContentPriority],
        constraint: LengthConstraint
    ) -> Tuple[Dict[PromptSection, str], List[PromptSection]]:
        """应用激进压缩"""
        modified_sections = []
        
        for section, content in sections.items():
            priority = priorities.get(section, ContentPriority.MEDIUM)
            
            if priority in [ContentPriority.OPTIONAL, ContentPriority.LOW]:
                sections[section] = ""
                modified_sections.append(section)
            elif priority == ContentPriority.MEDIUM:
                sections[section] = self._compress_text_moderate(content)
                modified_sections.append(section)
            elif priority == ContentPriority.HIGH and len(content) > 300:
                sections[section] = self._compress_text_light(content)
                modified_sections.append(section)
        
        return sections, modified_sections
    
    def _apply_extreme_compression(
        self,
        sections: Dict[PromptSection, str],
        priorities: Dict[PromptSection, ContentPriority],
        constraint: LengthConstraint
    ) -> Tuple[Dict[PromptSection, str], List[PromptSection]]:
        """应用极度压缩"""
        modified_sections = []
        
        for section, content in sections.items():
            priority = priorities.get(section, ContentPriority.MEDIUM)
            
            if priority != ContentPriority.CRITICAL:
                if priority in [ContentPriority.OPTIONAL, ContentPriority.LOW, ContentPriority.MEDIUM]:
                    sections[section] = ""
                    modified_sections.append(section)
                elif priority == ContentPriority.HIGH:
                    sections[section] = self._compress_text_aggressive(content)
                    modified_sections.append(section)
            else:
                # 即使是关键内容也要压缩
                if len(content) > 200:
                    sections[section] = self._compress_text_light(content)
                    modified_sections.append(section)
        
        return sections, modified_sections
    
    def _compress_text_light(self, text: str) -> str:
        """轻度文本压缩"""
        if not text:
            return text
        
        # 移除多余空白
        compressed = re.sub(r'\s+', ' ', text.strip())
        
        # 简化长句
        sentences = compressed.split('。')
        if len(sentences) > 3:
            # 保留前3句
            compressed = '。'.join(sentences[:3]) + '。'
        
        return compressed
    
    def _compress_text_moderate(self, text: str) -> str:
        """中度文本压缩"""
        if not text:
            return text
        
        # 先应用轻度压缩
        compressed = self._compress_text_light(text)
        
        # 提取关键信息
        sentences = compressed.split('。')
        if len(sentences) > 2:
            # 保留前2句
            compressed = '。'.join(sentences[:2]) + '。'
        
        # 移除修饰词
        compressed = re.sub(r'(非常|特别|相当|比较|十分)', '', compressed)
        
        return compressed
    
    def _compress_text_aggressive(self, text: str) -> str:
        """激进文本压缩"""
        if not text:
            return text
        
        # 提取关键词
        keywords = self._extract_key_concepts(text)
        
        # 重构为简洁表达
        if keywords:
            return f"关键要点：{' '.join(keywords[:5])}"
        else:
            # 保留第一句
            first_sentence = text.split('。')[0]
            return first_sentence[:100] + '。' if len(first_sentence) > 100 else first_sentence + '。'
    
    def _extract_key_concepts(self, text: str) -> List[str]:
        """提取关键概念"""
        # 简化的关键词提取
        import jieba
        
        try:
            # 分词
            words = list(jieba.cut(text))
            
            # 过滤停用词和短词
            stop_words = {'的', '是', '在', '和', '与', '对', '为', '了', '到', '从'}
            keywords = [w for w in words if len(w) > 1 and w not in stop_words]
            
            # 按词频排序
            word_freq = {}
            for word in keywords:
                word_freq[word] = word_freq.get(word, 0) + 1
            
            sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
            return [word for word, freq in sorted_words[:10]]
            
        except ImportError:
            # 如果没有jieba，使用简单的方法
            words = re.findall(r'[\u4e00-\u9fff]+', text)
            return list(set(words))[:10]
    
    def _reassemble_prompt(self, sections: Dict[PromptSection, str]) -> str:
        """重新组装prompt"""
        parts = []
        
        # 按重要性顺序组装
        section_order = [
            PromptSection.SYSTEM_IDENTITY,
            PromptSection.ROLE_DESCRIPTION,
            PromptSection.MEMORY_SECTION,
            PromptSection.TASK_CONTEXT,
            PromptSection.CURRENT_SITUATION,
            PromptSection.INSTRUCTIONS,
            PromptSection.CONSTRAINTS,
            PromptSection.OUTPUT_FORMAT,
            PromptSection.EXAMPLES
        ]
        
        for section in section_order:
            if section in sections and sections[section].strip():
                parts.append(sections[section].strip())
        
        return '\n\n'.join(parts)
    
    def _calculate_post_compression_confidence(
        self,
        original_confidence: float,
        compression_level: CompressionLevel
    ) -> float:
        """计算压缩后的置信度"""
        confidence_penalty = {
            CompressionLevel.NONE: 0.0,
            CompressionLevel.LIGHT: 0.05,
            CompressionLevel.MODERATE: 0.15,
            CompressionLevel.AGGRESSIVE: 0.30,
            CompressionLevel.EXTREME: 0.50
        }
        
        penalty = confidence_penalty.get(compression_level, 0.0)
        return max(0.1, original_confidence - penalty)
    
    def _calculate_content_preservation(
        self,
        original_sections: Dict[PromptSection, str],
        compressed_sections: Dict[PromptSection, str]
    ) -> float:
        """计算内容保留率"""
        original_total = sum(len(content) for content in original_sections.values())
        compressed_total = sum(len(content) for content in compressed_sections.values())
        
        if original_total == 0:
            return 1.0
        
        return compressed_total / original_total
    
    def _calculate_compression_quality(
        self,
        compressed_prompt: GeneratedPrompt,
        compression_level: CompressionLevel,
        content_preserved: float
    ) -> float:
        """计算压缩质量分数"""
        # 基础质量分数
        base_quality = {
            CompressionLevel.NONE: 1.0,
            CompressionLevel.LIGHT: 0.9,
            CompressionLevel.MODERATE: 0.8,
            CompressionLevel.AGGRESSIVE: 0.6,
            CompressionLevel.EXTREME: 0.4
        }
        
        quality = base_quality.get(compression_level, 0.5)
        
        # 考虑内容保留率
        quality *= (0.5 + 0.5 * content_preserved)
        
        # 考虑结构完整性
        if len(compressed_prompt.sections) >= 3:  # 至少保留3个部分
            quality *= 1.1
        
        return min(1.0, quality)
    
    def _update_compression_stats(self, result: CompressionResult):
        """更新压缩统计"""
        self.compression_stats["total_compressions"] += 1
        if result.compression_ratio < 1.0:
            self.compression_stats["successful_compressions"] += 1
        
        # 更新平均压缩比
        total_ratio = (self.compression_stats["average_compression_ratio"] * 
                      (self.compression_stats["total_compressions"] - 1) + result.compression_ratio)
        self.compression_stats["average_compression_ratio"] = total_ratio / self.compression_stats["total_compressions"]
        
        # 更新平均压缩时间
        total_time = (self.compression_stats["average_compression_time"] * 
                     (self.compression_stats["total_compressions"] - 1) + result.compression_time)
        self.compression_stats["average_compression_time"] = total_time / self.compression_stats["total_compressions"]
        
        # 更新压缩级别使用统计
        self.compression_stats["compression_level_usage"][result.compression_level.value] += 1
    
    def _init_compression_strategies(self) -> Dict[str, Any]:
        """初始化压缩策略"""
        return {
            "preserve_quality": True,
            "adaptive_threshold": 0.8,
            "minimum_sections": 3,
            "critical_section_protection": True
        }
    
    def _init_content_analyzers(self) -> Dict[str, Any]:
        """初始化内容分析器"""
        return {
            "keyword_extractor": True,
            "importance_scorer": True,
            "redundancy_detector": True
        }
    
    def _init_section_optimizers(self) -> Dict[str, Any]:
        """初始化部分优化器"""
        return {
            "memory_optimizer": True,
            "instruction_optimizer": True,
            "context_optimizer": True
        }
    
    def get_compression_statistics(self) -> Dict[str, Any]:
        """获取压缩统计信息"""
        return self.compression_stats.copy()


def create_prompt_length_controller(config: Optional[Dict[str, Any]] = None) -> PromptLengthController:
    """创建Prompt长度控制器"""
    return PromptLengthController(config) 