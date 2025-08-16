import { useState, useCallback, useEffect, useRef } from 'react';
import { FileGeneratedMessage, StreamMessageType } from './streaming-types';

// 文件树中的文件项接口
export interface FileItem {
  file_id: string;
  file_name: string;
  file_type: string;
  file_size: number;
  upload_time: string;
  file_path?: string;
  is_generated?: boolean;
  session_id?: string;
  metadata?: any;
  category?: string;
  description?: string;
}

// 文件分类配置
export interface FileCategoryConfig {
  pattern: RegExp | ((file: FileItem) => boolean);
  folder: string;
  priority: number;
  description: string;
}

// 默认文件分类规则
export const DEFAULT_FILE_CATEGORIES: FileCategoryConfig[] = [
  {
    pattern: /\.(png|jpg|jpeg|gif|svg|webp)$/i,
    folder: 'generated/charts',
    priority: 10,
    description: '生成的图表和图像文件'
  },
  {
    pattern: /\.(csv|xlsx|xls)$/i,
    folder: 'input/data',
    priority: 8,
    description: '数据文件'
  },
  {
    pattern: /\.(las|log)$/i,
    folder: 'input/logs',
    priority: 9,
    description: '测井数据文件'
  },
  {
    pattern: /\.(pdf|doc|docx)$/i,
    folder: 'input/documents',
    priority: 7,
    description: '文档文件'
  },
  {
    pattern: /\.(py|js|ts|json)$/i,
    folder: 'generated/scripts',
    priority: 6,
    description: '生成的脚本文件'
  },
  {
    pattern: /report|analysis|summary/i,
    folder: 'generated/reports',
    priority: 8,
    description: '分析报告'
  },
  {
    pattern: () => true, // 默认分类
    folder: 'generated/others',
    priority: 1,
    description: '其他生成文件'
  }
];

// 文件树集成管理器配置
export interface FileTreeIntegrationConfig {
  sessionId: string;
  apiBaseUrl?: string;
  categories?: FileCategoryConfig[];
  enableAutoClassification?: boolean;
  enableAutoRefresh?: boolean;
  refreshInterval?: number;
  onFileAdded?: (file: FileItem) => void;
  onFileRemoved?: (fileId: string) => void;
  onFolderCreated?: (folderPath: string) => void;
  enableDebugLogs?: boolean;
}

