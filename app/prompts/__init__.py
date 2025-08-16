"""提示词模块包"""

from app.prompts.prompts import (
    get_main_agent_system_prompt,
    # 保留传统智能体提示词以维持兼容性，但已标记为弃用
    get_data_agent_system_prompt,
    get_expert_agent_system_prompt,
    # 新增专业智能体提示词
    get_specialized_agent_system_prompt
)

__all__ = [
    'get_main_agent_system_prompt',
    # 传统智能体提示词（已弃用）
    'get_data_agent_system_prompt',
    'get_expert_agent_system_prompt',
    # 专业智能体提示词
    'get_specialized_agent_system_prompt'
] 