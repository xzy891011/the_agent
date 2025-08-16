"""
会话历史管理模块 - 提供历史消息管理和总结功能
"""

import logging
from typing import List, Dict, Any, Optional, Union, Callable
from langchain_core.messages import (
    BaseMessage, 
    HumanMessage, 
    AIMessage, 
    SystemMessage,
    FunctionMessage
)
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

# 特殊消息类型，用于标记需要删除的消息
class RemoveMessage(BaseMessage):
    """用于标记需要从历史记录中删除的消息"""
    
    type: str = "remove"  # 修复：显式定义type字段
    
    def __init__(self, id: str, **kwargs):
        """初始化删除消息
        
        Args:
            id: 要删除的消息ID
        """
        super().__init__(content="", type="remove", additional_kwargs={"id": id}, **kwargs)
        self.id = id  # 保留id属性便于访问

# 配置日志
logger = logging.getLogger(__name__)

class HistoryManager:
    """会话历史管理器"""
    
    @staticmethod
    def should_summarize(messages: List[BaseMessage], threshold: int = 10) -> bool:
        """检查是否应该总结对话历史
        
        Args:
            messages: 消息列表
            threshold: 消息数量阈值
            
        Returns:
            布尔值，是否应该总结
        """
        # 只计算用户和AI消息
        relevant_messages = [
            msg for msg in messages 
            if isinstance(msg, (HumanMessage, AIMessage))
        ]
        
        return len(relevant_messages) >= threshold
    
    @staticmethod
    def summarize_messages(
        messages: List[BaseMessage], 
        llm: Optional[BaseChatModel] = None,
        keep_last_n: int = 4
    ) -> str:
        """总结消息历史
        
        Args:
            messages: 消息列表
            llm: 用于总结的语言模型
            keep_last_n: 保留的最后n条消息数
            
        Returns:
            历史总结文本
        """
        # 如果消息太少，直接返回
        if len(messages) <= keep_last_n:
            return "对话太短，无需总结"
        
        # 筛选需要总结的消息
        # 跳过系统消息和最后几条消息
        to_summarize = []
        system_msgs = []
        recent_msgs = []
        
        for i, msg in enumerate(messages):
            if isinstance(msg, SystemMessage):
                system_msgs.append(msg)
            elif i >= len(messages) - keep_last_n:
                recent_msgs.append(msg)
            else:
                # 只总结用户和AI消息
                if isinstance(msg, (HumanMessage, AIMessage)):
                    to_summarize.append(msg)
        
        # 如果没有要总结的消息，直接返回
        if not to_summarize:
            return "无需总结的对话内容"
        
        # 如果没有提供LLM，则使用规则化总结
        if llm is None:
            return HistoryManager._rule_based_summarize(to_summarize)
        
        # 使用LLM总结
        try:
            # 构建总结提示
            history_text = "\n".join([
                f"{'用户' if isinstance(msg, HumanMessage) else 'AI'}: {msg.content}"
                for msg in to_summarize
            ])
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", "你是一个专业的对话总结助手。你的任务是简洁地总结以下对话历史的关键点和主要信息。总结应包含所有重要的事实、决策和上下文，但要尽量精简。"),
                ("human", "请总结以下对话历史:\n\n{history}")
            ])
            
            # 调用LLM生成总结
            chain = prompt | llm
            result = chain.invoke({"history": history_text})
            
            # 提取总结文本
            if hasattr(result, "content"):
                return result.content
            elif isinstance(result, dict) and "content" in result:
                return result["content"]
            else:
                return str(result)
        
        except Exception as e:
            logger.error(f"使用LLM总结历史失败: {str(e)}")
            # 回退到规则化总结
            return HistoryManager._rule_based_summarize(to_summarize)
    
    @staticmethod
    def _rule_based_summarize(messages: List[BaseMessage]) -> str:
        """基于规则的简单总结方法
        
        Args:
            messages: 要总结的消息列表
            
        Returns:
            总结文本
        """
        # 提取主题和关键点
        topics = set()
        user_queries = []
        ai_responses = []
        
        for msg in messages:
            content = getattr(msg, "content", "")
            if not content or not isinstance(content, str):
                continue
                
            # 提取可能的主题
            words = content.split()
            if len(words) > 3:
                # 简单方式：取前几个词作为主题候选
                potential_topic = " ".join(words[:min(len(words), 5)])
                if len(potential_topic) > 10:
                    topics.add(potential_topic)
            
            # 记录用户查询和AI响应
            if isinstance(msg, HumanMessage):
                user_queries.append(content)
            elif isinstance(msg, AIMessage):
                ai_responses.append(content)
        
        # 构建总结
        summary_parts = []
        
        # 添加主题
        if topics:
            topics_text = "、".join(list(topics)[:3])
            summary_parts.append(f"对话主题: {topics_text}")
        
        # 添加用户查询概述
        if user_queries:
            query_count = len(user_queries)
            query_sample = user_queries[0]
            if len(query_sample) > 100:
                query_sample = query_sample[:97] + "..."
            summary_parts.append(f"用户进行了{query_count}次提问，最初提问: {query_sample}")
        
        # 添加AI响应概述
        if ai_responses:
            response_count = len(ai_responses)
            summary_parts.append(f"AI提供了{response_count}次回答")
        
        # 组合总结
        if summary_parts:
            return "。".join(summary_parts)
        else:
            return "对话历史中没有足够的内容可以总结"
    
    @staticmethod
    def trim_messages(
        messages: List[BaseMessage], 
        max_messages: int = 10,
        max_tokens: Optional[int] = None,
        token_counter: Optional[Callable[[List[BaseMessage]], int]] = None
    ) -> List[RemoveMessage]:
        """裁剪消息历史，保留最重要的和最近的消息
        
        Args:
            messages: 消息列表
            max_messages: 保留的最大消息数
            max_tokens: 最大token数
            token_counter: 用于计算token数的函数
            
        Returns:
            标记为删除的消息列表
        """
        if len(messages) <= max_messages:
            return []  # 无需裁剪
        
        # 保留的消息类型
        keep_types = (SystemMessage, HumanMessage, AIMessage)
        
        # 按类型和位置重要性排序
        rated_messages = []
        for i, msg in enumerate(messages):
            # 消息评分 (越高越重要)
            score = 0
            
            # 系统消息最重要
            if isinstance(msg, SystemMessage):
                score += 100
            # 最近的消息更重要
            recency_score = i / len(messages) * 50
            score += recency_score
            
            # 添加到评分列表
            if hasattr(msg, "id"):
                rated_messages.append((msg, score, getattr(msg, "id")))
            else:
                # 生成一个临时ID
                tmp_id = f"msg_{i}_{hash(str(msg.content))}"
                rated_messages.append((msg, score, tmp_id))
        
        # 按重要性排序
        rated_messages.sort(key=lambda x: x[1], reverse=True)
        
        # 选择保留的消息
        to_keep_ids = {item[2] for item in rated_messages[:max_messages]}
        
        # 生成要删除的消息列表
        to_remove = []
        for msg in messages:
            if hasattr(msg, "id"):
                msg_id = msg.id
            else:
                # 查找对应的临时ID
                for _, _, tmp_id in rated_messages:
                    if hash(str(msg.content)) in tmp_id:
                        msg_id = tmp_id
                        break
                else:
                    continue  # 跳过无法识别ID的消息
            
            if msg_id not in to_keep_ids:
                # 修复: 使用新的方式创建RemoveMessage
                to_remove.append(RemoveMessage(id=msg_id))
        
        return to_remove
    
    @staticmethod
    def filter_messages(
        messages: List[BaseMessage], 
        keep_system: bool = True,
        keep_last_n: int = 4
    ) -> List[BaseMessage]:
        """过滤消息，保留系统消息和最后N条消息
        
        Args:
            messages: 消息列表
            keep_system: 是否保留系统消息
            keep_last_n: 保留的最后n条消息数
            
        Returns:
            过滤后的消息列表
        """
        if len(messages) <= keep_last_n:
            return messages  # 无需过滤
        
        # 分离系统消息和其他消息
        system_msgs = []
        other_msgs = []
        
        for msg in messages:
            if keep_system and isinstance(msg, SystemMessage):
                system_msgs.append(msg)
            else:
                other_msgs.append(msg)
        
        # 保留最后N条非系统消息
        recent_msgs = other_msgs[-keep_last_n:] if other_msgs else []
        
        # 组合结果
        return system_msgs + recent_msgs 