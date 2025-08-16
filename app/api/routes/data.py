"""
数据管理API路由 - 处理数据统计和质量检查相关的HTTP请求

功能包括：
1. 数据统计信息
2. 数据质量评估
3. 数据清理建议
4. 数据可视化支持
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, date
from fastapi import APIRouter, HTTPException, Depends

from app.core.engine import IsotopeEngine
from app.api.dependencies import get_engine
from app.api.models import APIResponse

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/statistics", response_model=APIResponse)
async def get_data_statistics(
    session_id: Optional[str] = None,
    engine: IsotopeEngine = Depends(get_engine)
):
    """获取数据统计信息
    
    Args:
        session_id: 可选的会话ID过滤
        engine: 引擎实例
        
    Returns:
        数据统计信息
    """
    try:
        # 获取文件列表
        if session_id:
            files = engine.get_session_files(session_id)
        else:
            files = []
            for sid in engine.sessions:
                files.extend(engine.get_session_files(sid))
        
        # 计算统计信息
        total_files = len(files)
        file_types = {}
        total_size = 0
        uploaded_today = 0
        generated_today = 0
        
        today = date.today()
        
        for file_info in files:
            # 文件类型统计
            file_name = file_info.get("file_name", "")
            extension = file_name.split('.')[-1].lower() if '.' in file_name else 'unknown'
            file_types[extension] = file_types.get(extension, 0) + 1
            
            # 大小统计
            size = file_info.get("size", 0)
            if isinstance(size, (int, float)):
                total_size += size
            
            # 今日文件统计
            upload_time = file_info.get("upload_time", "")
            try:
                if upload_time:
                    file_date = datetime.fromisoformat(upload_time.replace('Z', '+00:00')).date()
                    if file_date == today:
                        if file_info.get("is_generated", False):
                            generated_today += 1
                        else:
                            uploaded_today += 1
            except (ValueError, AttributeError):
                pass
        
        statistics = {
            "total_files": total_files,
            "file_types": file_types,
            "total_size": total_size,
            "uploaded_today": uploaded_today,
            "generated_today": generated_today,
            "sessions_count": len(engine.sessions) if engine.sessions else 0
        }
        
        return APIResponse(
            success=True,
            message="数据统计信息获取成功",
            data=statistics
        )
        
    except Exception as e:
        logger.error(f"获取数据统计失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取数据统计失败: {str(e)}")

@router.get("/quality", response_model=APIResponse)
async def get_data_quality(
    session_id: Optional[str] = None,
    engine: IsotopeEngine = Depends(get_engine)
):
    """获取数据质量评估
    
    Args:
        session_id: 可选的会话ID过滤
        engine: 引擎实例
        
    Returns:
        数据质量评估信息
    """
    try:
        # 获取文件列表
        if session_id:
            files = engine.get_session_files(session_id)
        else:
            files = []
            for sid in engine.sessions:
                files.extend(engine.get_session_files(sid))
        
        # 简单的数据质量评估逻辑
        total_files = len(files)
        
        if total_files == 0:
            # 如果没有文件，返回默认质量评估
            quality_data = {
                "completeness": 100.0,
                "accuracy": 100.0,
                "consistency": 100.0,
                "validity": 100.0,
                "issues": [],
                "recommendations": ["建议上传一些数据文件进行分析"]
            }
        else:
            # 基于文件数量和类型的质量评估
            completeness = min(95, 70 + (total_files * 2))
            
            # 检查文件名规范性
            valid_names = 0
            name_issues = []
            for file_info in files:
                file_name = file_info.get("file_name", "")
                if file_name and not file_name.startswith('.') and len(file_name) > 3:
                    valid_names += 1
                else:
                    name_issues.append(f"文件名不规范: {file_name}")
            
            accuracy = (valid_names / total_files * 100) if total_files > 0 else 100
            
            # 检查文件类型一致性
            expected_types = {'las', 'csv', 'xlsx', 'png', 'jpg', 'pdf', 'txt', 'json'}
            actual_types = set()
            type_issues = []
            for file_info in files:
                file_name = file_info.get("file_name", "")
                if '.' in file_name:
                    extension = file_name.split('.')[-1].lower()
                    actual_types.add(extension)
                    if extension not in expected_types:
                        type_issues.append(f"未知文件类型: {extension}")
            
            consistency = min(95, len(actual_types & expected_types) / len(expected_types) * 100) if expected_types else 100
            
            # 文件大小有效性检查
            valid_sizes = 0
            size_issues = []
            for file_info in files:
                size = file_info.get("size", 0)
                if isinstance(size, (int, float)) and size > 0:
                    valid_sizes += 1
                else:
                    size_issues.append(f"文件大小异常: {file_info.get('file_name', 'unknown')}")
            
            validity = (valid_sizes / total_files * 100) if total_files > 0 else 100
            
            # 收集所有问题
            issues = name_issues + type_issues + size_issues
            
            # 生成建议
            recommendations = []
            if accuracy < 90:
                recommendations.append("建议检查和修正文件命名规范")
            if consistency < 80:
                recommendations.append("建议统一文件格式，使用标准的地质数据格式")
            if validity < 90:
                recommendations.append("建议检查文件完整性，重新上传损坏的文件")
            if completeness < 80:
                recommendations.append("建议增加更多数据文件以提高分析完整性")
            
            if not recommendations:
                recommendations.append("数据质量良好，可以继续分析")
            
            quality_data = {
                "completeness": completeness,
                "accuracy": min(98, accuracy),
                "consistency": min(92, consistency),
                "validity": min(96, validity),
                "issues": issues[:10],  # 限制问题数量
                "recommendations": recommendations
            }
        
        return APIResponse(
            success=True,
            message="数据质量评估完成",
            data=quality_data
        )
        
    except Exception as e:
        logger.error(f"数据质量评估失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"数据质量评估失败: {str(e)}")

@router.get("/summary", response_model=APIResponse)
async def get_data_summary(
    session_id: Optional[str] = None,
    engine: IsotopeEngine = Depends(get_engine)
):
    """获取数据摘要信息
    
    Args:
        session_id: 可选的会话ID过滤
        engine: 引擎实例
        
    Returns:
        数据摘要信息
    """
    try:
        # 获取文件列表
        if session_id:
            files = engine.get_session_files(session_id)
            sessions_count = 1
        else:
            files = []
            for sid in engine.sessions:
                files.extend(engine.get_session_files(sid))
            sessions_count = len(engine.sessions)
        
        # 计算各种统计
        file_types_count = {}
        total_size = 0
        earliest_upload = None
        latest_upload = None
        
        for file_info in files:
            # 文件类型统计
            file_name = file_info.get("file_name", "")
            extension = file_name.split('.')[-1].lower() if '.' in file_name else 'unknown'
            file_types_count[extension] = file_types_count.get(extension, 0) + 1
            
            # 大小统计
            size = file_info.get("size", 0)
            if isinstance(size, (int, float)):
                total_size += size
            
            # 时间统计
            upload_time = file_info.get("upload_time", "")
            try:
                if upload_time:
                    dt = datetime.fromisoformat(upload_time.replace('Z', '+00:00'))
                    if earliest_upload is None or dt < earliest_upload:
                        earliest_upload = dt
                    if latest_upload is None or dt > latest_upload:
                        latest_upload = dt
            except (ValueError, AttributeError):
                pass
        
        # 格式化文件大小
        def format_file_size(bytes_size):
            for unit in ['B', 'KB', 'MB', 'GB']:
                if bytes_size < 1024:
                    return f"{bytes_size:.1f} {unit}"
                bytes_size /= 1024
            return f"{bytes_size:.1f} TB"
        
        summary = {
            "overview": {
                "total_files": len(files),
                "total_sessions": sessions_count,
                "total_size": total_size,
                "total_size_formatted": format_file_size(total_size)
            },
            "file_types": file_types_count,
            "time_range": {
                "earliest_upload": earliest_upload.isoformat() if earliest_upload else None,
                "latest_upload": latest_upload.isoformat() if latest_upload else None
            },
            "recommendations": [
                "定期备份重要数据文件",
                "建议使用标准化的文件命名规范",
                "考虑对大文件进行压缩存储"
            ]
        }
        
        return APIResponse(
            success=True,
            message="数据摘要获取成功",
            data=summary
        )
        
    except Exception as e:
        logger.error(f"获取数据摘要失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取数据摘要失败: {str(e)}")

@router.post("/cleanup", response_model=APIResponse)
async def cleanup_data(
    session_id: Optional[str] = None,
    dry_run: bool = True,
    engine: IsotopeEngine = Depends(get_engine)
):
    """数据清理操作
    
    Args:
        session_id: 可选的会话ID过滤
        dry_run: 是否只是预览清理结果
        engine: 引擎实例
        
    Returns:
        清理结果
    """
    try:
        # 获取文件列表
        if session_id:
            files = engine.get_session_files(session_id)
        else:
            files = []
            for sid in engine.sessions:
                files.extend(engine.get_session_files(sid))
        
        # 找出需要清理的文件
        cleanup_candidates = []
        
        for file_info in files:
            file_name = file_info.get("file_name", "")
            size = file_info.get("size", 0)
            
            # 检查是否为临时文件或重复文件
            if (file_name.startswith('temp_') or 
                file_name.startswith('.') or 
                file_name.endswith('.tmp') or
                size == 0):
                cleanup_candidates.append({
                    "file_id": file_info.get("file_id"),
                    "file_name": file_name,
                    "reason": "临时文件或空文件"
                })
        
        if not dry_run and cleanup_candidates:
            # 实际执行清理
            cleaned_count = 0
            for candidate in cleanup_candidates:
                try:
                    success = engine.delete_file(candidate["file_id"], session_id)
                    if success:
                        cleaned_count += 1
                except:
                    pass
            
            result_message = f"清理完成，删除了{cleaned_count}个文件"
        else:
            result_message = f"发现{len(cleanup_candidates)}个文件可以清理"
        
        return APIResponse(
            success=True,
            message=result_message,
            data={
                "cleanup_candidates": cleanup_candidates,
                "dry_run": dry_run,
                "total_candidates": len(cleanup_candidates)
            }
        )
        
    except Exception as e:
        logger.error(f"数据清理失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"数据清理失败: {str(e)}") 