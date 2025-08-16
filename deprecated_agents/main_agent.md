# 主智能体模块 (main_agent.py)

主智能体是天然气碳同位素数据解释智能体系统的核心组件，负责整个系统的主要决策逻辑、用户交互、工具调用和任务协调。该模块基于LangChain和LangGraph框架实现，采用ReAct（推理-行动）模式，能够自主分析用户需求并调用合适的工具解决问题。

## 主要功能

主智能体提供以下核心功能：

1. **用户需求理解**：分析用户输入，识别用户的真实需求和意图
2. **任务分类与管理**：将用户需求分类并创建结构化任务
3. **工具选择与调用**：根据任务需要选择并调用合适的工具
4. **人机交互管理**：在需要时请求用户提供额外信息或确认
5. **任务移交**：将特定任务移交给专家智能体处理
6. **响应生成**：生成专业、清晰的响应返回给用户

## 架构设计

主智能体基于`BaseAgent`基类构建，具备以下核心组件：

1. **ReAct智能体**：采用推理-行动模式，可以思考并选择工具执行
2. **提示词系统**：使用精心设计的系统提示词，指导智能体行为
3. **工具集成**：可动态注册和使用多种工具
4. **状态管理**：维护任务执行过程的状态
5. **错误处理**：管理执行过程中可能出现的异常

## 关键方法

### 1. 初始化与配置

通过`__init__`方法初始化智能体，设置LLM、工具集、系统提示词等：

```python
agent = MainAgent(
    llm=ChatOpenAI(model="gpt-4o"),
    tools=[file_reader_tool, isotope_calculator_tool],
    system_prompt=custom_prompt,  # 可选，默认使用内置提示词
    name="天然气碳同位素助手",
    verbose=True
)
```

### 2. 执行流程

主要执行流程由`run`方法定义，处理系统状态并生成响应：

```python
# 创建初始状态
state = StateManager.create_initial_state()

# 添加用户消息
state = StateManager.update_messages(
    state, 
    HumanMessage(content="请分析这个碳同位素数据：δ13C1 = -35‰")
)

# 运行智能体
updated_state = agent.run(state)

# 获取响应
response = updated_state["messages"][-1]
```

### 3. 任务管理

智能体可以从用户消息自动创建任务，并在执行过程中更新任务状态：

```python
# 创建任务
task_info = agent._create_task_from_message("分析碳同位素数据")

# 更新任务状态
state = StateManager.update_current_task(state, task_info)
```

### 4. 工具调用

智能体可以自动识别需要使用工具的情况，并调用相应工具：

```python
# 工具调用会自动记录在状态中
tool_executions = state["current_task"]["tool_executions"]
```

### 5. 智能体协作

可以将特定任务移交给专家智能体处理：

```python
# 将任务移交给专家智能体
state = agent.handoff_to_expert(state)
```

### 6. 人机交互

在需要用户输入时，可以请求人类介入：

```python
# 请求用户提供更多信息
state = agent.request_human_input(state, "需要提供样本的采集深度和位置")
```

## 与LangGraph集成

主智能体设计为可与LangGraph框架无缝集成，可作为图节点在工作流中使用：

```python
def main_agent_node(state: IsotopeSystemState) -> Dict[str, Any]:
    """主智能体节点处理逻辑"""
    agent = MainAgent(llm=llm, tools=tools)
    return agent.run(state)

# 添加到图中
graph.add_node("main_agent", main_agent_node)
```

## 提示词系统

主智能体使用专门设计的系统提示词，定义了其行为模式和专业知识范围。提示词包括：

1. 工作流程指导
2. 思考框架
3. 沟通风格规范
4. 专业知识范围
5. 可用工具说明

这些提示词确保智能体能够专业、清晰地与用户交流，并在处理问题时遵循结构化的思考过程。

## 任务类型

主智能体根据用户输入识别以下任务类型：

1. **general_query**：一般性查询，可直接回答
2. **isotope_analysis**：碳同位素数据分析，可能需要专家处理
3. **data_processing**：数据处理任务，需要使用数据处理工具
4. **planning**：研究或分析规划任务，需要任务分解

## 错误处理

主智能体包含全面的错误处理机制，确保在执行过程中出现问题时能够：

1. 记录详细错误信息
2. 生成友好的错误消息返回给用户
3. 在可能的情况下提供替代解决方案

## 使用示例

以下是使用主智能体处理用户查询的完整示例：

```python
from app.agents.main_agent import MainAgent
from app.core.state import StateManager
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from app.tools.isotope_tools import create_isotope_calculator_tool

# 创建工具
isotope_tool = create_isotope_calculator_tool()

# 创建智能体
agent = MainAgent(
    llm=ChatOpenAI(model="gpt-4o"),
    tools=[isotope_tool],
    verbose=True
)

# 创建初始状态
state = StateManager.create_initial_state()

# 添加用户查询
user_query = "请根据这些甲烷碳同位素数据分析气源：δ13C1 = -35‰, δ13C2 = -28‰, δ13C3 = -25‰"
state = StateManager.update_messages(state, HumanMessage(content=user_query))

# 运行智能体
result_state = agent.run(state)

# 处理响应
for message in result_state["messages"]:
    print(f"{message.__class__.__name__}: {message.content}")

# 查看任务执行过程
if "current_task" in result_state:
    task = result_state["current_task"]
    print(f"任务类型: {task['task_type']}")
    print(f"任务状态: {task['status']}")
    
    if "tool_executions" in task:
        print("工具调用:")
        for i, tool_exec in enumerate(task["tool_executions"]):
            print(f"  {i+1}. {tool_exec['tool_name']}")
```

## 最佳实践

1. **提供完整工具集**：确保智能体有足够的工具来解决领域问题
2. **使用高质量LLM**：主智能体的表现很大程度上依赖于底层LLM的能力
3. **保持状态一致性**：避免直接修改状态，始终使用`StateManager`来更新
4. **监控执行过程**：启用verbose模式以便调试和监控
5. **设置合理超时**：对于复杂任务，确保LLM和工具有足够的执行时间

## 扩展与定制

主智能体设计为可扩展的，可以通过以下方式进行定制：

1. **添加自定义工具**：开发并注册新的领域特定工具
2. **自定义系统提示词**：根据特定应用场景调整系统提示词
3. **扩展任务类型**：增加新的任务类型和处理逻辑
4. **集成专家智能体**：开发专门的专家智能体处理特定问题

通过这些扩展点，主智能体可以适应各种天然气地球化学数据分析和解释场景。 