"""
工具注册中心 - 管理工具的注册、发现和调用

该模块提供了统一的工具注册和管理机制，支持:
1. 工具的注册与发现
2. 工具元数据的管理
3. 工具的动态加载与卸载
4. 工具调用与参数验证
5. MCP (Model Context Protocol) 工具集成
6. 从@task装饰器到MCP协议的平滑迁移
"""

import inspect
import logging
from typing import Dict, List, Any, Optional, Callable, Type, Union
import functools
import json
import asyncio

from langchain_core.tools import BaseTool, Tool as LangchainTool
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, create_model, Field

from app.core.task_decorator import task, TaskRegistry
from app.core.system_capability_registry import (
    SystemCapability, CapabilityType, register_capability
)

# 配置日志
logger = logging.getLogger(__name__)

class ToolRegistry:
    """工具注册中心，管理所有可用工具"""
    
    def __init__(self):
        """初始化工具注册中心"""
        # 存储所有注册的工具
        self._tools: Dict[str, BaseTool] = {}
        # 存储工具的元数据
        self._tool_metadata: Dict[str, Dict[str, Any]] = {}
        # 存储工具的分类信息
        self._tool_categories: Dict[str, List[str]] = {}
        
        # MCP相关
        self._mcp_tools: Dict[str, BaseTool] = {}
        self._mcp_enabled: bool = False
        self._mcp_client = None
        
        self.task_registry = TaskRegistry()
        
        logger.info("工具注册中心初始化完成")
    
    def register_tool(self, tool: BaseTool, category: Optional[str] = None) -> None:
        """注册工具到注册中心
        
        Args:
            tool: 要注册的工具
            category: 工具分类，可选
        """
        # 检查工具名称是否已存在
        if tool.name in self._tools:
            logger.warning(f"工具 '{tool.name}' 已存在，将被覆盖")
        
        # 存储工具实例
        self._tools[tool.name] = tool
        
        # 保存工具元数据
        self._tool_metadata[tool.name] = {
            "name": tool.name,
            "description": tool.description,
            "args_schema": getattr(tool, "args_schema", None),
            "return_type": getattr(tool, "return_direct", False),
            "category": category
        }
        
        # 更新分类信息
        if category:
            if category not in self._tool_categories:
                self._tool_categories[category] = []
            self._tool_categories[category].append(tool.name)
        
        # MCP工具直接注册，不再需要转换为@task
        
        # 注册到系统能力注册表
        self._register_to_capability_registry(tool, category)
        
        logger.info(f"工具 '{tool.name}' 已注册到工具注册表 (分类: {category or '默认'})")
    

    
    def _infer_capability_type(self, tool: BaseTool, category: Optional[str] = None) -> CapabilityType:
        """智能推断工具的能力类型"""
        tool_name = tool.name.lower()
        tool_desc = tool.description.lower() if tool.description else ""
        category_lower = category.lower() if category else ""
        
        # 分析类工具
        analysis_keywords = ["analyze", "analysis", "calculate", "compute", "classify", "identify", "detect", "trend", "maturity"]
        if any(keyword in tool_name for keyword in analysis_keywords) or any(keyword in tool_desc for keyword in analysis_keywords):
            return CapabilityType.ANALYSIS
        
        # 可视化类工具
        visualization_keywords = ["plot", "chart", "diagram", "graph", "visualize", "draw", "generate_image", "bernard", "whiticar"]
        if any(keyword in tool_name for keyword in visualization_keywords) or any(keyword in tool_desc for keyword in visualization_keywords):
            return CapabilityType.VISUALIZATION
            
        # 数据处理类工具
        data_keywords = ["process", "load", "parse", "extract", "transform", "validate", "clean", "prepare"]
        if any(keyword in tool_name for keyword in data_keywords) or any(keyword in tool_desc for keyword in data_keywords) or "data" in category_lower:
            return CapabilityType.DATA_PROCESSING
        
        # 根据分类推断
        if category_lower:
            if "analysis" in category_lower:
                return CapabilityType.ANALYSIS
            elif "visualization" in category_lower or "plot" in category_lower:
                return CapabilityType.VISUALIZATION
            elif "data" in category_lower:
                return CapabilityType.DATA_PROCESSING
        
        # 默认为工具类型
        return CapabilityType.TOOL
    
    def _register_to_capability_registry(self, tool: BaseTool, category: Optional[str] = None):
        """将工具注册到系统能力注册表"""
        # 智能推断能力类型
        capability_type = self._infer_capability_type(tool, category)
        
        # 创建系统能力
        capability = SystemCapability(
            name=tool.name,
            type=capability_type,
            description=tool.description,
            parameters=getattr(tool, "args_schema", {}) if hasattr(tool, "args_schema") else {},
            metadata={
                "category": category or "default",
                "is_tool": True,
                "task_name": f"task_{tool.name}"
            }
        )
        
        # 注册到系统能力注册表
        register_capability(capability)
    
    def register_function_as_tool(
        self, 
        func: Callable, 
        name: Optional[str] = None, 
        description: Optional[str] = None,
        category: Optional[str] = None,
        return_direct: bool = False,
        use_structured_tool: bool = False
    ) -> BaseTool:
        """将函数注册为工具
        
        Args:
            func: 要注册的函数
            name: 工具名称，默认使用函数名
            description: 工具描述，默认使用函数docstring
            category: 工具分类，可选
            return_direct: 是否直接返回结果而不经过代理
            use_structured_tool: 是否强制使用StructuredTool，即使是单参数函数
            
        Returns:
            注册的工具实例
        """
        # 提取函数信息
        func_name = name or func.__name__
        func_doc = description or inspect.getdoc(func) or ""
        
        # 检查函数参数，如果有多个参数则使用StructuredTool
        sig = inspect.signature(func)
        if len(sig.parameters) > 1 or use_structured_tool:
            # 使用StructuredTool处理多参数函数或当强制使用StructuredTool时
            logger.info(f"为函数 {func_name} 创建StructuredTool")
            tool = StructuredTool.from_function(
                func=func,
                name=func_name,
                description=func_doc,
                return_direct=return_direct
            )
        else:
            # 单参数函数使用普通Tool
            logger.info(f"为函数 {func_name} 创建普通Tool")
            tool = LangchainTool.from_function(
                func=func,
                name=func_name,
                description=func_doc,
                return_direct=return_direct
            )
        
        # 注册工具
        self.register_tool(tool, category)
        
        return tool
    
    def register_with_decorator(
        self, 
        name: Optional[str] = None, 
        description: Optional[str] = None,
        category: Optional[str] = None,
        return_direct: bool = False,
        use_structured_tool: bool = False
    ) -> Callable:
        """工具注册装饰器
        
        用法:
        @registry.register_with_decorator(category="file")
        def read_file(file_path: str) -> str:
            '''读取文件内容'''
            with open(file_path, "r") as f:
                return f.read()
        
        Args:
            name: 工具名称，默认使用函数名
            description: 工具描述，默认使用函数docstring
            category: 工具分类，可选
            return_direct: 是否直接返回结果而不经过代理
            use_structured_tool: 是否强制使用StructuredTool，即使是单参数函数
            
        Returns:
            装饰器函数
        """
        def decorator(func):
            self.register_function_as_tool(
                func, 
                name=name, 
                description=description,
                category=category,
                return_direct=return_direct,
                use_structured_tool=use_structured_tool
            )
            
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            
            return wrapper
        
        return decorator
    
    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """获取工具实例
        
        Args:
            tool_name: 工具名称
            
        Returns:
            工具实例，如果不存在则返回None
        """
        return self._tools.get(tool_name)
    
    def get_all_tools(self) -> List[BaseTool]:
        """获取所有工具列表
        
        Returns:
            所有注册的工具列表
        """
        return list(self._tools.values())
    
    def get_tools_by_category(self, category: str) -> List[BaseTool]:
        """获取指定分类的工具
        
        Args:
            category: 工具分类
            
        Returns:
            该分类下的工具列表
        """
        tool_names = self._tool_categories.get(category, [])
        return [self._tools[name] for name in tool_names if name in self._tools]
    
    def get_tool_metadata(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """获取工具元数据
        
        Args:
            tool_name: 工具名称
            
        Returns:
            工具元数据，如果不存在则返回None
        """
        return self._tool_metadata.get(tool_name)
    
    def get_all_categories(self) -> List[str]:
        """获取所有工具分类
        
        Returns:
            所有工具分类列表
        """
        return list(self._tool_categories.keys())
    
    def search_tools(self, query: str) -> List[BaseTool]:
        """搜索工具
        
        Args:
            query: 搜索关键词
            
        Returns:
            匹配的工具列表
        """
        query = query.lower()
        results = []
        
        for name, tool in self._tools.items():
            # 在名称和描述中搜索关键词
            if query in name.lower() or query in tool.description.lower():
                results.append(tool)
        
        return results
    
    def get_tools_as_langchain_format(self) -> List[Dict[str, Any]]:
        """获取适合LangChain/OpenAI格式的工具定义
        
        Returns:
            工具定义列表，适合LangChain/OpenAI使用
        """
        tools_data = []
        
        for name, tool in self._tools.items():
            # 基本工具信息
            tool_data = {
                "name": tool.name,
                "description": tool.description,
            }
            
            # 添加参数模式
            if hasattr(tool, "args_schema") and tool.args_schema:
                if hasattr(tool.args_schema, "schema") and callable(getattr(tool.args_schema, "schema", None)):
                    schema = tool.args_schema.schema()
                    tool_data["parameters"] = schema.get("properties", {})
                    tool_data["required"] = schema.get("required", [])
            
            tools_data.append(tool_data)
        
        return tools_data
    
    def unregister_tool(self, tool_name: str) -> bool:
        """注销工具
        
        Args:
            tool_name: 要注销的工具名称
            
        Returns:
            是否成功注销
        """
        if tool_name not in self._tools:
            logger.warning(f"工具 '{tool_name}' 不存在，无法注销")
            return False
        
        # 获取工具分类
        category = self._tool_metadata[tool_name].get("category")
        
        # 从分类中移除
        if category and category in self._tool_categories:
            if tool_name in self._tool_categories[category]:
                self._tool_categories[category].remove(tool_name)
            
            # 如果分类为空，也移除分类
            if not self._tool_categories[category]:
                del self._tool_categories[category]
        
        # 删除工具和元数据
        del self._tools[tool_name]
        del self._tool_metadata[tool_name]
        
        logger.info(f"工具 '{tool_name}' 已注销")
        return True
    
    def clear_all_tools(self) -> None:
        """清除所有注册的工具"""
        self._tools.clear()
        self._tool_metadata.clear()
        self._tool_categories.clear()
        self._mcp_tools.clear()
        logger.info("所有工具已清除")
    
    # ==================== MCP 相关方法 ====================
    
    def enable_mcp(self) -> None:
        """启用MCP支持（简化版，避免异步问题）"""
        try:
            from app.tools.enhanced_mcp_client import MCPServerInstance
            
            # 直接启用MCP模式，暂时跳过复杂的异步初始化
            self._mcp_enabled = True
            
            # 标记所有现有工具都支持MCP
            for tool_name, tool in self._tools.items():
                self._mcp_tools[tool_name] = tool
            
            logger.info(f"MCP已启用，当前可用工具数: {len(self._tools)}")
            
        except ImportError:
            logger.warning("MCP增强客户端不可用，跳过MCP启用")
        except Exception as e:
            logger.error(f"启用MCP失败: {e}")
    
    def disable_mcp(self) -> None:
        """禁用MCP支持"""
        # 从主工具列表中移除MCP工具
        mcp_tool_names = list(self._mcp_tools.keys())
        for tool_name in mcp_tool_names:
            if tool_name in self._tools:
                del self._tools[tool_name]
            if tool_name in self._tool_metadata:
                del self._tool_metadata[tool_name]
        
        # 清除MCP工具
        self._mcp_tools.clear()
        self._mcp_enabled = False
        self._mcp_client = None
        
        logger.info("MCP已禁用")
    
    def is_mcp_enabled(self) -> bool:
        """检查MCP是否已启用"""
        return self._mcp_enabled
    
    def get_mcp_tools(self) -> List[BaseTool]:
        """获取所有MCP工具"""
        return list(self._mcp_tools.values())
    
    def get_mcp_tool(self, tool_name: str) -> Optional[BaseTool]:
        """获取特定的MCP工具"""
        return self._mcp_tools.get(tool_name)
    
    def invoke_mcp_tool(self, tool_name: str, **kwargs) -> Any:
        """调用MCP工具"""
        if not self._mcp_enabled:
            raise RuntimeError("MCP未启用")
        
        if tool_name not in self._mcp_tools:
            raise ValueError(f"MCP工具 {tool_name} 未找到")
        
        tool = self._mcp_tools[tool_name]
        
        try:
            # 优先使用异步调用
            if hasattr(tool, '_arun'):
                # 如果在异步上下文中，直接调用
                try:
                    loop = asyncio.get_running_loop()
                    # 在现有事件循环中创建任务
                    return asyncio.create_task(tool._arun(**kwargs))
                except RuntimeError:
                    # 没有运行的事件循环，同步调用
                    return tool._run(**kwargs)
            else:
                return tool._run(**kwargs)
                
        except Exception as e:
            logger.error(f"调用MCP工具 {tool_name} 失败: {e}")
            raise
    
    async def ainvoke_mcp_tool(self, tool_name: str, **kwargs) -> Any:
        """异步调用MCP工具"""
        if not self._mcp_enabled:
            raise RuntimeError("MCP未启用")
        
        if self._mcp_client:
            return await self._mcp_client.invoke_tool(tool_name, **kwargs)
        else:
            raise RuntimeError("MCP客户端未初始化")
    
    def migrate_to_mcp(self) -> Dict[str, Any]:
        """将现有工具迁移到MCP"""
        if not self._mcp_enabled:
            self.enable_mcp()
        
        migration_result = {
            "total_tools": len(self._tools),
            "mcp_tools": len(self._mcp_tools),
            "migration_successful": True,
            "errors": []
        }
        
        # 迁移统计
        logger.info(f"工具迁移完成：总工具数 {migration_result['total_tools']}, "
                   f"MCP工具数 {migration_result['mcp_tools']}")
        
        return migration_result
    
    def get_tool_source(self, tool_name: str) -> str:
        """获取工具来源（legacy, mcp, unknown）"""
        if tool_name in self._mcp_tools:
            return "mcp"
        elif tool_name in self._tools:
            # 检查元数据中是否标记为MCP工具
            metadata = self._tool_metadata.get(tool_name, {})
            if metadata.get("category") == "mcp":
                return "mcp"
            else:
                return "legacy"
        else:
            return "unknown"

# 创建全局工具注册中心实例
registry = ToolRegistry()

# 装饰器简写，方便直接导入使用
def register_tool(
    name: Optional[str] = None, 
    description: Optional[str] = None,
    category: Optional[str] = None,
    return_direct: bool = False,
    use_structured_tool: bool = False
) -> Callable:
    """注册工具的装饰器
    
    用法:
    @register_tool(category="file")
    def read_file(file_path: str) -> str:
        '''读取文件内容'''
        with open(file_path, "r") as f:
            return f.read()
    
    Args:
        name: 工具名称，默认使用函数名
        description: 工具描述，默认使用函数docstring
        category: 工具分类，可选
        return_direct: 是否直接返回结果而不经过代理
        use_structured_tool: 是否强制使用StructuredTool，即使是单参数函数
    """
    return registry.register_with_decorator(
        name=name, 
        description=description,
        category=category,
        return_direct=return_direct,
        use_structured_tool=use_structured_tool
    )

def get_all_tools() -> List[BaseTool]:
    """获取所有注册的工具"""
    return registry.get_all_tools()

def get_tool(name: str) -> Optional[BaseTool]:
    """根据名称获取工具"""
    return registry.get_tool(name)

def get_tools_by_category(category: str) -> List[BaseTool]:
    """获取指定分类的所有工具"""
    return registry.get_tools_by_category(category)

def get_tools_for_llm() -> List[Dict[str, Any]]:
    """获取适合LLM使用的工具定义"""
    return registry.get_tools_as_langchain_format()

# 添加task注册和管理功能
class TaskRegistry:
    """任务注册中心，管理所有可用的task"""
    
    def __init__(self):
        """初始化任务注册中心"""
        # 存储所有注册的任务
        self._tasks: Dict[str, Callable] = {}
        # 存储任务的元数据
        self._task_metadata: Dict[str, Dict[str, Any]] = {}
        
        logger.info("任务注册中心初始化完成")
    
    def register_task(self, task_func: Callable, name: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> None:
        """注册任务到注册中心
        
        Args:
            task_func: 要注册的任务函数
            name: 任务名称，默认使用函数名
            metadata: 任务元数据，可选
        """
        task_name = name or task_func.__name__
        
        # 检查任务名称是否已存在
        if task_name in self._tasks:
            logger.warning(f"任务 '{task_name}' 已存在，将被覆盖")
        
        # 存储任务实例
        self._tasks[task_name] = task_func
        
        # 保存任务元数据
        self._task_metadata[task_name] = metadata or {
            "name": task_name,
            "description": inspect.getdoc(task_func) or "",
            "module": task_func.__module__
        }
        
        logger.info(f"任务 '{task_name}' 已注册")
    
    def register_with_decorator(self, name: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Callable:
        """任务注册装饰器
        
        用法:
        @task_registry.register_with_decorator(name="process_data")
        def process_data_task(data: Dict[str, Any]) -> Dict[str, Any]:
            '''处理数据任务'''
            # 处理逻辑
            return processed_data
        
        Args:
            name: 任务名称，默认使用函数名
            metadata: 任务元数据，可选
            
        Returns:
            装饰器函数
        """
        def decorator(func):
            self.register_task(func, name=name, metadata=metadata)
            
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            
            return wrapper
        
        return decorator
    
    def get_task(self, task_name: str) -> Optional[Callable]:
        """获取任务函数
        
        Args:
            task_name: 任务名称
            
        Returns:
            任务函数，如果不存在则返回None
        """
        return self._tasks.get(task_name)
    
    def get_all_tasks(self) -> Dict[str, Callable]:
        """获取所有任务
        
        Returns:
            所有注册的任务字典 {任务名: 任务函数}
        """
        return self._tasks
    
    def get_task_metadata(self, task_name: str) -> Optional[Dict[str, Any]]:
        """获取任务元数据
        
        Args:
            task_name: 任务名称
            
        Returns:
            任务元数据，如果不存在则返回None
        """
        return self._task_metadata.get(task_name)
    
    def unregister_task(self, task_name: str) -> bool:
        """取消注册任务
        
        Args:
            task_name: 要取消注册的任务名称
            
        Returns:
            是否成功取消注册
        """
        if task_name in self._tasks:
            del self._tasks[task_name]
            if task_name in self._task_metadata:
                del self._task_metadata[task_name]
            logger.info(f"任务 '{task_name}' 已取消注册")
            return True
        else:
            logger.warning(f"任务 '{task_name}' 不存在，无法取消注册")
            return False
    
    def clear_all_tasks(self) -> None:
        """清除所有注册的任务"""
        self._tasks.clear()
        self._task_metadata.clear()
        logger.info("所有任务已清除")

# 创建全局任务注册中心实例
task_registry = TaskRegistry()

# 以下是公共API函数

def get_task_by_name(task_name: str) -> Optional[Callable]:
    """根据名称获取任务
    
    Args:
        task_name: 任务名称
        
    Returns:
        任务函数，如果不存在则返回None
    """
    return task_registry.get_task(task_name)

def apply_langgraph_decorator(func: Callable) -> Callable:
    """应用LangGraph装饰器到任务函数
    
    Args:
        func: 要应用装饰器的函数
        
    Returns:
        应用了装饰器的函数
    """
    # 这里可以添加LangGraph特定的装饰器逻辑
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            logger.info(f"执行LangGraph任务: {func.__name__}")
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            logger.error(f"执行LangGraph任务 {func.__name__} 失败: {str(e)}")
            raise
    
    return wrapper

# 导入并注册所有工具
def register_all_tools(enable_mcp: bool = True):
    """注册所有工具
    
    Args:
        enable_mcp: 是否启用MCP支持
    """
    try:
        # 工具模块会在导入时自动注册（通过@register_tool装饰器）
        logger.info("开始导入工具模块...")
        
        # 导入各个工具模块（导入时会自动触发注册）
        try:
            import app.tools.file_tools
            logger.info("file_tools模块导入成功")
        except Exception as e:
            logger.warning(f"file_tools模块导入失败: {str(e)}")
            
        try:
            import app.tools.logging
            logger.info("logging模块导入成功")
        except Exception as e:
            logger.warning(f"logging模块导入失败: {str(e)}")
            
        try:
            import app.tools.knowledge_tools
            logger.info("knowledge_tools模块导入成功")
        except Exception as e:
            logger.warning(f"knowledge_tools模块导入失败: {str(e)}")
            
        try:
            import app.tools.meanderpy
            logger.info("meanderpy模块导入成功")
        except Exception as e:
            logger.warning(f"meanderpy模块导入失败: {str(e)}")
            
        try:
            import app.tools.rock_core
            logger.info("rock_core模块导入成功")
        except Exception as e:
            logger.warning(f"rock_core模块导入失败: {str(e)}")
            
        try:
            import app.tools.reservior
            logger.info("reservior模块导入成功")
        except Exception as e:
            logger.warning(f"reservior模块导入失败: {str(e)}")
        
        logger.info(f"成功注册 {len(registry._tools)} 个传统工具")
        
        # 不再需要注册传统的@task任务
        
        # 启用MCP支持
        if enable_mcp:
            try:
                registry.enable_mcp()
                logger.info(f"MCP已启用，总工具数: {len(registry.get_all_tools())}")
            except Exception as e:
                logger.warning(f"启用MCP失败: {e}")
        
        # 记录工具分类情况
        for category in registry.get_all_categories():
            tools = registry.get_tools_by_category(category)
            logger.info(f"分类 '{category}': {len(tools)} 个工具")
            
    except Exception as e:
        logger.error(f"注册工具时出错: {str(e)}")

# 自动注册所有工具
register_all_tools() 

def get_tool_registry() -> ToolRegistry:
    """获取全局工具注册表实例
    
    Returns:
        ToolRegistry: 全局工具注册表实例
    """
    return registry

def get_task_registry() -> TaskRegistry:
    """获取全局任务注册表实例
    
    Returns:
        TaskRegistry: 全局任务注册表实例
    """
    return task_registry


# ==================== MCP相关便利函数 ====================

def enable_mcp_tools() -> bool:
    """启用MCP工具支持
    
    Returns:
        bool: 是否成功启用
    """
    try:
        registry.enable_mcp()
        return True
    except Exception as e:
        logger.error(f"启用MCP工具失败: {e}")
        return False


def disable_mcp_tools() -> bool:
    """禁用MCP工具支持
    
    Returns:
        bool: 是否成功禁用
    """
    try:
        registry.disable_mcp()
        return True
    except Exception as e:
        logger.error(f"禁用MCP工具失败: {e}")
        return False


def is_mcp_enabled() -> bool:
    """检查MCP是否已启用"""
    return registry.is_mcp_enabled()


def get_mcp_tools() -> List[BaseTool]:
    """获取所有MCP工具"""
    return registry.get_mcp_tools()


def get_mixed_tools() -> List[BaseTool]:
    """获取混合工具列表（传统工具 + MCP工具）"""
    all_tools = registry.get_all_tools()
    if registry.is_mcp_enabled():
        # 如果MCP已启用，工具列表中已经包含了MCP工具
        return all_tools
    else:
        # 如果MCP未启用，只返回传统工具
        return [tool for tool in all_tools if registry.get_tool_source(tool.name) != "mcp"]


def migrate_tools_to_mcp() -> Dict[str, Any]:
    """将工具迁移到MCP协议
    
    Returns:
        Dict[str, Any]: 迁移结果统计
    """
    return registry.migrate_to_mcp()


def get_tool_statistics() -> Dict[str, Any]:
    """获取工具统计信息
    
    Returns:
        Dict[str, Any]: 工具统计信息
    """
    stats = {
        "total_tools": len(registry.get_all_tools()),
        "legacy_tools": 0,
        "mcp_tools": len(registry.get_mcp_tools()),
        "mcp_enabled": registry.is_mcp_enabled(),
        "categories": {}
    }
    
    # 统计传统工具
    for tool_name in registry._tools.keys():
        if registry.get_tool_source(tool_name) == "legacy":
            stats["legacy_tools"] += 1
    
    # 统计分类
    for category in registry.get_all_categories():
        stats["categories"][category] = len(registry.get_tools_by_category(category))
    
    return stats


def invoke_any_tool(tool_name: str, prefer_mcp: bool = True, **kwargs) -> Any:
    """调用任意工具（优先使用MCP）
    
    Args:
        tool_name: 工具名称
        prefer_mcp: 是否优先使用MCP工具
        **kwargs: 工具参数
        
    Returns:
        Any: 工具执行结果
    """
    # 检查工具来源
    tool_source = registry.get_tool_source(tool_name)
    
    if prefer_mcp and tool_source == "mcp" and registry.is_mcp_enabled():
        # 使用MCP调用
        return registry.invoke_mcp_tool(tool_name, **kwargs)
    else:
        # 使用传统方式调用
        tool = registry.get_tool(tool_name)
        if tool:
            return tool._run(**kwargs)
        else:
            raise ValueError(f"工具 {tool_name} 未找到")


async def ainvoke_any_tool(tool_name: str, prefer_mcp: bool = True, **kwargs) -> Any:
    """异步调用任意工具（优先使用MCP）
    
    Args:
        tool_name: 工具名称
        prefer_mcp: 是否优先使用MCP工具
        **kwargs: 工具参数
        
    Returns:
        Any: 工具执行结果
    """
    # 检查工具来源
    tool_source = registry.get_tool_source(tool_name)
    
    if prefer_mcp and tool_source == "mcp" and registry.is_mcp_enabled():
        # 使用MCP异步调用
        return await registry.ainvoke_mcp_tool(tool_name, **kwargs)
    else:
        # 使用传统方式调用
        tool = registry.get_tool(tool_name)
        if tool:
            if hasattr(tool, '_arun'):
                return await tool._arun(**kwargs)
            else:
                return tool._run(**kwargs)
        else:
            raise ValueError(f"工具 {tool_name} 未找到") 