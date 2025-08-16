"""
可视化API路由 - 阶段4多模态Streaming支持

提供DAG可视化、图表生成、文件预览等多模态内容API
"""

from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
import json
import logging
import io
import base64
from datetime import datetime

from ..dependencies import get_engine
from ..models import (
    APIResponse, DAGVisualization, DAGNode, DAGEdge,
    StreamResponse, MediaContent, MediaType
)
from ...core.engine import IsotopeEngine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/visualization", tags=["visualization"])

# ==================== 请求模型 ====================

class DAGVisualizationRequest(BaseModel):
    """DAG可视化请求"""
    session_id: Optional[str] = None
    format: str = "mermaid"  # mermaid, svg, png
    layout: str = "TB"  # Top-Bottom, Left-Right, etc.
    include_status: bool = True

class ChartGenerationRequest(BaseModel):
    """图表生成请求"""
    chart_type: str  # line, bar, pie, scatter, etc.
    data: Dict[str, Any]
    title: Optional[str] = None
    options: Optional[Dict[str, Any]] = None

# ==================== DAG可视化API ====================

@router.get("/dag/mermaid")
async def get_dag_mermaid(
    session_id: Optional[str] = Query(None, description="会话ID"),
    layout: str = Query("TB", description="布局方向"),
    include_status: bool = Query(True, description="包含状态信息"),
    engine: IsotopeEngine = Depends(get_engine)
):
    """获取DAG的Mermaid代码"""
    try:
        logger.info(f"获取DAG Mermaid代码，会话ID: {session_id}")
        
        # 获取当前工作流图
        if not hasattr(engine, 'workflow_graph') or not engine.workflow_graph:
            raise HTTPException(status_code=404, detail="工作流图不存在")
        
        try:
            graph_obj = engine.workflow_graph.get_graph()
            mermaid_code = graph_obj.draw_mermaid()
            
            # 增强Mermaid代码，添加样式和状态
            enhanced_mermaid = _enhance_mermaid_code(mermaid_code, include_status)
            
            return APIResponse(
                success=True,
                message="获取Mermaid代码成功",
                data={
                    "mermaid_code": enhanced_mermaid,
                    "layout": layout,
                    "timestamp": datetime.now().isoformat()
                }
            )
            
        except Exception as e:
            logger.error(f"生成Mermaid代码失败: {str(e)}")
            raise HTTPException(status_code=500, detail=f"生成Mermaid代码失败: {str(e)}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取DAG Mermaid代码失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取DAG可视化失败: {str(e)}")

@router.get("/dag/image")
async def get_dag_image(
    session_id: Optional[str] = Query(None, description="会话ID"),
    format: str = Query("svg", description="图片格式: svg, png"),
    engine: IsotopeEngine = Depends(get_engine)
):
    """获取DAG图像"""
    try:
        logger.info(f"获取DAG图像，格式: {format}，会话ID: {session_id}")
        
        # 生成图像
        image_data = engine.generate_graph_image()
        if not image_data:
            raise HTTPException(status_code=404, detail="无法生成图像")
        
        # 确定MIME类型
        if format.lower() == "svg":
            media_type = "image/svg+xml"
            if isinstance(image_data, str):
                content = image_data.encode('utf-8')
            else:
                content = image_data
        elif format.lower() == "png":
            media_type = "image/png"
            if isinstance(image_data, str):
                # 假设是base64编码
                content = base64.b64decode(image_data)
            else:
                content = image_data
        else:
            raise HTTPException(status_code=400, detail=f"不支持的格式: {format}")
        
        return Response(content=content, media_type=media_type)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取DAG图像失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取DAG图像失败: {str(e)}")

