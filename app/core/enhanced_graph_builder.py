"""
简化的增强版图构建器 - 专注于图结构构建，智能体从外部注入

重构特点：
1. 移除内部智能体定义，智能体从engine.py注入
2. 实现动态Task DAG调度架构  
3. 支持人类在环和并行执行
4. 基于LLM驱动的智能路由
5. 集成MCP工具能力画像
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable, Union, Literal, Set, Tuple
from enum import Enum
import uuid

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import add_messages
from langgraph.constants import Send
from langgraph.types import Command

from app.core.state import IsotopeSystemState, StateManager, TaskStatus
from app.core.config import ConfigManager
from app.core.postgres_checkpoint import get_postgres_checkpoint_manager, PostgreSQLCheckpointManager
from app.core.task_decorator import task_registry, get_task_by_name, apply_langgraph_decorator

from app.core.dag_visualizer import DAGVisualizer, create_dag_visualizer_from_graph

# MCP工具支持将在运行时动态导入，避免循环导入

logger = logging.getLogger(__name__)

class TaskType(str, Enum):
    """任务类型枚举"""
    CONSULTATION = "consultation"
    DATA_ANALYSIS = "data_analysis"
    EXPERT_ANALYSIS = "expert_analysis"
    MULTI_STEP = "multi_step"
    TOOL_EXECUTION = "tool_execution"
    
    # 油气勘探专业任务
    SEISMIC_PROCESSING = "seismic_processing"
    LOGGING_RECONSTRUCTION = "logging_reconstruction"
    WELL_LOGGING_ANALYSIS = "well_logging_analysis"
    STRUCTURE_RECOGNITION = "structure_recognition"
    WELL_SEISMIC_FUSION = "well_seismic_fusion"
    RESERVOIR_MODELING = "reservoir_modeling"
    RESERVOIR_SIMULATION = "reservoir_simulation"

class TaskPriority(str, Enum):
    """任务优先级枚举"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class SubgraphType(str, Enum):
    """子图类型枚举"""
    DATA_PROCESSING = "data_processing"
    ISOTOPE_ANALYSIS = "isotope_analysis"
    VISUALIZATION = "visualization"
    REPORT_GENERATION = "report_generation"

