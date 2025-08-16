# Ollama嵌入模型配置说明

## 环境变量配置

在项目根目录下的 `.env` 文件中添加以下配置：

```bash
# Ollama服务地址
OLLAMA_BASE_URL=http://localhost:11434

# 嵌入模型名称
OLLAMA_EMBEDDING_MODEL=bge-m3:latest
```

## 模型准备

确保您已经安装并启动了Ollama服务，并拉取了bge-m3模型：

```bash
# 启动Ollama服务
ollama serve

# 拉取bge-m3模型
ollama pull bge-m3:latest
```

## 验证配置

您可以通过以下命令验证模型是否正常工作：

```bash
# 列出已安装的模型
ollama list

# 测试嵌入功能
curl http://localhost:11434/api/embeddings \
  -d '{
    "model": "bge-m3:latest",
    "prompt": "测试文本"
  }'
```

## 模型特性

bge-m3:latest 是一个高质量的多语言嵌入模型，支持：
- 中文和英文文本嵌入
- 1024维向量输出
- 优秀的语义理解能力
- 适合检索增强生成(RAG)任务

## 故障排除

1. **连接失败**: 检查OLLAMA_BASE_URL是否正确
2. **模型未找到**: 确保已通过`ollama pull bge-m3:latest`下载模型
3. **向量维度不匹配**: 确保Elasticsearch索引使用1024维度配置 