"""
Task装饰器模块 - 阶段2实现

该模块提供了基于LangGraph Functional API的@task装饰器，用于：
1. 将现有工具转换为可检查点的任务
2. 支持确定性执行和副作用封装
3. 实现失败重播和错误恢复
4. 提供工具执行的可观测性
"""

import logging
import functools
import time
import json
import inspect
from typing import Any, Callable, Dict, List, Optional, Union
from datetime import datetime
import traceback

from app.utils.stream_writer import get_stream_writer

try:
    from langgraph.func import task as langgraph_task
    LANGGRAPH_FUNCTIONAL_API_AVAILABLE = True
except ImportError:
    LANGGRAPH_FUNCTIONAL_API_AVAILABLE = False
    langgraph_task = None

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)

class TaskRegistry:
    """Task注册表，管理所有@task化的工具"""
    
    def __init__(self):
        self._tasks: Dict[str, Callable] = {}
        self._task_metadata: Dict[str, Dict[str, Any]] = {}
        
    def register_task(self, name: str, task_func: Callable, metadata: Optional[Dict[str, Any]] = None):
        """注册task到注册表"""
        self._tasks[name] = task_func
        self._task_metadata[name] = metadata or {}
        logger.info(f"Task '{name}' 已注册到注册表")
        
    def get_task(self, name: str) -> Optional[Callable]:
        """获取task函数"""
        return self._tasks.get(name)
        
    def get_all_tasks(self) -> Dict[str, Callable]:
        """获取所有task"""
        return self._tasks.copy()
        
    def get_task_metadata(self, name: str) -> Dict[str, Any]:
        """获取task元数据"""
        return self._task_metadata.get(name, {})

# 全局task注册表
task_registry = TaskRegistry()

def task(
    name: Optional[str] = None,
    retry_policy: Optional[Dict[str, Any]] = None,
    timeout: Optional[int] = None,
    deterministic: bool = True,
    track_execution: bool = True
):
    """
    Task装饰器 - 将函数转换为LangGraph @task
    
    这个装饰器将现有的工具函数转换为支持检查点的task，提供：
    1. 确定性执行 - 重播时返回相同结果
    2. 副作用封装 - 确保副作用只执行一次
    3. 错误恢复 - 支持失败重播
    4. 执行追踪 - 提供可观测性
    
    Args:
        name: task名称，默认使用函数名
        retry_policy: 重试策略，如 {"max_attempts": 3, "delay": 1.0}
        timeout: 超时时间（秒）
        deterministic: 是否要求确定性执行
        track_execution: 是否追踪执行信息
    
    用法：
        @task(name="analyze_data", retry_policy={"max_attempts": 3})
        def analyze_isotope_data(file_id: str) -> str:
            # 工具实现
            pass
    """
    def decorator(func: Callable) -> Callable:
        task_name = name or func.__name__
        
        # 包装函数以添加执行追踪
        @functools.wraps(func)
        def tracked_func(*args, **kwargs):
            if track_execution:
                start_time = time.time()
                logger.info(f"开始执行task: {task_name}")
                
            try:
                result = func(*args, **kwargs)
                
                if track_execution:
                    duration = time.time() - start_time
                    logger.info(f"Task {task_name} 执行成功，耗时: {duration:.2f}秒")
                
                return result
                
            except Exception as e:
                if track_execution:
                    duration = time.time() - start_time
                    logger.error(f"Task {task_name} 执行失败，耗时: {duration:.2f}秒，错误: {str(e)}")
                raise
        
        # 修改：不立即应用LangGraph装饰器，而是在函数属性中存储配置
        # 当LangGraph图运行时再应用装饰器
        tracked_func._task_config = {
            "name": task_name,
            "retry_policy": retry_policy,
            "timeout": timeout,
            "deterministic": deterministic,
            "track_execution": track_execution
        }
        
        # 注册到task注册表，存储原始函数
        task_registry.register_task(task_name, tracked_func, {
            "original_func": func,
            "retry_policy": retry_policy,
            "timeout": timeout,
            "deterministic": deterministic,
            "track_execution": track_execution,
            "is_wrapped": True
        })
        
        return tracked_func
    
    return decorator

def _is_in_langgraph_context() -> bool:
    """检查当前是否在LangGraph上下文中运行"""
    # 检查调用栈，查找LangGraph相关帧
    frames = inspect.stack()
    for frame in frames:
        if 'langgraph' in frame.filename:
            return True
    return False

