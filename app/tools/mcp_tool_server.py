"""
MCP工具服务器 - 将现有@task工具包装为MCP服务器

该模块将现有的@task装饰器工具转换为标准的MCP协议工具，
提供标准化的工具调用接口。
"""

import asyncio
import logging
import json
import inspect
from typing import Dict, Any, List, Optional, Callable, Union
from dataclasses import dataclass, asdict
from datetime import datetime
import traceback

from mcp.server.fastmcp import FastMCP
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


@dataclass
class MCPToolResult:
    """MCP工具执行结果"""
    success: bool
    result: Any = None
    error: Optional[str] = None
    tool_name: str = ""
    execution_time: float = 0.0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class MCPToolWrapper:
    """MCP工具包装器，将LangChain工具转换为MCP工具"""
    
    def __init__(self, tool: BaseTool):
        self.tool = tool
        self.name = tool.name
        self.description = tool.description
        
    async def execute(self, **kwargs) -> MCPToolResult:
        """执行工具并返回MCP格式的结果"""
        start_time = datetime.now()
        
        try:
            # 执行工具
            if asyncio.iscoroutinefunction(self.tool._run):
                result = await self.tool._run(**kwargs)
            else:
                result = self.tool._run(**kwargs)
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return MCPToolResult(
                success=True,
                result=result,
                tool_name=self.name,
                execution_time=execution_time,
                metadata={
                    "tool_type": "langchain_tool",
                    "original_tool": self.tool.__class__.__name__
                }
            )
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            error_msg = f"工具执行失败: {str(e)}"
            logger.error(f"{self.name} 执行失败: {error_msg}\n{traceback.format_exc()}")
            
            return MCPToolResult(
                success=False,
                error=error_msg,
                tool_name=self.name,
                execution_time=execution_time,
                metadata={
                    "tool_type": "langchain_tool",
                    "original_tool": self.tool.__class__.__name__,
                    "error_type": type(e).__name__
                }
            )


