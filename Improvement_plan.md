────────────────────────────────────────
一、总体目标与衡量指标
────────────────────────────────────────
1. 业务目标  
   • 能在单一会话中完成"多井—多学科—多阶段"油气勘探与开发决策支持；  
   • 支持多模态（文本 / 表格 / 图像 / 3D 模型 / 文件）输入输出；  
   • 引入人在回路（HITL）后，用户平均等待时长 ≤ 5 s／次。  

2. 技术 KPI  
┌──────────────┬──────────┐
│ 指标                   │ 目标值           │
├──────────────┼──────────┤
│ 子图并行度             │ ≥ 8 并发         │
│ 任务失败可重播覆盖率   │ 100 %            │
│ 长对话 token 消耗下降   │ ≥ 30 %           │
│ 工具调用成功率         │ ≥ 95 %           │
│ 会话恢复时间           │ ≤ 30 s           │
└──────────────┴──────────┘

────────────────────────────────────────
二、架构与技术方案
────────────────────────────────────────
1. 分层角色  
   • Meta-Supervisor（Python 逻辑）：身份校验、异常兜底；  
   • Task-Planner（LLM + 子图生成）：把用户需求拆为 DAG；  
   • Runtime-Supervisor（Python）：监控子图运行、限流、超时重试；  
   • Critic / Auditor（LLM + 规则）：质量与安全审查；  
   • Domain-Expert-Subgraph（Geology / Geophysics / Reservoir …）：领域工作；  
   • Tool-Task（deterministic）：封装所有副作用操作（绘图、仿真、RAG 检索）。  

2. LangGraph 关键用法  
   • `@task(deterministic=True)`：封装工具节点；  
   • Subgraph：每个领域流水线编译为子图，Planner 运行时 `graph.add_node("geo_sg", geo_compiled)`；  
   • 并行：Planner 输出边 `data_sg -> geo_sg`，其余井号分支通过 `Conditional` 自动并发；  
   • `interrupt()`：在子图关键决策点等待用户上传/确认；  
   • Checkpointer：使用 `PostgresSaver`（生产）| `SQLiteFileSaver`（测试），`thread_id = session_id`；  
   • Streaming：`stream(..., subgraphs=True, stream_mode=["messages","events","custom","debug"])`，namespace 用来在前端分层渲染。  

3. 记忆与数据  
   • Short-Term：各 Agent 里最近 K 条，用 LangGraph reducer `add_messages`；  
   • Episodic（Blackboard）：`state["blackboard"]` 合并字段，子图共享；  
   • Long-Term：FAISS + Elasticsearch，namespace=项目/井号/主题。`retrieve_memories_node` 负责写入 `state["context"]`。  

4. 工具 Registry  
   • 架设 `app/tools/registry.py` → `register_tool()` / `get_tool()`；  
   • 每个工具 pydantic schema，自动导出 OpenAI-tool 格式；  
   • 支持异步 Job 工具：`is_background=True`，状态落到 `state["jobs"]`，Runtime-Supervisor 轮询。  

5. 前端（Gradio）  
   • ChatBot message = {role, content, files?, images?, namespace?}；  
   • 侧边栏展示 DAG 可视化、子图进度、Checkpoint 列表；  
   • 碰到 interrupt 自动弹窗＋上传控件。  

────────────────────────────────────────
三、分阶段实施清单（12 周为例）
────────────────────────────────────────
阶段 0：基线准备（0.5 周）  
   • 升级 langgraph 至最新稳定版；  
   • 创建 `dev` 分支；配置 Postgres / Redis / FAISS / MinIO；  
   • 整理已有工具清单，补齐 pydantic schema。  

阶段 1：任务-子图框架（2 周）  
1）新增模块  
   • `planner_node.py`（LLM-Planner)  
   • `runtime_supervisor.py`  
   • `critic_node.py`  
2）修改 `GraphBuilder`  
   • START → planner → dynamic subgraph → critic → runtime_supervisor。  
3）改造 `IsotopeEngine`  
   • `resume_workflow` 走 `thread_id`;  
   • `process_message_streaming` 直接 yield 原生 chunk。  
输出：可视 DAG 正常运行，Planner 能把"读取三口井数据+生成图"拆成并行子图。  

阶段 2：工具 @task 化 & Checkpoint（2 周）  
   • 把 10 + 常用脚本改写为 `@task`;  
   • 引入 PostgresSaver；  
   • 实现失败节点重播、子图 level-2 checkpoint。  

阶段 3：记忆层升级（1.5 周）  
   • FAISS 向量索引 + Elasticsearch attribute；  
   • `retrieve_memories_node` + reducer；  
   • HistoryManager 按会话/阶段自动摘要写入长记忆。  

阶段 4：前后端分离改造 & 多模态Streaming（2 周）  
   • 后端API化：将Gradio应用重构为RESTful API + WebSocket服务；  
   • 前端独立化：开发Vue/React现代前端框架，替代Gradio界面；  
   • 流式接口设计：`custom` stream 规范：`{"type":"image","file_id":...}` / `{"type":"file",...}`；  
   • 多模态支持：统一的文件、图片、DAG可视化传输协议；  
   • WebSocket通信：实时双向流式数据传输；  
   • 前端组件：侧边栏DAG渲染（mermaid.js）、文件管理、会话管理。  

