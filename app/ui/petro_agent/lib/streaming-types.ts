// 前端流式消息类型定义
// 与后端 app/ui/streaming_types.py 保持一致

export enum StreamMessageType {
  // 节点状态消息
  NODE_START = "node_start",
  NODE_END = "node_end", 
  NODE_ERROR = "node_error",
  
  // 路由决策消息
  ROUTER_DECISION = "router_decision",
  ROUTER_PATH = "router_path",
  
  // LLM相关消息
  LLM_TOKEN = "llm_token",
  LLM_START = "llm_start",
  LLM_END = "llm_end",
  
  // 工具/任务执行消息
  TOOL_START = "tool_start",
  TOOL_PROGRESS = "tool_progress", 
  TOOL_RESULT = "tool_result",
  TOOL_ERROR = "tool_error",
  
  // 文件操作消息
  FILE_GENERATED = "file_generated",
  FILE_UPLOADED = "file_uploaded",
  FILE_PROCESSED = "file_processed",
  
  // Agent思考过程
  AGENT_THINKING = "agent_thinking",
  AGENT_PLANNING = "agent_planning",
  AGENT_DECISION = "agent_decision",
  
  // 系统消息
  SYSTEM_INFO = "system_info",
  SYSTEM_WARNING = "system_warning", 
  SYSTEM_ERROR = "system_error",
  
  // 会话状态
  SESSION_START = "session_start",
  SESSION_END = "session_end",
  
  // 检查点
  CHECKPOINT_SAVED = "checkpoint_saved",
  CHECKPOINT_RESTORED = "checkpoint_restored"
}

// 基础流式消息接口
export interface BaseStreamMessage {
  id: string;
  type: StreamMessageType;
  timestamp: string;
  session_id?: string;
  source?: string;
  priority?: 'low' | 'normal' | 'high' | 'critical';
  metadata?: Record<string, any>;
}

// 节点状态消息
export interface NodeStatusMessage extends BaseStreamMessage {
  type: StreamMessageType.NODE_START | StreamMessageType.NODE_END | StreamMessageType.NODE_ERROR;
  node_id: string;
  node_name: string;
  agent_name?: string;
  details?: string;
  error_info?: string;
}

// 路由决策消息
export interface RouterMessage extends BaseStreamMessage {
  type: StreamMessageType.ROUTER_DECISION | StreamMessageType.ROUTER_PATH;
  decision: string;
  available_paths?: string[];
  selected_path?: string;
  confidence?: number;
  reasoning?: string;
}

// LLM Token消息
export interface LLMTokenMessage extends BaseStreamMessage {
  type: StreamMessageType.LLM_TOKEN | StreamMessageType.LLM_START | StreamMessageType.LLM_END;
  content: string;
  model_name?: string;
  token_count?: number;
  is_final?: boolean;
}

// 工具执行消息  
export interface ToolExecutionMessage extends BaseStreamMessage {
  type: StreamMessageType.TOOL_START | StreamMessageType.TOOL_PROGRESS | StreamMessageType.TOOL_RESULT | StreamMessageType.TOOL_ERROR;
  tool_name: string;
  progress?: number;
  status?: string;
  result?: any;
  error_message?: string;
  execution_time?: number;
}

// 文件生成消息
export interface FileGeneratedMessage extends BaseStreamMessage {
  type: StreamMessageType.FILE_GENERATED | StreamMessageType.FILE_UPLOADED | StreamMessageType.FILE_PROCESSED;
  file_id: string;
  file_name: string;
  file_path: string;
  file_type: string;
  file_size?: number;
  category?: string;
  description?: string;
  thumbnail_url?: string;
}

// Agent思考消息
export interface AgentThinkingMessage extends BaseStreamMessage {
  type: StreamMessageType.AGENT_THINKING | StreamMessageType.AGENT_PLANNING | StreamMessageType.AGENT_DECISION;
  agent_name: string;
  content: string;
  reasoning_step?: number;
  total_steps?: number;
  decision_options?: string[];
  selected_option?: string;
}

// 系统消息
export interface SystemMessage extends BaseStreamMessage {
  type: StreamMessageType.SYSTEM_INFO | StreamMessageType.SYSTEM_WARNING | StreamMessageType.SYSTEM_ERROR;
  message: string;
  details?: string;
  action_required?: boolean;
  suggested_actions?: string[];
}

