"use client";

import React from 'react';
import { 
  StreamMessage, 
  StreamMessageType,
  NodeStatusMessage,
  RouterMessage,
  LLMTokenMessage,
  ToolExecutionMessage,
  FileGeneratedMessage,
  AgentThinkingMessage,
  SystemMessage,
  isNodeMessage,
  isRouterMessage,
  isLLMMessage,
  isToolMessage,
  isFileMessage,
  isAgentMessage,
  isSystemMessage
} from '../lib/streaming-types';
import { Card, CardContent } from './ui/card';
import { Badge } from './ui/badge';
import { Progress } from './ui/progress';
import { 
  Play, 
  Pause, 
  CheckCircle, 
  XCircle, 
  Route, 
  MessageSquare, 
  Settings, 
  FileText, 
  Brain, 
  Info, 
  AlertTriangle, 
  AlertCircle,
  Download,
  Eye,
  Loader2,
  Clock,
  Zap
} from 'lucide-react';

// 节点状态消息组件
export function NodeStatusDisplay({ message }: { message: NodeStatusMessage }) {
  const getIcon = () => {
    switch (message.type) {
      case StreamMessageType.NODE_START:
        return <Play className="h-4 w-4 text-green-600" />;
      case StreamMessageType.NODE_END:
        return <CheckCircle className="h-4 w-4 text-green-600" />;
      case StreamMessageType.NODE_ERROR:
        return <XCircle className="h-4 w-4 text-red-600" />;
    }
  };

  const getStatusColor = () => {
    switch (message.type) {
      case StreamMessageType.NODE_START:
        return 'bg-blue-50 border-blue-200';
      case StreamMessageType.NODE_END:
        return 'bg-green-50 border-green-200';
      case StreamMessageType.NODE_ERROR:
        return 'bg-red-50 border-red-200';
    }
  };

  const getStatusText = () => {
    switch (message.type) {
      case StreamMessageType.NODE_START:
        return '开始执行';
      case StreamMessageType.NODE_END:
        return '执行完成';
      case StreamMessageType.NODE_ERROR:
        return '执行错误';
    }
  };

  return (
    <Card className={`mb-2 ${getStatusColor()}`}>
      <CardContent className="p-3">
        <div className="flex items-center space-x-2">
          {getIcon()}
          <div className="flex-1">
            <div className="flex items-center space-x-2">
              <span className="font-medium text-sm">{message.node_name}</span>
              <Badge variant="outline" className="text-xs">
                {getStatusText()}
              </Badge>
              {message.agent_name && (
                <Badge variant="secondary" className="text-xs">
                  {message.agent_name}
                </Badge>
              )}
            </div>
            {message.details && (
              <p className="text-xs text-gray-600 mt-1">{message.details}</p>
            )}
            {message.error_info && (
              <p className="text-xs text-red-600 mt-1 font-mono bg-red-50 p-1 rounded">
                {message.error_info}
              </p>
            )}
          </div>
          <span className="text-xs text-gray-500">
            {new Date(message.timestamp).toLocaleTimeString()}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

// 路由决策消息组件
export function RouterDisplay({ message }: { message: RouterMessage }) {
  return (
    <Card className="mb-2 bg-purple-50 border-purple-200">
      <CardContent className="p-3">
        <div className="flex items-center space-x-2">
          <Route className="h-4 w-4 text-purple-600" />
          <div className="flex-1">
            <div className="flex items-center space-x-2">
              <span className="font-medium text-sm">路由决策</span>
              <Badge variant="outline" className="text-xs bg-purple-100">
                {message.decision}
              </Badge>
              {message.confidence && (
                <Badge variant="secondary" className="text-xs">
                  置信度: {Math.round(message.confidence * 100)}%
                </Badge>
              )}
            </div>
            {message.available_paths && (
              <p className="text-xs text-gray-600 mt-1">
                可选路径: {message.available_paths.join(', ')}
              </p>
            )}
            {message.selected_path && (
              <p className="text-xs text-purple-700 mt-1 font-medium">
                选择: {message.selected_path}
              </p>
            )}
            {message.reasoning && (
              <p className="text-xs text-gray-600 mt-1 italic">
                推理: {message.reasoning}
              </p>
            )}
          </div>
          <span className="text-xs text-gray-500">
            {new Date(message.timestamp).toLocaleTimeString()}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

// LLM Token消息组件 (通常不单独显示，而是累积到聊天消息中)
export function LLMTokenDisplay({ message }: { message: LLMTokenMessage }) {
  if (message.type === StreamMessageType.LLM_TOKEN) {
    // Token通常不单独显示，直接返回null或在父组件中处理
    return null;
  }

  const getIcon = () => {
    switch (message.type) {
      case StreamMessageType.LLM_START:
        return <MessageSquare className="h-4 w-4 text-blue-600" />;
      case StreamMessageType.LLM_END:
        return <CheckCircle className="h-4 w-4 text-green-600" />;
    }
  };

  return (
    <Card className="mb-2 bg-blue-50 border-blue-200">
      <CardContent className="p-3">
        <div className="flex items-center space-x-2">
          {getIcon()}
          <div className="flex-1">
            <div className="flex items-center space-x-2">
              <span className="font-medium text-sm">AI思考</span>
              {message.model_name && (
                <Badge variant="outline" className="text-xs">
                  {message.model_name}
                </Badge>
              )}
              {message.token_count && (
                <Badge variant="secondary" className="text-xs">
                  {message.token_count} tokens
                </Badge>
              )}
            </div>
            {message.content && (
              <p className="text-xs text-gray-600 mt-1">{message.content}</p>
            )}
          </div>
          <span className="text-xs text-gray-500">
            {new Date(message.timestamp).toLocaleTimeString()}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

// 工具执行消息组件
export function ToolExecutionDisplay({ message }: { message: ToolExecutionMessage }) {
  const getIcon = () => {
    switch (message.type) {
      case StreamMessageType.TOOL_START:
        return <Loader2 className="h-4 w-4 text-blue-600 animate-spin" />;
      case StreamMessageType.TOOL_PROGRESS:
        return <Settings className="h-4 w-4 text-orange-600" />;
      case StreamMessageType.TOOL_RESULT:
        return <CheckCircle className="h-4 w-4 text-green-600" />;
      case StreamMessageType.TOOL_ERROR:
        return <XCircle className="h-4 w-4 text-red-600" />;
    }
  };

  const getStatusColor = () => {
    switch (message.type) {
      case StreamMessageType.TOOL_START:
        return 'bg-blue-50 border-blue-200';
      case StreamMessageType.TOOL_PROGRESS:
        return 'bg-orange-50 border-orange-200';
      case StreamMessageType.TOOL_RESULT:
        return 'bg-green-50 border-green-200';
      case StreamMessageType.TOOL_ERROR:
        return 'bg-red-50 border-red-200';
    }
  };

  const getStatusText = () => {
    switch (message.type) {
      case StreamMessageType.TOOL_START:
        return '开始执行';
      case StreamMessageType.TOOL_PROGRESS:
        return '执行中';
      case StreamMessageType.TOOL_RESULT:
        return '执行完成';
      case StreamMessageType.TOOL_ERROR:
        return '执行失败';
    }
  };

  return (
    <Card className={`mb-2 ${getStatusColor()}`}>
      <CardContent className="p-3">
        <div className="flex items-center space-x-2">
          {getIcon()}
          <div className="flex-1">
            <div className="flex items-center space-x-2">
              <span className="font-medium text-sm">{message.tool_name}</span>
              <Badge variant="outline" className="text-xs">
                {getStatusText()}
              </Badge>
              {message.execution_time && (
                <Badge variant="secondary" className="text-xs flex items-center space-x-1">
                  <Clock className="h-3 w-3" />
                  <span>{message.execution_time}ms</span>
                </Badge>
              )}
            </div>
            
            {message.status && (
              <p className="text-xs text-gray-600 mt-1">{message.status}</p>
            )}
            
            {message.progress !== undefined && (
              <div className="mt-2">
                <div className="flex items-center space-x-2">
                  <Progress value={message.progress} className="flex-1 h-2" />
                  <span className="text-xs text-gray-500">{message.progress}%</span>
                </div>
              </div>
            )}
            
            {message.result && (
              <div className="mt-2 p-2 bg-gray-50 rounded text-xs font-mono">
                {typeof message.result === 'string' ? message.result : JSON.stringify(message.result, null, 2)}
              </div>
            )}
            
            {message.error_message && (
              <p className="text-xs text-red-600 mt-1 font-mono bg-red-50 p-1 rounded">
                {message.error_message}
              </p>
            )}
          </div>
          <span className="text-xs text-gray-500">
            {new Date(message.timestamp).toLocaleTimeString()}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

// 文件生成消息组件
export function FileGeneratedDisplay({ 
  message, 
  onView, 
  onDownload 
}: { 
  message: FileGeneratedMessage;
  onView?: (file: FileGeneratedMessage) => void;
  onDownload?: (file: FileGeneratedMessage) => void;
}) {
  const getFileIcon = () => {
    if (message.file_type.includes('image')) {
      return <FileText className="h-4 w-4 text-blue-600" />;
    }
    return <FileText className="h-4 w-4 text-green-600" />;
  };

  const getStatusColor = () => {
    switch (message.type) {
      case StreamMessageType.FILE_GENERATED:
        return 'bg-green-50 border-green-200';
      case StreamMessageType.FILE_UPLOADED:
        return 'bg-blue-50 border-blue-200';
      case StreamMessageType.FILE_PROCESSED:
        return 'bg-purple-50 border-purple-200';
    }
  };

  const getStatusText = () => {
    switch (message.type) {
      case StreamMessageType.FILE_GENERATED:
        return '文件已生成';
      case StreamMessageType.FILE_UPLOADED:
        return '文件已上传';
      case StreamMessageType.FILE_PROCESSED:
        return '文件已处理';
    }
  };

  const formatFileSize = (bytes?: number) => {
    if (!bytes) return '';
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  };

  return (
    <Card className={`mb-2 ${getStatusColor()}`}>
      <CardContent className="p-3">
        <div className="flex items-center space-x-2">
          {getFileIcon()}
          <div className="flex-1">
            <div className="flex items-center space-x-2">
              <span className="font-medium text-sm">{message.file_name}</span>
              <Badge variant="outline" className="text-xs">
                {getStatusText()}
              </Badge>
              {message.category && (
                <Badge variant="secondary" className="text-xs">
                  {message.category}
                </Badge>
              )}
            </div>
            
            <div className="flex items-center space-x-2 mt-1">
              <span className="text-xs text-gray-500">{message.file_type}</span>
              {message.file_size && (
                <span className="text-xs text-gray-500">
                  • {formatFileSize(message.file_size)}
                </span>
              )}
            </div>
            
            {message.description && (
              <p className="text-xs text-gray-600 mt-1">{message.description}</p>
            )}
            
            <div className="flex items-center space-x-2 mt-2">
              {onView && (
                <button
                  onClick={() => onView(message)}
                  className="text-xs bg-blue-100 hover:bg-blue-200 text-blue-700 px-2 py-1 rounded flex items-center space-x-1"
                >
                  <Eye className="h-3 w-3" />
                  <span>查看</span>
                </button>
              )}
              {onDownload && (
                <button
                  onClick={() => onDownload(message)}
                  className="text-xs bg-green-100 hover:bg-green-200 text-green-700 px-2 py-1 rounded flex items-center space-x-1"
                >
                  <Download className="h-3 w-3" />
                  <span>下载</span>
                </button>
              )}
            </div>
          </div>
          <span className="text-xs text-gray-500">
            {new Date(message.timestamp).toLocaleTimeString()}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

// Agent思考消息组件
export function AgentThinkingDisplay({ message }: { message: AgentThinkingMessage }) {
  const getIcon = () => {
    switch (message.type) {
      case StreamMessageType.AGENT_THINKING:
        return <Brain className="h-4 w-4 text-purple-600" />;
      case StreamMessageType.AGENT_PLANNING:
        return <Route className="h-4 w-4 text-blue-600" />;
      case StreamMessageType.AGENT_DECISION:
        return <Zap className="h-4 w-4 text-orange-600" />;
    }
  };

  const getStatusColor = () => {
    switch (message.type) {
      case StreamMessageType.AGENT_THINKING:
        return 'bg-purple-50 border-purple-200';
      case StreamMessageType.AGENT_PLANNING:
        return 'bg-blue-50 border-blue-200';
      case StreamMessageType.AGENT_DECISION:
        return 'bg-orange-50 border-orange-200';
    }
  };

  const getStatusText = () => {
    switch (message.type) {
      case StreamMessageType.AGENT_THINKING:
        return '思考中';
      case StreamMessageType.AGENT_PLANNING:
        return '制定计划';
      case StreamMessageType.AGENT_DECISION:
        return '做出决策';
    }
  };

  return (
    <Card className={`mb-2 ${getStatusColor()}`}>
      <CardContent className="p-3">
        <div className="flex items-center space-x-2">
          {getIcon()}
          <div className="flex-1">
            <div className="flex items-center space-x-2">
              <span className="font-medium text-sm">{message.agent_name}</span>
              <Badge variant="outline" className="text-xs">
                {getStatusText()}
              </Badge>
              {message.reasoning_step && message.total_steps && (
                <Badge variant="secondary" className="text-xs">
                  步骤 {message.reasoning_step}/{message.total_steps}
                </Badge>
              )}
            </div>
            
            <p className="text-xs text-gray-700 mt-1 italic">{message.content}</p>
            
            {message.decision_options && (
              <div className="mt-2">
                <p className="text-xs text-gray-600 mb-1">选项:</p>
                <div className="flex flex-wrap gap-1">
                  {message.decision_options.map((option, index) => (
                    <Badge 
                      key={index} 
                      variant={option === message.selected_option ? "default" : "outline"}
                      className="text-xs"
                    >
                      {option}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
          <span className="text-xs text-gray-500">
            {new Date(message.timestamp).toLocaleTimeString()}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

// 系统消息组件
export function SystemMessageDisplay({ message }: { message: SystemMessage }) {
  const getIcon = () => {
    switch (message.type) {
      case StreamMessageType.SYSTEM_INFO:
        return <Info className="h-4 w-4 text-blue-600" />;
      case StreamMessageType.SYSTEM_WARNING:
        return <AlertTriangle className="h-4 w-4 text-yellow-600" />;
      case StreamMessageType.SYSTEM_ERROR:
        return <AlertCircle className="h-4 w-4 text-red-600" />;
    }
  };

  const getStatusColor = () => {
    switch (message.type) {
      case StreamMessageType.SYSTEM_INFO:
        return 'bg-blue-50 border-blue-200';
      case StreamMessageType.SYSTEM_WARNING:
        return 'bg-yellow-50 border-yellow-200';
      case StreamMessageType.SYSTEM_ERROR:
        return 'bg-red-50 border-red-200';
    }
  };

  const getStatusText = () => {
    switch (message.type) {
      case StreamMessageType.SYSTEM_INFO:
        return '系统信息';
      case StreamMessageType.SYSTEM_WARNING:
        return '系统警告';
      case StreamMessageType.SYSTEM_ERROR:
        return '系统错误';
    }
  };

  return (
    <Card className={`mb-2 ${getStatusColor()}`}>
      <CardContent className="p-3">
        <div className="flex items-center space-x-2">
          {getIcon()}
          <div className="flex-1">
            <div className="flex items-center space-x-2">
              <span className="font-medium text-sm">{getStatusText()}</span>
              {message.action_required && (
                <Badge variant="destructive" className="text-xs">
                  需要操作
                </Badge>
              )}
            </div>
            
            <p className="text-xs text-gray-700 mt-1">{message.message}</p>
            
            {message.details && (
              <p className="text-xs text-gray-600 mt-1 font-mono bg-gray-50 p-1 rounded">
                {message.details}
              </p>
            )}
            
            {message.suggested_actions && (
              <div className="mt-2">
                <p className="text-xs text-gray-600 mb-1">建议操作:</p>
                <ul className="text-xs text-gray-700 list-disc list-inside">
                  {message.suggested_actions.map((action, index) => (
                    <li key={index}>{action}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          <span className="text-xs text-gray-500">
            {new Date(message.timestamp).toLocaleTimeString()}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

// 通用流式消息显示组件
export function StreamMessageDisplay({ 
  message, 
  onFileView, 
  onFileDownload 
}: { 
  message: StreamMessage;
  onFileView?: (file: FileGeneratedMessage) => void;
  onFileDownload?: (file: FileGeneratedMessage) => void;
}) {
  if (isNodeMessage(message)) {
    return <NodeStatusDisplay message={message} />;
  }
  
  if (isRouterMessage(message)) {
    return <RouterDisplay message={message} />;
  }
  
  if (isLLMMessage(message)) {
    return <LLMTokenDisplay message={message} />;
  }
  
  if (isToolMessage(message)) {
    return <ToolExecutionDisplay message={message} />;
  }
  
  if (isFileMessage(message)) {
    return (
      <FileGeneratedDisplay 
        message={message} 
        onView={onFileView}
        onDownload={onFileDownload}
      />
    );
  }
  
  if (isAgentMessage(message)) {
    return <AgentThinkingDisplay message={message} />;
  }
  
  if (isSystemMessage(message)) {
    return <SystemMessageDisplay message={message} />;
  }
  
  return null;
} 