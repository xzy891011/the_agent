"use client";

import React from 'react';
import { 
  StreamMessage, 
  StreamMessageType,
  NodeStatusMessage,
  ToolExecutionMessage,
  FileGeneratedMessage,
  AgentThinkingMessage,
  SystemMessage
} from '../lib/streaming-types';
import { 
  StreamMessageDisplay,
  NodeStatusDisplay,
  ToolExecutionDisplay,
  FileGeneratedDisplay,
  AgentThinkingDisplay,
  SystemMessageDisplay
} from './stream-messages';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { 
  CheckCircle, 
  AlertCircle, 
  Clock, 
  FileText, 
  Brain, 
  BarChart3, 
  Settings,
  Download,
  Image,
  Info,
  TrendingUp,
  User,
  Bot
} from 'lucide-react';
import { parseStreamMessage } from '@/lib/streaming-types';

// 消息段落类型
interface MessageSegment {
  type: 'text' | 'node_status' | 'tool_execution' | 'file_generated' | 'agent_thinking' | 'system_message' | 'analysis_result';
  content: string;
  data?: any;
  timestamp?: string;
}

// 智能消息解析器类
class IntelligentMessageParser {
  // 解析AI消息内容，优先处理结构化消息，然后处理普通文本
  parseMessage(content: string): MessageSegment[] {
    const segments: MessageSegment[] = [];
    
    // 首先尝试提取结构化消息
      const structuredMessagesRaw = this.extractStructuredMessages(content);
      // 将连续的 llm_token 合并为一个结构化消息，避免每个 token 一个卡片
      const structuredMessages = this.accumulateLLMTokens(structuredMessagesRaw);
    
    if (structuredMessages.length > 0) {
      // 如果有结构化消息，优先处理这些消息
      structuredMessages.forEach(messageData => {
        const segment = this.createSegmentFromStructuredMessage(messageData);
        if (segment) {
          segments.push(segment);
        }
      });
      
      // 获取清理后的文本内容（移除结构化消息标记）
      let cleanText = content;
      const messageRegex = /\/\*STREAM_MESSAGE:(.+?)\*\//g;
      cleanText = cleanText.replace(messageRegex, '').trim();
      
      // 如果还有剩余的文本内容，解析为普通文本
      if (cleanText) {
        segments.push({
          type: 'text',
          content: cleanText,
          data: {},
          timestamp: new Date().toISOString()
        });
      }
    } else {
      // 没有结构化消息，使用传统解析方法
      return this.parseMessageLegacy(content);
    }
    
    return segments;
  }

  // 提取结构化消息
  private extractStructuredMessages(content: string): any[] {
    const messages: any[] = [];
    const messageRegex = /\/\*STREAM_MESSAGE:(.+?)\*\//g;
    let match;
    
    while ((match = messageRegex.exec(content)) !== null) {
      try {
        const messageData = JSON.parse(match[1]);
        messages.push(messageData);
      } catch (error) {
        console.warn('解析结构化消息失败:', error, match[1]);
      }
    }
    
    return messages;
  }

    // 将连续的 LLM token 进行聚合，合并为一条结构化消息
    private accumulateLLMTokens(messages: any[]): any[] {
      if (!messages || messages.length === 0) return messages;
      const result: any[] = [];
      let tokenBuffer: any | null = null;
      for (const msg of messages) {
        if (msg && msg.type === 'llm_token') {
          // 检查source是否发生变化，如果变化则需要flush当前buffer
          const currentSource = msg.source || '';
          const bufferSource = tokenBuffer?.source || '';
          
          if (!tokenBuffer || (currentSource && bufferSource && currentSource !== bufferSource)) {
            // 如果有现有buffer且source发生变化，先flush现有buffer
            if (tokenBuffer && currentSource !== bufferSource) {
              result.push(tokenBuffer);
            }
            // 初始化新的缓冲，保留关键信息
            tokenBuffer = {
              ...msg,
              content: msg.content || '',
              // 标记为聚合后的token，便于下游识别
              aggregated: true
            };
          } else {
            tokenBuffer.content += msg.content || '';
            // 合并模型与来源等元数据（以最新为准）
            tokenBuffer.llm_model = msg.llm_model || tokenBuffer.llm_model;
            // 保持原始source，不覆盖
            if (msg.metadata) {
              tokenBuffer.metadata = { ...(tokenBuffer.metadata || {}), ...msg.metadata };
            }
          }
          // 如果出现显式完成标记，立即flush
          if (msg.is_complete) {
            result.push(tokenBuffer);
            tokenBuffer = null;
          }
        } else {
          // 遇到非token消息，先flush已累积token
          if (tokenBuffer) {
            result.push(tokenBuffer);
            tokenBuffer = null;
          }
          result.push(msg);
        }
      }
      // 结束时flush剩余token
      if (tokenBuffer) {
        result.push(tokenBuffer);
      }
      return result;
    }

