# PetroAgent - 智能地质分析系统前端

这是一个基于 Next.js 和 assistant-ui 构建的现代化前端界面，用于天然气碳同位素数据解释智能体系统。

## 🌟 功能特性

### 六大核心模块

1. **实时仪表盘** - 系统状态监控和项目进度概览
2. **地质建模中心** - AI驱动的地质建模工具，集成assistant-ui聊天界面
3. **工作流管理** - 任务编排和DAG可视化
4. **数据管理中心** - 多源数据集成和文件管理
5. **智能决策分析** - 甜点识别、资源评估、经济评价
6. **AI智能助手** - 自然语言交互和会话管理

### 技术亮点

- 🎨 **现代化UI设计** - 基于 Tailwind CSS 和 shadcn/ui 组件
- 🤖 **AI助手集成** - 使用 assistant-ui 和 LangGraph 运行时
- 📊 **实时数据可视化** - Recharts 图表和 Mermaid 工作流图
- 🔄 **流式数据处理** - 支持实时流式输出和WebSocket通信
- 📱 **响应式设计** - 适配各种屏幕尺寸
- 🌐 **国际化支持** - 中文界面和本地化

## 🚀 快速开始

### 前置要求

- Node.js 18+ 
- npm 或 yarn
- 后端API服务器运行在 `localhost:7102`

### 安装依赖

```bash
npm install
```

### 开发模式

```bash
npm run dev
```

访问 http://localhost:3000 查看应用

### 生产构建

```bash
npm run build
npm start
```

## 🏗️ 项目结构

```
app/ui/petro_agent/
├── app/                    # Next.js 应用目录
│   ├── layout.tsx         # 根布局
│   ├── page.tsx           # 主页面
│   └── globals.css        # 全局样式
├── components/            # React 组件
│   ├── ui/               # 基础UI组件
│   ├── assistant-ui/     # AI助手组件
│   ├── Dashboard.tsx     # 仪表盘组件
│   ├── GeologicalModelingHub.tsx  # 地质建模中心
│   ├── FileManager.tsx   # 文件管理器
│   ├── SessionManager.tsx # 会话管理器
│   └── DAGVisualization.tsx # DAG可视化
├── lib/                  # 工具库
│   ├── utils.ts         # 工具函数
│   └── chatApi.ts       # API客户端
└── package.json         # 项目配置
```

## 🔧 配置说明

### 环境变量

创建 `.env.local` 文件：

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:7102
NEXT_PUBLIC_LANGGRAPH_API_URL=http://localhost:7102/api/v1
NEXT_PUBLIC_LANGGRAPH_ASSISTANT_ID=your_assistant_id
```

### API 集成

前端通过以下API端点与后端通信：

- `GET /api/v1/system/status` - 系统状态
- `POST /api/v1/sessions` - 创建会话
- `GET /api/v1/sessions` - 获取会话列表
- `POST /api/v1/chat/send` - 发送消息
- `GET /api/v1/files` - 文件管理
- `POST /api/v1/files/upload` - 文件上传

## 🎯 核心组件说明

### Dashboard 组件
- 实时系统监控
- 项目进度跟踪
- 任务执行时间线
- 智能体状态面板

### GeologicalModelingHub 组件
- 左侧参数配置面板
- 中央3D模型视图
- 右侧AI助手聊天
- 模型质量验证

### FileManager 组件
- 文件上传和下载
- 文件类型识别
- 批量操作支持
- 会话文件管理

### SessionManager 组件
- 会话创建和删除
- 会话状态管理
- 历史会话浏览
- 元数据编辑

## 🔄 与后端集成

### LangGraph 集成
使用 `@assistant-ui/react-langgraph` 实现与后端LangGraph服务的无缝集成：

```typescript
const runtime = useLangGraphRuntime({
  threadId: sessionId,
  stream: async function* (messages, { command }) {
    // 流式处理实现
  },
});
```

### 实时通信
支持Server-Sent Events (SSE) 和 WebSocket 进行实时数据传输。

## 🎨 UI/UX 设计

### 设计原则
- **直观易用** - 清晰的信息架构和导航
- **响应式** - 适配桌面和移动设备
- **一致性** - 统一的设计语言和交互模式
- **可访问性** - 支持键盘导航和屏幕阅读器

### 主题系统
支持明暗主题切换，使用CSS变量实现主题定制。

## 📊 数据可视化

### 图表组件
- **Recharts** - 统计图表和数据分析
- **Mermaid** - 工作流程图和DAG可视化
- **Three.js** - 3D地质模型展示（规划中）

## 🔍 开发指南

### 添加新组件

1. 在 `components/` 目录创建组件文件
2. 使用 TypeScript 定义 props 接口
3. 遵循现有的命名约定
4. 添加适当的错误处理

### API 调用规范

```typescript
// 使用统一的错误处理
try {
  const response = await fetch(`${apiBaseUrl}/api/v1/endpoint`);
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  const data = await response.json();
  // 处理数据
} catch (error) {
  console.error('API调用失败:', error);
  // 错误处理
}
```

## 🧪 测试

```bash
# 运行测试
npm test

# 类型检查
npm run type-check

# 代码检查
npm run lint
```

## 📦 部署

### Docker 部署

```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
```

### 环境配置
- **开发环境**: `npm run dev`
- **测试环境**: `npm run build && npm start`
- **生产环境**: 使用 PM2 或 Docker 容器

## 🤝 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🆘 故障排除

### 常见问题

1. **构建失败** - 检查 Node.js 版本和依赖安装
2. **API连接失败** - 确认后端服务器运行状态
3. **样式问题** - 清除浏览器缓存或重新构建
4. **类型错误** - 运行 `npm run type-check` 检查类型

### 获取帮助

- 查看控制台错误信息
- 检查网络请求状态
- 确认环境变量配置
- 联系开发团队

---

**PetroAgent** - 让地质分析更智能，让决策更精准！
