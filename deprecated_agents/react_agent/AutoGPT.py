import json
from typing import List, Optional, Tuple
import os
import traceback

from langchain_community.chat_message_histories.in_memory import ChatMessageHistory
from langchain.tools.render import render_text_description
from langchain_core.language_models.chat_models import BaseChatModel
from langchain.output_parsers import PydanticOutputParser, OutputFixingParser
from langchain.schema.output_parser import StrOutputParser
from langchain.tools.base import BaseTool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder,HumanMessagePromptTemplate
from pydantic import ValidationError
import re
from app.agents.react_agent.Action import Action
from app.agents.react_agent.CallbackHandlers import ColoredPrintHandler
from app.agents.react_agent.PrintUtils import THOUGHT_COLOR
from app.agents.react_agent.UIState import UIState


class AutoGPT:
    """AutoGPT：基于Langchain实现"""

    @staticmethod
    def __format_thought_observation(thought: str, action: Action, observation: str) -> str:
        # 将全部JSON代码块替换为空
        ret = re.sub(r'```json(.*?)```', '', thought, flags=re.DOTALL)
        ret += "\n" + str(action) + "\n返回结果:\n" + observation
        return ret

    @staticmethod
    def __extract_json_action(text: str) -> str | None:
        # 匹配最后出现的JSON代码块
        json_pattern = re.compile(r'```json(.*?)```', re.DOTALL)
        matches = json_pattern.findall(text)
        if matches:
            last_json_str = matches[-1]
            return last_json_str
        return None

    def __init__(
            self,
            llm: BaseChatModel,
            tools: List[BaseTool],
            work_dir: str = "./data",
            main_prompt_file: str = "./prompts/main/main.json",
            max_thought_steps: Optional[int] = 10,
    ):
        self.llm = llm
        self.tools = tools
        self.work_dir = work_dir
        self.max_thought_steps = max_thought_steps
        self.thought_process_history = ""
        self.reply = ""
        self.origin_image = None
        self.result_image = None
        self.visualization_3d = None
        # OutputFixingParser： 如果输出格式不正确，尝试修复
        self.output_parser = PydanticOutputParser(pydantic_object=Action)
        self.robust_parser = OutputFixingParser.from_llm(parser=self.output_parser, llm=self.llm)

        self.main_prompt_file = main_prompt_file
        self.__init_prompt_templates()
        self.__init_chains()

        self.verbose_handler = ColoredPrintHandler(color=THOUGHT_COLOR)
        self.has_printed_debug = False  # 添加调试信息打印标志
        self.ui_state = UIState()

    def __init_prompt_templates(self):
        with open(self.main_prompt_file, 'r', encoding='utf-8') as f:
            self.prompt = ChatPromptTemplate.from_messages(
                [
                    MessagesPlaceholder(variable_name="chat_history"),
                    HumanMessagePromptTemplate.from_template(f.read()),
                ]
            ).partial(
                work_dir=self.work_dir,
                tools=render_text_description(self.tools),
                tool_names=','.join([tool.name for tool in self.tools]),
                format_instructions=self.output_parser.get_format_instructions(),
            )

    def __init_chains(self):
        # 主流程的chain
        self.main_chain = (self.prompt | self.llm | StrOutputParser())

    def __find_tool(self, tool_name: str) -> Optional[BaseTool]:
        for tool in self.tools:
            if tool.name == tool_name:
                return tool
        return None

    def __step(
            self, 
            task, 
            short_term_memory, 
            chat_history
    ):
        """执行一步思考"""
        response = ""
        # 准备输入变量
        inputs = {
            "input": task,
            "agent_scratchpad": "\n".join(short_term_memory),
            "chat_history": chat_history.messages
        }
        
        for s in self.main_chain.stream(inputs):
            response += s
            # 修改这里：直接更新到 ui_state
            self.ui_state.thought_process += s
            yield "PUSH_UI", self.push_UI()

        self.ui_state.thought_process += "\n"
        # 提取JSON代码块
        json_action = self.__extract_json_action(response)
        # 带容错的解析
        action = self.robust_parser.parse(
            json_action if json_action else response
        )
        yield "PROCESS", (action, response)

    def __exec_action(self, action: Action):
        try:
            # 查找工具
            tool = self.__find_tool(action.name)
            if tool is None:
                observation = (
                    f"Error: 找不到工具或指令 '{action.name}'. "
                    f"请从提供的工具/指令列表中选择，请确保按对顶格式输出。"
                )
            else:
                try:
                    # 执行工具
                    observation = tool.run(action.args)
                    
                    # 处理不同类型的返回值
                    if isinstance(observation, dict):
                        # 如果是图片处理工具的返回结果
                        if observation.get("type") == "image_result":
                            self.ui_state.origin_image = observation.get("origin_image")
                            self.ui_state.result_image = observation.get("result_image")
                            observation_str = observation.get("message", str(observation))
                            return observation_str
                        # 如果是3D可视化工具的返回结果
                        elif observation.get("type") == "3d_visualization":
                            self.ui_state.visualization_3d = observation.get("content")
                            print(f"Debug: Setting visualization_3d to: {self.ui_state.visualization_3d}")  # 调试信息
                            observation_str = observation.get("message", str(observation))
                            return observation_str
                        else:
                            return str(observation)
                    else:
                        return str(observation) if observation is not None else ""
                    
                except ValidationError as e:
                    observation = (
                        f"Validation Error in args: {str(e)}, args: {action.args}"
                    )
                except Exception as e:
                    observation = f"Error: {str(e)}, {type(e).__name__}, args: {action.args}"
                
            return observation
            
        except Exception as e:
            print(f"Error in __exec_action: {str(e)}")
            traceback.print_exc()
            return f"Error executing action: {str(e)}"

    def push_UI(self):
        """返回当前UI状态"""
        try:
            return {
                "thought_process": self.ui_state.thought_process,
                "result": self.ui_state.result,
                "origin_image": self.ui_state.origin_image,
                "result_image": self.ui_state.result_image,
                "visualization_3d": self.ui_state.visualization_3d
            }
        except Exception as e:
            print(f"[Error] in push_UI: {str(e)}")
            traceback.print_exc()
            return {}

    def run(
            self,
            task,
            chat_history: ChatMessageHistory
    ):
        """运行智能体"""
        try:
            # 重置UI状态
            self.ui_state = UIState()
            
            # 初始化短时记忆
            short_term_memory = []

            # 思考步数
            thought_step_count = 0

            # 开始逐步思考
            while thought_step_count < self.max_thought_steps:
                # 更新轮次信息
                self.ui_state.thought_process += f"\n>>>>Round: {thought_step_count}<<<<\n"
                yield self.push_UI()

                # 执行思考
                for output_type, output_value in self.__step(
                        task=task,
                        short_term_memory=short_term_memory,
                        chat_history=chat_history,
                ):
                    if output_type == "PUSH_UI":
                        yield output_value
                    elif output_type == "PROCESS":
                        action, response = output_value

                # 如果是结束指令，执行最后一步
                if action.name == "FINISH":
                    # 修改这里：确保 FINISH 动作有正确的参数格式
                    if not action.args:
                        action.args = {"reply": "对话结束"}  # 提供默认回复
                    self.ui_state.result = action.args.get("reply", "对话结束")
                    yield self.push_UI()
                    break

                # 执行动作
                observation = self.__exec_action(action)
                
                # 处理观察结果
                observation_str = self._process_observation(observation)

                # 更新思考过程
                self.ui_state.thought_process += f"\n----\n工具执行结果:\n{observation_str}\n"
                yield self.push_UI()

                # 更新短时记忆
                short_term_memory.append(
                    self.__format_thought_observation(
                        response, action, observation_str
                    )
                )
                thought_step_count += 1

            if thought_step_count >= self.max_thought_steps:
                self.ui_state.result = "抱歉，我没能完成您的任务。"
                yield self.push_UI()
            print(short_term_memory)
            # 更新长时记忆
            chat_history.add_user_message(task)
            chat_history.add_ai_message(self.ui_state.result)

        except Exception as e:
            print(f"Error in run: {str(e)}")
            traceback.print_exc()
            self.ui_state.result = f"Error running AutoGPT: {str(e)}"
            yield self.push_UI()

    def _process_observation(self, observation):
        """处理观察结果"""
        try:
            if isinstance(observation, dict):
                if observation.get("type") == "image_result":
                    # 直接更新UI状态
                    self.ui_state.origin_image = observation.get("origin_image")
                    self.ui_state.result_image = observation.get("result_image")
                    print(f"[Image] New images processed: {self.ui_state.origin_image is not None}, {self.ui_state.result_image is not None}")
                    return observation.get("message", str(observation))
                elif observation.get("type") == "3d_visualization":
                    # 直接更新UI状态
                    self.ui_state.visualization_3d = observation.get("content")
                    print(f"[3D] New model: {self.ui_state.visualization_3d}")
                    return observation.get("message", str(observation))
            return str(observation) if observation is not None else ""
        except Exception as e:
            print(f"[Error] in _process_observation: {str(e)}")
            traceback.print_exc()
            return str(observation)
