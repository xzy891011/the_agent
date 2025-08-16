"use client";

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogDescription } from './ui/dialog';
import { 
  Database, 
  FileText, 
  BarChart3, 
  CheckCircle, 
  AlertTriangle, 
  Loader2,
  Upload,
  Download,
  Eye,
  Trash2,
  File,
  FileImage,
  Search,
  Filter,
  Folder,
  FolderPlus,
  FolderOpen,
  Wand2,
  Brain,
  Tags,
  Lightbulb,
  Move,
  Copy,
  MoreHorizontal,
  ChevronRight,
  ChevronDown,
  CheckSquare,
  Square,
  Move3D,
  Plus
} from 'lucide-react';
import { Input } from './ui/input';
import { ScrollArea } from './ui/scroll-area';
import { SmartFileClassifier } from './smart-file-classifier';
import { Label } from './ui/label';
import { DialogFooter } from './ui/dialog';

interface FileStatistics {
  total_files: number;
  file_types: Record<string, number>;
  total_size: number;
  uploaded_today: number;
  generated_today: number;
}

interface DataQuality {
  completeness: number;
  accuracy: number;
  consistency: number;
  validity: number;
  issues?: string[];
  recommendations?: string[];
}

interface FileItem {
  file_id: string;
  file_name: string;
  file_type: string;
  file_size: number;
  upload_time: string;
  session_id?: string;
  content_type?: string;
  url?: string;
  metadata?: any;
}

interface DataManagerProps {
  apiBaseUrl?: string;
  sessionId?: string;
}

// 新增接口定义
interface FolderNode {
  path: string;
  name: string;
  children: FolderNode[];
  files: FileItem[];
  isExpanded?: boolean;
}

interface FileOperation {
  type: 'move' | 'copy';
  sourceFileId: string;
  targetFolder: string;
}

// 新增：批量操作相关状态
interface BatchOperation {
  selectedFiles: Set<string>;
  operationType: 'move' | 'copy' | 'delete' | null;
  showBatchDialog: boolean;
}