  // 根据结构化消息创建MessageSegment
  private createSegmentFromStructuredMessage(messageData: any): MessageSegment | null {
    if (!messageData.type) {
      return null;
    }

    const timestamp = messageData.timestamp || new Date().toISOString();

    switch (messageData.type) {
      case 'node_start':
      case 'node_complete':
      case 'node_error':
        return {
          type: 'node_status',
          content: messageData.content || '',
          data: {
            node_name: messageData.node_name,
            status: messageData.status,
            details: messageData.details,
            action: messageData.type === 'node_start' ? 'start' : 
                   messageData.type === 'node_complete' ? 'complete' : 'error',
            source: messageData.source
          },
          timestamp
        };

      case 'agent_thinking':
        return {
          type: 'agent_thinking',
          content: messageData.content || '',
          data: {
            agent_name: messageData.agent_name,
            thinking_type: messageData.thinking_type,
            // 提取纯净的思考内容（去掉emoji前缀）
            thinking_content: this.extractThinkingContent(messageData.content || ''),
            source: messageData.source
          },
          timestamp
        };

      case 'tool_start':
      case 'tool_progress':
      case 'tool_complete':
      case 'tool_error':
        return {
          type: 'tool_execution',
          content: messageData.content || '',
          data: {
            tool_name: messageData.tool_name || messageData.source,
            action: messageData.action || messageData.type.replace('tool_', ''),
            status: messageData.status,
            progress: messageData.progress,
            details: messageData.details,
            output: messageData.output,
            error_message: messageData.error_message
          },
          timestamp
        };

      case 'file_generated':
        return {
          type: 'file_generated',
          content: messageData.content || '',
          data: {
            file_id: messageData.file_id,
            file_name: messageData.file_name,
            file_type: messageData.file_type,
            file_path: messageData.file_path,
            category: messageData.category,
            description: `已生成文件: ${messageData.file_name}`
          },
          timestamp
        };

      case 'llm_token':
        // 对于LLM token，需要根据内容区分是系统状态消息还是Agent思考
        const content = messageData.content || '';
        
        // 1. 如果是系统状态信息，归类为system_message
        if (this.isSystemStatusMessage(content)) {
          return {
            type: 'system_message',
            content: content,
            data: {
              source: messageData.source,
              llm_model: messageData.llm_model,
              is_token: messageData.is_token,
              status_type: this.getSystemStatusType(content),
              metadata: messageData.metadata
            },
            timestamp
          };
        }
        
        // 2. 普通LLM输出归类为agent_thinking
        // 从'source'键值解析智能体名称和思考类型
        const source = messageData.source || '';
        let agentName = 'unknown_agent';
        let thinkingType = 'thinking';
        
        if (source) {
          // 解析source字段，格式通常为 "agent_name_action" 或 "agent_name"
          
          // 特殊处理已知的节点名称
          if (source === 'critic') {
            agentName = 'critic';
            thinkingType = 'review';
          } else if (source === 'meta_supervisor') {
            agentName = 'meta_supervisor';
            thinkingType = 'analysis';
          } else if (source === 'runtime_supervisor') {
            agentName = 'runtime_supervisor';
            thinkingType = 'monitoring';
          } else if (source === 'smart_router') {
            agentName = 'smart_router';
            thinkingType = 'router';
          } else if (source === 'assistant') {
            agentName = 'assistant';
            thinkingType = 'thinking';
          } else {
            // 通用解析逻辑
            const parts = source.split('_');
            if (parts.length >= 2) {
              // 检查是否为标准的智能体格式 "xxx_agent_yyy"
              const agentIndex = parts.indexOf('agent');
              if (agentIndex !== -1) {
                // 格式如 "main_agent_analyze" -> agentName: "main_agent", thinkingType: "analyze"
                agentName = parts.slice(0, agentIndex + 1).join('_');
                thinkingType = parts.slice(agentIndex + 1).join('_');
              } else {
                // 格式如 "main_analyze" -> agentName: "main", thinkingType: "analyze"
                agentName = parts[0];
                thinkingType = parts.slice(1).join('_');
              }
            } else {
              // 只有一个部分，当作智能体名称
              agentName = source;
              thinkingType = 'thinking';
            }
          }
          
          // 标准化思考类型映射
          const thinkingTypeMap: { [key: string]: string } = {
            'analyze': 'analysis',
            'execute_task': 'execute_task', 
            'respond': 'respond',
            'plan': 'planning',
            'review': 'review',
            'think': 'thinking',
            'monitor': 'monitoring',
            'decision': 'decision_making'
          };
          
          thinkingType = thinkingTypeMap[thinkingType] || thinkingType || 'thinking';
        }

        return {
          type: 'agent_thinking',
          content: content,
          data: {
            agent_name: agentName,
            thinking_type: thinkingType,
            thinking_content: content,
            source: source,
            llm_model: messageData.llm_model,
            is_token: messageData.is_token,
            metadata: messageData.metadata
          },
          timestamp
        };

      case 'route_decision':
        return {
          type: 'system_message',
          content: messageData.content || '',
          data: {
            from_node: messageData.from_node,
            to_node: messageData.to_node,
            reason: messageData.reason,
            decision_type: 'route'
          },
          timestamp
        };

      default:
        // 未知类型归类为system_message
        return {
          type: 'system_message',
          content: messageData.content || JSON.stringify(messageData),
          data: messageData,
          timestamp
        };
    }
  }

