# 流式输出模块使用指南

## 概述

我们已经重新设计并实现了流式输出模块，支持丰富的流式消息类型和前端差异化显示。该模块充分利用了LangGraph和Vercel AI SDK的现成机制。

### ⚠️ 重要更新 (2024)

为了避免功能重复和职责混淆，我们已将**流式消息推送功能**统一迁移到 `app/core/stream_writer_helper.py`：

- **删除**：`streaming_processor.py` 中的 `push_*` 函数
- **保留**：`stream_writer_helper.py` 中的完整推送功能
- **职责明确**：
  - `streaming_processor.py` - 专门负责**处理和解析**流式数据
  - `stream_writer_helper.py` - 专门负责**推送消息**到流中

请更新您的代码导入：
```python
# ✅ 正确用法
from app.core.stream_writer_helper import push_thinking, push_file, push_progress

# ❌ 已删除，不再可用
from app.ui.streaming_processor import push_thinking_message
```

## 架构设计

### 🏗️ 系统架构

```
后端流式处理器 (app/ui/streaming_processor.py)
           ↓
    LangGraph Stream Writer
           ↓
     SSE流 (Server-Sent Events)
           ↓
前端流式处理器 (lib/use-stream-processor.ts)
           ↓
   React组件显示 (components/stream-messages.tsx)
           ↓
文件树集成管理器 (lib/file-tree-integration.ts)
```

### 📦 核心组件

| 组件 | 路径 | 功能 |
|-----|------|-----|
| **后端流式处理器** | `app/ui/streaming_processor.py` | 监听LangGraph事件，生成流式消息 |
| **后端消息类型** | `app/ui/streaming_types.py` | 流式消息类型定义 |
| **前端消息类型** | `lib/streaming-types.ts` | 前端消息类型定义（与后端一致） |
| **前端流式处理器** | `lib/use-stream-processor.ts` | React Hook，处理流式消息 |
| **文件树集成管理器** | `lib/file-tree-integration.ts` | 自动处理文件生成事件 |
| **消息显示组件** | `components/stream-messages.tsx` | 各种消息类型的React显示组件 |
| **SSE API路由** | `app/api/stream/route.ts` | 前端SSE连接端点 |

## 🌊 流式消息类型

### 1. 节点状态消息 (Node Status)
- `node_start`: 节点开始执行
- `node_end`: 节点执行完成
- `node_error`: 节点执行错误

### 2. 路由决策消息 (Router)
- `router_decision`: 路由决策
- `router_path`: 路径选择

### 3. LLM相关消息
- `llm_token`: LLM token流
- `llm_start`: LLM开始生成
- `llm_end`: LLM生成结束

### 4. 工具执行消息 (Tool)
- `tool_start`: 工具开始执行
- `tool_progress`: 工具执行进度
- `tool_result`: 工具执行结果
- `tool_error`: 工具执行错误

### 5. 文件操作消息 (File)
- `file_generated`: 文件已生成
- `file_uploaded`: 文件已上传
- `file_processed`: 文件已处理

### 6. Agent思考消息
- `agent_thinking`: Agent思考过程
- `agent_planning`: Agent制定计划
- `agent_decision`: Agent做出决策

### 7. 系统消息
- `system_info`: 系统信息
- `system_warning`: 系统警告
- `system_error`: 系统错误

## 💻 使用方法

### 后端使用

#### 1. 创建流式处理器实例

```python
from app.ui.streaming_processor import LangGraphStreamingProcessor

# 创建处理器
processor = LangGraphStreamingProcessor(
    session_id="your-session-id",
    file_manager=your_file_manager,
    enable_debug=True
)

# 处理LangGraph流
for chunk in graph.stream(inputs, stream_mode=["messages", "custom"]):
    processor.process_chunk(chunk)
```

#### 2. 推送自定义消息（使用 stream_writer_helper）

```python
# 导入流式消息推送工具
from app.core.stream_writer_helper import push_progress, push_file, push_thinking

# 推送工具进度消息
push_progress(
    tool_name="data_analysis",
    progress=0.5,  # 进度百分比 (0.0-1.0)
    details="正在分析数据..."
)

# 推送文件生成消息
push_file(
    file_id="file-123",
    file_name="analysis_result.png",
    file_path="generated/charts/analysis_result.png",
    file_type="image"
)

# 推送Agent思考消息
push_thinking(
    agent_name="DataAgent",
    content="正在分析数据的统计特征和分布模式...",
    thinking_type="analysis"
)
```

