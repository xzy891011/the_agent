# 核心模块 (Core)

核心模块包含智能体系统的基础组件，负责状态管理、图构建、配置管理等核心功能。

## 状态管理模块 (state.py)

状态管理模块定义了智能体系统的状态结构，并提供了一系列方法来创建和操作状态。该模块是基于LangGraph的状态管理机制设计的，使用TypedDict定义状态结构，并通过reducer函数控制状态更新行为。

### 主要组件

#### 1. 状态结构定义

```python
class IsotopeSystemState(TypedDict):
    """天然气碳同位素数据解释智能体系统的状态定义"""
    messages: Annotated[List[BaseMessage], add_messages]  # 对话消息历史
    action_history: List[Dict[str, Any]]  # 执行动作历史
    files: Dict[str, FileInfo]  # 文件信息
    current_task: Optional[TaskInfo]  # 当前任务状态
    tool_results: List[ToolExecution]  # 工具执行结果历史
    metadata: Dict[str, Any]  # 元数据，包括会话信息等
```

状态包含以下关键部分：
- `messages`: 对话消息历史，使用LangGraph的`add_messages` reducer确保消息追加而非覆盖
- `action_history`: 智能体执行的动作历史记录
- `files`: 系统中的文件信息
- `current_task`: 当前正在处理的任务信息
- `tool_results`: 工具执行结果历史
- `metadata`: 会话信息等元数据

#### 2. 辅助数据结构

- `TaskStatus`: 任务状态枚举（未开始、进行中、等待用户输入、已完成、失败）
- `ToolExecution`: 工具执行记录结构
- `FileInfo`: 文件信息结构
- `TaskInfo`: 任务信息结构

#### 3. 状态管理器 (StateManager)

`StateManager`类提供了一系列静态方法，用于创建和操作状态：

- `create_initial_state()`: 创建初始状态
- `update_messages()`: 更新消息历史
- `add_action_record()`: 添加执行动作记录
- `add_file()` / `remove_file()`: 管理文件信息
- `update_current_task()`: 更新当前任务状态
- `add_tool_result()`: 添加工具执行结果
- `update_metadata()`: 更新元数据

同时提供了几个便捷方法来查询状态：

- `get_last_message()`: 获取最后一条消息
- `get_last_human_message()`: 获取最后一条人类消息
- `get_conversation_history()`: 获取对话历史
- `get_formatted_state_for_llm()`: 获取格式化的状态信息用于LLM

### 使用示例

```python
from app.core.state import StateManager, TaskStatus
from langchain_core.messages import HumanMessage

# 创建初始状态
state = StateManager.create_initial_state()

# 添加消息
human_msg = HumanMessage(content="你好，我想分析一些天然气碳同位素数据")
state = StateManager.update_messages(state, human_msg)

# 更新元数据
state = StateManager.update_metadata(state, {
    "session_id": "session123",
    "user_id": "user456"
})

# 获取格式化的状态信息用于LLM
formatted_state = StateManager.get_formatted_state_for_llm(state)
```

### 设计理念

1. **不可变状态**: 所有状态更新操作都返回新的状态对象，而不是修改原始状态，确保状态追踪和回溯能力。

2. **类型安全**: 使用TypedDict定义状态结构，提供类型提示和文档。

3. **功能模块化**: 将状态管理功能封装在StateManager类中，提供清晰的API。

4. **与LangGraph集成**: 状态结构设计兼容LangGraph的状态管理机制，使用add_messages等reducer函数。

5. **易于扩展**: 状态结构可根据需要轻松扩展，添加新的状态字段或管理方法。

### 测试

提供了完整的单元测试，确保状态管理功能正常工作：

```bash
# 运行测试
python -m app.core.test_state
``` 