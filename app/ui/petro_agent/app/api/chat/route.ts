import { NextRequest } from 'next/server';

// 流式消息类型定义（与前端保持一致）
enum StreamMessageType {
  NODE_START = "node_start",
  NODE_END = "node_end",
  NODE_ERROR = "node_error",
  ROUTER_DECISION = "router_decision",
  LLM_TOKEN = "llm_token",
  LLM_START = "llm_start", 
  LLM_END = "llm_end",
  TOOL_START = "tool_start",
  TOOL_PROGRESS = "tool_progress",
  TOOL_RESULT = "tool_result",
  TOOL_ERROR = "tool_error",
  FILE_GENERATED = "file_generated",
  AGENT_THINKING = "agent_thinking",
  AGENT_PLANNING = "agent_planning",
  SYSTEM_INFO = "system_info"
}

// LangGraph流数据解析器
class LangGraphStreamParser {
  private sessionId: string;
  private messageId: number = 0;
  private currentNodes: Set<string> = new Set();
  private activeTools: Set<string> = new Set();
  private lastAgentThinking: string = '';

  constructor(sessionId: string) {
    this.sessionId = sessionId;
  }

  generateMessageId(): string {
    return `msg-${this.sessionId}-${++this.messageId}-${Date.now()}`;
  }

  // 解析LangGraph流数据
  parseStreamData(rawData: string): Array<{text?: string, structuredMessage?: any}> {
    const results: Array<{text?: string, structuredMessage?: any}> = [];
    
    try {
      // 解析原始数据
      if (rawData.startsWith('节点 ')) {
        const match = rawData.match(/^节点 (\w+) 数据: (.+)$/);
        if (!match) return results;
        
        const [, nodeType, dataStr] = match;
        let data;
        
        try {
          // 尝试解析JSON数据
          data = JSON.parse(dataStr);
        } catch {
          // 如果不是JSON，当作普通字符串处理
          data = { content: dataStr };
        }

        const parsedResults = this.parseNodeData(nodeType, data);
        results.push(...parsedResults);
      }
    } catch (error) {
      console.warn('解析流数据失败:', error, '原始数据:', rawData);
    }

    return results;
  }

  // 解析不同类型的节点数据
  parseNodeData(nodeType: string, data: any): Array<{text?: string, structuredMessage?: any}> {
    const results: Array<{text?: string, structuredMessage?: any}> = [];

    switch (nodeType) {
      case 'values':
        return this.parseValuesData(data);
      case 'messages':
        return this.parseMessagesData(data);
      case 'updates':
        return this.parseUpdatesData(data);
      case 'custom':
        return this.parseCustomData(data);
      default:
        console.log('未知节点类型:', nodeType);
        return results;
    }
  }

  // 解析values数据（系统状态）
  parseValuesData(data: any): Array<{text?: string, structuredMessage?: any}> {
    const results: Array<{text?: string, structuredMessage?: any}> = [];

    if (data.messages && Array.isArray(data.messages)) {
      const lastMessage = data.messages[data.messages.length - 1];
      
      // 检查是否有新的AI消息
      if (lastMessage && lastMessage.content && typeof lastMessage.content === 'string') {
        // 如果是完整的AI消息，生成LLM结束事件
        if (lastMessage.additional_kwargs || lastMessage.response_metadata) {
          results.push({
            structuredMessage: {
              id: this.generateMessageId(),
              type: StreamMessageType.LLM_END,
              timestamp: new Date().toISOString(),
              session_id: this.sessionId,
              content: lastMessage.content,
              model_name: lastMessage.response_metadata?.model_name,
              token_count: lastMessage.content.length,
              is_final: true
            }
          });
        }
      }
    }

    // 检查工具结果
    if (data.tool_results && Array.isArray(data.tool_results)) {
      data.tool_results.forEach((toolResult: any) => {
        results.push({
          structuredMessage: {
            id: this.generateMessageId(),
            type: StreamMessageType.TOOL_RESULT,
            timestamp: new Date().toISOString(),
            session_id: this.sessionId,
            tool_name: toolResult.tool_name || 'unknown',
            result: toolResult.output,
            status: toolResult.status || 'completed',
            execution_time: toolResult.execution_time
          }
        });
      });
    }

    // 检查文件信息
    if (data.files && typeof data.files === 'object') {
      Object.values(data.files).forEach((fileInfo: any) => {
        if (fileInfo && fileInfo.file_id) {
          results.push({
            structuredMessage: {
              id: this.generateMessageId(),
              type: StreamMessageType.FILE_GENERATED,
              timestamp: new Date().toISOString(),
              session_id: this.sessionId,
              file_id: fileInfo.file_id,
              file_name: fileInfo.file_name,
              file_path: fileInfo.file_path,
              file_type: fileInfo.file_type || 'unknown',
              file_size: fileInfo.size,
              category: this.detectFileCategory(fileInfo.file_name, fileInfo.file_type),
              description: `Generated file: ${fileInfo.file_name}`
            }
          });
        }
      });
    }

    return results;
  }

