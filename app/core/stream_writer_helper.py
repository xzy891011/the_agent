"""
LangGraph流式写入辅助工具

提供便捷的方法来通过langgraph.config.get_stream_writer推送各种执行状态信息
基于LangGraph官方文档: https://langchain-ai.github.io/langgraph/how-tos/streaming/
"""

import logging
from typing import Dict, Any, Optional
from langgraph.config import get_stream_writer

logger = logging.getLogger(__name__)


class LangGraphStreamWriter:
    """LangGraph流式写入器辅助类"""
    
    @staticmethod
    def push_agent_thinking(agent_name: str, content: str, thinking_type: str = "analysis"):
        """
        推送Agent思考过程
        
        Args:
            agent_name: Agent名称
            content: 思考内容
            thinking_type: 思考类型（analysis, planning, decision等）
        """
        try:
            writer = get_stream_writer()
            writer({
                "agent_thinking": {
                    "agent_name": agent_name,
                    "content": content,
                    "thinking_type": thinking_type
                }
            })
            logger.debug(f"推送Agent思考: {agent_name} - {content[:50]}...")
        except Exception as e:
            logger.warning(f"推送Agent思考失败: {e}")
    
    @staticmethod
    def push_node_execution(node_name: str, action: str, status: str, details: str = ""):
        """
        推送节点执行状态
        
        Args:
            node_name: 节点名称
            action: 执行动作（start, complete, error）
            status: 状态描述
            details: 详细信息
        """
        try:
            writer = get_stream_writer()
            writer({
                "node_execution": {
                    "node_name": node_name,
                    "action": action,
                    "status": status,
                    "details": details
                }
            })
            logger.debug(f"推送节点执行状态: {node_name} - {action}")
        except Exception as e:
            logger.warning(f"推送节点执行状态失败: {e}")
    
    @staticmethod
    def push_route_decision(from_node: str, to_node: str, reason: str):
        """
        推送路由决策信息
        
        Args:
            from_node: 源节点
            to_node: 目标节点  
            reason: 路由原因
        """
        try:
            writer = get_stream_writer()
            writer({
                "route_decision": {
                    "from_node": from_node,
                    "to_node": to_node,
                    "reason": reason
                }
            })
            logger.debug(f"推送路由决策: {from_node} -> {to_node}")
        except Exception as e:
            logger.warning(f"推送路由决策失败: {e}")
    
    @staticmethod
    def push_tool_progress(tool_name: str, progress: float, details: str = "", source: str = "tool"):
        """
        推送工具执行进度
        
        Args:
            tool_name: 工具名称
            progress: 进度百分比（0.0-1.0）
            details: 进度详情
            source: 来源标识
        """
        try:
            writer = get_stream_writer()
            writer({
                "tool_progress": {
                    "tool_name": tool_name,
                    "progress": progress,
                    "details": details,
                    "source": source
                }
            })
            logger.debug(f"推送工具进度: {tool_name} - {progress*100:.1f}%")
        except Exception as e:
            logger.warning(f"推送工具进度失败: {e}")
    
    @staticmethod
    def push_file_generated(file_id: str, file_name: str, file_path: str, 
                          file_type: str = "unknown", source: str = "system"):
        """
        推送文件生成通知
        
        Args:
            file_id: 文件ID
            file_name: 文件名
            file_path: 文件路径
            file_type: 文件类型
            source: 来源标识
        """
        try:
            writer = get_stream_writer()
            writer({
                "file_generated": {
                    "file_id": file_id,
                    "file_name": file_name,
                    "file_path": file_path,
                    "file_type": file_type,
                    "source": source
                }
            })
            logger.debug(f"推送文件生成: {file_name}")
        except Exception as e:
            logger.warning(f"推送文件生成失败: {e}")
    
    @staticmethod
    def push_task_status(task_name: str, status: str, progress: float = 0.0, details: str = ""):
        """
        推送任务状态更新
        
        Args:
            task_name: 任务名称
            status: 任务状态（started, running, completed, failed）
            progress: 任务进度（0.0-1.0）
            details: 状态详情
        """
        try:
            writer = get_stream_writer()
            writer({
                "task_status": {
                    "task_name": task_name,
                    "status": status,
                    "progress": progress,
                    "details": details
                }
            })
            logger.debug(f"推送任务状态: {task_name} - {status}")
        except Exception as e:
            logger.warning(f"推送任务状态失败: {e}")
    
    @staticmethod
    def push_llm_response(content: str, model_name: str = "unknown", is_complete: bool = False):
        """
        推送LLM响应内容（主要用于非标准LLM集成）
        
        Args:
            content: 响应内容
            model_name: 模型名称
            is_complete: 是否为完整响应
        """
        try:
            writer = get_stream_writer()
            writer({
                "llm_response": {
                    "content": content,
                    "model_name": model_name,
                    "is_complete": is_complete
                }
            })
            logger.debug(f"推送LLM响应: {content[:50]}...")
        except Exception as e:
            logger.warning(f"推送LLM响应失败: {e}")
    
    @staticmethod
    def push_error_info(error_message: str, error_code: str = "", source: str = "system"):
        """
        推送错误信息
        
        Args:
            error_message: 错误消息
            error_code: 错误代码
            source: 错误来源
        """
        try:
            writer = get_stream_writer()
            writer({
                "error_info": {
                    "error_message": error_message,
                    "error_code": error_code,
                    "source": source
                }
            })
            logger.debug(f"推送错误信息: {error_message}")
        except Exception as e:
            logger.warning(f"推送错误信息失败: {e}")
    
    @staticmethod
    def push_analysis_result(result_type: str, result_data: Dict[str, Any], confidence: float = 0.0):
        """
        推送分析结果
        
        Args:
            result_type: 结果类型（geological, chemical, isotope等）
            result_data: 结果数据
            confidence: 置信度（0.0-1.0）
        """
        try:
            writer = get_stream_writer()
            writer({
                "analysis_result": {
                    "result_type": result_type,
                    "result_data": result_data,
                    "confidence": confidence
                }
            })
            logger.debug(f"推送分析结果: {result_type}")
        except Exception as e:
            logger.warning(f"推送分析结果失败: {e}")
    
    @staticmethod
    def push_custom_message(message_type: str, data: Dict[str, Any]):
        """
        推送自定义消息
        
        Args:
            message_type: 消息类型标识
            data: 消息数据
        """
        try:
            writer = get_stream_writer()
            writer({
                message_type: data
            })
            logger.debug(f"推送自定义消息: {message_type}")
        except Exception as e:
            logger.warning(f"推送自定义消息失败: {e}")


