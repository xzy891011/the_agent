"""
MCP (Model Context Protocol) 客户端管理器
统一管理与外部团队工具服务的连接和调用
"""

import logging
import json
import asyncio
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass
from enum import Enum
import httpx
import time

logger = logging.getLogger(__name__)


class MCPServerType(Enum):
    """MCP服务器类型"""
    HTTP = "http"
    WEBSOCKET = "websocket"
    GRPC = "grpc"


@dataclass
class MCPServerConfig:
    """MCP服务器配置"""
    name: str
    url: str
    server_type: MCPServerType = MCPServerType.HTTP
    auth_token: Optional[str] = None
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class MCPTool:
    """MCP工具定义"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    server_name: str
    endpoint: str
    method: str = "POST"
    timeout: Optional[int] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class MCPClientManager:
    """
    MCP客户端管理器
    
    负责管理与多个MCP服务器的连接，工具发现和调用
    """
    
    def __init__(self):
        self.servers: Dict[str, MCPServerConfig] = {}
        self.tools: Dict[str, MCPTool] = {}
        self.clients: Dict[str, httpx.AsyncClient] = {}
        self._tool_cache: Dict[str, List[MCPTool]] = {}
        
    def register_server(
        self, 
        config: MCPServerConfig,
        override: bool = False
    ) -> None:
        """
        注册MCP服务器
        
        Args:
            config: 服务器配置
            override: 是否覆盖已存在的服务器
        """
        if config.name in self.servers and not override:
            logger.warning(f"MCP服务器 {config.name} 已存在")
            return
        
        self.servers[config.name] = config
        
        # 创建HTTP客户端
        if config.server_type == MCPServerType.HTTP:
            headers = {}
            if config.auth_token:
                headers["Authorization"] = f"Bearer {config.auth_token}"
            
            self.clients[config.name] = httpx.AsyncClient(
                base_url=config.url,
                headers=headers,
                timeout=config.timeout
            )
        
        logger.info(f"成功注册MCP服务器: {config.name} ({config.url})")
    
    async def discover_tools(self, server_name: str) -> List[MCPTool]:
        """
        从服务器发现可用工具
        
        Args:
            server_name: 服务器名称
            
        Returns:
            工具列表
        """
        if server_name not in self.servers:
            raise ValueError(f"服务器 {server_name} 未注册")
        
        # 检查缓存
        if server_name in self._tool_cache:
            return self._tool_cache[server_name]
        
        server = self.servers[server_name]
        tools = []
        
        try:
            if server.server_type == MCPServerType.HTTP:
                client = self.clients[server_name]
                response = await client.get("/tools")
                response.raise_for_status()
                
                tools_data = response.json()
                for tool_info in tools_data.get("tools", []):
                    tool = MCPTool(
                        name=tool_info["name"],
                        description=tool_info.get("description", ""),
                        input_schema=tool_info.get("input_schema", {}),
                        output_schema=tool_info.get("output_schema", {}),
                        server_name=server_name,
                        endpoint=tool_info.get("endpoint", f"/tools/{tool_info['name']}"),
                        method=tool_info.get("method", "POST"),
                        timeout=tool_info.get("timeout"),
                        metadata=tool_info.get("metadata", {})
                    )
                    tools.append(tool)
                    self.tools[f"{server_name}.{tool.name}"] = tool
            
            # 缓存结果
            self._tool_cache[server_name] = tools
            logger.info(f"从服务器 {server_name} 发现 {len(tools)} 个工具")
            
        except Exception as e:
            logger.error(f"发现工具失败 ({server_name}): {e}")
            raise
        
        return tools
    
    async def invoke_tool(
        self,
        tool_name: str,
        inputs: Dict[str, Any],
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        调用MCP工具
        
        Args:
            tool_name: 工具名称 (格式: "server.tool" 或直接 "tool")
            inputs: 输入参数
            timeout: 超时时间（覆盖默认值）
            
        Returns:
            工具执行结果
        """
        # 解析工具名称
        if "." in tool_name:
            full_name = tool_name
        else:
            # 在所有工具中查找
            matching_tools = [k for k in self.tools.keys() if k.endswith(f".{tool_name}")]
            if not matching_tools:
                raise ValueError(f"未找到工具: {tool_name}")
            if len(matching_tools) > 1:
                raise ValueError(f"工具名称不明确，找到多个匹配: {matching_tools}")
            full_name = matching_tools[0]
        
        if full_name not in self.tools:
            raise ValueError(f"工具 {full_name} 未注册")
        
        tool = self.tools[full_name]
        server = self.servers[tool.server_name]
        
        # 验证输入
        # TODO: 使用 jsonschema 验证 inputs 符合 tool.input_schema
        
        # 执行调用
        result = await self._execute_with_retry(
            tool=tool,
            inputs=inputs,
            timeout=timeout or tool.timeout or server.timeout,
            max_retries=server.max_retries,
            retry_delay=server.retry_delay
        )
        
        return result
    
    async def _execute_with_retry(
        self,
        tool: MCPTool,
        inputs: Dict[str, Any],
        timeout: int,
        max_retries: int,
        retry_delay: float
    ) -> Dict[str, Any]:
        """
        带重试的工具执行
        
        Args:
            tool: 工具定义
            inputs: 输入参数
            timeout: 超时时间
            max_retries: 最大重试次数
            retry_delay: 重试延迟
            
        Returns:
            执行结果
        """
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    await asyncio.sleep(retry_delay * attempt)
                    logger.info(f"重试调用工具 {tool.name} (第 {attempt + 1} 次)")
                
                server = self.servers[tool.server_name]
                
                if server.server_type == MCPServerType.HTTP:
                    client = self.clients[tool.server_name]
                    
                    # 构建请求
                    request_data = {
                        "tool": tool.name,
                        "inputs": inputs,
                        "metadata": tool.metadata
                    }
                    
                    # 发送请求
                    start_time = time.time()
                    
                    if tool.method.upper() == "POST":
                        response = await client.post(
                            tool.endpoint,
                            json=request_data,
                            timeout=timeout
                        )
                    elif tool.method.upper() == "GET":
                        response = await client.get(
                            tool.endpoint,
                            params=inputs,
                            timeout=timeout
                        )
                    else:
                        raise ValueError(f"不支持的HTTP方法: {tool.method}")
                    
                    response.raise_for_status()
                    result = response.json()
                    
                    execution_time = time.time() - start_time
                    logger.info(f"工具 {tool.name} 执行成功，耗时 {execution_time:.2f}s")
                    
                    # 添加执行元数据
                    if isinstance(result, dict):
                        result["_mcp_metadata"] = {
                            "tool_name": tool.name,
                            "server_name": tool.server_name,
                            "execution_time": execution_time,
                            "attempt": attempt + 1
                        }
                    
                    return result
                
                else:
                    raise NotImplementedError(f"暂不支持 {server.server_type} 类型的服务器")
                
            except httpx.TimeoutException as e:
                last_error = f"超时: {e}"
                logger.warning(f"工具 {tool.name} 调用超时 (尝试 {attempt + 1}/{max_retries + 1})")
                
            except httpx.HTTPStatusError as e:
                last_error = f"HTTP错误 {e.response.status_code}: {e.response.text}"
                logger.warning(f"工具 {tool.name} 调用失败 (尝试 {attempt + 1}/{max_retries + 1}): {last_error}")
                
            except Exception as e:
                last_error = str(e)
                logger.error(f"工具 {tool.name} 调用异常 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
        
        # 所有重试都失败
        error_msg = f"工具 {tool.name} 调用失败（重试 {max_retries} 次后）: {last_error}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    
    def register_tool(self, tool: MCPTool) -> None:
        """
        手动注册工具（用于本地工具或自定义工具）
        
        Args:
            tool: 工具定义
        """
        full_name = f"{tool.server_name}.{tool.name}"
        self.tools[full_name] = tool
        logger.info(f"成功注册工具: {full_name}")
    
    def list_tools(self) -> List[str]:
        """
        列出所有可用工具
        
        Returns:
            工具名称列表
        """
        return list(self.tools.keys())
    
    def get_tool(self, tool_name: str) -> Optional[MCPTool]:
        """
        获取工具定义
        
        Args:
            tool_name: 工具名称
            
        Returns:
            工具定义
        """
        return self.tools.get(tool_name)
    
    async def close(self):
        """关闭所有客户端连接"""
        for client in self.clients.values():
            await client.aclose()
        self.clients.clear()
        logger.info("已关闭所有MCP客户端连接")


# 全局MCP管理器实例
_mcp_manager: Optional[MCPClientManager] = None


def get_mcp_manager() -> MCPClientManager:
    """获取全局MCP管理器实例"""
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPClientManager()
    return _mcp_manager


async def init_mcp_servers(config: Dict[str, Any]) -> MCPClientManager:
    """
    根据配置初始化MCP服务器
    
    Args:
        config: 配置字典，包含 mcp_servers 列表
        
    Returns:
        初始化后的MCP管理器
    """
    manager = get_mcp_manager()
    
    for server_config in config.get("mcp_servers", []):
        server = MCPServerConfig(
            name=server_config["name"],
            url=server_config["url"],
            server_type=MCPServerType(server_config.get("type", "http")),
            auth_token=server_config.get("auth_token"),
            timeout=server_config.get("timeout", 30),
            max_retries=server_config.get("max_retries", 3),
            retry_delay=server_config.get("retry_delay", 1.0),
            metadata=server_config.get("metadata", {})
        )
        manager.register_server(server)
        
        # 自动发现工具
        if server_config.get("auto_discover", True):
            try:
                await manager.discover_tools(server.name)
            except Exception as e:
                logger.warning(f"自动发现工具失败 ({server.name}): {e}")
    
    return manager
