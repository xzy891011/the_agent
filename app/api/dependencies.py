"""
API依赖注入模块 - 处理常用的依赖注入功能

避免循环导入，提供独立的依赖注入函数
"""

from typing import Optional
from fastapi import HTTPException

from app.core.engine import IsotopeEngine

# 全局引擎实例 - 由main.py设置
_engine_instance: Optional[IsotopeEngine] = None

def set_engine(engine: IsotopeEngine) -> None:
    """设置全局引擎实例
    
    Args:
        engine: 引擎实例
    """
    global _engine_instance
    _engine_instance = engine

def get_engine() -> IsotopeEngine:
    """依赖注入 - 获取引擎实例
    
    Returns:
        引擎实例
        
    Raises:
        HTTPException: 如果引擎未初始化
    """
    if _engine_instance is None:
        raise HTTPException(status_code=503, detail="引擎未初始化")
    return _engine_instance 