# 便捷函数，可以直接导入使用
def push_thinking(agent_name: str, content: str, thinking_type: str = "analysis"):
    """便捷函数：推送Agent思考"""
    LangGraphStreamWriter.push_agent_thinking(agent_name, content, thinking_type)

def push_node_start(node_name: str, details: str = ""):
    """便捷函数：推送节点开始执行"""
    LangGraphStreamWriter.push_node_execution(node_name, "start", "started", details)

def push_node_complete(node_name: str, details: str = ""):
    """便捷函数：推送节点执行完成"""
    LangGraphStreamWriter.push_node_execution(node_name, "complete", "completed", details)

def push_node_error(node_name: str, error_msg: str):
    """便捷函数：推送节点执行错误"""
    LangGraphStreamWriter.push_node_execution(node_name, "error", "error", error_msg)

def push_route(from_node: str, to_node: str, reason: str = ""):
    """便捷函数：推送路由决策"""
    LangGraphStreamWriter.push_route_decision(from_node, to_node, reason)

def push_progress(tool_name: str, progress: float, details: str = ""):
    """便捷函数：推送工具进度"""
    LangGraphStreamWriter.push_tool_progress(tool_name, progress, details)

def push_file(file_id: str, file_name: str, file_path: str, file_type: str = "unknown"):
    """便捷函数：推送文件生成"""
    LangGraphStreamWriter.push_file_generated(file_id, file_name, file_path, file_type)

def push_error(error_message: str, source: str = "system"):
    """便捷函数：推送错误信息"""
    LangGraphStreamWriter.push_error_info(error_message, source=source) 