export function useFileTreeIntegration(config: FileTreeIntegrationConfig) {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [folders, setFolders] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());
  
  const refreshTimerRef = useRef<NodeJS.Timeout | null>(null);
  const pendingFiles = useRef<Set<string>>(new Set());
  const categories = config.categories || DEFAULT_FILE_CATEGORIES;
  
  const apiBaseUrl = config.apiBaseUrl || 'http://localhost:7102';

  // 调试日志
  const debugLog = useCallback((message: string, data?: any) => {
    if (config.enableDebugLogs) {
      console.log(`[FileTreeIntegration] ${message}`, data);
    }
  }, [config.enableDebugLogs]);

  // 文件分类函数
  const classifyFile = useCallback((file: FileItem): string => {
    debugLog(`分类文件: ${file.file_name}`, file);
    
    // 如果文件已有路径，优先使用现有路径
    if (file.file_path && file.file_path !== file.file_name) {
      const pathParts = file.file_path.split('/');
      if (pathParts.length > 1) {
        return pathParts.slice(0, -1).join('/');
      }
    }
    
    // 根据文件元数据分类
    if (file.metadata?.analysis_type) {
      const analysisType = file.metadata.analysis_type.toLowerCase();
      if (analysisType.includes('isotope')) {
        return 'generated/isotope_analysis';
      }
      if (analysisType.includes('log')) {
        return 'generated/log_analysis';
      }
      if (analysisType.includes('chart')) {
        return 'generated/charts';
      }
    }
    
    // 根据category字段分类
    if (file.category) {
      const categoryLower = file.category.toLowerCase();
      if (categoryLower.includes('chart') || categoryLower.includes('图表')) {
        return 'generated/charts';
      }
      if (categoryLower.includes('report') || categoryLower.includes('报告')) {
        return 'generated/reports';
      }
      if (categoryLower.includes('data') || categoryLower.includes('数据')) {
        return 'input/data';
      }
    }
    
    // 按优先级应用分类规则
    const sortedCategories = [...categories].sort((a, b) => b.priority - a.priority);
    
    for (const category of sortedCategories) {
      if (typeof category.pattern === 'function') {
        if (category.pattern(file)) {
          debugLog(`文件匹配规则: ${category.description} -> ${category.folder}`);
          return category.folder;
        }
      } else if (category.pattern instanceof RegExp) {
        if (category.pattern.test(file.file_name)) {
          debugLog(`文件匹配正则: ${category.pattern} -> ${category.folder}`);
          return category.folder;
        }
      }
    }
    
    return 'generated/others';
  }, [categories, debugLog]);

  // 获取文件列表
  const fetchFiles = useCallback(async (retryCount = 0) => {
    if (!config.sessionId) {
      debugLog('没有会话ID，跳过文件获取');
      return;
    }
    
    try {
      setLoading(true);
      debugLog(`获取会话文件: ${config.sessionId}`);
      
      const params = new URLSearchParams();
      params.append('session_id', config.sessionId);
      
      const response = await fetch(`${apiBaseUrl}/api/v1/files/list?${params}`);
      
      if (response.ok) {
        const data = await response.json();
        if (data.success && data.files) {
          setFiles(data.files);
          setLastRefresh(new Date());
          debugLog(`成功获取 ${data.files.length} 个文件`);
        } else {
          debugLog('API响应格式错误', data);
        }
      } else {
        const errorText = await response.text();
        debugLog(`获取文件失败 (${response.status}): ${errorText}`);
        
        // 重试逻辑
        if (retryCount < 2) {
          setTimeout(() => fetchFiles(retryCount + 1), 1000);
          return;
        }
      }
    } catch (error) {
      debugLog('获取文件异常', error);
      
      // 重试逻辑
      if (retryCount < 2) {
        setTimeout(() => fetchFiles(retryCount + 1), 1000);
        return;
      }
    } finally {
      setLoading(false);
    }
  }, [config.sessionId, apiBaseUrl, debugLog]);

  // 获取文件夹列表
  const fetchFolders = useCallback(async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/files/folders/tree`);
      if (response.ok) {
        const data = await response.json();
        if (data.success && data.data?.folders) {
          setFolders(data.data.folders);
          debugLog(`获取到 ${data.data.folders.length} 个文件夹`);
        }
      }
    } catch (error) {
      debugLog('获取文件夹失败', error);
    }
  }, [apiBaseUrl, debugLog]);

  // 创建文件夹
  const createFolder = useCallback(async (folderPath: string): Promise<boolean> => {
    try {
      debugLog(`创建文件夹: ${folderPath}`);
      
      const response = await fetch(`${apiBaseUrl}/api/v1/files/folders/create`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          folder_path: folderPath
        })
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          setFolders(prev => [...prev, folderPath]);
          config.onFolderCreated?.(folderPath);
          debugLog(`文件夹创建成功: ${folderPath}`);
          return true;
        }
      }
      
      debugLog(`文件夹创建失败: ${folderPath}`);
      return false;
    } catch (error) {
      debugLog('创建文件夹异常', error);
      return false;
    }
  }, [apiBaseUrl, config, debugLog]);

  // 移动文件到指定文件夹
  const moveFileToFolder = useCallback(async (fileId: string, targetFolder: string): Promise<boolean> => {
    try {
      debugLog(`移动文件 ${fileId} 到 ${targetFolder}`);
      
      const formData = new FormData();
      formData.append('target_folder', targetFolder);
      
      const response = await fetch(`${apiBaseUrl}/api/v1/files/${fileId}/move`, {
        method: 'PUT',
        body: formData
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          debugLog(`文件移动成功: ${fileId} -> ${targetFolder}`);
          // 刷新文件列表
          await fetchFiles();
          return true;
        }
      }
      
      debugLog(`文件移动失败: ${fileId} -> ${targetFolder}`);
      return false;
    } catch (error) {
      debugLog('移动文件异常', error);
      return false;
    }
  }, [apiBaseUrl, fetchFiles, debugLog]);

  // 处理文件生成事件
  const handleFileGenerated = useCallback(async (fileMessage: FileGeneratedMessage) => {
    debugLog('处理文件生成事件', fileMessage);
    
    // 防止重复处理
    if (pendingFiles.current.has(fileMessage.file_id)) {
      debugLog('文件已在处理中，跳过', fileMessage.file_id);
      return;
    }
    
    pendingFiles.current.add(fileMessage.file_id);
    
    try {
      // 转换为FileItem格式
      const newFile: FileItem = {
        file_id: fileMessage.file_id,
        file_name: fileMessage.file_name,
        file_type: fileMessage.file_type,
        file_size: fileMessage.file_size || 0,
        upload_time: fileMessage.timestamp,
        file_path: fileMessage.file_path,
        is_generated: fileMessage.type === StreamMessageType.FILE_GENERATED,
        session_id: config.sessionId,
        category: fileMessage.category,
        description: fileMessage.description,
        metadata: fileMessage.metadata
      };
      
      // 自动分类并移动文件
      if (config.enableAutoClassification) {
        const targetFolder = classifyFile(newFile);
        
        // 确保目标文件夹存在
        if (!folders.includes(targetFolder)) {
          await createFolder(targetFolder);
        }
        
        // 如果文件不在正确的文件夹中，移动它
        const currentFolder = newFile.file_path ? 
          newFile.file_path.split('/').slice(0, -1).join('/') : '';
        
        if (currentFolder !== targetFolder) {
          await moveFileToFolder(newFile.file_id, targetFolder);
          newFile.file_path = `${targetFolder}/${newFile.file_name}`;
        }
      }
      
      // 更新本地文件列表
      setFiles(prev => {
        const existingIndex = prev.findIndex(f => f.file_id === newFile.file_id);
        if (existingIndex >= 0) {
          // 更新现有文件
          const updated = [...prev];
          updated[existingIndex] = newFile;
          return updated;
        } else {
          // 添加新文件
          return [...prev, newFile];
        }
      });
      
      config.onFileAdded?.(newFile);
      debugLog('文件处理完成', newFile);
      
    } catch (error) {
      debugLog('处理文件生成事件失败', error);
    } finally {
      pendingFiles.current.delete(fileMessage.file_id);
    }
  }, [
    config.sessionId, 
    config.enableAutoClassification, 
    config.onFileAdded,
    folders, 
    classifyFile, 
    createFolder, 
    moveFileToFolder,
    debugLog
  ]);

  // 删除文件
  const removeFile = useCallback(async (fileId: string): Promise<boolean> => {
    try {
      debugLog(`删除文件: ${fileId}`);
      
      const response = await fetch(`${apiBaseUrl}/api/v1/files/${fileId}`, {
        method: 'DELETE'
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          setFiles(prev => prev.filter(f => f.file_id !== fileId));
          config.onFileRemoved?.(fileId);
          debugLog(`文件删除成功: ${fileId}`);
          return true;
        }
      }
      
      debugLog(`文件删除失败: ${fileId}`);
      return false;
    } catch (error) {
      debugLog('删除文件异常', error);
      return false;
    }
  }, [apiBaseUrl, config, debugLog]);

  // 下载文件
  const downloadFile = useCallback(async (file: FileItem) => {
    try {
      debugLog(`下载文件: ${file.file_name}`);
      
      const response = await fetch(`${apiBaseUrl}/api/v1/files/${file.file_id}/download`);
      
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = file.file_name;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        debugLog(`文件下载成功: ${file.file_name}`);
      } else {
        debugLog(`文件下载失败: ${file.file_name}`);
      }
    } catch (error) {
      debugLog('下载文件异常', error);
    }
  }, [apiBaseUrl, debugLog]);

  // 获取文件预览URL
  const getFilePreviewUrl = useCallback((file: FileItem): string | null => {
    if (file.file_type.startsWith('image/')) {
      return `${apiBaseUrl}/api/v1/files/${file.file_id}/preview`;
    }
    return null;
  }, [apiBaseUrl]);

  // 自动刷新
  useEffect(() => {
    if (config.enableAutoRefresh && config.refreshInterval) {
      refreshTimerRef.current = setInterval(() => {
        fetchFiles();
      }, config.refreshInterval);
      
      return () => {
        if (refreshTimerRef.current) {
          clearInterval(refreshTimerRef.current);
        }
      };
    }
  }, [config.enableAutoRefresh, config.refreshInterval, fetchFiles]);

  // 初始化
  useEffect(() => {
    if (config.sessionId) {
      fetchFiles();
      fetchFolders();
    }
  }, [config.sessionId, fetchFiles, fetchFolders]);

  // 清理
  useEffect(() => {
    return () => {
      if (refreshTimerRef.current) {
        clearInterval(refreshTimerRef.current);
      }
    };
  }, []);

  return {
    // 状态
    files,
    folders,
    loading,
    lastRefresh,
    
    // 文件操作
    handleFileGenerated,
    removeFile,
    downloadFile,
    moveFileToFolder,
    getFilePreviewUrl,
    
    // 文件夹操作
    createFolder,
    
    // 刷新操作
    refresh: fetchFiles,
    refreshFolders: fetchFolders,
    
    // 工具函数
    classifyFile,
    
    // 统计信息
    stats: {
      totalFiles: files.length,
      generatedFiles: files.filter(f => f.is_generated).length,
      uploadedFiles: files.filter(f => !f.is_generated).length,
      totalFolders: folders.length
    }
  };
} 