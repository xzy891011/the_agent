"use client";

import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Activity, Server, Database, Clock } from 'lucide-react';

interface SystemStatusProps {
  apiBaseUrl?: string;
  className?: string;
}

interface SystemStatusData {
  status: string;
  uptime: number;
  memory_usage: number;
  cpu_usage: number;
  active_sessions: number;
  total_requests: number;
  error_count: number;
  last_updated: string;
}

export default function SystemStatus({ apiBaseUrl = 'http://localhost:7102', className = "" }: SystemStatusProps) {
  const [systemData, setSystemData] = useState<SystemStatusData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSystemStatus = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${apiBaseUrl}/api/v1/system/status`);
      const data = await response.json();
      
      if (data.success) {
        setSystemData(data.data);
        setError(null);
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

  useEffect(() => {
    fetchSystemStatus();
    const interval = setInterval(fetchSystemStatus, 30000); // 30秒更新一次
    return () => clearInterval(interval);
  }, [apiBaseUrl]);

  const formatUptime = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${minutes}m`;
  };

  const getStatusBadge = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'healthy':
      case 'running':
        return <Badge className="bg-green-100 text-green-800">正常</Badge>;
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
      <Card className={className}>
        <CardHeader>
          <CardTitle className="text-sm font-medium flex items-center">
            <Server className="w-4 h-4 mr-2" />
            系统状态
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle className="text-sm font-medium flex items-center">
            <Server className="w-4 h-4 mr-2" />
            系统状态
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-4">
            <p className="text-sm text-red-600">{error}</p>
            <button 
              onClick={fetchSystemStatus}
              className="text-xs text-blue-600 hover:underline mt-2"
            >
              重试
            </button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="text-sm font-medium flex items-center justify-between">
          <div className="flex items-center">
            <Server className="w-4 h-4 mr-2" />
            系统状态
          </div>
          {systemData && getStatusBadge(systemData.status)}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {systemData && (
          <>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <div className="flex items-center text-gray-500 mb-1">
                  <Activity className="w-3 h-3 mr-1" />
                  CPU使用率
                </div>
                <div className="font-medium">
                  {systemData.cpu_usage?.toFixed(1) || 'N/A'}%
                </div>
              </div>
              
              <div>
                <div className="flex items-center text-gray-500 mb-1">
                  <Database className="w-3 h-3 mr-1" />
                  内存使用率
                </div>
                <div className="font-medium">
                  {systemData.memory_usage?.toFixed(1) || 'N/A'}%
                </div>
              </div>
              
              <div>
                <div className="flex items-center text-gray-500 mb-1">
                  <Clock className="w-3 h-3 mr-1" />
                  运行时间
                </div>
                <div className="font-medium">
                  {systemData.uptime ? formatUptime(systemData.uptime) : 'N/A'}
                </div>
              </div>
              
              <div>
                <div className="text-gray-500 mb-1">活跃会话</div>
                <div className="font-medium">
                  {systemData.active_sessions || 0}
                </div>
              </div>
            </div>

            <div className="pt-3 border-t space-y-2 text-xs text-gray-500">
              <div className="flex justify-between">
                <span>总请求数</span>
                <span>{systemData.total_requests || 0}</span>
              </div>
              <div className="flex justify-between">
                <span>错误数</span>
                <span className={systemData.error_count > 0 ? 'text-red-600' : ''}>
                  {systemData.error_count || 0}
                </span>
              </div>
              <div className="flex justify-between">
                <span>最后更新</span>
                <span>
                  {systemData.last_updated 
                    ? new Date(systemData.last_updated).toLocaleTimeString()
                    : '刚刚'
                  }
                </span>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// 系统信息组件
export const SystemInfo: React.FC<{ className?: string }> = ({ className = "" }) => {
  const [info, setInfo] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchSystemInfo = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/v1/system/info');
        if (response.ok) {
          const data = await response.json();
          setInfo(data.data);
        }
      } catch (error) {
        console.error('获取系统信息失败:', error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchSystemInfo();
  }, []);

  if (isLoading || !info) {
    return (
      <div className={`p-4 border rounded-lg bg-white ${className}`}>
        <div className="text-sm text-gray-500">加载中...</div>
      </div>
    );
  }

  return (
    <div className={`p-4 border rounded-lg bg-white ${className}`}>
      <h3 className="font-medium text-gray-900 mb-3">系统信息</h3>
      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-gray-600">API版本</span>
          <span className="text-gray-900">{info.api_version}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-600">Python版本</span>
          <span className="text-gray-900">{info.python_version}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-600">主机名</span>
          <span className="text-gray-900">{info.hostname}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-600">当前时间</span>
          <span className="text-gray-900">
            {new Date(info.current_time).toLocaleString()}
          </span>
        </div>
      </div>
    </div>
  );
}; 