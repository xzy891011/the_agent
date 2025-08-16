"use client";

import React, { useState, useCallback } from 'react';
import { ChevronRight, ChevronDown, Folder, FolderOpen, File } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from './button';
import { Checkbox } from './checkbox';

export interface TreeNode {
  id: string;
  name: string;
  type: 'folder' | 'file';
  path: string;
  children?: TreeNode[];
  metadata?: any;
  fileData?: any; // 文件的完整数据
}

interface TreeViewProps {
  data: TreeNode[];
  selectedItems?: Set<string>;
  onItemSelect?: (id: string, isSelected: boolean) => void;
  onItemClick?: (node: TreeNode) => void;
  className?: string;
  showCheckboxes?: boolean;
  expandedFolders?: Set<string>;
  onFolderToggle?: (folderId: string, isExpanded: boolean) => void;
}

interface TreeItemProps {
  node: TreeNode;
  level: number;
  selectedItems?: Set<string>;
  onItemSelect?: (id: string, isSelected: boolean) => void;
  onItemClick?: (node: TreeNode) => void;
  showCheckboxes?: boolean;
  expandedFolders?: Set<string>;
  onFolderToggle?: (folderId: string, isExpanded: boolean) => void;
}

export function TreeItem({
  node,
  level,
  selectedItems,
  onItemSelect,
  onItemClick,
  showCheckboxes = false,
  expandedFolders,
  onFolderToggle
}: TreeItemProps) {
  const isFolder = node.type === 'folder';
  const isExpanded = expandedFolders?.has(node.id) ?? false;
  const isSelected = selectedItems?.has(node.id) ?? false;
  const hasChildren = node.children && node.children.length > 0;

  const handleToggle = useCallback(() => {
    if (isFolder && onFolderToggle) {
      onFolderToggle(node.id, !isExpanded);
    }
  }, [isFolder, onFolderToggle, node.id, isExpanded]);

  const handleSelect = useCallback((checked: boolean) => {
    if (onItemSelect) {
      onItemSelect(node.id, checked);
    }
  }, [onItemSelect, node.id]);

  const handleItemClick = useCallback(() => {
    if (onItemClick) {
      onItemClick(node);
    }
  }, [onItemClick, node]);

  return (
    <div className="select-none">
      <div
        className={cn(
          "flex items-center space-x-2 py-1 px-2 rounded-sm cursor-pointer hover:bg-gray-100 transition-colors",
          isSelected && "bg-blue-50 border border-blue-200",
          level > 0 && "ml-4"
        )}
        style={{ paddingLeft: `${level * 16 + 8}px` }}
        onClick={handleItemClick}
      >
        {/* 展开/折叠图标 */}
        {isFolder && (
          <Button
            variant="ghost"
            size="sm"
            className="h-4 w-4 p-0 hover:bg-gray-200"
            onClick={(e) => {
              e.stopPropagation();
              handleToggle();
            }}
          >
            {hasChildren ? (
              isExpanded ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )
            ) : (
              <div className="h-3 w-3" /> // 占位符，保持对齐
            )}
          </Button>
        )}

        {/* 选择框 */}
        {showCheckboxes && (
          <Checkbox
            checked={isSelected}
            onCheckedChange={handleSelect}
            onClick={(e) => e.stopPropagation()}
          />
        )}

        {/* 文件/文件夹图标 */}
        <div className="flex-shrink-0">
          {isFolder ? (
            isExpanded ? (
              <FolderOpen className="h-4 w-4 text-blue-500" />
            ) : (
              <Folder className="h-4 w-4 text-blue-500" />
            )
          ) : (
            <File className="h-4 w-4 text-gray-500" />
          )}
        </div>

        {/* 文件/文件夹名称 */}
        <span
          className={cn(
            "flex-1 text-sm truncate",
            isFolder ? "font-medium text-gray-700" : "text-gray-600"
          )}
          title={node.name}
        >
          {node.name}
        </span>

        {/* 文件数量（仅文件夹） */}
        {isFolder && hasChildren && (
          <span className="text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">
            {node.children?.length || 0}
          </span>
        )}
      </div>

      {/* 子节点 */}
      {isFolder && isExpanded && hasChildren && (
        <div className="ml-2">
          {node.children?.map((child) => (
            <TreeItem
              key={child.id}
              node={child}
              level={level + 1}
              selectedItems={selectedItems}
              onItemSelect={onItemSelect}
              onItemClick={onItemClick}
              showCheckboxes={showCheckboxes}
              expandedFolders={expandedFolders}
              onFolderToggle={onFolderToggle}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function TreeView({
  data,
  selectedItems,
  onItemSelect,
  onItemClick,
  className,
  showCheckboxes = false,
  expandedFolders,
  onFolderToggle
}: TreeViewProps) {
  return (
    <div className={cn("space-y-1", className)}>
      {data.map((node) => (
        <TreeItem
          key={node.id}
          node={node}
          level={0}
          selectedItems={selectedItems}
          onItemSelect={onItemSelect}
          onItemClick={onItemClick}
          showCheckboxes={showCheckboxes}
          expandedFolders={expandedFolders}
          onFolderToggle={onFolderToggle}
        />
      ))}
    </div>
  );
}

// 工具函数：将扁平的文件列表转换为树形结构
export function buildFileTree(files: any[], folders: string[] = []): TreeNode[] {
  const tree: TreeNode[] = [];
  const folderMap: Map<string, TreeNode> = new Map();

  // 首先创建所有文件夹节点
  folders.forEach(folderPath => {
    const parts = folderPath.split('/').filter(part => part.length > 0);
    let currentPath = '';
    
    parts.forEach((part, index) => {
      const parentPath = currentPath;
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      
      if (!folderMap.has(currentPath)) {
        const folderNode: TreeNode = {
          id: `folder-${currentPath}`,
          name: part,
          type: 'folder',
          path: currentPath,
          children: []
        };
        
        folderMap.set(currentPath, folderNode);
        
        // 添加到父文件夹或根目录
        if (parentPath) {
          const parent = folderMap.get(parentPath);
          if (parent && parent.children) {
            parent.children.push(folderNode);
          }
        } else {
          tree.push(folderNode);
        }
      }
    });
  });

  // 然后添加文件
  files.forEach(file => {
    const filePath = file.file_path || '';
    const fileName = file.file_name || 'unknown';
    
    const fileNode: TreeNode = {
      id: file.file_id || `file-${fileName}`,
      name: fileName,
      type: 'file',
      path: filePath ? `${filePath}/${fileName}` : fileName,
      fileData: file,
      metadata: file.metadata
    };

    // 如果文件有路径，找到对应的文件夹
    if (filePath) {
      const folder = folderMap.get(filePath);
      if (folder && folder.children) {
        folder.children.push(fileNode);
      } else {
        // 如果文件夹不存在，添加到根目录
        tree.push(fileNode);
      }
    } else {
      // 没有路径的文件添加到根目录
      tree.push(fileNode);
    }
  });

  return tree;
}

// 工具函数：从树中提取所有选中的文件
export function getSelectedFiles(tree: TreeNode[], selectedIds: Set<string>): any[] {
  const selectedFiles: any[] = [];
  
  function traverse(nodes: TreeNode[]) {
    nodes.forEach(node => {
      if (node.type === 'file' && selectedIds.has(node.id) && node.fileData) {
        selectedFiles.push(node.fileData);
      }
      if (node.children) {
        traverse(node.children);
      }
    });
  }
  
  traverse(tree);
  return selectedFiles;
} 