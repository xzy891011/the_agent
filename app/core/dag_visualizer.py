"""
DAG可视化模块 - 阶段1增强实现

该模块提供工作流图的可视化功能，包括：
1. Mermaid图表生成
2. 交互式HTML可视化
3. 节点状态实时更新
4. 子图并行度展示
5. 执行进度跟踪
"""

import logging
import json
import base64
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

class NodeStatus(str, Enum):
    """节点状态枚举"""
    PENDING = "pending"      # 等待执行
    RUNNING = "running"      # 正在执行
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 失败
    SKIPPED = "skipped"      # 跳过

class NodeType(str, Enum):
    """节点类型枚举"""
    SUPERVISOR = "supervisor"       # 监督节点
    AGENT = "agent"                # 智能体节点
    CRITIC = "critic"              # 审查节点
    PLANNER = "planner"            # 规划节点
    TOOL = "tool"                  # 工具节点
    SUBGRAPH = "subgraph"          # 子图节点

class DAGNode:
    """DAG节点类"""
    
    def __init__(
        self,
        node_id: str,
        node_type: NodeType,
        label: str,
        status: NodeStatus = NodeStatus.PENDING,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.node_id = node_id
        self.node_type = node_type
        self.label = label
        self.status = status
        self.metadata = metadata or {}
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.execution_time: Optional[float] = None
        self.error: Optional[str] = None
        
    def start_execution(self):
        """开始执行"""
        self.status = NodeStatus.RUNNING
        self.start_time = datetime.now()
        
    def complete_execution(self, success: bool = True, error: Optional[str] = None):
        """完成执行"""
        self.end_time = datetime.now()
        if self.start_time:
            self.execution_time = (self.end_time - self.start_time).total_seconds()
        
        if success:
            self.status = NodeStatus.COMPLETED
        else:
            self.status = NodeStatus.FAILED
            self.error = error
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "label": self.label,
            "status": self.status.value,
            "metadata": self.metadata,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "execution_time": self.execution_time,
            "error": self.error
        }

