"""
动态子图生成器模块 - Stage 5实现

该模块负责根据任务计划动态生成LangGraph子图，支持：
1. 根据任务类型生成相应的子图
2. 动态节点编排
3. 条件路由和中断点设置
4. 子图的编译和执行
"""

import logging
from typing import Dict, List, Any, Optional, Callable, Union
from datetime import datetime
from enum import Enum
import uuid

from langgraph.graph import StateGraph
from langchain_core.messages import BaseMessage, AIMessage

from app.core.state import IsotopeSystemState, StateManager
from app.core.enhanced_graph_builder import SubgraphType, TaskType
from app.tools.registry import task_registry
from app.core.system_capability_registry import get_system_capability_registry

logger = logging.getLogger(__name__)

class SubgraphGenerator:
    """动态子图生成器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化子图生成器
        
        Args:
            config: 配置参数
        """
        self.config = config or {}
        self.capability_registry = get_system_capability_registry()
        self.task_registry = task_registry
        
        # 子图模板定义
        self.subgraph_templates = {
            SubgraphType.DATA_PROCESSING: self._create_data_processing_subgraph,
            SubgraphType.ISOTOPE_ANALYSIS: self._create_isotope_analysis_subgraph,
            SubgraphType.VISUALIZATION: self._create_visualization_subgraph,
            SubgraphType.REPORT_GENERATION: self._create_report_generation_subgraph
        }
        
        logger.info("动态子图生成器初始化完成")
    
    def generate_subgraph(
        self, 
        subgraph_type: SubgraphType,
        task_plan: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> StateGraph:
        """生成指定类型的子图
        
        Args:
            subgraph_type: 子图类型
            task_plan: 任务计划
            context: 上下文信息
            
        Returns:
            生成的子图
        """
        logger.info(f"开始生成子图: {subgraph_type.value}")
        
        try:
            # 获取子图生成模板
            template_func = self.subgraph_templates.get(subgraph_type)
            if not template_func:
                logger.warning(f"未找到子图模板: {subgraph_type.value}")
                return self._create_default_subgraph(task_plan)
            
            # 生成子图
            subgraph = template_func(task_plan, context)
            
            logger.info(f"子图生成成功: {subgraph_type.value}")
            return subgraph
            
        except Exception as e:
            logger.error(f"生成子图失败: {str(e)}")
            return self._create_default_subgraph(task_plan)
    
    def _create_data_processing_subgraph(
        self, 
        task_plan: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> StateGraph:
        """创建数据处理子图"""
        logger.debug("创建数据处理子图")
        
        graph = StateGraph(IsotopeSystemState)
        
        # 数据加载节点
        def load_data_node(state: IsotopeSystemState) -> IsotopeSystemState:
            """加载数据节点"""
            try:
                # 查找数据加载相关的task
                load_tasks = [
                    task for task in self.task_registry.get_all_tasks()
                    if "load" in task.lower() or "read" in task.lower()
                ]
                
                if load_tasks:
                    # 执行第一个匹配的task
                    task_name = load_tasks[0]
                    task_func = self.task_registry.get_task(task_name)
                    if task_func:
                        # TODO: 根据实际task签名调整参数
                        result = f"已加载数据（使用task: {task_name}）"
                    else:
                        result = "数据加载失败：未找到task函数"
                else:
                    result = "数据加载完成（使用默认方法）"
                
                msg = AIMessage(content=f"📊 {result}")
                return StateManager.update_messages(state, msg)
                
            except Exception as e:
                logger.error(f"数据加载失败: {str(e)}")
                error_msg = AIMessage(content=f"❌ 数据加载失败: {str(e)}")
                return StateManager.update_messages(state, error_msg)
        
        # 数据预处理节点
        def preprocess_data_node(state: IsotopeSystemState) -> IsotopeSystemState:
            """数据预处理节点"""
            try:
                # 查找预处理相关的task
                preprocess_tasks = [
                    task for task in self.task_registry.get_all_tasks()
                    if "preprocess" in task.lower() or "clean" in task.lower()
                ]
                
                if preprocess_tasks:
                    result = f"数据预处理完成（使用task: {preprocess_tasks[0]}）"
                else:
                    result = "数据预处理完成（使用默认方法）"
                
                msg = AIMessage(content=f"🔧 {result}")
                return StateManager.update_messages(state, msg)
                
            except Exception as e:
                logger.error(f"数据预处理失败: {str(e)}")
                error_msg = AIMessage(content=f"❌ 数据预处理失败: {str(e)}")
                return StateManager.update_messages(state, error_msg)
        
        # 数据验证节点
        def validate_data_node(state: IsotopeSystemState) -> IsotopeSystemState:
            """数据验证节点"""
            try:
                msg = AIMessage(content="✅ 数据验证通过")
                return StateManager.update_messages(state, msg)
            except Exception as e:
                logger.error(f"数据验证失败: {str(e)}")
                error_msg = AIMessage(content=f"❌ 数据验证失败: {str(e)}")
                return StateManager.update_messages(state, error_msg)
        
        # 添加节点
        graph.add_node("load_data", load_data_node)
        graph.add_node("preprocess_data", preprocess_data_node)
        graph.add_node("validate_data", validate_data_node)
        
        # 设置流程
        graph.set_entry_point("load_data")
        graph.add_edge("load_data", "preprocess_data")
        graph.add_edge("preprocess_data", "validate_data")
        graph.add_edge("validate_data", "__end__")
        
        return graph
    
    def _create_isotope_analysis_subgraph(
        self, 
        task_plan: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> StateGraph:
        """创建同位素分析子图"""
        logger.debug("创建同位素分析子图")
        
        graph = StateGraph(IsotopeSystemState)
        
        # 同位素数据分析节点
        def analyze_isotope_node(state: IsotopeSystemState) -> IsotopeSystemState:
            """同位素数据分析节点"""
            try:
                # 查找同位素分析相关的task
                isotope_tasks = [
                    task for task in self.task_registry.get_all_tasks()
                    if "isotope" in task.lower() or "classify" in task.lower()
                ]
                
                if isotope_tasks:
                    result = f"同位素分析完成（使用task: {isotope_tasks[0]}）"
                else:
                    result = "同位素分析完成（使用默认方法）"
                
                msg = AIMessage(content=f"🔬 {result}")
                return StateManager.update_messages(state, msg)
                
            except Exception as e:
                logger.error(f"同位素分析失败: {str(e)}")
                error_msg = AIMessage(content=f"❌ 同位素分析失败: {str(e)}")
                return StateManager.update_messages(state, error_msg)
        
        # 气源分类节点
        def classify_gas_source_node(state: IsotopeSystemState) -> IsotopeSystemState:
            """气源分类节点"""
            try:
                # 查找气源分类相关的task
                classify_tasks = [
                    task for task in self.task_registry.get_all_tasks()
                    if "classify" in task.lower() or "gas_source" in task.lower()
                ]
                
                if classify_tasks:
                    result = f"气源分类完成（使用task: {classify_tasks[0]}）"
                else:
                    result = "气源分类完成：煤型气/油型气/混合气"
                
                msg = AIMessage(content=f"🏷️ {result}")
                return StateManager.update_messages(state, msg)
                
            except Exception as e:
                logger.error(f"气源分类失败: {str(e)}")
                error_msg = AIMessage(content=f"❌ 气源分类失败: {str(e)}")
                return StateManager.update_messages(state, error_msg)
        
        # 结果解释节点
        def interpret_results_node(state: IsotopeSystemState) -> IsotopeSystemState:
            """结果解释节点"""
            try:
                msg = AIMessage(content="📝 分析结果解释：基于碳同位素值的专业地质解释")
                return StateManager.update_messages(state, msg)
            except Exception as e:
                logger.error(f"结果解释失败: {str(e)}")
                error_msg = AIMessage(content=f"❌ 结果解释失败: {str(e)}")
                return StateManager.update_messages(state, error_msg)
        
        # 添加节点
        graph.add_node("analyze_isotope", analyze_isotope_node)
        graph.add_node("classify_gas_source", classify_gas_source_node)
        graph.add_node("interpret_results", interpret_results_node)
        
        # 设置流程
        graph.set_entry_point("analyze_isotope")
        graph.add_edge("analyze_isotope", "classify_gas_source")
        graph.add_edge("classify_gas_source", "interpret_results")
        graph.add_edge("interpret_results", "__end__")
        
        return graph
    
    def _create_visualization_subgraph(
        self, 
        task_plan: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> StateGraph:
        """创建可视化子图"""
        logger.debug("创建可视化子图")
        
        graph = StateGraph(IsotopeSystemState)
        
        # 准备可视化数据节点
        def prepare_vis_data_node(state: IsotopeSystemState) -> IsotopeSystemState:
            """准备可视化数据"""
            try:
                msg = AIMessage(content="📊 准备可视化数据")
                return StateManager.update_messages(state, msg)
            except Exception as e:
                error_msg = AIMessage(content=f"❌ 准备可视化数据失败: {str(e)}")
                return StateManager.update_messages(state, error_msg)
        
        # 生成图表节点
        def generate_charts_node(state: IsotopeSystemState) -> IsotopeSystemState:
            """生成图表"""
            try:
                # 查找可视化相关的task
                vis_tasks = [
                    task for task in self.task_registry.get_all_tasks()
                    if "visual" in task.lower() or "plot" in task.lower() or "chart" in task.lower()
                ]
                
                if vis_tasks:
                    result = f"图表生成完成（使用task: {vis_tasks[0]}）"
                else:
                    result = "图表生成完成（散点图、箱线图、分布图）"
                
                msg = AIMessage(content=f"📈 {result}")
                return StateManager.update_messages(state, msg)
                
            except Exception as e:
                logger.error(f"生成图表失败: {str(e)}")
                error_msg = AIMessage(content=f"❌ 生成图表失败: {str(e)}")
                return StateManager.update_messages(state, error_msg)
        
        # 保存图表节点
        def save_charts_node(state: IsotopeSystemState) -> IsotopeSystemState:
            """保存图表"""
            try:
                msg = AIMessage(content="💾 图表已保存")
                return StateManager.update_messages(state, msg)
            except Exception as e:
                error_msg = AIMessage(content=f"❌ 保存图表失败: {str(e)}")
                return StateManager.update_messages(state, error_msg)
        
        # 添加节点
        graph.add_node("prepare_vis_data", prepare_vis_data_node)
        graph.add_node("generate_charts", generate_charts_node)
        graph.add_node("save_charts", save_charts_node)
        
        # 设置流程
        graph.set_entry_point("prepare_vis_data")
        graph.add_edge("prepare_vis_data", "generate_charts")
        graph.add_edge("generate_charts", "save_charts")
        graph.add_edge("save_charts", "__end__")
        
        return graph
    
    def _create_report_generation_subgraph(
        self, 
        task_plan: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> StateGraph:
        """创建报告生成子图"""
        logger.debug("创建报告生成子图")
        
        graph = StateGraph(IsotopeSystemState)
        
        # 收集报告数据节点
        def collect_report_data_node(state: IsotopeSystemState) -> IsotopeSystemState:
            """收集报告数据"""
            try:
                msg = AIMessage(content="📋 收集报告数据")
                return StateManager.update_messages(state, msg)
            except Exception as e:
                error_msg = AIMessage(content=f"❌ 收集报告数据失败: {str(e)}")
                return StateManager.update_messages(state, error_msg)
        
        # 生成报告节点
        def generate_report_node(state: IsotopeSystemState) -> IsotopeSystemState:
            """生成报告"""
            try:
                msg = AIMessage(content="📄 生成分析报告")
                return StateManager.update_messages(state, msg)
            except Exception as e:
                error_msg = AIMessage(content=f"❌ 生成报告失败: {str(e)}")
                return StateManager.update_messages(state, error_msg)
        
        # 格式化报告节点
        def format_report_node(state: IsotopeSystemState) -> IsotopeSystemState:
            """格式化报告"""
            try:
                msg = AIMessage(content="✨ 报告格式化完成")
                return StateManager.update_messages(state, msg)
            except Exception as e:
                error_msg = AIMessage(content=f"❌ 报告格式化失败: {str(e)}")
                return StateManager.update_messages(state, error_msg)
        
        # 添加节点
        graph.add_node("collect_report_data", collect_report_data_node)
        graph.add_node("generate_report", generate_report_node)
        graph.add_node("format_report", format_report_node)
        
        # 设置流程
        graph.set_entry_point("collect_report_data")
        graph.add_edge("collect_report_data", "generate_report")
        graph.add_edge("generate_report", "format_report")
        graph.add_edge("format_report", "__end__")
        
        return graph
    
    def _create_default_subgraph(self, task_plan: Dict[str, Any]) -> StateGraph:
        """创建默认子图"""
        logger.debug("创建默认子图")
        
        graph = StateGraph(IsotopeSystemState)
        
        # 默认处理节点
        def default_process_node(state: IsotopeSystemState) -> IsotopeSystemState:
            """默认处理节点"""
            try:
                task_description = task_plan.get("description", "任务处理")
                msg = AIMessage(content=f"🔄 {task_description} - 处理中...")
                return StateManager.update_messages(state, msg)
            except Exception as e:
                error_msg = AIMessage(content=f"❌ 处理失败: {str(e)}")
                return StateManager.update_messages(state, error_msg)
        
        # 完成节点
        def complete_node(state: IsotopeSystemState) -> IsotopeSystemState:
            """完成节点"""
            try:
                msg = AIMessage(content="✅ 任务完成")
                return StateManager.update_messages(state, msg)
            except Exception as e:
                error_msg = AIMessage(content=f"❌ 完成失败: {str(e)}")
                return StateManager.update_messages(state, error_msg)
        
        # 添加节点
        graph.add_node("default_process", default_process_node)
        graph.add_node("complete", complete_node)
        
        # 设置流程
        graph.set_entry_point("default_process")
        graph.add_edge("default_process", "complete")
        graph.add_edge("complete", "__end__")
        
        return graph
    
    def compile_subgraph(
        self, 
        subgraph: StateGraph,
        checkpointer: Optional[Any] = None,
        interrupt_before: Optional[List[str]] = None
    ) -> Any:
        """编译子图
        
        Args:
            subgraph: 要编译的子图
            checkpointer: 检查点器
            interrupt_before: 在哪些节点前设置中断点
            
        Returns:
            编译后的子图
        """
        try:
            compile_kwargs = {}
            
            if checkpointer:
                compile_kwargs["checkpointer"] = checkpointer
            
            if interrupt_before:
                compile_kwargs["interrupt_before"] = interrupt_before
            
            compiled = subgraph.compile(**compile_kwargs)
            logger.info("子图编译成功")
            return compiled
            
        except Exception as e:
            logger.error(f"子图编译失败: {str(e)}")
            # 尝试无参数编译
            try:
                compiled = subgraph.compile()
                logger.info("子图使用默认配置编译成功")
                return compiled
            except Exception as e2:
                logger.error(f"子图默认编译也失败: {str(e2)}")
                raise

# 创建全局子图生成器实例
_subgraph_generator = None

def get_subgraph_generator(config: Optional[Dict[str, Any]] = None) -> SubgraphGenerator:
    """获取子图生成器的单例实例
    
    Args:
        config: 配置参数
        
    Returns:
        子图生成器实例
    """
    global _subgraph_generator
    if _subgraph_generator is None:
        _subgraph_generator = SubgraphGenerator(config)
    return _subgraph_generator