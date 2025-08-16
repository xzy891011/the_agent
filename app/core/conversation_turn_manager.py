"""
对话轮次管理器 - 解决流式输出与历史存储的不匹配问题

主要功能：
1. 流式输出过程中累积token为完整消息
2. 管理用户-助手对话轮次
3. 存储完整对话到历史记录
4. 为前端提供正确格式的历史消息
"""

import logging
import time
import uuid
from typing import Dict, List, Optional, Any, Union, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage

logger = logging.getLogger(__name__)


class TurnType(str, Enum):
    """对话轮次类型"""
    USER_INPUT = "user_input"           # 用户输入
    ASSISTANT_RESPONSE = "assistant_response"  # 助手回复
    SYSTEM_MESSAGE = "system_message"   # 系统消息
    TOOL_EXECUTION = "tool_execution"   # 工具执行


class TurnStatus(str, Enum):
    """轮次状态"""
    PENDING = "pending"         # 等待开始
    STREAMING = "streaming"     # 流式输出中
    COMPLETED = "completed"     # 已完成
    ERROR = "error"            # 出错


@dataclass
class ConversationTurn:
    """对话轮次数据类"""
    turn_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    turn_type: TurnType = TurnType.ASSISTANT_RESPONSE
    status: TurnStatus = TurnStatus.PENDING
    session_id: Optional[str] = None
    
    # 消息内容
    content_parts: List[str] = field(default_factory=list)  # 累积的内容片段
    complete_content: str = ""  # 完整内容
    
    # 元数据
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    source: Optional[str] = None  # 来源智能体/节点
    
    # 流式消息信息
    stream_messages: List[Dict[str, Any]] = field(default_factory=list)  # 原始流式消息
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 工具相关（如果是工具执行轮次）
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_output: Optional[Any] = None
    
    def add_content_part(self, part: str) -> None:
        """添加内容片段"""
        if part:
            self.content_parts.append(part)
            self.complete_content += part
    
    def mark_completed(self) -> None:
        """标记轮次完成"""
        self.status = TurnStatus.COMPLETED
        self.end_time = time.time()
    
    def mark_error(self, error_msg: str) -> None:
        """标记轮次出错"""
        self.status = TurnStatus.ERROR
        self.end_time = time.time()
        self.metadata["error"] = error_msg
    
    def to_message(self) -> BaseMessage:
        """转换为LangChain消息对象"""
        if self.turn_type == TurnType.USER_INPUT:
            return HumanMessage(
                content=self.complete_content,
                additional_kwargs={"turn_id": self.turn_id, "metadata": self.metadata}
            )
        elif self.turn_type == TurnType.ASSISTANT_RESPONSE:
            return AIMessage(
                content=self.complete_content,
                additional_kwargs={"turn_id": self.turn_id, "metadata": self.metadata}
            )
        elif self.turn_type == TurnType.SYSTEM_MESSAGE:
            return SystemMessage(
                content=self.complete_content,
                additional_kwargs={"turn_id": self.turn_id, "metadata": self.metadata}
            )
        elif self.turn_type == TurnType.TOOL_EXECUTION:
            return ToolMessage(
                content=self.complete_content,
                tool_call_id=self.metadata.get("tool_call_id", ""),
                name=self.tool_name or "unknown",
                additional_kwargs={"turn_id": self.turn_id, "metadata": self.metadata}
            )
        else:
            return AIMessage(content=self.complete_content)
    
    def to_api_format(self) -> Dict[str, Any]:
        """转换为API格式的消息"""
        role_mapping = {
            TurnType.USER_INPUT: "user",
            TurnType.ASSISTANT_RESPONSE: "assistant", 
            TurnType.SYSTEM_MESSAGE: "system",
            TurnType.TOOL_EXECUTION: "tool"
        }
        
        return {
            "id": self.turn_id,
            "role": role_mapping.get(self.turn_type, "assistant"),
            "content": self.complete_content,
            "timestamp": datetime.fromtimestamp(self.start_time).isoformat(),
            "type": "text",
            "metadata": {
                **self.metadata,
                "turn_type": self.turn_type.value,
                "status": self.status.value,
                "source": self.source,
                "duration": (self.end_time - self.start_time) if self.end_time else None
            }
        }