  // 解析messages数据（LLM token流）
  parseMessagesData(data: any): Array<{text?: string, structuredMessage?: any}> {
    const results: Array<{text?: string, structuredMessage?: any}> = [];

    if (Array.isArray(data)) {
      const [message, metadata] = data;
      
      if (message && message.content !== undefined) {
        const content = message.content || '';
        
        // 检查是否是token流的开始
        if (content === '' && message.id && !message.additional_kwargs?.content) {
          results.push({
            structuredMessage: {
              id: this.generateMessageId(),
              type: StreamMessageType.LLM_START,
              timestamp: new Date().toISOString(),
              session_id: this.sessionId,
              model_name: message.response_metadata?.model_name,
              message_id: message.id
            }
          });
        }
        
        // 处理token流
        if (content) {
          // 返回给AI SDK的文本流
          results.push({
            text: content
          });
          
          // 同时生成结构化消息
          results.push({
            structuredMessage: {
              id: this.generateMessageId(),
              type: StreamMessageType.LLM_TOKEN,
              timestamp: new Date().toISOString(),
              session_id: this.sessionId,
              content: content,
              model_name: message.response_metadata?.model_name,
              token_count: content.length,
              is_final: !!message.response_metadata?.finish_reason
            }
          });
        }
      }
    }

    return results;
  }

  // 解析updates数据（节点状态更新）
  parseUpdatesData(data: any): Array<{text?: string, structuredMessage?: any}> {
    const results: Array<{text?: string, structuredMessage?: any}> = [];

    if (typeof data === 'object' && data !== null) {
      // 遍历更新的节点
      Object.keys(data).forEach(nodeName => {
        const nodeData = data[nodeName];
        
        if (!this.currentNodes.has(nodeName)) {
          // 节点开始执行
          this.currentNodes.add(nodeName);
          results.push({
            structuredMessage: {
              id: this.generateMessageId(),
              type: StreamMessageType.NODE_START,
              timestamp: new Date().toISOString(),
              session_id: this.sessionId,
              node_id: nodeName,
              node_name: nodeName,
              agent_name: this.getAgentNameFromNode(nodeName),
              details: `节点 ${nodeName} 开始执行`
            }
          });
        }

        // 检查是否有路由决策
        if (nodeData && nodeData.agent_analysis) {
          results.push({
            structuredMessage: {
              id: this.generateMessageId(),
              type: StreamMessageType.ROUTER_DECISION,
              timestamp: new Date().toISOString(),
              session_id: this.sessionId,
              decision: nodeData.agent_analysis.task_type || 'unknown',
              reasoning: nodeData.agent_analysis.reasoning || '',
              confidence: 0.8,
              selected_path: nodeName
            }
          });
        }
      });
    }

    return results;
  }

  // 解析custom数据（Agent思考过程）
  parseCustomData(data: any): Array<{text?: string, structuredMessage?: any}> {
    const results: Array<{text?: string, structuredMessage?: any}> = [];

    if (data && data.agent_thinking) {
      const thinking = data.agent_thinking;
      
      // 避免重复的思考消息
      if (thinking !== this.lastAgentThinking) {
        this.lastAgentThinking = thinking;
        
        results.push({
          structuredMessage: {
            id: this.generateMessageId(),
            type: StreamMessageType.AGENT_THINKING,
            timestamp: new Date().toISOString(),
            session_id: this.sessionId,
            content: thinking,
            agent_name: this.extractAgentName(thinking),
            reasoning_step: this.extractReasoningStep(thinking),
            total_steps: 5 // 默认值
          }
        });
      }
    }

    return results;
  }

  // 工具函数
  private detectFileCategory(fileName: string, fileType: string): string {
    if (fileType?.includes('image') || /\.(png|jpg|jpeg|gif|svg)$/i.test(fileName)) {
      return '图表';
    }
    if (/\.(csv|xlsx|xls)$/i.test(fileName)) {
      return '数据';
    }
    if (/\.(las|log)$/i.test(fileName)) {
      return '测井数据';
    }
    if (/report|analysis/i.test(fileName)) {
      return '报告';
    }
    return '其他';
  }

