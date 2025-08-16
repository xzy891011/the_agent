"""
增强的MCP客户端管理器

集成langchain-mcp-adapters库，提供统一的工具调用接口，
支持现有@task工具的平滑迁移到MCP协议。
"""

import asyncio
import logging
import json
from typing import Dict, Any, List, Optional, Union, Callable
from dataclasses import dataclass
import subprocess
import tempfile
import os
from pathlib import Path

# LangChain MCP适配器
try:
    from langchain_mcp_adapters.client import MultiServerMCPClient
    from langchain_mcp_adapters.tools import load_mcp_tools
    MCP_ADAPTERS_AVAILABLE = True
except ImportError:
    MultiServerMCPClient = None
    load_mcp_tools = None
    MCP_ADAPTERS_AVAILABLE = False
    
from langchain_core.tools import BaseTool
from app.tools.mcp_tool_server import setup_mcp_servers, get_isotope_mcp_server, get_legacy_task_mcp_server

logger = logging.getLogger(__name__)


@dataclass
class MCPServerInstance:
    """MCP服务器实例信息"""
    name: str
    server_type: str  # "internal", "external", "subprocess"
    config: Dict[str, Any]
    process: Optional[subprocess.Popen] = None
    tools: List[BaseTool] = None
    status: str = "stopped"  # "running", "stopped", "error"
    
    def __post_init__(self):
        if self.tools is None:
            self.tools = []


