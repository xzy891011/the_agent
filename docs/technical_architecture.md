# 天然气碳同位素智能分析系统 - 记忆机制技术架构文档

## 系统概述

天然气碳同位素智能分析系统是一个基于 LangGraph 的多智能体协作系统，集成了先进的记忆机制，能够为不同专业角色的智能体提供个性化的记忆管理和知识检索服务。

### 核心特性

- **多智能体协作架构**：支持12个专业角色的智能体
- **智能记忆管理**：基于角色和领域的记忆筛选与注入
- **动态Prompt优化**：根据上下文自动调整Prompt结构
- **质量评估反馈**：基于使用效果的自适应优化
- **前后端分离**：支持传统Gradio和现代React前端

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户界面层                                 │
├─────────────────────────────────────────────────────────────────┤
│  Gradio UI        │  React Frontend  │  API Gateway              │
├─────────────────────────────────────────────────────────────────┤
│                        业务逻辑层                                 │
├─────────────────────────────────────────────────────────────────┤
│  MetaSupervisor   │  TaskPlanner     │  RuntimeSupervisor       │
├─────────────────────────────────────────────────────────────────┤
│                        智能体层                                   │
├─────────────────────────────────────────────────────────────────┤
│  地球物理分析      │  油藏工程       │  经济评价    │  质量控制    │
├─────────────────────────────────────────────────────────────────┤
│                        记忆管理层                                 │
├─────────────────────────────────────────────────────────────────┤
│  记忆命名空间      │  记忆筛选器     │  Prompt管理器 │  质量监控    │
├─────────────────────────────────────────────────────────────────┤
│                        数据存储层                                 │
├─────────────────────────────────────────────────────────────────┤
│  PostgreSQL       │  MySQL          │  Elasticsearch │  Redis   │
└─────────────────────────────────────────────────────────────────┘
```

## 记忆机制核心模块

### 1. 增强记忆命名空间 (Enhanced Memory Namespace)

**位置**: `app/core/memory/enhanced_memory_namespace.py`

**功能**:
- 支持智能体角色标签 (12种专业角色)
- 支持领域标签 (16个专业领域)
- 多维度记忆分类和索引
- 权限控制和访问管理

**核心类**:
```python
class EnhancedMemoryNamespace:
    - add_memory_with_tags()      # 添加带标签的记忆
    - get_memories_by_role()      # 按角色获取记忆
    - get_memories_by_domain()    # 按领域获取记忆
    - search_memories()           # 智能搜索记忆
```

### 2. 智能体记忆偏好 (Agent Memory Preferences)

**位置**: `app/core/memory/agent_memory_preferences.py`

**功能**:
- 12个智能体角色的详细偏好配置
- 领域权重和时间衰减设置
- 个性化记忆筛选规则
- 动态偏好调整机制

**核心类**:
```python
class AgentMemoryPreferences:
    - get_preference_for_agent()  # 获取智能体偏好
    - update_preference()         # 更新偏好配置
    - get_domain_weights()        # 获取领域权重
    - calculate_memory_score()    # 计算记忆评分
```

### 3. 记忆筛选器 (Agent Memory Filter)

**位置**: `app/core/memory/agent_memory_filter.py`

**功能**:
- 基于偏好的智能记忆筛选
- 5层筛选流程：基础筛选→综合评分→智能选择→优化去重→长度控制
- 批量处理和缓存机制
- 筛选结果统计和分析

**核心类**:
```python
class AgentMemoryFilter:
    - filter_memories()           # 主要筛选接口
    - basic_filter()             # 基础筛选
    - comprehensive_scoring()     # 综合评分
    - intelligent_selection()     # 智能选择
```

### 4. 记忆注入器 (Agent Memory Injector)

**位置**: `app/core/memory/agent_memory_injector.py`

**功能**:
- 在智能体执行前注入相关记忆
- 与LangGraph集成的自动注入机制
- 支持多种注入策略
- 注入效果监控和反馈

**核心类**:
```python
class AgentMemoryInjector:
    - inject_memories()           # 注入记忆
    - auto_inject_for_agent()     # 自动注入
    - register_injection_hook()   # 注册注入钩子
    - monitor_injection_effect()  # 监控注入效果