阶段 5：Agent架构升级 & HITL机制（2 周）  
   • 废弃旧Agent模式：完全移除基于"解析Json + 搜索Tools + 执行Tools"的传统Agent；  
   • 统一动态子图架构：全面采用MetaSupervisor + TaskPlanner + RuntimeSupervisor模式；  
   • @task化工具统一：所有工具调用统一为@task装饰器模式；  
   • Agent间通信优化：基于LangGraph子图的标准化通信协议；  
   • 子图关键节点加 `interrupt`；  
   • Critic 节点调用 RAG + 规则审查；不通过→ goto Planner 重新拆解或 interrupt 请求用户。  

阶段 6：扩展领域 Agent & 并行压测（1.5 周）  
   • 新增 Geophysics/Reservoir/Economics 子图；  
   • 使用 10 井×3 学科并行压测，监控 CPU/GPU/tokens；  
   • 调整 Runtime-Supervisor 策略；  
   • 前后端分离架构的性能优化与稳定性测试。  

阶段 7：Observability & 灾难恢复（1 周）  
   • 日志写入 Loki/Elastic；  
   • Prometheus exporter + Grafana Dashboard；  
   • CLI `engine.list_checkpoints()` + `engine.resume(id)`。  

里程碑验收标准：  
M1（第 2 周末）—— DAG 框架 + Planner 子图演示通过；  
M2（第 4 周末）—— 工具 @task + checkpoint 重播通过 5 次随机中断；  
M3（第 6 周末）—— 记忆检索 F1 ≥ 0.8，token 使用下降 ≥ 25 %；  
M4（第 8 周末）—— 前后端分离架构 + 多模态流式展示完成；  
M5（第10 周末）—— Agent架构升级 + HITL机制验证通过；  
M6（第11.5周末）—— 并发 8 子图吞吐达标 + 前后端性能优化；  
M7（第12 周末）—— 完成全链路 Demo + 监控报警系统。  

────────────────────────────────────────
四、保障体系
────────────────────────────────────────
1. 组织与分工  
   • 架构/核心 LangGraph：2 人（负责 Planner/GraphBuilder/Runtime-Supervisor）  
   • 工具&子图：3 人（按业务域分）  
   • 前端 & Streaming：1 人  
   • DevOps & QA：1 人  
   • 产品 & 业务专家：1 人  

2. 测试策略  
   • 单元：task 函数、工具 schema 验证；  
   • 集成：子图执行 + checkpoint replay；  
   • 压力：并发 50 线程 / 1000 tool-call。  
   • HITL：脚本模拟用户多轮澄清、文件上传。  

3. 风险与缓解  
| 风险 | 缓解措施 |
| ---- | -------- |
| LangGraph API 变动 | 固定版本 & Demo 验收后再升 | 
| 子图并行 OOM | Runtime-Supervisor 动态限流 + queue | 
| 工具副作用幂等性 | `@task(deterministic)`+ 结果哈希缓存 | 
| LLM 输出格式偏差 | OutputFixingParser + Critic 校验 | 
| 大量文件传输 | MinIO + presigned URL，前端懒加载 | 
| 前后端分离兼容性 | 渐进式迁移 + API版本控制 + 双模式运行 |
| Agent架构升级风险 | 保留旧架构备份 + 分阶段切换 + 回滚机制 |
| WebSocket连接稳定性 | 心跳检测 + 自动重连 + 降级到HTTP轮询 |
| 流式数据一致性 | 消息序列号 + 确认机制 + 状态同步 |

4. 交付物  
   • `docs/ARCHITECTURE.md`：最新架构图、子图接口；  
   • `docs/API_SPECIFICATION.md`：前后端分离API规范文档；  
   • `frontend/`：独立前端应用（Vue/React）+ 部署配置；  
   • `backend/api/`：RESTful API + WebSocket服务模块；  
   • `scripts/migrate_v1_to_v2.py`：旧会话→新 checkpoint 迁移脚本；  
   • `scripts/migrate_agent_architecture.py`：Agent架构升级迁移脚本；  
   • `helm/chart/og-ai`：K8s 部署模板（包含前后端服务）；  
   • `grafana/dashboard.json`：监控仪表盘；  
   • 全量测试报告 & 对比基线。  

────────────────────────────────────────
五、结束语
────────────────────────────────────────
该方案将「Planner-Subgraph-Task-Checkpoint-Critic-HITL」链路在 LangGraph 内部显式化，把 LLM 从"调度-执行大包大揽"解放出来，使系统具有  
• DAG 可观测、可并行、可回滚；  
• 记忆分级、避免遗忘；  
• 工具副作用可重放、结果可追溯；  
• 参数/文件/多模态在统一流通道展示；  
• 面向油气勘探全生命周期弹性扩展。  