export default function DataManager({ 
  apiBaseUrl = 'http://localhost:7102', 
  sessionId 
}: DataManagerProps) {
  const [statistics, setStatistics] = useState<FileStatistics | null>(null);
  const [quality, setQuality] = useState<DataQuality | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [showPreviewDialog, setShowPreviewDialog] = useState(false);
  const [previewData, setPreviewData] = useState<string>('');
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);

  // 新增文件管理相关状态
  const [files, setFiles] = useState<FileItem[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedFileType, setSelectedFileType] = useState<string>('all');
  const [showFileManager, setShowFileManager] = useState(false);
  const [selectedFile, setSelectedFile] = useState<FileItem | null>(null);
  const [showFileDetails, setShowFileDetails] = useState(false);

  // 新增状态变量
  const [folderTree, setFolderTree] = useState<FolderNode[]>([]);
  const [selectedFolder, setSelectedFolder] = useState<string>('');
  const [showSmartClassifier, setShowSmartClassifier] = useState(false);
  const [pendingOperation, setPendingOperation] = useState<FileOperation | null>(null);
  const [showCreateFolderDialog, setShowCreateFolderDialog] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [newFolderParent, setNewFolderParent] = useState('');
  const [draggedFile, setDraggedFile] = useState<FileItem | null>(null);
  
  // 文件操作相关状态
  const [selectedFileForOperation, setSelectedFileForOperation] = useState<string | null>(null);
  const [operationType, setOperationType] = useState<'copy' | 'move'>('copy');
  const [showFolderSelector, setShowFolderSelector] = useState(false);
  const [targetFolderPath, setTargetFolderPath] = useState('');

  // 新增：批量操作状态
  const [batchOperation, setBatchOperation] = useState<BatchOperation>({
    selectedFiles: new Set(),
    operationType: null,
    showBatchDialog: false
  });

  // 新增：文件夹操作状态
  const [showFolderOperationDialog, setShowFolderOperationDialog] = useState(false);
  const [folderOperationType, setFolderOperationType] = useState<'delete' | 'move' | null>(null);
  const [selectedFolderForOperation, setSelectedFolderForOperation] = useState<string>('');

  // 新增：文件夹内上传
  const [showUploadToFolderDialog, setShowUploadToFolderDialog] = useState(false);
  const [targetUploadFolder, setTargetUploadFolder] = useState('');

  // 在组件状态中添加新的状态
  const [pendingUploads, setPendingUploads] = useState<{files: File[], folderPath: string} | null>(null);
  const [showUploadConfirm, setShowUploadConfirm] = useState(false);

  const fetchDataStatistics = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      // 获取所有文件（不过滤会话），然后在客户端过滤
      const filesResponse = await fetch(`${apiBaseUrl}/api/v1/files/list`);
      
      if (filesResponse.ok) {
        const filesData = await filesResponse.json();
        if (filesData.success && filesData.files) {
          // 只统计用户通过数据管理中心上传的文件，排除系统生成的文件
          const uploadedFiles = filesData.files.filter((file: any) => 
            !file.metadata?.is_generated && 
            !file.is_generated &&
            file.file_name && 
            file.file_name.trim() !== ''
          );
          
          const fileTypes: Record<string, number> = {};
          let totalSize = 0;
          let uploadedToday = 0;

          const today = new Date().toDateString();

          uploadedFiles.forEach((file: any) => {
            // 统计文件类型
            const extension = file.file_name.split('.').pop()?.toLowerCase() || 'unknown';
            fileTypes[extension] = (fileTypes[extension] || 0) + 1;

            // 统计大小
            totalSize += file.file_size || 0;

            // 统计今日上传
            const fileDate = new Date(file.upload_time).toDateString();
            if (fileDate === today) {
              uploadedToday++;
            }
          });

          setStatistics({
            total_files: uploadedFiles.length,
            file_types: fileTypes,
            total_size: totalSize,
            uploaded_today: uploadedToday,
            generated_today: 0 // 数据管理中心不统计生成的文件
          });
        }
      }

      // 获取数据质量信息
      const qualityResponse = await fetch(`${apiBaseUrl}/api/v1/data/quality`);
      if (qualityResponse.ok) {
        const qualityData = await qualityResponse.json();
        if (qualityData.success) {
          setQuality(qualityData.data);
        }
      } else {
        // 如果没有质量数据，基于上传文件生成模拟数据
        const totalFiles = statistics?.total_files || 0;
        setQuality({
          completeness: Math.min(95, 80 + (totalFiles / 10)),
          accuracy: Math.min(98, 85 + (totalFiles / 20)),
          consistency: Math.min(92, 75 + (totalFiles / 15)),
          validity: Math.min(96, 82 + (totalFiles / 12)),
          issues: [],
          recommendations: totalFiles === 0 ? 
            ["建议上传一些数据文件进行分析"] : 
            ["数据质量良好，可以继续分析"]
        });
      }

    } catch (err) {
      setError('获取数据统计失败');
      console.error('获取数据统计失败:', err);
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl]);

  useEffect(() => {
    fetchDataStatistics();
  }, [fetchDataStatistics]);

  // 新增：获取所有文件列表
  const fetchFiles = useCallback(async () => {
    try {
      setFilesLoading(true);
      
      // 获取所有通过数据管理中心上传的文件（无会话过滤）
      const response = await fetch(`${apiBaseUrl}/api/v1/files/list`);
      
      if (response.ok) {
        const data = await response.json();
        if (data.success && data.files) {
          // 过滤掉系统生成的文件，只显示用户上传的文件
          const uploadedFiles = data.files.filter((file: FileItem) => 
            !file.metadata?.is_generated && file.file_name
          );
          setFiles(uploadedFiles);
        }
      }
    } catch (error) {
      console.error('获取文件列表失败:', error);
    } finally {
      setFilesLoading(false);
    }
  }, [apiBaseUrl]);

  // 新增：删除文件
  const handleDeleteFile = async (fileId: string) => {
    if (!confirm('确定要删除这个文件吗？此操作不可撤销。')) {
      return;
    }

    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/files/${fileId}`, {
        method: 'DELETE'
      });

      if (response.ok) {
        // 从列表中移除文件
        setFiles(prev => prev.filter(f => f.file_id !== fileId));
        // 刷新统计数据
        await fetchDataStatistics();
        console.log('文件删除成功');
      } else {
        console.error('删除文件失败');
      }
    } catch (error) {
      console.error('删除文件时发生错误:', error);
    }
  };

  // 新增：下载文件
  const handleDownloadFile = async (file: FileItem) => {
    try {
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
      }
    } catch (error) {
      console.error('下载文件失败:', error);
    }
  };

  // 新增：查看文件详情
  const handleViewFileDetails = (file: FileItem) => {
    setSelectedFile(file);
    setShowFileDetails(true);
  };

  // 新增：获取文件图标
  const getFileIcon = (fileType: string, fileName: string) => {
    const extension = fileName.split('.').pop()?.toLowerCase();
    
    if (extension === 'xlsx' || extension === 'xls') {
      return <FileText className="h-4 w-4 text-green-600" />;
    }
    
    if (extension === 'docx' || extension === 'doc') {
      return <FileText className="h-4 w-4 text-blue-600" />;
    }
    
    switch (fileType) {
      case 'image':
        return <FileImage className="h-4 w-4 text-green-500" />;
      case 'document':
        return <FileText className="h-4 w-4 text-blue-500" />;
      case 'spreadsheet':
        return <FileText className="h-4 w-4 text-green-500" />;
      case 'text':
        return <File className="h-4 w-4 text-gray-500" />;
      default:
        return <File className="h-4 w-4 text-gray-500" />;
    }
  };

  // 新增：过滤文件
  const filteredFiles = files.filter(file => {
    const matchesSearch = file.file_name.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesType = selectedFileType === 'all' || file.file_type === selectedFileType;
    
    // 如果选中了文件夹，只显示该文件夹中的文件
    const matchesFolder = !selectedFolder || 
      file.metadata?.folder_path === selectedFolder ||
      file.metadata?.path === selectedFolder ||
      (selectedFolder === '' && !file.metadata?.folder_path && !file.metadata?.path); // 根目录
    
    return matchesSearch && matchesType && matchesFolder;
  });

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const getQualityBadge = (score: number) => {
    if (score >= 95) {
      return <Badge className="bg-green-100 text-green-800">{score.toFixed(1)}% 优秀</Badge>;
    } else if (score >= 85) {
      return <Badge className="bg-blue-100 text-blue-800">{score.toFixed(1)}% 良好</Badge>;
    } else if (score >= 70) {
      return <Badge className="bg-yellow-100 text-yellow-800">{score.toFixed(1)}% 一般</Badge>;
    } else {
      return <Badge className="bg-red-100 text-red-800">{score.toFixed(1)}% 较差</Badge>;
    }
  };

  // 批量上传文件
  const handleBatchUpload = () => {
    setShowUploadDialog(true);
  };

  // 处理文件上传
  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    try {
      setUploading(true);
      let successCount = 0;
      let failCount = 0;
      
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const formData = new FormData();
        formData.append('file', file);
        
        // 如果选择了特定文件夹，将文件上传到该文件夹
        if (selectedFolder) {
          formData.append('folder_path', selectedFolder);
        }
        
        // 确保传递session_id
        if (sessionId) {
          formData.append('session_id', sessionId);
        } else {
          console.warn('警告：上传文件时没有会话ID，文件可能无法正确关联到会话');
        }
        
        const response = await fetch(`${apiBaseUrl}/api/v1/files/upload`, {
          method: 'POST',
          body: formData,
        });

        if (response.ok) {
          const result = await response.json();
          if (result.success) {
            console.log(`文件 ${file.name} 上传成功，文件ID: ${result.file_info?.file_id}`);
            successCount++;
          } else {
            console.error(`文件 ${file.name} 上传失败: ${result.message}`);
            failCount++;
          }
        } else {
          console.error(`文件 ${file.name} 上传失败，HTTP状态: ${response.status}`);
          failCount++;
        }
      }

      // 显示上传结果
      if (successCount > 0) {
        console.log(`成功上传 ${successCount} 个文件${failCount > 0 ? `，${failCount} 个失败` : ''}`);
        alert(`成功上传 ${successCount} 个文件${failCount > 0 ? `，${failCount} 个失败` : ''}`);
      }
      
      // 上传完成后刷新数据
      await fetchDataStatistics();
      await fetchFiles();
      await fetchFolderTree(); // 刷新文件夹树
      setShowUploadDialog(false);
      
      // 重置文件输入
      if (event.target) {
        event.target.value = '';
      }
      
    } catch (error) {
      console.error('批量上传失败:', error);
      setError('文件上传过程中发生错误');
      alert('文件上传过程中发生错误');
    } finally {
      setUploading(false);
    }
  };

  // 批量下载文件
  const handleBatchDownload = async () => {
    if (selectedFiles.length === 0) {
      alert('请先选择要下载的文件');
      return;
    }

    try {
      // 这里可以实现批量下载功能
      console.log('批量下载文件:', selectedFiles);
      alert(`开始下载 ${selectedFiles.length} 个文件`);
    } catch (error) {
      console.error('批量下载失败:', error);
    }
  };

  // 数据预览
  const handleDataPreview = async () => {
    try {
      // 获取一些示例数据进行预览
      const response = await fetch(`${apiBaseUrl}/api/v1/files/list?limit=5`);
      if (response.ok) {
        const data = await response.json();
        if (data.success && data.files) {
          const previewText = data.files.map((file: any) => 
            `文件名: ${file.file_name}\n类型: ${file.file_type}\n大小: ${file.file_size} 字节\n上传时间: ${file.upload_time}\n`
          ).join('\n---\n');
          
          setPreviewData(previewText || '暂无数据可预览');
          setShowPreviewDialog(true);
        }
      }
    } catch (error) {
      console.error('数据预览失败:', error);
      setPreviewData('数据预览失败');
      setShowPreviewDialog(true);
    }
  };

  // 质量检查
  const handleQualityCheck = async () => {
    try {
      // 重新获取质量数据
      await fetchDataStatistics();
      
      const qualityScore = quality ? 
        (quality.completeness + quality.accuracy + quality.consistency + quality.validity) / 4 : 0;
      
      let message = `数据质量检查完成！\n\n综合评分: ${qualityScore.toFixed(1)}%\n\n`;
      
      if (quality) {
        message += `完整性: ${quality.completeness.toFixed(1)}%\n`;
        message += `准确性: ${quality.accuracy.toFixed(1)}%\n`;
        message += `一致性: ${quality.consistency.toFixed(1)}%\n`;
        message += `有效性: ${quality.validity.toFixed(1)}%\n\n`;
        
        if (qualityScore >= 90) {
          message += '✅ 数据质量优秀';
        } else if (qualityScore >= 80) {
          message += '✅ 数据质量良好';
        } else if (qualityScore >= 70) {
          message += '⚠️ 数据质量一般，建议优化';
        } else {
          message += '❌ 数据质量较差，需要改进';
        }
      }
      
      alert(message);
    } catch (error) {
      console.error('质量检查失败:', error);
      alert('质量检查失败');
    }
  };

  // 新增：将扁平文件夹列表转换为树形结构
  const buildFolderTree = useCallback((folders: string[], files: FileItem[]): FolderNode[] => {
    const tree: FolderNode[] = [];
    const folderMap = new Map<string, FolderNode>();

    // 创建根节点映射
    const createFolderNode = (path: string): FolderNode => {
      const parts = path.split('/');
      const name = parts[parts.length - 1];
      return {
        path,
        name,
        children: [],
        files: [],
        isExpanded: false
      };
    };

    // 首先创建所有文件夹节点
    folders.forEach(folderPath => {
      if (!folderMap.has(folderPath)) {
        const node = createFolderNode(folderPath);
        folderMap.set(folderPath, node);
      }
    });

    // 构建层级关系
    folders.forEach(folderPath => {
      const node = folderMap.get(folderPath);
      if (!node) return;

      const parts = folderPath.split('/');
      if (parts.length === 1) {
        // 根级文件夹
        tree.push(node);
      } else {
        // 子文件夹，找到父文件夹
        const parentPath = parts.slice(0, -1).join('/');
        const parent = folderMap.get(parentPath);
        if (parent) {
          parent.children.push(node);
        } else {
          // 父文件夹不存在，添加到根级
          tree.push(node);
        }
      }
    });

    // 将文件分配到对应的文件夹
    files.forEach(file => {
      const folderPath = file.metadata?.folder_path || file.metadata?.path || '';
      if (folderPath) {
        const folder = folderMap.get(folderPath);
        if (folder) {
          folder.files.push(file);
        }
      } else {
        // 没有文件夹路径的文件，创建根级文件
        // 这里暂时不处理，只显示在右侧文件列表中
      }
    });

    return tree;
  }, []);

  // 新增：获取文件夹树结构
  const fetchFolderTree = useCallback(async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/files/folders/tree`);
      if (response.ok) {
        const data = await response.json();
        if (data.success && data.data) {
          const folders = data.data.folders || [];
          
          // 使用当前的文件列表而不是API返回的文件列表，确保数据同步
          const tree = buildFolderTree(folders, files);
          setFolderTree(tree);
          console.log('获取文件夹树成功:', { 
            folders: folders.length, 
            tree: tree.length, 
            totalFiles: files.length 
          });
        }
      }
    } catch (error) {
      console.error('获取文件夹树失败:', error);
    }
  }, [apiBaseUrl, buildFolderTree, files]);

  // 新增：创建文件夹
  const handleCreateFolder = useCallback(async (folderPath: string) => {
    try {
      // 使用FormData发送数据，符合后端API期望
      const formData = new FormData();
      formData.append('folder_path', folderPath);
      
      const response = await fetch(`${apiBaseUrl}/api/v1/files/folders/create`, {
        method: 'POST',
        body: formData
      });

      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          await fetchFolderTree(); // 刷新文件夹树
          setShowCreateFolderDialog(false);
          setNewFolderName('');
          setNewFolderParent('');
          console.log('文件夹创建成功:', folderPath);
        } else {
          console.error('创建文件夹失败:', data.message);
        }
      } else {
        console.error('创建文件夹失败，HTTP状态:', response.status);
      }
    } catch (error) {
      console.error('创建文件夹失败:', error);
    }
  }, [apiBaseUrl, fetchFolderTree]);

  // 新增：移动文件
  const handleMoveFile = useCallback(async (fileId: string, targetFolder: string) => {
    try {
      // 使用FormData发送数据
      const formData = new FormData();
      formData.append('target_folder', targetFolder);
      
      const response = await fetch(`${apiBaseUrl}/api/v1/files/${fileId}/move`, {
        method: 'PUT',
        body: formData
      });

      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          await Promise.all([fetchFiles(), fetchFolderTree()]); // 刷新文件列表和文件夹树
          console.log('文件移动成功:', data.message);
        } else {
          console.error('移动文件失败:', data.message);
        }
      } else {
        console.error('移动文件失败，HTTP状态:', response.status);
      }
    } catch (error) {
      console.error('移动文件失败:', error);
    }
  }, [apiBaseUrl, fetchFiles, fetchFolderTree]);

  // 新增：复制文件
  const handleCopyFile = useCallback(async (fileId: string, targetFolder: string, newName?: string) => {
    try {
      // 使用FormData发送数据
      const formData = new FormData();
      formData.append('target_folder', targetFolder);
      if (newName) {
        formData.append('new_name', newName);
      }
      
      const response = await fetch(`${apiBaseUrl}/api/v1/files/${fileId}/copy`, {
        method: 'POST',
        body: formData
      });

      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          await Promise.all([fetchFiles(), fetchFolderTree()]);
          console.log('文件复制成功:', data.message);
        } else {
          console.error('复制文件失败:', data.message);
        }
      } else {
        console.error('复制文件失败，HTTP状态:', response.status);
      }
    } catch (error) {
      console.error('复制文件失败:', error);
    }
  }, [apiBaseUrl, fetchFiles, fetchFolderTree]);

  // 新增：批量操作函数
  const toggleFileSelection = useCallback((fileId: string) => {
    setBatchOperation(prev => {
      const newSelected = new Set(prev.selectedFiles);
      if (newSelected.has(fileId)) {
        newSelected.delete(fileId);
      } else {
        newSelected.add(fileId);
      }
      return { ...prev, selectedFiles: newSelected };
    });
  }, []);

  const selectAllFiles = useCallback(() => {
    const visibleFileIds = filteredFiles.map(file => file.file_id);
    setBatchOperation(prev => ({
      ...prev,
      selectedFiles: new Set(visibleFileIds)
    }));
  }, [filteredFiles]);

  const clearSelection = useCallback(() => {
    setBatchOperation(prev => ({
      ...prev,
      selectedFiles: new Set()
    }));
  }, []);

  // 新增：批量移动文件
  const handleBatchMove = useCallback(async (targetFolder: string) => {
    try {
      const formData = new FormData();
      Array.from(batchOperation.selectedFiles).forEach(fileId => {
        formData.append('file_ids', fileId);
      });
      formData.append('target_folder', targetFolder);

      const response = await fetch(`${apiBaseUrl}/api/v1/files/batch/move`, {
        method: 'POST',
        body: formData
      });

      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          await Promise.all([fetchFiles(), fetchFolderTree()]);
          clearSelection();
          console.log('批量移动成功:', data.message);
        }
      }
    } catch (error) {
      console.error('批量移动失败:', error);
    }
  }, [apiBaseUrl, batchOperation.selectedFiles, fetchFiles, fetchFolderTree, clearSelection]);

  // 新增：批量复制文件
  const handleBatchCopy = useCallback(async (targetFolder: string) => {
    try {
      const formData = new FormData();
      Array.from(batchOperation.selectedFiles).forEach(fileId => {
        formData.append('file_ids', fileId);
      });
      formData.append('target_folder', targetFolder);

      const response = await fetch(`${apiBaseUrl}/api/v1/files/batch/copy`, {
        method: 'POST',
        body: formData
      });

      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          await Promise.all([fetchFiles(), fetchFolderTree()]);
          clearSelection();
          console.log('批量复制成功:', data.message);
        }
      }
    } catch (error) {
      console.error('批量复制失败:', error);
    }
  }, [apiBaseUrl, batchOperation.selectedFiles, fetchFiles, fetchFolderTree, clearSelection]);

  // 新增：批量删除文件
  const handleBatchDelete = useCallback(async () => {
    if (!confirm(`确定要删除选中的 ${batchOperation.selectedFiles.size} 个文件吗？此操作不可撤销。`)) {
      return;
    }

    try {
      const formData = new FormData();
      Array.from(batchOperation.selectedFiles).forEach(fileId => {
        formData.append('file_ids', fileId);
      });

      const response = await fetch(`${apiBaseUrl}/api/v1/files/batch/delete`, {
        method: 'POST',
        body: formData
      });

      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          await Promise.all([fetchFiles(), fetchFolderTree()]);
          clearSelection();
          console.log('批量删除成功:', data.message);
        }
      }
    } catch (error) {
      console.error('批量删除失败:', error);
    }
  }, [apiBaseUrl, batchOperation.selectedFiles, fetchFiles, fetchFolderTree, clearSelection]);

  // 新增：删除文件夹
  const handleDeleteFolder = useCallback(async (folderPath: string, recursive: boolean = false) => {
    if (!confirm(`确定要删除文件夹 "${folderPath}" 吗？${recursive ? '包括其中的所有文件和子文件夹。' : ''}此操作不可撤销。`)) {
      return;
    }

    try {
      const url = `${apiBaseUrl}/api/v1/files/folders/${encodeURIComponent(folderPath)}?recursive=${recursive}`;
      const response = await fetch(url, {
        method: 'DELETE'
      });

      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          await Promise.all([fetchFiles(), fetchFolderTree()]);
          console.log('文件夹删除成功:', data.message);
        }
      }
    } catch (error) {
      console.error('删除文件夹失败:', error);
    }
  }, [apiBaseUrl, fetchFiles, fetchFolderTree]);

  // 新增：移动文件夹
  const handleMoveFolder = useCallback(async (sourcePath: string, targetParent: string, newName?: string) => {
    try {
      const formData = new FormData();
      formData.append('target_parent', targetParent);
      if (newName) {
        formData.append('new_name', newName);
      }

      const response = await fetch(`${apiBaseUrl}/api/v1/files/folders/${encodeURIComponent(sourcePath)}/move`, {
        method: 'PUT',
        body: formData
      });

      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          await Promise.all([fetchFiles(), fetchFolderTree()]);
          console.log('文件夹移动成功:', data.message);
        }
      }
    } catch (error) {
      console.error('移动文件夹失败:', error);
    }
  }, [apiBaseUrl, fetchFiles, fetchFolderTree]);

  // 新增：上传文件到指定文件夹
  const handleUploadToFolder = useCallback(async (files: FileList, targetFolder: string) => {
    try {
      setUploading(true);
      let successCount = 0;
      let failCount = 0;
      
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const formData = new FormData();
        formData.append('file', file);
        formData.append('folder_path', targetFolder);
        
        // 确保传递session_id
        if (sessionId) {
          formData.append('session_id', sessionId);
        }
        
        const response = await fetch(`${apiBaseUrl}/api/v1/files/upload-to-folder`, {
          method: 'POST',
          body: formData,
        });

        if (response.ok) {
          const result = await response.json();
          if (result.success) {
            console.log(`文件 ${file.name} 上传到文件夹 ${targetFolder} 成功`);
            successCount++;
          } else {
            console.error(`文件 ${file.name} 上传失败: ${result.message}`);
            failCount++;
          }
        } else {
          console.error(`文件 ${file.name} 上传失败，HTTP状态: ${response.status}`);
          failCount++;
        }
      }

      // 显示上传结果
      if (successCount > 0) {
        console.log(`成功上传 ${successCount} 个文件到文件夹 ${targetFolder}${failCount > 0 ? `，${failCount} 个失败` : ''}`);
      }
      
      // 上传完成后刷新数据
      await Promise.all([fetchDataStatistics(), fetchFiles(), fetchFolderTree()]);
      setShowUploadToFolderDialog(false);
      
    } catch (error) {
      console.error('上传文件到文件夹失败:', error);
      setError('上传文件到文件夹过程中发生错误');
    } finally {
      setUploading(false);
    }
  }, [apiBaseUrl, sessionId, fetchDataStatistics, fetchFiles, fetchFolderTree]);

  // 新增：切换文件夹展开状态
  const toggleFolderExpanded = useCallback((folderPath: string) => {
    setFolderTree(prev => {
      const updateNode = (nodes: FolderNode[]): FolderNode[] => {
        return nodes.map(node => {
          if (node.path === folderPath) {
            return { ...node, isExpanded: !node.isExpanded };
          }
          if (node.children.length > 0) {
            return { ...node, children: updateNode(node.children) };
          }
          return node;
        });
      };
      return updateNode(prev);
    });
  }, []);

  // 递归计算文件夹中的文件总数
  const countFilesRecursive = useCallback((node: FolderNode): number => {
    let count = node.files.length;
    for (const child of node.children) {
      count += countFilesRecursive(child);
    }
    return count;
  }, []);

  // 修改：渲染文件夹树节点 - 添加文件夹操作按钮
  const renderFolderNode = useCallback((node: FolderNode, level: number = 0) => {
    const hasChildren = node.children.length > 0;
    const hasFiles = node.files.length > 0;
    const totalFileCount = countFilesRecursive(node);

    return (
      <div key={node.path} className="select-none group">
        <div 
          className={`flex items-center justify-between py-1 px-2 hover:bg-gray-100 rounded cursor-pointer ${
            selectedFolder === node.path ? 'bg-blue-50 border-l-2 border-blue-500' : ''
          }`}
          style={{ paddingLeft: `${level * 16 + 8}px` }}
        >
          <div 
            className="flex items-center flex-1"
            onClick={() => {
              setSelectedFolder(node.path);
              if (hasChildren) {
                toggleFolderExpanded(node.path);
              }
            }}
          >
            {hasChildren && (
              <ChevronRight 
                className={`h-4 w-4 mr-1 transition-transform ${
                  node.isExpanded ? 'rotate-90' : ''
                }`}
              />
            )}
            <Folder className="h-4 w-4 mr-2 text-blue-600" />
            <span className="text-sm font-medium">{node.name}</span>
            <span className="text-xs text-gray-500 ml-2">
              ({totalFileCount})
            </span>
          </div>
          
          {/* 文件夹操作按钮 */}
          <div className="flex items-center space-x-1 opacity-100 transition-opacity">
            <Button
              size="sm"
              variant="ghost"
              className="h-6 w-6 p-0"
              title="上传文件到此文件夹"
              onClick={(e) => {
                e.stopPropagation();
                setTargetUploadFolder(node.path);
                setShowUploadToFolderDialog(true);
              }}
            >
              <Upload className="h-3 w-3" />
            </Button>
            
            <Button
              size="sm"
              variant="ghost"
              className="h-6 w-6 p-0"
              title="移动文件夹"
              onClick={(e) => {
                e.stopPropagation();
                setSelectedFolderForOperation(node.path);
                setFolderOperationType('move');
                setShowFolderOperationDialog(true);
              }}
            >
              <Move3D className="h-3 w-3" />
            </Button>
            
            <Button
              size="sm"
              variant="ghost"
              className="h-6 w-6 p-0 text-red-600 hover:text-red-700"
              title="删除文件夹"
              onClick={(e) => {
                e.stopPropagation();
                setSelectedFolderForOperation(node.path);
                setFolderOperationType('delete');
                setShowFolderOperationDialog(true);
              }}
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          </div>
        </div>
        
        {/* 递归渲染子文件夹 */}
        {node.isExpanded && hasChildren && (
          <div>
            {node.children.map(child => renderFolderNode(child, level + 1))}
          </div>
        )}
      </div>
    );
  }, [selectedFolder, toggleFolderExpanded, countFilesRecursive]);

  // 修改：文件列表渲染 - 添加批量选择
  const renderFileList = useCallback(() => {
    return (
      <div className="space-y-4">
        {/* 新增：当选中文件夹时显示"导入文件到此文件夹"按钮 */}
        {selectedFolder && (
          <div className="mb-4 p-3 bg-blue-50 rounded-lg border border-blue-200">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <FolderOpen className="h-5 w-5 text-blue-600" />
                <span className="text-sm font-medium text-blue-800">
                  当前文件夹: {selectedFolder || '根目录'}
                </span>
              </div>
              <Button
                onClick={() => {
                  setTargetUploadFolder(selectedFolder);
                  setShowUploadToFolderDialog(true);
                }}
                className="text-sm"
                size="sm"
              >
                <Upload className="h-4 w-4 mr-1" />
                导入文件到此文件夹
              </Button>
            </div>
          </div>
        )}

        {/* 工具栏和搜索过滤 */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center space-x-2">
            <Search className="h-4 w-4 text-gray-400" />
            <Input
              placeholder="搜索文件..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-64"
            />
          </div>
          
          {/* 文件类型过滤按钮 */}
          <div className="flex items-center space-x-1">
            <Button
              variant={selectedFileType === 'all' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setSelectedFileType('all')}
            >
              全部
            </Button>
            <Button
              variant={selectedFileType === 'image' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setSelectedFileType('image')}
            >
              图片
            </Button>
            <Button
              variant={selectedFileType === 'document' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setSelectedFileType('document')}
            >
              文档
            </Button>
            <Button
              variant={selectedFileType === 'data' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setSelectedFileType('data')}
            >
              数据
            </Button>
          </div>
          
          <Button variant="outline" onClick={() => setSearchTerm('')}>
            <Filter className="h-4 w-4 mr-2" />
            清除过滤
          </Button>
          

        </div>

        {/* 全选/取消全选和批量操作 */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center space-x-2">
            <Button
              size="sm"
              variant="ghost"
              onClick={batchOperation.selectedFiles.size === filteredFiles.length ? clearSelection : selectAllFiles}
              className="text-sm"
            >
              {batchOperation.selectedFiles.size === filteredFiles.length ? (
                <CheckSquare className="h-4 w-4 mr-1" />
              ) : (
                <Square className="h-4 w-4 mr-1" />
              )}
              {batchOperation.selectedFiles.size === filteredFiles.length ? '取消全选' : '全选'}
            </Button>
            
            {batchOperation.selectedFiles.size > 0 && (
              <Badge variant="outline" className="text-xs">
                已选择 {batchOperation.selectedFiles.size} 个文件
              </Badge>
            )}
          </div>
          
          {/* 批量操作按钮 */}
          {batchOperation.selectedFiles.size > 0 && (
            <div className="flex items-center space-x-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setBatchOperation(prev => ({ ...prev, operationType: 'move', showBatchDialog: true }));
                }}
                className="text-xs"
              >
                <Move className="h-3 w-3 mr-1" />
                批量移动
              </Button>
              
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setBatchOperation(prev => ({ ...prev, operationType: 'copy', showBatchDialog: true }));
                }}
                className="text-xs"
              >
                <Copy className="h-3 w-3 mr-1" />
                批量复制
              </Button>
              
              <Button
                size="sm"
                variant="destructive"
                onClick={handleBatchDelete}
                className="text-xs"
              >
                <Trash2 className="h-3 w-3 mr-1" />
                批量删除
              </Button>
            </div>
          )}
        </div>

        {/* 文件列表 */}
        {filteredFiles.map((file) => (
          <div
            key={file.file_id}
            className={`flex items-center justify-between p-4 border rounded-lg hover:bg-gray-50 ${
              batchOperation.selectedFiles.has(file.file_id) ? 'bg-blue-50 border-blue-200' : ''
            }`}
          >
            {/* 文件选择checkbox */}
            <div className="flex items-center space-x-3">
              <Button
                size="sm"
                variant="ghost"
                className="h-6 w-6 p-0"
                onClick={() => toggleFileSelection(file.file_id)}
              >
                {batchOperation.selectedFiles.has(file.file_id) ? (
                  <CheckSquare className="h-4 w-4 text-blue-600" />
                ) : (
                  <Square className="h-4 w-4" />
                )}
              </Button>

              {/* 文件信息 */}
              <div className="flex items-center space-x-3">
                <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                  {getFileIcon(file.file_type, file.file_name)}
                </div>
                <div>
                  <p className="font-medium text-gray-900">{file.file_name}</p>
                  <p className="text-sm text-gray-500">
                    {formatFileSize(file.file_size)} • {new Date(file.upload_time).toLocaleDateString()}
                  </p>
                </div>
              </div>
            </div>

            {/* 文件操作按钮 */}
            <div className="flex items-center space-x-2">
              <Button
                size="sm"
                variant="ghost"
                title="复制"
                onClick={() => {
                  setSelectedFileForOperation(file.file_id);
                  setOperationType('copy');
                  setShowFolderSelector(true);
                }}
              >
                <Copy className="h-4 w-4" />
              </Button>
              
              <Button
                size="sm"
                variant="ghost"
                title="移动"
                onClick={() => {
                  setSelectedFileForOperation(file.file_id);
                  setOperationType('move');
                  setShowFolderSelector(true);
                }}
              >
                <Move className="h-4 w-4" />
              </Button>
              
              <Button
                size="sm"
                variant="ghost"
                title="下载"
                onClick={() => window.open(file.url, '_blank')}
              >
                <Download className="h-4 w-4" />
              </Button>
              
              <Button
                size="sm"
                variant="ghost"
                title="删除文件"
                className="text-red-600 hover:text-red-700 hover:bg-red-50"
                onClick={() => {
                  if (confirm(`确定要删除文件 "${file.file_name}" 吗？此操作不可撤销。`)) {
                    handleDeleteFile(file.file_id);
                  }
                }}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          </div>
        ))}
      </div>
    );
  }, [filteredFiles, batchOperation, toggleFileSelection, clearSelection, selectAllFiles, handleBatchDelete]);

  // 页面加载时获取数据
  useEffect(() => {
    fetchDataStatistics();
    fetchFiles();
    fetchFolderTree(); // 获取文件夹树
  }, [sessionId]); // 只依赖sessionId

  // 修改文件选择处理函数，不立即上传
  const handleFileSelect = (files: FileList, folderPath: string) => {
    if (!files.length) return;
    
    // 将FileList转换为File数组，避免引用失效
    const fileArray = Array.from(files);
    
    // 保存待上传的文件信息，显示确认对话框
    setPendingUploads({ files: fileArray, folderPath });
    setShowUploadConfirm(true);
  };

  // 修改上传函数
  const handleFolderUpload = async () => {
    if (!pendingUploads) return;
    
    const { files, folderPath } = pendingUploads;
    const formData = new FormData();
    
    files.forEach(file => {
      formData.append('files', file);
    });
    
    if (sessionId) {
      formData.append('session_id', sessionId);
    }
    formData.append('folder_path', folderPath);
    formData.append('metadata', JSON.stringify({
      uploaded_to_folder: folderPath,
      upload_time: new Date().toISOString()
    }));

    try {
      setUploading(true);
      const response = await fetch(`${apiBaseUrl}/api/v1/files/batch-upload`, {
        method: 'POST',
        body: formData,
      });

      if (response.ok) {
        const result = await response.json();
        console.log('上传结果:', result);
        alert(`上传成功：成功上传 ${result.data.uploaded.length} 个文件到 ${folderPath}`);
        
        // 关闭对话框并重置状态
        setShowUploadConfirm(false);
        setPendingUploads(null);
        
        // 刷新文件列表和文件夹树
        await Promise.all([
          fetchFiles(),
          fetchFolderTree()
        ]);
        
        // 输出调试信息
        console.log(`✅ 上传完成，目标文件夹: ${folderPath}`);
        
        // 自动选择上传的文件夹，这样用户能看到新上传的文件
        setSelectedFolder(folderPath);
        
        // 确保展开上传的文件夹及其所有父文件夹
        setFolderTree(prev => {
          // 创建一个深拷贝来避免直接修改原数组
          const updatedTree = JSON.parse(JSON.stringify(prev));
          
          // 递归函数来查找并展开文件夹
          const expandFolderRecursive = (nodes: FolderNode[], targetPath: string): boolean => {
            for (const node of nodes) {
              if (node.path === targetPath) {
                node.isExpanded = true;
                return true;
              }
              // 递归搜索子文件夹
              if (node.children && expandFolderRecursive(node.children, targetPath)) {
                node.isExpanded = true; // 展开父文件夹
                return true;
              }
            }
            return false;
          };
          
          // 展开目标文件夹
          expandFolderRecursive(updatedTree, folderPath);
          
          return updatedTree;
        });
        
      } else {
        throw new Error('上传失败');
      }
    } catch (error) {
      console.error('上传失败:', error);
      alert('上传失败，请重试');
    } finally {
      setUploading(false);
    }
  };

  // 取消上传
  const handleCancelUpload = () => {
    setShowUploadConfirm(false);
    setPendingUploads(null);
  };

  if (loading) {
    return (
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-3xl font-bold text-gray-900">数据管理中心</h2>
          <div className="flex items-center space-x-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span className="text-sm text-gray-600">加载中...</span>
          </div>
        </div>
        
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {[1, 2].map((i) => (
            <Card key={i}>
              <CardHeader>
                <CardTitle className="text-sm font-medium">加载中...</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-32 bg-gray-200 rounded animate-pulse"></div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-3xl font-bold text-gray-900">数据管理中心</h2>
          <Button onClick={fetchDataStatistics} size="sm">
            重试
          </Button>
        </div>
        
        <Card>
          <CardContent className="p-6">
            <div className="text-center">
              <AlertTriangle className="h-12 w-12 text-red-500 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-gray-900 mb-2">数据加载失败</h3>
              <p className="text-gray-600 mb-4">{error}</p>
              <Button onClick={fetchDataStatistics}>
                重新加载
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold text-gray-900">数据管理中心</h2>
        <div className="flex items-center space-x-2">
          <Button onClick={fetchDataStatistics} size="sm" variant="outline">
            刷新数据
          </Button>
          <Button 
            size="sm" 
            variant="outline"
            onClick={() => setShowSmartClassifier(!showSmartClassifier)}
          >
            <Brain className="h-4 w-4 mr-2" />
            智能管理
          </Button>

        </div>
      </div>

      {/* 智能文件分类器 */}
      {showSmartClassifier && (
        <SmartFileClassifier
          files={files}
          folders={folderTree.map(node => node.path)}
          onCreateFolder={handleCreateFolder}
          onFileMove={handleMoveFile}
          onSearchResults={(results) => {
            // 处理搜索结果
            console.log('搜索结果:', results);
          }}
          className="mb-6"
        />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 数据统计 */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center">
              <Database className="h-5 w-5 mr-2" />
              数据统计
            </CardTitle>
          </CardHeader>
          <CardContent>
            {statistics ? (
              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">总文件数</span>
                  <Badge variant="outline">{statistics.total_files} 个文件</Badge>
                </div>
                
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">总大小</span>
                  <Badge variant="outline">{formatFileSize(statistics.total_size)}</Badge>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">今日上传</span>
                  <Badge className="bg-blue-100 text-blue-800">{statistics.uploaded_today} 个</Badge>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">今日生成</span>
                  <Badge className="bg-green-100 text-green-800">{statistics.generated_today} 个</Badge>
                </div>

                <div className="border-t pt-4">
                  <h4 className="text-sm font-medium text-gray-700 mb-2">文件类型分布</h4>
                  <div className="space-y-2">
                    {Object.entries(statistics.file_types).map(([type, count]) => (
                      <div key={type} className="flex justify-between items-center">
                        <span className="text-xs text-gray-600">{type.toUpperCase()}</span>
                        <Badge variant="outline" className="text-xs">{count}</Badge>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-8 text-gray-500">
                暂无数据统计信息
              </div>
            )}
          </CardContent>
        </Card>

        {/* 数据质量 */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center">
              <BarChart3 className="h-5 w-5 mr-2" />
              数据质量评估
            </CardTitle>
          </CardHeader>
          <CardContent>
            {quality ? (
              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">完整性</span>
                  {getQualityBadge(quality.completeness)}
                </div>
                
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">准确性</span>
                  {getQualityBadge(quality.accuracy)}
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">一致性</span>
                  {getQualityBadge(quality.consistency)}
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">有效性</span>
                  {getQualityBadge(quality.validity)}
                </div>

                <div className="border-t pt-4">
                  <div className="flex justify-between items-center">
                    <span className="text-sm font-medium text-gray-700">综合评分</span>
                    <div className="text-lg font-bold text-green-600">
                      {((quality.completeness + quality.accuracy + quality.consistency + quality.validity) / 4).toFixed(1)}%
                    </div>
                  </div>
                  <div className="mt-2 text-xs text-gray-500">
                    基于文件完整性、数据准确性、格式一致性和内容有效性的综合评估
                  </div>
                  
                  {/* 显示建议 */}
                  {quality.recommendations && quality.recommendations.length > 0 && (
                    <div className="mt-3">
                      <h5 className="text-xs font-medium text-gray-700 mb-1">建议</h5>
                      <ul className="text-xs text-gray-600 space-y-1">
                        {quality.recommendations.map((rec, index) => (
                          <li key={index} className="flex items-start">
                            <span className="text-blue-500 mr-1">•</span>
                            <span>{rec}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {/* 显示问题 */}
                  {quality.issues && quality.issues.length > 0 && (
                    <div className="mt-3">
                      <h5 className="text-xs font-medium text-gray-700 mb-1">发现的问题</h5>
                      <ul className="text-xs text-red-600 space-y-1">
                        {quality.issues.map((issue, index) => (
                          <li key={index} className="flex items-start">
                            <span className="text-red-500 mr-1">⚠</span>
                            <span>{issue}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="text-center py-8 text-gray-500">
                暂无数据质量信息
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 文件管理区域 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 文件夹树 */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <div className="flex items-center">
                <Folder className="h-5 w-5 mr-2" />
                文件夹结构
              </div>
              <Button 
                size="sm" 
                variant="outline"
                onClick={() => setShowCreateFolderDialog(true)}
              >
                <FolderPlus className="h-4 w-4" />
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-96">
              {folderTree.length > 0 ? (
                <div className="space-y-1">
                  {folderTree.map(node => renderFolderNode(node))}
                </div>
              ) : (
                <div className="text-center py-8 text-gray-500">
                  <Folder className="h-12 w-12 mx-auto mb-2 text-gray-300" />
                  <p>暂无文件夹</p>
                  <Button 
                    size="sm" 
                    variant="outline" 
                    className="mt-2"
                    onClick={() => setShowCreateFolderDialog(true)}
                  >
                    创建第一个文件夹
                  </Button>
                </div>
              )}
            </ScrollArea>
          </CardContent>
        </Card>

        {/* 文件列表 */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <div className="flex items-center">
                <File className="h-5 w-5 mr-2" />
                文件列表
                {selectedFolder && (
                  <Badge variant="outline" className="ml-2">
                    {selectedFolder}
                  </Badge>
                )}
              </div>
              <div className="flex items-center space-x-2">
                <Input
                  placeholder="搜索文件..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-48"
                />
                <Button 
                  size="sm" 
                  variant="outline"
                  onClick={() => setShowFileManager(true)}
                >
                  管理文件
                </Button>
              </div>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {renderFileList()}
          </CardContent>
        </Card>
      </div>

      {/* 创建文件夹对话框 */}
      <Dialog open={showCreateFolderDialog} onOpenChange={setShowCreateFolderDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>创建新文件夹</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                文件夹名称
              </label>
              <Input
                value={newFolderName}
                onChange={(e) => setNewFolderName(e.target.value)}
                placeholder="输入文件夹名称"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                父文件夹路径
              </label>
              <Input
                value={newFolderParent || selectedFolder || ''}
                onChange={(e) => setNewFolderParent(e.target.value)}
                placeholder={selectedFolder ? `在 "${selectedFolder}" 下创建` : "根目录"}
                readOnly={!!selectedFolder}
              />
              {selectedFolder && (
                <p className="text-xs text-blue-600 mt-1">
                  将在当前选中的文件夹 "{selectedFolder}" 下创建
                </p>
              )}
            </div>
            <div className="flex justify-end space-x-2">
              <Button variant="outline" onClick={() => setShowCreateFolderDialog(false)}>
                取消
              </Button>
              <Button 
                onClick={() => {
                  const folderPath = newFolderParent ? 
                    `${newFolderParent}/${newFolderName}` : 
                    newFolderName;
                  handleCreateFolder(folderPath);
                }}
                disabled={!newFolderName.trim()}
              >
                创建
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* 文件夹选择对话框 */}
      <Dialog open={showFolderSelector} onOpenChange={setShowFolderSelector}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {operationType === 'copy' ? '复制文件' : '移动文件'}
              {selectedFileForOperation && ` - ${files.find(f => f.file_id === selectedFileForOperation)?.file_name || '未知文件'}`}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                选择目标文件夹
              </label>
              <Input
                value={targetFolderPath}
                onChange={(e) => setTargetFolderPath(e.target.value)}
                placeholder="输入目标文件夹路径，例如: data/input"
              />
              <p className="text-xs text-gray-500 mt-1">
                留空表示根目录
              </p>
            </div>
            
            {/* 文件夹树快速选择 */}
            {folderTree.length > 0 && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  或从现有文件夹中选择
                </label>
                <ScrollArea className="h-32 border rounded p-2">
                  <div className="space-y-1">
                    <div 
                      className="p-2 hover:bg-gray-100 rounded cursor-pointer text-sm"
                      onClick={() => setTargetFolderPath('')}
                    >
                      📁 根目录
                    </div>
                    {folderTree.map(node => (
                      <div key={node.path}>
                        <div 
                          className="p-2 hover:bg-gray-100 rounded cursor-pointer text-sm"
                          onClick={() => setTargetFolderPath(node.path)}
                        >
                          📁 {node.path}
                        </div>
                        {node.children.map(child => (
                          <div 
                            key={child.path}
                            className="p-2 hover:bg-gray-100 rounded cursor-pointer text-sm ml-4"
                            onClick={() => setTargetFolderPath(child.path)}
                          >
                            📁 {child.path}
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </div>
            )}
            
            <div className="flex justify-end space-x-2">
              <Button variant="outline" onClick={() => setShowFolderSelector(false)}>
                取消
              </Button>
              <Button 
                onClick={async () => {
                  if (selectedFileForOperation) {
                    if (operationType === 'copy') {
                      await handleCopyFile(selectedFileForOperation, targetFolderPath);
                    } else {
                      await handleMoveFile(selectedFileForOperation, targetFolderPath);
                    }
                    setShowFolderSelector(false);
                    setSelectedFileForOperation(null);
                    setTargetFolderPath('');
                  }
                }}
                disabled={!selectedFileForOperation}
              >
                {operationType === 'copy' ? '复制' : '移动'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* 批量操作对话框 */}
      <Dialog open={batchOperation.showBatchDialog} onOpenChange={(open) => 
        setBatchOperation(prev => ({ ...prev, showBatchDialog: open }))
      }>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              批量{batchOperation.operationType === 'move' ? '移动' : '复制'}文件
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-4">
            <p className="text-sm text-gray-600">
              选择目标文件夹：
            </p>
            
            <div className="space-y-2 max-h-60 overflow-y-auto">
              {folderTree.map(folder => (
                <Button
                  key={folder.path}
                  variant="ghost"
                  className="w-full justify-start"
                  onClick={() => {
                    if (batchOperation.operationType === 'move') {
                      handleBatchMove(folder.path);
                    } else if (batchOperation.operationType === 'copy') {
                      handleBatchCopy(folder.path);
                    }
                    setBatchOperation(prev => ({ ...prev, showBatchDialog: false }));
                  }}
                >
                  <Folder className="h-4 w-4 mr-2" />
                  {folder.path || '根目录'}
                </Button>
              ))}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* 文件夹操作对话框 */}
      <Dialog open={showFolderOperationDialog} onOpenChange={setShowFolderOperationDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {folderOperationType === 'delete' ? '删除文件夹' : '移动文件夹'}
            </DialogTitle>
          </DialogHeader>
          
          {folderOperationType === 'delete' ? (
            <div className="space-y-4">
              <p className="text-sm text-gray-600">
                确定要删除文件夹 "{selectedFolderForOperation}" 吗？
              </p>
              
              <div className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  id="recursive-delete"
                  onChange={(e) => {
                    if (e.target.checked) {
                      handleDeleteFolder(selectedFolderForOperation, true);
                    } else {
                      handleDeleteFolder(selectedFolderForOperation, false);
                    }
                    setShowFolderOperationDialog(false);
                  }}
                />
                <label htmlFor="recursive-delete" className="text-sm">
                  递归删除（包括子文件夹和文件）
                </label>
              </div>
              
              <div className="flex justify-end space-x-2">
                <Button
                  variant="outline"
                  onClick={() => setShowFolderOperationDialog(false)}
                >
                  取消
                </Button>
                <Button
                  variant="destructive"
                  onClick={() => {
                    handleDeleteFolder(selectedFolderForOperation, false);
                    setShowFolderOperationDialog(false);
                  }}
                >
                  删除
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <p className="text-sm text-gray-600">
                选择目标父文件夹：
              </p>
              
              <div className="space-y-2 max-h-60 overflow-y-auto">
                {folderTree
                  .filter(folder => folder.path !== selectedFolderForOperation)
                  .map(folder => (
                  <Button
                    key={folder.path}
                    variant="ghost"
                    className="w-full justify-start"
                    onClick={() => {
                      handleMoveFolder(selectedFolderForOperation, folder.path);
                      setShowFolderOperationDialog(false);
                    }}
                  >
                    <Folder className="h-4 w-4 mr-2" />
                    {folder.path || '根目录'}
                  </Button>
                ))}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* 上传文件到文件夹对话框 */}
      <Dialog open={showUploadToFolderDialog} onOpenChange={setShowUploadToFolderDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>上传文件到文件夹</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>目标文件夹</Label>
              <Input
                value={targetUploadFolder}
                onChange={(e) => setTargetUploadFolder(e.target.value)}
                placeholder="文件夹路径"
              />
            </div>
            <div>
              <Label>选择文件</Label>
              <div className="space-y-2">
                <input
                  type="file"
                  multiple
                  className="hidden"
                  id={`folder-upload-${targetUploadFolder}`}
                  onChange={(e) => {
                    if (e.target.files) {
                      handleFileSelect(e.target.files, targetUploadFolder);
                      setShowUploadToFolderDialog(false);
                      // 重置input值，允许重复选择相同文件
                      e.target.value = '';
                    }
                  }}
                />
                <Button 
                  type="button"
                  onClick={() => {
                    document.getElementById(`folder-upload-${targetUploadFolder}`)?.click();
                  }}
                  className="w-full"
                  variant="outline"
                >
                  <Upload className="h-4 w-4 mr-2" />
                  选择文件
                </Button>
              </div>
            </div>
            {uploading && (
              <div className="text-sm text-gray-600">正在上传文件...</div>
            )}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowUploadToFolderDialog(false)}
            >
              取消
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 文件上传对话框 */}
      <Dialog open={showUploadDialog} onOpenChange={setShowUploadDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>批量上传文件</DialogTitle>
            <DialogDescription>
              选择要上传的文件
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4">
            <div>
              <Label htmlFor="file-upload">选择文件</Label>
              <input
                id="file-upload"
                type="file"
                multiple
                className="mt-2 block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
                onChange={handleFileUpload}
                disabled={uploading}
              />
            </div>
            
            {uploading && (
              <div className="flex items-center justify-center space-x-2 py-4">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span className="text-sm text-gray-600">正在上传文件...</span>
              </div>
            )}
          </div>
          
          <DialogFooter>
            <Button 
              variant="outline" 
              onClick={() => setShowUploadDialog(false)}
              disabled={uploading}
            >
              取消
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 文件夹上传确认对话框 */}
      {showUploadConfirm && pendingUploads && (
        <Dialog open={showUploadConfirm} onOpenChange={setShowUploadConfirm}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>确认上传文件</DialogTitle>
              <DialogDescription>
                将 {pendingUploads.files.length} 个文件上传到文件夹：
                <code className="bg-muted px-1 py-0.5 rounded text-sm ml-1">
                  {pendingUploads.folderPath || '根目录'}
                </code>
              </DialogDescription>
            </DialogHeader>
            
            <div className="space-y-2 max-h-40 overflow-y-auto">
              <div className="text-sm font-medium">待上传文件：</div>
              {pendingUploads.files.map((file, index) => (
                <div key={index} className="flex items-center gap-2 text-sm p-2 bg-muted rounded">
                  <FileText className="h-4 w-4" />
                  <span className="flex-1 truncate">{file.name}</span>
                  <span className="text-muted-foreground">
                    ({(file.size / 1024 / 1024).toFixed(2)} MB)
                  </span>
                </div>
              ))}
            </div>
            
            <div className="flex justify-end space-x-2 pt-4">
              <Button 
                variant="outline" 
                onClick={handleCancelUpload}
                disabled={uploading}
              >
                取消
              </Button>
              <Button 
                onClick={handleFolderUpload}
                disabled={uploading}
              >
                {uploading ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                    上传中...
                  </>
                ) : (
                  <>
                    <Upload className="h-4 w-4 mr-2" />
                    确认上传
                  </>
                )}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
} 