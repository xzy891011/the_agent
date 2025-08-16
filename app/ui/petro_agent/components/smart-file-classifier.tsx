"use client";

import React, { useState, useCallback, useMemo } from 'react';
import { useChat } from '@ai-sdk/react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Badge } from './ui/badge';
import { ScrollArea } from './ui/scroll-area';
import { 
  Search, 
  FolderPlus, 
  Wand2, 
  FileText, 
  Tags, 
  Brain,
  Lightbulb,
  Filter,
  SortAsc
} from 'lucide-react';

interface SmartFileClassifierProps {
  files: any[];
  folders: string[];
  onCreateFolder?: (folderPath: string) => void;
  onFileMove?: (fileId: string, targetFolder: string) => void;
  onSearchResults?: (results: any[]) => void;
  className?: string;
}

interface ClassificationSuggestion {
  category: string;
  folderPath: string;
  reason: string;
  confidence: number;
  files: any[];
}

interface FolderSuggestion {
  name: string;
  path: string;
  purpose: string;
  expectedFiles: string[];
}

export function SmartFileClassifier({
  files,
  folders,
  onCreateFolder,
  onFileMove,
  onSearchResults,
  className
}: SmartFileClassifierProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [classifications, setClassifications] = useState<ClassificationSuggestion[]>([]);
  const [folderSuggestions, setFolderSuggestions] = useState<FolderSuggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);

  // 使用AI SDK进行智能分析
  const { messages, append, isLoading } = useChat({
    api: '/api/chat',
    body: {
      mode: 'file_analysis'
    }
  });

  // 智能文件搜索
  const searchResults = useMemo(() => {
    if (!searchQuery.trim()) return files;
    
    const query = searchQuery.toLowerCase();
    return files.filter(file => {
      // 基础文件名匹配
      if (file.file_name.toLowerCase().includes(query)) return true;
      
      // 文件类型匹配
      if (file.file_type && file.file_type.toLowerCase().includes(query)) return true;
      
      // 元数据匹配
      if (file.metadata) {
        const metadataStr = JSON.stringify(file.metadata).toLowerCase();
        if (metadataStr.includes(query)) return true;
      }
      
      // 智能语义匹配（简化版）
      const semanticKeywords = {
        '测井': ['las', 'log', 'well'],
        '同位素': ['isotope', 'carbon', 'c13'],
        '图表': ['chart', 'plot', 'png', 'jpg'],
        '数据': ['csv', 'xlsx', 'data'],
        '报告': ['report', 'analysis', 'doc'],
        '模型': ['model', '3d', 'geological']
      };
      
      for (const [chinese, keywords] of Object.entries(semanticKeywords)) {
        if (query.includes(chinese)) {
          return keywords.some(keyword => 
            file.file_name.toLowerCase().includes(keyword) ||
            (file.metadata && JSON.stringify(file.metadata).toLowerCase().includes(keyword))
          );
        }
      }
      
      return false;
    });
  }, [files, searchQuery]);

  // AI智能分类分析
  const analyzeFiles = useCallback(async () => {
    if (files.length === 0) return;
    
    setIsAnalyzing(true);
    try {
      // 构建文件摘要信息
      const fileSummary = files.map(file => ({
        name: file.file_name,
        type: file.file_type,
        size: file.file_size,
        metadata: file.metadata,
        isGenerated: file.is_generated
      }));

      const prompt = `分析以下文件列表，提供智能分类建议和文件夹结构建议：

文件列表：
${JSON.stringify(fileSummary, null, 2)}

现有文件夹：
${folders.join(', ')}

请提供：
1. 文件分类建议（按类型、用途、项目阶段等）
2. 推荐的文件夹结构
3. 每个分类的命名建议和理由

回复格式为JSON：
{
  "classifications": [
    {
      "category": "分类名称",
      "folderPath": "建议文件夹路径",
      "reason": "分类理由",
      "confidence": 0.95,
      "fileNames": ["文件名1", "文件名2"]
    }
  ],
  "folderSuggestions": [
    {
      "name": "文件夹名称",
      "path": "完整路径",
      "purpose": "用途说明",
      "expectedFiles": ["预期文件类型"]
    }
  ]
}`;

      // 直接调用文件分析API
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          messages: [{ role: 'user', content: prompt }],
          mode: 'file_analysis'
        })
      });

      if (!response.ok) {
        throw new Error('AI分析请求失败');
      }

      const analysisResult = await response.json();
      
      if (analysisResult.success && analysisResult.analysis) {
        const analysis = analysisResult.analysis;
        
        // 转换分析结果为组件需要的格式
        const aiClassifications: ClassificationSuggestion[] = analysis.classifications.map((item: any) => ({
          category: item.category,
          folderPath: item.folderPath,
          reason: item.reason,
          confidence: item.confidence,
          files: files.filter(f => item.fileNames.includes(f.file_name))
        }));

        const aiFolderSuggestions: FolderSuggestion[] = analysis.folderSuggestions;

        setClassifications(aiClassifications);
        setFolderSuggestions(aiFolderSuggestions);
        setShowSuggestions(true);
        return;
      }
      
      // 如果AI分析失败，使用备用的本地分析
      const mockClassifications: ClassificationSuggestion[] = [
        {
          category: '测井数据',
          folderPath: 'input/logs',
          reason: '包含LAS格式的测井曲线文件',
          confidence: 0.95,
          files: files.filter(f => f.file_name.toLowerCase().includes('.las'))
        },
        {
          category: '同位素分析图表',
          folderPath: 'generated/isotope_charts',
          reason: '系统生成的同位素分析图表',
          confidence: 0.90,
          files: files.filter(f => f.is_generated && f.metadata?.analysis_type?.includes('isotope'))
        },
        {
          category: '原始数据',
          folderPath: 'input/data',
          reason: '包含CSV、Excel等原始数据文件',
          confidence: 0.85,
          files: files.filter(f => ['csv', 'xlsx', 'xls'].some(ext => f.file_name.toLowerCase().endsWith(ext)))
        }
      ];

      const mockFolderSuggestions: FolderSuggestion[] = [
        {
          name: '项目文档',
          path: 'input/documents',
          purpose: '存放项目相关的文档、报告、说明文件',
          expectedFiles: ['PDF文档', 'Word文档', '项目说明']
        },
        {
          name: '三维模型',
          path: 'generated/3d_models',
          purpose: '存放生成的三维地质模型文件',
          expectedFiles: ['模型文件', '渲染结果', '参数文件']
        },
        {
          name: '质控文件',
          path: 'qc/validation',
          purpose: '存放数据质控、验证相关的文件',
          expectedFiles: ['质控报告', '验证数据', '检查结果']
        }
      ];

      setClassifications(mockClassifications);
      setFolderSuggestions(mockFolderSuggestions);
      setShowSuggestions(true);

    } catch (error) {
      console.error('AI分析失败:', error);
    } finally {
      setIsAnalyzing(false);
    }
  }, [files, folders, append]);

  // 应用分类建议
  const applyClassification = useCallback((suggestion: ClassificationSuggestion) => {
    // 如果文件夹不存在，先创建
    if (onCreateFolder && !folders.includes(suggestion.folderPath)) {
      onCreateFolder(suggestion.folderPath);
    }

    // 移动文件到建议的文件夹
    if (onFileMove) {
      suggestion.files.forEach(file => {
        onFileMove(file.file_id, suggestion.folderPath);
      });
    }
  }, [folders, onCreateFolder, onFileMove]);

  // 创建建议的文件夹
  const createSuggestedFolder = useCallback((suggestion: FolderSuggestion) => {
    if (onCreateFolder) {
      onCreateFolder(suggestion.path);
    }
  }, [onCreateFolder]);

  // 通知搜索结果
  React.useEffect(() => {
    if (onSearchResults) {
      onSearchResults(searchResults);
    }
  }, [searchResults, onSearchResults]);

  return (
    <div className={className}>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center space-x-2">
            <Brain className="h-5 w-5" />
            <span>智能文件管理</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* 智能搜索 */}
          <div className="space-y-2">
            <div className="flex items-center space-x-2">
              <Search className="h-4 w-4 text-gray-500" />
              <Input
                placeholder="智能搜索文件... (支持文件名、类型、语义搜索)"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="flex-1"
              />
            </div>
            {searchQuery && (
              <div className="text-sm text-gray-600">
                找到 {searchResults.length} 个匹配的文件
              </div>
            )}
          </div>

          {/* AI分析按钮 */}
          <div className="flex space-x-2">
            <Button
              onClick={analyzeFiles}
              disabled={isAnalyzing || files.length === 0}
              className="flex items-center space-x-2"
            >
              <Wand2 className="h-4 w-4" />
              <span>{isAnalyzing ? 'AI分析中...' : 'AI智能分类'}</span>
            </Button>
            
            <Button
              variant="outline"
              onClick={() => setShowSuggestions(!showSuggestions)}
              disabled={classifications.length === 0 && folderSuggestions.length === 0}
            >
              <Lightbulb className="h-4 w-4 mr-2" />
              查看建议
            </Button>
          </div>

          {/* 分类建议 */}
          {showSuggestions && (
            <div className="space-y-4">
              {classifications.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-gray-700 mb-2 flex items-center">
                    <Tags className="h-4 w-4 mr-2" />
                    文件分类建议
                  </h4>
                  <ScrollArea className="h-40">
                    <div className="space-y-2">
                      {classifications.map((suggestion, index) => (
                        <div key={index} className="border rounded-lg p-3 space-y-2">
                          <div className="flex items-center justify-between">
                            <div>
                              <div className="font-medium text-sm">{suggestion.category}</div>
                              <div className="text-xs text-gray-500">{suggestion.folderPath}</div>
                            </div>
                            <div className="flex items-center space-x-2">
                              <Badge variant="secondary">
                                {Math.round(suggestion.confidence * 100)}%
                              </Badge>
                              <Button
                                size="sm"
                                onClick={() => applyClassification(suggestion)}
                              >
                                应用
                              </Button>
                            </div>
                          </div>
                          <div className="text-xs text-gray-600">{suggestion.reason}</div>
                          <div className="text-xs">
                            <span className="text-gray-500">包含文件: </span>
                            <span>{suggestion.files.length} 个</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                </div>
              )}

              {folderSuggestions.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-gray-700 mb-2 flex items-center">
                    <FolderPlus className="h-4 w-4 mr-2" />
                    文件夹结构建议
                  </h4>
                  <ScrollArea className="h-40">
                    <div className="space-y-2">
                      {folderSuggestions.map((suggestion, index) => (
                        <div key={index} className="border rounded-lg p-3 space-y-2">
                          <div className="flex items-center justify-between">
                            <div>
                              <div className="font-medium text-sm">{suggestion.name}</div>
                              <div className="text-xs text-gray-500">{suggestion.path}</div>
                            </div>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => createSuggestedFolder(suggestion)}
                              disabled={folders.includes(suggestion.path)}
                            >
                              {folders.includes(suggestion.path) ? '已存在' : '创建'}
                            </Button>
                          </div>
                          <div className="text-xs text-gray-600">{suggestion.purpose}</div>
                          <div className="text-xs">
                            <span className="text-gray-500">适用于: </span>
                            <span>{suggestion.expectedFiles.join(', ')}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                </div>
              )}
            </div>
          )}

          {/* 统计信息 */}
          <div className="grid grid-cols-2 gap-4 pt-2 border-t text-xs text-gray-600">
            <div>
              <span className="font-medium">总文件数: </span>
              <span>{files.length}</span>
            </div>
            <div>
              <span className="font-medium">文件夹数: </span>
              <span>{folders.length}</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
} 