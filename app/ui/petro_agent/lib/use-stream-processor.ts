import { useState, useEffect, useCallback, useRef } from 'react';
import { 
  StreamMessage, 
  StreamMessageType, 
  parseStreamMessage,
  isFileMessage,
  isNodeMessage,
  isToolMessage,
  isAgentMessage,
  isSystemMessage,
  FileGeneratedMessage,
  ToolExecutionMessage,
  AgentThinkingMessage,
  SystemMessage,
  NodeStatusMessage
} from './streaming-types';

// 流式消息处理器配置
interface StreamProcessorConfig {
  sessionId: string;
  apiBaseUrl?: string;
  onFileGenerated?: (file: FileGeneratedMessage) => void;
  onToolProgress?: (tool: ToolExecutionMessage) => void;
  onAgentThinking?: (thinking: AgentThinkingMessage) => void;
  onSystemMessage?: (system: SystemMessage) => void;
  onNodeStatusChange?: (node: NodeStatusMessage) => void;
  enableDebugLogs?: boolean;
}

// 消息统计接口
interface MessageStats {
  totalMessages: number;
  nodeMessages: number;
  toolMessages: number;
  fileMessages: number;
  agentMessages: number;
  systemMessages: number;
  errorCount: number;
}

// 当前执行状态
interface ExecutionState {
  currentNode?: string;
  currentTool?: string;
  isThinking: boolean;
  activeTools: Set<string>;
  generatedFiles: FileGeneratedMessage[];
}

