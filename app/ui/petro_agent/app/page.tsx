"use client";

import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from '@/components/ui/dropdown-menu';
import { toast } from 'sonner';
import { Toaster } from '@/components/ui/sonner';
import { 
  LayoutGrid, 
  WorkflowIcon, 
  Database, 
  Brain, 
  BarChart3, 
  Settings,
  Menu,
  X,
  Home,
  Activity,
  Users,
  MessageSquare,
  Plus,
  ChevronDown,
  Clock,
  RefreshCw,
  Trash2,
  MoreVertical
} from 'lucide-react';

// 导入我们的自定义组件
import Dashboard from '@/components/Dashboard';
import GeologicalModelingHub from '@/components/GeologicalModelingHub';
import DAGVisualization from '@/components/DAGVisualization';
import FileManager from '@/components/FileManager';
import SessionManager from '@/components/SessionManager';
import SystemStatus from '@/components/SystemStatus';
import WorkflowHistory from '@/components/WorkflowHistory';
import DataManager from '@/components/DataManager';

// 简单的logger对象，用于前端日志记录
const logger = {
  info: (message: string, data?: any) => {
    console.log(`[INFO] ${message}`, data || '');
  },
  error: (message: string, error?: any) => {
    console.error(`[ERROR] ${message}`, error || '');
  },
  warn: (message: string, data?: any) => {
    console.warn(`[WARN] ${message}`, data || '');
  },
  debug: (message: string, data?: any) => {
    console.debug(`[DEBUG] ${message}`, data || '');
  }
};

interface SessionInfo {
  session_id: string;
  status: 'active' | 'inactive' | 'interrupted' | 'error';
  created_at: string;
  last_updated: string;
  message_count: number;
  metadata?: Record<string, any>;
}

interface ChatMessage {
  id: string | number;
  content: string;
  sender: 'user' | 'assistant';
  timestamp: string;
  type: string;
}

