# 该文件已被新的LangGraph架构替代，标记为弃用
# 新架构使用LangGraph内置的消息和工具调用模型
# 此文件可以安全删除

import warnings
warnings.warn(
    "custom_react_agent_models.py已弃用，请使用新的LangGraph架构", 
    DeprecationWarning, 
    stacklevel=2
)

# 为了向后兼容，保留类定义但标记为弃用
class AgentAction:
    """已弃用：请使用LangGraph的标准消息模型"""
    def __init__(self, tool, tool_input, log):
        warnings.warn("AgentAction已弃用", DeprecationWarning)
        self.tool = tool
        self.tool_input = tool_input
        self.log = log

class AgentFinish:
    """已弃用：请使用LangGraph的标准消息模型"""
    def __init__(self, return_values, log):
        warnings.warn("AgentFinish已弃用", DeprecationWarning)
        self.return_values = return_values
        self.log = log 