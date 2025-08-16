"use client";

import React, { useState, useEffect, useRef } from 'react';
import { Button } from './ui/button';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';

interface FileInfo {
  file_id: string;
  file_name: string;
  file_type: string;
  file_size: number;
  content_type: string;
  upload_time: string;
  session_id?: string;
  url?: string;
  metadata?: Record<string, any>;
}

interface FileManagerProps {
  sessionId?: string;
  apiBaseUrl?: string;
  className?: string;
  onFileUploaded?: (file: FileInfo) => void;
  onFileSelected?: (file: FileInfo) => void;
}

export default function FileManager({
  sessionId,
  apiBaseUrl = 'http://localhost:7102',
  className = "",
  onFileUploaded,
  onFileSelected
}: FileManagerProps) {
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 获取文件列表
  const fetchFiles = async () => {
    try {
      setIsLoading(true);
      setError(null);
      
      const params = new URLSearchParams();
      if (sessionId) {
        params.append('session_id', sessionId);
      }
      
      const response = await fetch(`${apiBaseUrl}/api/v1/files/list?${params}`);
      if (!response.ok) {
        if (response.status === 404) {
          // 404错误表示没有文件，设置为空数组
          setFiles([]);
          return;
        }
        throw new Error(`获取文件列表失败: ${response.status}`);
      }
      
      const data = await response.json();
      if (data.success && data.data?.files) {
        setFiles(data.data.files);
      } else {
        // 如果没有文件数据，设置为空数组
        setFiles([]);
      }
    } catch (err) {
      console.error('获取文件列表错误:', err);
      setError(err instanceof Error ? err.message : '获取文件列表失败');
      // 即使出错也设置为空数组，避免显示错误
      setFiles([]);
    } finally {
      setIsLoading(false);
    }
  };

  // 上传文件
  const handleFileUpload = async (fileList: FileList) => {
    if (!fileList.length) return;

    setIsUploading(true);
    setError(null);

    try {
      for (const file of Array.from(fileList)) {
        const formData = new FormData();
        formData.append('file', file);
        if (sessionId) {
          formData.append('session_id', sessionId);
        }

        const response = await fetch(`${apiBaseUrl}/api/v1/files/upload`, {
          method: 'POST',
          body: formData,
        });

        if (!response.ok) {
          throw new Error(`上传文件 ${file.name} 失败: ${response.status}`);
        }

        const data = await response.json();
        if (data.success && data.file_info) {
          const newFile = data.file_info;
          setFiles(prev => [newFile, ...prev]);
          onFileUploaded?.(newFile);
        } else {
          throw new Error(data.message || `上传文件 ${file.name} 失败`);
        }
      }
    } catch (err) {
      console.error('文件上传错误:', err);
      setError(err instanceof Error ? err.message : '文件上传失败');
    } finally {
      setIsUploading(false);
      // 清空文件输入
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  // 下载文件
  const handleDownload = async (file: FileInfo) => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/files/${file.file_id}/download`);
      if (!response.ok) {
        throw new Error(`下载文件失败: ${response.status}`);
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = file.file_name;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('下载文件错误:', err);
      setError(err instanceof Error ? err.message : '下载文件失败');
    }
  };

  // 删除文件
  const handleDelete = async (fileId: string) => {
    if (!confirm('确定要删除这个文件吗？此操作不可撤销。')) {
      return;
    }

    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/files/${fileId}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        throw new Error(`删除文件失败: ${response.status}`);
      }

      const data = await response.json();
      if (data.success) {
        setFiles(prev => prev.filter(f => f.file_id !== fileId));
        setSelectedFiles(prev => {
          const newSet = new Set(prev);
          newSet.delete(fileId);
          return newSet;
        });
      } else {
        throw new Error(data.message || '删除文件失败');
      }
    } catch (err) {
      console.error('删除文件错误:', err);
      setError(err instanceof Error ? err.message : '删除文件失败');
    }
  };

  // 格式化文件大小
  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  // 获取文件类型图标
  const getFileIcon = (fileType: string): string => {
    switch (fileType.toLowerCase()) {
      case 'image':
        return '🖼️';
      case 'document':
        return '📄';
      case 'text':
        return '📝';
      case 'code':
        return '💻';
      case 'data':
        return '📊';
      case 'archive':
        return '📦';
      case 'spreadsheet':
        return '📈';
      case 'presentation':
        return '📽️';
      default:
        return '📁';
    }
  };

  // 获取文件类型颜色
  const getFileTypeColor = (fileType: string): string => {
    switch (fileType.toLowerCase()) {
      case 'image':
        return 'bg-green-100 text-green-800';
      case 'document':
        return 'bg-blue-100 text-blue-800';
      case 'text':
        return 'bg-gray-100 text-gray-800';
      case 'code':
        return 'bg-purple-100 text-purple-800';
      case 'data':
        return 'bg-orange-100 text-orange-800';
      case 'archive':
        return 'bg-yellow-100 text-yellow-800';
      case 'spreadsheet':
        return 'bg-emerald-100 text-emerald-800';
      case 'presentation':
        return 'bg-pink-100 text-pink-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  // 切换文件选择状态
  const toggleFileSelection = (fileId: string) => {
    setSelectedFiles(prev => {
      const newSet = new Set(prev);
      if (newSet.has(fileId)) {
        newSet.delete(fileId);
      } else {
        newSet.add(fileId);
      }
      return newSet;
    });
  };

  // 批量删除文件
  const handleBatchDelete = async () => {
    if (selectedFiles.size === 0) {
      alert('请先选择要删除的文件');
      return;
    }

    if (!confirm(`确定要删除选中的 ${selectedFiles.size} 个文件吗？此操作不可撤销。`)) {
      return;
    }

    try {
      for (const fileId of selectedFiles) {
        await handleDelete(fileId);
      }
      setSelectedFiles(new Set());
    } catch (err) {
      console.error('批量删除文件错误:', err);
      setError(err instanceof Error ? err.message : '批量删除文件失败');
    }
  };

  // 格式化时间
  const formatTime = (timeString: string): string => {
    try {
      return new Date(timeString).toLocaleString('zh-CN');
    } catch {
      return timeString;
    }
  };

  // 组件挂载时获取文件列表
  useEffect(() => {
    fetchFiles();
  }, [sessionId]);

  return (
    <Card className={`w-full ${className}`}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">文件管理</CardTitle>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className="h-8"
          >
            {isUploading ? '上传中...' : '上传文件'}
          </Button>
          {selectedFiles.size > 0 && (
            <Button
              size="sm"
              variant="destructive"
              onClick={handleBatchDelete}
              className="h-8"
            >
              删除选中 ({selectedFiles.size})
            </Button>
          )}
        </div>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={(e) => e.target.files && handleFileUpload(e.target.files)}
          className="hidden"
        />
      </CardHeader>
      <CardContent>
        {error && (
          <div className="mb-4 p-2 bg-red-50 border border-red-200 rounded text-red-600 text-sm">
            {error}
            <button 
              onClick={() => setError(null)}
              className="ml-2 text-red-800 hover:text-red-900"
            >
              ×
            </button>
          </div>
        )}

        {isLoading ? (
          <div className="text-center py-4 text-sm text-gray-500">
            加载文件列表...
          </div>
        ) : files.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <div className="text-4xl mb-2">📁</div>
            <div>暂无文件</div>
            <div className="text-sm mt-1">点击"上传文件"按钮开始上传</div>
          </div>
        ) : (
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {files.map((file) => (
              <div
                key={file.file_id}
                className={`p-3 border rounded cursor-pointer transition-colors ${
                  selectedFiles.has(file.file_id)
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                }`}
                onClick={() => {
                  toggleFileSelection(file.file_id);
                  onFileSelected?.(file);
                }}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <span className="text-lg">{getFileIcon(file.file_type)}</span>
                    <span className="font-medium text-sm truncate">
                      {file.file_name}
                    </span>
                    <Badge className={`text-xs ${getFileTypeColor(file.file_type)}`}>
                      {file.file_type}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-2 ml-2">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDownload(file);
                      }}
                      className="h-6 w-6 p-0"
                      title="下载文件"
                    >
                      ⬇️
                    </Button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(file.file_id);
                      }}
                      className="text-red-500 hover:text-red-700 text-sm"
                      title="删除文件"
                    >
                      ×
                    </button>
                  </div>
                </div>
                <div className="text-xs text-gray-600 flex justify-between">
                  <span>大小: {formatFileSize(file.file_size)}</span>
                  <span>上传于: {formatTime(file.upload_time)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
} 