### 前端使用

#### 1. 集成到React组件

```tsx
import { useStreamProcessor } from '../lib/use-stream-processor';
import { useFileTreeIntegration } from '../lib/file-tree-integration';
import { StreamMessageDisplay } from './stream-messages';

function ChatComponent({ sessionId }: { sessionId: string }) {
  // 流式消息处理器
  const streamProcessor = useStreamProcessor({
    sessionId,
    enableDebugLogs: true,
    onFileGenerated: (file) => console.log('文件生成:', file),
    onToolProgress: (tool) => console.log('工具进度:', tool),
    onAgentThinking: (thinking) => console.log('Agent思考:', thinking),
  });

  // 文件树集成管理器
  const fileTreeManager = useFileTreeIntegration({
    sessionId,
    enableAutoClassification: true,
    enableAutoRefresh: true,
    onFileAdded: (file) => console.log('文件已添加:', file),
  });

  return (
    <div>
      {/* 显示执行状态 */}
      <div className="status-bar">
        <Badge variant={streamProcessor.isExecuting ? "default" : "outline"}>
          {streamProcessor.isExecuting ? '执行中' : '空闲'}
        </Badge>
        {streamProcessor.currentActivity && (
          <Badge variant="secondary">{streamProcessor.currentActivity}</Badge>
        )}
      </div>

      {/* 流式消息显示 */}
      <div className="messages">
        {streamProcessor.messages.map(message => (
          <StreamMessageDisplay
            key={message.id}
            message={message}
            onFileView={(file) => {/* 查看文件 */}}
            onFileDownload={(file) => fileTreeManager.downloadFile(file)}
          />
        ))}
      </div>

      {/* 文件统计 */}
      <div className="file-stats">
        <p>总文件: {fileTreeManager.stats.totalFiles}</p>
        <p>生成文件: {fileTreeManager.stats.generatedFiles}</p>
        <p>上传文件: {fileTreeManager.stats.uploadedFiles}</p>
      </div>
    </div>
  );
}
```

#### 2. 监听SSE流式消息

```tsx
useEffect(() => {
  if (!sessionId) return;

  const eventSource = new EventSource(`/api/stream?sessionId=${sessionId}`);
  
  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    streamProcessor.addMessage(data);
  };
  
  return () => eventSource.close();
}, [sessionId]);
```

## 🎨 前端显示样式

### 消息类型样式设计

| 消息类型 | 颜色主题 | 图标 | 特殊功能 |
|---------|---------|------|---------|
| **节点状态** | 蓝色/绿色/红色 | Play/CheckCircle/XCircle | 状态标记 |
| **路由决策** | 紫色 | Route | 置信度显示 |
| **工具执行** | 橙色/蓝色 | Settings/Loader2 | 进度条 |
| **文件生成** | 绿色 | FileText | 查看/下载按钮 |
| **Agent思考** | 紫色 | Brain | 步骤进度 |
| **系统消息** | 蓝色/黄色/红色 | Info/AlertTriangle | 操作建议 |

### 样式示例

```tsx
// 工具执行消息 - 带进度条
<Card className="bg-orange-50 border-orange-200">
  <CardContent className="p-3">
    <div className="flex items-center space-x-2">
      <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
      <span className="font-medium">数据分析工具</span>
      <Badge variant="outline">执行中</Badge>
    </div>
    <Progress value={75} className="mt-2" />
    <span className="text-xs text-gray-500">75%</span>
  </CardContent>
</Card>

// 文件生成消息 - 带操作按钮
<Card className="bg-green-50 border-green-200">
  <CardContent className="p-3">
    <div className="flex items-center justify-between">
      <div className="flex items-center space-x-2">
        <FileText className="h-4 w-4 text-green-600" />
        <span className="font-medium">analysis_result.png</span>
        <Badge variant="outline">文件已生成</Badge>
      </div>
      <div className="flex space-x-2">
        <Button size="sm" variant="outline">
          <Eye className="h-3 w-3 mr-1" />查看
        </Button>
        <Button size="sm" variant="outline">
          <Download className="h-3 w-3 mr-1" />下载
        </Button>
      </div>
    </div>
  </CardContent>
</Card>
```

