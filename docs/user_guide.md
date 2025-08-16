# 天然气碳同位素智能分析系统 - 用户指南

## 快速开始

### 系统要求

- **操作系统**: Linux (推荐 Ubuntu 20.04+)
- **Python**: 3.9+ (推荐 3.10)
- **内存**: 8GB+ (推荐 16GB)
- **存储**: 50GB+ 可用空间
- **GPU**: 可选，用于加速AI模型推理

### 环境准备

1. **创建虚拟环境**
```bash
# 创建conda环境
conda create -n sweet python=3.10
conda activate sweet

# 或使用venv
python -m venv sweet
source sweet/bin/activate  # Linux/Mac
# sweet\Scripts\activate  # Windows
```

2. **安装依赖**
```bash
# 在项目根目录下
pip install -r requirements.txt

# 如果使用GPU
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### 配置文件设置

1. **复制配置模板**
```bash
cp .env.example .env
cp config/config.example.yaml config/config.yaml
```

2. **编辑环境变量** (`.env`)
```bash
# 基础配置
OPENAI_API_KEY=sk-your-openai-key
CLAUDE_API_KEY=sk-your-claude-key
MODEL_PROVIDER=openai

# 数据库配置
POSTGRES_URL=postgresql://user:password@localhost:5432/isotope_db
MYSQL_URL=mysql://user:password@localhost:3306/isotope_db
ELASTICSEARCH_URL=http://localhost:9200
REDIS_URL=redis://localhost:6379

# 记忆系统配置
MEMORY_NAMESPACE_ENABLED=true
MEMORY_FILTER_ENABLED=true
DYNAMIC_PROMPT_ENABLED=true
MEMORY_MONITOR_ENABLED=true

# 文件存储
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
```

3. **配置智能体参数** (`config/config.yaml`)
```yaml
# AI模型配置
model:
  provider: "openai"
  name: "gpt-4"
  temperature: 0.1
  max_tokens: 4000

# 记忆系统配置
memory:
  namespace_enabled: true
  filter_enabled: true
  dynamic_prompt_enabled: true
  monitor_enabled: true
  
  # 智能体记忆偏好
  agent_preferences:
    geophysics_analysis:
      domain_weights:
        geophysics: 0.4
        data_analysis: 0.3
        geological_interpretation: 0.2
        technical_report: 0.1
      time_decay_factor: 0.1
      max_memory_items: 50
      
    reservoir_engineering:
      domain_weights:
        reservoir_engineering: 0.4
        production_optimization: 0.3
        data_analysis: 0.2
        economic_evaluation: 0.1
      time_decay_factor: 0.1
      max_memory_items: 50

# 数据库配置
database:
  postgres:
    enabled: true
    checkpoint_enabled: true
    session_persistence: true
  
  mysql:
    enabled: false
    checkpoint_enabled: false
    
  elasticsearch:
    enabled: true
    memory_search: true
    
  redis:
    enabled: true
    caching: true
    session_timeout: 3600
```

### 数据库初始化

1. **PostgreSQL设置**
```bash
# 创建数据库
createdb isotope_db

# 运行初始化脚本
python scripts/init_database.py --db postgres
```

2. **Elasticsearch设置**
```bash
# 启动Elasticsearch
docker run -d --name elasticsearch \
  -p 9200:9200 -p 9300:9300 \
  -e "discovery.type=single-node" \
  elasticsearch:8.8.0

# 创建索引
python scripts/init_elasticsearch.py
```

3. **Redis设置**
```bash
# 启动Redis
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

## 系统启动

### 方式1: 传统Gradio界面

```bash
# 在conda环境中
conda activate sweet

# 启动Gradio界面
python run_ui.py
```

访问地址: `http://localhost:7860`

### 方式2: 现代React前端

```bash
# 启动后端API服务
conda activate sweet
python -m app.api.main

# 启动前端界面 (新终端)
cd app/ui/petro_agent
npm install
npm run dev
```

- 后端API: `http://localhost:7102`
- 前端界面: `http://localhost:3000`

## 功能使用指南

### 智能体对话