class IsotopeToolsMCPServer:
    """天然气同位素工具MCP服务器"""
    
    def __init__(self, name: str = "IsotopeTools"):
        self.mcp_server = FastMCP(name)
        self.tools: Dict[str, MCPToolWrapper] = {}
        self._setup_server()
        
    def _setup_server(self):
        """设置MCP服务器的基础路由"""
        logger.info("初始化MCP服务器...")
        
    def register_tool(self, tool: BaseTool) -> None:
        """注册LangChain工具到MCP服务器"""
        wrapper = MCPToolWrapper(tool)
        self.tools[tool.name] = wrapper
        
        # 动态创建MCP工具函数
        self._create_mcp_tool_function(wrapper)
        
        logger.info(f"已注册MCP工具: {tool.name}")
    
    def _create_mcp_tool_function(self, wrapper: MCPToolWrapper):
        """为工具包装器创建MCP工具函数"""
        tool = wrapper.tool
        
        # 获取工具的参数模式
        if hasattr(tool, 'args_schema') and tool.args_schema:
            # 使用工具定义的参数模式
            args_schema = tool.args_schema
        else:
            # 尝试从函数签名推断参数
            args_schema = self._infer_args_schema(tool)
        
        # 创建MCP工具函数
        async def mcp_tool_func(**kwargs) -> str:
            """动态创建的MCP工具函数"""
            try:
                result = await wrapper.execute(**kwargs)
                
                if result.success:
                    # 返回JSON格式的结果
                    return json.dumps({
                        "success": True,
                        "result": result.result,
                        "tool_name": result.tool_name,
                        "execution_time": result.execution_time,
                        "metadata": result.metadata
                    }, ensure_ascii=False, indent=2)
                else:
                    return json.dumps({
                        "success": False,
                        "error": result.error,
                        "tool_name": result.tool_name,
                        "execution_time": result.execution_time,
                        "metadata": result.metadata
                    }, ensure_ascii=False, indent=2)
                    
            except Exception as e:
                error_msg = f"MCP工具调用失败: {str(e)}"
                logger.error(error_msg)
                return json.dumps({
                    "success": False,
                    "error": error_msg,
                    "tool_name": wrapper.name
                }, ensure_ascii=False, indent=2)
        
        # 设置函数名和文档
        mcp_tool_func.__name__ = tool.name
        mcp_tool_func.__doc__ = tool.description
        
        # 将函数注册到MCP服务器
        self.mcp_server.tool()(mcp_tool_func)
        
    def _infer_args_schema(self, tool: BaseTool) -> Optional[BaseModel]:
        """从工具推断参数模式"""
        try:
            if hasattr(tool, '_run'):
                sig = inspect.signature(tool._run)
                
                # 创建动态Pydantic模型
                fields = {}
                for name, param in sig.parameters.items():
                    if name in ('self', 'kwargs'):
                        continue
                        
                    # 确定字段类型
                    annotation = param.annotation if param.annotation != inspect.Parameter.empty else str
                    default = param.default if param.default != inspect.Parameter.empty else ...
                    
                    fields[name] = (annotation, default)
                
                if fields:
                    return type(f"{tool.name}Args", (BaseModel,), {"__annotations__": fields})
                    
        except Exception as e:
            logger.warning(f"推断工具参数模式失败 {tool.name}: {e}")
            
        return None
    
    def register_tools_from_registry(self, tool_registry) -> None:
        """从工具注册表批量注册工具"""
        try:
            tools = tool_registry.get_all_tools()
            logger.info(f"开始注册 {len(tools)} 个工具到MCP服务器...")
            
            for tool in tools:
                try:
                    self.register_tool(tool)
                except Exception as e:
                    logger.error(f"注册工具 {tool.name} 失败: {e}")
                    
            logger.info(f"成功注册 {len(self.tools)} 个MCP工具")
            
        except Exception as e:
            logger.error(f"批量注册工具失败: {e}")
    
    def get_tool_info(self) -> Dict[str, Any]:
        """获取所有工具信息"""
        logger.info(f"get_tool_info 调用，当前工具数: {len(self.tools)}")
        tools_info = {}
        for name, wrapper in self.tools.items():
            tools_info[name] = {
                "name": wrapper.name,
                "description": wrapper.description,
                "tool_type": "langchain_tool"
            }
        logger.info(f"get_tool_info 返回 {len(tools_info)} 个工具信息")
        return tools_info
    
    def run(self, transport: str = "stdio", **kwargs):
        """运行MCP服务器"""
        logger.info(f"启动MCP服务器，传输方式: {transport}")
        self.mcp_server.run(transport=transport, **kwargs)