export default function PetroAgentUI() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [currentSessionId, setCurrentSessionId] = useState<string>('');
  const [currentSessionInfo, setCurrentSessionInfo] = useState<SessionInfo | null>(null);
  const [availableSessions, setAvailableSessions] = useState<SessionInfo[]>([]);
  const [showNewSessionDialog, setShowNewSessionDialog] = useState(false);
  const [showSettingsDialog, setShowSettingsDialog] = useState(false);
  const [newSessionName, setNewSessionName] = useState('');
  const [newSessionDescription, setNewSessionDescription] = useState('');
  const [sessionSelectOpen, setSessionSelectOpen] = useState(false);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [isCreatingSession, setIsCreatingSession] = useState(false);
  const [isSessionChanging, setIsSessionChanging] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [settings, setSettings] = useState({
    apiBaseUrl: 'http://localhost:7102',
    autoSave: true,
    theme: 'light',
    language: 'zh-CN',
    darkMode: false
  });
  
  // API基础URL配置
  const apiBaseUrl = settings.apiBaseUrl;

  // 获取所有会话列表
  const fetchSessions = async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/sessions/list`);
      if (response.ok) {
        const data = await response.json();
        if (data.success && Array.isArray(data.sessions)) {
          // 按更新时间排序，最近的在前
          const sortedSessions = data.sessions.sort((a: SessionInfo, b: SessionInfo) => 
            new Date(b.last_updated).getTime() - new Date(a.last_updated).getTime()
          );
          setAvailableSessions(sortedSessions);
          return sortedSessions;
        }
      }
      return [];
    } catch (error) {
      console.error('获取会话列表失败:', error);
      return [];
    }
  };

  // 获取或创建默认会话
  const getOrCreateDefaultSession = async () => {
    try {
      setSessionLoading(true);
      
      // 先尝试获取会话列表
      const sessions = await fetchSessions();
      
      if (sessions.length > 0) {
        // 查找名为"默认会话"的会话，如果没有就使用最新的会话
        const defaultSession = sessions.find((s: SessionInfo) => 
          s.metadata?.title === '默认会话' || s.metadata?.name === '默认会话'
        ) || sessions[0];
        
        setCurrentSessionId(defaultSession.session_id);
        setCurrentSessionInfo(defaultSession);
        logger.info('使用已存在的会话', { sessionId: defaultSession.session_id, sessionName: defaultSession.metadata?.name || defaultSession.metadata?.title });
        return defaultSession.session_id;
      } else {
        // 如果没有任何会话，创建默认会话
        return await createDefaultSession();
      }
    } catch (error) {
      console.error('获取或创建默认会话失败:', error);
      return null;
    } finally {
      setSessionLoading(false);
    }
  };

  // 创建默认会话
  const createDefaultSession = async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/sessions/create`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          metadata: {
            title: '默认会话',
            name: '默认会话',
            description: '系统默认地质分析会话'
          }
        }),
      });
      
      const data = await response.json();
      if (data.success && data.data.session_id) {
        const newSession: SessionInfo = {
          session_id: data.data.session_id,
          status: 'active',
          created_at: new Date().toISOString(),
          last_updated: new Date().toISOString(),
          message_count: 0,
          metadata: {
            title: '默认会话',
            name: '默认会话',
            description: '系统默认地质分析会话'
          }
        };
        
        setCurrentSessionId(newSession.session_id);
        setCurrentSessionInfo(newSession);
        setAvailableSessions([newSession]);
        
        logger.info('创建默认会话成功', { sessionId: newSession.session_id, sessionName: newSession.metadata?.name });
        return newSession.session_id;
      } else {
        console.error('创建默认会话失败:', data.message);
        return null;
      }
    } catch (error) {
      console.error('创建默认会话失败:', error);
      return null;
    }
  };

  // 创建新会话（用户输入名称）
  const handleCreateSession = async () => {
    if (!newSessionName.trim()) {
      toast.error('请输入会话名称');
      return;
    }
    
    setIsCreatingSession(true);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/sessions/create`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          session_name: newSessionName.trim(),
          session_description: newSessionDescription.trim() || undefined,
          metadata: {
            created_from: 'web_ui',
            created_at: new Date().toISOString()
          }
        }),
      });

      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          logger.info('新会话创建成功', { 
            sessionId: data.data.session_id, 
            name: newSessionName 
          });
          
          // 关闭对话框
          setShowNewSessionDialog(false);
          setNewSessionName('');
          setNewSessionDescription('');
          
          // 切换到新会话
          await handleSessionChange(data.data.session_id);
          
          toast.success(`会话"${newSessionName}"创建成功`);
        } else {
          throw new Error(data.message || '创建会话失败');
        }
      } else {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
    } catch (error) {
      logger.error('创建会话失败', error);
      toast.error('创建会话失败，请重试');
    } finally {
      setIsCreatingSession(false);
    }
  };

  // 处理会话选择（确保所有组件都重新加载）
  const handleSessionSelected = async (sessionId: string) => {
    if (sessionId === currentSessionId) return;
    
    try {
      setSessionLoading(true);
      
      // 更新当前会话ID
      setCurrentSessionId(sessionId);
      
      // 查找会话信息
      const sessionInfo = availableSessions.find(s => s.session_id === sessionId);
      if (sessionInfo) {
        setCurrentSessionInfo(sessionInfo);
      }
      
      // 通知所有子组件会话已切换（通过重新渲染强制更新）
      // 这里可以添加一个状态来强制重新渲染所有tab内容
      console.log(`切换到会话: ${sessionId}`);
      
      // 如果当前在地质建模中心tab，触发数据重新加载
      if (activeTab === 'modeling') {
        // 组件会通过sessionId的变化自动重新加载数据
      }
      
    } catch (error) {
      console.error('切换会话失败:', error);
    } finally {
      setSessionLoading(false);
    }
  };

  // 处理会话创建
  const handleSessionCreated = (session: SessionInfo) => {
    setCurrentSessionId(session.session_id);
    setCurrentSessionInfo(session);
  };

  // 处理会话删除
  const handleSessionDeleted = async (sessionId: string) => {
    if (sessionId === currentSessionId) {
      // 如果删除的是当前会话，切换到其他会话或创建新的默认会话
      const remainingSessions = availableSessions.filter(s => s.session_id !== sessionId);
      if (remainingSessions.length > 0) {
        await handleSessionSelected(remainingSessions[0].session_id);
      } else {
        // 没有其他会话，创建默认会话
        await getOrCreateDefaultSession();
      }
    }
    
    // 刷新会话列表
    await fetchSessions();
  };

  // 删除会话的具体实现
  const deleteSession = async (sessionId: string) => {
    if (!sessionId) return;
    
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/sessions/${sessionId}`, {
        method: 'DELETE',
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          toast.success('会话删除成功');
          
          // 调用删除处理逻辑
          await handleSessionDeleted(sessionId);
        } else {
          toast.error(data.message || '删除会话失败');
        }
      } else {
        toast.error('删除会话失败，请重试');
      }
    } catch (error) {
      logger.error('删除会话失败', error);
      toast.error('删除会话失败，请重试');
    }
  };

  // 确认删除会话
  const confirmDeleteSession = (sessionId: string, sessionName: string) => {
    if (confirm(`确定要删除会话"${sessionName}"吗？此操作不可撤销。`)) {
      deleteSession(sessionId);
    }
  };

  // 保存设置
  const handleSaveSettings = () => {
    // 这里可以保存设置到本地存储
    localStorage.setItem('petro-agent-settings', JSON.stringify(settings));
    setShowSettingsDialog(false);
  };

  // 格式化时间显示
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

  // 加载设置
  useEffect(() => {
    const savedSettings = localStorage.getItem('petro-agent-settings');
    if (savedSettings) {
      try {
        const parsed = JSON.parse(savedSettings);
        setSettings({ ...settings, ...parsed });
      } catch (e) {
        console.error('加载设置失败:', e);
      }
    }
  }, []);

  // 初始化：获取或创建默认会话（而不是总是创建新会话）
  useEffect(() => {
    if (!currentSessionId) {
      getOrCreateDefaultSession();
    }
  }, []);

  // 当会话ID变化时，定期获取会话列表
  useEffect(() => {
    if (currentSessionId) {
      // 初始获取一次
      fetchSessions();
      
      // 每30秒刷新一次会话列表
      const interval = setInterval(fetchSessions, 30000);
      return () => clearInterval(interval);
    }
  }, [currentSessionId]);

  const navigationItems = [
    {
      id: 'dashboard',
      label: '实时仪表盘',
      icon: LayoutGrid,
      description: '系统状态总览'
    },
    {
      id: 'modeling',
      label: '地质建模中心',
      icon: Brain,
      description: '智能建模与分析'
    },
    {
      id: 'workflow',
      label: '工作流管理',
      icon: WorkflowIcon,
      description: '任务编排与执行'
    },
    {
      id: 'data',
      label: '数据管理中心',
      icon: Database,
      description: '多源数据整合'
    },
    {
      id: 'analysis',
      label: '智能决策分析',
      icon: BarChart3,
      description: '深度数据洞察'
    }
  ];

  const renderTabContent = () => {
    // 如果没有会话ID，显示加载状态
    if (!currentSessionId) {
      return (
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-4 text-gray-400" />
            <p className="text-gray-500">正在初始化会话...</p>
          </div>
        </div>
      );
    }

    switch (activeTab) {
      case 'dashboard':
        return <Dashboard apiBaseUrl={apiBaseUrl} />;
      
      case 'modeling':
        return <GeologicalModelingHub apiBaseUrl={apiBaseUrl} sessionId={currentSessionId} key={currentSessionId} />;
      
      case 'workflow':
        return (
          <div className="p-6 space-y-6" key={currentSessionId}>
            <div className="flex items-center justify-between">
              <h2 className="text-3xl font-bold text-gray-900">智能任务工作流管理</h2>
              <Button>创建新工作流</Button>
            </div>
            
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <DAGVisualization 
                title="当前工作流图"
                className="h-96"
              />
              <WorkflowHistory apiBaseUrl={apiBaseUrl} />
            </div>
          </div>
        );
      
      case 'data':
        return <DataManager 
          apiBaseUrl={apiBaseUrl}
          sessionId={currentSessionId}
          key={currentSessionId}
        />;
      
      case 'analysis':
        return (
          <div className="p-6 space-y-6" key={currentSessionId}>
            <div className="flex items-center justify-between">
              <h2 className="text-3xl font-bold text-gray-900">智能决策与分析模块</h2>
              <Button>生成分析报告</Button>
            </div>
            
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* 甜点区识别 */}
              <Card>
                <CardHeader>
                  <CardTitle>甜点区识别</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div className="h-64 bg-gray-100 rounded flex items-center justify-center">
                      <div className="text-center text-gray-500">
                        <div className="text-4xl mb-2">🎯</div>
                        <div>甜点概率分布图</div>
                        <div className="text-sm mt-1">模型运行后显示结果</div>
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-4 text-center">
                      <div>
                        <div className="text-sm text-red-600">高概率区域</div>
                        <div className="font-bold">3 个区块</div>
                      </div>
                      <div>
                        <div className="text-sm text-yellow-600">中等概率区域</div>
                        <div className="font-bold">7 个区块</div>
                      </div>
                      <div>
                        <div className="text-sm text-gray-600">推荐钻井位置</div>
                        <div className="font-bold">12 个点</div>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
              
              {/* 资源潜力评估 */}
              <Card>
                <CardHeader>
                  <CardTitle>资源潜力评估</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div className="space-y-3">
                      <div className="flex justify-between items-center">
                        <span className="text-blue-600">储量预测</span>
                        <span className="font-bold text-lg">2.4 亿 m³</span>
                      </div>
                      <div className="text-sm text-gray-500">置信度: 65%</div>
                      
                      <div className="flex justify-between items-center">
                        <span className="text-green-600">经济评价</span>
                        <span className="font-bold text-lg">NPV: $45M</span>
                      </div>
                      <div className="text-sm text-gray-500">IRR: 23.5%</div>
                      
                      <div className="flex justify-between items-center">
                        <span className="text-purple-600">风险评估</span>
                        <span className="font-bold text-lg">中等风险</span>
                      </div>
                      <div className="text-sm text-gray-500">成功概率: 72%</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
            
            {/* 智能洞察与建议 */}
            <Card>
              <CardHeader>
                <CardTitle>智能洞察与建议</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div className="p-4 bg-green-50 rounded-lg">
                    <div className="flex items-center mb-2">
                      <div className="w-2 h-2 bg-green-500 rounded-full mr-2"></div>
                      <span className="font-medium text-green-800">优化建议</span>
                    </div>
                    <p className="text-sm text-green-700">
                      建议在A区块执行加密井方案，预计可提升产量15%
                    </p>
                  </div>
                  
                  <div className="p-4 bg-yellow-50 rounded-lg">
                    <div className="flex items-center mb-2">
                      <div className="w-2 h-2 bg-yellow-500 rounded-full mr-2"></div>
                      <span className="font-medium text-yellow-800">风险提醒</span>
                    </div>
                    <p className="text-sm text-yellow-700">
                      B区块存在断层风险，建议进行详细地震解释
                    </p>
                  </div>
                  
                  <div className="p-4 bg-blue-50 rounded-lg">
                    <div className="flex items-center mb-2">
                      <div className="w-2 h-2 bg-blue-500 rounded-full mr-2"></div>
                      <span className="font-medium text-blue-800">技术建议</span>
                    </div>
                    <p className="text-sm text-blue-700">
                      推荐采用水平压裂技术，预计可提升改造效果
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        );
      
      default:
        return <Dashboard apiBaseUrl={apiBaseUrl} />;
    }
  };

  const handleSessionChange = async (sessionId: string) => {
    if (sessionId === currentSessionId) return;
    
    setIsSessionChanging(true);
    try {
      logger.info('切换会话', { from: currentSessionId, to: sessionId });
      
      // 首先更新会话ID
      setCurrentSessionId(sessionId);
      
      // 清空当前消息，准备加载新会话的历史记录
      setMessages([]);
      
      // 刷新会话列表以获取最新信息
      const sessions = await fetchSessions();
      
      // 找到并设置当前会话信息
      const targetSession = sessions.find((s: SessionInfo) => s.session_id === sessionId);
      if (targetSession) {
        setCurrentSessionInfo(targetSession);
        logger.info('更新当前会话信息', { sessionInfo: targetSession });
      } else {
        logger.error('未找到目标会话信息', { sessionId });
      }
      
      // 加载新会话的聊天历史
      try {
        const historyResponse = await fetch(`${apiBaseUrl}/api/v1/chat/${sessionId}/history`);
        if (historyResponse.ok) {
          const historyData = await historyResponse.json();
          if (historyData.success && historyData.data?.messages) {
            // 转换历史消息格式
            const historyMessages = historyData.data.messages.map((msg: any) => ({
              id: Date.now() + Math.random(),
              content: msg.content || '',
              sender: msg.role === 'user' ? 'user' : 'assistant',
              timestamp: msg.timestamp || new Date().toISOString(),
              type: msg.type || 'text'
            }));
            
            setMessages(historyMessages);
            logger.info('成功加载会话历史记录', { 
              sessionId, 
              messageCount: historyMessages.length 
            });
            
            // 显示成功提示
            if (historyMessages.length > 0) {
              toast.success(`已切换到会话，加载了 ${historyMessages.length} 条历史消息`);
            } else {
              toast.success('已切换到新会话');
            }
          }
        } else {
          logger.warn('获取会话历史失败', { sessionId, status: historyResponse.status });
          toast.error('会话切换成功，但历史记录加载失败');
        }
      } catch (historyError) {
        logger.error('加载会话历史时出错', historyError);
        toast.error('会话切换成功，但历史记录加载失败');
      }
      
      logger.info('会话切换完成', { sessionId });
    } catch (error) {
      logger.error('切换会话失败', error);
      toast.error('切换会话失败，请重试');
    } finally {
      setIsSessionChanging(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex">
      {/* 侧边栏 */}
      <div className={`bg-white shadow-lg transition-all duration-300 ${sidebarOpen ? 'w-64' : 'w-16'}`}>
        <div className="p-4">
          <div className="flex items-center justify-between mb-8">
            <div className={`flex items-center ${sidebarOpen ? '' : 'justify-center'}`}>
              <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold mr-3">
                P
              </div>
              {sidebarOpen && (
                <div>
                  <h1 className="text-xl font-bold text-gray-900">PetroAgent</h1>
                  <p className="text-xs text-gray-500">智能地质分析系统</p>
                </div>
              )}
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="p-1"
            >
              {sidebarOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            </Button>
          </div>

          <nav className="space-y-2">
            {navigationItems.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveTab(item.id)}
                  className={`w-full flex items-center px-3 py-2 rounded-lg text-left transition-colors ${
                    activeTab === item.id
                      ? 'bg-blue-100 text-blue-700 border border-blue-200'
                      : 'text-gray-600 hover:bg-gray-100'
                  }`}
                >
                  <Icon className="h-5 w-5 mr-3" />
                  {sidebarOpen && (
                    <div>
                      <div className="font-medium">{item.label}</div>
                      <div className="text-xs text-gray-500">{item.description}</div>
                    </div>
                  )}
                </button>
              );
            })}
          </nav>

          {/* 侧边栏底部：会话管理 */}
          {sidebarOpen && currentSessionId && (
            <div className="mt-8 pt-4 border-t border-gray-200">
              <div className="text-xs text-gray-500 mb-2">当前会话</div>
              <div className="bg-gray-50 rounded-lg p-3">
                <div className="text-sm font-medium text-gray-900 truncate">
                  {currentSessionInfo?.metadata?.title || currentSessionInfo?.metadata?.name || '未命名会话'}
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  {currentSessionInfo?.last_updated && formatTime(currentSessionInfo.last_updated)}
                </div>
                <div className="text-xs text-gray-500">
                  {currentSessionInfo?.message_count || 0} 条消息
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 主内容区域 */}
      <div className="flex-1 flex flex-col">
        {/* 顶部标题栏 */}
        <div className="bg-white shadow-sm border-b p-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">
                {navigationItems.find(item => item.id === activeTab)?.label || 'PetroAgent'}
              </h1>
              <p className="text-sm text-gray-600">
                {navigationItems.find(item => item.id === activeTab)?.description}
              </p>
            </div>
            
            {/* 右上角操作按钮 */}
            <div className="flex items-center space-x-3">
              {/* 会话选择下拉菜单 */}
              <div className="flex items-center space-x-2">
                <Select value={currentSessionId} onValueChange={handleSessionChange}>
                  <SelectTrigger className="w-[300px]">
                    <SelectValue placeholder="选择会话">
                      {currentSessionId && availableSessions.length > 0 && (
                        <div className="flex items-center justify-between w-full">
                          <span className="font-medium">
                            {availableSessions.find(s => s.session_id === currentSessionId)?.metadata?.name || 
                             availableSessions.find(s => s.session_id === currentSessionId)?.metadata?.title || 
                             '未命名会话'}
                          </span>
                          <span className="text-xs text-gray-500 ml-2">
                            {availableSessions.find(s => s.session_id === currentSessionId)?.message_count || 0} 条消息
                          </span>
                        </div>
                      )}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {availableSessions.map((session) => (
                      <SelectItem key={session.session_id} value={session.session_id}>
                        <div className="flex flex-col py-1">
                          <div className="font-medium">
                            {session.metadata?.name || session.metadata?.title || '未命名会话'}
                          </div>
                          <div className="text-xs text-gray-500 flex items-center space-x-2">
                            <span>
                              {new Date(session.last_updated).toLocaleDateString('zh-CN', {
                                month: 'short',
                                day: 'numeric',
                                hour: '2-digit',
                                minute: '2-digit'
                              })}
                            </span>
                            <span>•</span>
                            <span>{session.message_count || 0} 条消息</span>
                            {session.metadata?.description && (
                              <>
                                <span>•</span>
                                <span className="truncate max-w-[100px]">
                                  {session.metadata.description}
                                </span>
                              </>
                            )}
                          </div>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                {/* 会话操作菜单 */}
                {currentSessionId && (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button size="sm" variant="outline">
                        <MoreVertical className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem
                        onClick={() => {
                          const sessionName = currentSessionInfo?.metadata?.name || 
                                            currentSessionInfo?.metadata?.title || 
                                            '未命名会话';
                          confirmDeleteSession(currentSessionId, sessionName);
                        }}
                        className="text-red-600 hover:text-red-700 hover:bg-red-50"
                      >
                        <Trash2 className="h-4 w-4 mr-2" />
                        删除会话
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                )}
              </div>

              {/* 刷新会话按钮 */}
              <Button 
                size="sm" 
                variant="outline"
                onClick={fetchSessions}
                disabled={sessionLoading}
              >
                <RefreshCw className={`h-4 w-4 ${sessionLoading ? 'animate-spin' : ''}`} />
              </Button>
              
              {/* 新建会话按钮 */}
              <Dialog open={showNewSessionDialog} onOpenChange={setShowNewSessionDialog}>
                <DialogTrigger asChild>
                  <Button size="sm">
                    <Plus className="h-4 w-4 mr-2" />
                    新建会话
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>创建新会话</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-4 py-4">
                    <div>
                      <Label htmlFor="sessionName">会话名称 *</Label>
                      <Input
                        id="sessionName"
                        value={newSessionName}
                        onChange={(e) => setNewSessionName(e.target.value)}
                        placeholder="输入会话名称，例如：某某油田数据分析"
                        maxLength={50}
                      />
                      <p className="text-xs text-gray-500 mt-1">
                        {newSessionName.length}/50 字符
                      </p>
                    </div>
                    
                    <div>
                      <Label htmlFor="sessionDescription">描述（可选）</Label>
                      <Input
                        id="sessionDescription"
                        value={newSessionDescription}
                        onChange={(e) => setNewSessionDescription(e.target.value)}
                        placeholder="简要描述本次分析的目标和内容"
                        maxLength={100}
                      />
                      <p className="text-xs text-gray-500 mt-1">
                        {newSessionDescription.length}/100 字符
                      </p>
                    </div>
                    
                    <div className="flex justify-end space-x-2">
                      <Button 
                        variant="outline" 
                        onClick={() => {
                          setShowNewSessionDialog(false);
                          setNewSessionName('');
                          setNewSessionDescription('');
                        }}
                      >
                        取消
                      </Button>
                      <Button 
                        onClick={handleCreateSession}
                        disabled={!newSessionName.trim()}
                      >
                        创建会话
                      </Button>
                    </div>
                  </div>
                </DialogContent>
              </Dialog>

              {/* 设置按钮 */}
              <Dialog open={showSettingsDialog} onOpenChange={setShowSettingsDialog}>
                <DialogTrigger asChild>
                  <Button variant="outline" size="sm">
                    <Settings className="h-4 w-4 mr-2" />
                    设置
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>系统设置</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-4 py-4">
                    <div>
                      <Label htmlFor="apiBaseUrl">API基础URL</Label>
                      <Input
                        id="apiBaseUrl"
                        value={settings.apiBaseUrl}
                        onChange={(e) => setSettings({...settings, apiBaseUrl: e.target.value})}
                        placeholder="http://localhost:7102"
                      />
                    </div>
                    
                    <div className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        id="autoSave"
                        checked={settings.autoSave}
                        onChange={(e) => setSettings({...settings, autoSave: e.target.checked})}
                      />
                      <Label htmlFor="autoSave">自动保存会话</Label>
                    </div>
                    
                    <div className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        id="darkMode"
                        checked={settings.darkMode}
                        onChange={(e) => setSettings({...settings, darkMode: e.target.checked})}
                      />
                      <Label htmlFor="darkMode">深色模式</Label>
                    </div>
                    
                    <div className="flex justify-end space-x-2">
                      <Button 
                        variant="outline" 
                        onClick={() => setShowSettingsDialog(false)}
                      >
                        取消
                      </Button>
                      <Button onClick={handleSaveSettings}>
                        保存
                      </Button>
                    </div>
                  </div>
                </DialogContent>
              </Dialog>
            </div>
          </div>
        </div>

        {/* 主内容 */}
        <div className="flex-1 overflow-auto">
          {renderTabContent()}
        </div>
      </div>
      
      {/* Toast通知 */}
      <Toaster />
    </div>
  );
}
