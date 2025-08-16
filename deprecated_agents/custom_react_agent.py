"""
自定义稳定版Agent模块 - 使用JSON解析替代LangGraph的create_react_agent
"""
from typing import Dict, List, Any, Optional, Callable, Union, Type, Tuple, Generator
import logging
import json
import re
from datetime import datetime
import time  # 添加 time 导入用于生成时间戳
import uuid

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_core.messages import (
    BaseMessage, 
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage
)
from langchain_core.output_parsers import JsonOutputParser
from langchain.output_parsers import OutputFixingParser
from langchain.schema.output_parser import StrOutputParser
from langgraph.config import get_stream_writer

from app.core.state import IsotopeSystemState, StateManager, TaskStatus
from app.agents.base_agent import BaseAgent
from app.agents.custom_react_agent_models import AgentAction
from app.prompts.custom_prompts import get_custom_agent_system_prompt

# 配置日志
logger = logging.getLogger(__name__)

def extract_json_from_llm_output(text: str) -> Optional[str]:
    """从LLM输出中提取JSON部分
    
    Args:
        text: LLM输出的文本
        
    Returns:
        提取的JSON字符串，如果没有则返回None
    """
    # 匹配JSON代码块
    json_pattern = re.compile(r'```json\s*(.*?)\s*```', re.DOTALL)
    matches = json_pattern.findall(text)
    
    # 如果找到JSON代码块，返回最后一个
    if matches:
        return matches[-1].strip()
    
    # 没有找到代码块，尝试寻找直接的JSON对象
    json_obj_pattern = re.compile(r'(\{.*\})', re.DOTALL)
    matches = json_obj_pattern.findall(text)
    if matches:
        # 可能有多个JSON对象，选择最后一个最完整的
        for match in reversed(matches):
            try:
                json.loads(match)
                return match
            except:
                continue
    
    return None