class ConversationTurnManager:
    """对话轮次管理器"""
    
    def __init__(self, session_id: Optional[str] = None):
        """
        初始化对话轮次管理器
        
        Args:
            session_id: 会话ID
        """
        self.session_id = session_id
        self.active_turns: Dict[str, ConversationTurn] = {}  # 正在进行的轮次
        self.completed_turns: List[ConversationTurn] = []    # 已完成的轮次
        self.current_assistant_turn: Optional[ConversationTurn] = None  # 当前AI回复轮次
        
        logger.info(f"对话轮次管理器初始化完成，会话ID: {session_id}")
    
    def start_user_turn(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        开始用户输入轮次
        
        Args:
            content: 用户输入内容
            metadata: 元数据
            
        Returns:
            轮次ID
        """
        turn = ConversationTurn(
            turn_type=TurnType.USER_INPUT,
            status=TurnStatus.COMPLETED,  # 用户输入通常是立即完成的
            session_id=self.session_id,
            complete_content=content,
            metadata=metadata or {}
        )
        turn.mark_completed()
        
        self.completed_turns.append(turn)
        logger.info(f"用户输入轮次完成: {turn.turn_id}, 内容长度: {len(content)}")
        
        return turn.turn_id
    
    def start_assistant_turn(self, source: Optional[str] = None, 
                           metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        开始助手回复轮次
        
        Args:
            source: 来源智能体/节点
            metadata: 元数据
            
        Returns:
            轮次ID
        """
        # 如果有正在进行的助手轮次，先完成它
        if self.current_assistant_turn and self.current_assistant_turn.status == TurnStatus.STREAMING:
            logger.warning("强制完成未完成的助手轮次")
            self.complete_assistant_turn()
        
        turn = ConversationTurn(
            turn_type=TurnType.ASSISTANT_RESPONSE,
            status=TurnStatus.STREAMING,
            session_id=self.session_id,
            source=source,
            metadata=metadata or {}
        )
        
        self.current_assistant_turn = turn
        self.active_turns[turn.turn_id] = turn
        
        logger.info(f"助手回复轮次开始: {turn.turn_id}, 来源: {source}")
        return turn.turn_id
    
    def add_assistant_content(self, content: str, stream_message: Optional[Dict[str, Any]] = None) -> bool:
        """
        添加助手回复内容片段
        
        Args:
            content: 内容片段
            stream_message: 原始流式消息
            
        Returns:
            是否成功添加
        """
        if not self.current_assistant_turn:
            logger.warning("没有活跃的助手轮次，创建新的轮次")
            self.start_assistant_turn()
        
        if self.current_assistant_turn.status != TurnStatus.STREAMING:
            logger.warning("当前助手轮次不在流式状态，忽略内容")
            return False
        
        # 添加内容片段
        self.current_assistant_turn.add_content_part(content)
        
        # 保存原始流式消息
        if stream_message:
            self.current_assistant_turn.stream_messages.append(stream_message)
        
        logger.debug(f"添加助手内容片段: 长度={len(content)}, 总长度={len(self.current_assistant_turn.complete_content)}")
        return True
    
    def complete_assistant_turn(self) -> Optional[str]:
        """
        完成当前助手回复轮次
        
        Returns:
            完成的轮次ID，如果没有活跃轮次则返回None
        """
        if not self.current_assistant_turn:
            logger.warning("没有活跃的助手轮次可以完成")
            return None
        
        turn = self.current_assistant_turn
        turn.mark_completed()
        
        # 移除活跃轮次，添加到已完成列表
        if turn.turn_id in self.active_turns:
            del self.active_turns[turn.turn_id]
        self.completed_turns.append(turn)
        
        # 清除当前助手轮次
        self.current_assistant_turn = None
        
        logger.info(f"助手回复轮次完成: {turn.turn_id}, 内容长度: {len(turn.complete_content)}")
        return turn.turn_id
    
    def start_tool_turn(self, tool_name: str, tool_input: Dict[str, Any], 
                       source: Optional[str] = None) -> str:
        """
        开始工具执行轮次
        
        Args:
            tool_name: 工具名称
            tool_input: 工具输入
            source: 来源
            
        Returns:
            轮次ID
        """
        turn = ConversationTurn(
            turn_type=TurnType.TOOL_EXECUTION,
            status=TurnStatus.STREAMING,
            session_id=self.session_id,
            source=source,
            tool_name=tool_name,
            tool_input=tool_input,
            metadata={"tool_start_time": time.time()}
        )
        
        self.active_turns[turn.turn_id] = turn
        logger.info(f"工具执行轮次开始: {turn.turn_id}, 工具: {tool_name}")
        
        return turn.turn_id
    
    def complete_tool_turn(self, turn_id: str, tool_output: Any) -> bool:
        """
        完成工具执行轮次
        
        Args:
            turn_id: 轮次ID
            tool_output: 工具输出
            
        Returns:
            是否成功完成
        """
        if turn_id not in self.active_turns:
            logger.warning(f"工具轮次不存在: {turn_id}")
            return False
        
        turn = self.active_turns[turn_id]
        if turn.turn_type != TurnType.TOOL_EXECUTION:
            logger.warning(f"轮次类型不是工具执行: {turn_id}")
            return False
        
        # 设置工具输出和完整内容
        turn.tool_output = tool_output
        turn.complete_content = str(tool_output) if tool_output else ""
        turn.mark_completed()
        
        # 移除活跃轮次，添加到已完成列表
        del self.active_turns[turn_id]
        self.completed_turns.append(turn)
        
        logger.info(f"工具执行轮次完成: {turn_id}")
        return True
    
    def process_stream_message(self, stream_message: Dict[str, Any]) -> Optional[str]:
        """
        处理流式消息，自动管理轮次
        
        Args:
            stream_message: 流式消息
            
        Returns:
            处理的轮次ID，如果未处理则返回None
        """
        try:
            role = stream_message.get("role")
            content = stream_message.get("content", "")
            source = stream_message.get("source")
            
            if role == "assistant" and content:
                # 如果没有活跃的助手轮次，开始新的轮次
                if not self.current_assistant_turn:
                    self.start_assistant_turn(source=source)
                
                # 添加内容
                self.add_assistant_content(content, stream_message)
                return self.current_assistant_turn.turn_id
            
            elif role == "tool":
                # 工具消息处理（这里简化处理，实际可能需要更复杂的逻辑）
                tool_name = stream_message.get("tool_name", "unknown")
                if content:
                    turn_id = self.start_tool_turn(tool_name, {}, source)
                    self.complete_tool_turn(turn_id, content)
                    return turn_id
            
            # 其他类型的消息暂时不处理
            return None
            
        except Exception as e:
            logger.error(f"处理流式消息失败: {str(e)}")
            return None
    
    def get_conversation_history(self, include_incomplete: bool = False) -> List[BaseMessage]:
        """
        获取对话历史（LangChain消息格式）
        
        Args:
            include_incomplete: 是否包含未完成的轮次
            
        Returns:
            LangChain消息列表
        """
        messages = []
        
        # 添加已完成的轮次
        for turn in self.completed_turns:
            messages.append(turn.to_message())
        
        # 添加未完成的轮次（如果需要）
        if include_incomplete:
            for turn in self.active_turns.values():
                if turn.complete_content:  # 只有有内容的才添加
                    messages.append(turn.to_message())
        
        logger.debug(f"获取对话历史: {len(messages)} 条消息")
        return messages
    
    def get_api_conversation_history(self, include_incomplete: bool = False) -> List[Dict[str, Any]]:
        """
        获取对话历史（API格式）
        
        Args:
            include_incomplete: 是否包含未完成的轮次
            
        Returns:
            API格式的消息列表
        """
        messages = []
        
        # 添加已完成的轮次
        for turn in self.completed_turns:
            if turn.complete_content:  # 只有有内容的才添加
                messages.append(turn.to_api_format())
        
        # 添加未完成的轮次（如果需要）
        if include_incomplete:
            for turn in self.active_turns.values():
                if turn.complete_content:  # 只有有内容的才添加
                    messages.append(turn.to_api_format())
        
        logger.debug(f"获取API对话历史: {len(messages)} 条消息")
        return messages
    
    def cleanup_completed_turns(self, keep_last_n: int = 10) -> int:
        """
        清理已完成的轮次，保留最后N个
        
        Args:
            keep_last_n: 保留的轮次数量
            
        Returns:
            清理的轮次数量
        """
        if len(self.completed_turns) <= keep_last_n:
            return 0
        
        removed_count = len(self.completed_turns) - keep_last_n
        self.completed_turns = self.completed_turns[-keep_last_n:]
        
        logger.info(f"清理了 {removed_count} 个已完成的轮次")
        return removed_count
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "session_id": self.session_id,
            "completed_turns": len(self.completed_turns),
            "active_turns": len(self.active_turns),
            "current_assistant_turn_active": self.current_assistant_turn is not None,
            "current_assistant_content_length": len(self.current_assistant_turn.complete_content) if self.current_assistant_turn else 0
        }
    
    def reset(self) -> None:
        """重置管理器状态"""
        self.active_turns.clear()
        self.completed_turns.clear()
        self.current_assistant_turn = None
        logger.info("对话轮次管理器已重置")


class MessageAccumulator:
    """消息累积器 - 将流式token累积为完整消息"""
    
    def __init__(self):
        self.accumulated_content = ""
        self.message_parts = []
        self.start_time = time.time()
        self.last_update = time.time()
    
    def add_token(self, token: str) -> None:
        """添加token"""
        self.accumulated_content += token
        self.message_parts.append(token)
        self.last_update = time.time()
    
    def get_complete_message(self) -> str:
        """获取完整消息"""
        return self.accumulated_content
    
    def reset(self) -> None:
        """重置累积器"""
        self.accumulated_content = ""
        self.message_parts.clear()
        self.start_time = time.time()
        self.last_update = time.time()
    
    def is_empty(self) -> bool:
        """检查是否为空"""
        return len(self.accumulated_content) == 0


def create_conversation_turn_manager(session_id: Optional[str] = None) -> ConversationTurnManager:
    """
    工厂函数：创建对话轮次管理器
    
    Args:
        session_id: 会话ID
        
    Returns:
        对话轮次管理器实例
    """
    return ConversationTurnManager(session_id=session_id) 