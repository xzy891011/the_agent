"""
主智能体模块 - 实现系统的主要决策和控制流程
"""
from typing import Dict, List, Any, Optional, Callable, Union, Type, Tuple
import logging
import json
import re
from datetime import datetime
from pydantic import BaseModel, Field

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool
from langchain_core.messages import (
    BaseMessage, 
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
    FunctionMessage
)
from langchain_core.utils.function_calling import convert_to_openai_tool

# 从LangGraph导入相关模块，替换LangChain的AgentExecutor
from langgraph.prebuilt import create_react_agent
from langgraph.prebuilt.chat_agent_executor import AgentState
from langgraph.errors import GraphRecursionError
from langgraph.checkpoint.memory import MemorySaver

# 保留LangChain的Tool用于兼容性
from langchain.agents import Tool as LangchainTool

from app.core.state import IsotopeSystemState, StateManager, TaskStatus, TaskInfo
from app.agents.base_agent import BaseAgent
from app.prompts.prompts import get_main_agent_system_prompt
from langgraph.config import get_stream_writer
from app.agents.custom_react_agent import CustomReactAgent

# 配置日志
logger = logging.getLogger(__name__)

class MainAgent(BaseAgent):
    """主智能体类，作为系统的主要决策者
    
    该智能体负责：
    1. 接收和处理用户输入
    2. 决定任务类型和执行流程
    3. 协调其他智能体和工具的调用
    4. 生成用户可理解的最终输出
    """
    
    def __init__(
        self,
        llm: Optional[BaseChatModel] = None,
        tools: Optional[List[BaseTool]] = None,
        system_prompt: Optional[str] = None,
        name: str = "天然气碳同位素智能助手",
        verbose: bool = False,
        callbacks: Optional[List[Any]] = None,
        use_custom_agent: bool = False,
        config: Optional[Dict[str, Any]] = None
    ):
        """初始化主智能体
        
        Args:
            llm: 语言模型，如果为None将使用默认配置创建
            tools: 可用工具列表
            system_prompt: 系统提示词，如果为None将使用默认提示词
            name: 智能体名称
            verbose: 是否输出详细日志
            callbacks: 回调函数列表，用于流式输出等
            use_custom_agent: 是否使用自定义Agent
            config: 配置字典，用于传递其他配置参数
        """
        # 保存配置信息
        self.config = config or {}
        
        # 导入工具系统
        try:
            from app.tools import get_all_tools, get_tools_by_category
            
            # 合并传入的工具和注册中心的工具
            registered_tools = get_all_tools()
            if tools:
                # 避免工具重复
                tool_names = {t.name for t in tools}
                # 只添加未包含的工具
                additional_tools = [t for t in registered_tools if t.name not in tool_names]
                combined_tools = tools + additional_tools
                logger.info(f"合并传入工具和注册工具，共 {len(combined_tools)} 个工具")
            else:
                combined_tools = registered_tools
                logger.info(f"使用注册中心的工具，共 {len(combined_tools)} 个工具")
                
            # 按类别记录工具数量
            try:
                from app.tools.registry import registry
                categories = registry.get_all_categories()
                for category in categories:
                    category_tools = get_tools_by_category(category)
                    logger.info(f"主智能体加载 {category} 类工具 {len(category_tools)} 个")
            except:
                logger.info("无法按类别记录工具")
                
            # 使用合并后的工具列表
            tools = combined_tools
        except ImportError as e:
            logger.warning(f"导入工具系统失败: {e}，将使用传入的工具")
            # 保持传入的工具不变
        
        
        # 调用父类构造函数
        super().__init__(
            llm=llm,
            # tools=tools,
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
                logger.info(f"使用自定义Agent模式初始化主智能体 {self.name}")
        else:
            self.agent = self._create_agent()
            if self.verbose:
                logger.info(f"使用LangGraph ReAct Agent模式初始化主智能体 {self.name}")
    
    def _create_agent(self):
        """创建LangGraph基于ReAct的智能体
        
        Returns:
            初始化的LangGraph智能体
        """
        
        # 使用v2版本创建ReAct Agent
        logger.info("创建ReAct Agent...")
        try:
            agent_executor = create_react_agent(
                model=self.llm,
                tools=self.tools,
                prompt=self.system_prompt,
                version="v2"  # 使用最新版本的ReAct Agent
            )
            logger.info("ReAct Agent创建成功")
            return agent_executor
        except Exception as e:
            logger.error(f"创建ReAct Agent失败: {str(e)}")
            
            # 尝试使用替代配置
            logger.info("尝试使用替代配置创建ReAct Agent...")
            try:
                # 转换工具为OpenAI格式
                openai_tools = [convert_to_openai_tool(tool) for tool in self.tools]
                
                agent_executor = create_react_agent(
                    model=self.llm,  # 直接使用原始LLM
                    tools=openai_tools,  # 使用OpenAI格式的工具
                    prompt=self.system_prompt,
                    version="v2"
                )
                logger.info("使用替代配置创建ReAct Agent成功")
                return agent_executor
            except Exception as e2:
                logger.error(f"使用替代配置创建ReAct Agent也失败: {str(e2)}")
                raise RuntimeError(f"无法创建ReAct Agent: {str(e)} | {str(e2)}")
    
    def _create_custom_agent(self):
        """创建自定义稳定版Agent
        
        Returns:
            初始化的自定义Agent
        """
        logger.info("创建自定义Agent...")
        try:
            # 从配置中获取最大迭代次数
            agent_config = self.config.get("agent", {})
            max_iterations = agent_config.get("max_iterations", 10)
            
            agent = CustomReactAgent(
                llm=self.llm,
                tools=self.tools,
                system_prompt=self.system_prompt,
                name=self.name,
                verbose=self.verbose,
                callbacks=self.callbacks,
                max_iterations=max_iterations,
                agent_role="supervisor",
                config=self.config
            )
            logger.info("自定义Agent创建成功")
            return agent
        except Exception as e:
            logger.error(f"创建自定义Agent失败: {str(e)}")
            raise RuntimeError(f"无法创建自定义Agent: {str(e)}")
    
    def _prepare_messages_for_llm(self, state: IsotopeSystemState) -> List[BaseMessage]:
        """准备用于LLM的消息列表
        
        Args:
            state: 当前系统状态
            
        Returns:
            消息列表
        """
        # 首先使用父类方法获取基础消息列表（包含系统提示和执行历史等）
        messages = super()._prepare_messages_for_llm(state)
        
        # 检查上下文中是否有相关记忆
        if "context" in state and "relevant_memories" in state["context"]:
            memories = state["context"]["relevant_memories"]
            memory_msg = SystemMessage(content=f"以下是与当前对话相关的记忆，可以参考：\n{memories}")
            
            # 插入记忆消息到系统消息之后、对话历史之前
            system_msg_count = sum(1 for msg in messages if isinstance(msg, SystemMessage))
            if system_msg_count > 0:
                messages.insert(system_msg_count, memory_msg)
            else:
                messages.append(memory_msg)
        
        # 添加文件系统信息
        if "files" in state and state["files"]:
            files_info = self._format_files_information(state["files"])
            files_msg = SystemMessage(content=f"当前会话的文件信息：\n{files_info}")
            
            # 插入文件信息到系统消息之后、对话历史之前
            system_msg_count = sum(1 for msg in messages if isinstance(msg, SystemMessage))
            if system_msg_count > 0:
                messages.insert(system_msg_count, files_msg)
            else:
                messages.append(files_msg)
        
        return messages
    
    def _format_files_information(self, files_dict: Dict[str, Any]) -> str:
        """格式化文件信息为字符串
        
        Args:
            files_dict: 文件信息字典
            
        Returns:
            格式化的文件信息字符串
        """
        if not files_dict:
            return "当前没有可用的文件。"
        
        info_lines = ["可用文件列表:"]
        
        for file_id, file_info in files_dict.items():
            file_name = file_info.get("file_name", "未知名称")
            file_type = file_info.get("file_type", "未知类型")
            file_path = file_info.get("file_path", "未知路径")
            file_size = file_info.get("size", 0)
            upload_time = file_info.get("upload_time", "未知时间")
            description = file_info.get("description", "")
            
            # 格式化文件大小
            if file_size < 1024:
                size_str = f"{file_size} 字节"
            elif file_size < 1024 * 1024:
                size_str = f"{file_size / 1024:.2f} KB"
            else:
                size_str = f"{file_size / (1024 * 1024):.2f} MB"
            
            # 更详细的文件信息格式，突出显示文件ID
            file_line = f"- 文件ID: 【{file_id}】\n  名称: {file_name}\n  类型: {file_type}\n  大小: {size_str}\n  上传时间: {upload_time}\n  路径: {file_path}"
            if description:
                file_line += f"\n  描述: {description}"
            info_lines.append(file_line)
        
        # 检测是否有碳同位素相关文件
        has_isotope_files = any(
            file_info.get("file_name", "").lower().find("isotope") >= 0 or 
            file_info.get("description", "").lower().find("同位素") >= 0 or
            (file_info.get("file_type", "") in ["csv", "xlsx", "xls"] and 
             (file_info.get("file_name", "").lower().find("δ13c") >= 0 or 
              file_info.get("description", "").lower().find("δ13c") >= 0))
            for file_id, file_info in files_dict.items()
        )
        
        # 添加文件ID格式说明
        info_lines.append("\n文件ID说明:")
        info_lines.append("- u-开头: 用户上传的文件")
        info_lines.append("- g-开头: 系统生成的文件") 
        info_lines.append("- t-开头: 临时文件")
        
        # 添加使用说明
        info_lines.append("\n您可以通过文件ID引用这些文件，例如：")
        info_lines.append("- 请分析文件ID为【u-12345678】的内容") 
        info_lines.append("- 请处理我刚上传的文件")
        
        # 针对天然气碳同位素数据文件添加专门说明
        if has_isotope_files:
            info_lines.append("\n检测到可能的碳同位素数据文件，您可以使用以下分析功能：")
            info_lines.append("- 请分析该文件中的碳同位素数据")
            info_lines.append("- 请根据同位素数据判断天然气的成因类型")
            info_lines.append("- 请生成Bernard图解分析气源")
            info_lines.append("- 请创建碳同位素-碳数关系图")
            info_lines.append("- 请检查数据中是否存在同位素倒转现象")
            info_lines.append("- 请评估天然气的热成熟度")
        
        info_lines.append("\n可使用以下工具处理文件：")
        info_lines.append("- analyze_carbon_isotope_data：分析碳同位素数据")
        info_lines.append("- classify_gas_source：判别天然气气源类型")
        info_lines.append("- plot_bernard_diagram：创建Bernard图解") 
        info_lines.append("- plot_carbon_number_trend：创建碳同位素-碳数关系图")
        info_lines.append("- plot_whiticar_diagram：创建Whiticar图解")
        
        return "\n".join(info_lines)
    
    def run(self, state: IsotopeSystemState) -> Dict[str, Any]:
        """运行主智能体
        
        Args:
            state: 当前系统状态
            
        Returns:
            更新后的状态
        """
        # 获取流写入器
        writer = get_stream_writer()
        
        # 检查状态中是否有文件
        if "files" in state and state["files"]:
            file_count = len(state["files"])
            if writer:
                writer({"agent_thinking": f"检测到会话中有 {file_count} 个文件"})
                # 显示前3个文件信息
                count = 0
                for file_id, file_info in state["files"].items():
                    if count >= 3:
                        break
                    file_name = file_info.get("file_name", "未知文件")
                    file_type = file_info.get("file_type", "未知类型")
                    writer({"agent_thinking": f"文件: {file_name} (ID: {file_id}), 类型: {file_type}"})
                    count += 1
        
        # 获取最后一条用户消息
        last_user_message = StateManager.get_last_human_message(state)
        
        if last_user_message:
            # 显示思考过程
            writer({"agent_thinking": f"正在思考如何回答关于'{last_user_message.content[:30]}...'的问题"})
            
            # 检查是否有相关记忆
            session_id = state.get("session_id")
            memory_store = state.get("memory_store")
            if session_id and memory_store:
                writer({"agent_thinking": "检索相关历史记忆..."})
                try:
                    relevant_memories = memory_store.search_memories(
                        user_id=session_id,
                        query=last_user_message.content,
                        limit=3
                    )
                    if relevant_memories:
                        writer({"agent_thinking": f"找到{len(relevant_memories)}条相关记忆"})
                        for memory in relevant_memories:
                            preview = memory.content[:50] + "..." if len(memory.content) > 50 else memory.content
                            writer({"agent_thinking": f"记忆: {preview}"})
                    else:
                        writer({"agent_thinking": "未找到相关记忆"})
                except Exception as e:
                    logger.warning(f"检索记忆时出错: {str(e)}")
        
        try:
            # 添加动作记录
            state = StateManager.add_action_record(
                state, 
                {
                    "node": "main_agent",
                    "action": "process_input",
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
                error_msg = "未找到用户消息，无法继续处理。"
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
                task_info = self._create_task_from_message(latest_human_msg.content)
                state = StateManager.update_current_task(state, task_info)
                logger.info(f"创建新任务: {task_info['task_type']}")
            
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
                    "recursion_limit": 10,  # 合理的递归限制
                    "timeout": 60,  # 合理的超时时间
                }
                
                logger.info(f"主智能体开始处理输入: {latest_human_msg.content[:100]}")
                
                # 调用LLM前
                writer({"agent_action": "调用LLM生成回复"})
                
                # 运行LangGraph智能体
                try:
                    # 使用stream方法获取结果
                    final_result = None
                    tool_calls = []
                    
                    # 流式处理LangGraph执行结果
                    for chunk in self.agent.stream(
                        agent_state,
                        config,
                        stream_mode="values"
                    ):
                        # 更新最终状态
                        final_result = chunk
                        
                        # 显式日志记录，帮助调试
                        if self.verbose:
                            logger.info(f"处理中间状态类型: {type(chunk)}")
                            logger.info(f"中间状态键: {chunk.keys() if hasattr(chunk, 'keys') else 'No keys'}")
                            if "intermediate_steps" in chunk:
                                logger.info(f"中间步骤数量: {len(chunk['intermediate_steps'])}")
                        
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
                                
                                # 解析工具调用和结果
                                action, result = action_result
                                
                                # 增加调试信息
                                logger.info(f"捕获到工具调用: {action}")
                                logger.info(f"工具调用结果: {result}")
                                logger.info(f"工具调用类型: {type(action)}")
                                
                                if hasattr(action, '__dict__'):
                                    logger.info(f"工具调用属性: {action.__dict__}")
                                
                                # 获取工具名称和输入（处理不同格式的工具调用）
                                tool_name = None
                                tool_input = None
                                
                                # 提取工具名称和输入
                                if hasattr(action, 'tool'):
                                    tool_name = action.tool
                                    tool_input = action.tool_input
                                    logger.info(f"从tool属性获取: {tool_name}")
                                elif hasattr(action, 'name'):
                                    tool_name = action.name
                                    tool_input = action.arguments
                                    logger.info(f"从name属性获取: {tool_name}")
                                else:
                                    # 尝试从字典获取
                                    if isinstance(action, dict):
                                        tool_name = action.get('name', action.get('tool', 'unknown_tool'))
                                        tool_input = action.get('arguments', action.get('tool_input', {}))
                                        logger.info(f"从字典获取: {tool_name}")
                                
                                # 如果提取到工具信息
                                if tool_name:
                                    # 处理工具输入
                                    if isinstance(tool_input, str):
                                        try:
                                            tool_input = json.loads(tool_input)
                                            logger.info("成功将工具输入解析为JSON")
                                        except:
                                            logger.info("工具输入不是JSON格式，保持原样")
                                    
                                    # 查找工具实例 - 优先使用工具注册中心
                                    try:
                                        from app.tools import get_tool
                                        tool = get_tool(tool_name)
                                        logger.info(f"从工具注册中心获取到工具: {tool_name}")
                                    except (ImportError, AttributeError):
                                        logger.info(f"工具注册中心不可用，无法获取工具: {tool_name}")
                                        tool = None
                                        
                                    # 如果注册中心无法获取工具，记录这个错误
                                    if not tool:
                                        logger.warning(f"找不到工具: {tool_name}，但仍记录结果")
                                    
                                    # 创建工具执行记录
                                    tool_call = {
                                        "tool_name": tool_name,
                                        "input": tool_input,
                                        "output": str(result),
                                        "status": "success",
                                        "timestamp": datetime.now().isoformat()
                                    }
                                    tool_calls.append((action, result))
                                    
                                    # 记录日志
                                    logger.info(f"执行工具: {tool_name} 结果: {str(result)[:100]}")
                                else:
                                    logger.warning(f"无法识别工具名称: {action}")
                    
                    # 处理最终结果
                    if final_result and "messages" in final_result and final_result["messages"]:
                        # 获取最后一条消息作为响应
                        last_message = final_result["messages"][-1]
                        
                        # 创建AI消息
                        if isinstance(last_message, AIMessage):
                            ai_message = last_message
                        else:
                            # 如果不是AIMessage，则创建一个
                            ai_message = AIMessage(content=str(last_message))
                        
                        # 检查消息中是否有工具调用信息
                        tool_calls_in_message = False
                        if hasattr(ai_message, 'tool_calls') and ai_message.tool_calls:
                            logger.info(f"消息中包含工具调用: {ai_message.tool_calls}")
                            tool_calls_in_message = True
                        
                        # 更新任务状态
                        if tool_calls:
                            try:
                                # 添加工具调用记录到任务
                                state = self._update_task_with_tool_executions(state, tool_calls)
                                logger.info(f"记录了{len(tool_calls)}个工具调用")
                            except Exception as tool_err:
                                logger.error(f"更新工具执行记录时出错: {tool_err}")
                                # 防御性处理：确保不会中断流程
                        elif tool_calls_in_message:
                            # 如果消息中有工具调用但中间步骤没有捕获到，也记录下来
                            logger.info("从消息中提取工具调用")
                            # 创建工具执行记录
                            current_task = state.get("current_task", {})
                            if "tool_executions" not in current_task:
                                current_task["tool_executions"] = []
                            
                            for call in ai_message.tool_calls:
                                tool_execution = {
                                    "tool_name": call.get('name', 'unknown_tool'),
                                    "input": call.get('arguments', {}),
                                    "output": "从消息中提取的工具调用，无结果",
                                    "status": "unknown",
                                    "timestamp": datetime.now().isoformat()
                                }
                                current_task["tool_executions"].append(tool_execution)
                            
                            state = StateManager.update_current_task(state, current_task)
                        else:
                            logger.info("没有捕获到工具调用，这是一个直接回复")
                            # 将任务状态标记为已完成
                            current_task = state.get("current_task", {})
                            if current_task:
                                current_task["status"] = TaskStatus.COMPLETED
                                current_task["updated_at"] = datetime.now().isoformat()
                                state = StateManager.update_current_task(state, current_task)
                                logger.info(f"任务已完成: {current_task.get('task_type', 'unknown')}")
                        
                        # 更新消息历史
                        return StateManager.update_messages(state, ai_message)
                    else:
                        # 如果没有得到有效响应，返回默认消息
                        default_response = AIMessage(content="我处理了您的请求，但无法生成有效的响应。请尝试重新表述您的问题。")
                        return StateManager.update_messages(state, default_response)
                    
                except GraphRecursionError as e:
                    # 处理递归限制错误
                    logger.error(f"智能体执行超出递归限制: {str(e)}")
                    error_response = AIMessage(content=f"处理您的请求时达到了最大迭代次数。这可能表明您的请求过于复杂或需要进一步澄清。请尝试简化您的问题或提供更多信息。")
                    return StateManager.update_messages(state, error_response)
                
                except ValueError as e:
                    # 处理值错误
                    logger.error(f"智能体调用出错: {str(e)}")
                    error_response = AIMessage(content=f"在处理您的请求时遇到了技术问题: {str(e)}")
                    return StateManager.update_messages(state, error_response)
                
                except TypeError as e:
                    # 专门处理类型错误，例如 'float' is not iterable
                    logger.error(f"智能体调用类型错误: {str(e)}")
                    if "not iterable" in str(e):
                        logger.error("检测到迭代类型错误，可能是state中包含非可迭代对象")
                    error_response = AIMessage(content=f"在处理您的请求时遇到了类型错误。请稍后再试。[等待用户]")
                    return StateManager.update_messages(state, error_response)
                
        except Exception as e:
            # 处理异常
            logger.error(f"主智能体执行出错: {str(e)}")
            return self.handle_error(e, state)
    
    def _create_task_from_message(self, message_content: str) -> Dict[str, Any]:
        """从消息内容创建任务信息
        
        Args:
            message_content: 消息内容
            
        Returns:
            任务信息字典
        """
        # 简单任务类型识别（这里可以使用更复杂的逻辑）
        task_type = "general_query"  # 默认为一般查询
        
        if re.search(r'同位素|碳同位素|isotope|δ13C', message_content, re.IGNORECASE):
            task_type = "isotope_analysis"  # 同位素分析任务
        elif re.search(r'数据|分析|处理|计算|data|analyze', message_content, re.IGNORECASE):
            task_type = "data_processing"  # 数据处理任务
        elif re.search(r'计划|规划|怎么做|步骤|plan|steps', message_content, re.IGNORECASE):
            task_type = "planning"  # 规划任务
        
        # 创建任务信息 - TaskInfo是TypedDict而不是Pydantic模型，无需调用.dict()
        return {
            "task_id": f"task_{hash(message_content) % 10000}",
            "task_type": task_type,
            "description": f"处理用户查询: {message_content[:100]}{'...' if len(message_content) > 100 else ''}",
            "status": TaskStatus.IN_PROGRESS,
            "steps": [],
            "current_step": 0,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
    
    def _update_task_with_tool_executions(
        self, 
        state: IsotopeSystemState, 
        agent_actions: List[Tuple[Any, Any]]
    ) -> IsotopeSystemState:
        """使用工具执行结果更新任务状态
        
        Args:
            state: 当前系统状态
            agent_actions: 智能体执行的动作列表
            
        Returns:
            更新后的状态
        """
        current_task = state.get("current_task", {})
        if not current_task:
            return state
        
        # 初始化工具执行列表（如果不存在）
        if "tool_executions" not in current_task:
            current_task["tool_executions"] = []
        
        # 获取已执行工具列表
        tool_executions = current_task["tool_executions"]
        
        # 增加调试日志
        logger.info(f"记录{len(agent_actions)}个工具执行")
        
        # 类型检查：确保agent_actions是可迭代的
        if not hasattr(agent_actions, '__iter__'):
            logger.error(f"agent_actions不是可迭代对象，而是 {type(agent_actions)}")
            # 如果是单个元组，尝试转换为列表
            if isinstance(agent_actions, tuple) and len(agent_actions) == 2:
                agent_actions = [agent_actions]
            # 如果是其他类型，直接返回原状态
            else:
                logger.error("无法处理的agent_actions类型，跳过工具执行记录")
                return state
        
        # 添加新的工具执行
        for action, result in agent_actions:
            try:
                # 尝试获取工具名称和输入
                tool_name = None
                tool_input = None
                
                # 提取工具名称和输入（兼容多种格式）
                if hasattr(action, 'tool'):
                    tool_name = action.tool
                    tool_input = action.tool_input
                elif hasattr(action, 'name'):
                    tool_name = action.name
                    tool_input = action.arguments
                elif isinstance(action, dict):
                    tool_name = action.get('name', action.get('tool', action.get('tool_name')))
                    tool_input = action.get('arguments', action.get('tool_input', action.get('input')))
                
                if not tool_name:
                    logger.warning(f"无法识别工具名称，跳过记录: {action}")
                    continue
                
                # 规范化工具输入
                if isinstance(tool_input, str):
                    try:
                        tool_input = json.loads(tool_input)
                    except:
                        pass  # 如果不是JSON格式，保持原样
                
                # 创建工具执行记录
                execution = {
                    "tool_name": tool_name,
                    "input": tool_input,
                    "output": str(result),
                    "status": "success",
                    "timestamp": datetime.now().isoformat()
                }
                
                # 添加到执行列表
                tool_executions.append(execution)
                
                # 记录日志
                logger.info(f"记录工具执行: {tool_name}")
                if self.verbose:
                    logger.info(f"工具输入: {tool_input}")
                    logger.info(f"工具输出: {str(result)[:100]}")
                
            except Exception as e:
                logger.error(f"处理工具执行记录时出错: {str(e)}")
        
        # 更新任务
        current_task["tool_executions"] = tool_executions
        return StateManager.update_current_task(state, current_task)
    
    def handoff_to_expert(self, state: IsotopeSystemState) -> Dict[str, Any]:
        """将任务移交给专家智能体
        
        Args:
            state: 当前系统状态
            
        Returns:
            更新后的状态，指示下一步应由专家智能体处理
        """
        # 记录移交决定
        handoff_msg = AIMessage(content="我需要将这个问题交给碳同位素专家智能体来处理，它有更专业的知识来解析这些数据。")
        
        # 更新任务类型
        current_task = state.get("current_task", {})
        if current_task:
            current_task["task_type"] = "isotope_analysis"
            current_task["handoff_to"] = "expert_agent"
            state = StateManager.update_current_task(state, current_task)
        
        # 记录移交消息
        return StateManager.update_messages(state, handoff_msg)
    
    def request_human_input(self, state: IsotopeSystemState, reason: str) -> Dict[str, Any]:
        """请求人类用户输入
        
        Args:
            state: 当前系统状态
            reason: 请求人类输入的原因
            
        Returns:
            更新后的状态，指示等待用户输入
        """
        # 更新任务状态
        current_task = state.get("current_task", {})
        if current_task:
            current_task["status"] = TaskStatus.WAITING_USER
            current_task["waiting_reason"] = reason
            state = StateManager.update_current_task(state, current_task)
        
        # 添加请求用户输入的消息
        request_msg = AIMessage(content=f"请提供更多信息: {reason}")
        return StateManager.update_messages(state, request_msg)
    
    def add_tool(self, tool: BaseTool, category: Optional[str] = None) -> None:
        """添加工具到智能体
        
        Args:
            tool: 要添加的工具
            category: 工具分类，可选
        """
        # 检查工具是否已存在
        for existing_tool in self.tools:
            if existing_tool.name == tool.name:
                logger.warning(f"工具 {tool.name} 已存在，跳过添加")
                return
        
        # 添加到工具列表
        self.tools.append(tool)
        
        # 尝试将工具添加到全局注册中心
        try:
            from app.tools.registry import registry
            registry.register_tool(tool, category)
            logger.info(f"工具 {tool.name} 已添加到全局注册中心")
        except ImportError:
            logger.warning("全局工具注册中心不可用，仅添加到智能体")
        
        # 重新创建Agent以包含新工具
        self.agent = self._create_agent()
        
        logger.info(f"工具 {tool.name} 已添加到智能体")
    
    def add_tools(self, tools: List[BaseTool], category: Optional[str] = None) -> None:
        """批量添加工具到智能体
        
        Args:
            tools: 要添加的工具列表
            category: 工具分类，可选
        """
        # 添加所有工具
        added = False
        for tool in tools:
            # 检查工具是否已存在
            if any(existing_tool.name == tool.name for existing_tool in self.tools):
                continue
                
            self.tools.append(tool)
            
            # 尝试将工具添加到全局注册中心
            try:
                from app.tools.registry import registry
                registry.register_tool(tool, category)
            except ImportError:
                pass
                
            added = True
        
        # 只有在实际添加了工具后才重新创建Agent
        if added:
            self.agent = self._create_agent()
            logger.info(f"已批量添加工具到智能体") 