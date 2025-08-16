"""
Agent间标准通信协议模块 - Stage 5实现

该模块定义了基于LangGraph的标准化Agent通信协议，支持：
1. 消息格式标准化
2. 任务传递和状态同步
3. 能力查询和响应
4. 执行状态报告
5. 中断和异常处理
"""

import logging
import json
from typing import Dict, List, Any, Optional, Union, Literal
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
import uuid

logger = logging.getLogger(__name__)

# 消息类型枚举
class MessageType(str, Enum):
    """通信消息类型"""
    # 任务相关
    TASK_HANDOFF = "task_handoff"          # 任务交接
    TASK_REQUEST = "task_request"          # 任务请求
    TASK_RESPONSE = "task_response"        # 任务响应
    TASK_STATUS = "task_status"            # 任务状态更新
    
    # 能力相关
    CAPABILITY_QUERY = "capability_query"    # 能力查询
    CAPABILITY_RESPONSE = "capability_response"  # 能力响应
    CAPABILITY_UPDATE = "capability_update"      # 能力更新
    
    # 执行相关
    EXECUTION_START = "execution_start"      # 执行开始
    EXECUTION_STATUS = "execution_status"    # 执行状态
    EXECUTION_RESULT = "execution_result"    # 执行结果
    EXECUTION_ERROR = "execution_error"      # 执行错误
    
    # 中断相关
    INTERRUPT_REQUEST = "interrupt_request"  # 中断请求
    INTERRUPT_RESPONSE = "interrupt_response"  # 中断响应
    
    # 系统相关
    HEARTBEAT = "heartbeat"                  # 心跳
    SYSTEM_STATUS = "system_status"          # 系统状态
    ERROR = "error"                          # 错误消息

# Agent类型枚举
class AgentType(str, Enum):
    """Agent类型"""
    META_SUPERVISOR = "meta_supervisor"
    TASK_PLANNER = "task_planner"
    RUNTIME_SUPERVISOR = "runtime_supervisor"
    CRITIC = "critic"
    DATA_AGENT = "data_agent"
    EXPERT_AGENT = "expert_agent"
    MAIN_AGENT = "main_agent"
    SYSTEM_REGISTRY = "system_registry"

# 基础消息模型
class AgentMessage(BaseModel):
    """Agent间通信的基础消息模型"""
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    message_type: MessageType
    from_agent: AgentType
    to_agent: Union[AgentType, List[AgentType]]  # 支持单播和多播
    timestamp: datetime = Field(default_factory=datetime.now)
    protocol_version: str = "1.0"
    correlation_id: Optional[str] = None  # 用于关联请求和响应
    payload: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None
    
    class Config:
        arbitrary_types_allowed = True

# 具体消息类型定义
class TaskHandoffMessage(AgentMessage):
    """任务交接消息"""
    message_type: Literal[MessageType.TASK_HANDOFF] = MessageType.TASK_HANDOFF
    
    def __init__(self, **data):
        super().__init__(**data)
        # 确保payload包含必要字段
        required_fields = ["task_id", "task_type", "description"]
        for field in required_fields:
            if field not in self.payload:
                raise ValueError(f"TaskHandoffMessage payload must contain '{field}'")

class CapabilityQueryMessage(AgentMessage):
    """能力查询消息"""
    message_type: Literal[MessageType.CAPABILITY_QUERY] = MessageType.CAPABILITY_QUERY
    
    def __init__(self, **data):
        super().__init__(**data)
        # payload应包含query和category
        if "query" not in self.payload:
            self.payload["query"] = "all"

class ExecutionStatusMessage(AgentMessage):
    """执行状态消息"""
    message_type: Literal[MessageType.EXECUTION_STATUS] = MessageType.EXECUTION_STATUS
    
    def __init__(self, **data):
        super().__init__(**data)
        # 确保包含状态信息
        if "status" not in self.payload:
            raise ValueError("ExecutionStatusMessage payload must contain 'status'")

class InterruptRequestMessage(AgentMessage):
    """中断请求消息"""
    message_type: Literal[MessageType.INTERRUPT_REQUEST] = MessageType.INTERRUPT_REQUEST
    
    def __init__(self, **data):
        super().__init__(**data)
        # 确保包含中断原因
        if "reason" not in self.payload:
            raise ValueError("InterruptRequestMessage payload must contain 'reason'")

# 消息工厂
class MessageFactory:
    """消息工厂，用于创建标准化消息"""
    
    @staticmethod
    def create_task_handoff(
        from_agent: AgentType,
        to_agent: AgentType,
        task_id: str,
        task_type: str,
        description: str,
        priority: str = "normal",
        context: Optional[Dict[str, Any]] = None
    ) -> TaskHandoffMessage:
        """创建任务交接消息"""
        return TaskHandoffMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            payload={
                "task_id": task_id,
                "task_type": task_type,
                "description": description,
                "priority": priority,
                "context": context or {}
            }
        )
    
    @staticmethod
    def create_capability_query(
        from_agent: AgentType,
        to_agent: AgentType = AgentType.SYSTEM_REGISTRY,
        query: str = "all",
        category: Optional[str] = None
    ) -> CapabilityQueryMessage:
        """创建能力查询消息"""
        return CapabilityQueryMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            payload={
                "query": query,
                "category": category
            }
        )
    
    @staticmethod
    def create_execution_status(
        from_agent: AgentType,
        to_agent: AgentType,
        task_id: str,
        status: str,
        progress: float = 0.0,
        details: Optional[Dict[str, Any]] = None
    ) -> ExecutionStatusMessage:
        """创建执行状态消息"""
        return ExecutionStatusMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            payload={
                "task_id": task_id,
                "status": status,
                "progress": progress,
                "details": details or {}
            }
        )
    
    @staticmethod
    def create_interrupt_request(
        from_agent: AgentType,
        to_agent: AgentType,
        reason: str,
        interrupt_type: str,
        action_required: str,
        context: Optional[Dict[str, Any]] = None
    ) -> InterruptRequestMessage:
        """创建中断请求消息"""
        return InterruptRequestMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            payload={
                "reason": reason,
                "interrupt_type": interrupt_type,
                "action_required": action_required,
                "context": context or {}
            }
        )