// 会话状态消息
export interface SessionMessage extends BaseStreamMessage {
  type: StreamMessageType.SESSION_START | StreamMessageType.SESSION_END;
  session_info?: Record<string, any>;
}

// 检查点消息
export interface CheckpointMessage extends BaseStreamMessage {
  type: StreamMessageType.CHECKPOINT_SAVED | StreamMessageType.CHECKPOINT_RESTORED;
  checkpoint_id: string;
  checkpoint_data?: any;
}

// 所有消息类型的联合类型
export type StreamMessage = 
  | NodeStatusMessage
  | RouterMessage  
  | LLMTokenMessage
  | ToolExecutionMessage
  | FileGeneratedMessage
  | AgentThinkingMessage
  | SystemMessage
  | SessionMessage
  | CheckpointMessage;

// 消息解析工厂函数
export function parseStreamMessage(data: any): StreamMessage | null {
  try {
    if (!data || !data.type) {
      return null;
    }

    const baseFields = {
      id: data.id || `msg-${Date.now()}-${Math.random()}`,
      timestamp: data.timestamp || new Date().toISOString(),
      session_id: data.session_id,
      source: data.source,
      priority: data.priority || 'normal',
      metadata: data.metadata || data.data || {}
    };

    switch (data.type) {
      case 'node_start':
      case 'node_complete':
      case 'node_error':
        // 适配后端实际发送的格式
        return {
          ...baseFields,
          type: data.type === 'node_complete' ? StreamMessageType.NODE_END : 
                data.type === 'node_start' ? StreamMessageType.NODE_START : StreamMessageType.NODE_ERROR,
          node_id: data.node_name || data.node_id || 'unknown',
          node_name: data.node_name || 'unknown',
          agent_name: data.agent_name || data.source,
          details: data.details || data.content,
          error_info: data.error_message || (data.type === 'node_error' ? data.details : undefined)
        } as NodeStatusMessage;

      case 'route_decision':
      case StreamMessageType.ROUTER_DECISION:
      case StreamMessageType.ROUTER_PATH:
        return {
          ...baseFields,
          type: StreamMessageType.ROUTER_DECISION,
          decision: data.reason || data.decision || 'unknown',
          available_paths: data.available_routes || data.available_paths,
          selected_path: data.to_node || data.selected_path,
          confidence: data.confidence,
          reasoning: data.reason || data.reasoning
        } as RouterMessage;

      case 'llm_token':
      case StreamMessageType.LLM_TOKEN:
      case StreamMessageType.LLM_START:
      case StreamMessageType.LLM_END:
        return {
          ...baseFields,
          type: StreamMessageType.LLM_TOKEN,
          content: data.content || data.token || '',
          model_name: data.llm_model || data.model_name,
          token_count: data.token_count,
          is_final: data.is_complete || data.is_final || false
        } as LLMTokenMessage;

      case 'tool_start':
      case 'tool_progress':
      case 'tool_complete':
      case 'tool_error':
      case StreamMessageType.TOOL_START:
      case StreamMessageType.TOOL_PROGRESS:
      case StreamMessageType.TOOL_RESULT:
      case StreamMessageType.TOOL_ERROR:
        const toolType = data.type === 'tool_complete' ? StreamMessageType.TOOL_RESULT : 
                        data.type === 'tool_start' ? StreamMessageType.TOOL_START :
                        data.type === 'tool_progress' ? StreamMessageType.TOOL_PROGRESS : StreamMessageType.TOOL_ERROR;
        return {
          ...baseFields,
          type: toolType,
          tool_name: data.tool_name || 'unknown',
          progress: data.progress,
          status: data.status || data.action,
          result: data.output || data.result,
          error_message: data.error_message,
          execution_time: data.execution_time || data.duration
        } as ToolExecutionMessage;

      case 'file_generated':
      case StreamMessageType.FILE_GENERATED:
      case StreamMessageType.FILE_UPLOADED:
      case StreamMessageType.FILE_PROCESSED:
        return {
          ...baseFields,
          type: StreamMessageType.FILE_GENERATED,
          file_id: data.file_id || `file-${Date.now()}`,
          file_name: data.file_name || 'unknown',
          file_path: data.file_path || '',
          file_type: data.file_type || 'unknown',
          file_size: data.file_size,
          category: data.category || 'generated',
          description: data.description,
          thumbnail_url: data.thumbnail_url || data.preview_url
        } as FileGeneratedMessage;

      case 'agent_thinking':
      case StreamMessageType.AGENT_THINKING:
      case StreamMessageType.AGENT_PLANNING:
      case StreamMessageType.AGENT_DECISION:
        // 适配后端实际发送的格式
        let content = data.content;
        let agent_name = data.agent_name;
        
        // 处理后端发送的简化格式: {'agent_thinking': '内容'}
        if (typeof data.agent_thinking === 'string') {
          content = data.agent_thinking;
          agent_name = data.source || 'Agent';
        }
        
        // 提取思考内容中的智能体名称
        if (content && content.includes('正在思考:')) {
          const match = content.match(/🤔\s*(\w+)\s*正在思考:\s*(.+)/);
          if (match) {
            agent_name = match[1];
            content = match[2];
          }
        }
        
        return {
          ...baseFields,
          type: StreamMessageType.AGENT_THINKING,
          agent_name: agent_name || data.source || 'Agent',
          content: content || '',
          reasoning_step: data.reasoning_step || data.step_number,
          total_steps: data.total_steps || 5,
          decision_options: data.decision_options,
          selected_option: data.selected_option
        } as AgentThinkingMessage;

      case StreamMessageType.SYSTEM_INFO:
      case StreamMessageType.SYSTEM_WARNING:
      case StreamMessageType.SYSTEM_ERROR:
        return {
          ...baseFields,
          type: data.type,
          message: data.message || data.content,
          details: data.details,
          action_required: data.action_required,
          suggested_actions: data.suggested_actions
        } as SystemMessage;

      case StreamMessageType.SESSION_START:
      case StreamMessageType.SESSION_END:
        return {
          ...baseFields,
          type: data.type,
          session_info: data.session_info
        } as SessionMessage;

      case StreamMessageType.CHECKPOINT_SAVED:
      case StreamMessageType.CHECKPOINT_RESTORED:
        return {
          ...baseFields,
          type: data.type,
          checkpoint_id: data.checkpoint_id,
          checkpoint_data: data.checkpoint_data
        } as CheckpointMessage;

      default:
        console.warn('未知的流式消息类型:', data.type, data);
        return null;
    }
  } catch (error) {
    console.error('解析流式消息失败:', error, data);
    return null;
  }
}

