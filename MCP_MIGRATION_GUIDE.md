# MCP工具迁移指南

## 🎯 迁移概述

本项目已成功从传统的 `@task` 装饰器系统迁移到现代化的 **MCP (Model Context Protocol)** 协议。这一迁移提供了：

- ✅ **标准化协议**：使用行业标准的MCP协议
- ✅ **向后兼容**：保持现有工具的完全兼容性
- ✅ **增强扩展性**：更容易集成外部工具和服务
- ✅ **统一接口**：通过MCP协议统一管理所有工具
- ✅ **动态工具发现**：运行时自动发现和注册工具

## 🔧 架构变化

### 迁移前 (传统@task装饰器)
```
用户请求 → 智能体 → @task装饰器工具 → 直接执行
```

### 迁移后 (MCP协议)
```
用户请求 → 智能体 → MCP客户端 → MCP服务器 → 工具执行
```

## 📋 核心组件

### 1. MCP工具服务器 (`app/tools/mcp_tool_server.py`)
- 将LangChain工具包装为MCP服务器
- 支持同步和异步工具调用
- 自动工具参数验证和错误处理

### 2. 增强MCP客户端 (`app/tools/enhanced_mcp_client.py`)
- 集成 `langchain-mcp-adapters` 库
- 支持多服务器管理
- 提供统一的工具调用接口

### 3. 更新的工具注册表 (`app/tools/registry.py`)
- 增加MCP支持
- 保持传统工具的向后兼容性
- 提供混合模式（传统+MCP）

## 🚀 使用方式

### 启用MCP协议

```python
from app.tools.registry import enable_mcp_tools, get_tool_registry

# 启用MCP支持
enable_mcp_tools()

# 获取工具注册表
registry = get_tool_registry()

# 检查MCP状态
if registry.is_mcp_enabled():
    print("MCP协议已启用")
```

### 调用MCP工具

```python
from app.tools.registry import invoke_any_tool, get_mixed_tools

# 获取所有可用工具（传统+MCP）
tools = get_mixed_tools()

# 优先使用MCP协议调用工具
result = invoke_any_tool(
    tool_name="enhanced_plot_bernard_diagram",
    prefer_mcp=True,
    data_file="path/to/data.xlsx",
    depth_column="depth"
)
```

### 智能体集成

智能体会自动识别MCP工具并优先使用：

```python
from app.agents.langgraph_agent import LangGraphAgent

# 创建智能体（自动支持MCP）
agent = LangGraphAgent(
    name="分析智能体",
    role="expert_analysis",
    llm=llm
)

# 智能体会自动使用MCP工具
response = agent.process("分析这个碳同位素数据")
```

## 📊 迁移验证

运行测试脚本验证迁移是否成功：

```bash
conda activate sweet
python test_mcp_migration.py
```

期望输出：
```
✅ 通过 工具注册表MCP集成
✅ 通过 MCP服务器设置
✅ 通过 增强MCP客户端
✅ 通过 智能体MCP集成
✅ 通过 图构建器MCP支持
✅ 通过 向后兼容性
```

## 🔄 向后兼容性

**重要：所有现有代码无需修改！**

传统的工具调用方式仍然完全支持：

```python
# 传统方式仍可用
from app.tools.registry import get_all_tools, get_tool

tools = get_all_tools()  # 获取所有工具
tool = get_tool("preview_file_content")  # 获取特定工具
```

## 📈 性能对比

| 特性 | 传统@task | MCP协议 | 改进 |
|------|-----------|---------|------|
| 工具发现 | 静态导入 | 动态发现 | ⬆️ 灵活性 |
| 错误处理 | 基础 | 增强 | ⬆️ 可靠性 |
| 参数验证 | 手动 | 自动 | ⬆️ 安全性 |
| 协议标准 | 自定义 | 行业标准 | ⬆️ 互操作性 |
| 扩展性 | 受限 | 无限 | ⬆️ 可扩展 |

## 🛠️ 开发指南

### 添加新的MCP工具

1. 创建标准LangChain工具：
```python
from langchain_core.tools import BaseTool
from app.tools.registry import register_tool

@register_tool("my_new_tool", category="analysis")
class MyNewTool(BaseTool):
    name = "my_new_tool"
    description = "我的新工具"
    
    def _run(self, query: str) -> str:
        # 工具逻辑
        return "result"
```

2. 工具会自动注册到MCP服务器，无需额外配置！

### 自定义MCP服务器

```python
from app.tools.mcp_tool_server import IsotopeMCPServer

# 创建自定义服务器
custom_server = IsotopeMCPServer("custom_tools")

# 注册自定义工具
custom_server.register_tool(my_custom_tool)
```

## 🔍 故障排查

### 常见问题

1. **MCP工具不可用**
   ```python
   # 检查MCP状态
   from app.tools.registry import is_mcp_enabled
   print(f"MCP启用状态: {is_mcp_enabled()}")
   ```

2. **工具调用失败**
   ```python
   # 使用详细错误信息
   try:
       result = invoke_any_tool("tool_name", **params)
   except Exception as e:
       print(f"工具调用失败: {e}")
   ```

3. **循环导入错误**
   - 所有MCP相关导入已优化为动态导入
   - 如遇到问题，检查导入顺序

### 日志分析

启用详细日志：
```python
import logging
logging.getLogger("app.tools").setLevel(logging.DEBUG)
```

## 🎯 最佳实践

1. **优先使用MCP协议**：新开发的功能应优先使用MCP工具
2. **保持向后兼容**：不要删除现有的`@task`装饰器工具
3. **统一错误处理**：使用MCP的标准错误处理机制
4. **工具分类管理**：合理使用工具分类，便于管理和发现
5. **异步优先**：新工具应支持异步调用

## 📝 变更日志

### v1.0.0 - MCP迁移完成
- ✅ 成功迁移所有16个现有工具到MCP协议
- ✅ 保持100%向后兼容性
- ✅ 集成langchain-mcp-adapters库
- ✅ 实现动态工具发现和注册
- ✅ 优化智能体工具调用流程
- ✅ 增强错误处理和日志记录

## 🔗 相关文档

- [LangGraph MCP集成](https://langchain-ai.github.io/langgraph/agents/mcp/)
- [MCP协议规范](https://github.com/modelcontextprotocol/specification)
- [项目工具注册表文档](app/tools/README.md)

---

**🎉 恭喜！您的项目已成功迁移到MCP协议，享受更现代化的工具调用体验！**