```

### 5. 动态Prompt管理器 (Dynamic Prompt Manager)

**位置**: `app/core/memory/dynamic_prompt_manager.py`

**功能**:
- 根据智能体角色动态调整Prompt结构
- 支持9种Prompt结构类型、5种样式
- 智能体特定的Prompt模板
- 上下文感知的Prompt生成

**核心类**:
```python
class DynamicPromptManager:
    - generate_dynamic_prompt()   # 生成动态Prompt
    - optimize_prompt_structure() # 优化Prompt结构
    - apply_agent_template()      # 应用智能体模板
    - calculate_confidence_score() # 计算置信度
```

### 6. 记忆相关性评分器 (Memory Relevance Scorer)

**位置**: `app/core/memory/memory_relevance_scorer.py`

**功能**:
- 多维度记忆相关性评估
- 8个相关性因子：语义相似性、任务相关性、时间衰减等
- 6种评分策略：语义导向、任务导向、时间导向等
- 批量评分和缓存优化

**核心类**:
```python
class MemoryRelevanceScorer:
    - score_memory_relevance()    # 评分记忆相关性
    - batch_score_memories()      # 批量评分
    - calculate_factor_scores()   # 计算因子得分
    - optimize_scoring_strategy() # 优化评分策略
```

### 7. Prompt长度控制器 (Prompt Length Controller)

**位置**: `app/core/memory/prompt_length_controller.py`

**功能**:
- 智能Prompt长度控制
- 5级压缩策略：无压缩、轻度、中度、激进、极度
- 内容优先级分析
- 压缩质量评估

**核心类**:
```python
class PromptLengthController:
    - control_prompt_length()     # 控制Prompt长度
    - compress_content()          # 压缩内容
    - analyze_content_priority()  # 分析内容优先级
    - evaluate_compression_quality() # 评估压缩质量
```

### 8. 记忆使用监控器 (Memory Usage Monitor)

**位置**: `app/core/memory/memory_usage_monitor.py`

**功能**:
- 全面的记忆使用监控
- 8种监控指标：使用频率、相关性准确度、响应质量等
- 性能报告生成
- 异常检测和趋势分析

**核心类**:
```python
class MemoryUsageMonitor:
    - monitor_memory_usage()      # 监控记忆使用
    - generate_performance_report() # 生成性能报告
    - detect_anomalies()          # 检测异常
    - analyze_trends()            # 分析趋势
```

### 9. 自适应记忆优化器 (Adaptive Memory Optimizer)

**位置**: `app/core/memory/adaptive_memory_optimizer.py`

**功能**:
- 基于反馈的自适应学习
- 5种反馈类型：用户明确/隐式、系统性能、任务完成、质量评估
- 4种优化策略：保守、激进、平衡、自适应
- 参数自动调整和回滚机制

**核心类**:
```python
class AdaptiveMemoryOptimizer:
    - optimize_based_on_feedback() # 基于反馈优化
    - auto_adjust_parameters()     # 自动调整参数
    - evaluate_optimization_effect() # 评估优化效果
    - rollback_if_needed()         # 必要时回滚
```

## 数据流图

```mermaid
graph TB
    A[用户请求] --> B[智能体选择]
    B --> C[记忆筛选器]
    C --> D[相关性评分]
    D --> E[动态Prompt生成]
    E --> F[长度控制]
    F --> G[记忆注入]
    G --> H[智能体执行]
    H --> I[使用监控]
    I --> J[自适应优化]
    J --> K[反馈循环]
    K --> C
```

## 技术栈

- **核心框架**: LangGraph, LangChain
- **数据库**: PostgreSQL, MySQL, Elasticsearch, Redis
- **前端**: React (Next.js), Gradio
- **API**: FastAPI, WebSocket
- **AI模型**: OpenAI GPT, Claude, 本地模型
- **工具**: MinIO, FAISS, Numpy, Pandas

## 配置管理

### 环境变量配置

```bash
# 数据库配置
POSTGRES_URL=postgresql://user:password@localhost/db_name
MYSQL_URL=mysql://user:password@localhost/db_name
ELASTICSEARCH_URL=http://localhost:9200
REDIS_URL=redis://localhost:6379

# AI模型配置
OPENAI_API_KEY=sk-xxx
CLAUDE_API_KEY=sk-xxx
MODEL_PROVIDER=openai

