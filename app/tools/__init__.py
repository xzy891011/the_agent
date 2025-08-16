"""
工具系统包 - 包含系统所有可用工具和工具注册机制

此包提供：
1. 工具注册中心 - 集中管理所有工具
2. 文件操作工具 - 读取和处理各种文件
3. 代码生成和执行工具 - 生成和安全执行Python代码
4. 自定义工具接口 - 可扩展的工具开发框架
5. 知识检索工具 - 提供信息检索功能，包括RAGFlow、SQL、文件系统等
"""

from app.tools.registry import (
    register_tool, 
    get_all_tools, 
    get_tool, 
    get_tools_by_category,
    get_tools_for_llm,
    registry
)

# 导入工具模块 - 使用条件性导入避免依赖问题
import app.tools.file_tools
import app.tools.code_executor  # 导入代码执行工具
import app.tools.logging
import app.tools.meanderpy

# 条件性导入可能有依赖问题的模块
try:
    import app.tools.rock_core
except ImportError as e:
    import logging
    logging.getLogger(__name__).warning(f"rock_core模块导入失败: {e}")

try:
    import app.tools.reservior
except ImportError as e:
    import logging
    logging.getLogger(__name__).warning(f"reservior模块导入失败: {e}")

import app.tools.knowledge_tools  # 导入知识检索工具

# 获取所有注册的工具
all_tools = get_all_tools()
file_tools = get_tools_by_category("file")
code_tools = get_tools_by_category("code")  # 添加代码工具的快捷访问
# isotope_tools = get_tools_by_category("isotope")  # 添加碳同位素工具的快捷访问
isotope_enhanced_tools = get_tools_by_category("logging")  # 添加增强碳同位素工具的快捷访问
meanderpy_tools = get_tools_by_category("meanderpy")  # 添加meanderpy工具的快捷访问
rock_core_tools = get_tools_by_category("rock_core")  # 添加岩心工具的快捷访问
knowledge_tools = get_tools_by_category("knowledge")  # 添加知识检索工具的快捷访问

def get_registered_tools_info() -> str:
    """获取所有注册工具的信息字符串"""
    tools = get_all_tools()
    categories = registry.get_all_categories()
    
    info = f"已注册工具: {len(tools)} 个，分类: {len(categories)} 个\n"
    
    # 按分类组织工具
    for category in categories:
        category_tools = get_tools_by_category(category)
        info += f"\n## 分类 '{category}' ({len(category_tools)} 个工具):\n"
        
        for tool in category_tools:
            info += f"- {tool.name}: {tool.description[:50]}{'...' if len(tool.description) > 50 else ''}\n"
    
    # 未分类工具
    uncategorized = [t for t in tools if registry.get_tool_metadata(t.name).get("category") is None]
    if uncategorized:
        info += f"\n未分类工具 ({len(uncategorized)} 个):\n"
        for tool in uncategorized:
            info += f"- {tool.name}: {tool.description[:50]}{'...' if len(tool.description) > 50 else ''}\n"
    
    return info 