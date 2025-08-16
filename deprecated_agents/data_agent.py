"""
数据处理智能体模块 - 专注于数据处理和特征提取
"""
from typing import Dict, List, Any, Optional, Callable, Union, Type, Tuple
import logging
import json
from datetime import datetime

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool
from langchain_core.messages import (
    BaseMessage, 
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage
)

# 从LangGraph导入相关模块
from langgraph.prebuilt import create_react_agent
# 移除对langgraph_codeact的导入，因为该模块不可用
# from langgraph_codeact import create_codeact
from langgraph.prebuilt.chat_agent_executor import AgentState
from langgraph.config import get_stream_writer

from app.core.state import IsotopeSystemState, StateManager, TaskStatus
from app.agents.base_agent import BaseAgent
from app.prompts.prompts import get_data_agent_system_prompt
from app.agents.custom_react_agent import CustomReactAgent

# 配置日志
logger = logging.getLogger(__name__)

class DataAgent(BaseAgent):
    """数据处理智能体类
    
    该智能体负责：
    1. 处理和清洗数据文件
    2. 提取数据特征
    3. 对数据进行初步分析和可视化
    4. 为专家智能体提供结构化数据
    """
    
    def __init__(
        self,
        llm: Optional[BaseChatModel] = None,
        tools: Optional[List[BaseTool]] = None,
        system_prompt: Optional[str] = None,
        name: Optional[str] = None,
        verbose: Optional[bool] = None,
        callbacks: Optional[List[Any]] = None,
        use_custom_agent: Optional[bool] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """初始化数据处理智能体
        
        Args:
            llm: 语言模型，如果为None将使用默认配置创建
            tools: 可用工具列表
            system_prompt: 系统提示词，如果为None将使用默认提示词
            name: 智能体名称，如果为None将从配置获取
            verbose: 是否输出详细日志，如果为None将从配置获取
            callbacks: 回调函数列表，用于流式输出等
            use_custom_agent: 是否使用自定义Agent，如果为None将从配置获取
            config: 配置字典，如果提供则从中读取配置
        """
        # 处理配置
        from app.core.config import ConfigManager
        config_manager = ConfigManager()
        if config is None:
            # 如果未提供配置，尝试加载默认配置
            try:
                config_manager.load_config()
                agent_config = config_manager.get_agent_config()
                data_agent_config = config_manager.get_data_agent_config()
            except Exception as e:
                logger.warning(f"加载配置失败，使用默认值: {str(e)}")
                agent_config = {}
                data_agent_config = {}
        else:
            agent_config = config.get("agent", {})
            data_agent_config = config.get("agent", {}).get("data_agent", {})
        
        # 从配置获取参数（如果未明确指定）
        if name is None:
            name = data_agent_config.get("name", "数据处理智能体")
            
        if verbose is None:
            verbose = data_agent_config.get("verbose", False)
            
        if use_custom_agent is None:
            use_custom_agent = agent_config.get("use_custom_agent", True)
            
        # 检查是否有系统提示词覆盖
        if system_prompt is None and data_agent_config.get("system_prompt_override"):
            system_prompt = data_agent_config.get("system_prompt_override")

        # 合并传入的工具和自动加载的工具
        if tools:
            logger.info(f"数据处理智能体：合并工具，共 {len(tools)} 个工具")
        
        # 调用父类构造函数
        super().__init__(
            llm=llm,
            tools=tools,
            system_prompt=system_prompt,
            name=name,
            verbose=verbose
        )
        
        # 设置回调
        self.callbacks = callbacks
        
        # 设置是否使用自定义Agent
        self.use_custom_agent = use_custom_agent
        
        # 创建智能体
        if self.use_custom_agent:
            self.agent = self._create_custom_agent()
            if self.verbose:
                logger.info(f"使用自定义Agent模式初始化数据处理智能体 {self.name}")
        else:
            self.agent = self._create_agent()
            if self.verbose:
                logger.info(f"使用LangGraph ReAct Agent模式初始化数据处理智能体 {self.name}")
    
    def _create_agent(self):
        """创建LangGraph基于ReAct的智能体
        
        Returns:
            初始化的LangGraph智能体
        """
        
        #创建ReAct智能体
        agent = create_react_agent(
            model=self.llm,
            tools=self.tools,
            prompt=self.system_prompt,
            version="v2",
            debug=True
        )
        
        return agent
    
    def _create_custom_agent(self):
        """创建自定义稳定版Agent
        
        Returns:
            初始化的自定义Agent
        """
        logger.info("创建自定义数据处理Agent...")
        try:
            # 获取配置
            from app.core.config import ConfigManager
            config_manager = ConfigManager()
            try:
                config_manager.load_config()
                agent_config = config_manager.get_agent_config()
            except Exception as e:
                logger.warning(f"加载配置失败，使用默认值: {str(e)}")
                agent_config = {}
                
            # 获取最大迭代次数
            max_iterations = agent_config.get("max_iterations", 10)
            
            agent = CustomReactAgent(
                llm=self.llm,
                tools=self.tools,
                system_prompt=self.system_prompt,
                name=self.name,
                verbose=self.verbose,
                callbacks=self.callbacks,
                max_iterations=max_iterations,
                agent_role="data_agent",
                config=agent_config
            )
            logger.info("自定义数据处理Agent创建成功")
            return agent
        except Exception as e:
            logger.error(f"创建自定义数据处理Agent失败: {str(e)}")
            raise RuntimeError(f"无法创建自定义数据处理Agent: {str(e)}")
    
    def run(self, state: IsotopeSystemState) -> Dict[str, Any]:
        """执行数据处理智能体
        
        Args:
            state: 当前系统状态
            
        Returns:
            更新后的系统状态
        """
        # 获取流写入器
        writer = get_stream_writer()
        if writer:
            writer({"agent_thinking": "数据处理智能体开始分析..."})
        
        # 检查状态中是否有文件
        if "files" in state and state["files"]:
            file_count = len(state["files"])
            if writer:
                writer({"agent_thinking": f"数据处理智能体检测到会话中有 {file_count} 个文件"})
                # 显示前3个文件信息
                count = 0
                for file_id, file_info in state["files"].items():
                    if count >= 3:
                        break
                    file_name = file_info.get("file_name", "未知文件")
                    file_type = file_info.get("file_type", "未知类型")
                    file_size = file_info.get("file_size", "未知大小")
                    writer({"agent_thinking": f"文件: {file_name} (ID: {file_id}), 类型: {file_type}, 大小: {file_size}"})
                    count += 1
                if file_count > 3:
                    writer({"agent_thinking": f"...以及{file_count - 3}个其他文件"})
        else:
            if writer:
                writer({"agent_thinking": "未检测到上传的文件"})
        
        # 获取最后一条用户消息
        last_user_message = StateManager.get_last_human_message(state)
        
        if last_user_message:
            # 显示思考过程
            writer({"agent_thinking": f"数据处理智能体正在思考如何处理关于'{last_user_message.content[:30]}...'的问题"})
            writer({"agent_thinking": "正在分析数据处理需求..."})
            
            # 检查是否有相关记忆
            session_id = state.get("session_id")
            memory_store = state.get("memory_store")
            if session_id and memory_store:
                writer({"agent_thinking": "检索相关历史记忆..."})
                try:
                    relevant_memories = memory_store.search_memories(
                        user_id=session_id,
                        query=last_user_message.content,
                        limit=5  # 增加记忆检索数量
                    )
                    if relevant_memories:
                        writer({"agent_thinking": f"找到{len(relevant_memories)}条相关记忆"})
                        for i, memory in enumerate(relevant_memories):
                            preview = memory.content[:50] + "..." if len(memory.content) > 50 else memory.content
                            writer({"agent_thinking": f"记忆{i+1}: {preview}"})
                    else:
                        writer({"agent_thinking": "未找到相关记忆"})
                except Exception as e:
                    logger.warning(f"检索记忆时出错: {str(e)}")
                
            writer({"agent_thinking": "数据处理智能体正在组织处理方案..."})
        
        try:
            # 添加动作记录
            state = StateManager.add_action_record(
                state, 
                {
                    "node": "data_agent",
                    "action": "process_data",
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            # 准备消息历史 - 添加防御性检查
            try:
                messages = self._prepare_messages_for_llm(state)
                self.log_messages(messages)
            except Exception as msg_err:
                logger.error(f"准备消息历史时出错: {msg_err}")
                messages = []
                # 确保至少有系统消息和一条人类消息
                if hasattr(self, "system_prompt") and self.system_prompt:
                    messages.append(SystemMessage(content=self.system_prompt))
                
                # 从state中提取最后的人类消息
                if "messages" in state and isinstance(state["messages"], list):
                    for msg in reversed(state["messages"]):
                        if isinstance(msg, HumanMessage):
                            messages.append(msg)
                            break
            
            # 获取最后一条人类消息作为输入
            human_messages = [msg for msg in messages if isinstance(msg, HumanMessage)]
            if not human_messages:
                # 如果没有人类消息，返回错误提示
                error_msg = "未找到用户消息，无法继续数据处理。"
                logger.error(error_msg)
                return StateManager.update_messages(
                    state, 
                    AIMessage(content=error_msg)
                )
            
            # 获取最后一条人类消息
            latest_human_msg = human_messages[-1]
            
            # 处理当前任务状态
            current_task = state.get("current_task")
            if not current_task:
                # 如果当前没有任务，创建新任务
                task_info = {
                    "task_id": f"data_task_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    "task_type": "data_processing",
                    "description": f"数据处理: {latest_human_msg.content[:50]}...",
                    "status": TaskStatus.IN_PROGRESS.value,
                    "created_at": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat(),
                    "metadata": {
                        "agent": "data_agent",
                        "input_message": latest_human_msg.content
                    }
                }
                state = StateManager.update_current_task(state, task_info)
                logger.info(f"创建新数据处理任务: {task_info['task_id']}")
                if writer:
                    writer({"agent_thinking": f"创建数据处理任务: {task_info['description']}"})
            else:
                # 更新现有任务
                current_task["last_updated"] = datetime.now().isoformat()
                state = StateManager.update_current_task(state, current_task)
                if writer:
                    writer({"agent_thinking": f"继续处理现有任务: {current_task.get('description', '未知任务')}"})
            
            # 根据模式选择运行方式
            if self.use_custom_agent and hasattr(self, 'agent') and isinstance(self.agent, CustomReactAgent):
                # 使用自定义Agent的run方法
                return self.agent.run(state)
            else:
                # 使用原始的LangGraph ReAct Agent逻辑
                # 准备LangGraph Agent的输入状态
                # 构建不包含系统消息的消息历史
                chat_history = []
                for msg in messages:
                    if not isinstance(msg, SystemMessage):
                        chat_history.append(msg)
                
                # 创建LangGraph Agent状态
                agent_state = {
                    "messages": chat_history,
                }
                
                # 设置递归限制和超时设置
                config = {
                    "recursion_limit": 8,  # 合理的递归限制
                    "timeout": 60,  # 合理的超时时间
                }
                
                logger.info(f"数据处理智能体开始处理输入: {latest_human_msg.content[:100]}")
                
                # 调用LLM前
                writer({"agent_action": "数据处理智能体调用LLM进行分析"})
                
                # 运行LangGraph智能体
                try:
                    # 流式处理LangGraph执行结果
                    final_result = None
                    tool_calls = []
                    
                    for chunk in self.agent.stream(
                        agent_state,
                        config,
                        stream_mode="values"
                    ):
                        try:
                            # 更新最终结果
                            final_result = chunk
                            
                            # 显式日志记录，帮助调试
                            if self.verbose:
                                logger.info(f"处理中间状态类型: {type(chunk)}")
                                
                            # 流式推送思考过程
                            if writer and "messages" in chunk:
                                last_message = chunk["messages"][-1] if chunk["messages"] else None
                                if isinstance(last_message, AIMessage):
                                    writer({"agent_thinking": last_message.content})
                                    
                            # 检查是否有工具执行
                            if "intermediate_steps" in chunk:
                                # 防御性检查：确保intermediate_steps是可迭代的
                                intermediate_steps = chunk["intermediate_steps"]
                                if not hasattr(intermediate_steps, '__iter__'):
                                    logger.error(f"intermediate_steps不是可迭代对象而是{type(intermediate_steps)}")
                                    continue
                                    
                                for action_result in intermediate_steps:
                                    # 防御性检查：确保action_result是元组或列表
                                    if not isinstance(action_result, (tuple, list)):
                                        logger.error(f"action_result不是元组/列表而是{type(action_result)}")
                                        continue
                                        
                                    # 防御性检查：确保action_result有两个元素
                                    if len(action_result) != 2:
                                        logger.error(f"action_result长度不为2: {len(action_result)}")
                                        continue
                                    
                                    # 记录工具调用，用于更新任务状态
                                    tool_calls.append(action_result)
                                    
                                    # 解析工具调用和结果
                                    action, result = action_result
                                    
                                    # 增加调试信息
                                    logger.info(f"数据处理智能体捕获到工具调用: {action}")
                                    logger.info(f"工具调用结果: {result}")
                                    
                        except Exception as chunk_err:
                            logger.error(f"处理流chunk时出错: {chunk_err}")
                            continue
                    
                    # 安全处理最终结果
                    try:
                        # 处理最终结果
                        if final_result and "messages" in final_result:
                            # 获取最后一条消息
                            agent_messages = final_result["messages"]
                            if agent_messages:
                                last_message = agent_messages[-1]
                                
                                # 为消息添加来源标记
                                if isinstance(last_message, AIMessage):
                                    metadata = getattr(last_message, "additional_kwargs", {})
                                    metadata["source"] = "data_agent"  # 添加来源标记
                                    
                                    try:
                                        last_message.additional_kwargs = metadata
                                    except:
                                        # 如果无法直接修改，创建新消息
                                        new_message = AIMessage(
                                            content=last_message.content,
                                            additional_kwargs=metadata
                                        )
                                        last_message = new_message
                                
                                # 更新状态中的消息
                                state = StateManager.update_messages(state, last_message)
                        
                        # 更新任务执行状态 - 记录工具执行情况
                        if tool_calls and "current_task" in state:
                            state = self._update_task_with_tool_executions(state, tool_calls)
                        
                        # 检查是否需要转到专家智能体或继续执行
                        last_ai_message = StateManager.get_last_ai_message(state)
                        if last_ai_message and isinstance(last_ai_message, AIMessage):
                            content = last_ai_message.content
                            # 检查是否有明确的路由标记
                            route_to = None
                            if "[返回Supervisor]" in content:
                                route_to = "supervisor"
                            elif "[需要专家分析]" in content:
                                route_to = "expert_agent"
                            elif "[等待用户]" in content:
                                route_to = "human_interaction"
                            
                            # 将路由决策添加到消息元数据
                            if route_to:
                                try:
                                    metadata = getattr(last_ai_message, "additional_kwargs", {})
                                    metadata["route_to"] = route_to
                                    # 尝试更新消息的元数据
                                    try:
                                        last_ai_message.additional_kwargs = metadata
                                    except:
                                        # 如果无法直接修改，创建新消息
                                        new_message = AIMessage(
                                            content=last_ai_message.content,
                                            additional_kwargs=metadata
                                        )
                                        # 替换最后一条消息
                                        messages = state.get("messages", [])
                                        if messages and messages[-1] == last_ai_message:
                                            messages[-1] = new_message
                                            state["messages"] = messages
                                except Exception as meta_err:
                                    logger.error(f"处理消息元数据时出错: {meta_err}")
                    except Exception as result_err:
                        logger.error(f"处理最终结果时出错: {result_err}")
                        if 'float' in str(result_err) and 'iterable' in str(result_err):
                            logger.error("检测到浮点数不可迭代错误，这通常是由于penalties参数传递有误导致的")
                        
                        # 创建消息指出处理错误
                        error_message = AIMessage(content=f"在处理结果时遇到错误: {str(result_err)}。工具可能已成功执行，但在解析或展示结果时出现问题。请考虑查看日志获取更多信息。[返回Supervisor]")
                        state = StateManager.update_messages(state, error_message)
                    
                    if writer:
                        writer({"agent_thinking": "数据处理智能体完成分析"})
                    
                    return state
                
                except Exception as agent_err:
                    logger.error(f"数据处理智能体执行过程中出错: {agent_err}")
                    if writer:
                        writer({"agent_thinking": f"执行过程中出错: {agent_err}"})
                    
                    # 创建错误消息
                    error_message = AIMessage(content=f"数据处理过程中遇到错误: {str(agent_err)} [返回Supervisor]")
                    return StateManager.update_messages(state, error_message)
                
        except Exception as e:
            logger.error(f"数据处理智能体运行错误: {str(e)}")
            if writer:
                writer({"agent_thinking": f"数据处理智能体错误: {str(e)}"})
            
            # 返回带错误消息的状态
            error_message = AIMessage(content=f"数据处理智能体错误: {str(e)} [返回Supervisor]")
            return StateManager.update_messages(state, error_message)
    
    def _update_task_with_tool_executions(self, state: IsotopeSystemState, agent_actions: List[Tuple[Any, Any]]) -> IsotopeSystemState:
        """使用工具执行结果更新任务状态
        
        Args:
            state: 当前系统状态
            agent_actions: 工具执行动作和结果的列表
            
        Returns:
            更新后的状态
        """
        current_task = state.get("current_task", {})
        if not current_task:
            return state
        
        # 初始化工具执行列表（如果不存在）
        if "tool_executions" not in current_task:
            current_task["tool_executions"] = []
        
        # 遍历所有工具调用
        for action, result in agent_actions:
            # 防御性检查
            if not hasattr(action, 'tool') or not hasattr(action, 'tool_input'):
                logger.warning(f"工具调用格式不正确: {action}")
                continue
                
            # 获取工具名称和输入
            try:
                tool_name = getattr(action, 'tool')
                tool_input = getattr(action, 'tool_input')
                
                # 尝试解析工具输入为字典
                if isinstance(tool_input, str):
                    try:
                        # 尝试将字符串解析为JSON
                        import json
                        tool_args = json.loads(tool_input)
                    except:
                        # 如果解析失败，创建一个包含原始输入的字典
                        tool_args = {"input": tool_input}
                else:
                    # 如果已经是字典，直接使用
                    tool_args = tool_input if isinstance(tool_input, dict) else {"input": tool_input}
                
                # 创建工具执行记录
                execution = {
                    "tool_name": tool_name,
                    "input": tool_args,
                    "output": str(result),
                    "status": "success",
                    "timestamp": datetime.now().isoformat()
                }
                
                # 添加到执行列表
                current_task["tool_executions"].append(execution)
                
            except Exception as e:
                logger.error(f"处理工具执行记录时出错: {str(e)}")
                # 尝试创建最基本的记录
                execution = {
                    "tool_name": str(action),
                    "input": "解析失败",
                    "output": str(result),
                    "status": "error",
                    "timestamp": datetime.now().isoformat(),
                    "error": str(e)
                }
                current_task["tool_executions"].append(execution)
        
        # 更新任务状态为进行中
        current_task["status"] = TaskStatus.IN_PROGRESS.value
        current_task["last_updated"] = datetime.now().isoformat()
        
        # 更新任务
        return StateManager.update_current_task(state, current_task) 