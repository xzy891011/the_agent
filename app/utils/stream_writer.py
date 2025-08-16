"""
流写入器工具模块
提供获取LangGraph流写入器的工具函数
"""

import logging
from typing import Optional, Any, Dict

logger = logging.getLogger(__name__)

def get_stream_writer() -> Optional[Any]:
    """获取LangGraph流写入器
    
    Returns:
        流写入器实例，如果不在LangGraph上下文中则返回None
    """
    try:
        from langgraph.config import get_stream_writer as langgraph_get_stream_writer
        return langgraph_get_stream_writer()
    except ImportError:
        logger.warning("LangGraph未安装或版本不支持get_stream_writer")
        return None
    except Exception as e:
        logger.debug(f"获取流写入器失败: {str(e)}")
        return None

def write_to_stream(data: Dict[str, Any]) -> bool:
    """写入数据到流
    
    Args:
        data: 要写入的数据
        
    Returns:
        是否成功写入
    """
    try:
        writer = get_stream_writer()
        if writer:
            writer(data)
            return True
        return False
    except Exception as e:
        logger.error(f"写入流数据失败: {str(e)}")
        return False 