class LegacyTaskMCPServer:
    """传统@task装饰器工具的MCP服务器"""
    
    def __init__(self, name: str = "LegacyTasks"):
        self.mcp_server = FastMCP(name)
        self.tasks: Dict[str, Callable] = {}
        self._setup_server()
        
    def _setup_server(self):
        """设置MCP服务器"""
        logger.info("初始化传统任务MCP服务器...")
    
    def register_task(self, task_name: str, task_func: Callable) -> None:
        """注册@task装饰的函数到MCP服务器"""
        self.tasks[task_name] = task_func
        
        # 创建MCP工具函数
        async def mcp_task_func(**kwargs) -> str:
            """动态创建的MCP任务函数"""
            try:
                start_time = datetime.now()
                
                # 执行任务
                if asyncio.iscoroutinefunction(task_func):
                    result = await task_func(**kwargs)
                else:
                    result = task_func(**kwargs)
                
                execution_time = (datetime.now() - start_time).total_seconds()
                
                return json.dumps({
                    "success": True,
                    "result": result,
                    "task_name": task_name,
                    "execution_time": execution_time,
                    "metadata": {
                        "task_type": "legacy_task"
                    }
                }, ensure_ascii=False, indent=2)
                
            except Exception as e:
                execution_time = (datetime.now() - start_time).total_seconds()
                error_msg = f"任务执行失败: {str(e)}"
                logger.error(f"{task_name} 执行失败: {error_msg}")
                
                return json.dumps({
                    "success": False,
                    "error": error_msg,
                    "task_name": task_name,
                    "execution_time": execution_time,
                    "metadata": {
                        "task_type": "legacy_task",
                        "error_type": type(e).__name__
                    }
                }, ensure_ascii=False, indent=2)
        
        # 设置函数属性
        mcp_task_func.__name__ = task_name
        mcp_task_func.__doc__ = getattr(task_func, '__doc__', f"Legacy task: {task_name}")
        
        # 注册到MCP服务器
        self.mcp_server.tool()(mcp_task_func)
        
        logger.info(f"已注册MCP任务: {task_name}")
    
    def register_tasks_from_registry(self, task_registry) -> None:
        """从任务注册表批量注册任务"""
        try:
            tasks = task_registry.get_all_tasks()
            logger.info(f"开始注册 {len(tasks)} 个任务到MCP服务器...")
            
            for task_name, task_func in tasks.items():
                try:
                    self.register_task(task_name, task_func)
                except Exception as e:
                    logger.error(f"注册任务 {task_name} 失败: {e}")
                    
            logger.info(f"成功注册 {len(self.tasks)} 个MCP任务")
            
        except Exception as e:
            logger.error(f"批量注册任务失败: {e}")
    
    def run(self, transport: str = "stdio", **kwargs):
        """运行MCP服务器"""
        logger.info(f"启动传统任务MCP服务器，传输方式: {transport}")
        self.mcp_server.run(transport=transport, **kwargs)


# 全局MCP服务器实例
_isotope_mcp_server: Optional[IsotopeToolsMCPServer] = None
_legacy_task_mcp_server: Optional[LegacyTaskMCPServer] = None


def get_isotope_mcp_server() -> IsotopeToolsMCPServer:
    """获取天然气同位素工具MCP服务器实例"""
    global _isotope_mcp_server
    if _isotope_mcp_server is None:
        _isotope_mcp_server = IsotopeToolsMCPServer()
    return _isotope_mcp_server


def get_legacy_task_mcp_server() -> LegacyTaskMCPServer:
    """获取传统任务MCP服务器实例"""
    global _legacy_task_mcp_server
    if _legacy_task_mcp_server is None:
        _legacy_task_mcp_server = LegacyTaskMCPServer()
    return _legacy_task_mcp_server


def setup_mcp_servers():
    """设置并启动统一MCP服务器"""
    try:
        # 导入注册表
        from app.tools.registry import get_tool_registry
        
        # 设置统一工具MCP服务器（不再需要两个分离的服务器）
        unified_server = get_isotope_mcp_server()
        tool_registry = get_tool_registry()
        unified_server.register_tools_from_registry(tool_registry)
        
        logger.info("统一MCP服务器设置完成")
        
        return {
            "unified_tools": unified_server
        }
        
    except Exception as e:
        logger.error(f"设置MCP服务器失败: {e}")
        raise


if __name__ == "__main__":
    """独立运行MCP服务器"""
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="运行MCP工具服务器")
    parser.add_argument("--server", choices=["tools", "tasks", "both"], default="both",
                       help="要运行的服务器类型")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio",
                       help="传输方式")
    parser.add_argument("--port", type=int, default=8000, help="HTTP服务器端口")
    
    args = parser.parse_args()
    
    if args.server in ["tools", "both"]:
        try:
            server = get_isotope_mcp_server()
            setup_mcp_servers()
            
            if args.transport == "stdio":
                server.run(transport="stdio")
            else:
                server.run(transport="streamable-http", port=args.port)
                
        except KeyboardInterrupt:
            logger.info("MCP服务器已停止")
        except Exception as e:
            logger.error(f"运行MCP服务器失败: {e}")
            sys.exit(1)
