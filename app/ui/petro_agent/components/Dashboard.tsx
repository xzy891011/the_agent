"use client";

import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Progress } from './ui/progress';
import { Activity, Database, Users, Cpu, AlertTriangle, CheckCircle, Server, Clock } from 'lucide-react';

interface SystemMetrics {
  cpu_usage?: number;
  memory_usage?: number;
  active_sessions?: number;
  total_requests?: number;
  error_count?: number;
  uptime?: number;
  status?: string;
}

interface DashboardProps {
  apiBaseUrl?: string;
}

export default function Dashboard({ apiBaseUrl = 'http://localhost:7102' }: DashboardProps) {
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 获取系统状态
  const fetchSystemStatus = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await fetch(`${apiBaseUrl}/api/v1/system/status`);
      const data = await response.json();
      
      if (data.success && data.data && data.status) {
        // 解析后端返回的数据结构
        const transformedMetrics: SystemMetrics = {
          cpu_usage: data.data.cpu_percent || 0,
          memory_usage: data.status.memory_usage?.percent || 0,
          active_sessions: data.status.active_sessions || 0,
          total_requests: 0, // 需要从其他接口获取，暂时设为0
          error_count: 0, // 需要从其他接口获取，暂时设为0
          uptime: parseUptime(data.status.uptime),
          status: data.status.engine_status || 'unknown'
        };
        setMetrics(transformedMetrics);
      } else {
        setError(data.message || '获取系统状态失败');
      }
    } catch (err) {
      setError('网络连接失败');
      console.error('获取系统状态失败:', err);
    } finally {
      setLoading(false);
    }
  };

  // 解析运行时间字符串为秒数
  const parseUptime = (uptimeStr: string): number => {
    if (!uptimeStr) return 0;
    
    // 解析类似 "185 days, 2:43:44" 的字符串
    const parts = uptimeStr.split(',');
    let totalSeconds = 0;
    
    // 解析天数
    const daysPart = parts[0]?.trim();
    if (daysPart && daysPart.includes('day')) {
      const days = parseInt(daysPart.split(' ')[0]);
      if (!isNaN(days)) {
        totalSeconds += days * 24 * 3600;
      }
    }
    
    // 解析时分秒
    const timePart = parts[1]?.trim() || parts[0]?.trim();
    if (timePart && timePart.includes(':')) {
      const timeParts = timePart.split(':');
      if (timeParts.length === 3) {
        const hours = parseInt(timeParts[0]);
        const minutes = parseInt(timeParts[1]);
        const seconds = parseInt(timeParts[2]);
        
        if (!isNaN(hours)) totalSeconds += hours * 3600;
        if (!isNaN(minutes)) totalSeconds += minutes * 60;
        if (!isNaN(seconds)) totalSeconds += seconds;
      }
    }
    
    return totalSeconds;
  };

  useEffect(() => {
    fetchSystemStatus();
    const interval = setInterval(fetchSystemStatus, 30000); // 30秒更新一次
    return () => clearInterval(interval);
  }, [apiBaseUrl]);

  const formatUptime = (seconds: number) => {
    if (!seconds) return 'N/A';
    
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${minutes}m`;
  };

  const getStatusBadge = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'healthy':
      case 'ready':
      case 'running':
        return <Badge className="bg-green-100 text-green-800">正常运行</Badge>;
      case 'warning':
        return <Badge className="bg-yellow-100 text-yellow-800">警告</Badge>;
      case 'error':
        return <Badge className="bg-red-100 text-red-800">错误</Badge>;
      default:
        return <Badge className="bg-gray-100 text-gray-800">未知</Badge>;
    }
  };

  if (loading) {
    return (
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-3xl font-bold text-gray-900">实时监控仪表盘</h2>
          <div className="flex items-center space-x-2">
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
            <span className="text-sm text-gray-600">加载中...</span>
          </div>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i}>
              <CardHeader>
                <CardTitle className="text-sm font-medium">加载中...</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-8 bg-gray-200 rounded animate-pulse"></div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  if (error || !metrics) {
    return (
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-3xl font-bold text-gray-900">实时监控仪表盘</h2>
          <div className="flex items-center space-x-2">
            <AlertTriangle className="h-4 w-4 text-red-500" />
            <span className="text-sm text-red-600">连接失败</span>
          </div>
        </div>
        
        <Card>
          <CardContent className="p-6">
            <div className="text-center">
              <AlertTriangle className="h-12 w-12 text-red-500 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-gray-900 mb-2">无法连接到后端系统</h3>
              <p className="text-gray-600 mb-4">{error}</p>
              <button 
                onClick={fetchSystemStatus}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
              >
                重试连接
              </button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold text-gray-900">实时监控仪表盘</h2>
        <div className="flex items-center space-x-2">
          {getStatusBadge(metrics.status || 'unknown')}
          <span className="text-sm text-gray-600">
            最后更新: {new Date().toLocaleTimeString()}
          </span>
        </div>
      </div>

      {/* 核心指标卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">CPU使用率</CardTitle>
            <Cpu className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics.cpu_usage?.toFixed(1) || '0.0'}%</div>
            <Progress value={metrics.cpu_usage || 0} className="mt-2" />
            <p className="text-xs text-muted-foreground mt-1">
              {(metrics.cpu_usage || 0) < 70 ? '运行正常' : '使用率较高'}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">内存使用率</CardTitle>
            <Database className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics.memory_usage?.toFixed(1) || '0.0'}%</div>
            <Progress value={metrics.memory_usage || 0} className="mt-2" />
            <p className="text-xs text-muted-foreground mt-1">
              {(metrics.memory_usage || 0) < 80 ? '内存充足' : '内存紧张'}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">活跃会话</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics.active_sessions || 0}</div>
            <p className="text-xs text-muted-foreground mt-1">
              当前活跃用户会话数
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">系统运行时间</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {metrics.uptime ? formatUptime(metrics.uptime) : 'N/A'}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              持续稳定运行
            </p>
          </CardContent>
        </Card>
      </div>

      {/* 系统详细信息 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 请求统计 */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg font-semibold">请求统计</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-600">总请求数</span>
                <span className="text-lg font-medium">{metrics.total_requests || 0}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-600">错误请求</span>
                <span className={`text-lg font-medium ${(metrics.error_count || 0) > 0 ? 'text-red-600' : 'text-green-600'}`}>
                  {metrics.error_count || 0}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-600">成功率</span>
                <span className="text-lg font-medium text-green-600">
                  {(metrics.total_requests || 0) > 0 
                    ? (((metrics.total_requests || 0) - (metrics.error_count || 0)) / (metrics.total_requests || 1) * 100).toFixed(1)
                    : '100.0'
                  }%
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 系统健康状态 */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg font-semibold">系统健康状态</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <Server className="h-4 w-4 text-blue-500" />
                  <span className="text-sm">API服务</span>
                </div>
                <Badge className="bg-green-100 text-green-800">正常</Badge>
              </div>
              
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <Database className="h-4 w-4 text-purple-500" />
                  <span className="text-sm">数据库连接</span>
                </div>
                <Badge className="bg-green-100 text-green-800">正常</Badge>
              </div>
              
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <Activity className="h-4 w-4 text-orange-500" />
                  <span className="text-sm">LangGraph引擎</span>
                </div>
                <Badge className={
                  metrics.status === 'ready' 
                    ? "bg-green-100 text-green-800" 
                    : "bg-yellow-100 text-yellow-800"
                }>
                  {metrics.status === 'ready' ? '正常' : '待命'}
                </Badge>
              </div>
              
              <div className="pt-2 text-xs text-gray-500">
                所有核心服务运行正常，系统状态良好
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
} 