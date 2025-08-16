"use client";

import React, { useState, useEffect, useRef } from 'react';
import { useChat } from '@ai-sdk/react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Badge } from './ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from './ui/dialog';
import { Checkbox } from './ui/checkbox';
import { ScrollArea } from './ui/scroll-area';
import { 
  FolderTree,
  File,
  FileText,
  FileImage,
  BarChart3,
  TrendingUp,
  Box,
  Download,
  Trash2,
  Eye,
  MessageSquare,
  Plus,
  FolderPlus,
  Send,
  User,
  Bot,
  Loader2,
  Info,
  ChevronDown
} from 'lucide-react';
import { TreeView, TreeNode, buildFileTree, getSelectedFiles } from './ui/tree-view';
import { SmartFileClassifier } from './smart-file-classifier';

// 导入新的流式消息处理组件
import { useStreamProcessor } from '../lib/use-stream-processor';
import { useFileTreeIntegration } from '../lib/file-tree-integration';
import { StreamMessageDisplay } from './stream-messages';
import { IntelligentMessageDisplay } from './intelligent-message-parser';
import { 
  StreamMessage, 
  FileGeneratedMessage,
  ToolExecutionMessage,
  AgentThinkingMessage,
  SystemMessage,
  NodeStatusMessage,
  parseStreamMessage
} from '../lib/streaming-types';

// 添加流式消息解析器类
class StreamMessageExtractor {
  private buffer: string = '';

  // 从混合流中提取结构化消息
  extractMessages(text: string): { cleanText: string; messages: StreamMessage[] } {
    this.buffer += text;
    const messages: StreamMessage[] = [];
    
    // 查找结构化消息标记
    const messageRegex = /\/\*STREAM_MESSAGE:(.+?)\*\//g;
    let match;
    let cleanText = this.buffer;
    
    while ((match = messageRegex.exec(this.buffer)) !== null) {
      try {
        const messageData = JSON.parse(match[1]);
        const parsedMessage = parseStreamMessage(messageData);
        if (parsedMessage) {
          messages.push(parsedMessage);
        }
        
        // 从干净文本中移除结构化消息标记
        cleanText = cleanText.replace(match[0], '');
      } catch (error) {
        console.warn('解析结构化消息失败:', error);
      }
    }
    
    this.buffer = cleanText;
    return { cleanText, messages };
  }

  // 重置缓冲区
  reset() {
    this.buffer = '';
  }

  // 获取当前缓冲的文本
  getCurrentText(): string {
    return this.buffer;
  }
}

interface FileItem {
  file_id: string;
  file_name: string;
  file_type: string;
  file_size: number;
  upload_time: string;
  file_path?: string;
  is_generated?: boolean;
  session_id?: string;
  metadata?: any; // 添加元数据字段支持
}

interface ModelingHubProps {
  apiBaseUrl?: string;
  sessionId?: string;
}

