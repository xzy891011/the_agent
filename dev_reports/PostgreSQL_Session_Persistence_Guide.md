# PostgreSQL会话持久化功能使用指南

## 概述

本项目已成功实现基于PostgreSQL的会话持久化功能，替换了原有的文件存储方式。该功能提供了更可靠、更高性能的会话状态管理，支持分布式部署和高并发访问。

## 功能特性

### 🔄 核心功能
- **会话状态持久化**：将会话状态保存到PostgreSQL数据库
- **自动恢复**：服务重启后自动从数据库恢复会话状态
- **会话过期管理**：支持设置会话过期时间，自动清理过期会话
- **统计信息**：提供详细的会话统计和监控信息
- **软删除**：支持软删除和硬删除会话

### 🏗️ 架构优势
- **高可用性**：基于PostgreSQL的可靠存储
- **分布式支持**：多个应用实例可共享会话状态
- **性能优化**：使用JSONB字段高效存储会话数据
- **事务安全**：确保会话状态的一致性
- **向后兼容**：保持对原有文件存储的兼容性

## 配置说明

### 1. 数据库配置

确保PostgreSQL数据库配置正确（在 `config/config.yaml` 中）：

```yaml
postgresql:
  host: localhost
  port: 5432
  user: sweet
  password: your_password
  database: isotope
```

### 2. 启用PostgreSQL会话持久化

#### 方法一：通过引擎配置
```python
from app.core.engine import IsotopeEngine

# 启用PostgreSQL会话持久化
engine = IsotopeEngine(
    config={
        "postgres_sessions": True,  # 启用PostgreSQL会话持久化
        "enhanced_graph": True      # 推荐同时启用增强图功能
    },
    enable_postgres_sessions=True,
    verbose=True
)
```

#### 方法二：通过配置文件
在配置文件中添加：
```yaml
postgres_sessions: true
```

### 3. 数据库表结构

系统会自动创建以下表结构：

```sql
CREATE TABLE isotope_sessions (
    session_id VARCHAR(255) PRIMARY KEY,
    session_data JSONB NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE,
    version INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE
);
```

包含以下索引：
- `idx_isotope_sessions_last_updated`
- `idx_isotope_sessions_created_at`
- `idx_isotope_sessions_is_active`
- `idx_isotope_sessions_expires_at`

## 使用方法

### 1. 基本会话操作

```python
from app.core.postgres_session_manager import get_postgres_session_manager

# 获取会话管理器
manager = get_postgres_session_manager()

# 保存会话
success = manager.save_session(
    session_id="my_session_id",
    session_data={
        "messages": [...],
        "metadata": {...},
        "files": {},
        "tasks": []
    },
    metadata={
        "name": "我的会话",
        "user_id": "user123"
    },
    expires_in_hours=24  # 24小时后过期
)

# 加载会话
session_data = manager.load_session("my_session_id")

# 列出会话
sessions = manager.list_sessions(limit=10, include_inactive=False)

# 删除会话
manager.delete_session("my_session_id", soft_delete=True)
```

### 2. 引擎集成使用

```python
from app.core.engine import IsotopeEngine

# 创建启用PostgreSQL会话持久化的引擎
engine = IsotopeEngine(enable_postgres_sessions=True)

# 创建会话（自动保存到PostgreSQL）
session_id = engine.create_session(
    metadata={"name": "新会话", "user_id": "user123"}
)

# 处理消息（会话状态自动保存到PostgreSQL）
for message in engine.resume_workflow(
    user_input="你好", 
    session_id=session_id, 
    stream=True
):
    print(message)

# 服务重启后自动恢复会话
# engine._restore_existing_sessions() 在初始化时自动调用
```

### 3. 会话统计和监控

```python
# 获取统计信息
stats = manager.get_session_statistics()
print(f"总会话数: {stats['total_sessions']}")
print(f"活跃会话数: {stats['active_sessions']}")
print(f"平均消息数: {stats['avg_messages_per_session']}")

# 清理过期会话
cleaned_count = manager.cleanup_expired_sessions()
print(f"清理了 {cleaned_count} 个过期会话")

# 恢复所有会话到内存
restore_result = manager.restore_all_sessions()
print(f"恢复了 {restore_result['restored_count']} 个会话")
```

## API端点

### PostgreSQL会话管理端点

#### 获取PostgreSQL会话列表
```
GET /api/sessions/postgres/sessions?limit=50&offset=0&include_inactive=false
```

#### 获取特定PostgreSQL会话
```
GET /api/sessions/postgres/sessions/{session_id}
```

#### 获取会话统计信息
```
GET /api/sessions/postgres/statistics
```