1. **选择智能体角色**
   - 地球物理分析师: 处理地球物理数据解释
   - 油藏工程师: 进行油藏工程分析
   - 经济评价师: 进行经济效益评估
   - 质量控制师: 进行质量检查和验证

2. **输入查询**
   - 支持自然语言查询
   - 支持文件上传分析
   - 支持多轮对话

3. **获取结果**
   - 文本回答
   - 图表可视化
   - 分析报告
   - 数据下载

### 记忆系统使用

1. **自动记忆**
   - 系统自动保存对话历史
   - 智能提取重要信息
   - 按角色和领域分类存储

2. **记忆检索**
   - 根据当前查询自动检索相关记忆
   - 支持语义搜索
   - 支持时间范围筛选

3. **记忆管理**
   - 查看记忆列表
   - 手动添加重要记忆
   - 删除过期记忆

### 文件管理

1. **上传文件**
   - 支持Excel、CSV、PDF、图片等格式
   - 自动识别文件类型
   - 关联到对应会话

2. **文件分析**
   - 自动解析数据结构
   - 生成数据摘要
   - 执行预定义分析

3. **结果导出**
   - 分析结果导出
   - 图表保存
   - 报告生成

## 高级功能

### 自定义智能体

1. **创建新角色**
```python
# 在 app/core/memory/agent_memory_preferences.py 中添加
AgentRole.CUSTOM_ANALYST = "custom_analyst"

# 配置记忆偏好
preferences[AgentRole.CUSTOM_ANALYST] = AgentPreference(
    agent_role=AgentRole.CUSTOM_ANALYST,
    domain_weights={
        DomainTag.CUSTOM_DOMAIN: 0.6,
        DomainTag.DATA_ANALYSIS: 0.3,
        DomainTag.TECHNICAL_REPORT: 0.1
    },
    time_decay_factor=0.1,
    max_memory_items=50
)
```

2. **配置Prompt模板**
```python
# 在 app/core/memory/dynamic_prompt_manager.py 中添加
templates[AgentRole.CUSTOM_ANALYST] = PromptTemplate(
    agent_role=AgentRole.CUSTOM_ANALYST,
    style=PromptStyle.ANALYTICAL,
    sections=[
        PromptSection.SYSTEM_IDENTITY,
        PromptSection.ROLE_DESCRIPTION,
        PromptSection.MEMORY_SECTION,
        PromptSection.INSTRUCTIONS
    ],
    memory_integration_strategy="domain_focused"
)
```

### 记忆筛选配置

1. **调整筛选策略**
```yaml
# config/config.yaml
memory:
  filter_strategy: "balanced"  # conservative, balanced, aggressive
  relevance_threshold: 0.7
  max_memories_per_request: 10
  enable_semantic_search: true
```

2. **自定义评分权重**
```yaml
memory:
  scoring_weights:
    semantic_similarity: 0.3
    task_relevance: 0.25
    time_decay: 0.15
    domain_match: 0.2
    agent_preference: 0.1
```

### 性能优化

1. **缓存配置**
```yaml
caching:
  redis_enabled: true
  memory_cache_size: 1000
  cache_ttl: 3600
  enable_result_caching: true
```

2. **并发控制**
```yaml
performance:
  max_concurrent_requests: 10
  request_timeout: 30
  memory_filter_timeout: 5
  prompt_generation_timeout: 3
```

## 监控和维护

### 系统监控

1. **性能指标查看**
```bash
# 查看系统状态
curl http://localhost:7102/api/v1/system/status

# 查看记忆使用统计
curl http://localhost:7102/api/v1/system/metrics
```

2. **日志查看**
```bash
# 查看应用日志
tail -f logs/app.log

# 查看记忆系统日志
tail -f logs/memory.log

# 查看性能日志
tail -f logs/performance.log
```

### 数据维护

1. **定期清理**
```bash
# 清理过期记忆
python scripts/cleanup_expired_memories.py

# 清理临时文件
python scripts/cleanup_temp_files.py

# 数据库优化
python scripts/optimize_database.py
```

2. **备份恢复**
```bash
# 备份数据库
python scripts/backup_database.py

# 恢复数据库
python scripts/restore_database.py --backup-file backup.sql
```

## 常见问题解答

### Q: 系统启动失败，显示数据库连接错误