@router.get("/dag/structure")
async def get_dag_structure(
    session_id: Optional[str] = Query(None, description="会话ID"),
    engine: IsotopeEngine = Depends(get_engine)
):
    """获取DAG结构数据"""
    try:
        logger.info(f"获取DAG结构，会话ID: {session_id}")
        
        if not hasattr(engine, 'workflow_graph') or not engine.workflow_graph:
            raise HTTPException(status_code=404, detail="工作流图不存在")
        
        # 提取节点和边信息
        nodes = []
        edges = []
        
        # 这里需要根据实际的图结构来提取信息
        # 假设engine有方法获取图结构
        try:
            graph_obj = engine.workflow_graph.get_graph()
            
            # 构建节点信息
            for node_id in graph_obj.nodes:
                nodes.append(DAGNode(
                    id=node_id,
                    label=node_id,
                    type="agent" if "agent" in node_id.lower() else "supervisor",
                    status="active",  # 这里可以从会话状态获取
                    metadata={}
                ))
            
            # 构建边信息
            for edge in graph_obj.edges:
                if isinstance(edge, tuple) and len(edge) >= 2:
                    edges.append(DAGEdge(
                        from_node=edge[0],
                        to_node=edge[1],
                        label=edge[2] if len(edge) > 2 else None
                    ))
            
            dag_viz = DAGVisualization(
                nodes=nodes,
                edges=edges,
                layout="TB",
                metadata={
                    "session_id": session_id,
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            return APIResponse(
                success=True,
                message="获取DAG结构成功",
                data=dag_viz.dict()
            )
            
        except Exception as e:
            logger.error(f"提取DAG结构失败: {str(e)}")
            raise HTTPException(status_code=500, detail=f"提取DAG结构失败: {str(e)}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取DAG结构失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取DAG结构失败: {str(e)}")

# ==================== 多模态内容API ====================

@router.post("/stream/multimodal")
async def stream_multimodal_content(
    content: MediaContent,
    session_id: Optional[str] = None,
    engine: IsotopeEngine = Depends(get_engine)
):
    """流式发送多模态内容"""
    try:
        logger.info(f"流式发送多模态内容，类型: {content.type}")
        
        # 构建流式响应
        stream_data = {
            "type": "multimodal",
            "multimodal": {
                "type": content.type.value,
                "content": content.content,
                "metadata": content.metadata or {},
                "url": content.url
            },
            "session_id": session_id,
            "timestamp": datetime.now().isoformat()
        }
        
        # 如果有引擎的流写入器，使用它
        if hasattr(engine, 'get_stream_writer'):
            writer = engine.get_stream_writer()
            if writer:
                writer(stream_data)
        
        return StreamResponse(
            type="multimodal",
            data=stream_data
        )
        
    except Exception as e:
        logger.error(f"流式发送多模态内容失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"流式发送失败: {str(e)}")

@router.post("/chart/generate")
async def generate_chart(
    request: ChartGenerationRequest,
    session_id: Optional[str] = None
):
    """生成图表"""
    try:
        logger.info(f"生成图表，类型: {request.chart_type}")
        
        # 这里可以集成图表生成库（如matplotlib, plotly等）
        # 现在返回模拟数据
        chart_data = {
            "chart_type": request.chart_type,
            "data": request.data,
            "title": request.title or f"{request.chart_type}图表",
            "options": request.options or {},
            "generated_at": datetime.now().isoformat()
        }
        
        return APIResponse(
            success=True,
            message="图表生成成功",
            data={
                "chart": chart_data,
                "format": "json",
                "session_id": session_id
            }
        )
        
    except Exception as e:
        logger.error(f"生成图表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"生成图表失败: {str(e)}")

# ==================== 辅助函数 ====================

def _enhance_mermaid_code(mermaid_code: str, include_status: bool = True) -> str:
    """增强Mermaid代码，添加样式和状态"""
    lines = mermaid_code.split('\n')
    enhanced_lines = []
    
    for line in lines:
        enhanced_lines.append(line)
    
    # 添加样式定义
    if include_status:
        enhanced_lines.extend([
            "",
            "    %% 节点样式定义",
            "    classDef startEnd fill:#e1f5fe,stroke:#01579b,stroke-width:2px",
            "    classDef supervisor fill:#fff3e0,stroke:#ef6c00,stroke-width:2px", 
            "    classDef agent fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px",
            "    classDef critic fill:#e8f5e8,stroke:#2e7d32,stroke-width:2px",
            "    classDef tool fill:#fce4ec,stroke:#c2185b,stroke-width:2px",
            "",
            "    %% 应用样式",
            "    class START,END startEnd",
            "    class META,PLAN,RUNTIME supervisor", 
            "    class DATA,EXPERT agent",
            "    class CRITIC critic"
        ])
    
    return '\n'.join(enhanced_lines) 