export function useStreamProcessor(config: StreamProcessorConfig) {
  const [messages, setMessages] = useState<StreamMessage[]>([]);
  const [stats, setStats] = useState<MessageStats>({
    totalMessages: 0,
    nodeMessages: 0,
    toolMessages: 0,
    fileMessages: 0,
    agentMessages: 0,
    systemMessages: 0,
    errorCount: 0
  });
  
  const [executionState, setExecutionState] = useState<ExecutionState>({
    isThinking: false,
    activeTools: new Set(),
    generatedFiles: []
  });

  const messageBuffer = useRef<Map<string, StreamMessage>>(new Map());
  const processingQueue = useRef<StreamMessage[]>([]);
  const isProcessing = useRef(false);

  // 调试日志函数
  const debugLog = useCallback((message: string, data?: any) => {
    if (config.enableDebugLogs) {
      console.log(`[StreamProcessor] ${message}`, data);
    }
  }, [config.enableDebugLogs]);

  // 处理单个流式消息
  const processMessage = useCallback((message: StreamMessage) => {
    debugLog(`处理消息: ${message.type}`, message);
    
    // 更新统计信息
    setStats(prev => {
      const newStats = { ...prev, totalMessages: prev.totalMessages + 1 };
      
      if (isNodeMessage(message)) newStats.nodeMessages++;
      if (isToolMessage(message)) newStats.toolMessages++;
      if (isFileMessage(message)) newStats.fileMessages++;
      if (isAgentMessage(message)) newStats.agentMessages++;
      if (isSystemMessage(message)) newStats.systemMessages++;
      
      // 检查错误消息
      if (message.type.includes('error') || message.priority === 'critical') {
        newStats.errorCount++;
      }
      
      return newStats;
    });

    // 更新执行状态
    setExecutionState(prev => {
      const newState = { ...prev };
      
      if (isNodeMessage(message)) {
        if (message.type === StreamMessageType.NODE_START) {
          newState.currentNode = message.node_name;
        } else if (message.type === StreamMessageType.NODE_END) {
          newState.currentNode = undefined;
        }
      }
      
      if (isToolMessage(message)) {
        if (message.type === StreamMessageType.TOOL_START) {
          newState.activeTools = new Set([...prev.activeTools, message.tool_name]);
          newState.currentTool = message.tool_name;
        } else if (message.type === StreamMessageType.TOOL_RESULT || message.type === StreamMessageType.TOOL_ERROR) {
          const newActiveTools = new Set(prev.activeTools);
          newActiveTools.delete(message.tool_name);
          newState.activeTools = newActiveTools;
          if (newState.currentTool === message.tool_name) {
            newState.currentTool = undefined;
          }
        }
      }
      
      if (isAgentMessage(message)) {
        newState.isThinking = message.type === StreamMessageType.AGENT_THINKING;
      }
      
      if (isFileMessage(message)) {
        newState.generatedFiles = [...prev.generatedFiles, message as FileGeneratedMessage];
      }
      
      return newState;
    });

    // 调用相应的回调函数
    try {
      if (isFileMessage(message)) {
        config.onFileGenerated?.(message as FileGeneratedMessage);
      }
      
      if (isToolMessage(message)) {
        config.onToolProgress?.(message as ToolExecutionMessage);
      }
      
      if (isAgentMessage(message)) {
        config.onAgentThinking?.(message as AgentThinkingMessage);
      }
      
      if (isSystemMessage(message)) {
        config.onSystemMessage?.(message as SystemMessage);
      }
      
      if (isNodeMessage(message)) {
        config.onNodeStatusChange?.(message as NodeStatusMessage);
      }
    } catch (error) {
      console.error('[StreamProcessor] 回调函数执行错误:', error);
    }
    
    // 添加到消息历史
    setMessages(prev => [...prev, message]);
    
  }, [config, debugLog]);

  // 批处理消息队列
  const processBatch = useCallback(async () => {
    if (isProcessing.current || processingQueue.current.length === 0) {
      return;
    }
    
    isProcessing.current = true;
    
    try {
      const batch = processingQueue.current.splice(0, 10); // 每批处理10条消息
      
      for (const message of batch) {
        await processMessage(message);
      }
      
      // 如果队列还有消息，继续处理
      if (processingQueue.current.length > 0) {
        setTimeout(processBatch, 10); // 10ms后处理下一批
      }
    } catch (error) {
      console.error('[StreamProcessor] 批处理错误:', error);
    } finally {
      isProcessing.current = false;
    }
  }, [processMessage]);

  // 添加消息到处理队列
  const addMessage = useCallback((data: any) => {
    const message = parseStreamMessage(data);
    if (!message) {
      debugLog('无法解析消息', data);
      return;
    }
    
    // 防重复处理
    const messageKey = `${message.type}-${message.id}-${message.timestamp}`;
    if (messageBuffer.current.has(messageKey)) {
      debugLog('重复消息，跳过', message);
      return;
    }
    
    messageBuffer.current.set(messageKey, message);
    processingQueue.current.push(message);
    
    // 启动批处理
    processBatch();
  }, [debugLog, processBatch]);

  // 清理消息缓冲区（防止内存泄漏）
  useEffect(() => {
    const cleanupInterval = setInterval(() => {
      const now = Date.now();
      const cutoff = now - 5 * 60 * 1000; // 5分钟前的消息
      
      for (const [key, message] of messageBuffer.current.entries()) {
        if (new Date(message.timestamp).getTime() < cutoff) {
          messageBuffer.current.delete(key);
        }
      }
    }, 60000); // 每分钟清理一次
    
    return () => clearInterval(cleanupInterval);
  }, []);

  // 重置状态
  const reset = useCallback(() => {
    setMessages([]);
    setStats({
      totalMessages: 0,
      nodeMessages: 0,
      toolMessages: 0,
      fileMessages: 0,
      agentMessages: 0,
      systemMessages: 0,
      errorCount: 0
    });
    setExecutionState({
      isThinking: false,
      activeTools: new Set(),
      generatedFiles: []
    });
    messageBuffer.current.clear();
    processingQueue.current = [];
  }, []);

  // 获取特定类型的消息
  const getMessagesByType = useCallback((type: StreamMessageType) => {
    return messages.filter(msg => msg.type === type);
  }, [messages]);

  // 获取最新的文件生成消息
  const getLatestFiles = useCallback((limit: number = 10) => {
    return messages
      .filter(isFileMessage)
      .slice(-limit)
      .reverse() as FileGeneratedMessage[];
  }, [messages]);

  // 获取活跃的工具执行状态
  const getActiveToolsStatus = useCallback(() => {
    const activeToolsArray = Array.from(executionState.activeTools);
    return activeToolsArray.map(toolName => {
      const latestMessage = messages
        .filter(isToolMessage)
        .filter(msg => (msg as ToolExecutionMessage).tool_name === toolName)
        .slice(-1)[0] as ToolExecutionMessage;
      
      return {
        toolName,
        status: latestMessage?.status || 'running',
        progress: latestMessage?.progress || 0
      };
    });
  }, [messages, executionState.activeTools]);

  // 检查是否有错误
  const hasErrors = useCallback(() => {
    return stats.errorCount > 0;
  }, [stats.errorCount]);

  // 获取最近的系统消息
  const getRecentSystemMessages = useCallback((limit: number = 5) => {
    return messages
      .filter(isSystemMessage)
      .slice(-limit)
      .reverse() as SystemMessage[];
  }, [messages]);

  return {
    // 状态
    messages,
    stats,
    executionState,
    
    // 方法
    addMessage,
    reset,
    getMessagesByType,
    getLatestFiles,
    getActiveToolsStatus,
    hasErrors,
    getRecentSystemMessages,
    
    // 计算属性
    isExecuting: executionState.activeTools.size > 0 || executionState.isThinking,
    currentActivity: executionState.currentTool || executionState.currentNode || (executionState.isThinking ? 'thinking' : null)
  };
}

// 扩展useChat钩子，集成流式消息处理
export function useEnhancedChat(config: StreamProcessorConfig & {
  api?: string;
  body?: any;
  initialMessages?: any[];
}) {
  const streamProcessor = useStreamProcessor(config);
  
  // 这里可以集成到现有的useChat钩子中
  // 监听AI SDK的流式数据并解析自定义消息
  
  return {
    ...streamProcessor,
    // 可以添加更多增强功能
  };
} 