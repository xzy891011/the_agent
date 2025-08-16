# LangGraph流式处理使用指南

基于[LangGraph官方文档](https://langchain-ai.github.io/langgraph/how-tos/streaming/)的流式处理最佳实践。

## 📋 流式模式对比

| 流模式 | 描述 | 是否推送到前端 | 用途 |
|--------|------|---------------|------|
| **messages** | LLM token流 | ✅ 推送 | 实时显示AI回复 |
| **custom** | 自定义数据流 | ✅ 推送 | 执行状态、进度、通知 |
| **updates** | 节点状态更新 | ✅ 选择性推送 | 节点执行跟踪 |
| **values** | 完整状态快照 | ❌ 通常不推送 | 数据量大，仅特殊需求 |
| **debug** | 调试信息 | ❌ 开发时使用 | 调试和问题排查 |

## 🎯 推荐的状态推送方式

### 1. 使用 `get_stream_writer` + custom流（推荐）

```python
from langgraph.config import get_stream_writer
from app.core.stream_writer_helper import push_thinking, push_node_start, push_progress

def my_agent_node(state):
    # 推送Agent思考过程
    push_thinking("main_agent", "正在分析用户请求...")
    
    # 推送节点开始执行
    push_node_start("data_analysis", "开始数据分析任务")
    
    # 执行业务逻辑...
    
    # 推送工具执行进度
    push_progress("data_processor", 0.5, "已处理50%的数据")
    
    return state
```

### 2. 在工具中推送进度信息

```python
from langchain_core.tools import tool
from app.core.stream_writer_helper import push_progress, push_file

@tool
def process_geological_data(file_path: str) -> str:
    """处理地质数据文件"""
    
    # 推送开始状态
    push_progress("geological_processor", 0.0, "开始处理地质数据")
    
    # 执行处理...
    for i, step in enumerate(processing_steps):
        progress = (i + 1) / len(processing_steps)
        push_progress("geological_processor", progress, f"正在执行: {step}")
        
        # 实际处理逻辑
        result = process_step(step)
    
    # 推送文件生成通知
    output_file = generate_report(results)
    push_file("report_001", "geological_analysis_report.pdf", output_file, "pdf")
    
    return "地质数据处理完成"
```

## 📡 支持的自定义消息类型

### Agent思考过程
```python
from app.core.stream_writer_helper import LangGraphStreamWriter

# 方式1：使用便捷函数
push_thinking("main_agent", "正在分析数据模式...")

# 方式2：使用完整方法
LangGraphStreamWriter.push_agent_thinking(
    agent_name="expert_agent",
    content="基于同位素特征，推断气源为热成因",
    thinking_type="analysis"
)
```

### 节点执行状态
```python
# 节点开始
push_node_start("meta_supervisor", "开始任务分析")

# 节点完成
push_node_complete("meta_supervisor", "任务分析完成，识别为consultation类型")

# 节点错误
push_node_error("data_agent", "数据文件格式不支持")
```

### 路由决策
```python
push_route("meta_supervisor", "main_agent", "简单咨询，直接路由到主Agent")
```

### 工具和任务进度
```python
# 工具执行进度
push_progress("isotope_analyzer", 0.75, "同位素分析75%完成")

# 任务状态更新
LangGraphStreamWriter.push_task_status(
    task_name="geological_analysis", 
    status="running",
    progress=0.6,
    details="正在进行地球化学分析"
)
```

### 文件生成通知
```python
push_file(
    file_id="analysis_001",
    file_name="isotope_analysis_report.pdf", 
    file_path="/data/generated/analysis_001.pdf",
    file_type="pdf"
)
```

### 分析结果
```python
LangGraphStreamWriter.push_analysis_result(
    result_type="isotope",
    result_data={
        "carbon_isotope": -42.5,
        "hydrogen_isotope": -145.2,
        "gas_type": "thermogenic"
    },
    confidence=0.87
)
```

### 错误信息
```python
push_error("数据文件损坏，无法读取", source="file_reader")
```

## 🔄 在现有代码中集成流式推送

### 1. 在Agent中添加思考推送

```python
# app/agents/main_agent.py
from app.core.stream_writer_helper import push_thinking

class MainAgent:
    def analyze_request(self, state):
        push_thinking("main_agent", "开始分析用户请求类型...")
        
        # 现有分析逻辑
        task_type = self._classify_task(state.get("messages", []))
        
        push_thinking("main_agent", f"识别任务类型: {task_type}")
        
        return {"task_type": task_type}
```

### 2. 在工具中添加进度推送

```python
# app/tools/data_analysis.py  
from app.core.stream_writer_helper import push_progress, push_file

@task(deterministic=True)
def analyze_isotope_data(file_path: str):
    """同位素数据分析工具"""
    
    push_progress("isotope_analyzer", 0.0, "开始读取数据文件")
    
    # 读取数据
    data = read_isotope_file(file_path)
    push_progress("isotope_analyzer", 0.3, "数据读取完成，开始分析")
    
    # 分析处理
    results = process_isotope_data(data)
    push_progress("isotope_analyzer", 0.8, "分析计算完成，生成报告")
    
    # 生成报告
    report_path = generate_report(results)
    push_file("isotope_report", "isotope_analysis.pdf", report_path, "pdf")
    
    push_progress("isotope_analyzer", 1.0, "同位素分析全部完成")
    
    return results
```

### 3. 在图构建器中添加路由推送

```python
# app/core/enhanced_graph_builder.py
from app.core.stream_writer_helper import push_route

def route_to_next_node(state):
    current_task = state.get("current_task")
    
    if current_task["complexity"] == "simple":
        next_node = "main_agent"
        reason = "简单任务，直接路由到主Agent"
    else:
        next_node = "task_planner"  
        reason = "复杂任务，路由到任务规划器"
    
    push_route("meta_supervisor", next_node, reason)
    
    return next_node
```

## 🎨 前端显示效果

经过优化的流式处理器会将这些自定义消息转换为统一格式，前端可以实现：

- **实时思考气泡**: 显示Agent当前思考过程
- **执行状态指示器**: 显示当前执行的节点和状态  
- **进度条**: 显示工具执行进度
- **路由流程图**: 可视化决策路径
- **文件下载链接**: 生成文件的即时下载
- **分析结果卡片**: 格式化显示分析结果

## ⚠️ 注意事项

1. **避免过度推送**: 不要在循环中频繁推送相同类型的消息
2. **消息大小控制**: 自定义消息内容建议控制在200字符以内
3. **错误处理**: `get_stream_writer()`在非LangGraph执行上下文中会失败，需要适当的异常处理
4. **性能考虑**: 大量流式消息可能影响性能，合理控制推送频率

## 🚀 最佳实践总结

1. **主要使用custom流**: 通过`get_stream_writer`推送执行状态
2. **messages流自动处理**: LLM输出会自动通过messages流传输
3. **updates流选择性使用**: 只在需要详细节点状态时关注
4. **values流避免推送**: 数据量大，通常不适合前端显示
5. **结构化消息**: 使用预定义的消息格式，便于前端处理

通过这种方式，您可以实现完整的LangGraph执行状态可视化，让用户实时了解系统的工作进展。 