"""
LangGraph流式处理器
负责监听Graph执行过程中的各种事件，转换为统一的流式消息格式

基于LangGraph官方文档优化: https://langchain-ai.github.io/langgraph/how-tos/streaming/
支持的流模式:
- messages: 流式传输2元组(LLM token, metadata)
- updates: 流式传输每步之后的状态更新
- custom: 流式传输自定义数据
- values: 流式传输完整状态值（通常不推送到前端）
- debug: 流式传输调试信息
"""

import logging
import time
from typing import Dict, Any, Optional, Generator, List, Callable, Union
from datetime import datetime
import asyncio
import json

from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, ToolMessage

from app.ui.streaming_types import (
    StreamMessageType, BaseStreamMessage, NodeStatusMessage, RouterMessage,
    LLMTokenMessage, ToolExecutionMessage, FileGeneratedMessage, 
    AgentThinkingMessage, ErrorMessage, InfoMessage,
    create_message, serialize_message
)

logger = logging.getLogger(__name__)


class LangGraphStreamingProcessor:
    """LangGraph流式处理器 - 基于官方文档优化"""
    
    def __init__(self, session_id: Optional[str] = None):
        """
        初始化流式处理器
        
        Args:
            session_id: 会话ID
        """
        self.session_id = session_id
        self.active_nodes: Dict[str, float] = {}  # 节点名 -> 开始时间
        self.message_buffer: List[BaseStreamMessage] = []
        
        # 事件处理器映射
        self.event_handlers = {
            "on_chain_start": self._handle_node_start,
            "on_chain_end": self._handle_node_end,
            "on_chain_error": self._handle_node_error,
            "on_llm_start": self._handle_llm_start,
            "on_llm_new_token": self._handle_llm_token,
            "on_llm_end": self._handle_llm_end,
            "on_tool_start": self._handle_tool_start,
            "on_tool_end": self._handle_tool_end,
            "on_tool_error": self._handle_tool_error,
        }
        
        logger.info(f"LangGraph流式处理器初始化完成，会话ID: {session_id}")
    
    def process_langgraph_stream(
        self, 
        stream_generator: Generator,
        stream_modes: List[str] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        处理LangGraph流式输出
        
        Args:
            stream_generator: LangGraph流生成器
            stream_modes: 流模式列表
            
        Yields:
            处理后的流式消息
        """
        if stream_modes is None:
            stream_modes = ["messages", "custom", "updates"]  # 默认不包含values以避免冗余数据
        
        logger.info(f"开始处理LangGraph流，模式: {stream_modes}")
        
        try:
            for chunk in stream_generator:
                # 处理不同类型的流数据
                messages = self._process_stream_chunk(chunk)
                
                # 产生所有生成的消息
                for message in messages:
                    yield serialize_message(message)
                    
        except Exception as e:
            logger.error(f"处理LangGraph流时出错: {str(e)}")
            error_msg = create_message(
                StreamMessageType.ERROR,
                session_id=self.session_id,
                source="streaming_processor",
                error_message=f"流处理错误: {str(e)}",
                error_code="STREAM_PROCESSING_ERROR"
            )
            yield serialize_message(error_msg)
    
    def _process_stream_chunk(self, chunk: Any) -> List[BaseStreamMessage]:
        """
        处理单个流数据块 - 基于真实格式优化
        
        Args:
            chunk: LangGraph流数据块
            
        Returns:
            生成的消息列表
        """
        messages = []
        
        try:
            # 添加调试日志来查看chunk格式
            logger.debug(f"[DEBUG] 收到chunk类型: {type(chunk)}, 内容预览: {str(chunk)[:200]}...")
            
            # 基于LangGraph官方文档的chunk类型判断
            if self._is_message_chunk(chunk):
                logger.debug(f"[DEBUG] 识别为messages流chunk")
                messages.extend(self._handle_message_chunk(chunk))
            
            elif self._is_update_chunk(chunk):
                logger.debug(f"[DEBUG] 识别为updates流chunk")
                messages.extend(self._handle_update_chunk(chunk))
            
            elif self._is_custom_chunk(chunk):
                logger.debug(f"[DEBUG] 识别为custom流chunk")
                messages.extend(self._handle_custom_chunk(chunk))
            
            elif self._is_values_chunk(chunk):
                logger.debug(f"[DEBUG] 识别为values流chunk（通常跳过处理）")
                # values流包含完整状态，通常不需要推送到前端
                # 只在需要特定状态信息时才处理
                messages.extend(self._handle_values_chunk_selective(chunk))
            
            else:
                # 未识别的chunk格式，尝试通用处理
                logger.debug(f"[DEBUG] 未识别的chunk格式，尝试通用处理")
                fallback_messages = self._handle_unknown_chunk(chunk)
                messages.extend(fallback_messages)
                
        except Exception as e:
            logger.error(f"处理流数据块时出错: {str(e)}, chunk类型: {type(chunk)}")
            error_msg = create_message(
                StreamMessageType.ERROR,
                session_id=self.session_id,
                source="chunk_processor",
                error_message=f"数据块处理错误: {str(e)}"
            )
            messages.append(error_msg)
        
        return messages
    
    def _is_message_chunk(self, chunk: Any) -> bool:
        """
        判断是否为消息流数据块 - 基于官方文档优化
        
        LangGraph官方消息流格式:
        1. ('messages', (LLM_token, metadata)) - 标准格式
        2. (LLM_token, metadata) - 直接格式
        """
        if not isinstance(chunk, tuple) or len(chunk) < 2:
            return False
        
        # 格式1: ('messages', ...)
        if chunk[0] == 'messages':
            return True
        
        # 排除其他已知的流类型标识符
        if chunk[0] in ['custom', 'updates', 'values', 'debug']:
            return False
        
        # 格式2: (LLM_token, metadata) - 检查第一个元素是否为LLM输出
        first_element = chunk[0]
        second_element = chunk[1]
        
        # 检查是否是LangChain消息对象
        try:
            from langchain_core.messages import BaseMessage
            if isinstance(first_element, BaseMessage):
                return True
        except ImportError:
            # 回退检查：是否有消息对象的典型属性
            if hasattr(first_element, 'content'):
                return True
        
        # 检查是否是字符串token（LLM的文本输出）
        # 但要确保第一个元素不是流类型标识符
        if isinstance(first_element, str) and first_element.strip():
            # 第二个元素应该是metadata字典
            if isinstance(second_element, dict):
                # 进一步检查：确保不是其他流格式的误判
                # LLM token通常不会是单个常见词汇
                if len(first_element) > 2 and not first_element.isalpha():
                    return True
        
        return False
    
    def _is_update_chunk(self, chunk: Any) -> bool:
        """判断是否为更新流数据块"""
        # LangGraph更新流格式: ('updates', {...})
        if isinstance(chunk, tuple) and len(chunk) == 2 and chunk[0] == 'updates':
            return True
        return False
    
    def _is_custom_chunk(self, chunk: Any) -> bool:
        """判断是否为自定义流数据块"""
        # LangGraph自定义流格式: ('custom', {...})
        if isinstance(chunk, tuple) and len(chunk) == 2 and chunk[0] == 'custom':
            return True
        return False
    
    def _is_values_chunk(self, chunk: Any) -> bool:
        """判断是否为值流数据块"""
        # LangGraph值流格式: ('values', {...})
        if isinstance(chunk, tuple) and len(chunk) == 2 and chunk[0] == 'values':
            return True
        return False

    def _handle_message_chunk(self, chunk: tuple) -> List[BaseStreamMessage]:
        """
        处理消息流数据块 - 基于真实格式优化
        
        真实格式示例:
        ('messages', (AIMessageChunk(content='```'), metadata))
        """
        messages = []
        
        if len(chunk) < 2:
            logger.warning(f"[DEBUG] 消息chunk格式错误: {chunk}")
            return messages
        
        logger.debug(f"[DEBUG] 处理消息chunk: 长度={len(chunk)}")
        
        try:
            from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage, BaseMessage
            
            # 解析chunk格式
            if chunk[0] == 'messages':
                # 标准格式: ('messages', message_data)
                message_data = chunk[1]
                
                if isinstance(message_data, tuple) and len(message_data) >= 1:
                    # ('messages', (message, metadata))
                    message = message_data[0]
                    metadata = message_data[1] if len(message_data) > 1 else {}
                else:
                    # ('messages', message)
                    message = message_data
                    metadata = {}
            else:
                # 直接格式: (LLM token, metadata)
                message = chunk[0]
                metadata = chunk[1] if len(chunk) > 1 else {}
            
            # 处理不同类型的消息
            if isinstance(message, (AIMessage, AIMessageChunk)):
                # AI消息 - LLM输出
                content = getattr(message, 'content', '')
                
                if content and str(content).strip():  # 只处理非空内容
                    # 确定是否为完整消息
                    is_complete = isinstance(message, AIMessage)
                    
                    # 从metadata中提取节点信息
                    source = "ai_assistant"
                    llm_model = "unknown"
                    if isinstance(metadata, dict):
                        source = metadata.get('langgraph_node', metadata.get('node', source))
                        llm_model = metadata.get('ls_model_name', llm_model)
                    
                    llm_msg = create_message(
                        StreamMessageType.LLM_TOKEN,
                        session_id=self.session_id,
                        source=source,
                        content=str(content),
                        is_complete=is_complete,
                        llm_model=llm_model,
                        metadata=metadata if isinstance(metadata, dict) else {}
                    )
                    messages.append(llm_msg)
                    logger.debug(f"[DEBUG] 创建LLM消息: 完整={is_complete}, 长度={len(str(content))}")
            
            elif isinstance(message, ToolMessage):
                # 工具消息
                tool_msg = create_message(
                    StreamMessageType.TOOL_COMPLETE,
                    session_id=self.session_id,
                    source="tool_executor",
                    tool_name=getattr(message, 'name', 'unknown'),
                    action="complete",
                    output=getattr(message, 'content', ''),
                    metadata=metadata if isinstance(metadata, dict) else {}
                )
                messages.append(tool_msg)
                logger.debug(f"[DEBUG] 创建工具消息")
            
            # 注意：HumanMessage通常不需要推送到前端，因为是用户输入
            
        except ImportError:
            # 降级处理：无法导入LangChain消息类型
            logger.warning("无法导入LangChain消息类型，使用降级处理")
            message = chunk[1] if chunk[0] == 'messages' else chunk[0]
            content = getattr(message, 'content', str(message))
            
            if content and str(content).strip():
                llm_msg = create_message(
                    StreamMessageType.LLM_TOKEN,
                    session_id=self.session_id,
                    source="ai_assistant",
                    content=str(content),
                    is_complete=True
                )
                messages.append(llm_msg)
        
        logger.debug(f"[DEBUG] 消息chunk处理结果: 生成了 {len(messages)} 个消息")
        return messages

    def _handle_update_chunk(self, chunk: tuple) -> List[BaseStreamMessage]:
        """
        处理更新流数据块 - 基于真实格式简化优化
        
        真实格式示例:
        ('updates', {'meta_supervisor': {完整节点状态}})
        
        根据实际需求，我们主要关心:
        1. 节点执行状态（开始/完成/错误）
        2. 路由决策信息
        3. 任务执行进度
        """
        messages = []
        
        if len(chunk) != 2 or chunk[0] != 'updates':
            logger.warning(f"[DEBUG] 更新chunk格式错误: {chunk}")
            return messages
        
        update_data = chunk[1]
        if not isinstance(update_data, dict):
            logger.warning(f"[DEBUG] 更新数据不是字典格式: {type(update_data)}")
            return messages
        
        logger.debug(f"[DEBUG] 处理updates: 节点数量={len(update_data)}")
        
        # 为每个节点的更新生成消息
        for node_name, node_data in update_data.items():
            logger.debug(f"[DEBUG] 处理节点: {node_name}")
            
            # 生成节点状态更新消息
            if isinstance(node_data, dict):
                # 检测节点状态
                status_info = self._analyze_node_status(node_name, node_data)
                
                # 创建节点状态消息
                if status_info['type'] in ['start', 'complete', 'error']:
                    message_type_map = {
                        'start': StreamMessageType.NODE_START,
                        'complete': StreamMessageType.NODE_COMPLETE,
                        'error': StreamMessageType.NODE_ERROR
                    }
                    
                    node_msg = create_message(
                        message_type_map[status_info['type']],
                        session_id=self.session_id,
                        source=node_name,
                        node_name=node_name,
                        status=status_info['status'],
                        details=status_info['details']
                    )
                    messages.append(node_msg)
                
                # 检测路由信息
                route_info = self._extract_route_info(node_name, node_data)
                if route_info:
                    route_msg = create_message(
                        StreamMessageType.ROUTE_DECISION,
                        session_id=self.session_id,
                        source=node_name,
                        from_node=node_name,
                        to_node=route_info['to_node'],
                        reason=route_info['reason']
                    )
                    messages.append(route_msg)
            
            else:
                # 简单状态描述
                info_msg = create_message(
                    StreamMessageType.INFO,
                    session_id=self.session_id,
                    source=node_name,
                    content=f"节点 {node_name}: {str(node_data)[:100]}"
                )
                messages.append(info_msg)
        
        logger.debug(f"[DEBUG] updates处理结果: 生成了 {len(messages)} 个消息")
        return messages
    
    def _analyze_node_status(self, node_name: str, node_data: dict) -> dict:
        """分析节点状态"""
        # 检查是否包含状态指示信息
        status_str = str(node_data).lower()
        
        if any(word in status_str for word in ['start', 'begin', 'running', 'executing']):
            if node_name not in self.active_nodes:
                self.active_nodes[node_name] = time.time()
            return {
                'type': 'start',
                'status': 'started',
                'details': f"节点 {node_name} 开始执行"
            }
        elif any(word in status_str for word in ['complete', 'finish', 'done', 'end']):
            start_time = self.active_nodes.pop(node_name, time.time())
            duration = time.time() - start_time
            return {
                'type': 'complete',
                'status': 'completed',
                'details': f"节点 {node_name} 执行完成，耗时 {duration:.2f}s"
            }
        elif any(word in status_str for word in ['error', 'fail', 'exception']):
            return {
                'type': 'error',
                'status': 'error',
                'details': f"节点 {node_name} 执行出错"
            }
        else:
            return {
                'type': 'update',
                'status': 'updated',
                'details': f"节点 {node_name} 状态更新"
            }
    
    def _extract_route_info(self, node_name: str, node_data: dict) -> Optional[dict]:
        """提取路由信息"""
        # 尝试从元数据中提取路由信息
        metadata = node_data.get('metadata', {})
        if isinstance(metadata, dict):
            # 检查是否包含执行策略（可能包含路由信息）
            execution_strategy = metadata.get('execution_strategy', {})
            if execution_strategy:
                return {
                    'to_node': 'next_node',  # 这里需要根据实际策略提取
                    'reason': '执行策略决策'
                }
        
        return None

    def _handle_custom_chunk(self, chunk: tuple) -> List[BaseStreamMessage]:
        """
        处理自定义流数据块 - 扩展支持更多消息类型
        
        真实格式示例:
        ('custom', {'agent_thinking': '🔍 main_agent 正在分析您的请求...'})
        
        基于get_stream_writer的使用模式，支持:
        1. agent_thinking - Agent思考过程
        2. tool_progress - 工具执行进度  
        3. file_generated - 文件生成通知
        4. node_execution - 节点执行详情
        5. route_decision - 路由决策
        6. task_status - 任务状态更新
        7. llm_response - LLM响应内容
        8. error_info - 错误信息
        9. analysis_result - 分析结果
        """
        messages = []
        
        if len(chunk) != 2 or chunk[0] != 'custom':
            logger.warning(f"[DEBUG] 自定义chunk格式错误: {chunk}")
            return messages
        
        custom_data = chunk[1]
        if not isinstance(custom_data, dict):
            logger.warning(f"[DEBUG] 自定义数据不是字典格式: {type(custom_data)}")
            return messages
        
        logger.debug(f"[DEBUG] 处理custom: 键={list(custom_data.keys())}")
        
        # 处理Agent思考消息
        if "agent_thinking" in custom_data:
            thinking_data = custom_data["agent_thinking"]
            if isinstance(thinking_data, dict):
                # 结构化思考数据
                agent_name = thinking_data.get("agent_name", "unknown")
                content = thinking_data.get("content", "")
                thinking_type = thinking_data.get("thinking_type", "analysis")
            elif isinstance(thinking_data, str):
                # 简单字符串格式
                content = thinking_data
                agent_name = "unknown"
                thinking_type = "analysis"
                
                # 尝试从内容中提取agent名称
                if "main_agent" in thinking_data:
                    agent_name = "main_agent"
                elif "data_agent" in thinking_data:
                    agent_name = "data_agent"
                elif "expert_agent" in thinking_data:
                    agent_name = "expert_agent"
            else:
                logger.warning(f"[DEBUG] 不支持的agent_thinking格式: {type(thinking_data)}")
                content = str(thinking_data)
                agent_name = "unknown"
                thinking_type = "analysis"
            
            thinking_msg = create_message(
                StreamMessageType.AGENT_THINKING,
                session_id=self.session_id,
                source=agent_name,
                agent_name=agent_name,
                thinking_type=thinking_type,
                content=content
            )
            messages.append(thinking_msg)
            logger.debug(f"[DEBUG] 创建Agent思考消息: {agent_name}")
        
        # 处理工具进度消息
        if "tool_progress" in custom_data:
            progress_data = custom_data["tool_progress"]
            if isinstance(progress_data, dict):
                progress_msg = create_message(
                    StreamMessageType.TOOL_PROGRESS,
                    session_id=self.session_id,
                    source=progress_data.get("source", "tool"),
                    tool_name=progress_data.get("tool_name", "unknown"),
                    action="progress",
                    progress=progress_data.get("progress", 0.0),
                    details=progress_data.get("details", "")
                )
                messages.append(progress_msg)
                logger.debug(f"[DEBUG] 创建工具进度消息")
        
        # 处理文件生成消息
        if "file_generated" in custom_data:
            file_data = custom_data["file_generated"]
            if isinstance(file_data, dict):
                file_msg = create_message(
                    StreamMessageType.FILE_GENERATED,
                    session_id=self.session_id,
                    source=file_data.get("source", "system"),
                    file_id=file_data.get("file_id", ""),
                    file_name=file_data.get("file_name", "unknown"),
                    file_type=file_data.get("file_type", "unknown"),
                    file_path=file_data.get("file_path", ""),
                    category="generated"
                )
                messages.append(file_msg)
                logger.debug(f"[DEBUG] 创建文件生成消息")
        
        # 处理节点执行详情
        if "node_execution" in custom_data:
            exec_data = custom_data["node_execution"]
            if isinstance(exec_data, dict):
                action = exec_data.get("action", "update")
                if action == "start":
                    message_type = StreamMessageType.NODE_START
                elif action == "complete":
                    message_type = StreamMessageType.NODE_COMPLETE
                elif action == "error":
                    message_type = StreamMessageType.NODE_ERROR
                else:
                    message_type = StreamMessageType.INFO
                
                if message_type == StreamMessageType.INFO:
                    node_msg = create_message(
                        message_type,
                        session_id=self.session_id,
                        source=exec_data.get("node_name", "unknown"),
                        content=f"节点 {exec_data.get('node_name', 'unknown')} 状态: {exec_data.get('status', 'unknown')}"
                    )
                else:
                    node_msg = create_message(
                        message_type,
                        session_id=self.session_id,
                        source=exec_data.get("node_name", "unknown"),
                        node_name=exec_data.get("node_name", "unknown"),
                        status=exec_data.get("status", "unknown"),
                        details=exec_data.get("details", "")
                    )
                messages.append(node_msg)
                logger.debug(f"[DEBUG] 创建节点执行消息")
        
        # 处理路由决策
        if "route_decision" in custom_data:
            route_data = custom_data["route_decision"]
            if isinstance(route_data, dict):
                route_msg = create_message(
                    StreamMessageType.ROUTE_DECISION,
                    session_id=self.session_id,
                    source=route_data.get("from_node", "router"),
                    from_node=route_data.get("from_node", "unknown"),
                    to_node=route_data.get("to_node", "unknown"),
                    reason=route_data.get("reason", "")
                )
                messages.append(route_msg)
                logger.debug(f"[DEBUG] 创建路由决策消息")
        
        # 处理任务状态更新
        if "task_status" in custom_data:
            task_data = custom_data["task_status"]
            if isinstance(task_data, dict):
                task_name = task_data.get("task_name", "unknown")
                status = task_data.get("status", "unknown")
                progress = task_data.get("progress", 0.0)
                details = task_data.get("details", "")
                
                # 根据状态确定消息类型
                if status in ["started", "running"]:
                    message_type = StreamMessageType.TOOL_START
                    action = "start"
                elif status in ["completed", "finished"]:
                    message_type = StreamMessageType.TOOL_COMPLETE
                    action = "complete"
                elif status in ["failed", "error"]:
                    message_type = StreamMessageType.TOOL_ERROR
                    action = "error"
                else:
                    message_type = StreamMessageType.TOOL_PROGRESS
                    action = "progress"
                
                task_msg = create_message(
                    message_type,
                    session_id=self.session_id,
                    source="task_manager",
                    tool_name=task_name,
                    action=action,
                    progress=progress,
                    details=details if details else f"任务 {task_name} 状态: {status}"
                )
                messages.append(task_msg)
                logger.debug(f"[DEBUG] 创建任务状态消息: {task_name} - {status}")
        
        # 处理LLM响应内容
        if "llm_response" in custom_data:
            llm_data = custom_data["llm_response"]
            if isinstance(llm_data, dict):
                content = llm_data.get("content", "")
                model_name = llm_data.get("model_name", "unknown")
                is_complete = llm_data.get("is_complete", False)
                
                if content and content.strip():
                    llm_msg = create_message(
                        StreamMessageType.LLM_TOKEN,
                        session_id=self.session_id,
                        source="custom_llm",
                        content=content,
                        is_complete=is_complete,
                        llm_model=model_name
                    )
                    messages.append(llm_msg)
                    logger.debug(f"[DEBUG] 创建自定义LLM响应消息")
        
        # 处理错误信息
        if "error_info" in custom_data:
            error_data = custom_data["error_info"]
            if isinstance(error_data, dict):
                error_msg = create_message(
                    StreamMessageType.ERROR,
                    session_id=self.session_id,
                    source=error_data.get("source", "system"),
                    error_message=error_data.get("error_message", ""),
                    error_code=error_data.get("error_code", "")
                )
                messages.append(error_msg)
                logger.debug(f"[DEBUG] 创建错误信息消息")
        
        # 处理分析结果
        if "analysis_result" in custom_data:
            analysis_data = custom_data["analysis_result"]
            if isinstance(analysis_data, dict):
                result_type = analysis_data.get("result_type", "unknown")
                result_data = analysis_data.get("result_data", {})
                confidence = analysis_data.get("confidence", 0.0)
                
                # 创建分析结果信息消息
                content = f"分析结果 ({result_type}): 置信度 {confidence:.2%}"
                if isinstance(result_data, dict) and result_data:
                    # 添加关键结果信息
                    key_info = []
                    for key, value in list(result_data.items())[:3]:  # 只显示前3个键值对
                        key_info.append(f"{key}: {value}")
                    content += f" | {', '.join(key_info)}"
                
                analysis_msg = create_message(
                    StreamMessageType.INFO,
                    session_id=self.session_id,
                    source="analysis_engine",
                    content=content,
                    metadata={
                        "result_type": result_type,
                        "confidence": confidence,
                        "result_data": result_data
                    }
                )
                messages.append(analysis_msg)
                logger.debug(f"[DEBUG] 创建分析结果消息: {result_type}")
        
        # 处理通用自定义消息
        handled_keys = {
            "agent_thinking", "tool_progress", "file_generated", "node_execution", 
            "route_decision", "task_status", "llm_response", "error_info", "analysis_result"
        }
        
        for key, value in custom_data.items():
            if key not in handled_keys:
                info_msg = create_message(
                    StreamMessageType.INFO,
                    session_id=self.session_id,
                    source="custom",
                    content=f"{key}: {str(value)[:200]}{'...' if len(str(value)) > 200 else ''}"
                )
                messages.append(info_msg)
                logger.debug(f"[DEBUG] 创建通用自定义消息: {key}")
        
        logger.debug(f"[DEBUG] custom处理结果: 生成了 {len(messages)} 个消息")
        return messages

    def _handle_values_chunk_selective(self, chunk: tuple) -> List[BaseStreamMessage]:
        """
        选择性处理值流数据块
        
        values流包含完整状态快照，数据量大，通常不推送到前端
        只在需要特定信息时才提取必要部分
        """
        messages = []
        
        if len(chunk) != 2 or chunk[0] != 'values':
            return messages
        
        values_data = chunk[1]
        if not isinstance(values_data, dict):
            return messages
        
        logger.debug(f"[DEBUG] values chunk包含: {list(values_data.keys())}")
        
        # 只提取最新的AI回复（如果有）
        messages_list = values_data.get('messages', [])
        if messages_list:
            try:
                # 获取最后一条AI消息
                for msg in reversed(messages_list):
                    if hasattr(msg, 'content') and getattr(msg, '__class__', None).__name__ in ['AIMessage']:
                        content = getattr(msg, 'content', '')
                        if content and '审查通过' not in content and '任务分析完成' not in content:
                            # 这是一个有效的AI回复
                            ai_msg = create_message(
                                StreamMessageType.INFO,
                                session_id=self.session_id,
                                source="ai_assistant",
                                content=f"AI回复: {str(content)[:100]}{'...' if len(str(content)) > 100 else ''}"
                            )
                            messages.append(ai_msg)
                            logger.debug(f"[DEBUG] 从values中提取AI回复")
                            break
            except Exception as e:
                logger.debug(f"[DEBUG] 提取values中AI消息失败: {e}")
        
        # 提取任务状态信息（如果有）
        current_task = values_data.get('current_task')
        if current_task:
            task_msg = create_message(
                StreamMessageType.INFO,
                session_id=self.session_id,
                source="task_manager",
                content=f"当前任务: {str(current_task)[:100]}"
            )
            messages.append(task_msg)
            logger.debug(f"[DEBUG] 从values中提取任务信息")
        
        logger.debug(f"[DEBUG] values选择性处理结果: 生成了 {len(messages)} 个消息")
        return messages

    def _handle_unknown_chunk(self, chunk: Any) -> List[BaseStreamMessage]:
        """处理未识别的数据块"""
        messages = []
        
        # 尝试通用处理
        try:
            if isinstance(chunk, dict):
                # 字典格式，尝试提取有用信息
                for key, value in chunk.items():
                    if key.startswith('__') and key.endswith('__'):
                        continue  # 跳过系统属性
                    
                    info_msg = create_message(
                        StreamMessageType.INFO,
                        session_id=self.session_id,
                        source="unknown",
                        content=f"{key}: {str(value)[:200]}"
                    )
                    messages.append(info_msg)
            
            elif isinstance(chunk, (str, int, float)):
                # 简单类型
                if str(chunk).strip():
                    info_msg = create_message(
                        StreamMessageType.INFO,
                        session_id=self.session_id,
                        source="unknown",
                        content=str(chunk)[:200]
                    )
                    messages.append(info_msg)
            
            else:
                # 其他类型，记录但不处理
                logger.debug(f"[DEBUG] 跳过未识别chunk类型: {type(chunk)}")
                
        except Exception as e:
            logger.error(f"通用处理chunk失败: {e}")
        
        return messages

    def _handle_node_start(self, event_data: Dict[str, Any]) -> BaseStreamMessage:
        """处理节点开始事件"""
        node_name = event_data.get("name", "unknown")
        self.active_nodes[node_name] = time.time()
        
        return create_message(
            StreamMessageType.NODE_START,
            session_id=self.session_id,
            source=node_name,
            node_name=node_name,
            status="started"
        )
    
    def _handle_node_end(self, event_data: Dict[str, Any]) -> BaseStreamMessage:
        """处理节点结束事件"""
        node_name = event_data.get("name", "unknown")
        start_time = self.active_nodes.pop(node_name, time.time())
        duration = time.time() - start_time
        
        return create_message(
            StreamMessageType.NODE_COMPLETE,
            session_id=self.session_id,
            source=node_name,
            node_name=node_name,
            status="completed",
            duration=duration
        )
    
    def _handle_node_error(self, event_data: Dict[str, Any]) -> BaseStreamMessage:
        """处理节点错误事件"""
        node_name = event_data.get("name", "unknown")
        error_msg = event_data.get("error", "Unknown error")
        
        return create_message(
            StreamMessageType.NODE_ERROR,
            session_id=self.session_id,
            source=node_name,
            node_name=node_name,
            status="error",
            details=str(error_msg)
        )
    
    def _handle_llm_start(self, event_data: Dict[str, Any]) -> BaseStreamMessage:
        """处理LLM开始事件"""
        return create_message(
            StreamMessageType.INFO,
            session_id=self.session_id,
            source="llm",
            content="开始生成回答...",
            level="info"
        )
    
    def _handle_llm_token(self, event_data: Dict[str, Any]) -> BaseStreamMessage:
        """处理LLM Token事件"""
        token = event_data.get("token", "")
        
        return create_message(
            StreamMessageType.LLM_TOKEN,
            session_id=self.session_id,
            source="llm",
            content=token,
            is_complete=False
        )
    
    def _handle_llm_end(self, event_data: Dict[str, Any]) -> BaseStreamMessage:
        """处理LLM结束事件"""
        return create_message(
            StreamMessageType.LLM_COMPLETE,
            session_id=self.session_id,
            source="llm",
            content="",
            is_complete=True
        )
    
    def _handle_tool_start(self, event_data: Dict[str, Any]) -> BaseStreamMessage:
        """处理工具开始事件"""
        tool_name = event_data.get("name", "unknown")
        
        return create_message(
            StreamMessageType.TOOL_START,
            session_id=self.session_id,
            source=tool_name,
            tool_name=tool_name,
            action="start"
        )
    
    def _handle_tool_end(self, event_data: Dict[str, Any]) -> BaseStreamMessage:
        """处理工具结束事件"""
        tool_name = event_data.get("name", "unknown")
        output = event_data.get("output", "")
        
        return create_message(
            StreamMessageType.TOOL_COMPLETE,
            session_id=self.session_id,
            source=tool_name,
            tool_name=tool_name,
            action="complete",
            output=output
        )
    
    def _handle_tool_error(self, event_data: Dict[str, Any]) -> BaseStreamMessage:
        """处理工具错误事件"""
        tool_name = event_data.get("name", "unknown")
        error = event_data.get("error", "Unknown error")
        
        return create_message(
            StreamMessageType.TOOL_ERROR,
            session_id=self.session_id,
            source=tool_name,
            tool_name=tool_name,
            action="error",
            error_message=str(error)
        )


# 注意：流式消息推送功能已移至 app/core/stream_writer_helper.py
# 请使用 stream_writer_helper.py 中的推送函数来避免重复功能
# 
# 使用示例：
# from app.core.stream_writer_helper import push_thinking, push_file, push_progress
# 
# push_thinking("agent_name", "思考内容")
# push_file("file_id", "file_name", "file_path", "file_type")
# push_progress("tool_name", 0.5, "进度详情") 