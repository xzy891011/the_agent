"use client";

import React, { useState, useEffect, useRef, useCallback } from 'react';

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  type?: string;
  metadata?: any;
}

interface WebSocketChatProps {
  sessionId: string;
  className?: string;
  onStatusChange?: (status: string) => void;
}

export const WebSocketChat: React.FC<WebSocketChatProps> = ({
  sessionId,
  className = "",
  onStatusChange
}) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isConnected, setIsConnected] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState("disconnected");
  
  const websocketRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 5;
  
  // 自动滚动到底部
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };
  
  useEffect(() => {
    scrollToBottom();
  }, [messages]);
  
  // 连接WebSocket
  const connectWebSocket = useCallback(() => {
    if (websocketRef.current?.readyState === WebSocket.OPEN) {
      return;
    }
    
    const wsUrl = `ws://localhost:8000/ws/${sessionId}`;
    console.log(`连接WebSocket: ${wsUrl}`);
    
    try {
      const ws = new WebSocket(wsUrl);
      websocketRef.current = ws;
      
      ws.onopen = () => {
        console.log("WebSocket连接已建立");
        setIsConnected(true);
        setConnectionStatus("connected");
        reconnectAttempts.current = 0;
        onStatusChange?.("connected");
        
        // 清除重连定时器
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
          reconnectTimeoutRef.current = null;
        }
      };
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          handleWebSocketMessage(data);
        } catch (error) {
          console.error("解析WebSocket消息失败:", error);
        }
      };
      
      ws.onclose = (event) => {
        console.log("WebSocket连接已关闭", event.code, event.reason);
        setIsConnected(false);
        setConnectionStatus("disconnected");
        onStatusChange?.("disconnected");
        
        // 尝试重连
        if (reconnectAttempts.current < maxReconnectAttempts) {
          reconnectAttempts.current++;
          const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
          console.log(`${delay}ms后尝试第${reconnectAttempts.current}次重连`);
          
          setConnectionStatus("reconnecting");
          onStatusChange?.("reconnecting");
          
          reconnectTimeoutRef.current = setTimeout(() => {
            connectWebSocket();
          }, delay);
        } else {
          console.error("达到最大重连次数，停止重连");
          setConnectionStatus("failed");
          onStatusChange?.("failed");
        }
      };
      
      ws.onerror = (error) => {
        console.error("WebSocket错误:", error);
        setConnectionStatus("error");
        onStatusChange?.("error");
      };
      
    } catch (error) {
      console.error("创建WebSocket连接失败:", error);
      setConnectionStatus("error");
      onStatusChange?.("error");
    }
  }, [sessionId, onStatusChange]);
  
  // 处理WebSocket消息
  const handleWebSocketMessage = (data: any) => {
    const messageType = data.type;
    
    switch (messageType) {
      case "connect":
        console.log("收到连接确认消息");
        break;
        
      case "stream_start":
        console.log("开始接收流式数据");
        setIsStreaming(true);
        break;
        
      case "stream_data":
        const messageData = data.data;
        if (messageData.content) {
          const newMessage: Message = {
            id: `msg-${Date.now()}-${Math.random()}`,
            role: messageData.role || 'assistant',
            content: messageData.content,
            timestamp: new Date().toISOString(),
            type: messageData.type,
            metadata: messageData
          };
          
          setMessages(prev => {
            // 检查是否需要更新最后一条消息（流式更新）
            const lastMessage = prev[prev.length - 1];
            if (lastMessage && lastMessage.role === 'assistant' && isStreaming) {
              // 如果是同一个流式响应，追加内容
              const updatedMessage = {
                ...lastMessage,
                content: lastMessage.content + messageData.content,
                metadata: { ...lastMessage.metadata, ...messageData }
              };
              return [...prev.slice(0, -1), updatedMessage];
            } else {
              // 新消息
              return [...prev, newMessage];
            }
          });
        }
        break;
        
      case "stream_end":
        console.log("流式数据接收完成");
        setIsStreaming(false);
        break;
        
      case "error":
        console.error("WebSocket错误消息:", data.data);
        const errorMessage: Message = {
          id: `error-${Date.now()}`,
          role: 'system',
          content: `错误: ${data.data.error}`,
          timestamp: new Date().toISOString(),
          type: 'error'
        };
        setMessages(prev => [...prev, errorMessage]);
        break;
        
      default:
        console.log("未知消息类型:", messageType, data);
    }
  };
  
  // 发送消息
  const sendMessage = () => {
    if (!inputValue.trim() || !isConnected || !websocketRef.current) {
      return;
    }
    
    // 添加用户消息到UI
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: inputValue,
      timestamp: new Date().toISOString()
    };
    setMessages(prev => [...prev, userMessage]);
    
    // 发送到WebSocket
    const message = {
      type: "chat",
      data: {
        message: inputValue
      }
    };
    
    try {
      websocketRef.current.send(JSON.stringify(message));
      console.log("消息已发送:", inputValue);
      setInputValue("");
    } catch (error) {
      console.error("发送消息失败:", error);
    }
  };
  
  // 组件挂载时连接WebSocket
  useEffect(() => {
    connectWebSocket();
    
    // 组件卸载时清理
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (websocketRef.current) {
        websocketRef.current.close();
      }
    };
  }, [connectWebSocket]);
  
  // 处理输入框回车事件
  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };
  
  // 获取连接状态显示
  const getStatusDisplay = () => {
    switch (connectionStatus) {
      case "connected":
        return { text: "已连接", color: "text-green-600", icon: "●" };
      case "connecting":
      case "reconnecting":
        return { text: "连接中...", color: "text-yellow-600", icon: "◐" };
      case "disconnected":
        return { text: "已断开", color: "text-gray-600", icon: "○" };
      case "error":
      case "failed":
        return { text: "连接失败", color: "text-red-600", icon: "●" };
      default:
        return { text: "未知状态", color: "text-gray-600", icon: "○" };
    }
  };
  
  const statusDisplay = getStatusDisplay();
  
  return (
    <div className={`flex flex-col h-full bg-white border rounded-lg ${className}`}>
      {/* 头部 - 连接状态 */}
      <div className="flex items-center justify-between p-3 border-b bg-gray-50">
        <h3 className="font-medium text-gray-900">智能对话</h3>
        <div className="flex items-center space-x-2">
          <span className={`text-sm ${statusDisplay.color}`}>
            {statusDisplay.icon} {statusDisplay.text}
          </span>
          {isStreaming && (
            <span className="text-xs text-blue-600 animate-pulse">正在输入...</span>
          )}
        </div>
      </div>
      
      {/* 消息列表 */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 ? (
          <div className="text-center text-gray-500 mt-8">
            <p>开始对话吧！</p>
          </div>
        ) : (
          messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg ${
                  message.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : message.role === 'system'
                    ? 'bg-yellow-100 text-yellow-800 border border-yellow-300'
                    : 'bg-gray-100 text-gray-900'
                }`}
              >
                <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                <p className="text-xs mt-1 opacity-70">
                  {new Date(message.timestamp).toLocaleTimeString()}
                </p>
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>
      
      {/* 输入区域 */}
      <div className="border-t p-3">
        <div className="flex space-x-2">
          <textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder={isConnected ? "输入消息..." : "等待连接..."}
            disabled={!isConnected}
            className="flex-1 resize-none border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:text-gray-500"
            rows={2}
          />
          <button
            onClick={sendMessage}
            disabled={!isConnected || !inputValue.trim() || isStreaming}
            className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:bg-gray-400 disabled:cursor-not-allowed"
          >
            发送
          </button>
        </div>
        
        {/* 快捷功能按钮 */}
        <div className="flex space-x-2 mt-2">
          <button
            onClick={() => setInputValue("请介绍一下天然气碳同位素分析的基本原理")}
            disabled={!isConnected}
            className="text-xs text-blue-600 hover:text-blue-800 disabled:text-gray-400"
          >
            示例问题1
          </button>
          <button
            onClick={() => setInputValue("帮我分析上传的数据文件")}
            disabled={!isConnected}
            className="text-xs text-blue-600 hover:text-blue-800 disabled:text-gray-400"
          >
            示例问题2
          </button>
        </div>
      </div>
    </div>
  );
}; 