  // 提取纯净的思考内容
  private extractThinkingContent(content: string): string {
    // 移除emoji前缀，如 "🤔 main_agent 正在思考: "
    const match = content.match(/🤔\s*\w+\s*正在思考:\s*(.+)/) || 
                  content.match(/🔍\s*(.+)/) || 
                  content.match(/💭\s*(.+)/);
    return match ? match[1].trim() : content;
  }

  // 判断是否为系统状态消息
  private isSystemStatusMessage(content: string): boolean {
    if (!content) return false;
    
    const systemPatterns = [
      /^📋\s*任务分析完成/,
      /^✅\s*审查通过/,
      /^❌\s*审查失败/,
      /TaskType\./,
      /复杂度:/,
      /评分:/
    ];
    
    return systemPatterns.some(pattern => pattern.test(content));
  }

  // 获取系统状态类型
  private getSystemStatusType(content: string): string {
    if (content.includes('任务分析完成')) return 'task_analysis';
    if (content.includes('审查通过')) return 'review_passed';
    if (content.includes('审查失败')) return 'review_failed';
    return 'general';
  }

  // 传统解析方法（保持向后兼容）
  private parseMessageLegacy(content: string): MessageSegment[] {
    const segments: MessageSegment[] = [];
    
    // 特殊标记（emoji）
    const emojiMarkers = ['📋', '🤔', '🔍', '📝', '💭', '💬', '✅', '❌', '⚠️', '🔧', '📁', '📄', '🧠', 'ℹ️', '🎯', '📊'];
    
    // 创建用于分割的正则表达式，匹配emoji开头的内容
    const emojiPattern = new RegExp(`(${emojiMarkers.join('|')})`, 'g');
    
    // 首先尝试按emoji分割
    if (emojiPattern.test(content)) {
      // 重置正则表达式位置
      emojiPattern.lastIndex = 0;
      
      // 使用更高级的分割逻辑
      const emojiRegex = new RegExp(`(${emojiMarkers.join('|')}.*?)(?=${emojiMarkers.join('|')}|$)`, 'g');
      let match;
      
      while ((match = emojiRegex.exec(content)) !== null) {
        const segment = match[1].trim();
        if (segment) {
          const type = this.detectSegmentType(segment);
          segments.push({
            type,
            content: segment,
            data: this.extractSegmentData(type, segment),
            timestamp: new Date().toISOString()
          });
        }
      }
      
      // 如果正则匹配没有找到任何内容，则尝试简单分割
      if (segments.length === 0) {
        // 按emoji字符分割
        const parts = content.split(new RegExp(`(${emojiMarkers.join('|')})`, 'g')).filter(part => part.trim());
        
        let currentContent = '';
        
        for (let i = 0; i < parts.length; i++) {
          const part = parts[i].trim();
          if (!part) continue;
          
          // 如果是emoji标记
          if (emojiMarkers.includes(part)) {
            // 保存之前的内容
            if (currentContent.trim()) {
              const type = this.detectSegmentType(currentContent);
              segments.push({
                type,
                content: currentContent.trim(),
                data: this.extractSegmentData(type, currentContent),
                timestamp: new Date().toISOString()
              });
            }
            
            // 开始新的段落，包含emoji
            currentContent = part;
          } else {
            // 添加到当前内容
            if (currentContent) {
              currentContent += ' ' + part;
            } else {
              currentContent = part;
            }
          }
        }
        
        // 保存最后一个段落
        if (currentContent.trim()) {
          const type = this.detectSegmentType(currentContent);
          segments.push({
            type,
            content: currentContent.trim(),
            data: this.extractSegmentData(type, currentContent),
            timestamp: new Date().toISOString()
          });
        }
      }
    } else {
      // 如果没有emoji，按行分割并检测类型变化
      const lines = content.split('\n').filter(line => line.trim());
      let currentSegment = '';
      let currentType: MessageSegment['type'] = 'text';
      
      for (const line of lines) {
        const trimmedLine = line.trim();
        if (!trimmedLine) continue;
        
        const lineType = this.detectSegmentType(trimmedLine);
        
        // 如果类型发生变化，保存当前段落
        if (lineType !== currentType && currentSegment.trim()) {
          segments.push({
            type: currentType,
            content: currentSegment.trim(),
            data: this.extractSegmentData(currentType, currentSegment),
            timestamp: new Date().toISOString()
          });
          currentSegment = '';
        }
        
        // 更新类型并添加内容
        currentType = lineType;
        if (currentSegment) {
          currentSegment += '\n' + trimmedLine;
        } else {
          currentSegment = trimmedLine;
        }
      }
      
      // 保存最后一个段落
      if (currentSegment.trim()) {
        segments.push({
          type: currentType,
          content: currentSegment.trim(),
          data: this.extractSegmentData(currentType, currentSegment),
          timestamp: new Date().toISOString()
        });
      }
    }
    
    // 如果仍然没有段落，将整个内容作为文本
    if (segments.length === 0 && content.trim()) {
      segments.push({
        type: 'text',
        content: content.trim(),
        data: {},
        timestamp: new Date().toISOString()
      });
    }
    
    // 合并相同类型的连续段落
    const mergedSegments = this.mergeConsecutiveSegments(segments);
    
    return mergedSegments;
  }