**A**: 检查数据库配置和服务状态
```bash
# 检查PostgreSQL状态
systemctl status postgresql

# 检查连接
psql -U user -d isotope_db -h localhost

# 检查环境变量
echo $POSTGRES_URL
```

### Q: 记忆筛选很慢，如何优化？

**A**: 调整筛选配置和缓存设置
```yaml
memory:
  filter_strategy: "conservative"  # 使用保守策略
  enable_caching: true
  cache_size: 2000
  max_memories_per_request: 5  # 减少每次请求的记忆数量
```

### Q: AI模型响应超时

**A**: 检查网络连接和模型配置
```bash
# 测试API连接
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
  https://api.openai.com/v1/models

# 调整超时设置
MODEL_TIMEOUT=60  # 增加超时时间
```

### Q: 如何添加新的智能体角色？

**A**: 按照以下步骤添加：

1. 在 `agent_memory_preferences.py` 中添加角色和偏好
2. 在 `dynamic_prompt_manager.py` 中添加Prompt模板
3. 在配置文件中添加角色配置
4. 重启系统使配置生效

### Q: 记忆系统占用内存过多

**A**: 调整记忆配置参数
```yaml
memory:
  max_memory_items: 30  # 减少最大记忆数量
  memory_cleanup_interval: 3600  # 增加清理频率
  enable_memory_compression: true  # 启用内存压缩
```

### Q: 如何查看记忆使用统计？

**A**: 使用API接口查看
```bash
# 查看整体统计
curl http://localhost:7102/api/v1/system/metrics

# 查看特定智能体的记忆使用
curl http://localhost:7102/api/v1/system/memory-stats?agent=geophysics_analysis
```

### Q: 前端界面加载缓慢

**A**: 优化前端配置
```javascript
// next.config.js
module.exports = {
  experimental: {
    outputStandalone: true,
  },
  compress: true,
  images: {
    unoptimized: true
  }
}
```

## 故障排除

### 1. 系统启动问题

**症状**: 系统无法正常启动
**排查步骤**:
```bash
# 1. 检查Python环境
python --version
pip list | grep langchain

# 2. 检查配置文件
python -c "from app.core.config import ConfigManager; print(ConfigManager().load_config())"

# 3. 检查数据库连接
python -c "from app.core.postgres_checkpoint import PostgresCheckpoint; print('DB OK')"

# 4. 查看详细错误日志
python run_ui.py --debug
```

### 2. 性能问题

**症状**: 系统响应缓慢
**排查步骤**:
```bash
# 1. 检查系统资源
top -p $(pgrep -f "python.*run_ui.py")

# 2. 分析慢查询
tail -f logs/performance.log | grep "slow"

# 3. 检查缓存命中率
redis-cli info stats | grep cache

# 4. 优化配置
# 减少max_memory_items
# 启用缓存
# 调整并发数
```

### 3. 记忆系统问题

**症状**: 记忆检索不准确
**排查步骤**:
```bash
# 1. 检查记忆数据
python scripts/debug_memory.py --session-id SESSION_ID

# 2. 测试筛选器
python scripts/test_memory_filter.py --agent geophysics_analysis

# 3. 调整评分权重
# 修改 config/config.yaml 中的 scoring_weights

# 4. 重建记忆索引
python scripts/rebuild_memory_index.py
```

## 最佳实践

### 1. 系统配置

- 使用SSD存储提高数据库性能
- 配置足够的内存避免频繁交换
- 定期清理过期数据和日志文件
- 启用Redis缓存提升响应速度

### 2. 记忆管理

- 定期检查记忆质量和相关性
- 根据使用情况调整智能体偏好
- 监控记忆使用统计，及时优化
- 备份重要的记忆数据

### 3. 性能优化

- 合理设置并发数和超时时间
- 启用缓存机制减少重复计算
- 定期优化数据库索引
- 监控系统资源使用情况

### 4. 安全管理

- 定期更新API密钥
- 使用HTTPS保护数据传输
- 限制文件上传大小和类型
- 定期备份重要数据

---

*本指南版本: v2.0.0*  
*最后更新: 2024年12月*  
*技术支持: 开发团队* 