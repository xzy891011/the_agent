"""
自定义Agent提示词模块 - 为自定义Agent提供系统提示词
"""
from typing import Dict, List, Any, Optional

from app.prompts.prompts import (
    get_main_agent_system_prompt,
    get_data_agent_system_prompt,
    get_expert_agent_system_prompt
)

def get_custom_agent_system_prompt(agent_role: str, tools_str: str) -> str:
    """获取自定义Agent的系统提示词
    
    Args:
        agent_role: 智能体角色（supervisor、expert_agent、data_agent）
        tools_str: 工具描述字符串
        
    Returns:
        格式化后的系统提示词
    """
    base_prompt = ""
    
    if agent_role == "supervisor":
        base_prompt = get_main_agent_system_prompt()
    elif agent_role == "expert_agent":
        base_prompt = get_expert_agent_system_prompt()
    elif agent_role == "data_agent":
        base_prompt = get_data_agent_system_prompt()
    else:
        base_prompt = "你是一个智能助手，可以帮助用户解决各种问题。"
    
    # 添加工具错误处理指导
    error_handling_guide = """
## 工具执行错误处理指南
当工具执行失败时，你会收到包含错误信息的响应。面对工具错误，请遵循以下原则：

1. 不要重复调用失败的工具：如果一个工具执行失败，不要用相同的参数再次调用它，这只会导致相同的错误。
2. 尝试替代方案：可以考虑使用不同的参数再次尝试，或者使用其他工具来达成类似目的。
3. 适应当前状况：根据已有的工具执行结果，给出尽可能有用的分析或回答，即使某些工具失败。
4. 清晰沟通：向用户解释工具执行失败的原因，并说明你的后续策略。
5. 识别错误模式：错误消息通常会以"❌"符号开头，或者包含"error"、"failed"等关键词。

记住：面对错误时的灵活处理比固执地重复相同操作更有价值。一个好的智能体应该能从错误中学习并调整策略。
"""
    
    # 添加JSON输出格式指导
    json_format_guide = """
## 输出内容格式：
- 你的输出必须分为3部分：
    1. 【工作规划】- 总结历史对话消息，并根据历史对话消息，分析并更新要完成的工作计划，已完成的工作计划后边添加[已完成]，未完成的工作计划后边添加[未完成]
    2. 【工具调用规划】- 严格根据【工作规划】，思考并规划调用哪些工具，禁止调用与【工作规划】无关的工具。对于已经成功执行返回结果的工具，后边添加[已执行]，对于未执行的工具，后边添加[未执行]。如果有工具tools可以调用，则列出工具调用规划列表，如果没有工具tools可以调用，则列出工具调用规划列表为空
    3. 【动作请求】- JSON格式的动作请求，【重要】：一次仅允许输出一个JSON格式的动作请求，且JSON块输出完毕后禁止继续输出任何内容，具体格式如下：
        - 当需要调用工具时，你需要在分析思考后使用以下JSON格式输出工具调用请求，注意：当你的角色是【监督者supervisor】时，禁止调用工具:

        ```json
        {
            "action_type": "tool_call",
            "tool_name": "工具名称",
            "tool_args": {
                "参数1": "值1",
                "参数2": "值2"
            }
        }
        ```

        - 当需要路由到其他节点时，使用以下格式:

        ```json
        {
            "action_type": "route",
            "route_to": "目标节点。如果你的角色是【监督者supervisor】，则可选值: supervisor, data_agent, expert_agent, human_interaction；如果你的角色是【数据智能体data_agent】或【专家智能体expert_agent】，则可选值: supervisor",
            "response": "传递给目标节点的高度凝练总结性回复，禁止描述细节"
        }
        ```

        - 只有当你的角色是【监督者supervisor】时，才可以在完成任务不需要更多操作时，使用以下格式:

        ```json
        {
            "action_type": "finish",
            "response": "给用户的最终总结回复，告知用户任务是否完成"
        }
        ```
        【重要】：一次仅允许输出一个JSON格式的动作请求，且JSON块输出完毕后禁止继续输出任何内容
## 请按照上述输出内容格式输出【工作规划】、【工具调用规划】、【动作请求】：
"""
    
    # 添加可用工具信息
    tools_intro = f"""
可用的工具tools列表：
{tools_str}
"""
    
    # 组合提示词
    return base_prompt + "\n\n" + error_handling_guide + "\n\n" + tools_intro + "\n\n" + json_format_guide