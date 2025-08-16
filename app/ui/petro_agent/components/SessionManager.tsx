"use client";

import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { ScrollArea } from './ui/scroll-area';
import { 
  List,
  Trash2,
  Clock,
  MessageSquare,
  RefreshCw,
  AlertCircle
} from 'lucide-react';

interface SessionInfo {
  session_id: string;
  status: 'active' | 'inactive' | 'interrupted' | 'error';
  created_at: string;
  last_updated: string;
  message_count: number;
  metadata?: Record<string, any>;
}

interface SessionManagerProps {
  currentSessionId?: string;
  apiBaseUrl?: string;
  className?: string;
  onSessionSelected?: (sessionId: string) => void;
  onSessionCreated?: (session: SessionInfo) => void;
  onSessionDeleted?: (sessionId: string) => void;
}

export default function SessionManager({
  currentSessionId,
  apiBaseUrl = 'http://localhost:7102',
  className,
  onSessionSelected,
  onSessionDeleted
}: SessionManagerProps) {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 获取会话列表
  const fetchSessions = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await fetch(`${apiBaseUrl}/api/v1/sessions/list`);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      
      if (data.success && Array.isArray(data.data?.sessions)) {
        // 按更新时间排序，最近的在前
        const sortedSessions = data.data.sessions.sort((a: SessionInfo, b: SessionInfo) => 
          new Date(b.last_updated).getTime() - new Date(a.last_updated).getTime()
        );
        setSessions(sortedSessions);
      } else {
        setSessions([]);
      }
    } catch (err) {
      console.error('获取会话列表失败:', err);
      setError('获取会话列表失败');
      setSessions([]);
    } finally {
      setLoading(false);
    }
  };

  // 删除会话
  const handleDeleteSession = async (sessionId: string) => {
    if (!confirm('确定要删除这个会话吗？')) return;
    
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/sessions/${sessionId}`, {
        method: 'DELETE',
      });
      
      if (response.ok) {
        // 从列表中移除
        setSessions(prev => prev.filter(session => session.session_id !== sessionId));
        // 通知父组件
        onSessionDeleted?.(sessionId);
      } else {
        throw new Error('删除会话失败');
      }
    } catch (err) {
      console.error('删除会话失败:', err);
      alert('删除会话失败');
    }
  };

  // 选择会话
  const handleSelectSession = (sessionId: string) => {
    onSessionSelected?.(sessionId);
  };

  // 格式化时间
  const formatTime = (timeStr: string) => {
    try {
      const date = new Date(timeStr);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      
      if (diffMs < 60000) { // 1分钟内
        return '刚刚';
      } else if (diffMs < 3600000) { // 1小时内
        return `${Math.floor(diffMs / 60000)}分钟前`;
      } else if (diffMs < 86400000) { // 1天内
        return `${Math.floor(diffMs / 3600000)}小时前`;
      } else {
        return date.toLocaleDateString();
      }
    } catch {
      return '未知时间';
    }
  };

  // 获取状态徽章
  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'active':
        return <Badge className="bg-green-100 text-green-800">活跃</Badge>;
      case 'inactive':
        return <Badge variant="secondary">非活跃</Badge>;
      case 'interrupted':
        return <Badge className="bg-yellow-100 text-yellow-800">中断</Badge>;
      case 'error':
        return <Badge className="bg-red-100 text-red-800">错误</Badge>;
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  // 初始加载和定期刷新
  useEffect(() => {
    fetchSessions();
    const interval = setInterval(fetchSessions, 30000); // 每30秒刷新一次
    return () => clearInterval(interval);
  }, [apiBaseUrl]);

  // 当前会话ID变化时，刷新列表
  useEffect(() => {
    if (currentSessionId) {
      fetchSessions();
    }
  }, [currentSessionId]);

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center text-sm">
            <List className="h-4 w-4 mr-2" />
            会话历史
          </CardTitle>
          <Button 
            variant="ghost" 
            size="sm" 
            onClick={fetchSessions}
            disabled={loading}
          >
            <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
        {sessions.length > 0 && (
          <p className="text-xs text-gray-500">
            共 {sessions.length} 个会话
          </p>
        )}
      </CardHeader>
      
      <CardContent className="p-0">
        {loading ? (
          <div className="p-4 text-center text-sm text-gray-500">
            <RefreshCw className="h-4 w-4 animate-spin mx-auto mb-2" />
            加载中...
          </div>
        ) : error ? (
          <div className="p-4 text-center text-sm text-red-600">
            <AlertCircle className="h-4 w-4 mx-auto mb-2" />
            {error}
          </div>
        ) : sessions.length === 0 ? (
          <div className="p-4 text-center text-sm text-gray-500">
            <MessageSquare className="h-8 w-8 mx-auto mb-2 text-gray-400" />
            暂无会话记录
          </div>
        ) : (
          <ScrollArea className="h-64">
            <div className="space-y-1 p-2">
              {sessions.map((session) => (
                <div
                  key={session.session_id}
                  className={`flex items-center justify-between p-2 rounded-lg cursor-pointer transition-colors ${
                    session.session_id === currentSessionId
                      ? 'bg-blue-50 border border-blue-200'
                      : 'hover:bg-gray-50'
                  }`}
                  onClick={() => handleSelectSession(session.session_id)}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center space-x-2 mb-1">
                      <div className="text-xs font-medium text-gray-900 truncate">
                        {session.session_id.slice(0, 8)}...
                      </div>
                      {getStatusBadge(session.status)}
                    </div>
                    
                    <div className="flex items-center space-x-2 text-xs text-gray-500">
                      <Clock className="h-3 w-3" />
                      <span>{formatTime(session.last_updated)}</span>
                      <MessageSquare className="h-3 w-3" />
                      <span>{session.message_count || 0} 条消息</span>
                    </div>
                  </div>
                  
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteSession(session.session_id);
                    }}
                    className="ml-2 h-6 w-6 p-0 text-gray-400 hover:text-red-500"
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              ))}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
} 