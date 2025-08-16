"use client";

import React, { useEffect, useRef, useState } from 'react';
import { Button } from './ui/button';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';

interface DAGVisualizationProps {
  mermaidCode?: string;
  title?: string;
  className?: string;
  onRefresh?: () => void;
  onExport?: () => void;
}

export default function DAGVisualization({
  mermaidCode = "",
  title = "工作流图",
  className = "",
  onRefresh,
  onExport
}: DAGVisualizationProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mermaidInstance, setMermaidInstance] = useState<any>(null);

  // 默认示例Mermaid代码
  const defaultMermaidCode = `
graph TD
    START([开始]) --> META[MetaSupervisor]
    META --> PLAN[TaskPlanner]
    PLAN --> DATA[DataAgent]
    PLAN --> EXPERT[ExpertAgent]
    DATA --> CRITIC[Critic审查]
    EXPERT --> CRITIC
    CRITIC --> RUNTIME[RuntimeSupervisor]
    RUNTIME --> END([结束])
    
    classDef startEnd fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef supervisor fill:#fff3e0,stroke:#ef6c00,stroke-width:2px
    classDef agent fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    classDef critic fill:#e8f5e8,stroke:#2e7d32,stroke-width:2px
    
    class START,END startEnd
    class META,PLAN,RUNTIME supervisor
    class DATA,EXPERT agent
    class CRITIC critic
  `;

  // 初始化Mermaid
  useEffect(() => {
    const initMermaid = async () => {
      try {
        setIsLoading(true);
        setError(null);

        // 动态导入mermaid
        const { default: mermaid } = await import('mermaid');
        
        // 配置mermaid
        mermaid.initialize({
          startOnLoad: false,
          theme: 'default',
          securityLevel: 'loose',
          flowchart: {
            curve: 'linear',
            useMaxWidth: true,
            htmlLabels: true
          },
          themeVariables: {
            primaryColor: '#3b82f6',
            primaryTextColor: '#1f2937',
            primaryBorderColor: '#2563eb',
            lineColor: '#6b7280',
            secondaryColor: '#f3f4f6',
            tertiaryColor: '#fef3c7'
          }
        });

        setMermaidInstance(mermaid);
        setIsLoading(false);
      } catch (err) {
        console.error('初始化Mermaid失败:', err);
        setError('无法加载图表渲染器');
        setIsLoading(false);
      }
    };

    initMermaid();
  }, []);

  // 渲染图表
  useEffect(() => {
    if (!mermaidInstance || !containerRef.current) return;

    const renderChart = async () => {
      try {
        setError(null);
        const container = containerRef.current;
        if (!container) return;

        // 清空容器
        container.innerHTML = '';

        // 使用传入的mermaidCode或默认代码
        const codeToRender = mermaidCode.trim() || defaultMermaidCode;
        
        // 生成唯一ID
        const chartId = `mermaid-chart-${Date.now()}`;
        
        // 渲染图表
        const { svg, bindFunctions } = await mermaidInstance.render(chartId, codeToRender);
        
        // 插入SVG
        container.innerHTML = svg;
        
        // 绑定交互函数（如果有）
        if (bindFunctions) {
          bindFunctions(container);
        }

        // 添加响应式样式
        const svgElement = container.querySelector('svg');
        if (svgElement) {
          svgElement.style.maxWidth = '100%';
          svgElement.style.height = 'auto';
        }

      } catch (err) {
        console.error('渲染图表失败:', err);
        const errorMessage = err instanceof Error ? err.message : '未知错误';
        setError('图表渲染失败');
        
        // 显示错误信息
        if (containerRef.current) {
          containerRef.current.innerHTML = `
            <div class="flex items-center justify-center h-64 text-red-500">
              <div class="text-center">
                <div class="text-lg font-semibold">图表渲染失败</div>
                <div class="text-sm mt-2">${errorMessage}</div>
              </div>
            </div>
          `;
        }
      }
    };

    renderChart();
  }, [mermaidInstance, mermaidCode]);

  const handleExportSVG = () => {
    const svgElement = containerRef.current?.querySelector('svg');
    if (svgElement) {
      const svgData = new XMLSerializer().serializeToString(svgElement);
      const blob = new Blob([svgData], { type: 'image/svg+xml' });
      const url = URL.createObjectURL(blob);
      
      const link = document.createElement('a');
      link.href = url;
      link.download = `${title}-workflow.svg`;
      link.click();
      
      URL.revokeObjectURL(url);
    }
  };

  const handleExportPNG = async () => {
    const svgElement = containerRef.current?.querySelector('svg');
    if (svgElement) {
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      const img = new Image();
      
      const svgData = new XMLSerializer().serializeToString(svgElement);
      const blob = new Blob([svgData], { type: 'image/svg+xml' });
      const url = URL.createObjectURL(blob);
      
      img.onload = () => {
        canvas.width = img.width;
        canvas.height = img.height;
        ctx?.drawImage(img, 0, 0);
        
        canvas.toBlob((blob) => {
          if (blob) {
            const pngUrl = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = pngUrl;
            link.download = `${title}-workflow.png`;
            link.click();
            URL.revokeObjectURL(pngUrl);
          }
        });
        
        URL.revokeObjectURL(url);
      };
      
      img.src = url;
    }
  };

  return (
    <Card className={className}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
        <CardTitle className="text-lg font-semibold">{title}</CardTitle>
        <div className="flex gap-2">
          {onRefresh && (
            <Button
              variant="outline"
              size="sm"
              onClick={onRefresh}
              disabled={isLoading}
            >
              🔄 刷新
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={handleExportSVG}
            disabled={isLoading || !!error}
          >
            📄 导出SVG
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleExportPNG}
            disabled={isLoading || !!error}
          >
            🖼️ 导出PNG
          </Button>
          {onExport && (
            <Button
              variant="outline"
              size="sm"
              onClick={onExport}
              disabled={isLoading || !!error}
            >
              💾 导出
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto"></div>
              <div className="mt-2 text-sm text-gray-500">加载图表渲染器...</div>
            </div>
          </div>
        )}
        
        {error && (
          <div className="flex items-center justify-center h-64 text-red-500">
            <div className="text-center">
              <div className="text-lg font-semibold">渲染错误</div>
              <div className="text-sm mt-2">{error}</div>
            </div>
          </div>
        )}
        
        <div
          ref={containerRef}
          className="mermaid-container w-full min-h-64"
          style={{ display: isLoading || error ? 'none' : 'block' }}
        />
        
        {!isLoading && !error && mermaidCode && (
          <div className="mt-4 p-3 bg-gray-50 rounded">
            <details>
              <summary className="cursor-pointer text-sm font-medium text-gray-700">
                查看Mermaid代码
              </summary>
              <pre className="mt-2 text-xs text-gray-600 overflow-x-auto">
                {mermaidCode || defaultMermaidCode}
              </pre>
            </details>
          </div>
        )}
      </CardContent>
    </Card>
  );
} 