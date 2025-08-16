# 执行引擎 (Engine) 设计文档

## 1. 概述

执行引擎是智能体系统的中央协调组件，负责整合各个模块，提供统一的API接口，并管理系统的生命周期。它是连接用户、智能体、工具和状态管理的核心枢纽。

## 2. 功能职责

执行引擎的主要职责包括：

1. **智能体管理**：创建和初始化各类智能体，包括主智能体和专家智能体
2. **工作流协调**：基于LangGraph构建和管理智能体工作流
3. **会话管理**：维护用户会话状态和历史记录
4. **工具注册与执行**：管理系统可用工具，并协调工具的调用
5. **状态持久化**：提供会话状态的保存和恢复功能
6. **错误处理**：统一处理系统中的异常和错误情况

## 3. 核心组件

### 3.1 IsotopeEngine 类

`IsotopeEngine` 类是整个执行引擎的主要实现，包含以下核心方法：

- **初始化方法**：配置引擎参数，创建智能体和工作流图
- **会话管理方法**：创建、获取和重置会话
- **输入处理方法**：处理用户输入并生成响应
- **工具管理方法**：注册和管理系统工具
- **状态持久化方法**：保存和加载会话状态

### 3.2 与其他模块的关系

执行引擎与系统其他模块的关系：

- **主智能体 (MainAgent)**：由引擎创建和管理，处理主要的用户交互
- **图构建器 (GraphBuilder)**：用于构建智能体工作流图
- **状态管理器 (StateManager)**：管理和更新系统状态
- **工具注册表**：管理系统可用的工具集合

## 4. 工作流程

### 4.1 初始化流程

```
加载配置 -> 创建LLM实例 -> 创建主智能体 -> 注册工具 -> 构建工作流图 -> 编译图
```

### 4.2 处理用户输入流程

```
接收用户输入 -> 创建或获取会话 -> 添加用户消息到状态 -> 执行工作流图 -> 获取结果 -> 更新会话状态 -> 返回响应
```

### 4.3 工具调用流程

```
识别工具调用请求 -> 查找对应工具 -> 解析工具参数 -> 执行工具 -> 记录执行结果 -> 生成工具结果消息
```

## 5. 使用示例

### 5.1 创建执行引擎实例

```python
from app.core.engine import IsotopeEngine
from langchain_core.tools import tool

# 定义工具
@tool
def calculator(a: int, b: int, operation: str = "add") -> str:
    if operation == "add":
        return f"结果: {a + b}"
    # ...其他操作...

# 创建引擎实例
engine = IsotopeEngine(
    config={
        "llm": {
            "model_name": "Qwen/Qwen2.5-72B-Instruct",
            "temperature": 0.7
        },
        "agent_name": "碳同位素智能助手"
    },
    tools=[calculator],
    verbose=True
)
```

### 5.2 处理用户输入

```python
# 创建会话
session_id = engine.create_session()

# 同步处理模式
result = engine.process_input("请计算5加3", session_id)

# 流式处理模式
for state_update in engine.process_input("请计算5加3", session_id, stream=True):
    # 处理状态更新...
    pass
```

### 5.3 工具注册

```python
@tool
def get_isotope_info(isotope_name: str) -> str:
    # 实现工具逻辑...
    pass

# 注册工具
engine.register_tool(get_isotope_info)
```

### 5.4 会话管理

```python
# 获取会话状态
state = engine.get_session_state(session_id)

# 重置会话
engine.reset_session(session_id)

# 保存会话
engine.save_session_state(session_id, "session_backup.json")

# 加载会话
loaded_session_id = engine.load_session_state("session_backup.json")
```

## 6. 设计考虑

### 6.1 可扩展性

- 支持动态添加新工具
- 设计为可扩展新的智能体类型
- 工作流图可以灵活配置和修改

### 6.2 健壮性

- 完善的错误处理机制
- 会话状态持久化备份
- 异常情况下的优雅降级

### 6.3 性能优化

- 流式处理支持
- 状态更新优化
- 缓存机制

## 7. 未来扩展

1. **分布式执行**：支持跨进程或服务器的分布式执行
2. **多模态支持**：增强对多模态内容的处理能力
3. **工具版本管理**：支持工具的版本管理和兼容性检查
4. **智能体市场**：支持动态加载和切换不同智能体
5. **性能监控**：添加性能监控和分析功能

## 8. 附录

### 8.1 状态结构

执行引擎使用的状态结构：

```python
{
    "messages": [...],  # 消息历史
    "action_history": [...],  # 执行动作历史
    "files": {...},  # 文件信息
    "current_task": {...},  # 当前任务状态
    "tool_results": [...],  # 工具执行结果
    "metadata": {...}  # 元数据
}
```

### 8.2 会话管理

会话结构：

```python
{
    "session_id": "...",
    "state": {...},  # 状态对象
    "created_at": "...",  # 创建时间
    "last_updated": "..."  # 最后更新时间
}
``` 