class EnhancedGraphBuilder:
    """简化的增强版图构建器 - 专注于图结构，智能体外部注入"""
    
    def __init__(
        self,
        # 核心智能体（极简架构）
        smart_router: Optional[Any] = None,
        
        # 专业智能体字典（从engine注入）
        specialized_agents: Optional[Dict[str, Any]] = None,
        
        # 配置和基础设施
        config: Optional[Union[ConfigManager, Dict[str, Any]]] = None,
        checkpointer: Optional[Any] = None,
        enable_postgres_checkpoint: bool = True,
        enable_mysql_checkpoint: bool = False,
        checkpoint_backend: str = "postgres"
    ):
        """
        初始化极简的图构建器
        
        Args:
            smart_router: 统一智能路由器智能体实例
            specialized_agents: 专业智能体字典
            config: 配置管理器或字典
            checkpointer: 检查点管理器
            enable_postgres_checkpoint: 是否启用PostgreSQL检查点
            enable_mysql_checkpoint: 是否启用MySQL检查点
            checkpoint_backend: 检查点后端类型
        """
        # 核心智能体（极简架构）
        self.smart_router = smart_router
        
        # 专业智能体
        self.specialized_agents = specialized_agents or {}
        
        # 配置管理
        self.config = self._safe_get_config(config)
        
        # 检查点管理
        self.checkpointer = checkpointer
        self.enable_postgres_checkpoint = enable_postgres_checkpoint
        self.enable_mysql_checkpoint = enable_mysql_checkpoint
        self.checkpoint_backend = self._determine_checkpoint_backend()
        
        # 初始化检查点管理器
        self._init_checkpoint_managers()
        
        # 执行统计
        self.execution_stats = {
            "graphs_built": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "avg_execution_time": 0.0,
            "mcp_enabled": self._get_mcp_status(),
            "tool_statistics": self._get_tool_statistics()
        }
        
        # DAG可视化器
        self.dag_visualizer = None
        
        logger.info(f"EnhancedGraphBuilder初始化完成，使用{self.checkpoint_backend}检查点后端")
    
    def _get_mcp_status(self) -> bool:
        """动态获取MCP状态，避免循环导入"""
        try:
            from app.tools.registry import is_mcp_enabled
            return is_mcp_enabled()
        except ImportError:
            return False
    
    def _get_tool_statistics(self) -> Dict[str, Any]:
        """动态获取工具统计信息，避免循环导入"""
        try:
            from app.tools.registry import get_tool_statistics
            return get_tool_statistics()
        except ImportError:
            return {}
    
    def _safe_get_config(self, config: Any) -> Dict[str, Any]:
        """安全地获取配置字典"""
        if config is None:
            return {}
        elif isinstance(config, dict):
            return config
        elif hasattr(config, 'config'):
            return getattr(config, 'config', {})
        elif hasattr(config, 'to_dict'):
            return config.to_dict()
        else:
            logger.warning(f"未识别的配置类型: {type(config)}")
            return {}
    
    def _determine_checkpoint_backend(self) -> str:
        """确定检查点后端"""
        if self.enable_postgres_checkpoint:
            return "postgres"
        elif self.enable_mysql_checkpoint:
            return "mysql"
        else:
            return "memory"
    
    def _init_checkpoint_managers(self):
        """初始化检查点管理器"""
        self.postgres_checkpoint_manager = None
        self.mysql_checkpoint_manager = None
        
        if self.checkpoint_backend == "postgres":
            self._init_postgres_checkpoint()
        elif self.checkpoint_backend == "mysql":
            self._init_mysql_checkpoint()
    
    def _init_postgres_checkpoint(self):
        """初始化PostgreSQL检查点管理器"""
        try:
            logger.info("正在启用PostgreSQL检查点管理器...")
            self.postgres_checkpoint_manager = get_postgres_checkpoint_manager(self.config)
            
            if self.postgres_checkpoint_manager:
                postgres_available = self.postgres_checkpoint_manager.test_connection()
                if postgres_available:
                    logger.info("PostgreSQL检查点管理器连接测试成功")
                else:
                    logger.warning("PostgreSQL连接测试失败，但检查点管理器已创建")
            else:
                logger.warning("PostgreSQL检查点管理器创建失败")
                self.postgres_checkpoint_manager = None
        except Exception as e:
            logger.error(f"初始化PostgreSQL检查点管理器失败: {str(e)}")
            self.postgres_checkpoint_manager = None
    
    def _init_mysql_checkpoint(self):
        """初始化MySQL检查点管理器"""
        try:
            logger.info("正在启用MySQL检查点管理器...")
            from app.core.mysql_checkpoint import get_mysql_checkpoint_manager
            self.mysql_checkpoint_manager = get_mysql_checkpoint_manager(self.config)
            
            if self.mysql_checkpoint_manager:
                mysql_available = self.mysql_checkpoint_manager.test_connection()
                if mysql_available:
                    logger.info("MySQL检查点管理器连接测试成功")
                else:
                    logger.warning("MySQL连接测试失败，但检查点管理器已创建")
            else:
                logger.warning("MySQL检查点管理器创建失败")
                self.mysql_checkpoint_manager = None
        except Exception as e:
            logger.error(f"初始化MySQL检查点管理器失败: {str(e)}")
            self.mysql_checkpoint_manager = None
    
    def build_enhanced_graph(self, session_id: Optional[str] = None) -> StateGraph:
        """构建增强版动态调度图"""
        logger.info("构建动态Task DAG调度图")
        
        try:
            # 导入状态类型
            from app.core.state import IsotopeSystemState
            
            # 创建状态图
            graph = StateGraph(IsotopeSystemState)
            
            # 核心节点：使用外部注入的智能体
            core_nodes = self._create_core_nodes()
            
            # 动态智能体节点：基于注册表的专业智能体
            dynamic_nodes = self._create_dynamic_agent_nodes()
            
            # 添加所有节点
            all_nodes = {**core_nodes, **dynamic_nodes}
            for node_name, node_func in all_nodes.items():
                graph.add_node(node_name, node_func)
                logger.info(f"添加图节点: {node_name}")
            
            # 构建动态路由架构
            self._build_dynamic_routing(graph, all_nodes)
            
            # 设置入口点（直接从智能路由器开始）
            graph.set_entry_point("smart_router")
            
            logger.info("动态调度图构建完成")
            self.execution_stats["graphs_built"] += 1
            
            # 初始化DAG可视化器
            try:
                self.dag_visualizer = DAGVisualizer(self.config)
                self._populate_dag_visualizer(all_nodes)
                logger.info("DAG可视化器初始化完成")
            except Exception as e:
                logger.warning(f"DAG可视化器初始化失败: {str(e)}")
            
            return graph
            
        except Exception as e:
            logger.error(f"构建增强图失败: {str(e)}")
            # 返回最小化图避免崩溃
            return self._create_minimal_fallback_graph()
    
    def _create_core_nodes(self) -> Dict[str, Callable]:
        """创建核心节点（极简ReAct架构）"""
        nodes = {}
        
        # Smart Router节点 - 统一处理用户意图识别和智能体路由
        if self.smart_router:
            def smart_router_node(state: IsotopeSystemState) -> IsotopeSystemState:
                """统一智能路由器节点"""
                logger.info("执行统一智能路由器节点")
                try:
                    return self.smart_router.run(state)
                except Exception as e:
                    logger.error(f"智能路由器执行失败: {str(e)}")
                    state["metadata"]["smart_router_error"] = str(e)
                    return state
            
            nodes["smart_router"] = smart_router_node
        
        return nodes
    
    def _create_dynamic_agent_nodes(self) -> Dict[str, Callable]:
        """创建动态智能体节点"""
        nodes = {}
        
        # 为每个专业智能体创建节点
        for agent_name, agent_instance in self.specialized_agents.items():
            def create_agent_node(agent_name: str, agent: Any) -> Callable:
                def agent_node(state: IsotopeSystemState) -> IsotopeSystemState:
                    """动态智能体节点"""
                    logger.info(f"执行专业智能体: {agent_name}")
                    try:
                        if hasattr(agent, 'run'):
                            return agent.run(state)
                        else:
                            logger.warning(f"智能体{agent_name}缺少run方法")
                            return state
                    except Exception as e:
                        logger.error(f"智能体{agent_name}执行失败: {str(e)}")
                        state["metadata"][f"{agent_name}_error"] = str(e)
                        return state
                
                return agent_node
            
            nodes[agent_name] = create_agent_node(agent_name, agent_instance)
        
        return nodes
    
    def _build_dynamic_routing(self, graph: StateGraph, all_nodes: Dict[str, Callable]):
        """构建极简的ReAct路由架构"""
        
        # 极简路由：Smart Router -> 专业智能体 -> END
        if "smart_router" in all_nodes:
            def route_from_smart_router(state: IsotopeSystemState) -> str:
                """Smart Router路由到专业智能体"""
                # 从状态中获取推荐的智能体
                recommended_agent = state.get("metadata", {}).get("recommended_agent", "")
                
                # 如果推荐的智能体存在，直接路由过去
                if recommended_agent and recommended_agent in all_nodes:
                    return recommended_agent
                
                # 否则根据消息内容简单判断
                messages = state.get("messages", [])
                if messages:
                    last_message = messages[-1].content if hasattr(messages[-1], 'content') else str(messages[-1])
                    
                    # 简单关键词匹配
                    if any(keyword in last_message.lower() for keyword in ['录井', '测井', 'logging', 'well']):
                        return "logging" if "logging" in all_nodes else "__end__"
                    elif any(keyword in last_message.lower() for keyword in ['地震', 'seismic', '地球物理']):
                        return "seismic" if "seismic" in all_nodes else "__end__"
                    elif any(keyword in last_message.lower() for keyword in ['咨询', '介绍', '帮助', '功能', '怎么用', '问题']):
                        return "assistant" if "assistant" in all_nodes else "__end__"
                
                # 默认路由到助手智能体
                if "assistant" in all_nodes:
                    return "assistant"
                return "__end__"
            
            # 构建所有可能的路由目标
            route_targets = {}
            if "logging" in all_nodes:
                route_targets["logging"] = "logging"
            if "seismic" in all_nodes:
                route_targets["seismic"] = "seismic"
            if "assistant" in all_nodes:
                route_targets["assistant"] = "assistant"
            route_targets["__end__"] = "__end__"
            
            graph.add_conditional_edges(
                "smart_router",
                route_from_smart_router,
                route_targets
            )
        
        # 专业智能体完成后直接结束
        for agent_name in ["logging", "seismic", "assistant"]:
            if agent_name in all_nodes:
                graph.add_edge(agent_name, "__end__")
        
        logger.info("极简ReAct路由架构构建完成")
    
    def _create_minimal_fallback_graph(self) -> StateGraph:
        """创建最小化的fallback图"""
        from app.core.state import IsotopeSystemState
        
        graph = StateGraph(IsotopeSystemState)
        
        def fallback_node(state: IsotopeSystemState) -> IsotopeSystemState:
            """Fallback节点"""
            if "messages" not in state:
                state["messages"] = []
            
            state["messages"].append(
                AIMessage(content="系统当前处于简化模式，请稍后重试。")
            )
            return state
        
        graph.add_node("fallback", fallback_node)
        graph.set_entry_point("fallback")
        graph.add_edge("fallback", "__end__")
        
        logger.warning("使用fallback图")
        return graph
    
    def compile_enhanced_graph(self, graph: Optional[StateGraph] = None, session_id: Optional[str] = None) -> Any:
        """编译增强版图"""
        if graph is None:
            graph = self.build_enhanced_graph(session_id)
        
        try:
            # 获取检查点管理器
            checkpointer = self._get_active_checkpointer()
            
            # 编译图
            if checkpointer:
                compiled_graph = graph.compile(checkpointer=checkpointer)
                logger.info(f"图编译完成，使用{type(checkpointer).__name__}检查点管理器")
            else:
                compiled_graph = graph.compile()
                logger.info("图编译完成，未使用检查点管理器")
            
            return compiled_graph
            
        except Exception as e:
            logger.error(f"图编译失败: {str(e)}")
            # 尝试不使用检查点管理器编译
            try:
                compiled_graph = graph.compile()
                logger.warning("图编译成功，但未使用检查点管理器")
                return compiled_graph
            except Exception as e2:
                logger.error(f"fallback编译也失败: {str(e2)}")
                raise e
    
    def _get_active_checkpointer(self):
        """获取活跃的检查点管理器"""
        if self.checkpointer:
            return self.checkpointer
        
        if self.checkpoint_backend == "postgres" and self.postgres_checkpoint_manager:
            return self.postgres_checkpoint_manager.get_checkpointer()
        elif self.checkpoint_backend == "mysql" and self.mysql_checkpoint_manager:
            return self.mysql_checkpoint_manager.get_checkpointer()
        else:
            # 使用内存检查点管理器作为fallback
            return MemorySaver()
    
    def create_thread_config(self, thread_id: Optional[str] = None) -> Dict[str, Any]:
        """创建线程配置"""
        if thread_id is None:
            thread_id = str(uuid.uuid4())
        
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": "",
                "checkpoint_id": None
            }
        }
    
    def visualize_graph(self, compiled_graph: Optional[Any] = None) -> Tuple[str, Optional[bytes]]:
        """可视化图结构"""
        if compiled_graph is None:
            return "图未编译，无法可视化", None
        
        try:
            # 获取图对象
            graph_obj = compiled_graph.get_graph()
            
            # 生成Mermaid文本
            mermaid_text = graph_obj.draw_mermaid()
            
            # 尝试生成PNG图像
            png_data = None
            try:
                png_data = graph_obj.draw_png()
            except Exception as png_error:
                logger.debug(f"PNG图像生成失败: {str(png_error)}")
            
            return mermaid_text, png_data
            
        except Exception as e:
            logger.error(f"图可视化失败: {str(e)}")
            return f"可视化失败: {str(e)}", None
    
    def get_execution_statistics(self) -> Dict[str, Any]:
        """获取执行统计信息"""
        return {
            **self.execution_stats,
            "specialized_agents_count": len(self.specialized_agents),
            "checkpoint_backend": self.checkpoint_backend,
            "postgres_available": self.postgres_checkpoint_manager is not None,
            "mysql_available": self.mysql_checkpoint_manager is not None
        }
    
    def validate_configuration(self) -> Dict[str, Any]:
        """验证配置"""
        validation_result = {
            "valid": True,
            "warnings": [],
            "errors": [],
            "recommendations": []
        }
        
        # 检查核心智能体
        required_agents = ["meta_supervisor", "task_planner", "smart_router", "task_dispatcher"]
        missing_agents = []
        for agent_name in required_agents:
            if getattr(self, agent_name, None) is None:
                missing_agents.append(agent_name)
        
        if missing_agents:
            validation_result["errors"].append(f"缺少核心智能体: {missing_agents}")
            validation_result["valid"] = False
        
        # 检查专业智能体
        if not self.specialized_agents:
            validation_result["warnings"].append("未配置专业智能体，将使用默认处理逻辑")
        
        # 检查检查点配置
        if not self._get_active_checkpointer():
            validation_result["warnings"].append("检查点管理器不可用，状态将不会持久化")
        
        return validation_result
    
    def _populate_dag_visualizer(self, all_nodes: Dict[str, Callable]):
        """填充DAG可视化器"""
        if not self.dag_visualizer:
            return
        
        try:
            from app.core.dag_visualizer import NodeType
            
            # 添加核心节点（极简架构）
            core_nodes = {
                "smart_router": (NodeType.AGENT, "统一智能路由器")
            }
            
            for node_id, (node_type, label) in core_nodes.items():
                if node_id in all_nodes:
                    self.dag_visualizer.add_node(node_id, node_type, label)
            
            # 添加专业智能体节点
            for agent_name in self.specialized_agents.keys():
                if agent_name in all_nodes:
                    self.dag_visualizer.add_node(
                        agent_name, 
                        NodeType.AGENT, 
                        f"{agent_name}智能体"
                    )
            
            # 添加基本边连接（极简ReAct架构）
            edges = [
                ("smart_router", "logging"),
                ("smart_router", "seismic"),
                ("smart_router", "assistant")
            ]
            
            for from_node, to_node in edges:
                if from_node in all_nodes and to_node in all_nodes:
                    self.dag_visualizer.add_edge(from_node, to_node)
                    
            logger.info("DAG可视化器节点和边添加完成")
            
        except Exception as e:
            logger.warning(f"填充DAG可视化器失败: {str(e)}")
    
    def get_dag_visualization(self) -> Optional[str]:
        """获取DAG可视化"""
        if self.dag_visualizer:
            try:
                return self.dag_visualizer.generate_mermaid(include_status=True)
            except Exception as e:
                logger.warning(f"生成DAG可视化失败: {str(e)}")
                return None
        return None
    
    def get_dag_html_visualization(self) -> Optional[str]:
        """获取DAG HTML可视化"""
        if self.dag_visualizer:
            try:
                return self.dag_visualizer.generate_interactive_html()
            except Exception as e:
                logger.warning(f"生成DAG HTML可视化失败: {str(e)}")
                return None
        return None