#### 恢复PostgreSQL会话到内存
```
POST /api/sessions/postgres/restore
```

#### 清理过期会话
```
POST /api/sessions/postgres/cleanup
```

#### 测试PostgreSQL连接
```
GET /api/sessions/postgres/connection/test
```

### 兼容性端点

#### 获取恢复会话信息（兼容原有API）
```
GET /api/sessions/restored
```

#### 手动触发会话恢复
```
POST /api/sessions/restore
```

## 工作流程

### 1. 会话创建流程
```
用户创建会话 → 引擎创建会话状态 → 保存到内存 → 同时保存到PostgreSQL
```

### 2. 会话更新流程
```
用户发送消息 → 引擎处理消息 → 更新会话状态 → 自动保存到PostgreSQL
```

### 3. 服务重启恢复流程
```
服务启动 → 检查PostgreSQL连接 → 恢复所有活跃会话 → 加载到内存 → 服务就绪
```

### 4. 会话过期清理流程
```
定期任务 → 扫描过期会话 → 标记为非活跃 → 可选择硬删除
```

## 性能优化

### 1. 数据库优化
- 使用JSONB字段高效存储会话数据
- 创建适当的索引加速查询
- 使用连接池管理数据库连接
- 启用自动提交减少事务开销

### 2. 序列化优化
- 智能处理不可序列化对象
- 跳过大型对象（如MemoryStore）
- 保留关键信息（如LangChain消息）

### 3. 内存管理
- 优先从PostgreSQL恢复会话
- 回退到文件检查点
- 及时清理过期会话

## 故障处理

### 1. PostgreSQL连接失败
- 系统会自动回退到文件存储
- 记录详细错误日志
- 不影响系统正常运行

### 2. 会话序列化错误
- 跳过不可序列化对象
- 记录警告信息
- 保存可序列化部分

### 3. 会话恢复失败
- 记录失败的会话ID
- 继续恢复其他会话
- 提供详细的错误统计

## 测试验证

### 运行基本测试
```bash
conda activate sweet
python simple_postgres_test.py
```

### 运行完整测试
```bash
conda activate sweet
python test_postgres_session_persistence.py
```

### 测试API端点
```bash
# 测试PostgreSQL连接
curl http://localhost:8000/api/sessions/postgres/connection/test

# 获取会话统计
curl http://localhost:8000/api/sessions/postgres/statistics

# 恢复会话
curl -X POST http://localhost:8000/api/sessions/postgres/restore
```

## 监控和维护

### 1. 定期监控
- 检查会话数量增长趋势
- 监控数据库性能
- 关注过期会话清理情况

### 2. 维护任务
- 定期清理过期会话
- 备份重要会话数据
- 优化数据库索引

### 3. 日志监控
- 关注连接失败日志
- 监控序列化错误
- 跟踪恢复成功率

## 最佳实践

### 1. 会话管理
- 设置合理的过期时间
- 及时清理不需要的会话
- 使用有意义的会话元数据

### 2. 性能优化
- 避免存储过大的会话数据
- 定期清理过期会话
- 监控数据库性能

### 3. 安全考虑
- 保护数据库连接信息
- 定期备份会话数据
- 使用适当的访问控制

## 故障排除

### 常见问题

#### 1. PostgreSQL连接失败
```
错误: PostgreSQL连接测试失败
解决: 检查数据库配置和网络连接
```

#### 2. 会话序列化错误
```
错误: can't compare offset-naive and offset-aware datetimes
解决: 已修复时区处理问题，更新到最新版本
```

#### 3. 会话恢复失败
```
错误: 会话恢复时出现异常
解决: 检查数据库表结构和权限
```

### 调试方法

#### 1. 启用详细日志
```python
engine = IsotopeEngine(verbose=True, enable_postgres_sessions=True)
```

#### 2. 检查数据库状态
```sql
SELECT COUNT(*) FROM isotope_sessions WHERE is_active = true;
SELECT * FROM isotope_sessions ORDER BY last_updated DESC LIMIT 10;
```

#### 3. 测试连接
```python
from app.core.postgres_session_manager import get_postgres_session_manager
manager = get_postgres_session_manager()
print(manager.test_connection())
```

## 总结

PostgreSQL会话持久化功能为系统提供了：

✅ **可靠性**：基于PostgreSQL的持久化存储  
✅ **性能**：高效的JSONB存储和索引  
✅ **扩展性**：支持分布式部署  
✅ **兼容性**：保持向后兼容  
✅ **监控**：完整的统计和监控功能  

该功能已通过完整测试，可以在生产环境中安全使用。 