  // 合并相同类型的连续段落
  private mergeConsecutiveSegments(segments: MessageSegment[]): MessageSegment[] {
    if (segments.length <= 1) {
      return segments;
    }

    const merged: MessageSegment[] = [];
    let currentSegment = segments[0];

    for (let i = 1; i < segments.length; i++) {
      const nextSegment = segments[i];
      
      // 如果类型相同且时间戳相近（同一次解析），则合并
      if (currentSegment.type === nextSegment.type && 
          this.shouldMergeSegments(currentSegment, nextSegment)) {
        
        // 合并内容，用适当的分隔符
        const separator = this.getMergeSeparator(currentSegment.type);
        currentSegment.content += separator + nextSegment.content;
        
        // 合并数据（保留第一个段落的数据，但也合并有用的信息）
        if (nextSegment.data && Object.keys(nextSegment.data).length > 0) {
          currentSegment.data = { ...currentSegment.data, ...nextSegment.data };
        }
      } else {
        // 类型不同，保存当前段落并开始新段落
        merged.push(currentSegment);
        currentSegment = nextSegment;
      }
    }

    // 添加最后一个段落
    merged.push(currentSegment);
    
    return merged;
  }

  // 判断是否应该合并两个段落
  private shouldMergeSegments(current: MessageSegment, next: MessageSegment): boolean {
    // 相同类型才考虑合并
    if (current.type !== next.type) {
      return false;
    }

    // 检查合并后的内容是否会过长（避免UI渲染问题）
    const combinedLength = current.content.length + next.content.length;
    if (combinedLength > 2000) {
      console.log('⚠️ 跳过合并：合并后内容过长', { combinedLength, currentType: current.type });
      return false;
    }

    // 检查是否包含JSON或特殊格式内容（不应该合并）
    const hasJsonPattern = /```json|{[\s\S]*}|\[[\s\S]*\]/.test(current.content + next.content);
    if (hasJsonPattern) {
      console.log('⚠️ 跳过合并：包含JSON或特殊格式', { currentType: current.type });
      return false;
    }

    // 检查是否包含不同类型的标记（如调试信息vs普通思考）
    const currentHasDebug = /\[调试\]|\[DEBUG\]|\[测试\]/.test(current.content);
    const nextHasDebug = /\[调试\]|\[DEBUG\]|\[测试\]/.test(next.content);
    if (currentHasDebug !== nextHasDebug) {
      console.log('⚠️ 跳过合并：调试标记不匹配', { currentHasDebug, nextHasDebug });
      return false;
    }

    // 只有内容很短的情况下才考虑合并
    const shouldMerge = (current.content.length < 100 && next.content.length < 100) ||
                       (current.content.length < 30 || next.content.length < 30);

    if (shouldMerge) {
      console.log('✅ 执行合并：', { 
        type: current.type, 
        currentLength: current.content.length, 
        nextLength: next.content.length 
      });
    }

    return shouldMerge;
  }

  // 获取合并时使用的分隔符
  private getMergeSeparator(type: MessageSegment['type']): string {
    switch (type) {
      case 'agent_thinking':
        return ' '; // 思考过程用空格连接，保持流畅性
      case 'text':
        return ' '; // 普通文本用空格连接
      case 'tool_execution':
        return '\n'; // 工具执行用换行连接，保持结构
      case 'system_message':
        return '\n'; // 系统消息用换行分隔
      case 'node_status':
        return '\n'; // 节点状态用换行分隔
      case 'analysis_result':
        return ' '; // 分析结果用空格连接
      case 'file_generated':
        return '\n'; // 文件生成用换行分隔
      default:
        return ' ';
    }
  }

  // 检测段落类型
  private detectSegmentType(line: string): MessageSegment['type'] {
    // 任务分析标记
    if (line.includes('📋') && (line.includes('任务分析完成') || line.includes('TaskType.') || line.includes('任务分析'))) {
      return 'analysis_result';
    }
    
    // 节点状态标记 - 增强模式识别
    if ((line.includes('节点') && (line.includes('数据:') || line.includes('开始') || line.includes('完成'))) ||
        line.includes('messages 数据') || line.includes('values 数据') || line.includes('updates 数据') || line.includes('custom 数据')) {
      return 'node_status';
    }
    
    // 工具执行标记
    if (line.includes('🔧') || line.includes('工具') || line.includes('执行') || line.includes('tool_') ||
        line.includes('正在调用工具') || line.includes('工具调用完成')) {
      return 'tool_execution';
    }
    
    // 文件生成标记 - 增强模式识别
    if (line.includes('📁') || line.includes('📄') || line.includes('文件') || line.includes('已生成') || line.includes('已保存') ||
        line.includes('图片已保存') || line.includes('file_id') || line.includes('.png') || line.includes('.jpg') ||
        line.includes('.pdf') || line.includes('.xlsx') || line.includes('.csv')) {
      return 'file_generated';
    }
    
    // Agent思考标记 - 增强模式识别，按优先级匹配
    if (line.includes('🤔') || line.includes('🔍') || line.includes('📝') || line.includes('💭') || line.includes('💬')) {
      return 'agent_thinking';
    }
    
    // 进一步的Agent思考模式
    if (line.includes('main_agent 正在') || line.includes('agent_thinking') || line.includes('正在分析') ||
        line.includes('正在处理') || line.includes('思考') || line.includes('分析您的请求') ||
        line.includes('理解了您的需求') || line.includes('为您准备') || line.includes('[调试]') ||
        line.includes('正在整理分析结果')) {
      return 'agent_thinking';
    }
    
    // 系统消息标记 - 增强模式识别
    if (line.includes('✅') && (line.includes('审查') || line.includes('通过') || line.includes('评分'))) {
      return 'system_message';
    }
    
    if (line.includes('⚠️') || line.includes('❌') || line.includes('审查失败') || 
        line.includes('质量检查') || line.includes('安全检查')) {
      return 'system_message';
    }
    
    // JSON代码块检测（特殊处理）
    if (line.includes('```json') || (line.includes('{') && line.includes('"') && line.includes(':'))) {
      return 'node_status'; // 将JSON归类为节点状态，因为通常是系统输出
    }
    
    return 'text';
  }