export function GeologicalModelingHub({ 
  apiBaseUrl = 'http://localhost:7102',
  sessionId 
}: ModelingHubProps) {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());
  const [activeTab, setActiveTab] = useState('chat');
  const [loading, setLoading] = useState(false);
  const [showFileSelector, setShowFileSelector] = useState(false);
  const [allFiles, setAllFiles] = useState<FileItem[]>([]);
  const [selectedForImport, setSelectedForImport] = useState<Set<string>>(new Set());
  const [importLoading, setImportLoading] = useState(false);
  
  // 文件夹树相关状态
  const [folders, setFolders] = useState<string[]>([]);
  const [fileTree, setFileTree] = useState<TreeNode[]>([]);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(['folder-input', 'folder-generated']));
  const [useTreeView, setUseTreeView] = useState(true);

  // 会话历史消息加载状态
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [initialMessages, setInitialMessages] = useState([
    {
      id: 'welcome',
      role: 'assistant' as const,
      content: '欢迎使用PetroAgent智能地质分析系统！我可以帮助您进行地质建模、测井数据分析、储层评价等专业工作。请告诉我您需要什么帮助。',
    }
  ]);

  // 流式消息处理相关状态
  const [debugMode, setDebugMode] = useState(false);
  const [streamDebugLogs, setStreamDebugLogs] = useState<string[]>([]);
  const [realTimeTokens, setRealTimeTokens] = useState<string[]>([]);
  const [showStreamMessages, setShowStreamMessages] = useState(true);
  const [streamMessageFilter, setStreamMessageFilter] = useState<string>('all');

  // 添加流式消息提取器
  const messageExtractor = useRef(new StreamMessageExtractor());

  // 添加滚动容器引用
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  // 添加调试日志函数
  const addDebugLog = (message: string) => {
    const timestamp = new Date().toISOString();
    const logEntry = `[${timestamp}] ${message}`;
    console.log(logEntry);
    setStreamDebugLogs(prev => [...prev.slice(-20), logEntry]);
  };

  // 添加实时token追踪
  const addRealTimeToken = (token: string) => {
    console.log('🔥 实时Token:', token);
    setRealTimeTokens(prev => [...prev.slice(-10), token]);
  };

  // 滚动到消息底部
  const scrollToBottom = () => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ 
        behavior: 'smooth',
        block: 'end'
      });
    }
  };

  // 集成流式消息处理器
  const streamProcessor = useStreamProcessor({
    sessionId: sessionId || '',
    apiBaseUrl,
    enableDebugLogs: true,
    onFileGenerated: (file: FileGeneratedMessage) => {
      console.log('📁 收到文件生成事件:', file);
      addDebugLog(`📁 文件生成: ${file.file_name}`);
      // 刷新文件列表
      setTimeout(() => fetchFiles(), 1000);
    },
    onToolProgress: (tool: ToolExecutionMessage) => {
      console.log('🔧 工具执行进度:', tool);
      addDebugLog(`🔧 工具执行: ${tool.tool_name} - ${tool.status}`);
    },
    onAgentThinking: (thinking: AgentThinkingMessage) => {
      console.log('🧠 Agent思考过程:', thinking);
      addDebugLog(`🧠 ${thinking.agent_name}: ${thinking.content.substring(0, 50)}...`);
    },
    onSystemMessage: (system: SystemMessage) => {
      console.log('⚠️ 系统消息:', system);
      addDebugLog(`⚠️ 系统: ${system.message}`);
    },
    onNodeStatusChange: (node: NodeStatusMessage) => {
      console.log('🔄 节点状态变化:', node);
      addDebugLog(`🔄 节点: ${node.node_name} - ${node.type}`);
    }
  });

  // 使用 AI SDK 4.x 的正确配置
  const {
    messages,
    input,
    handleInputChange,
    handleSubmit,
    isLoading,
    error,
    append,
    setMessages,
    reload
  } = useChat({
    api: '/api/chat',
    body: {
      sessionId: sessionId,
    },
    initialMessages: initialMessages,
    streamProtocol: 'text',
    // AI SDK 4.x的回调配置
    onResponse: (response) => {
      console.log('🔍 [DEBUG] onResponse 回调触发，响应对象:', response);
      addDebugLog(`✅ Chat API响应: ${response.status}`);
      if (response.status === 200) {
        addDebugLog('🎬 开始接收流式响应...');
        setHistoryLoaded(true);
        // 重置消息提取器
        messageExtractor.current.reset();
        streamProcessor.reset();
      }
    },
    onFinish: (message) => {
      console.log('🏁 [DEBUG] onFinish 回调触发，完整消息对象:', message);
      addDebugLog(`🏁 流式响应完成: ${message.content?.length || 0}字符`);
      
      // 处理完整消息中的结构化消息
      if (message.content) {
        const { cleanText, messages: extractedMessages } = messageExtractor.current.extractMessages(message.content);
        
        // 处理提取的结构化消息
        extractedMessages.forEach(msg => {
          streamProcessor.addMessage(msg);
        });
        
        // 如果有新的实时token
        if (cleanText) {
          addRealTimeToken(cleanText);
        }
      }
      
      // 刷新文件列表以获取可能生成的新文件
      if (sessionId) {
        addDebugLog('🔄 刷新文件列表...');
        fetchFiles();
      }
    },
    onError: (error) => {
      addDebugLog(`❌ Chat API错误: ${error.message}`);
      console.error('❌ Chat API错误:', error);
    }
  });

  // 🔍 调试：监听messages状态变化
  useEffect(() => {
    addDebugLog(`📝 当前消息数量: ${messages.length}`);
    if (messages.length > 0) {
      const lastMsg = messages[messages.length - 1];
      addDebugLog(`📄 最新消息: ${lastMsg.role} - ${lastMsg.content?.substring(0, 50)}...`);
    }
  }, [messages]);

  // 监听流式消息处理器状态
  useEffect(() => {
    if (streamProcessor.messages.length > 0) {
      const lastStreamMsg = streamProcessor.messages[streamProcessor.messages.length - 1];
      addDebugLog(`🌊 流式消息: ${lastStreamMsg.type} - ${JSON.stringify(lastStreamMsg).substring(0, 100)}...`);
    }
  }, [streamProcessor.messages]);

  // 集成文件树管理器
  const fileTreeManager = useFileTreeIntegration({
    sessionId: sessionId || '',
    apiBaseUrl,
    enableAutoClassification: true,
    enableAutoRefresh: true,
    refreshInterval: 30000,
    enableDebugLogs: true,
    onFileAdded: (file) => {
      console.log('📂 文件已添加到树:', file);
      addDebugLog(`📂 文件添加: ${file.file_name}`);
      fetchFiles();
    },
    onFileRemoved: (fileId) => {
      console.log('🗑️ 文件已从树中移除:', fileId);
      addDebugLog(`🗑️ 文件移除: ${fileId}`);
    },
    onFolderCreated: (folderPath) => {
      console.log('📁 文件夹已创建:', folderPath);
      addDebugLog(`📁 文件夹创建: ${folderPath}`);
    }
  });

  // 监听消息变化，自动滚动到底部
  useEffect(() => {
    if (messages.length > 0) {
      // 延迟一点以确保DOM已更新
      setTimeout(scrollToBottom, 100);
    }
  }, [messages]);

  // 监听流式消息变化，自动滚动到底部
  useEffect(() => {
    if (streamProcessor.messages.length > 0 && streamProcessor.isExecuting) {
      setTimeout(scrollToBottom, 50);
    }
  }, [streamProcessor.messages, streamProcessor.isExecuting]);

  // 监听loading状态变化，在开始和结束时滚动
  useEffect(() => {
    if (isLoading) {
      // 开始加载时滚动到底部
      setTimeout(scrollToBottom, 100);
    }
  }, [isLoading]);

  // 获取会话文件
  const fetchFiles = async (retryCount = 0) => {
    if (!sessionId) {
      console.warn('fetchFiles: 没有有效的sessionId');
      return;
    }
    
    try {
      setLoading(true);
      console.log(`正在获取会话 ${sessionId} 的文件列表...`);
      
      const params = new URLSearchParams();
      params.append('session_id', sessionId);
      
      const response = await fetch(`${apiBaseUrl}/api/v1/files/list?${params}`);
      
      if (response.ok) {
        const data = await response.json();
        console.log('API响应:', data);
        
        if (data.success && data.files) {
          setFiles(data.files);
          console.log(`✅ 成功获取 ${data.files.length} 个文件`);
          
          // 打印文件详情用于调试
          data.files.forEach((file: FileItem, index: number) => {
            console.log(`文件 ${index + 1}: ${file.file_name} (ID: ${file.file_id}, 会话: ${file.session_id})`);
          });
        } else {
          console.warn('API响应格式错误或success为false:', data);
          setFiles([]);
        }
      } else {
        const errorText = await response.text();
        console.error(`❌ 获取文件列表失败 (${response.status}):`, errorText);
        
        // 如果失败且重试次数少于2次，尝试重试
        if (retryCount < 2) {
          console.log(`尝试重试 (${retryCount + 1}/2)...`);
          setTimeout(() => fetchFiles(retryCount + 1), 1000);
          return;
        }
        
        setFiles([]);
      }
    } catch (error) {
      console.error('❌ 获取文件列表异常:', error);
      
      // 如果异常且重试次数少于2次，尝试重试
      if (retryCount < 2) {
        console.log(`异常重试 (${retryCount + 1}/2)...`);
        setTimeout(() => fetchFiles(retryCount + 1), 1000);
        return;
      }
      
      setFiles([]);
    } finally {
      setLoading(false);
    }
  };

  // 获取文件夹结构
  const fetchFolders = async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/files/folders/tree`);
      if (response.ok) {
        const data = await response.json();
        if (data.success && data.folders) {
          setFolders(data.folders);
          console.log(`获取到 ${data.folders.length} 个文件夹`);
        }
      }
    } catch (error) {
      console.error('获取文件夹列表失败:', error);
    }
  };

  // 简化的历史加载逻辑，确保消息始终能显示
  useEffect(() => {
    if (sessionId) {
      console.log(`会话 ${sessionId} 已准备就绪，设置historyLoaded为true`);
      setHistoryLoaded(true);
      
      // 关键修复：主动加载会话历史消息
      loadSessionHistory(sessionId);
    } else {
      // 没有sessionId时，重置状态
      setHistoryLoaded(false);
      // 重置到默认消息
      setMessages(initialMessages);
    }
  }, [sessionId]); // 仅依赖sessionId，避免循环

  // 新增：加载会话历史消息的函数
  const loadSessionHistory = async (currentSessionId: string) => {
    try {
      addDebugLog(`🔄 开始加载会话 ${currentSessionId} 的历史消息...`);
      
      const historyResponse = await fetch(`${apiBaseUrl}/api/v1/chat/${currentSessionId}/history`);
      if (historyResponse.ok) {
        const historyData = await historyResponse.json();
        if (historyData.success && historyData.data?.messages && historyData.data.messages.length > 0) {
          // 转换历史消息格式为useChat所需的格式
          const chatMessages = historyData.data.messages.map((msg: any) => ({
            id: msg.id || `msg-${Date.now()}-${Math.random()}`,
            role: msg.role === 'user' ? 'user' : 'assistant',
            content: msg.content || '',
            createdAt: msg.timestamp ? new Date(msg.timestamp) : new Date(),
          }));
          
          // 使用setMessages替换当前的消息列表
          setMessages(chatMessages);
          
          addDebugLog(`✅ 成功加载 ${chatMessages.length} 条历史消息`);
          console.log('📋 加载的历史消息:', chatMessages);
          
          // 标记历史已加载
          setHistoryLoaded(true);
        } else {
          addDebugLog('ℹ️ 该会话暂无历史消息，保持欢迎消息');
          // 如果没有历史消息，保持初始欢迎消息
          setMessages(initialMessages);
          setHistoryLoaded(true);
        }
      } else {
        addDebugLog(`❌ 获取会话历史失败: HTTP ${historyResponse.status}`);
        console.error('获取会话历史失败:', historyResponse.status);
        // 失败时保持初始消息
        setMessages(initialMessages);
        setHistoryLoaded(true);
      }
    } catch (error) {
      addDebugLog(`❌ 加载会话历史异常: ${error}`);
      console.error('加载会话历史异常:', error);
      // 异常时保持初始消息
      setMessages(initialMessages);
      setHistoryLoaded(true);
    }
  };

  // 初始化和会话变化时刷新文件列表
  useEffect(() => {
    if (sessionId) {
      fetchFiles();
      fetchFolders();
      // 重置流式消息处理器
      streamProcessor.reset();
    }
  }, [sessionId]);

  // 同步文件树管理器的文件到本地状态
  useEffect(() => {
    if (fileTreeManager.files.length > 0) {
      setFiles(fileTreeManager.files);
    }
  }, [fileTreeManager.files]);

  // 监听流式消息处理器的文件生成事件
  useEffect(() => {
    const latestFiles = streamProcessor.getLatestFiles(5);
    if (latestFiles.length > 0) {
      // 将文件生成消息传递给文件树管理器
      latestFiles.forEach(fileMsg => {
        fileTreeManager.handleFileGenerated(fileMsg);
      });
    }
  }, [streamProcessor.stats.fileMessages]);

  // 暂时禁用SSE连接以排查聊天流式响应问题
  // TODO: 重新启用SSE连接当主要聊天功能修复后
  /*
  useEffect(() => {
    if (!sessionId) return;

    let eventSource: EventSource;
    
    const connectToStream = () => {
      eventSource = new EventSource(`/api/stream?sessionId=${sessionId}`);
      
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('收到SSE流式消息:', data);
          streamProcessor.addMessage(data);
        } catch (error) {
          console.error('解析SSE消息失败:', error);
        }
      };
      
      eventSource.onerror = (error) => {
        console.error('SSE连接错误:', error);
      };
    };

    const timer = setTimeout(connectToStream, 1000);

    return () => {
      clearTimeout(timer);
      if (eventSource) {
        eventSource.close();
      }
    };
  }, [sessionId, apiBaseUrl, streamProcessor]);
  */

  // 创建文件夹
  const createFolder = async (folderPath: string) => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/files/folders/create`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          folder_path: folderPath
        })
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          // 更新文件夹列表
          setFolders(prev => [...prev, folderPath]);
          console.log(`文件夹 ${folderPath} 创建成功`);
          return true;
        }
      }
      return false;
    } catch (error) {
      console.error('创建文件夹失败:', error);
      return false;
    }
  };

  // 移动文件到文件夹
  const moveFileToFolder = async (fileId: string, targetFolder: string) => {
    try {
      // 使用FormData发送数据
      const formData = new FormData();
      formData.append('target_folder', targetFolder);
      
      const response = await fetch(`${apiBaseUrl}/api/v1/files/${fileId}/move`, {
        method: 'PUT',
        body: formData
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          console.log(`文件 ${fileId} 移动到 ${targetFolder} 成功`);
          // 刷新文件列表
          await fetchFiles();
          await fetchAllFiles();
          return true;
        }
      }
      return false;
    } catch (error) {
      console.error('移动文件失败:', error);
      return false;
    }
  };

  // 获取所有系统文件夹
  const fetchAllFolders = async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/files/folders/tree`);
      if (response.ok) {
        const data = await response.json();
        if (data.success && data.data) {
          const folders = data.data.folders || [];
          console.log(`获取到系统文件夹 ${folders.length} 个:`, folders);
          return folders;
        }
      }
      return [];
    } catch (error) {
      console.error('获取系统文件夹失败:', error);
      return [];
    }
  };

  // 获取所有系统文件
  const fetchAllFiles = async () => {
    try {
      // 先获取当前会话的文件
      const currentSessionParams = new URLSearchParams();
      if (sessionId) {
        currentSessionParams.append('session_id', sessionId);
      }
      
      const currentResponse = await fetch(`${apiBaseUrl}/api/v1/files/list?${currentSessionParams}`);
      let currentFileIds = new Set<string>();
      
      if (currentResponse.ok) {
        const currentData = await currentResponse.json();
        if (currentData.success && currentData.files) {
          currentFileIds = new Set(currentData.files.map((file: FileItem) => file.file_id));
        }
      }
      
      // 同时获取所有文件和文件夹
      const [filesResponse, foldersData] = await Promise.all([
        fetch(`${apiBaseUrl}/api/v1/files/list`),
        fetchAllFolders()
      ]);
      
      if (filesResponse.ok) {
        const data = await filesResponse.json();
        if (data.success && data.files) {
          // 过滤掉当前会话已有的文件，显示其他所有文件
          const availableFiles = data.files.filter((file: FileItem) => 
            !currentFileIds.has(file.file_id)
          );
          setAllFiles(availableFiles);
          console.log(`获取到 ${availableFiles.length} 个可导入文件，当前会话已有 ${currentFileIds.size} 个文件`);
          
          // 构建文件树，标记哪些文件是可导入的
          const allSystemFiles = data.files; // 包含所有系统文件
          const availableFileIds = new Set(availableFiles.map((f: FileItem) => f.file_id));
          
          // 为文件添加可导入标记
          const markedFiles = allSystemFiles.map((file: FileItem) => ({
            ...file,
            isImportable: availableFileIds.has(file.file_id)
          }));
          
          const tree = buildFileTree(markedFiles, foldersData);
          setFileTree(tree);
          console.log('构建的文件树:', tree);
        }
      }
    } catch (error) {
      console.error('获取所有文件失败:', error);
    }
  };

  // 导入选中的文件到当前会话
  const importSelectedFiles = async () => {
    if (selectedForImport.size === 0) return;
    
    try {
      setImportLoading(true);
      
      // 从文件树中获取选中的文件，如果使用树形视图
      const filesToImport = useTreeView ? 
        getSelectedFiles(fileTree, selectedForImport) :
        allFiles.filter(file => selectedForImport.has(file.file_id));
      
      const successfulImports: FileItem[] = [];
      const failedImports: string[] = [];
      
      console.log(`开始导入 ${filesToImport.length} 个文件到会话 ${sessionId}`);
      
      // 为每个文件调用后端API进行关联
      for (const file of filesToImport) {
        try {
          console.log(`正在关联文件: ${file.file_name} (${file.file_id})`);
          
          const response = await fetch(`${apiBaseUrl}/api/v1/files/${file.file_id}/associate`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              target_session_id: sessionId
            })
          });
          
          if (response.ok) {
            const result = await response.json();
            if (result.success) {
              // 更新文件信息，关联到当前会话
              const updatedFile = {
                ...file,
                session_id: sessionId,
                is_generated: false
              };
              successfulImports.push(updatedFile);
              console.log(`✅ 文件 ${file.file_name} 成功关联到会话 ${sessionId}`);
            } else {
              console.error(`❌ 文件 ${file.file_name} 关联失败:`, result.message);
              failedImports.push(file.file_name);
            }
          } else {
            const errorText = await response.text();
            console.error(`❌ 文件 ${file.file_name} 关联请求失败 (${response.status}):`, errorText);
            failedImports.push(file.file_name);
          }
        } catch (error) {
          console.error(`❌ 文件 ${file.file_name} 关联异常:`, error);
          failedImports.push(file.file_name);
        }
      }
      
      // 更新本地状态
      if (successfulImports.length > 0) {
        console.log(`✅ 成功导入 ${successfulImports.length} 个文件到当前会话`);
        
        // 从可导入文件列表中移除已成功导入的文件
        setAllFiles(prev => {
          const updatedAllFiles = prev.filter(file => 
            !successfulImports.some(imported => imported.file_id === file.file_id)
          );
          console.log(`可导入文件列表已更新，剩余 ${updatedAllFiles.length} 个文件`);
          return updatedAllFiles;
        });
        
        // 立即将成功导入的文件添加到当前文件列表
        setFiles(prev => {
          const existingIds = new Set(prev.map(f => f.file_id));
          const newFiles = successfulImports.filter(f => !existingIds.has(f.file_id));
          return [...prev, ...newFiles];
        });
      }
      
      // 清理选择状态
      setSelectedForImport(new Set());
      setShowFileSelector(false);
      
      // 给用户反馈
      const message = `导入完成：成功 ${successfulImports.length} 个${failedImports.length > 0 ? `，失败 ${failedImports.length} 个` : ''}`;
      console.log(message);
      
      // 延迟刷新以确保后端数据同步
      setTimeout(async () => {
        console.log('正在刷新文件列表以确保数据同步...');
        await fetchFiles();
      }, 2000);
      
    } catch (error) {
      console.error('❌ 导入文件失败:', error);
      alert('文件导入过程中发生错误，请重试');
    } finally {
      setImportLoading(false);
    }
  };

  useEffect(() => {
    if (sessionId) {
      console.log(`会话ID变更为: ${sessionId}，重新获取文件列表`);
      fetchFiles();
      fetchFolders();
      const interval = setInterval(() => {
        fetchFiles();
        fetchFolders();
      }, 30000);
      return () => clearInterval(interval);
    } else {
      console.warn('useEffect: 没有sessionId，清空文件列表');
      setFiles([]);
      setFolders([]);
      setFileTree([]);
    }
  }, [sessionId, apiBaseUrl]);

  const getFileIcon = (fileType: string, fileName: string) => {
    const extension = fileName.split('.').pop()?.toLowerCase();
    
    if (extension === 'las') {
      return <TrendingUp className="h-4 w-4 text-orange-500" />;
    }
    
    // 根据扩展名特殊处理
    if (extension === 'xlsx' || extension === 'xls') {
      return <FileText className="h-4 w-4 text-green-600" />;
    }
    
    if (extension === 'docx' || extension === 'doc') {
      return <FileText className="h-4 w-4 text-blue-600" />;
    }
    
    switch (fileType) {
      case 'image':
        return <FileImage className="h-4 w-4 text-green-500" />;
      case 'document':
        return <FileText className="h-4 w-4 text-blue-500" />;
      case 'spreadsheet':
        return <FileText className="h-4 w-4 text-green-500" />;
      case 'text':
        return <File className="h-4 w-4 text-gray-500" />;
      default:
        return <File className="h-4 w-4 text-gray-500" />;
    }
  };

  const formatFileSize = (bytes: number) => {
    const sizes = ['B', 'KB', 'MB', 'GB'];
    if (bytes === 0) return '0 B';
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${Math.round(bytes / Math.pow(1024, i) * 100) / 100} ${sizes[i]}`;
  };

  const handleFileSelect = (fileId: string) => {
    const newSelection = new Set(selectedFiles);
    if (newSelection.has(fileId)) {
      newSelection.delete(fileId);
    } else {
      newSelection.add(fileId);
    }
    setSelectedFiles(newSelection);
  };

  const handleFileDownload = async (file: FileItem) => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/files/${file.file_id}/download`);
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = file.file_name;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      }
    } catch (error) {
      console.error('下载文件失败:', error);
    }
  };

  const handleFileDelete = async (fileId: string) => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/files/${fileId}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        setFiles(prev => prev.filter(f => f.file_id !== fileId));
        setSelectedFiles(prev => {
          const newSet = new Set(prev);
          newSet.delete(fileId);
          return newSet;
        });
      }
    } catch (error) {
      console.error('删除文件失败:', error);
    }
  };

  const handleImportFileSelect = (fileId: string) => {
    const newSelection = new Set(selectedForImport);
    if (newSelection.has(fileId)) {
      newSelection.delete(fileId);
    } else {
      newSelection.add(fileId);
    }
    setSelectedForImport(newSelection);
  };

  // 处理文件夹展开/折叠
  const handleFolderToggle = (folderId: string, isExpanded: boolean) => {
    const newExpanded = new Set(expandedFolders);
    if (isExpanded) {
      newExpanded.add(folderId);
    } else {
      newExpanded.delete(folderId);
    }
    setExpandedFolders(newExpanded);
  };

  // 处理文件树中的文件选择
  const handleTreeFileSelect = (nodeId: string, isSelected: boolean) => {
    // 确保选择的是可导入的文件（不是当前会话已有的）
    const availableFileIds = new Set(allFiles.map(f => f.file_id));
    
    if (isSelected && availableFileIds.has(nodeId)) {
      setSelectedForImport(prev => new Set([...prev, nodeId]));
    } else {
      setSelectedForImport(prev => {
        const newSet = new Set(prev);
        newSet.delete(nodeId);
        return newSet;
      });
    }
  };

  // 处理文件树中的节点点击
  const handleTreeNodeClick = (node: TreeNode) => {
    if (node.type === 'file' && node.fileData) {
      // 文件点击时进行选择切换
      const isSelected = selectedForImport.has(node.id);
      handleTreeFileSelect(node.id, !isSelected);
    }
  };

  // 文件分类
  const categorizeFiles = () => {
    const categories = {
      input: files.filter(f => !f.is_generated && (
        f.file_type === 'text' || 
        f.file_type === 'document' ||  // 包含docx等文档文件
        f.file_type === 'spreadsheet' ||  // 包含xlsx等表格文件
        f.file_name.toLowerCase().endsWith('.csv') ||
        f.file_name.toLowerCase().endsWith('.txt') ||
        f.file_name.toLowerCase().endsWith('.docx') ||
        f.file_name.toLowerCase().endsWith('.xlsx')
      )),
      logs: files.filter(f => f.file_name.toLowerCase().endsWith('.las')),
      charts: files.filter(f => {
        // 检查是否是生成的图片文件
        const isGeneratedImage = f.is_generated && f.file_type === 'image';
        
        // 检查是否有地质建模相关的元数据
        const hasGeologicalMetadata = f.metadata && (
          f.metadata.category === 'analysis_result' ||
          f.metadata.geological_model === 'true' ||
          f.metadata.analysis_type?.includes('isotope') ||
          f.metadata.chart_type
        );
        
        // 检查文件名是否表明是分析结果
        const isAnalysisFile = f.file_type === 'image' && (
          f.file_name.toLowerCase().includes('isotope') ||
          f.file_name.toLowerCase().includes('trend') ||
          f.file_name.toLowerCase().includes('profile') ||
          f.file_name.toLowerCase().includes('analysis') ||
          f.file_name.toLowerCase().includes('chart')
        );
        
        return isGeneratedImage || hasGeologicalMetadata || isAnalysisFile;
      }),
      models: files.filter(f => f.is_generated && f.file_type === 'document'),
      reports: files.filter(f => f.is_generated && (f.file_name.toLowerCase().includes('report') || f.file_name.toLowerCase().includes('analysis')))
    };
    return categories;
  };

  const categorizeAllFiles = () => {
    const allCategories = {
      input: allFiles.filter(f => !f.is_generated && (
        f.file_type === 'text' || 
        f.file_type === 'document' ||  // 包含docx等文档文件
        f.file_type === 'spreadsheet' ||  // 包含xlsx等表格文件
        f.file_name.toLowerCase().endsWith('.csv') ||
        f.file_name.toLowerCase().endsWith('.txt') ||
        f.file_name.toLowerCase().endsWith('.docx') ||
        f.file_name.toLowerCase().endsWith('.xlsx')
      )),
      logs: allFiles.filter(f => f.file_name.toLowerCase().endsWith('.las')),
      images: allFiles.filter(f => f.file_type === 'image'),
      documents: allFiles.filter(f => f.file_type === 'document' && !f.is_generated),
      spreadsheets: allFiles.filter(f => f.file_type === 'spreadsheet'), // 新增表格文件分类
      others: allFiles.filter(f => !['image', 'document', 'text', 'spreadsheet'].includes(f.file_type) && 
                                  !f.file_name.toLowerCase().endsWith('.las') && 
                                  !f.file_name.toLowerCase().endsWith('.csv') &&
                                  !f.file_name.toLowerCase().endsWith('.txt') &&
                                  !f.file_name.toLowerCase().endsWith('.docx') &&
                                  !f.file_name.toLowerCase().endsWith('.xlsx'))
    };
    return allCategories;
  };

  const categories = categorizeFiles();

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold text-gray-900">地质建模中心</h2>
          <p className="text-gray-600 mt-1">从数据管理中心选择文件，通过自然语言交互进行智能地质建模与分析</p>
        </div>
        
        <div className="flex items-center space-x-2">
          {sessionId && (
            <Badge variant="outline">
              会话: {sessionId.slice(0, 8)}...
            </Badge>
          )}
          <Button onClick={() => fetchFiles()} size="sm" variant="outline">
            刷新文件
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* 左侧文件树 */}
        <div className="lg:col-span-1">
          <Card className="h-full">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium flex items-center">
                  <FolderTree className="h-4 w-4 mr-2" />
                  项目文件树
                </CardTitle>
                
                {/* 选择文件按钮 */}
                <Dialog open={showFileSelector} onOpenChange={setShowFileSelector}>
                  <DialogTrigger asChild>
                    <Button size="sm" variant="outline" onClick={fetchAllFiles}>
                      <FolderPlus className="h-3 w-3 mr-1" />
                      选择文件
                    </Button>
                  </DialogTrigger>
                  <DialogContent className="max-w-6xl max-h-[85vh] overflow-hidden">
                    <DialogHeader>
                      <div className="flex items-center justify-between">
                      <DialogTitle>从数据管理中心选择文件</DialogTitle>
                        <div className="flex items-center space-x-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setUseTreeView(!useTreeView)}
                          >
                            {useTreeView ? '切换为分类视图' : '切换为文件夹视图'}
                          </Button>
                        </div>
                      </div>
                    </DialogHeader>
                    
                    <div className="space-y-4">
                      {/* 说明区域 */}
                      <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                        <div className="flex items-center">
                          <Info className="h-5 w-5 text-blue-600 mr-2" />
                          <div>
                            <h3 className="text-sm font-medium text-blue-800">从数据管理中心选择文件</h3>
                            <p className="text-sm text-blue-600 mt-1">
                              请选择已在"数据管理中心"中整理好的文件加载到当前建模项目中。如需管理文件结构，请前往"数据管理中心"。
                            </p>
                          </div>
                        </div>
                      </div>
                      
                      {/* 文件选择器 */}
                      <div className="space-y-4">
                        <div className="flex items-center justify-between">
                      <p className="text-sm text-gray-600">
                        选择已上传到数据管理中心的文件加载到当前建模项目中
                      </p>
                          <div className="text-sm text-gray-500">
                            已选择 {selectedForImport.size} 个文件
                          </div>
                        </div>
                                              {useTreeView ? (
                          /* 文件夹树形视图 */
                          <div className="border rounded-lg p-4 h-96 overflow-y-auto">
                            <div className="flex items-center justify-between mb-3">
                              <h4 className="text-sm font-medium text-gray-700">文件夹结构</h4>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => {
                                  fetchAllFiles();
                                }}
                              >
                                刷新
                              </Button>
                            </div>
                            {fileTree.length > 0 ? (
                              <TreeView
                                data={fileTree}
                                selectedItems={selectedForImport}
                                onItemSelect={handleTreeFileSelect}
                                onItemClick={handleTreeNodeClick}
                                showCheckboxes={true}
                                expandedFolders={expandedFolders}
                                onFolderToggle={handleFolderToggle}
                              />
                            ) : (
                              <div className="flex items-center justify-center h-32 text-gray-500">
                                <div className="text-center">
                                  <FolderTree className="h-8 w-8 mx-auto mb-2" />
                                  <div className="text-sm">暂无文件或文件夹</div>
                                </div>
                              </div>
                            )}
                          </div>
                        ) : (
                          /* 传统分类视图 */
                          Object.entries(categorizeAllFiles()).map(([category, categoryFiles]) => (
                        <div key={category}>
                          <h4 className="text-sm font-medium text-gray-700 mb-2 capitalize">
                            {category} ({categoryFiles.length})
                          </h4>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-40 overflow-y-auto">
                            {categoryFiles.map((file) => (
                              <div
                                key={file.file_id}
                                className={`flex items-center space-x-2 p-2 rounded border cursor-pointer hover:bg-gray-50 ${
                                  selectedForImport.has(file.file_id) ? 'bg-blue-50 border-blue-200' : ''
                                }`}
                                onClick={() => handleImportFileSelect(file.file_id)}
                              >
                                <Checkbox 
                                  checked={selectedForImport.has(file.file_id)}
                                  onChange={() => handleImportFileSelect(file.file_id)}
                                />
                                {getFileIcon(file.file_type, file.file_name)}
                                <div className="flex-1 min-w-0">
                                  <div className="text-xs font-medium truncate" title={file.file_name}>
                                    {file.file_name}
                                  </div>
                                  <div className="text-xs text-gray-500">
                                    {formatFileSize(file.file_size)}
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                          {categoryFiles.length === 0 && (
                            <div className="text-xs text-gray-500 text-center py-2">
                              暂无{category}文件
                            </div>
                          )}
                        </div>
                          ))
                                                )}
                      
                      <div className="flex justify-end space-x-2 pt-4 border-t">
                        <Button 
                          variant="outline" 
                          onClick={() => setShowFileSelector(false)}
                        >
                          取消
                        </Button>
                        <Button 
                          onClick={importSelectedFiles}
                          disabled={selectedForImport.size === 0 || importLoading}
                        >
                          {importLoading ? '导入中...' : `导入 ${selectedForImport.size} 个文件`}
                        </Button>
                        </div>
                      </div>
                    </div>
                  </DialogContent>
                </Dialog>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {loading ? (
                <div className="text-center py-4 text-sm text-gray-500">
                  加载中...
                </div>
              ) : (
                <>
                  {/* 输入数据 */}
                  <div>
                    <h4 className="text-xs font-medium text-gray-700 mb-2">输入数据 ({categories.input.length})</h4>
                    <div className="space-y-1">
                      {categories.input.map((file) => (
                        <div
                          key={file.file_id}
                          className={`flex items-center space-x-2 p-2 rounded cursor-pointer hover:bg-gray-50 ${
                            selectedFiles.has(file.file_id) ? 'bg-blue-50 border border-blue-200' : ''
                          }`}
                          onClick={() => handleFileSelect(file.file_id)}
                        >
                          {getFileIcon(file.file_type, file.file_name)}
                          <span className="text-xs truncate flex-1" title={file.file_name}>
                            {file.file_name}
                          </span>
                          <div className="flex space-x-1">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleFileDownload(file);
                              }}
                              className="text-blue-500 hover:text-blue-700"
                            >
                              <Download className="h-3 w-3" />
                            </button>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleFileDelete(file.file_id);
                              }}
                              className="text-red-500 hover:text-red-700"
                            >
                              <Trash2 className="h-3 w-3" />
                            </button>
                          </div>
                        </div>
                      ))}
                      {categories.input.length === 0 && (
                        <div className="text-xs text-gray-500 text-center py-2">
                          暂无输入文件
                          <br />
                          <button 
                            onClick={() => setShowFileSelector(true)}
                            className="text-blue-500 hover:text-blue-700 underline"
                          >
                            从数据管理中心选择文件
                          </button>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* 测井曲线 */}
                  <div>
                    <h4 className="text-xs font-medium text-gray-700 mb-2">测井曲线 ({categories.logs.length})</h4>
                    <div className="space-y-1">
                      {categories.logs.map((file) => (
                        <div
                          key={file.file_id}
                          className={`flex items-center space-x-2 p-2 rounded cursor-pointer hover:bg-gray-50 ${
                            selectedFiles.has(file.file_id) ? 'bg-blue-50 border border-blue-200' : ''
                          }`}
                          onClick={() => handleFileSelect(file.file_id)}
                        >
                          {getFileIcon(file.file_type, file.file_name)}
                          <span className="text-xs truncate flex-1" title={file.file_name}>
                            {file.file_name}
                          </span>
                          <div className="flex space-x-1">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleFileDownload(file);
                              }}
                              className="text-blue-500 hover:text-blue-700"
                            >
                              <Download className="h-3 w-3" />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* 生成的图表 */}
                  <div>
                    <h4 className="text-xs font-medium text-gray-700 mb-2">生成图表 ({categories.charts.length})</h4>
                    <div className="space-y-1">
                      {categories.charts.map((file) => (
                        <div
                          key={file.file_id}
                          className={`flex items-center space-x-2 p-2 rounded cursor-pointer hover:bg-gray-50 ${
                            selectedFiles.has(file.file_id) ? 'bg-blue-50 border border-blue-200' : ''
                          }`}
                          onClick={() => handleFileSelect(file.file_id)}
                        >
                          {getFileIcon(file.file_type, file.file_name)}
                          <span className="text-xs truncate flex-1" title={file.file_name}>
                            {file.file_name}
                          </span>
                          <div className="flex space-x-1">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleFileDownload(file);
                              }}
                              className="text-blue-500 hover:text-blue-700"
                            >
                              <Download className="h-3 w-3" />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* 模型文件 */}
                  <div>
                    <h4 className="text-xs font-medium text-gray-700 mb-2">模型文件 ({categories.models.length})</h4>
                    <div className="space-y-1">
                      {categories.models.map((file) => (
                        <div
                          key={file.file_id}
                          className={`flex items-center space-x-2 p-2 rounded cursor-pointer hover:bg-gray-50 ${
                            selectedFiles.has(file.file_id) ? 'bg-blue-50 border border-blue-200' : ''
                          }`}
                          onClick={() => handleFileSelect(file.file_id)}
                        >
                          {getFileIcon(file.file_type, file.file_name)}
                          <span className="text-xs truncate flex-1" title={file.file_name}>
                            {file.file_name}
                          </span>
                          <div className="flex space-x-1">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleFileDownload(file);
                              }}
                              className="text-blue-500 hover:text-blue-700"
                            >
                              <Download className="h-3 w-3" />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* 分析报告 */}
                  <div>
                    <h4 className="text-xs font-medium text-gray-700 mb-2">分析报告 ({categories.reports.length})</h4>
                    <div className="space-y-1">
                      {categories.reports.map((file) => (
                        <div
                          key={file.file_id}
                          className={`flex items-center space-x-2 p-2 rounded cursor-pointer hover:bg-gray-50 ${
                            selectedFiles.has(file.file_id) ? 'bg-blue-50 border border-blue-200' : ''
                          }`}
                          onClick={() => handleFileSelect(file.file_id)}
                        >
                          {getFileIcon(file.file_type, file.file_name)}
                          <span className="text-xs truncate flex-1" title={file.file_name}>
                            {file.file_name}
                          </span>
                          <div className="flex space-x-1">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleFileDownload(file);
                              }}
                              className="text-blue-500 hover:text-blue-700"
                            >
                              <Download className="h-3 w-3" />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </div>

        {/* 右侧主要内容区域 */}
        <div className="lg:col-span-3">
          <Card className="h-full">
            <CardHeader>
              <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                <TabsList className="grid w-full grid-cols-3">
                  <TabsTrigger value="chat" className="flex items-center space-x-2">
                    <MessageSquare className="h-4 w-4" />
                    <span>AI助手对话</span>
                  </TabsTrigger>
                  <TabsTrigger value="2d" className="flex items-center space-x-2">
                    <BarChart3 className="h-4 w-4" />
                    <span>2D图表分析</span>
                  </TabsTrigger>
                  <TabsTrigger value="3d" className="flex items-center space-x-2">
                    <Box className="h-4 w-4" />
                    <span>3D模型视图</span>
                  </TabsTrigger>
                </TabsList>
              </Tabs>
            </CardHeader>
            
            <CardContent className="h-[600px] flex flex-col">
              <Tabs value={activeTab} onValueChange={setActiveTab}>
                <TabsContent value="chat" className="flex-1 flex flex-col">
                  {/* 聊天界面 */}
                  <div className="flex-1 flex flex-col">
                    {/* 调试开关按钮 */}
                    <div className="flex items-center justify-between mb-2 px-4">
                      <h3 className="text-sm font-medium text-gray-700">实时对话监控</h3>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setDebugMode(!debugMode)}
                        className={`text-xs ${debugMode ? 'bg-blue-100 text-blue-700' : 'text-gray-500'}`}
                      >
                        {debugMode ? '🔍 关闭调试' : '🔍 开启调试'}
                      </Button>
                    </div>

                    {/* 调试面板 */}
                    {debugMode && (
                      <div className="mb-4 mx-4 p-4 bg-gray-50 rounded-lg border">
                        <div className="flex items-center justify-between mb-2">
                          <h4 className="text-sm font-medium text-gray-700">🔍 流式调试面板</h4>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setStreamDebugLogs([]);
                              setRealTimeTokens([]);
                            }}
                          >
                            清空日志
                          </Button>
                        </div>
                        
                        {/* 调试日志 */}
                        <div className="mb-3">
                          <h5 className="text-xs font-medium text-gray-600 mb-1">📋 调试日志 ({streamDebugLogs.length})</h5>
                          <div className="bg-white rounded p-2 h-32 overflow-y-auto text-xs font-mono">
                            {streamDebugLogs.length === 0 ? (
                              <div className="text-gray-500">等待日志...</div>
                            ) : (
                              streamDebugLogs.map((log, index) => (
                                <div key={index} className="mb-1">{log}</div>
                              ))
                            )}
                          </div>
                        </div>
                        
                        {/* 实时Token */}
                        <div className="mb-3">
                          <h5 className="text-xs font-medium text-gray-600 mb-1">🔥 实时Token ({realTimeTokens.length})</h5>
                          <div className="bg-white rounded p-2 h-24 overflow-y-auto text-xs">
                            {realTimeTokens.length === 0 ? (
                              <div className="text-gray-500">等待Token...</div>
                            ) : (
                              realTimeTokens.map((token, index) => (
                                <div key={index} className="mb-1 border-b border-gray-100 pb-1">
                                  Token {index + 1}: "{token}"
                                </div>
                              ))
                            )}
                          </div>
                        </div>
                        
                        {/* 状态信息 */}
                        <div className="flex flex-wrap gap-2 text-xs">
                          <span className="bg-gray-200 px-2 py-1 rounded">消息数: {messages.length}</span>
                          <span className={`px-2 py-1 rounded ${isLoading ? 'bg-yellow-200' : 'bg-green-200'}`}>
                            加载中: {isLoading ? '是' : '否'}
                          </span>
                          <span className={`px-2 py-1 rounded ${error ? 'bg-red-200' : 'bg-green-200'}`}>
                            错误: {error ? '有' : '无'}
                          </span>
                          <span className="bg-blue-200 px-2 py-1 rounded">会话: {sessionId ? sessionId.slice(-8) : '无'}</span>
                          <span className={`px-2 py-1 rounded ${streamProcessor.isExecuting ? 'bg-green-200' : 'bg-gray-200'}`}>
                            流式: {streamProcessor.isExecuting ? '活跃' : '非活跃'}
                          </span>
                        </div>
                      </div>
                    )}

                    {/* 消息区域 */}
                    <div className="relative flex-1 mb-4">
                      <ScrollArea 
                        ref={scrollAreaRef}
                        className="h-full max-h-[calc(100vh-400px)] overflow-y-auto"
                      >
                        <div className="space-y-4 p-4">
                        {/* 流式消息过滤器 */}
                        {showStreamMessages && streamProcessor.messages.length > 0 && (
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center space-x-2">
                              <Badge variant="outline" className="text-xs">
                                流式状态: {streamProcessor.isExecuting ? '执行中' : '空闲'}
                              </Badge>
                              {streamProcessor.currentActivity && (
                                <Badge variant="secondary" className="text-xs">
                                  {streamProcessor.currentActivity}
                                </Badge>
                              )}
                              {streamProcessor.hasErrors() && (
                                <Badge variant="destructive" className="text-xs">
                                  {streamProcessor.stats.errorCount} 个错误
                                </Badge>
                              )}
                            </div>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setShowStreamMessages(!showStreamMessages)}
                              className="text-xs"
                            >
                              {showStreamMessages ? '隐藏流式消息' : '显示流式消息'}
                            </Button>
                          </div>
                        )}

                        {/* 历史消息加载指示器 */}
                        {!historyLoaded && sessionId && (
                          <div className="flex justify-center">
                            <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-2">
                              <div className="flex items-center space-x-2 text-blue-700">
                                <Loader2 className="h-4 w-4 animate-spin" />
                                <span className="text-sm">正在加载会话历史...</span>
                              </div>
                            </div>
                          </div>
                        )}
                        
                        {/* 会话切换成功提示 */}
                        {historyLoaded && sessionId && messages.length > 1 && (
                          <div className="flex justify-center mb-2">
                            <div className="bg-green-50 border border-green-200 rounded-lg px-3 py-1">
                              <div className="flex items-center space-x-2 text-green-700">
                                <span className="text-xs">✅ 已加载 {messages.length} 条历史消息</span>
                              </div>
                            </div>
                          </div>
                        )}
                        
                        {/* 🔍 调试信息：消息渲染状态 */}
                        {process.env.NODE_ENV === 'development' && (
                          <div className="mb-2 p-2 bg-yellow-50 border border-yellow-200 rounded text-xs">
                            <strong>🔍 调试信息:</strong> 当前消息数量: {messages.length}, historyLoaded: {historyLoaded.toString()}, sessionId: {sessionId?.slice(-8)}
                            {messages.length > 0 && (
                              <div>最新消息: {messages[messages.length - 1]?.role} - {messages[messages.length - 1]?.content?.substring(0, 30)}...</div>
                            )}
                          </div>
                        )}
                        
                        {/* 消息列表 - 使用智能消息解析显示 */}
                        {messages.map((message) => (
                          <IntelligentMessageDisplay
                            key={message.id}
                            role={message.role}
                            content={message.content}
                            timestamp={message.createdAt}
                          />
                        ))}

                        {/* 补充流式状态信息（仅显示实时执行状态，避免与主消息重复） */}
                        {showStreamMessages && streamProcessor.isExecuting && (
                          <div className="flex justify-start mb-2">
                            <div className="bg-blue-50 border border-blue-200 rounded-lg px-3 py-2">
                              <div className="flex items-center space-x-2">
                                <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
                                <span className="text-xs text-blue-700">
                                  {streamProcessor.currentActivity || 'AI正在处理中...'}
                                </span>
                                {streamProcessor.messages.length > 0 && (
                                  <Badge variant="outline" className="text-xs">
                                    {streamProcessor.messages.length} 项操作
                                  </Badge>
                                )}
                              </div>
                            </div>
                          </div>
                        )}
                        
                        {/* 当前消息加载指示器 */}
                        {isLoading && (
                          <div className="flex justify-start">
                            <div className="bg-gray-100 rounded-lg px-4 py-2">
                              <div className="flex items-center space-x-2">
                                <Bot className="h-4 w-4" />
                                <Loader2 className="h-4 w-4 animate-spin" />
                                <span className="text-sm text-gray-600">
                                  {streamProcessor.currentActivity || 'AI正在思考...'}
                                </span>
                              </div>
                            </div>
                          </div>
                        )}
                        
                        {/* 错误提示 */}
                        {error && (
                          <div className="flex justify-center">
                            <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-2">
                              <div className="flex items-center space-x-2 text-red-700">
                                <span className="text-sm">{error.message}</span>
                              </div>
                            </div>
                          </div>
                        )}
                        
                        {/* 滚动锚点 - 用于自动滚动到底部 */}
                        <div ref={messagesEndRef} />
                      </div>
                    </ScrollArea>
                    
                    {/* 滚动到底部按钮 */}
                    <Button
                      variant="outline"
                      size="sm"
                      className="absolute bottom-4 right-4 rounded-full shadow-lg bg-white hover:bg-gray-50"
                      onClick={scrollToBottom}
                      title="滚动到底部"
                    >
                      <ChevronDown className="h-4 w-4" />
                    </Button>
                  </div>
                    
                    {/* 输入区域 */}
                    <form onSubmit={handleSubmit} className="border-t p-4">
                      <div className="flex space-x-2">
                        <Input
                          value={input}
                          onChange={handleInputChange}
                          placeholder="请输入您的问题，例如：'分析测井数据'、'生成孔隙度分布图'、'构建储层模型'..."
                          disabled={isLoading}
                          className="flex-1"
                        />
                        <Button 
                          type="submit"
                          disabled={!input.trim() || isLoading}
                          size="sm"
                        >
                          {isLoading ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Send className="h-4 w-4" />
                          )}
                        </Button>
                      </div>
                    </form>
                  </div>
                </TabsContent>
                
                <TabsContent value="2d" className="flex-1">
                  <div className="h-full flex items-center justify-center">
                    {categories.charts.length > 0 ? (
                      <div className="text-center space-y-4">
                        <BarChart3 className="h-16 w-16 text-blue-500 mx-auto" />
                        <div>
                          <h3 className="text-lg font-medium text-gray-900">2D图表分析</h3>
                          <p className="text-gray-600">发现 {categories.charts.length} 个生成的图表文件</p>
                          <p className="text-sm text-gray-500 mt-2">
                            点击左侧文件树中的图表文件查看详情，或在对话中请求生成新的图表分析
                          </p>
                        </div>
                      </div>
                    ) : (
                      <div className="text-center space-y-4">
                        <BarChart3 className="h-16 w-16 text-gray-400 mx-auto" />
                        <div>
                          <h3 className="text-lg font-medium text-gray-900">2D图表分析</h3>
                          <p className="text-gray-600">尚未生成任何图表</p>
                          <p className="text-sm text-gray-500 mt-2">
                            在AI助手对话中输入指令，例如："生成孔隙度-渗透率散点图"或"绘制测井曲线图"
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                </TabsContent>
                
                <TabsContent value="3d" className="flex-1">
                  <div className="h-full flex items-center justify-center">
                    {categories.models.length > 0 ? (
                      <div className="text-center space-y-4">
                        <Box className="h-16 w-16 text-purple-500 mx-auto" />
                        <div>
                          <h3 className="text-lg font-medium text-gray-900">3D模型视图</h3>
                          <p className="text-gray-600">发现 {categories.models.length} 个模型文件</p>
                          <p className="text-sm text-gray-500 mt-2">
                            3D模型渲染功能正在开发中，您可以下载模型文件在专业软件中查看
                          </p>
                        </div>
                      </div>
                    ) : (
                      <div className="text-center space-y-4">
                        <Box className="h-16 w-16 text-gray-400 mx-auto" />
                        <div>
                          <h3 className="text-lg font-medium text-gray-900">3D模型视图</h3>
                          <p className="text-gray-600">尚未生成任何3D模型</p>
                          <p className="text-sm text-gray-500 mt-2">
                            在AI助手对话中输入指令，例如："构建储层3D模型"或"生成构造模型"
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

export default GeologicalModelingHub;