## 🗂️ 文件树集成

### 自动文件分类规则

```typescript
const DEFAULT_FILE_CATEGORIES = [
  {
    pattern: /\.(png|jpg|jpeg|gif|svg)$/i,
    folder: 'generated/charts',
    priority: 10,
    description: '生成的图表和图像文件'
  },
  {
    pattern: /\.(csv|xlsx|xls)$/i,
    folder: 'input/data',
    priority: 8,
    description: '数据文件'
  },
  {
    pattern: /\.(las|log)$/i,
    folder: 'input/logs',
    priority: 9,
    description: '测井数据文件'
  },
  {
    pattern: /report|analysis/i,
    folder: 'generated/reports',
    priority: 8,
    description: '分析报告'
  }
];
```

### 文件操作功能

```typescript
// 自动分类和移动文件
fileTreeManager.handleFileGenerated(fileMessage);

// 手动移动文件到文件夹
await fileTreeManager.moveFileToFolder('file-123', 'generated/charts');

// 创建新文件夹
await fileTreeManager.createFolder('custom/analysis');

// 下载文件
await fileTreeManager.downloadFile(fileItem);

// 获取文件预览URL
const previewUrl = fileTreeManager.getFilePreviewUrl(fileItem);
```

## 🔧 配置选项

### 流式处理器配置

```typescript
interface StreamProcessorConfig {
  sessionId: string;
  apiBaseUrl?: string;
  enableDebugLogs?: boolean;
  onFileGenerated?: (file: FileGeneratedMessage) => void;
  onToolProgress?: (tool: ToolExecutionMessage) => void;
  onAgentThinking?: (thinking: AgentThinkingMessage) => void;
  onSystemMessage?: (system: SystemMessage) => void;
  onNodeStatusChange?: (node: NodeStatusMessage) => void;
}
```

### 文件树集成配置

```typescript
interface FileTreeIntegrationConfig {
  sessionId: string;
  apiBaseUrl?: string;
  categories?: FileCategoryConfig[];
  enableAutoClassification?: boolean;
  enableAutoRefresh?: boolean;
  refreshInterval?: number;
  onFileAdded?: (file: FileItem) => void;
  onFileRemoved?: (fileId: string) => void;
  onFolderCreated?: (folderPath: string) => void;
  enableDebugLogs?: boolean;
}
```

## 🚀 部署和测试

### 1. 启动前端开发服务器

```bash
cd app/ui/petro_agent
npm run dev
```

### 2. 测试流式消息功能

1. 打开浏览器开发者工具
2. 进入"地质建模中心"
3. 开始对话，观察流式消息显示
4. 检查Network标签页中的SSE连接
5. 查看Console中的流式消息日志

### 3. 验证文件树集成

1. 上传文件或生成文件
2. 观察文件是否自动分类到正确文件夹
3. 测试文件预览和下载功能
4. 验证文件树自动刷新

## 📋 待优化事项

1. **性能优化**
   - 消息批处理
   - 虚拟滚动
   - 消息缓存清理

2. **用户体验**
   - 消息过滤和搜索
   - 消息导出功能
   - 自定义显示样式

3. **错误处理**
   - 连接断线重连
   - 消息重传机制
   - 优雅降级

4. **安全性**
   - 消息验证
   - 会话权限检查
   - XSS防护

## 🎯 总结

新的流式输出模块实现了：

✅ **丰富的消息类型** - 支持节点、工具、文件、Agent思考等多种消息类型
✅ **差异化显示** - 每种消息类型都有独特的视觉样式和交互功能  
✅ **文件树集成** - 自动处理文件生成事件，智能分类存放
✅ **实时状态监控** - 显示执行状态、进度、错误等信息
✅ **现代化架构** - 充分利用LangGraph和Vercel AI SDK机制
✅ **良好的可扩展性** - 易于添加新的消息类型和显示样式

该系统为用户提供了丰富的实时反馈，大大提升了交互体验和系统可观测性。 