// 消息类型判断工具函数
export function isNodeMessage(msg: StreamMessage): msg is NodeStatusMessage {
  return [StreamMessageType.NODE_START, StreamMessageType.NODE_END, StreamMessageType.NODE_ERROR].includes(msg.type);
}

export function isRouterMessage(msg: StreamMessage): msg is RouterMessage {
  return [StreamMessageType.ROUTER_DECISION, StreamMessageType.ROUTER_PATH].includes(msg.type);
}

export function isLLMMessage(msg: StreamMessage): msg is LLMTokenMessage {
  return [StreamMessageType.LLM_TOKEN, StreamMessageType.LLM_START, StreamMessageType.LLM_END].includes(msg.type);
}

export function isToolMessage(msg: StreamMessage): msg is ToolExecutionMessage {
  return [StreamMessageType.TOOL_START, StreamMessageType.TOOL_PROGRESS, StreamMessageType.TOOL_RESULT, StreamMessageType.TOOL_ERROR].includes(msg.type);
}

export function isFileMessage(msg: StreamMessage): msg is FileGeneratedMessage {
  return [StreamMessageType.FILE_GENERATED, StreamMessageType.FILE_UPLOADED, StreamMessageType.FILE_PROCESSED].includes(msg.type);
}

export function isAgentMessage(msg: StreamMessage): msg is AgentThinkingMessage {
  return [StreamMessageType.AGENT_THINKING, StreamMessageType.AGENT_PLANNING, StreamMessageType.AGENT_DECISION].includes(msg.type);
}

export function isSystemMessage(msg: StreamMessage): msg is SystemMessage {
  return [StreamMessageType.SYSTEM_INFO, StreamMessageType.SYSTEM_WARNING, StreamMessageType.SYSTEM_ERROR].includes(msg.type);
} 