class DAGVisualizer:
    """DAG可视化器
    
    提供工作流图的多种可视化形式，支持实时状态更新
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化可视化器
        
        Args:
            config: 配置参数
        """
        self.config = config or {}
        self.nodes: Dict[str, DAGNode] = {}
        self.edges: List[Tuple[str, str]] = []
        self.conditional_edges: Dict[str, Dict[str, str]] = {}
        self.subgraphs: Dict[str, List[str]] = {}
        
        # 样式配置
        self.node_styles = {
            NodeType.SUPERVISOR: {"color": "#ff6b6b", "shape": "diamond"},
            NodeType.AGENT: {"color": "#4ecdc4", "shape": "rect"},
            NodeType.CRITIC: {"color": "#ffe66d", "shape": "hexagon"},
            NodeType.PLANNER: {"color": "#95e1d3", "shape": "rect"},
            NodeType.TOOL: {"color": "#a8e6cf", "shape": "circle"},
            NodeType.SUBGRAPH: {"color": "#dda0dd", "shape": "rect"}
        }
        
        self.status_styles = {
            NodeStatus.PENDING: {"fill": "#f8f9fa", "stroke": "#dee2e6"},
            NodeStatus.RUNNING: {"fill": "#fff3cd", "stroke": "#ffc107"},
            NodeStatus.COMPLETED: {"fill": "#d1edff", "stroke": "#0066cc"},
            NodeStatus.FAILED: {"fill": "#f8d7da", "stroke": "#dc3545"},
            NodeStatus.SKIPPED: {"fill": "#e2e3e5", "stroke": "#6c757d"}
        }
        
        logger.info("DAG可视化器已初始化")
    
    def add_node(
        self,
        node_id: str,
        node_type: NodeType,
        label: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> DAGNode:
        """添加节点
        
        Args:
            node_id: 节点ID
            node_type: 节点类型
            label: 节点标签
            metadata: 节点元数据
            
        Returns:
            DAGNode: 创建的节点
        """
        node = DAGNode(node_id, node_type, label, metadata=metadata)
        self.nodes[node_id] = node
        logger.debug(f"添加节点: {node_id} ({node_type.value})")
        return node
    
    def add_edge(self, from_node: str, to_node: str):
        """添加边
        
        Args:
            from_node: 起始节点
            to_node: 目标节点
        """
        self.edges.append((from_node, to_node))
        logger.debug(f"添加边: {from_node} -> {to_node}")
    
    def add_conditional_edge(self, from_node: str, conditions: Dict[str, str]):
        """添加条件边
        
        Args:
            from_node: 起始节点
            conditions: 条件映射 {条件: 目标节点}
        """
        self.conditional_edges[from_node] = conditions
        logger.debug(f"添加条件边: {from_node} -> {conditions}")
    
    def add_subgraph(self, subgraph_name: str, node_ids: List[str]):
        """添加子图
        
        Args:
            subgraph_name: 子图名称
            node_ids: 子图中的节点ID列表
        """
        self.subgraphs[subgraph_name] = node_ids
        logger.debug(f"添加子图: {subgraph_name} ({len(node_ids)}个节点)")
    
    def update_node_status(self, node_id: str, status: NodeStatus, error: Optional[str] = None):
        """更新节点状态
        
        Args:
            node_id: 节点ID
            status: 新状态
            error: 错误信息（如果失败）
        """
        if node_id in self.nodes:
            node = self.nodes[node_id]
            
            if status == NodeStatus.RUNNING:
                node.start_execution()
            elif status in [NodeStatus.COMPLETED, NodeStatus.FAILED]:
                node.complete_execution(status == NodeStatus.COMPLETED, error)
            else:
                node.status = status
                
            logger.debug(f"更新节点状态: {node_id} -> {status.value}")
    
    def generate_mermaid(self, include_status: bool = True) -> str:
        """生成Mermaid图表
        
        Args:
            include_status: 是否包含状态信息
            
        Returns:
            Mermaid图表代码
        """
        mermaid_code = ["graph TD"]
        
        # 添加子图
        for subgraph_name, node_ids in self.subgraphs.items():
            mermaid_code.append(f"    subgraph {subgraph_name}")
            for node_id in node_ids:
                if node_id in self.nodes:
                    node = self.nodes[node_id]
                    status_suffix = f" [{node.status.value}]" if include_status else ""
                    mermaid_code.append(f"        {node_id}[{node.label}{status_suffix}]")
            mermaid_code.append("    end")
        
        # 添加普通节点
        for node_id, node in self.nodes.items():
            # 跳过已在子图中的节点
            if any(node_id in nodes for nodes in self.subgraphs.values()):
                continue
                
            status_suffix = f" [{node.status.value}]" if include_status else ""
            shape = self.node_styles.get(node.node_type, {}).get("shape", "rect")
            
            if shape == "diamond":
                mermaid_code.append(f"    {node_id}{{{node.label}{status_suffix}}}")
            elif shape == "circle":
                mermaid_code.append(f"    {node_id}(({node.label}{status_suffix}))")
            elif shape == "hexagon":
                mermaid_code.append(f"    {node_id}{{{{{node.label}{status_suffix}}}}}")
            else:  # rect
                mermaid_code.append(f"    {node_id}[{node.label}{status_suffix}]")
        
        # 添加边
        for from_node, to_node in self.edges:
            mermaid_code.append(f"    {from_node} --> {to_node}")
        
        # 添加条件边
        for from_node, conditions in self.conditional_edges.items():
            for condition, to_node in conditions.items():
                if condition == "__end__":
                    mermaid_code.append(f"    {from_node} --> END[结束]")
                else:
                    mermaid_code.append(f"    {from_node} -->|{condition}| {to_node}")
        
        # 添加样式
        if include_status:
            for node_id, node in self.nodes.items():
                status_style = self.status_styles.get(node.status, {})
                node_style = self.node_styles.get(node.node_type, {})
                
                fill = status_style.get("fill", "#f8f9fa")
                stroke = status_style.get("stroke", "#dee2e6")
                color = node_style.get("color", "#000000")
                
                mermaid_code.append(f"    style {node_id} fill:{fill},stroke:{stroke},color:{color}")
        
        return "\n".join(mermaid_code)
    
    def generate_interactive_html(self, title: str = "工作流DAG图") -> str:
        """生成交互式HTML可视化
        
        Args:
            title: 页面标题
            
        Returns:
            HTML代码
        """
        mermaid_code = self.generate_mermaid(include_status=True)
        
        # 生成节点信息表格
        nodes_info = []
        for node_id, node in self.nodes.items():
            nodes_info.append({
                "id": node_id,
                "type": node.node_type.value,
                "label": node.label,
                "status": node.status.value,
                "execution_time": f"{node.execution_time:.2f}s" if node.execution_time else "N/A",
                "error": node.error or "无"
            })
        
        # 统计信息
        total_nodes = len(self.nodes)
        completed_nodes = len([n for n in self.nodes.values() if n.status == NodeStatus.COMPLETED])
        failed_nodes = len([n for n in self.nodes.values() if n.status == NodeStatus.FAILED])
        running_nodes = len([n for n in self.nodes.values() if n.status == NodeStatus.RUNNING])
        
        html_template = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f8f9fa;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            padding: 20px;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            border-bottom: 2px solid #e9ecef;
            padding-bottom: 20px;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 15px;
            text-align: center;
            border-left: 4px solid #007bff;
        }}
        .stat-card.completed {{ border-left-color: #28a745; }}
        .stat-card.failed {{ border-left-color: #dc3545; }}
        .stat-card.running {{ border-left-color: #ffc107; }}
        .stat-value {{
            font-size: 2em;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .graph-container {{
            text-align: center;
            margin: 30px 0;
        }}
        .controls {{
            margin: 20px 0;
            text-align: center;
        }}
        .btn {{
            background: #007bff;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            margin: 0 5px;
        }}
        .btn:hover {{ background: #0056b3; }}
        .info-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        .info-table th, .info-table td {{
            border: 1px solid #dee2e6;
            padding: 8px 12px;
            text-align: left;
        }}
        .info-table th {{
            background-color: #f8f9fa;
            font-weight: 600;
        }}
        .status-badge {{
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.8em;
            font-weight: 500;
        }}
        .status-pending {{ background: #f8f9fa; color: #6c757d; }}
        .status-running {{ background: #fff3cd; color: #856404; }}
        .status-completed {{ background: #d1edff; color: #0066cc; }}
        .status-failed {{ background: #f8d7da; color: #721c24; }}
        .status-skipped {{ background: #e2e3e5; color: #495057; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <p>实时工作流执行状态图 - 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-value">{total_nodes}</div>
                <div>总节点数</div>
            </div>
            <div class="stat-card completed">
                <div class="stat-value">{completed_nodes}</div>
                <div>已完成</div>
            </div>
            <div class="stat-card failed">
                <div class="stat-value">{failed_nodes}</div>
                <div>失败</div>
            </div>
            <div class="stat-card running">
                <div class="stat-value">{running_nodes}</div>
                <div>执行中</div>
            </div>
        </div>
        
        <div class="controls">
            <button class="btn" onclick="refreshGraph()">刷新图表</button>
            <button class="btn" onclick="exportGraph()">导出图像</button>
            <button class="btn" onclick="toggleDetails()">切换详情</button>
        </div>
        
        <div class="graph-container">
            <div class="mermaid" id="mermaid-diagram">
{mermaid_code}
            </div>
        </div>
        
        <div id="details-section">
            <h3>节点执行详情</h3>
            <table class="info-table">
                <thead>
                    <tr>
                        <th>节点ID</th>
                        <th>类型</th>
                        <th>标签</th>
                        <th>状态</th>
                        <th>执行时间</th>
                        <th>错误信息</th>
                    </tr>
                </thead>
                <tbody>
"""
        
        # 添加节点信息行
        for node_info in nodes_info:
            status_class = f"status-{node_info['status']}"
            html_template += f"""
                    <tr>
                        <td>{node_info['id']}</td>
                        <td>{node_info['type']}</td>
                        <td>{node_info['label']}</td>
                        <td><span class="status-badge {status_class}">{node_info['status']}</span></td>
                        <td>{node_info['execution_time']}</td>
                        <td>{node_info['error']}</td>
                    </tr>
"""
        
        html_template += """
                </tbody>
            </table>
        </div>
    </div>
    
    <script>
        mermaid.initialize({ 
            startOnLoad: true,
            theme: 'default',
            flowchart: {
                useMaxWidth: true,
                htmlLabels: true,
                curve: 'basis'
            }
        });
        
        function refreshGraph() {
            location.reload();
        }
        
        function exportGraph() {
            // 这里可以添加图表导出功能
            alert('导出功能将在后续版本中实现');
        }
        
        function toggleDetails() {
            const details = document.getElementById('details-section');
            details.style.display = details.style.display === 'none' ? 'block' : 'none';
        }
        
        // 自动刷新（可选）
        // setInterval(refreshGraph, 5000);
    </script>
</body>
</html>
"""
        
        return html_template
    
    def generate_progress_summary(self) -> Dict[str, Any]:
        """生成执行进度摘要
        
        Returns:
            进度摘要字典
        """
        total_nodes = len(self.nodes)
        if total_nodes == 0:
            return {"progress": 0.0, "summary": "没有节点"}
        
        status_counts = {}
        execution_times = []
        
        for node in self.nodes.values():
            status_counts[node.status.value] = status_counts.get(node.status.value, 0) + 1
            if node.execution_time:
                execution_times.append(node.execution_time)
        
        completed = status_counts.get(NodeStatus.COMPLETED.value, 0)
        failed = status_counts.get(NodeStatus.FAILED.value, 0)
        progress = (completed + failed) / total_nodes
        
        avg_execution_time = sum(execution_times) / len(execution_times) if execution_times else 0
        
        return {
            "progress": progress,
            "total_nodes": total_nodes,
            "status_counts": status_counts,
            "avg_execution_time": avg_execution_time,
            "summary": f"进度: {progress:.1%} ({completed}/{total_nodes})"
        }
    
    def export_to_json(self) -> str:
        """导出为JSON格式
        
        Returns:
            JSON字符串
        """
        data = {
            "nodes": {node_id: node.to_dict() for node_id, node in self.nodes.items()},
            "edges": self.edges,
            "conditional_edges": self.conditional_edges,
            "subgraphs": self.subgraphs,
            "progress_summary": self.generate_progress_summary(),
            "export_time": datetime.now().isoformat()
        }
        
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    def load_from_langgraph(self, compiled_graph: Any) -> None:
        """从LangGraph编译图中加载结构
        
        Args:
            compiled_graph: LangGraph编译的图对象
        """
        try:
            # 获取图对象
            graph_obj = compiled_graph.get_graph()
            
            # 添加节点
            for node in graph_obj.nodes:
                node_type = self._infer_node_type(node)
                self.add_node(node, node_type, node)
            
            # 添加边
            for edge in graph_obj.edges:
                if hasattr(edge, 'source') and hasattr(edge, 'target'):
                    self.add_edge(edge.source, edge.target)
                elif isinstance(edge, tuple) and len(edge) == 2:
                    self.add_edge(edge[0], edge[1])
            
            logger.info(f"从LangGraph加载了 {len(self.nodes)} 个节点和 {len(self.edges)} 条边")
            
        except Exception as e:
            logger.error(f"从LangGraph加载图结构失败: {str(e)}")
    
    def _infer_node_type(self, node_name: str) -> NodeType:
        """推断节点类型
        
        Args:
            node_name: 节点名称
            
        Returns:
            推断的节点类型
        """
        node_name_lower = node_name.lower()
        
        if "supervisor" in node_name_lower or "meta" in node_name_lower:
            return NodeType.SUPERVISOR
        elif "critic" in node_name_lower:
            return NodeType.CRITIC
        elif "planner" in node_name_lower:
            return NodeType.PLANNER
        elif "agent" in node_name_lower:
            return NodeType.AGENT
        elif "tool" in node_name_lower:
            return NodeType.TOOL
        else:
            return NodeType.AGENT  # 默认为智能体节点

def create_dag_visualizer_from_graph(compiled_graph: Any, config: Optional[Dict[str, Any]] = None) -> DAGVisualizer:
    """从编译图创建DAG可视化器
    
    Args:
        compiled_graph: LangGraph编译的图对象
        config: 配置参数
        
    Returns:
        DAGVisualizer实例
    """
    visualizer = DAGVisualizer(config)
    visualizer.load_from_langgraph(compiled_graph)
    return visualizer 