  // 提取段落的结构化数据
  private extractSegmentData(type: MessageSegment['type'], content: string): any {
    const data: any = {};
    
    switch (type) {
      case 'analysis_result':
        // 提取任务类型和复杂度
        const taskMatch = content.match(/TaskType\.(\w+)\s*\(复杂度:\s*(\w+)\)/);
        if (taskMatch) {
          data.task_type = taskMatch[1];
          data.complexity = taskMatch[2];
        }
        break;
        
      case 'node_status':
        // 提取节点信息和AI回复内容
        const nodeMatch = content.match(/节点\s+(\w+)\s+数据/);
        if (nodeMatch) {
          data.node_name = nodeMatch[1];
        }
        
        // 从节点数据中提取AI回复内容
        const aiContentMatch = content.match(/AIMessage\(content='([^']*)'|AIMessageChunk\(content='([^']*)'/);
        if (aiContentMatch) {
          data.ai_content = aiContentMatch[1] || aiContentMatch[2];
        }
        
        // 提取LangGraph特定的数据类型
        if (content.includes('messages 数据')) {
          data.data_type = 'messages';
        } else if (content.includes('values 数据')) {
          data.data_type = 'values';
        } else if (content.includes('updates 数据')) {
          data.data_type = 'updates';
        } else if (content.includes('custom 数据')) {
          data.data_type = 'custom';
        }
        
        data.status = content.includes('完成') ? 'completed' : 'running';
        break;
        
      case 'tool_execution':
        // 提取工具信息
        const toolMatch = content.match(/(\w+)\s+(正在|已|执行|工具)/);
        if (toolMatch) {
          data.tool_name = toolMatch[1];
        }
        data.status = content.includes('完成') || content.includes('已') ? 'completed' : 'running';
        break;
        
      case 'file_generated':
        // 提取文件信息
        const fileMatch = content.match(/([^/\s]+\.(png|jpg|jpeg|gif|pdf|xlsx|csv|json))/i);
        if (fileMatch) {
          data.file_name = fileMatch[1];
          data.file_type = fileMatch[2];
        }
        
        // 提取文件ID
        const fileIdMatch = content.match(/file_id['":\s]*([a-zA-Z0-9\-_]+)/);
        if (fileIdMatch) {
          data.file_id = fileIdMatch[1];
        }
        break;
        
      case 'agent_thinking':
        // 提取agent信息
        const agentMatch = content.match(/(\w+_agent|\w+Agent)\s+(正在|思考)/);
        if (agentMatch) {
          data.agent_name = agentMatch[1];
        }
        
        // 提取思考内容
        const thinkingMatch = content.match(/🤔\s*(.+)/);
        if (thinkingMatch) {
          data.thinking_content = thinkingMatch[1];
        }
        break;
        
      case 'system_message':
        // 提取审查信息
        const scoreMatch = content.match(/评分:\s*([\d.]+)/);
        if (scoreMatch) {
          data.score = parseFloat(scoreMatch[1]);
        }
        data.passed = content.includes('✅') || content.includes('通过');
        
        // 提取审查类型
        if (content.includes('质量检查')) {
          data.review_type = 'quality';
        } else if (content.includes('安全检查')) {
          data.review_type = 'security';
        } else if (content.includes('审查')) {
          data.review_type = 'general';
        }
        break;
    }
    
    return data;
  }
}

// 段落显示组件
function MessageSegmentDisplay({ segment }: { segment: MessageSegment }) {
  switch (segment.type) {
    case 'analysis_result':
      return (
        <Card className="mb-2 bg-blue-50 border-blue-200">
          <CardContent className="p-3">
            <div className="flex items-center space-x-2">
              <BarChart3 className="h-4 w-4 text-blue-600" />
              <div className="flex-1">
                <div className="flex items-center space-x-2">
                  <span className="font-medium text-sm">任务分析</span>
                  {segment.data?.task_type && (
                    <Badge variant="outline" className="text-xs">
                      {segment.data.task_type}
                    </Badge>
                  )}
                  {segment.data?.complexity && (
                    <Badge variant="secondary" className="text-xs">
                      复杂度: {segment.data.complexity}
                    </Badge>
                  )}
                </div>
                <p className="text-xs text-gray-700 mt-1">{segment.content}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      );
      
    case 'node_status':
      const isStarting = segment.data?.action === 'start';
      const isCompleted = segment.data?.action === 'complete';
      const isError = segment.data?.action === 'error';
      
      return (
        <Card className={`mb-2 ${
          isError ? 'bg-red-50 border-red-200' : 
          isCompleted ? 'bg-green-50 border-green-200' : 
          'bg-blue-50 border-blue-200'
        }`}>
          <CardContent className="p-3">
            <div className="flex items-center space-x-2">
              {isError ? (
                <AlertCircle className="h-4 w-4 text-red-600" />
              ) : isCompleted ? (
                <CheckCircle className="h-4 w-4 text-green-600" />
              ) : (
                <Clock className="h-4 w-4 text-blue-600" />
              )}
              <div className="flex-1">
                <div className="flex items-center space-x-2">
                  <span className="font-medium text-sm">
                    {segment.data?.node_name || '节点状态'}
                  </span>
                  <Badge variant={isCompleted ? 'default' : isError ? 'destructive' : 'secondary'} className="text-xs">
                    {isError ? '错误' : isCompleted ? '已完成' : '执行中'}
                  </Badge>
                </div>
                
                {/* 显示节点详情 */}
                {segment.data?.details && (
                  <p className="text-sm text-gray-700 mt-1">{segment.data.details}</p>
                )}
                
                {/* 如果没有详情，显示原始内容 */}
                {!segment.data?.details && (
                  <p className="text-xs text-gray-600 mt-1">{segment.content}</p>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      );
      
    case 'agent_thinking':
      return (
        <Card className="mb-2 bg-purple-50 border-purple-200">
          <CardContent className="p-3">
            <div className="flex items-center space-x-2">
              <Brain className="h-4 w-4 text-purple-600" />
              <div className="flex-1">
                <div className="flex items-center space-x-2">
                  <span className="font-medium text-sm">
                    {segment.data?.agent_name || 'Agent'} 思考中
                  </span>
                  {segment.data?.thinking_type && (
                    <Badge variant="outline" className="text-xs">
                      {segment.data.thinking_type}
                    </Badge>
                  )}
                </div>
                
                {/* 显示纯净的思考内容 */}
                <p className="text-sm text-gray-700 mt-1">
                  {segment.data?.thinking_content || segment.content}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      );
      
    case 'tool_execution':
      const toolCompleted = segment.data?.action === 'complete';
      const toolError = segment.data?.action === 'error';
      const toolProgress = segment.data?.action === 'progress';
      
      return (
        <Card className={`mb-2 ${
          toolError ? 'bg-red-50 border-red-200' : 
          toolCompleted ? 'bg-green-50 border-green-200' : 
          'bg-orange-50 border-orange-200'
        }`}>
          <CardContent className="p-3">
            <div className="flex items-center space-x-2">
              <Settings className="h-4 w-4 text-orange-600" />
              <div className="flex-1">
                <div className="flex items-center space-x-2">
                  <span className="font-medium text-sm">
                    {segment.data?.tool_name || '工具执行'}
                  </span>
                  <Badge variant={toolCompleted ? 'default' : toolError ? 'destructive' : 'secondary'} className="text-xs">
                    {toolError ? '错误' : toolCompleted ? '已完成' : toolProgress ? '进行中' : '执行中'}
                  </Badge>
                  {segment.data?.progress && (
                    <Badge variant="outline" className="text-xs">
                      {Math.round(segment.data.progress * 100)}%
                    </Badge>
                  )}
                </div>
                
                {/* 显示工具详情或输出 */}
                {segment.data?.details && (
                  <p className="text-sm text-gray-700 mt-1">{segment.data.details}</p>
                )}
                {segment.data?.output && (
                  <p className="text-sm text-gray-700 mt-1">{segment.data.output}</p>
                )}
                {segment.data?.error_message && (
                  <p className="text-sm text-red-600 mt-1">{segment.data.error_message}</p>
                )}
                
                {/* 如果没有详情，显示原始内容 */}
                {!segment.data?.details && !segment.data?.output && !segment.data?.error_message && (
                  <p className="text-xs text-gray-600 mt-1">{segment.content}</p>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      );
      
    case 'file_generated':
      return (
        <Card className="mb-2 bg-emerald-50 border-emerald-200">
          <CardContent className="p-3">
            <div className="flex items-center space-x-2">
              <FileText className="h-4 w-4 text-emerald-600" />
              <div className="flex-1">
                <div className="flex items-center space-x-2">
                  <span className="font-medium text-sm">文件生成</span>
                  {segment.data?.file_type && (
                    <Badge variant="outline" className="text-xs">
                      {segment.data.file_type.toUpperCase()}
                    </Badge>
                  )}
                  {segment.data?.category && (
                    <Badge variant="secondary" className="text-xs">
                      {segment.data.category}
                    </Badge>
                  )}
                </div>
                
                {/* 显示文件名和描述 */}
                {segment.data?.file_name && (
                  <p className="text-sm font-medium text-gray-800 mt-1">
                    {segment.data.file_name}
                  </p>
                )}
                {segment.data?.description && (
                  <p className="text-xs text-gray-600 mt-1">{segment.data.description}</p>
                )}
                
                {/* 如果有文件路径，显示下载链接 */}
                {segment.data?.file_path && (
                  <div className="mt-2">
                    <Badge variant="outline" className="text-xs cursor-pointer hover:bg-gray-100">
                      <Download className="h-3 w-3 mr-1" />
                      下载文件
                    </Badge>
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      );
      
    case 'system_message':
      const isPassed = segment.data?.status_type === 'review_passed';
      const isFailed = segment.data?.status_type === 'review_failed';
      const isTaskAnalysis = segment.data?.status_type === 'task_analysis';
      
      return (
        <Card className={`mb-2 ${
          isFailed ? 'bg-red-50 border-red-200' : 
          isPassed ? 'bg-green-50 border-green-200' : 
          isTaskAnalysis ? 'bg-blue-50 border-blue-200' :
          'bg-gray-50 border-gray-200'
        }`}>
          <CardContent className="p-3">
            <div className="flex items-center space-x-2">
              {isFailed ? (
                <AlertCircle className="h-4 w-4 text-red-600" />
              ) : isPassed ? (
                <CheckCircle className="h-4 w-4 text-green-600" />
              ) : isTaskAnalysis ? (
                <BarChart3 className="h-4 w-4 text-blue-600" />
              ) : (
                <AlertCircle className="h-4 w-4 text-gray-600" />
              )}
              <div className="flex-1">
                <div className="flex items-center space-x-2">
                  <span className="font-medium text-sm">
                    {isTaskAnalysis ? '任务分析' : 
                     isPassed ? '审查通过' : 
                     isFailed ? '审查失败' : '系统消息'}
                  </span>
                  {segment.data?.source && (
                    <Badge variant="outline" className="text-xs">
                      {segment.data.source}
                    </Badge>
                  )}
                </div>
                <p className="text-sm text-gray-700 mt-1">{segment.content}</p>
                
                {/* 显示路由决策信息 */}
                {segment.data?.decision_type === 'route' && (
                  <div className="mt-2 text-xs text-gray-600">
                    <span>路由: {segment.data.from_node} → {segment.data.to_node}</span>
                    {segment.data.reason && (
                      <span className="ml-2">({segment.data.reason})</span>
                    )}
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      );
      
    case 'text':
    default:
      return (
        <div className="mb-2">
          <p className="text-sm text-gray-800 whitespace-pre-wrap">{segment.content}</p>
          {/* 显示LLM输出源信息 */}
          {segment.data?.is_llm_output && segment.data?.source && (
            <div className="mt-1">
              <Badge variant="outline" className="text-xs">
                来源: {segment.data.source}
                {segment.data.llm_model && ` (${segment.data.llm_model})`}
              </Badge>
            </div>
          )}
        </div>
      );
  }
}

// 智能消息显示组件
export function IntelligentMessageDisplay({ 
  role, 
  content, 
  timestamp 
}: { 
  role: 'user' | 'assistant' | 'system' | 'data';
  content: string;
  timestamp?: Date;
}) {
  const parser = new IntelligentMessageParser();
  
  if (role === 'user') {
    // 用户消息保持简单显示
    return (
      <div className="flex justify-end mb-4">
        <div className="max-w-[80%] rounded-lg px-4 py-2 bg-blue-600 text-white">
          <div className="flex items-start space-x-2">
            <User className="h-4 w-4 mt-1 flex-shrink-0" />
            <div className="flex-1">
              <div className="text-sm whitespace-pre-wrap">{content}</div>
              <div className="text-xs opacity-70 mt-1">
                {timestamp?.toLocaleTimeString() || new Date().toLocaleTimeString()}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }
  
  if (role === 'system') {
    // 系统消息显示
    return (
      <div className="flex justify-center mb-4">
        <div className="max-w-[70%] rounded-lg px-3 py-2 bg-yellow-50 border border-yellow-200">
          <div className="flex items-center space-x-2">
            <AlertCircle className="h-4 w-4 text-yellow-600" />
            <div className="text-xs text-yellow-800">{content}</div>
          </div>
        </div>
      </div>
    );
  }
  
  if (role === 'data') {
    // 数据消息通常不显示或作为系统消息处理
    return null;
  }
  
  // AI助手消息进行智能解析
  const segments = parser.parseMessage(content);
  
  // 调试信息
  if (process.env.NODE_ENV === 'development') {
    console.log('🔍 IntelligentMessageDisplay 解析结果:', {
      originalContent: content.substring(0, 200) + (content.length > 200 ? '...' : ''),
      segmentCount: segments.length,
      segmentTypes: segments.map(s => s.type),
      segments: segments.map(s => ({
        type: s.type,
        content: s.content.substring(0, 50) + (s.content.length > 50 ? '...' : '')
      }))
    });
  }
  
  return (
    <div className="flex justify-start mb-4">
      <div className="max-w-[85%] w-full">
        <div className="flex items-start space-x-2 mb-2">
          <Bot className="h-4 w-4 mt-1 flex-shrink-0 text-gray-600" />
          <div className="text-xs text-gray-500 flex items-center space-x-2">
            <span>AI助手 • {timestamp?.toLocaleTimeString() || new Date().toLocaleTimeString()}</span>
            {process.env.NODE_ENV === 'development' && (
              <span className="bg-yellow-100 px-1 rounded">
                🔧 {segments.length} 段落
              </span>
            )}
          </div>
        </div>
        
        <div className="space-y-1">
          {segments.length > 0 ? (
            segments.map((segment, index) => (
              <MessageSegmentDisplay key={index} segment={segment} />
            ))
          ) : (
            // 如果没有解析出段落，显示原始内容
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
              <p className="text-sm text-gray-900 whitespace-pre-wrap">{content}</p>
              {process.env.NODE_ENV === 'development' && (
                <div className="mt-2 text-xs text-red-600">
                  ⚠️ 未解析出任何段落，显示原始内容
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default IntelligentMessageDisplay; 