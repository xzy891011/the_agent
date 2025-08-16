# Stage 5 快速修复指南

## 🔧 需要立即修复的问题

### 1. RAG组件初始化问题
**问题**: MemoryIntegration初始化时参数不匹配
```
WARNING - RAG组件初始化失败: MemoryIntegration.__init__() got an unexpected keyword argument 'user_id'
```

**修复方案**:
```python
# 在 app/core/critic_node.py 中修改初始化代码
# 从:
self.memory_integration = MemoryIntegration(user_id="critic_node")
# 改为:
self.memory_integration = create_memory_integration()
```

### 2. 完整工作流测试失败
**问题**: 缺少data_agent节点定义
```
ERROR - At 'task_planner' node, 'route_after_task_planner' branch found unknown target 'data_agent'
```

**修复方案**:
在`build_enhanced_graph`方法中添加data_agent和expert_agent节点的定义，或者修改路由逻辑只使用已存在的节点。

### 3. 工具参数不匹配
**问题**: 某些工具执行失败
```
WARNING - 工具执行失败（可能是参数不匹配）: 1 validation error for preview_file_content
```

**修复方案**:
在工具转换为task时，需要更智能地处理参数映射。

## 📋 优化建议

### 1. 完善系统能力分类
```python
# 在 app/tools/registry.py 的 _register_to_capability_registry 方法中
# 添加更精确的能力类型判断逻辑
if "isotope" in tool.name.lower():
    capability_type = CapabilityType.ANALYSIS
elif "plot" in tool.name.lower() or "viz" in tool.name.lower():
    capability_type = CapabilityType.VISUALIZATION
# ... 更多分类规则
```

### 2. 实现动态子图执行
```python
# 创建子图执行器
class SubgraphExecutor:
    def execute_subgraph(self, subgraph, initial_state, config):
        """执行子图并返回结果"""
        # 1. 设置初始状态
        # 2. 执行子图
        # 3. 收集结果
        # 4. 返回最终状态
```

### 3. 集成Agent通信到执行流程
```python
# 在每个Agent节点中添加通信逻辑
def agent_node_with_communication(state):
    # 1. 接收消息
    messages = extract_messages_from_state(state, AgentType.CURRENT_AGENT)
    
    # 2. 处理任务
    result = process_task(state)
    
    # 3. 发送状态更新
    status_msg = MessageFactory.create_execution_status(...)
    state = inject_message_to_state(state, status_msg)
    
    return state
```

### 4. 实现中断恢复机制
```python
# 在 EnhancedGraphBuilder 中添加恢复方法
def resume_from_interrupt(self, session_id, interrupt_id, user_response):
    """从中断点恢复执行"""
    # 1. 加载中断上下文
    # 2. 处理用户响应
    # 3. 更新状态
    # 4. 继续执行
```

## 🚀 快速启动命令

```bash
# 运行测试
python test_stage5_full.py

# 检查工具注册状态
python -c "from app.tools.registry import get_all_tools, task_registry; print(f'工具: {len(get_all_tools())}, 任务: {len(task_registry.get_all_tasks())}')"

# 测试系统能力注册表
python -c "from app.core.system_capability_registry import get_system_capability_registry; r = get_system_capability_registry(); print(f'总能力数: {len(r.capabilities)}')"
```

## 📝 代码片段

### 创建完整的Agent节点
```python
def create_all_agent_nodes():
    """创建所有必需的Agent节点"""
    nodes = {
        "main_agent": main_agent_node,
        "data_agent": data_agent_node,
        "expert_agent": expert_agent_node,
        "meta_supervisor": meta_supervisor_node,
        "task_planner": task_planner_node,
        "runtime_supervisor": runtime_supervisor_node,
        "critic": critic_node
    }
    return nodes
```

### 智能参数映射
```python
def smart_parameter_mapping(tool, kwargs):
    """智能地映射工具参数"""
    if hasattr(tool, 'args_schema'):
        schema = tool.args_schema.schema()
        required = schema.get('required', [])
        
        # 尝试从kwargs中提取必需参数
        mapped_args = {}
        for param in required:
            if param in kwargs:
                mapped_args[param] = kwargs[param]
            elif 'query' in kwargs and param in ['file_id', 'path', 'name']:
                # 尝试智能映射
                mapped_args[param] = kwargs['query']
        
        return mapped_args
    return kwargs
```

## ⚡ 性能优化建议

1. **并行执行子图**: 当多个子图无依赖关系时，可以并行执行
2. **缓存系统能力**: 避免重复查询系统能力注册表
3. **消息批处理**: 批量处理Agent间的消息，减少通信开销
4. **检查点优化**: 只在关键节点创建检查点，避免过度存储

---

使用这个快速修复指南，可以快速解决Stage 5中遇到的主要问题，并进一步优化系统性能。 