# 消息路由器
class MessageRouter:
    """消息路由器，负责消息的分发和路由"""
    
    def __init__(self):
        self._handlers: Dict[MessageType, List[callable]] = {}
        self._agent_queues: Dict[AgentType, List[AgentMessage]] = {}
        logger.info("消息路由器初始化完成")
    
    def register_handler(self, message_type: MessageType, handler: callable):
        """注册消息处理器"""
        if message_type not in self._handlers:
            self._handlers[message_type] = []
        self._handlers[message_type].append(handler)
        logger.info(f"注册处理器 {handler.__name__} 用于消息类型 {message_type}")
    
    def route_message(self, message: AgentMessage) -> Dict[str, Any]:
        """路由消息到相应的处理器"""
        handlers = self._handlers.get(message.message_type, [])
        
        if not handlers:
            logger.warning(f"没有找到消息类型 {message.message_type} 的处理器")
            return {"success": False, "error": "No handler found"}
        
        results = []
        for handler in handlers:
            try:
                result = handler(message)
                results.append(result)
            except Exception as e:
                logger.error(f"处理消息时出错: {str(e)}")
                results.append({"success": False, "error": str(e)})
        
        return {"success": True, "results": results}
    
    def send_to_agent(self, message: AgentMessage):
        """发送消息到特定Agent的队列"""
        to_agents = message.to_agent if isinstance(message.to_agent, list) else [message.to_agent]
        
        for agent in to_agents:
            if agent not in self._agent_queues:
                self._agent_queues[agent] = []
            self._agent_queues[agent].append(message)
            logger.debug(f"消息 {message.message_id} 发送到 {agent} 的队列")
    
    def get_agent_messages(self, agent: AgentType) -> List[AgentMessage]:
        """获取特定Agent的消息队列"""
        messages = self._agent_queues.get(agent, [])
        # 清空队列
        if agent in self._agent_queues:
            self._agent_queues[agent] = []
        return messages

# 消息序列化和反序列化
class MessageSerializer:
    """消息序列化器"""
    
    @staticmethod
    def serialize(message: AgentMessage) -> str:
        """序列化消息为JSON字符串"""
        data = message.dict()
        # 转换datetime为ISO格式
        data["timestamp"] = data["timestamp"].isoformat()
        return json.dumps(data)
    
    @staticmethod
    def deserialize(data: str) -> AgentMessage:
        """从JSON字符串反序列化消息"""
        message_data = json.loads(data)
        # 转换ISO格式为datetime
        message_data["timestamp"] = datetime.fromisoformat(message_data["timestamp"])
        
        # 根据消息类型创建相应的消息对象
        message_type = MessageType(message_data["message_type"])
        
        if message_type == MessageType.TASK_HANDOFF:
            return TaskHandoffMessage(**message_data)
        elif message_type == MessageType.CAPABILITY_QUERY:
            return CapabilityQueryMessage(**message_data)
        elif message_type == MessageType.EXECUTION_STATUS:
            return ExecutionStatusMessage(**message_data)
        elif message_type == MessageType.INTERRUPT_REQUEST:
            return InterruptRequestMessage(**message_data)
        else:
            return AgentMessage(**message_data)

# 创建全局消息路由器实例
message_router = MessageRouter()

# 辅助函数
def send_message(message: AgentMessage):
    """发送消息的便捷函数"""
    message_router.send_to_agent(message)
    logger.info(f"发送消息 {message.message_type} 从 {message.from_agent} 到 {message.to_agent}")

def broadcast_message(
    from_agent: AgentType,
    message_type: MessageType,
    payload: Dict[str, Any],
    exclude_agents: Optional[List[AgentType]] = None
):
    """广播消息到所有Agent（除了排除列表中的）"""
    all_agents = list(AgentType)
    to_agents = [a for a in all_agents if a != from_agent and (not exclude_agents or a not in exclude_agents)]
    
    message = AgentMessage(
        message_type=message_type,
        from_agent=from_agent,
        to_agent=to_agents,
        payload=payload
    )
    
    send_message(message)
    logger.info(f"广播消息 {message_type} 从 {from_agent}")

# 集成到LangGraph状态
def inject_message_to_state(state: Dict[str, Any], message: AgentMessage) -> Dict[str, Any]:
    """将消息注入到LangGraph状态中"""
    if "agent_messages" not in state:
        state["agent_messages"] = []
    
    state["agent_messages"].append(message.dict())
    
    # 更新最近的Agent通信
    state["latest_agent_communication"] = {
        "from": message.from_agent,
        "to": message.to_agent,
        "type": message.message_type,
        "timestamp": message.timestamp.isoformat()
    }
    
    return state

def extract_messages_from_state(state: Dict[str, Any], agent: AgentType) -> List[AgentMessage]:
    """从LangGraph状态中提取特定Agent的消息"""
    messages = []
    
    if "agent_messages" in state:
        for msg_data in state["agent_messages"]:
            try:
                # 反序列化消息
                msg = MessageSerializer.deserialize(json.dumps(msg_data))
                # 检查是否是发给该Agent的
                to_agents = msg.to_agent if isinstance(msg.to_agent, list) else [msg.to_agent]
                if agent in to_agents:
                    messages.append(msg)
            except Exception as e:
                logger.error(f"提取消息时出错: {str(e)}")
    
    return messages 