class EnhancedMCPClient:
    """增强的MCP客户端管理器"""
    
    def __init__(self):
        self.servers: Dict[str, MCPServerInstance] = {}
        self.mcp_client: Optional[Any] = None
        self.tools: List[BaseTool] = []
        self._internal_servers = {}
        
        # 检查依赖
        if not MCP_ADAPTERS_AVAILABLE:
            logger.warning("langchain-mcp-adapters 未安装，部分MCP功能不可用")
    
    async def initialize(self) -> None:
        """初始化MCP客户端"""
        try:
            # 设置内部MCP服务器
            await self._setup_internal_servers()
            
            # 初始化多服务器MCP客户端（用于外部服务器）
            if MCP_ADAPTERS_AVAILABLE:
                server_configs = self._build_server_configs()
                if server_configs:
                    self.mcp_client = MultiServerMCPClient(server_configs)
            
            # 总是加载工具（无论是否有外部服务器）
            await self._load_tools_from_servers()
            
            logger.info("MCP客户端初始化完成")
            
        except Exception as e:
            logger.error(f"初始化MCP客户端失败: {e}")
            raise
    
    async def _setup_internal_servers(self) -> None:
        """设置统一的内部MCP服务器"""
        try:
            # 设置统一的工具服务器
            self._internal_servers = setup_mcp_servers()
            
            # 注册内部服务器
            for server_name, server_instance in self._internal_servers.items():
                self.servers[server_name] = MCPServerInstance(
                    name=server_name,
                    server_type="internal",
                    config={
                        "transport": "internal",
                        "server_instance": server_instance
                    },
                    status="running"
                )
            
            logger.info(f"设置了统一的内部MCP服务器: {list(self._internal_servers.keys())}")
            
        except Exception as e:
            logger.error(f"设置内部MCP服务器失败: {e}")
            raise
    
    def _build_server_configs(self) -> Dict[str, Any]:
        """构建MCP服务器配置"""
        configs = {}
        
        for server_name, server_info in self.servers.items():
            if server_info.server_type == "subprocess":
                # 子进程服务器配置
                configs[server_name] = {
                    "command": server_info.config.get("command", "python"),
                    "args": server_info.config.get("args", []),
                    "transport": "stdio"
                }
            elif server_info.server_type == "external":
                # 外部HTTP服务器配置
                configs[server_name] = {
                    "url": server_info.config.get("url"),
                    "transport": "streamable_http"
                }
        
        return configs
    
    async def _load_tools_from_servers(self) -> None:
        """从MCP服务器加载工具"""
        logger.info(f"开始加载MCP工具，mcp_client存在: {self.mcp_client is not None}")
        
        if not self.mcp_client:
            logger.info("没有外部MCP客户端，只加载内部工具")
            # 直接加载内部工具
            await self._load_internal_tools()
            logger.info(f"仅加载内部工具，总计: {len(self.tools)} 个MCP工具")
            return
            
        try:
            # 从外部服务器获取工具
            external_tools = await self.mcp_client.get_tools()
            self.tools.extend(external_tools)
            logger.info(f"加载了 {len(external_tools)} 个外部MCP工具")
            
            # 从内部服务器获取工具
            await self._load_internal_tools()
            
            logger.info(f"总共加载了 {len(self.tools)} 个MCP工具")
            
        except Exception as e:
            logger.error(f"加载MCP工具失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
    
    async def _load_internal_tools(self) -> None:
        """从内部服务器加载工具"""
        for server_name, server_instance in self._internal_servers.items():
            try:
                # 为内部工具创建BaseTool包装器
                tools_info = server_instance.get_tool_info()
                logger.info(f"从服务器 {server_name} 获取到 {len(tools_info)} 个工具信息")
                
                for tool_name, tool_info in tools_info.items():
                    # 创建工具包装器
                    tool = self._create_internal_tool_wrapper(
                        server_name, tool_name, tool_info, server_instance
                    )
                    self.tools.append(tool)
                    
                    # 更新服务器实例的工具列表
                    server_info = self.servers[server_name]
                    server_info.tools.append(tool)
                    
                logger.info(f"从服务器 {server_name} 成功加载 {len(tools_info)} 个工具")
                    
            except Exception as e:
                logger.error(f"加载内部服务器 {server_name} 的工具失败: {e}")
                import traceback
                logger.error(f"详细错误: {traceback.format_exc()}")
    
    def _create_internal_tool_wrapper(self, server_name: str, tool_name: str, 
                                    tool_info: Dict[str, Any], server_instance) -> BaseTool:
        """为内部工具创建BaseTool包装器"""
        
        # 使用tool装饰器创建工具，避免Pydantic字段验证问题
        from langchain_core.tools import tool
        
        @tool
        def internal_mcp_tool(**kwargs) -> Any:
            """Internal MCP tool wrapper.
            
            Executes the underlying MCP tool functionality.
            """
            # 同步调用内部工具
            if hasattr(server_instance, 'tools') and tool_name in server_instance.tools:
                wrapper = server_instance.tools[tool_name]
                # 运行异步方法
                try:
                    import asyncio
                    loop = asyncio.get_event_loop()
                    result = loop.run_until_complete(wrapper.execute(**kwargs))
                    
                    if result.success:
                        return result.result
                    else:
                        raise RuntimeError(result.error)
                except RuntimeError as e:
                    if "There is no current event loop" in str(e):
                        # 创建新的事件循环
                        import asyncio
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        result = loop.run_until_complete(wrapper.execute(**kwargs))
                        
                        if result.success:
                            return result.result
                        else:
                            raise RuntimeError(result.error)
                    else:
                        raise e
            else:
                raise ValueError(f"工具 {tool_name} 在服务器中未找到")
        
        # 设置工具名称和描述
        internal_mcp_tool.name = f"{server_name}_{tool_name}"
        internal_mcp_tool.description = tool_info.get('description', f"Internal MCP tool: {tool_name}")
        return internal_mcp_tool
    
    def register_subprocess_server(self, name: str, command: str, args: List[str], 
                                 auto_start: bool = True) -> None:
        """注册子进程MCP服务器"""
        config = {
            "command": command,
            "args": args,
            "transport": "stdio"
        }
        
        server_info = MCPServerInstance(
            name=name,
            server_type="subprocess",
            config=config
        )
        
        self.servers[name] = server_info
        
        if auto_start:
            self._start_subprocess_server(name)
        
        logger.info(f"注册了子进程MCP服务器: {name}")
    
    def register_external_server(self, name: str, url: str, 
                                auth_token: Optional[str] = None) -> None:
        """注册外部HTTP MCP服务器"""
        config = {
            "url": url,
            "transport": "streamable_http"
        }
        
        if auth_token:
            config["auth_token"] = auth_token
        
        server_info = MCPServerInstance(
            name=name,
            server_type="external", 
            config=config,
            status="configured"
        )
        
        self.servers[name] = server_info
        logger.info(f"注册了外部MCP服务器: {name} -> {url}")
    
    def _start_subprocess_server(self, server_name: str) -> None:
        """启动子进程MCP服务器"""
        if server_name not in self.servers:
            raise ValueError(f"服务器 {server_name} 未注册")
        
        server_info = self.servers[server_name]
        if server_info.server_type != "subprocess":
            raise ValueError(f"服务器 {server_name} 不是子进程类型")
        
        try:
            config = server_info.config
            cmd = [config["command"]] + config["args"]
            
            # 启动子进程
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            server_info.process = process
            server_info.status = "running"
            
            logger.info(f"启动了子进程MCP服务器: {server_name}")
            
        except Exception as e:
            server_info.status = "error"
            logger.error(f"启动子进程MCP服务器 {server_name} 失败: {e}")
            raise
    
    def get_all_tools(self) -> List[BaseTool]:
        """获取所有可用的MCP工具"""
        return self.tools.copy()
    
    def get_tools_by_server(self, server_name: str) -> List[BaseTool]:
        """获取特定服务器的工具"""
        if server_name in self.servers:
            return self.servers[server_name].tools.copy()
        return []
    
    def get_tool_by_name(self, tool_name: str) -> Optional[BaseTool]:
        """根据名称获取工具"""
        for tool in self.tools:
            if tool.name == tool_name:
                return tool
        return None
    
    async def invoke_tool(self, tool_name: str, **kwargs) -> Any:
        """调用MCP工具"""
        tool = self.get_tool_by_name(tool_name)
        if not tool:
            raise ValueError(f"工具 {tool_name} 未找到")
        
        try:
            # 优先使用异步调用
            if hasattr(tool, '_arun'):
                return await tool._arun(**kwargs)
            else:
                return tool._run(**kwargs)
                
        except Exception as e:
            logger.error(f"调用工具 {tool_name} 失败: {e}")
            raise
    
    def get_server_status(self) -> Dict[str, str]:
        """获取所有服务器状态"""
        return {name: info.status for name, info in self.servers.items()}
    
    async def shutdown(self) -> None:
        """关闭MCP客户端和所有服务器"""
        try:
            # 关闭外部客户端
            if self.mcp_client:
                # langchain-mcp-adapters 可能需要特定的关闭方法
                # 具体实现取决于库的版本
                pass
            
            # 停止子进程服务器
            for server_info in self.servers.values():
                if server_info.process:
                    server_info.process.terminate()
                    server_info.process.wait()
                    server_info.status = "stopped"
            
            logger.info("MCP客户端已关闭")
            
        except Exception as e:
            logger.error(f"关闭MCP客户端失败: {e}")


# 全局MCP客户端实例
_enhanced_mcp_client: Optional[EnhancedMCPClient] = None


async def get_enhanced_mcp_client() -> EnhancedMCPClient:
    """获取增强MCP客户端单例"""
    global _enhanced_mcp_client
    if _enhanced_mcp_client is None:
        _enhanced_mcp_client = EnhancedMCPClient()
        await _enhanced_mcp_client.initialize()
    return _enhanced_mcp_client


def create_mcp_tools_from_existing() -> List[BaseTool]:
    """从现有工具创建MCP工具（同步接口）"""
    async def _create():
        client = await get_enhanced_mcp_client()
        return client.get_all_tools()
    
    try:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(_create())
    except RuntimeError:
        # 如果没有事件循环，创建一个新的
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_create())
        finally:
            loop.close()


# 向后兼容的接口
def setup_mcp_tool_integration():
    """设置MCP工具集成（向后兼容接口）"""
    try:
        tools = create_mcp_tools_from_existing()
        logger.info(f"MCP工具集成设置完成，创建了 {len(tools)} 个工具")
        return tools
    except Exception as e:
        logger.error(f"设置MCP工具集成失败: {e}")
        return []


if __name__ == "__main__":
    """测试MCP客户端"""
    import asyncio
    
    async def test_mcp_client():
        try:
            client = await get_enhanced_mcp_client()
            
            # 测试获取工具
            tools = client.get_all_tools()
            print(f"发现 {len(tools)} 个MCP工具:")
            
            for tool in tools:
                print(f"- {tool.name}: {tool.description}")
            
            # 测试调用工具（如果有工具的话）
            if tools:
                first_tool = tools[0]
                print(f"\n测试调用工具: {first_tool.name}")
                # 这里需要根据具体工具提供适当的参数
                
        except Exception as e:
            print(f"测试失败: {e}")
            import traceback
            traceback.print_exc()
    
    asyncio.run(test_mcp_client())