# 记忆配置
MEMORY_NAMESPACE_ENABLED=true
MEMORY_FILTER_ENABLED=true
DYNAMIC_PROMPT_ENABLED=true
MEMORY_MONITOR_ENABLED=true
```

### 智能体配置

```yaml
agents:
  geophysics_analysis:
    role: "地球物理分析师"
    domain_weights:
      geophysics: 0.4
      data_analysis: 0.3
      geological_interpretation: 0.2
      technical_report: 0.1
    
  reservoir_engineering:
    role: "油藏工程师"
    domain_weights:
      reservoir_engineering: 0.4
      production_optimization: 0.3
      data_analysis: 0.2
      economic_evaluation: 0.1
```

## 性能指标

### 记忆系统性能

- **记忆筛选速度**: < 100ms (1000条记忆)
- **相关性评分准确度**: > 85%
- **Prompt生成时间**: < 50ms
- **记忆注入延迟**: < 20ms

### 系统整体性能

- **响应时间**: < 2s (普通查询)
- **并发处理**: 100个并发用户
- **内存使用**: < 2GB (单会话)
- **磁盘IO**: < 10MB/s (正常负载)

## 监控和运维

### 关键监控指标

1. **记忆使用率**: 各智能体的记忆使用频率
2. **筛选效果**: 记忆筛选的准确性和相关性
3. **响应质量**: 智能体回复的质量评分
4. **系统负载**: CPU、内存、磁盘使用情况

### 日志管理

```python
# 记忆操作日志
logger.info(f"记忆筛选: agent={agent_role}, query={query}, 
            found={len(memories)}, time={elapsed_time}ms")

# 性能监控日志
logger.info(f"性能指标: response_time={response_time}ms, 
            memory_usage={memory_usage}MB, quality_score={quality_score}")
```

## 扩展性设计

### 水平扩展

- **数据库分片**: 按智能体角色分片存储
- **缓存分层**: Redis缓存 + 本地缓存
- **负载均衡**: 多实例部署支持

### 垂直扩展

- **新增智能体角色**: 通过配置文件添加
- **自定义记忆筛选**: 插件化筛选器
- **扩展评分因子**: 可配置的评分维度

## 安全性设计

### 数据安全

- **敏感信息加密**: 记忆内容加密存储
- **访问权限控制**: 基于角色的访问控制
- **数据备份**: 定期备份重要数据

### 系统安全

- **API认证**: JWT令牌认证
- **输入验证**: 防止注入攻击
- **审计日志**: 完整的操作审计

## 故障处理

### 常见故障处理

1. **记忆检索失败**: 自动降级到基础检索
2. **AI模型不可用**: 切换到备用模型
3. **数据库连接失败**: 使用本地缓存
4. **网络超时**: 自动重试机制

### 恢复策略

- **自动恢复**: 系统自动检测并恢复
- **手动恢复**: 管理员手动干预
- **数据恢复**: 从备份恢复数据
- **服务降级**: 关闭非核心功能

## 版本管理

### 版本兼容性

- **向后兼容**: 支持旧版本API
- **数据迁移**: 自动数据格式迁移
- **配置升级**: 配置文件自动升级

### 发布流程

1. **开发测试**: 单元测试 + 集成测试
2. **预发布**: 在测试环境验证
3. **正式发布**: 灰度发布 + 全量发布
4. **监控验证**: 发布后监控验证

## 开发指南

### 添加新智能体

1. 在 `agent_memory_preferences.py` 中添加偏好配置
2. 在 `dynamic_prompt_manager.py` 中添加Prompt模板
3. 在 `specialized_agents.py` 中实现智能体逻辑
4. 更新配置文件和测试用例

### 自定义记忆筛选

1. 继承 `BaseMemoryFilter` 类
2. 实现 `filter_memories()` 方法
3. 在筛选器注册表中注册
4. 配置智能体使用新筛选器

### 扩展评分因子

1. 在 `RelevanceFactors` 枚举中添加新因子
2. 在 `MemoryRelevanceScorer` 中实现计算逻辑
3. 更新评分策略配置
4. 添加单元测试验证

---

*本文档版本: v2.0.0*  
*最后更新: 2024年12月*  
*维护人员: 系统架构团队* 