class CustomReactAgent(BaseAgent):
    """自定义稳定版Agent，使用JSON解析替代LangGraph的create_react_agent"""
    
    def __init__(
        self,
        llm: Optional[BaseChatModel] = None,
        tools: Optional[List[BaseTool]] = None,
        system_prompt: Optional[str] = None,
        name: str = "custom_agent",
        verbose: bool = False,
        callbacks: Optional[List[Any]] = None,
        max_iterations: Optional[int] = None,
        agent_role: str = "supervisor",
        config: Optional[Dict[str, Any]] = None
    ):
        """初始化自定义Agent
        
        Args:
            llm: 语言模型，如果为None将使用默认配置创建
            tools: 可用工具列表
            system_prompt: 系统提示词，如果为None将使用默认提示词
            name: 智能体名称
            verbose: 是否输出详细日志
            callbacks: 回调函数列表，用于流式输出等
            max_iterations: 最大迭代次数，如果为None则从配置获取
            agent_role: 智能体角色类型
            config: 配置字典，如果提供则从中读取配置
        """
        self.agent_role = agent_role
        self.callbacks = callbacks
        
        # 处理配置
        from app.core.config import ConfigManager
        config_manager = ConfigManager()
        if config is None:
            # 如果未提供配置，尝试加载默认配置
            try:
                config_manager.load_config()
                agent_config = config_manager.get_agent_config()
            except Exception as e:
                logger.warning(f"加载配置失败，使用默认值: {str(e)}")
                agent_config = {}
        else:
            agent_config = config
        
        # 从配置中获取最大迭代次数
        if max_iterations is None:
            self.max_iterations = agent_config.get("max_iterations", 10)
        else:
            self.max_iterations = max_iterations
        
        # 调用父类构造函数
        super().__init__(
            llm=llm,
            tools=tools,
            system_prompt=system_prompt,
            name=name,
            verbose=verbose
        )
        
        # 创建输出解析器
        self.output_parser = JsonOutputParser(pydantic_object=AgentAction)
        
        # 创建修复解析器
        self.fixing_parser = OutputFixingParser.from_llm(
            parser=self.output_parser,
            llm=self.llm
        )
        
        # 如果没有提供系统提示词，生成自定义的系统提示词
        if not self.system_prompt:
            tools_str = self.format_tool_for_prompt()
            self.system_prompt = get_custom_agent_system_prompt(
                agent_role=self.agent_role,
                tools_str=tools_str
            )
            if self.verbose:
                logger.info(f"已生成自定义{self.agent_role}系统提示词")
    
    def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Any:
        """执行工具
        
        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            
        Returns:
            工具执行结果，如果出错会返回包含error字段的字典
        """
        # 查找工具
        tool = None
        for t in self.tools:
            if t.name == tool_name:
                tool = t
                break
        
        # 处理找不到工具的情况
        if tool is None:
            error_msg = f"找不到工具: {tool_name}"
            logger.error(error_msg)
            return {"error": error_msg, "formatted_error": f"❌ 错误: {error_msg}"}
            
        # 转换参数类型（处理字符串格式的布尔值和数值）
        converted_args = {}
        for key, value in tool_args.items():
            if isinstance(value, str):
                # 转换布尔值
                if value.lower() in ("true", "false"):
                    converted_args[key] = (value.lower() == "true")
                # 转换整数
                elif value.isdigit():
                    converted_args[key] = int(value)
                # 转换浮点数
                elif re.match(r"^-?\d+(\.\d+)?$", value):
                    converted_args[key] = float(value)
                else:
                    # 保持字符串
                    converted_args[key] = value
            else:
                # 非字符串值保持不变
                converted_args[key] = value
                
        # 记录参数转换
        if converted_args != tool_args:
            logger.info(f"工具 {tool_name} 参数类型转换: {tool_args} -> {converted_args}")
        
        # 使用转换后的参数
        tool_args = converted_args
        
        # 执行工具
        try:
            # 特殊处理报告生成工具，传递系统状态
            if tool_name == "generate_isotope_report":
                logger.info("检测到报告生成工具调用，传递系统状态")
                # 获取当前状态
                if hasattr(self, "_state") and self._state:
                    # 确保state_dict是字典格式而不是复杂对象
                    # 创建一个简化的状态字典，只包含必要信息
                    simplified_state = {
                        "current_task": self._state.get("current_task", {}),
                        "files": self._state.get("files", {})
                    }
                    # 重写参数，确保state_dict参数存在
                    tool_args["state_dict"] = simplified_state
                    logger.info("已将简化系统状态传递给报告生成工具")
            
            # 尝试两种不同的调用方式
            try:
                # 方法1: 使用关键字参数调用 (tool.run(**tool_args))
                result = tool.run(**tool_args)
                logger.info(f"使用 **kwargs 方式成功调用工具 {tool_name}")
                # 格式化结果以便更好地展示
                return self._format_tool_result(result, tool_name)
            except TypeError as e:
                if "missing 1 required positional argument: 'tool_input'" in str(e):
                    # 方法2: 使用单一字符串参数调用 (tool.run(tool_input))
                    # 有些LangChain工具期望单一参数，将工具参数转换为单一字符串或字典
                    if len(tool_args) == 1 and next(iter(tool_args.values())) is not None:
                        # 如果只有一个参数，直接传递它的值
                        single_input = next(iter(tool_args.values()))
                        
                        # 特殊处理报告生成工具的单参数调用
                        if tool_name == "generate_isotope_report" and hasattr(self, "_state") and self._state:
                            # 创建一个简化的状态字典
                            simplified_state = {
                                "current_task": self._state.get("current_task", {}),
                                "files": self._state.get("files", {})
                            }
                            # 使用字典调用
                            logger.info("使用单一参数方式调用报告生成工具并传递状态")
                            result = tool.run({"state_dict": simplified_state})
                        else:
                            # 其他工具正常调用
                            result = tool.run(single_input)
                            
                        logger.info(f"使用单一参数值方式成功调用工具 {tool_name}")
                        return self._format_tool_result(result, tool_name)
                    else:
                        # 传递整个参数字典作为tool_input
                        # 特殊处理报告生成工具的字典参数调用
                        if tool_name == "generate_isotope_report" and hasattr(self, "_state") and self._state:
                            # 创建一个简化的状态字典
                            simplified_state = {
                                "current_task": self._state.get("current_task", {}),
                                "files": self._state.get("files", {})
                            }
                            # 使用字典调用
                            tool_args = {"state_dict": simplified_state}
                            logger.info("使用字典参数方式调用报告生成工具并传递状态")
                        
                        result = tool.run(tool_args)
                        logger.info(f"使用参数字典方式成功调用工具 {tool_name}")
                        return self._format_tool_result(result, tool_name)
                else:
                    # 其它类型的TypeError，重新抛出
                    raise
                    
        except Exception as e:
            error_msg = f"执行工具 {tool_name} 出错: {str(e)}"
            logger.error(error_msg)
            # 返回格式化的错误信息，更容易被LLM识别
            return {
                "error": error_msg, 
                "formatted_error": f"❌ 工具执行失败: {tool_name}\n错误信息: {str(e)}\n注意: 请勿重复执行相同的工具调用，应该尝试不同的参数或不同的工具。"
            }
            
    def _format_tool_result(self, result: Any, tool_name: str) -> Any:
        """格式化工具执行结果，使其更易于阅读和理解
        
        Args:
            result: 工具原始结果
            tool_name: 工具名称
            
        Returns:
            格式化后的结果
        """
        # 如果结果已经是字符串，检查是否为JSON字符串
        if isinstance(result, str):
            # 尝试解析为JSON
            if result.startswith("{") and result.endswith("}"):
                try:
                    json_data = json.loads(result)
                    # 如果是文件消息，保持原样返回，前端负责解析
                    if "file_message" in json_data:
                        return result
                except json.JSONDecodeError:
                    pass
            return result
            
        # 如果结果是字典，检查是否已经包含格式化的内容
        if isinstance(result, dict):
            # 检查是否有预先格式化的内容
            if "formatted_result" in result:
                return result["formatted_result"]
            
            # 如果是错误信息，特别处理
            if "error" in result:
                return f"❌ 错误: {result['error']}"
                
            # 尝试将字典格式化为易读的文本
            try:
                # 使用json.dumps美化输出，但限制层级和长度
                formatted = json.dumps(result, ensure_ascii=False, indent=2)
                if len(formatted) > 1000:  # 避免过长的输出
                    formatted = json.dumps(result, ensure_ascii=False)
                return f"🔍 {tool_name} 执行结果:\n{formatted}"
            except:
                pass
        
        # 如果是其他类型，尝试转换为字符串
        try:
            return f"🔍 {tool_name} 执行结果:\n{str(result)}"
        except:
            return f"🔍 {tool_name} 返回了无法显示的结果类型: {type(result).__name__}"
    
    def _update_task_with_tool_execution(
        self, 
        state: IsotopeSystemState, 
        tool_name: str, 
        tool_args: Dict[str, Any], 
        tool_result: Any
    ) -> IsotopeSystemState:
        """使用工具执行结果更新任务状态
        
        Args:
            state: 当前系统状态
            tool_name: 工具名称
            tool_args: 工具参数
            tool_result: 工具执行结果
            
        Returns:
            更新后的状态
        """
        current_task = state.get("current_task", {})
        if not current_task:
            return state
        
        # 初始化工具执行列表（如果不存在）
        if "tool_executions" not in current_task:
            current_task["tool_executions"] = []
        
        # 生成唯一的工具执行ID
        tool_execution_id = f"tool_exec_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}"
        
        # 创建工具执行记录
        execution = {
            "tool_name": tool_name,
            "tool_id": tool_execution_id,  # 添加唯一工具执行ID
            "input": tool_args,
            "output": str(tool_result),
            "status": "success",
            "timestamp": datetime.now().isoformat()
        }
        
        # 添加到执行列表
        current_task["tool_executions"].append(execution)
        
        # 更新任务
        return StateManager.update_current_task(state, current_task)
    
    def _extract_route_from_text(self, text: str) -> Optional[str]:
        """从文本中提取路由信息
        
        Args:
            text: 文本内容
            
        Returns:
            路由目标，如果没有则返回None
        """
        # 检查标准路由标记
        if "[数据处理]" in text:
            return "data_agent"
        elif "[专家分析]" in text:
            return "expert_agent"
        elif "[等待用户]" in text:
            return "human_interaction"
        elif "[完成]" in text:
            return None
        
        # 尝试以更宽松的方式检查路由信息
        text_lower = text.lower()
        if "路由到数据处理" in text_lower or "转到数据处理" in text_lower:
            return "data_agent"
        elif "路由到专家" in text_lower or "转到专家" in text_lower:
            return "expert_agent"
        elif "等待用户输入" in text_lower or "需要用户确认" in text_lower:
            return "human_interaction"
        
        return None
    
    def run(self, state: IsotopeSystemState) -> Dict[str, Any]:
        """运行自定义Agent
        
        Args:
            state: 当前系统状态
            
        Returns:
            更新后的状态
        """
        # 保存当前状态到实例变量，以便工具执行时可以访问
        self._state = state
        
        # 获取流写入器用于流式输出
        writer = get_stream_writer()
        
        # 记录动作开始
        state = StateManager.add_action_record(
            state, 
            {
                "node": self.name,
                "action": "process_input",
                "timestamp": datetime.now().isoformat()
            }
        )
        
        # 准备消息历史
        messages = self._prepare_messages_for_llm(state)
        self.log_messages(messages)
        
        # 获取最后一条用户消息
        last_human_msg = StateManager.get_last_human_message(state)
        if not last_human_msg:
            error_msg = "未找到用户消息，无法继续处理。"
            return StateManager.update_messages(state, AIMessage(content=error_msg))
        
        # 记录思考过程开始
        if writer:
            writer({"agent_thinking": f"{self.name}开始分析用户输入..."})
        
        # 运行循环，最多执行max_iterations次
        iteration = 0
        
        # 记录工具执行错误，避免重复执行相同的失败工具
        failed_tools = set()
        
        while iteration < self.max_iterations:
            # 调用LLM
            if writer:
                writer({"agent_thinking": f"思考中 (第{iteration+1}次迭代)...\n"})
                
                # 如果有失败的工具，提醒LLM
                if failed_tools:
                    writer({"agent_thinking": f"注意: 以下工具执行失败，请勿重复调用: {', '.join(failed_tools)}"})
            
            # 生成LLM响应 - 修改为支持实时内容提取的流式输出
            llm_response = ""
            current_json_buffer = ""  # 用于累积可能的JSON内容
            response_content_started = False  # 标记是否开始提取response内容
            extracted_response = ""  # 提取出来的真正响应内容
            
            # 获取流写入器用于实时输出
            from app.ui.streaming import get_stream_writer
            stream_writer = get_stream_writer()
            
            for chunk in self.llm.stream(messages):
                content = chunk.content
                llm_response += content
                current_json_buffer += content
                
                # 检查是否开始输出JSON格式的监督者响应
                if "【监督者supervisor】：" in current_json_buffer and not response_content_started:
                    # 尝试提取JSON部分
                    json_start = current_json_buffer.find("】：") + 2
                    if json_start > 1:  # 确保找到了JSON开始位置
                        json_part = current_json_buffer[json_start:]
                        
                        # 检查是否有完整的JSON结构开始
                        if json_part.strip().startswith('{"action_type"'):
                            response_content_started = True
                            # 开始查找response字段的内容
                            continue
                
                # 如果已经开始提取响应内容
                if response_content_started:
                    # 尝试解析当前缓冲区中的JSON，提取response字段
                    json_start = current_json_buffer.find("】：") + 2
                    if json_start > 1:
                        json_part = current_json_buffer[json_start:].strip()
                        
                        # 寻找response字段的内容
                        response_start = json_part.find('"response": "')
                        if response_start != -1:
                            response_start += len('"response": "')
                            response_end = -1
                            
                            # 寻找response字段的结束位置（处理转义字符）
                            i = response_start
                            while i < len(json_part):
                                if json_part[i] == '"' and (i == 0 or json_part[i-1] != '\\'):
                                    response_end = i
                                    break
                                i += 1
                            
                            if response_end != -1:
                                # 提取完整的response内容
                                new_response_content = json_part[response_start:response_end]
                                
                                # 如果有新的内容，输出增量部分
                                if len(new_response_content) > len(extracted_response):
                                    new_chunk = new_response_content[len(extracted_response):]
                                    extracted_response = new_response_content
                                    
                                    # 实时输出提取的内容而不是JSON
                                    if stream_writer and new_chunk:
                                        # 创建一个AI消息块来模拟正常的LLM输出
                                        from langchain_core.messages import AIMessageChunk
                                        clean_chunk = AIMessageChunk(content=new_chunk)
                                        stream_writer(clean_chunk)
            
            # 如果提取到了响应内容，用提取的内容替换原始LLM响应中的JSON部分
            if extracted_response and response_content_started:
                # 将LLM响应替换为提取出来的纯文本内容
                # 这样后续的JSON解析仍然能正常工作，但用户看到的是纯文本
                logger.info(f"成功提取监督者响应内容，长度: {len(extracted_response)}")
                
                # 保留原始响应用于JSON解析，但标记这是一个已处理的响应
                if hasattr(self, '_extracted_response_content'):
                    self._extracted_response_content = extracted_response
                else:
                    setattr(self, '_extracted_response_content', extracted_response)
            
            # 提取JSON部分
            json_str = extract_json_from_llm_output(llm_response)
            
            # 如果没有JSON，检查是否有路由标记
            if not json_str:
                route_to = self._extract_route_from_text(llm_response)
                
                if route_to:
                    # 有路由标记但没有JSON，创建路由动作
                    response_msg = AIMessage(
                        content=llm_response,
                        additional_kwargs={
                            "route_to": route_to,
                            "source": self.name
                        }
                    )
                    return StateManager.update_messages(state, response_msg)
                else:
                    # 没有JSON也没有路由标记，这是一个直接回复
                    return StateManager.update_messages(state, AIMessage(content=llm_response))
            
            try:
                # 解析JSON
                action_raw = self.fixing_parser.parse(json_str)

                # --- Robust handling of action type ---
                action_type = None
                tool_name = None
                tool_args = None
                route_to = None
                response_content = None

                if isinstance(action_raw, dict):
                    # Handle as dictionary
                    logger.debug("解析为字典")
                    action_type = action_raw.get("action_type")
                    if action_type == "tool_call":
                        tool_name = action_raw.get("tool_name")
                        # 记录工具名称，确保它不是None或空字符串
                        if not tool_name:
                            logger.warning(f"工具调用中缺少tool_name: {json.dumps(action_raw)}")
                            tool_name = "未命名工具"  # 提供默认值防止空名称
                        tool_args = action_raw.get("tool_args", {})
                    elif action_type == "route":
                        route_to = action_raw.get("route_to")
                        response_content = action_raw.get("response")
                    elif action_type == "finish":
                        response_content = action_raw.get("response")
                elif hasattr(action_raw, "action_type"):
                     # Handle as Pydantic object (or similar object with attributes)
                     logger.debug("解析为对象")
                     action_type = getattr(action_raw, "action_type", None)
                     if action_type == "tool_call":
                         tool_name = getattr(action_raw, "tool_name", None)
                         # 记录工具名称，确保它不是None或空字符串
                         if not tool_name:
                             logger.warning(f"工具调用对象中缺少tool_name: {action_raw}")
                             tool_name = "未命名工具"  # 提供默认值防止空名称
                         tool_args = getattr(action_raw, "tool_args", {})
                     elif action_type == "route":
                         route_to = getattr(action_raw, "route_to", None)
                         response_content = getattr(action_raw, "response", None)
                     elif action_type == "finish":
                         response_content = getattr(action_raw, "response", None)
                else:
                    # Unexpected type
                    logger.error(f"解析的动作既不是字典也不是预期的对象: {type(action_raw)}")
                    raise ValueError(f"无法解析的动作格式: {type(action_raw)}")
                # --- End robust handling ---


                # 根据动作类型处理
                # if action.action_type == "tool_call": # Old way
                if action_type == "tool_call": # New way
                    if not tool_name or not isinstance(tool_args, dict):
                         logger.error(f"无效的工具调用动作: name={tool_name}, args_type={type(tool_args)}")
                         raise ValueError("无效的工具调用动作")
                    
                    # 检查是否尝试调用已经失败过的工具
                    if tool_name in failed_tools:
                        warning_msg = f"正在尝试重复调用已失败的工具: {tool_name}，将跳过并告知LLM"
                        logger.warning(warning_msg)
                        if writer:
                            writer({"agent_thinking": f"⚠️ {warning_msg}"})
                        
                        # 将警告消息添加到消息历史
                        warning_tool_message = AIMessage(
                            content=f"⚠️ 警告: 工具 {tool_name} 之前已执行失败，请尝试其他工具或提供不同的参数。请勿重复执行相同的失败工具调用。"
                        )
                        messages.append(warning_tool_message)
                        continue  # 跳到下一次迭代

                    # 执行工具调用
                    if writer:
                        writer({"agent_thinking": f"执行工具: {tool_name}"})

                    tool_result = self._execute_tool(tool_name, tool_args)

                    # 检查工具执行是否出错
                    is_error = False
                    if isinstance(tool_result, dict) and "error" in tool_result:
                        is_error = True
                        # 记录失败的工具
                        failed_tools.add(tool_name)
                        if writer:
                            error_content = tool_result.get("formatted_error", f"❌ 工具执行失败: {tool_result['error']}")
                            writer({"agent_thinking": error_content})

                    # 添加工具执行记录
                    state = self._update_task_with_tool_execution(
                        state,
                        tool_name,
                        tool_args,
                        tool_result
                    )

                    # 将工具结果添加到消息历史
                    tool_message = ToolMessage(
                        content=f"【{tool_name}工具执行结果】: {str(tool_result) if not isinstance(tool_result, dict) or 'formatted_error' not in tool_result else tool_result['formatted_error']}",
                        name=tool_name, # 确保name字段始终被设置
                        tool_call_id=f"tool_call_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}"  # 使用时间戳和uuid组合确保唯一性
                    )
                    messages.append(tool_message)
                    
                    # 如果工具执行出错，添加一条特别的提示消息帮助LLM理解错误
                    if is_error:
                        error_hint = AIMessage(
                            content=f"⚠️ 工具 {tool_name} 执行失败，请勿重复调用。请考虑：\n1. 使用不同参数再次尝试\n2. 使用其他工具\n3. 直接给出目前可用的分析结果"
                        )
                        messages.append(error_hint)

                # elif action.action_type == "route": # Old way
                elif action_type == "route": # New way
                    if not route_to:
                        logger.error(f"无效的路由动作: route_to={route_to}")
                        raise ValueError("无效的路由动作")
                    # 路由到其他节点
                    if writer:
                        writer({"agent_thinking": f"路由到: {route_to}"})

                    # 创建响应消息并添加路由信息
                    response_msg = AIMessage(
                        content=response_content or f"正在路由到{route_to}处理...",
                    )

                    # 添加路由信息到消息元数据
                    response_msg.additional_kwargs = {
                        "route_to": route_to, # Use the extracted route_to
                        "source": self.name
                    }

                    # 更新状态并返回
                    return StateManager.update_messages(state, response_msg)

                # elif action.action_type == "finish": # Old way
                elif action_type == "finish": # New way
                    # 完成任务
                    if writer:
                        writer({"agent_thinking": "任务完成"})

                    # 创建响应消息 - 优先使用提取的内容
                    final_content = response_content or "任务已完成"
                    if hasattr(self, '_extracted_response_content') and self._extracted_response_content:
                        final_content = self._extracted_response_content
                        logger.info(f"使用提取的响应内容: {final_content[:100]}...")
                    
                    response_msg = AIMessage(content=final_content)
                    
                    # 添加结束标记到消息元数据
                    response_msg.additional_kwargs = {
                        "task_complete": True,
                        "route_to": "end",
                        "source": self.name
                    }

                    # 更新状态
                    state = StateManager.update_messages(state, response_msg)
                    
                    # 更新任务状态为完成
                    current_task = state.get("current_task", {})
                    if current_task:
                        current_task["status"] = TaskStatus.COMPLETED
                        state = StateManager.update_current_task(state, current_task)
                    
                    # 返回带有结束标记的状态
                    return state
                else:
                     # Handle case where action_type is None or unrecognized
                     logger.warning(f"未识别或缺失的 action_type: {action_type} in {action_raw}")
                     # Decide how to proceed: maybe treat as a direct response?
                     # For now, let's assume it might be a direct response hidden in the llm_response
                     if llm_response and not json_str: # If original response was just text
                         logger.info("Treating as direct response as action_type is invalid/missing.")
                         return StateManager.update_messages(state, AIMessage(content=llm_response))
                     else: # If there was JSON but it's invalid
                         raise ValueError(f"无法处理的动作类型: {action_type}")


            except Exception as e:
                # 解析错误，记录错误并继续
                logger.error(f"解析或执行出错: {str(e)}")
                if writer:
                    writer({"agent_thinking": f"处理出错: {str(e)}"})
                
                # 将错误信息添加到消息历史
                error_message = AIMessage(
                    content=f"⚠️ 发生错误: {str(e)}。请尝试不同的方法或命令。"
                )
                messages.append(error_message)
                
                # 如果是最后一次迭代，返回错误消息
                if iteration == self.max_iterations - 1:
                    error_msg = AIMessage(content=f"很抱歉，在处理您的请求时遇到了问题: {str(e)}")
                    return StateManager.update_messages(state, error_msg)
            
            # 增加迭代计数
            iteration += 1
        
        # 如果达到最大迭代次数仍未完成
        max_iter_msg = AIMessage(content="抱歉，处理您的请求时达到了最大迭代次数限制。请尝试重新表述您的问题。")
        return StateManager.update_messages(state, max_iter_msg)
    