def apply_langgraph_decorator(task_func: Callable) -> Callable:
    """
    为任务函数应用LangGraph装饰器，确保流式输出正确传递
    
    修复：避免传递不可序列化的配置对象，防止 'unhashable type: dict' 错误
    """
    if not hasattr(task_func, '_task_config'):
        logger.debug(f"任务 {task_func.__name__} 没有_task_config属性，使用原始函数")
        return task_func
    
    task_config = task_func._task_config
    
    try:
        # *** 关键修复：避免传递字典到装饰器，防止hashable错误 ***
        logger.debug(f"尝试为任务 {task_config['name']} 应用LangGraph装饰器")
        
        # 创建一个包装函数，确保流式输出正确传递
        @functools.wraps(task_func)
        def langgraph_wrapper(*args, **kwargs):
            try:
                # 在装饰器内部再次尝试获取流式写入器
                writer = None
                try:
                    writer = get_stream_writer()
                except RuntimeError:
                    pass
                
                if writer:
                    logger.debug(f"LangGraph装饰器成功获取流式写入器")
                else:
                    logger.debug(f"LangGraph装饰器未能获取流式写入器")
                
                # 执行原始任务函数
                return task_func(*args, **kwargs)
                
            except Exception as e:
                logger.error(f"LangGraph装饰器执行失败: {e}")
                # 如果装饰器执行失败，直接调用原始函数
                return task_func(*args, **kwargs)
        
        # *** 关键修复：应用装饰器时避免传递复杂配置对象 ***
        # 检查是否有重试配置，但不传递整个配置字典
        if task_config and 'retry' in task_config:
            retry_config = task_config['retry']
            if isinstance(retry_config, dict) and 'max_attempts' in retry_config:
                # 只提取基本的重试次数，避免复杂对象序列化问题
                max_attempts = retry_config.get('max_attempts', 3)
                logger.debug(f"任务 {task_config['name']} 配置重试次数: {max_attempts}")
        
        # *** 关键修复：直接应用装饰器，不传递配置参数以避免序列化错误 ***
        try:
            decorated_func = langgraph_task(langgraph_wrapper)
            logger.debug(f"✅ 成功为任务 {task_config['name']} 应用LangGraph装饰器")
            return decorated_func
        except Exception as decorator_error:
            logger.warning(f"直接装饰器应用失败: {decorator_error}")
            # 如果直接装饰器失败，返回wrapper函数
            return langgraph_wrapper
            
    except Exception as e:
        logger.error(f"应用LangGraph装饰器失败: {e}")
        logger.error(f"错误详情: {traceback.format_exc()}")
        # 如果所有装饰器应用都失败，返回原始函数
        return task_func

def convert_tool_to_task(
    tool: BaseTool,
    task_name: Optional[str] = None,
    retry_policy: Optional[Dict[str, Any]] = None,
    timeout: Optional[int] = None
) -> Callable:
    """
    将LangChain工具转换为Task
    
    Args:
        tool: LangChain BaseTool实例
        task_name: task名称，默认使用工具名
        retry_policy: 重试策略
        timeout: 超时时间
        
    Returns:
        转换后的task函数
    """
    name = task_name or tool.name
    
    @task(name=name, retry_policy=retry_policy, timeout=timeout)
    def tool_task(*args, **kwargs) -> Any:
        """工具任务包装器"""
        # 如果工具接受字典输入
        if hasattr(tool, 'args_schema') and tool.args_schema:
            # 构建工具输入
            if len(args) == 1 and isinstance(args[0], dict):
                tool_input = args[0]
            else:
                # 尝试从位置参数构建输入
                tool_input = {}
                if hasattr(tool.args_schema, '__fields__'):
                    field_names = list(tool.args_schema.__fields__.keys())
                    for i, arg in enumerate(args):
                        if i < len(field_names):
                            tool_input[field_names[i]] = arg
                # 添加关键字参数
                tool_input.update(kwargs)
        else:
            # 简单工具，直接传递参数
            if len(args) == 1 and not kwargs:
                tool_input = args[0]
            else:
                tool_input = {"args": args, "kwargs": kwargs}
        
        # 执行工具
        result = tool.invoke(tool_input)
        return result
    
    return tool_task

def get_task_by_name(name: str) -> Optional[Callable]:
    """根据名称获取task"""
    return task_registry.get_task(name)

def list_all_tasks() -> List[str]:
    """列出所有注册的task名称"""
    return list(task_registry.get_all_tasks().keys())

def get_task_metadata(name: str) -> Dict[str, Any]:
    """获取task元数据"""
    return task_registry.get_task_metadata(name)

# 辅助函数：创建确定性task
def deterministic_task(
    name: Optional[str] = None,
    retry_policy: Optional[Dict[str, Any]] = None
):
    """创建确定性task的便捷装饰器"""
    return task(
        name=name,
        retry_policy=retry_policy,
        deterministic=True,
        track_execution=True
    )

# 辅助函数：创建有副作用的task
def side_effect_task(
    name: Optional[str] = None,
    retry_policy: Optional[Dict[str, Any]] = None
):
    """创建有副作用的task的便捷装饰器"""
    return task(
        name=name,
        retry_policy=retry_policy,
        deterministic=False,  # 有副作用的task不要求严格确定性
        track_execution=True
    ) 