"use client";

import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Workflow, Calendar, Clock, CheckCircle, AlertCircle, Loader2, Play } from 'lucide-react';

interface WorkflowHistoryItem {
  session_id: string;
  created_at: string;
  last_updated?: string;
  messages_count?: number;
  status?: string;
  task_summary?: string;
}

interface WorkflowHistoryProps {
  apiBaseUrl?: string;
}

export default function WorkflowHistory({ apiBaseUrl = 'http://localhost:7102' }: WorkflowHistoryProps) {
  const [workflows, setWorkflows] = useState<WorkflowHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchWorkflowHistory = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await fetch(`${apiBaseUrl}/api/v1/sessions/list`);
      if (response.ok) {
        const data = await response.json();
        if (data.success && data.data?.sessions) {
          setWorkflows(data.data.sessions);
        }
      } else {
        setError('获取工作流历史失败');
      }
    } catch (err) {
      setError('网络连接失败');
      console.error('获取工作流历史失败:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWorkflowHistory();
  }, [apiBaseUrl]);

  const formatTimeAgo = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffInMs = now.getTime() - date.getTime();
    const diffInMinutes = Math.floor(diffInMs / (1000 * 60));
    const diffInHours = Math.floor(diffInMinutes / 60);
    const diffInDays = Math.floor(diffInHours / 24);

    if (diffInMinutes < 1) {
      return '刚刚';
    } else if (diffInMinutes < 60) {
      return `${diffInMinutes}分钟前`;
    } else if (diffInHours < 24) {
      return `${diffInHours}小时前`;
    } else {
      return `${diffInDays}天前`;
    }
  };

  const getStatusInfo = (workflow: WorkflowHistoryItem) => {
    const hasRecentActivity = workflow.last_updated && 
      (new Date().getTime() - new Date(workflow.last_updated).getTime()) < 30000; // 30秒内有活动

    if (hasRecentActivity) {
      return {
        status: 'running',
        label: '运行中',
        className: 'bg-blue-100 text-blue-800',
        icon: <Loader2 className="h-3 w-3 animate-spin" />
      };
    } else if (workflow.messages_count && workflow.messages_count > 1) {
      return {
        status: 'completed',
        label: '已完成',
        className: 'bg-green-100 text-green-800',
        icon: <CheckCircle className="h-3 w-3" />
      };
    } else {
      return {
        status: 'pending',
        label: '待继续',
        className: 'bg-gray-100 text-gray-800',
        icon: <Play className="h-3 w-3" />
      };
    }
  };

  const generateTaskSummary = (workflow: WorkflowHistoryItem) => {
    if (workflow.task_summary) {
      return workflow.task_summary;
    }
    
    // 根据消息数量推断任务类型
    if (workflow.messages_count === 0 || !workflow.messages_count) {
      return '新建会话';
    } else if (workflow.messages_count < 5) {
      return '初步咨询';
    } else if (workflow.messages_count < 10) {
      return '数据分析任务';
    } else {
      return '复杂建模工作流';
    }
  };

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center">
            <Workflow className="h-5 w-5 mr-2" />
            工作流历史
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin mr-2" />
            <span className="text-gray-600">加载中...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center">
            <Workflow className="h-5 w-5 mr-2" />
            工作流历史
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8">
            <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">加载失败</h3>
            <p className="text-gray-600 mb-4">{error}</p>
            <Button onClick={fetchWorkflowHistory} size="sm">
              重试
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <div className="flex items-center">
            <Workflow className="h-5 w-5 mr-2" />
            工作流历史
          </div>
          <Button onClick={fetchWorkflowHistory} size="sm" variant="outline">
            刷新
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {workflows.length === 0 ? (
          <div className="text-center py-8">
            <Workflow className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">暂无工作流历史</h3>
            <p className="text-gray-600">开始一个新对话来创建您的第一个工作流</p>
          </div>
        ) : (
          <div className="space-y-3 max-h-80 overflow-y-auto">
            {workflows.map((workflow) => {
              const statusInfo = getStatusInfo(workflow);
              return (
                <div key={workflow.session_id} className="flex items-center justify-between p-3 border rounded hover:bg-gray-50">
                  <div className="flex-1">
                    <div className="flex items-center space-x-2 mb-1">
                      <div className="font-medium text-sm">
                        {generateTaskSummary(workflow)}
                      </div>
                      <Badge className={statusInfo.className}>
                        <div className="flex items-center space-x-1">
                          {statusInfo.icon}
                          <span>{statusInfo.label}</span>
                        </div>
                      </Badge>
                    </div>
                    <div className="flex items-center space-x-4 text-xs text-gray-500">
                      <div className="flex items-center space-x-1">
                        <Calendar className="h-3 w-3" />
                        <span>{formatTimeAgo(workflow.created_at)}</span>
                      </div>
                      <div className="flex items-center space-x-1">
                        <Clock className="h-3 w-3" />
                        <span>会话ID: {workflow.session_id.slice(0, 8)}...</span>
                      </div>
                      {workflow.messages_count !== undefined && (
                        <div className="flex items-center space-x-1">
                          <span>{workflow.messages_count} 条消息</span>
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Button 
                      size="sm" 
                      variant="ghost"
                      onClick={() => {
                        // 这里可以添加查看详情的逻辑
                        console.log('查看工作流详情:', workflow.session_id);
                      }}
                    >
                      查看
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
} 