  private getAgentNameFromNode(nodeName: string): string {
    if (nodeName.includes('meta_supervisor')) return 'MetaSupervisor';
    if (nodeName.includes('task_planner')) return 'TaskPlanner';
    if (nodeName.includes('main_agent')) return 'MainAgent';
    if (nodeName.includes('data_agent')) return 'DataAgent';
    if (nodeName.includes('expert_agent')) return 'ExpertAgent';
    return nodeName;
  }

  private extractAgentName(thinking: string): string {
    const match = thinking.match(/(\w+_agent|\w+Agent|\w+Supervisor)\s/);
    return match ? match[1] : 'Agent';
  }

  private extractReasoningStep(thinking: string): number {
    const match = thinking.match(/步骤\s*(\d+)|第\s*(\d+)\s*步/);
    return match ? parseInt(match[1] || match[2]) : 1;
  }
}

export async function POST(req: NextRequest) {
  try {
    console.log('📨 收到聊天请求');
    const body = await req.json();
    const { messages, sessionId } = body;

    if (!messages || !Array.isArray(messages) || messages.length === 0) {
      return new Response(JSON.stringify({ error: 'Messages are required' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const lastMessage = messages[messages.length - 1];
    const userContent = lastMessage.content || '';

    console.log('📝 用户消息:', userContent.substring(0, 100));
    console.log('🆔 会话ID:', sessionId);

    // 构造后端API请求体
    const backendPayload = {
      message: userContent,
      session_id: sessionId || undefined,
      stream: true
    };

    console.log('🚀 调用后端API:', 'http://localhost:7102/api/v1/chat/send-stream');

    // 调用后端API
    const backendResponse = await fetch('http://localhost:7102/api/v1/chat/send-stream', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
      },
      body: JSON.stringify(backendPayload),
    });

    if (!backendResponse.ok) {
      console.error('❌ 后端API调用失败:', backendResponse.status, backendResponse.statusText);
      return new Response(JSON.stringify({ 
        error: `后端API调用失败: ${backendResponse.status} ${backendResponse.statusText}` 
      }), {
        status: backendResponse.status,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    console.log('✅ 后端API响应成功，开始处理流式数据');

    // 检查响应是否有body流
    if (!backendResponse.body) {
      return new Response(JSON.stringify({ error: '后端未返回流式数据' }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // 创建文本流，专注于提取AI响应内容
    const textStream = new ReadableStream({
      start(controller) {
        console.log('🔄 开始处理后端流式数据');
        
        const reader = backendResponse.body!.getReader();
              const decoder = new TextDecoder();
              let buffer = '';
        let totalChars = 0;
              
        const processStream = async () => {
              try {
                while (true) {
                  const { done, value } = await reader.read();
                  
                  if (done) {
                console.log(`✅ 流式数据读取完成，共输出 ${totalChars} 个字符`);
                    controller.close();
                    break;
                  }
                  
              // 解码数据块
                  const chunk = decoder.decode(value, { stream: true });
                  buffer += chunk;
                  
              // 处理SSE格式的完整行
              const lines = buffer.split('\n');
              buffer = lines.pop() || ''; // 保留不完整的行

              for (const line of lines) {
                if (line.trim() === '') continue;

                // 处理SSE格式数据
                if (line.startsWith('data: ')) {
                  const dataStr = line.substring(6).trim();
                  if (dataStr === '') continue;

                  try {
                    const data = JSON.parse(dataStr);
                    
                    // 🔧 更新：支持新的后端消息格式
                    console.log('📦 收到后端数据:', data);
                    
                    // 处理嵌套的消息格式: {"type": "data", "content": {"type": "actual_type", ...}}
                    let actualData = data;
                    if (data.type === 'data' && data.content && typeof data.content === 'object') {
                      actualData = data.content;
                      console.log('📦 解析嵌套数据:', actualData);
                    }
                    
                    // 处理后端发送的token类型消息（LLM输出）
                    if (data.type === 'token' && data.content) {
                      const tokenContent = data.content;
                      if (tokenContent && typeof tokenContent === 'string' && tokenContent.trim()) {
                        // 构造llm_token格式的结构化消息并嵌入
                        const llmTokenMessage = {
                          type: 'llm_token',
                          timestamp: new Date().toISOString(),
                          session_id: data.session_id,
                          source: data.source, 
                          role: data.role,
                          content: tokenContent,
                          is_token: true,
                          token: tokenContent,
                          llm_model: data.llm_model,
                          data: {
                            source: data.source,
                            is_token: true,
                            is_complete: false,
                            token: tokenContent,
                            llm_model: data.llm_model
                          }
                        };
                        
                        
                        const embeddedMessage = `/*STREAM_MESSAGE:${JSON.stringify(llmTokenMessage)}*/`;
                        controller.enqueue(new TextEncoder().encode(embeddedMessage));
                        console.log('📩 嵌入Token结构化消息:', llmTokenMessage.source, tokenContent.length > 20 ? tokenContent.substring(0, 20) + '...' : tokenContent);
                      }
                    }
                    
                    // 处理其他结构化消息 - 嵌入到流中供StreamMessageExtractor提取
                    else if (actualData.type && ['node_start', 'node_complete', 'node_error', 'agent_thinking', 'tool_progress', 'tool_start', 'tool_complete', 'tool_error', 'file_generated', 'route_decision'].includes(actualData.type)) {
                      // 将结构化消息嵌入到文本流中
                      const embeddedMessage = `/*STREAM_MESSAGE:${JSON.stringify(actualData)}*/`;
                      controller.enqueue(new TextEncoder().encode(embeddedMessage));
                      console.log('📩 嵌入结构化消息:', actualData.type, actualData.source || 'unknown');
                    }

                    // 处理start和end标记
                    else if (data.type === 'start') {
                      console.log('🎬 开始接收流式数据，会话ID:', data.session_id);
                    }
                    else if (data.type === 'end') {
                      console.log('🏁 流式数据接收完成，总块数:', data.total_chunks);
                    }
                    else if (data.type === 'error') {
                      console.error('❌ 后端流式错误:', data.error);
                    }
                    else {
                      console.log('⚠️ 未处理的消息类型:', data.type, data);
                    }
                    
                  } catch (parseError) {
                    console.warn('⚠️ JSON解析失败:', parseError);
                      }
                    }
                  }
                }
              } catch (error) {
                console.error('❌ 流处理错误:', error);
                controller.error(error);
          }
        };

        processStream();
      }
    });

    // 返回文本流响应
    return new Response(textStream, {
      headers: {
        'Content-Type': 'text/plain; charset=utf-8',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      },
    });
    
  } catch (error) {
    console.error('❌ API路由错误:', error);
    return new Response(JSON.stringify({ 
      error: '服务器内部错误',
      details: error instanceof Error ? error.message : String(error)
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

// 从后端数据中提取AI响应内容
function extractAIResponseContent(content: any): string | null {
  try {
    // 🔧 新增：直接处理后端新格式的消息
    if (typeof content === 'object' && content !== null) {
      // 处理新的流式消息格式
      if (content.role && content.content) {
        // 如果是assistant角色的消息，直接返回content
        if (content.role === 'assistant' && content.content) {
          // 过滤掉一些系统信息，只返回实际的AI回复内容
          const contentStr = content.content.toString();
          
          // 跳过纯系统状态信息
          if (contentStr.startsWith('📋 任务分析完成') || 
              contentStr.startsWith('✅ 审查通过') ||
              contentStr.includes('节点') && contentStr.includes('状态')) {
            return null;
          }
          
          return contentStr;
        }
        return null;
      }
      
      // 处理工具消息
      if (content.role === 'tool' && content.content) {
        return `🔧 ${content.tool_name || '工具'}: ${content.content}`;
      }
      
      // 处理系统消息
      if (content.role === 'system' && content.content) {
        return `ℹ️ ${content.content}`;
      }
    }

    // 🔧 保持对旧格式的兼容性
    // 检查是否是系统信息类型
    if (content.type !== 'info' || !content.content) {
      return null;
    }

    const contentStr = content.content;
    
    // 只处理节点消息数据
    if (contentStr.includes('节点 messages 数据:')) {
      // 提取AIMessageChunk中的content，支持多种格式
      
      // 格式1: content='内容'
      let match = contentStr.match(/content='([^']*)'/);
      if (match && match[1]) {
        return match[1];
      }
      
      // 格式2: content="内容"
      match = contentStr.match(/content="([^"]*)"/);
      if (match && match[1]) {
        return match[1];
      }
      
      // 格式3: content=内容（没有引号，遇到逗号或括号结束）
      match = contentStr.match(/content=([^,)]+)/);
      if (match && match[1]) {
        const extractedContent = match[1].trim();
        // 过滤掉一些无意义的内容
        if (extractedContent && extractedContent !== 'None' && extractedContent !== 'null') {
          return extractedContent;
        }
      }
    }
    
    // 检查节点自定义数据中的agent思考
    if (contentStr.includes('节点 custom 数据:') && contentStr.includes('agent_thinking')) {
      const match = contentStr.match(/'agent_thinking':\s*'([^']+)'/);
      if (match && match[1]) {
        return `🤔 ${match[1]}`;
      }
    }
    
    return null;
  } catch (error) {
    console.warn('⚠️ 提取AI内容时出错:', error);
    return null;
  }
} 