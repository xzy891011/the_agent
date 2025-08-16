"""
文件管理API路由 - 处理文件相关的HTTP请求

功能包括：
1. 文件上传和下载
2. 文件列表和搜索
3. 文件元数据管理
4. 多模态文件处理
"""

import logging
import os
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.engine import IsotopeEngine
from app.core.file_manager_adapter import get_file_manager
from app.api.dependencies import get_engine
from app.api.models import (
    FileInfo,
    FileUploadResponse,
    FileListResponse,
    APIResponse,
    ErrorResponse,
    FileAssociateRequest
)

logger = logging.getLogger(__name__)

router = APIRouter()

# FileAssociateRequest 已在 app.api.models 中定义

@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
    engine: IsotopeEngine = Depends(get_engine)
):
    """上传文件
    
    Args:
        file: 上传的文件
        session_id: 关联的会话ID
        metadata: 文件元数据（JSON字符串）
        engine: 引擎实例
        
    Returns:
        文件上传结果
    """
    try:
        # 检查文件大小（限制为50MB）
        max_size = 50 * 1024 * 1024  # 50MB
        if file.size and file.size > max_size:
            raise HTTPException(status_code=413, detail="文件大小超过限制（50MB）")
        
        # 读取文件内容
        file_content = await file.read()
        
        # 解析元数据
        import json
        file_metadata = {}
        if metadata:
            try:
                file_metadata = json.loads(metadata)
            except json.JSONDecodeError:
                logger.warning("无法解析文件元数据，使用空字典")
        
        # 创建临时文件保存上传的内容
        import tempfile
        import uuid
        
        # 确保上传目录存在
        upload_dir = "data/uploads"
        os.makedirs(upload_dir, exist_ok=True)
        
        # 生成安全的文件名
        file_id = str(uuid.uuid4())
        safe_filename = f"{file_id}_{file.filename}"
        temp_file_path = os.path.join(upload_dir, safe_filename)
        
        # 保存文件内容
        with open(temp_file_path, "wb") as temp_file:
            temp_file.write(file_content)
        
        # 使用引擎添加文件到会话
        file_info = engine.add_file_to_session(
            file_path=temp_file_path,  # 传递实际的文件路径
            file_name=file.filename,
            session_id=session_id,
            file_type=None,  # 将自动推断
            metadata={
                **file_metadata,
                "content_type": file.content_type,
                "size": len(file_content)
            }
        )
        
        # 转换为API格式
        original_file_type = file_info.get("file_type", "other")
        normalized_file_type = normalize_file_type(original_file_type)
        
        # 处理upload_time字段，确保是有效的datetime
        upload_time = normalize_upload_time(file_info.get("upload_time"))
        
        api_file_info = FileInfo(
            file_id=file_info["file_id"],
            file_name=file_info["file_name"],
            file_type=normalized_file_type,
            file_size=len(file_content),
            content_type=file.content_type or "application/octet-stream",
            upload_time=upload_time,
            session_id=session_id,
            url=f"/api/v1/files/{file_info['file_id']}/download",
            metadata=file_info.get("metadata", {})
        )
        
        return FileUploadResponse(
            success=True,
            message="文件上传成功",
            data={"session_id": session_id},
            file_info=api_file_info
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件上传失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"文件上传失败: {str(e)}")

@router.get("/list", response_model=FileListResponse)
async def list_files(
    session_id: Optional[str] = None,
    file_type: Optional[str] = None,
    limit: Optional[int] = 50,
    offset: Optional[int] = 0,
    engine: IsotopeEngine = Depends(get_engine)
):
    """获取文件列表
    
    Args:
        session_id: 会话ID（可选，用于过滤）
        file_type: 文件类型（可选，用于过滤）
        limit: 返回数量限制
        offset: 偏移量
        engine: 引擎实例
        
    Returns:
        文件列表
    """
    try:
        # 获取文件管理器适配器
        file_manager_adapter = get_file_manager()
        
        # 获取文件列表
        if session_id:
            # 获取特定会话的文件
            files = file_manager_adapter.get_all_files(session_id=session_id)
        else:
            # 获取所有文件
            files = file_manager_adapter.get_all_files()
        
        # 按文件类型过滤
        if file_type:
            files = [f for f in files if f.get("file_type") == file_type]
        
        # 转换为API格式
        api_files = []
        for file_info in files:
            # 标准化文件类型
            original_file_type = file_info.get("file_type", "other")
            normalized_file_type = normalize_file_type(original_file_type)
            
            # 处理upload_time字段，确保是有效的datetime
            upload_time = normalize_upload_time(file_info.get("upload_time"))
            
            # 获取文件路径/文件夹路径 - 优先使用最新的位置信息
            # 注意：移动文件后，metadata.folder_path可能是旧的，需要从对象路径推断新位置
            file_path = ""
            if hasattr(file_manager_adapter, 'get_file_location'):
                # 如果文件管理器支持获取位置信息，优先使用
                try:
                    file_path = file_manager_adapter.get_file_location(file_info["file_id"])
                except:
                    pass
            
            # 如果没有获取到位置信息，尝试从file_info中获取
            if not file_path:
                file_path = file_info.get("file_path") or ""
            
            # 如果仍然没有，从metadata中获取（但可能是旧的）
            if not file_path:
                file_path = file_info.get("metadata", {}).get("folder_path") or file_info.get("metadata", {}).get("path") or ""
            
            api_file = FileInfo(
                file_id=file_info["file_id"],
                file_name=file_info["file_name"],
                file_type=normalized_file_type,
                file_size=file_info.get("size", 0),
                content_type=file_info.get("content_type", "application/octet-stream"),
                upload_time=upload_time,
                session_id=file_info.get("session_id"),
                url=f"/api/v1/files/{file_info['file_id']}/download",
                file_path=file_path,
                metadata=file_info.get("metadata", {})
            )
            api_files.append(api_file)
        
        # 排序（按上传时间倒序）
        api_files.sort(key=lambda x: x.upload_time, reverse=True)
        
        # 应用分页
        total_count = len(api_files)
        if offset:
            api_files = api_files[offset:]
        if limit:
            api_files = api_files[:limit]
        
        return FileListResponse(
            success=True,
            message=f"获取到{len(api_files)}个文件",
            data={"total": total_count},
            files=api_files
        )
        
    except Exception as e:
        logger.error(f"获取文件列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取文件列表失败: {str(e)}")

@router.get("/statistics", response_model=APIResponse)
async def get_file_statistics(
    session_id: Optional[str] = None,
    engine: IsotopeEngine = Depends(get_engine)
):
    """获取文件统计信息
    
    Args:
        session_id: 可选的会话ID过滤
        engine: 引擎实例
        
    Returns:
        文件统计信息
    """
    try:
        # 导入文件管理器
        from app.core.file_manager import file_manager
        
        # 获取文件列表
        if session_id:
            files = file_manager.get_session_files(session_id)
        else:
            files = file_manager.get_all_files()
        
        # 计算统计信息
        total_files = len(files)
        file_types = {}
        total_size = 0
        uploaded_today = 0
        generated_today = 0
        
        from datetime import datetime, date
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
            "generated_today": generated_today
        }
        
        return APIResponse(
            success=True,
            message="文件统计信息获取成功",
            data=statistics
        )
        
    except Exception as e:
        logger.error(f"获取文件统计失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取文件统计失败: {str(e)}")

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
        # 导入文件管理器
        from app.core.file_manager import file_manager
        
        # 获取文件列表
        if session_id:
            files = file_manager.get_session_files(session_id)
        else:
            files = file_manager.get_all_files()
        
        # 简单的数据质量评估逻辑
        total_files = len(files)
        
        # 基于文件数量和类型的质量评估
        completeness = min(95, 70 + (total_files * 2))  # 文件越多，完整性越高
        
        # 检查文件名规范性
        valid_names = 0
        for file_info in files:
            file_name = file_info.get("file_name", "")
            # 简单的文件名规范性检查
            if file_name and not file_name.startswith('.') and len(file_name) > 3:
                valid_names += 1
        
        accuracy = (valid_names / total_files * 100) if total_files > 0 else 100
        
        # 检查文件类型一致性
        expected_types = {'las', 'csv', 'xlsx', 'png', 'jpg', 'pdf'}
        actual_types = set()
        for file_info in files:
            file_name = file_info.get("file_name", "")
            if '.' in file_name:
                extension = file_name.split('.')[-1].lower()
                actual_types.add(extension)
        
        consistency = len(actual_types & expected_types) / len(expected_types) * 100 if expected_types else 100
        
        # 文件大小有效性检查
        valid_sizes = 0
        for file_info in files:
            size = file_info.get("size", 0)
            if isinstance(size, (int, float)) and size > 0:
                valid_sizes += 1
        
        validity = (valid_sizes / total_files * 100) if total_files > 0 else 100
        
        quality_data = {
            "completeness": completeness,
            "accuracy": min(98, accuracy),
            "consistency": min(92, consistency),
            "validity": min(96, validity)
        }
        
        return APIResponse(
            success=True,
            message="数据质量评估完成",
            data=quality_data
        )
        
    except Exception as e:
        logger.error(f"数据质量评估失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"数据质量评估失败: {str(e)}")

@router.get("/search/{query}", response_model=FileListResponse)
async def search_files(
    query: str,
    session_id: Optional[str] = None,
    file_type: Optional[str] = None,
    limit: Optional[int] = 20,
    engine: IsotopeEngine = Depends(get_engine)
):
    """搜索文件
    
    Args:
        query: 搜索查询
        session_id: 会话ID（可选，用于限制搜索范围）
        file_type: 文件类型（可选，用于过滤）
        limit: 返回数量限制
        engine: 引擎实例
        
    Returns:
        搜索结果
    """
    try:
        # 获取文件管理器适配器
        file_manager_adapter = get_file_manager()
        
        # 导入文件管理器
        from app.core.file_manager import file_manager
        
        # 使用文件管理器的搜索功能
        matched_files = file_manager.search_files(query, session_id)
        
        # 按文件类型过滤
        if file_type:
            matched_files = [f for f in matched_files if f.get("file_type") == file_type]
        
        # 转换为API格式
        api_files = []
        for file_info in matched_files:
            # 标准化文件类型
            original_file_type = file_info.get("file_type", "other")
            normalized_file_type = normalize_file_type(original_file_type)
            
            # 处理upload_time字段，确保是有效的datetime
            upload_time = normalize_upload_time(file_info.get("upload_time"))
            
            # 获取文件路径/文件夹路径 - 优先使用最新的位置信息
            # 注意：移动文件后，metadata.folder_path可能是旧的，需要从对象路径推断新位置
            file_path = ""
            if hasattr(file_manager_adapter, 'get_file_location'):
                # 如果文件管理器支持获取位置信息，优先使用
                try:
                    file_path = file_manager_adapter.get_file_location(file_info["file_id"])
                except:
                    pass
            
            # 如果没有获取到位置信息，尝试从file_info中获取
            if not file_path:
                file_path = file_info.get("file_path") or ""
            
            # 如果仍然没有，从metadata中获取（但可能是旧的）
            if not file_path:
                file_path = file_info.get("metadata", {}).get("folder_path") or file_info.get("metadata", {}).get("path") or ""
            
            api_file = FileInfo(
                file_id=file_info["file_id"],
                file_name=file_info["file_name"],
                file_type=normalized_file_type,
                file_size=file_info.get("size", 0),
                content_type=file_info.get("content_type", "application/octet-stream"),
                upload_time=upload_time,
                session_id=file_info.get("session_id"),
                url=f"/api/v1/files/{file_info['file_id']}/download",
                file_path=file_path,
                metadata=file_info.get("metadata", {})
            )
            api_files.append(api_file)
        
        # 限制结果数量
        if limit:
            api_files = api_files[:limit]
        
        return FileListResponse(
            success=True,
            message=f"搜索到{len(api_files)}个文件",
            data={"query": query, "total": len(matched_files)},
            files=api_files
        )
        
    except Exception as e:
        logger.error(f"搜索文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"搜索文件失败: {str(e)}")

@router.post("/batch-download", response_model=APIResponse)
async def batch_download_files(
    file_ids: List[str],
    engine: IsotopeEngine = Depends(get_engine)
):
    """批量下载文件
    
    Args:
        file_ids: 文件ID列表
        engine: 引擎实例
        
    Returns:
        批量下载结果（返回下载链接）
    """
    try:
        download_links = []
        
        for file_id in file_ids:
            file_info = engine.get_file_info(file_id)
            if file_info:
                download_links.append({
                    "file_id": file_id,
                    "file_name": file_info["file_name"],
                    "download_url": f"/api/v1/files/{file_id}/download"
                })
        
        return APIResponse(
            success=True,
            message=f"生成了{len(download_links)}个文件的下载链接",
            data={"download_links": download_links}
        )
        
    except Exception as e:
        logger.error(f"批量下载失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"批量下载失败: {str(e)}")

@router.post("/{file_id}/associate", response_model=APIResponse)
async def associate_file_to_session(
    file_id: str,
    request: FileAssociateRequest,
    engine: IsotopeEngine = Depends(get_engine)
):
    """将文件关联到指定会话
    
    Args:
        file_id: 文件ID
        request: 包含目标会话ID的请求体
        engine: 引擎实例
        
    Returns:
        关联结果
    """
    try:
        # 获取文件信息
        file_info = engine.get_file_info(file_id)
        if not file_info:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        # 检查目标会话是否存在
        target_session = engine.get_session_by_id(request.target_session_id)
        if not target_session:
            raise HTTPException(status_code=404, detail="目标会话不存在")
        
        # 导入文件管理器来更新文件的会话关联
        from app.core.file_manager import file_manager
        
        # 更新文件索引中的session_id
        if file_id in file_manager.file_index:
            # 更新索引
            file_manager.file_index[file_id]["session_id"] = request.target_session_id
            
            # 强制保存索引，确保持久化
            try:
                file_manager._save_index()
                logger.info(f"文件索引已保存，文件 {file_id} 关联到会话 {request.target_session_id}")
            except Exception as save_error:
                logger.error(f"保存文件索引失败: {str(save_error)}")
                raise HTTPException(status_code=500, detail="保存文件索引失败")
            
            # 同时更新引擎中的会话状态
            try:
                state = engine.get_session_state(request.target_session_id)
                if state is not None:
                    # 更新状态中的文件信息
                    files = state.get("files", {})
                    files[file_id] = file_manager.file_index[file_id]
                    
                    # 更新状态
                    state["files"] = files
                    
                    # 保存会话状态
                    engine._update_session_state(request.target_session_id, state)
                    logger.info(f"会话状态已更新，文件 {file_id} 添加到会话 {request.target_session_id}")
            except Exception as state_error:
                logger.error(f"更新会话状态失败: {str(state_error)}")
                # 会话状态更新失败不应该影响文件关联，只记录日志
            
            return APIResponse(
                success=True,
                message="文件关联成功",
                data={"file_id": file_id, "session_id": request.target_session_id}
            )
        else:
            raise HTTPException(status_code=404, detail="文件在索引中不存在")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件关联失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"文件关联失败: {str(e)}")

@router.get("/{file_id}", response_model=APIResponse)
async def get_file_info(
    file_id: str,
    engine: IsotopeEngine = Depends(get_engine)
):
    """获取文件信息
    
    Args:
        file_id: 文件ID
        engine: 引擎实例
        
    Returns:
        文件详细信息
    """
    try:
        # 使用文件管理器适配器获取文件信息（而不是引擎）
        file_manager_adapter = get_file_manager()
        
        try:
            all_files = file_manager_adapter.get_all_files()
            file_info = None
            for f in all_files:
                if f.get("file_id") == file_id:
                    file_info = f
                    break
            
            if not file_info:
                raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")
                
        except Exception as e:
            logger.error(f"检查文件存在性失败: {str(e)}")
            raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")
        
        # 转换为API格式
        original_file_type = file_info.get("file_type", "other")
        normalized_file_type = normalize_file_type(original_file_type)
        
        # 处理upload_time字段，确保是有效的datetime格式
        upload_time = normalize_upload_time(file_info.get("upload_time"))
        upload_time_str = upload_time.isoformat()
        
        # 获取文件路径/文件夹路径 - 优先使用最新的位置信息
        # 注意：移动文件后，metadata.folder_path可能是旧的，需要从对象路径推断新位置
        file_path = ""
        if hasattr(file_manager_adapter, 'get_file_location'):
            # 如果文件管理器支持获取位置信息，优先使用
            try:
                file_path = file_manager_adapter.get_file_location(file_info["file_id"])
            except:
                pass
        
        # 如果没有获取到位置信息，尝试从file_info中获取
        if not file_path:
            file_path = file_info.get("file_path") or ""
        
        # 如果仍然没有，从metadata中获取（但可能是旧的）
        if not file_path:
            file_path = file_info.get("metadata", {}).get("folder_path") or file_info.get("metadata", {}).get("path") or ""
        
        api_file_info = {
            "file_id": file_info["file_id"],
            "file_name": file_info["file_name"],
            "file_type": normalized_file_type,
            "file_size": file_info.get("size", 0),
            "content_type": file_info.get("content_type", "application/octet-stream"),
            "upload_time": upload_time_str,
            "session_id": file_info.get("session_id"),
            "file_path": file_path,
            "url": f"/api/v1/files/{file_id}/download",
            "metadata": file_info.get("metadata", {})
        }
        
        return APIResponse(
            success=True,
            message="文件信息获取成功",
            data=api_file_info
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文件信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取文件信息失败: {str(e)}")

@router.get("/{file_id}/download")
async def download_file(
    file_id: str,
    engine: IsotopeEngine = Depends(get_engine)
):
    """下载文件
    
    Args:
        file_id: 文件ID
        engine: 引擎实例
        
    Returns:
        文件下载响应
    """
    try:
        # 获取文件信息
        file_info = engine.get_file_info(file_id)
        if not file_info:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        file_path = file_info.get("file_path")
        if not file_path or not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="文件不存在于磁盘")
        
        # 返回文件响应
        return FileResponse(
            path=file_path,
            filename=file_info["file_name"],
            media_type=file_info.get("content_type", "application/octet-stream")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"下载文件失败: {str(e)}")

@router.delete("/{file_id}", response_model=APIResponse)
async def delete_file(
    file_id: str,
    session_id: Optional[str] = None,
    engine: IsotopeEngine = Depends(get_engine)
):
    """删除文件
    
    Args:
        file_id: 文件ID
        session_id: 会话ID（可选）
        engine: 引擎实例
        
    Returns:
        删除结果
    """
    try:
        file_manager_adapter = get_file_manager()
        
        # 使用文件管理器适配器检查文件是否存在（而不是引擎）
        try:
            all_files = file_manager_adapter.get_all_files()
            file_info = None
            for f in all_files:
                if f.get("file_id") == file_id:
                    file_info = f
                    break
            
            if not file_info:
                raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")
                
        except Exception as e:
            logger.error(f"检查文件存在性失败: {str(e)}")
            raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")
        
        # 检查是否支持删除操作
        if not hasattr(file_manager_adapter, 'delete_file'):
            raise HTTPException(status_code=501, detail="当前存储后端不支持文件删除")
        
        # 使用文件管理器适配器删除文件
        success = file_manager_adapter.delete_file(file_id)
        
        if success:
            return APIResponse(
                success=True,
                message=f"文件删除成功: {file_info['file_name']}",
                data={"file_id": file_id, "file_name": file_info["file_name"]}
            )
        else:
            raise HTTPException(status_code=500, detail="删除文件失败")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除文件失败: {str(e)}")

@router.put("/{file_id}/move", response_model=APIResponse)
async def move_file(
    file_id: str,
    target_folder: str = Form(...),
    engine: IsotopeEngine = Depends(get_engine)
):
    """移动文件到指定文件夹
    
    Args:
        file_id: 文件ID
        target_folder: 目标文件夹路径
        engine: 引擎实例
        
    Returns:
        移动结果
    """
    try:
        file_manager_adapter = get_file_manager()
        
        # 使用文件管理器适配器检查文件是否存在（而不是引擎）
        try:
            all_files = file_manager_adapter.get_all_files()
            file_info = None
            for f in all_files:
                if f.get("file_id") == file_id:
                    file_info = f
                    break
            
            if not file_info:
                raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")
                
        except Exception as e:
            logger.error(f"检查文件存在性失败: {str(e)}")
            raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")
        
        # 检查是否支持移动操作
        if not hasattr(file_manager_adapter, 'move_file'):
            raise HTTPException(status_code=501, detail="当前存储后端不支持文件移动")
        
        # 移动文件
        success = file_manager_adapter.move_file(file_id, target_folder)
        
        if success:
            return APIResponse(
                success=True,
                message=f"文件移动成功: {file_info['file_name']} -> {target_folder}",
                data={
                    "file_id": file_id,
                    "target_folder": target_folder,
                    "file_name": file_info["file_name"]
                }
            )
        else:
            raise HTTPException(status_code=500, detail="文件移动失败")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"移动文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"移动文件失败: {str(e)}")

@router.post("/{file_id}/copy", response_model=APIResponse)
async def copy_file(
    file_id: str,
    target_folder: str = Form(...),
    new_name: Optional[str] = Form(None),
    engine: IsotopeEngine = Depends(get_engine)
):
    """复制文件到指定文件夹
    
    Args:
        file_id: 文件ID
        target_folder: 目标文件夹路径
        new_name: 新文件名（可选，如果不提供则使用原文件名）
        engine: 引擎实例
        
    Returns:
        复制结果
    """
    try:
        file_manager_adapter = get_file_manager()
        
        # 使用文件管理器适配器检查文件是否存在（而不是引擎）
        try:
            all_files = file_manager_adapter.get_all_files()
            file_info = None
            for f in all_files:
                if f.get("file_id") == file_id:
                    file_info = f
                    break
            
            if not file_info:
                raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")
                
        except Exception as e:
            logger.error(f"检查文件存在性失败: {str(e)}")
            raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")
        
        # 检查是否支持复制操作
        if not hasattr(file_manager_adapter, 'copy_file'):
            raise HTTPException(status_code=501, detail="当前存储后端不支持文件复制")
        
        # 使用新文件名或原文件名
        final_name = new_name or file_info["file_name"]
        
        # 复制文件
        new_file_info = file_manager_adapter.copy_file(file_id, target_folder, final_name)
        
        if new_file_info:
            return APIResponse(
                success=True,
                message=f"文件复制成功: {file_info['file_name']} -> {target_folder}/{final_name}",
                data={
                    "original_file_id": file_id,
                    "new_file_id": new_file_info.get("file_id"),
                    "target_folder": target_folder,
                    "new_file_name": final_name
                }
            )
        else:
            raise HTTPException(status_code=500, detail="文件复制失败")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"复制文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"复制文件失败: {str(e)}")

@router.post("/folders/create", response_model=APIResponse)
async def create_folder(
    folder_path: str = Form(...),
    engine: IsotopeEngine = Depends(get_engine)
):
    """创建文件夹
    
    Args:
        folder_path: 文件夹路径
        engine: 引擎实例
        
    Returns:
        创建结果
    """
    try:
        file_manager_adapter = get_file_manager()
        
        # 检查是否支持文件夹操作
        if not hasattr(file_manager_adapter, 'create_folder'):
            raise HTTPException(status_code=501, detail="当前存储后端不支持文件夹操作")
        
        # 创建文件夹
        success = file_manager_adapter.create_folder(folder_path)
        
        if success:
            return APIResponse(
                success=True,
                message=f"文件夹创建成功: {folder_path}",
                data={"folder_path": folder_path}
            )
        else:
            raise HTTPException(status_code=500, detail="文件夹创建失败")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建文件夹失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建文件夹失败: {str(e)}")

@router.get("/folders/tree", response_model=APIResponse)
async def get_folder_tree(
    root_path: Optional[str] = "",
    engine: IsotopeEngine = Depends(get_engine)
):
    """获取文件夹树结构
    
    Args:
        root_path: 根路径
        engine: 引擎实例
        
    Returns:
        文件夹树结构
    """
    try:
        file_manager_adapter = get_file_manager()
        
        # 检查是否支持文件夹操作
        if not hasattr(file_manager_adapter, 'get_folder_tree'):
            # 如果不支持，从文件元数据中提取文件夹信息
            files = file_manager_adapter.get_all_files()
            
            # 提取所有唯一的文件夹路径
            folders = set()
            file_list = []
            
            for f in files:
                # 提取文件夹路径
                folder_path = f.get("metadata", {}).get("folder_path") or f.get("metadata", {}).get("path")
                if folder_path:
                    folders.add(folder_path)
                
                # 构建文件信息
                file_info = {
                    "file_id": f.get("file_id"),
                    "file_name": f.get("file_name"),
                    "size": f.get("size", 0),
                    "upload_time": f.get("upload_time"),
                    "metadata": f.get("metadata", {})
                }
                file_list.append(file_info)
            
            tree = {
                "folders": list(folders),  # 确保是数组格式
                "files": file_list
            }
        else:
            # 获取文件夹树
            tree = file_manager_adapter.get_folder_tree(root_path)
        
        return APIResponse(
            success=True,
            message="文件夹树获取成功",
            data=tree
        )
        
    except Exception as e:
        logger.error(f"获取文件夹树失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取文件夹树失败: {str(e)}")

@router.post("/migrate-to-minio", response_model=APIResponse)
async def migrate_to_minio(
    engine: IsotopeEngine = Depends(get_engine)
):
    """将本地文件迁移到MinIO
    
    Args:
        engine: 引擎实例
        
    Returns:
        迁移结果
    """
    try:
        file_manager_adapter = get_file_manager()
        
        # 检查是否支持迁移
        if not hasattr(file_manager_adapter, 'migrate_to_minio'):
            raise HTTPException(status_code=501, detail="当前配置不支持文件迁移")
        
        # 执行迁移
        migrated_count = file_manager_adapter.migrate_to_minio()
        
        return APIResponse(
            success=True,
            message=f"文件迁移完成，共迁移 {migrated_count} 个文件",
            data={"migrated_count": migrated_count}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件迁移失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"文件迁移失败: {str(e)}")

# 批量上传端点增加文件夹选择功能
@router.post("/batch-upload", response_model=APIResponse)
async def batch_upload_files(
    files: List[UploadFile] = File(...),
    session_id: Optional[str] = Form(None),
    folder_path: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
    engine: IsotopeEngine = Depends(get_engine)
):
    """批量上传文件
    
    Args:
        files: 上传的文件列表
        session_id: 关联的会话ID
        folder_path: 目标文件夹路径（仅MinIO支持）
        metadata: 文件元数据（JSON字符串）
        engine: 引擎实例
        
    Returns:
        批量上传结果
    """
    try:
        file_manager_adapter = get_file_manager()
        uploaded_files = []
        failed_files = []
        
        # 解析元数据
        import json
        file_metadata = {}
        if metadata:
            try:
                file_metadata = json.loads(metadata)
            except json.JSONDecodeError:
                logger.warning("无法解析文件元数据，使用空字典")
        
        for file in files:
            try:
                # 检查文件大小
                max_size = 50 * 1024 * 1024  # 50MB
                if file.size and file.size > max_size:
                    failed_files.append({
                        "filename": file.filename,
                        "error": "文件大小超过限制（50MB）"
                    })
                    continue
                
                # 读取文件内容
                file_content = await file.read()
                
                # 构建包含folder_path的元数据
                complete_metadata = {
                    **file_metadata,
                    "content_type": file.content_type,
                    "size": len(file_content)
                }
                
                # 如果指定了folder_path，添加到元数据中
                if folder_path:
                    complete_metadata["folder_path"] = folder_path
                    complete_metadata["path"] = folder_path
                
                # 使用file_manager_adapter保存文件
                if hasattr(file_manager_adapter, 'save_file'):
                    # MinIO存储
                    file_info = file_manager_adapter.save_file(
                        file_data=file_content,
                        file_name=file.filename,
                        source="upload",
                        session_id=session_id,
                        folder_path=folder_path,
                        metadata=complete_metadata
                    )
                else:
                    # 本地存储（向后兼容）
                    import tempfile
                    import uuid
                    
                    upload_dir = "data/uploads"
                    os.makedirs(upload_dir, exist_ok=True)
                    
                    file_id = str(uuid.uuid4())
                    safe_filename = f"{file_id}_{file.filename}"
                    temp_file_path = os.path.join(upload_dir, safe_filename)
                    
                    with open(temp_file_path, "wb") as temp_file:
                        temp_file.write(file_content)
                    
                    file_info = file_manager_adapter.register_file(
                        file_path=temp_file_path,
                        file_name=file.filename,
                        source="upload",
                        session_id=session_id,
                        metadata=complete_metadata
                    )
                
                uploaded_files.append({
                    "file_id": file_info["file_id"],
                    "file_name": file_info["file_name"],
                    "url": f"/api/v1/files/{file_info['file_id']}/download"
                })
                
            except Exception as e:
                failed_files.append({
                    "filename": file.filename,
                    "error": str(e)
                })
                logger.error(f"上传文件失败 {file.filename}: {str(e)}")
        
        return APIResponse(
            success=len(uploaded_files) > 0,
            message=f"成功上传 {len(uploaded_files)} 个文件，失败 {len(failed_files)} 个",
            data={
                "uploaded": uploaded_files,
                "failed": failed_files,
                "folder_path": folder_path
            }
        )
        
    except Exception as e:
        logger.error(f"批量上传失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"批量上传失败: {str(e)}")

def normalize_upload_time(upload_time_raw: any) -> datetime:
    """标准化upload_time字段，确保返回有效的timezone-naive datetime对象
    
    Args:
        upload_time_raw: 原始的upload_time值（可能是字符串、datetime或空值）
        
    Returns:
        标准化后的timezone-naive datetime对象
    """
    from datetime import datetime, timezone
    
    # 如果为空或空字符串，使用当前时间（naive）
    if not upload_time_raw or upload_time_raw == "":
        return datetime.now()
    
    # 如果已经是datetime对象
    if isinstance(upload_time_raw, datetime):
        # 如果是timezone-aware，转换为naive
        if upload_time_raw.tzinfo is not None:
            return upload_time_raw.replace(tzinfo=None)
        else:
            # 已经是naive，直接返回
            return upload_time_raw
    
    # 如果是字符串，尝试解析
    if isinstance(upload_time_raw, str):
        try:
            # 处理ISO格式的时间字符串
            if 'Z' in upload_time_raw or '+' in upload_time_raw or upload_time_raw.endswith('00:00'):
                # 包含时区信息，解析后转换为naive
                dt = datetime.fromisoformat(upload_time_raw.replace('Z', '+00:00'))
                return dt.replace(tzinfo=None)
            else:
                # 不包含时区信息，直接解析
                return datetime.fromisoformat(upload_time_raw)
        except (ValueError, AttributeError):
            # 解析失败，使用当前时间
            return datetime.now()
    
    # 其他类型，使用当前时间
    return datetime.now()

def normalize_file_type(file_type: str) -> str:
    """标准化文件类型，确保与API模型兼容
    
    Args:
        file_type: 原始文件类型（可能是扩展名或文件管理器类型）
        
    Returns:
        标准化后的文件类型，符合FileType枚举
    """
    # 将输入转换为小写
    file_type_lower = file_type.lower().strip()
    
    # 完整的映射表：各种可能的输入 -> API模型FileType枚举值
    type_mapping = {
        # 图片文件
        "png": "image",
        "jpg": "image", 
        "jpeg": "image",
        "gif": "image",
        "bmp": "image", 
        "svg": "image",
        "webp": "image",
        "tiff": "image",
        "tif": "image",
        "ico": "image",
        
        # 文档文件
        "pdf": "document",
        "doc": "document",
        "docx": "document", 
        "rtf": "document",
        "odt": "document",
        
        # 文本文件
        "txt": "text",
        "log": "text", 
        "conf": "text",
        "ini": "text",
        "cfg": "text",
        "md": "text",
        "markdown": "text",
        "readme": "text",
        
        # 代码文件
        "py": "code",
        "js": "code",
        "html": "code",
        "css": "code",
        "java": "code",
        "cpp": "code",
        "c": "code",
        "h": "code",
        "php": "code",
        "rb": "code",
        "go": "code",
        "rs": "code",
        "swift": "code",
        "kt": "code",
        "ts": "code",
        "jsx": "code",
        "tsx": "code",
        "vue": "code",
        "scss": "code",
        "sass": "code",
        "less": "code",
        "sql": "code",
        "json": "code",
        "xml": "code",
        "yaml": "code",
        "yml": "code",
        
        # 表格文件
        "xls": "spreadsheet",
        "xlsx": "spreadsheet",
        "csv": "spreadsheet",
        "tsv": "spreadsheet",
        "ods": "spreadsheet",
        
        # 演示文件
        "ppt": "presentation",
        "pptx": "presentation",
        "odp": "presentation",
        
        # 数据文件
        "db": "data",
        "sqlite": "data",
        "sqlite3": "data",
        "mdb": "data",
        "parquet": "data",
        "avro": "data",
        "las": "data",
        "well": "data",
        
        # 压缩文件
        "zip": "archive",
        "rar": "archive",
        "7z": "archive",
        "tar": "archive",
        "gz": "archive",
        "bz2": "archive",
        "xz": "archive",
        "tar.gz": "archive",
        "tar.bz2": "archive",
        
        # 文件管理器内部类型（已经是正确的枚举值）
        "image": "image",
        "document": "document", 
        "text": "text",
        "code": "code",
        "spreadsheet": "spreadsheet",
        "presentation": "presentation",
        "data": "data",
        "archive": "archive",
        "other": "other",
    }
    
    # 尝试映射
    mapped_type = type_mapping.get(file_type_lower)
    if mapped_type:
        return mapped_type
    
    # 如果没有找到映射，根据常见模式进行推断
    if any(ext in file_type_lower for ext in ["image", "img", "pic", "photo"]):
        return "image"
    elif any(ext in file_type_lower for ext in ["doc", "document", "paper"]):
        return "document"
    elif any(ext in file_type_lower for ext in ["text", "txt", "plain"]):
        return "text"
    elif any(ext in file_type_lower for ext in ["code", "script", "program"]):
        return "code"
    elif any(ext in file_type_lower for ext in ["sheet", "excel", "calc", "spreadsheet"]):
        return "spreadsheet"
    elif any(ext in file_type_lower for ext in ["presentation", "slide", "ppt"]):
        return "presentation"
    elif any(ext in file_type_lower for ext in ["data", "database", "db"]):
        return "data"
    elif any(ext in file_type_lower for ext in ["archive", "zip", "compress"]):
        return "archive"
    
    # 默认返回 "other"
    return "other"

# 新增：批量文件操作API
@router.post("/batch/move", response_model=APIResponse)
async def batch_move_files(
    file_ids: List[str] = Form(...),
    target_folder: str = Form(...),
    engine: IsotopeEngine = Depends(get_engine)
):
    """批量移动文件到指定文件夹
    
    Args:
        file_ids: 文件ID列表
        target_folder: 目标文件夹路径
        engine: 引擎实例
        
    Returns:
        批量移动结果
    """
    try:
        file_manager_adapter = get_file_manager()
        
        # 检查是否支持移动操作
        if not hasattr(file_manager_adapter, 'move_file'):
            raise HTTPException(status_code=501, detail="当前存储后端不支持文件移动")
        
        success_files = []
        failed_files = []
        
        for file_id in file_ids:
            try:
                # 使用文件管理器适配器检查文件是否存在（而不是引擎）
                try:
                    all_files = file_manager_adapter.get_all_files()
                    file_info = None
                    for f in all_files:
                        if f.get("file_id") == file_id:
                            file_info = f
                            break
                    
                    if not file_info:
                        failed_files.append({
                            "file_id": file_id,
                            "error": "文件不存在"
                        })
                        continue
                        
                except Exception as e:
                    logger.error(f"检查文件存在性失败: {str(e)}")
                    failed_files.append({
                        "file_id": file_id,
                        "error": f"检查文件失败: {str(e)}"
                    })
                    continue
                
                # 移动文件
                success = file_manager_adapter.move_file(file_id, target_folder)
                
                if success:
                    success_files.append({
                        "file_id": file_id,
                        "file_name": file_info["file_name"]
                    })
                else:
                    failed_files.append({
                        "file_id": file_id,
                        "file_name": file_info["file_name"],
                        "error": "移动失败"
                    })
                    
            except Exception as e:
                failed_files.append({
                    "file_id": file_id,
                    "error": str(e)
                })
        
        return APIResponse(
            success=len(success_files) > 0,
            message=f"成功移动 {len(success_files)} 个文件，失败 {len(failed_files)} 个",
            data={
                "target_folder": target_folder,
                "success": success_files,
                "failed": failed_files
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量移动文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"批量移动文件失败: {str(e)}")

@router.post("/batch/copy", response_model=APIResponse)
async def batch_copy_files(
    file_ids: List[str] = Form(...),
    target_folder: str = Form(...),
    engine: IsotopeEngine = Depends(get_engine)
):
    """批量复制文件到指定文件夹
    
    Args:
        file_ids: 文件ID列表
        target_folder: 目标文件夹路径
        engine: 引擎实例
        
    Returns:
        批量复制结果
    """
    try:
        file_manager_adapter = get_file_manager()
        
        # 检查是否支持复制操作
        if not hasattr(file_manager_adapter, 'copy_file'):
            raise HTTPException(status_code=501, detail="当前存储后端不支持文件复制")
        
        success_files = []
        failed_files = []
        
        for file_id in file_ids:
            try:
                # 检查文件是否存在
                file_info = engine.get_file_info(file_id)
                if not file_info:
                    failed_files.append({
                        "file_id": file_id,
                        "error": "文件不存在"
                    })
                    continue
                
                # 复制文件
                new_file_info = file_manager_adapter.copy_file(
                    file_id, 
                    target_folder, 
                    file_info["file_name"]
                )
                
                if new_file_info:
                    success_files.append({
                        "original_file_id": file_id,
                        "new_file_id": new_file_info.get("file_id"),
                        "file_name": file_info["file_name"]
                    })
                else:
                    failed_files.append({
                        "file_id": file_id,
                        "file_name": file_info["file_name"],
                        "error": "复制失败"
                    })
                    
            except Exception as e:
                failed_files.append({
                    "file_id": file_id,
                    "error": str(e)
                })
        
        return APIResponse(
            success=len(success_files) > 0,
            message=f"成功复制 {len(success_files)} 个文件，失败 {len(failed_files)} 个",
            data={
                "target_folder": target_folder,
                "success": success_files,
                "failed": failed_files
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量复制文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"批量复制文件失败: {str(e)}")

@router.post("/batch/delete", response_model=APIResponse)
async def batch_delete_files(
    file_ids: List[str] = Form(...),
    session_id: Optional[str] = Form(None),
    engine: IsotopeEngine = Depends(get_engine)
):
    """批量删除文件
    
    Args:
        file_ids: 文件ID列表
        session_id: 会话ID（可选）
        engine: 引擎实例
        
    Returns:
        批量删除结果
    """
    try:
        file_manager_adapter = get_file_manager()
        
        # 检查是否支持删除操作
        if not hasattr(file_manager_adapter, 'delete_file'):
            raise HTTPException(status_code=501, detail="当前存储后端不支持文件删除")
        
        success_files = []
        failed_files = []
        
        for file_id in file_ids:
            try:
                # 使用文件管理器适配器检查文件是否存在（而不是引擎）
                try:
                    all_files = file_manager_adapter.get_all_files()
                    file_info = None
                    for f in all_files:
                        if f.get("file_id") == file_id:
                            file_info = f
                            break
                    
                    if not file_info:
                        failed_files.append({
                            "file_id": file_id,
                            "error": "文件不存在"
                        })
                        continue
                        
                except Exception as e:
                    logger.error(f"检查文件存在性失败: {str(e)}")
                    failed_files.append({
                        "file_id": file_id,
                        "error": f"文件不存在: {file_id}"
                    })
                    continue
                
                # 使用文件管理器适配器删除文件
                success = file_manager_adapter.delete_file(file_id)
                
                if success:
                    success_files.append({
                        "file_id": file_id,
                        "file_name": file_info["file_name"]
                    })
                else:
                    failed_files.append({
                        "file_id": file_id,
                        "file_name": file_info["file_name"],
                        "error": "删除失败"
                    })
                    
            except Exception as e:
                failed_files.append({
                    "file_id": file_id,
                    "error": str(e)
                })
        
        return APIResponse(
            success=len(success_files) > 0,
            message=f"成功删除 {len(success_files)} 个文件，失败 {len(failed_files)} 个",
            data={
                "success": success_files,
                "failed": failed_files
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量删除文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"批量删除文件失败: {str(e)}")

# 新增：文件夹管理API
@router.delete("/folders/{folder_path:path}", response_model=APIResponse)
async def delete_folder(
    folder_path: str,
    recursive: bool = False,
    engine: IsotopeEngine = Depends(get_engine)
):
    """删除文件夹
    
    Args:
        folder_path: 文件夹路径
        recursive: 是否递归删除子文件夹和文件
        engine: 引擎实例
        
    Returns:
        删除结果
    """
    try:
        file_manager_adapter = get_file_manager()
        
        # 检查是否支持文件夹删除
        if not hasattr(file_manager_adapter, 'delete_folder'):
            raise HTTPException(status_code=501, detail="当前存储后端不支持文件夹删除")
        
        # 删除文件夹
        success = file_manager_adapter.delete_folder(folder_path, recursive)
        
        if success:
            return APIResponse(
                success=True,
                message=f"文件夹删除成功: {folder_path}",
                data={"folder_path": folder_path, "recursive": recursive}
            )
        else:
            raise HTTPException(status_code=500, detail="文件夹删除失败")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除文件夹失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除文件夹失败: {str(e)}")

@router.put("/folders/{folder_path:path}/move", response_model=APIResponse)
async def move_folder(
    folder_path: str,
    target_parent: str = Form(...),
    new_name: Optional[str] = Form(None),
    engine: IsotopeEngine = Depends(get_engine)
):
    """移动文件夹
    
    Args:
        folder_path: 源文件夹路径
        target_parent: 目标父文件夹路径
        new_name: 新文件夹名（可选）
        engine: 引擎实例
        
    Returns:
        移动结果
    """
    try:
        file_manager_adapter = get_file_manager()
        
        # 检查是否支持文件夹移动
        if not hasattr(file_manager_adapter, 'move_folder'):
            raise HTTPException(status_code=501, detail="当前存储后端不支持文件夹移动")
        
        # 移动文件夹
        success = file_manager_adapter.move_folder(folder_path, target_parent, new_name)
        
        if success:
            final_name = new_name or folder_path.split('/')[-1]
            target_path = f"{target_parent.rstrip('/')}/{final_name}"
            return APIResponse(
                success=True,
                message=f"文件夹移动成功: {folder_path} -> {target_path}",
                data={
                    "source_path": folder_path,
                    "target_path": target_path
                }
            )
        else:
            raise HTTPException(status_code=500, detail="文件夹移动失败")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"移动文件夹失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"移动文件夹失败: {str(e)}")

@router.post("/upload-to-folder", response_model=FileUploadResponse)
async def upload_to_folder(
    file: UploadFile = File(...),
    folder_path: str = Form(...),
    session_id: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
    engine: IsotopeEngine = Depends(get_engine)
):
    """上传文件到指定文件夹
    
    Args:
        file: 上传的文件
        folder_path: 目标文件夹路径
        session_id: 关联的会话ID
        metadata: 文件元数据（JSON字符串）
        engine: 引擎实例
        
    Returns:
        文件上传结果
    """
    try:
        file_manager_adapter = get_file_manager()
        
        # 检查文件大小
        max_size = 50 * 1024 * 1024  # 50MB
        if file.size and file.size > max_size:
            raise HTTPException(status_code=413, detail="文件大小超过限制（50MB）")
        
        # 读取文件内容
        file_content = await file.read()
        
        # 解析元数据
        import json
        file_metadata = {}
        if metadata:
            try:
                file_metadata = json.loads(metadata)
            except json.JSONDecodeError:
                logger.warning("无法解析文件元数据，使用空字典")
        
        # 使用file_manager_adapter保存文件到指定文件夹
        if hasattr(file_manager_adapter, 'save_file'):
            # MinIO存储，支持文件夹路径
            file_info = file_manager_adapter.save_file(
                file_data=file_content,
                file_name=file.filename,
                source="upload",
                session_id=session_id,
                folder_path=folder_path,
                metadata={
                    **file_metadata,
                    "content_type": file.content_type,
                    "size": len(file_content)
                }
            )
        else:
            # 本地存储（向后兼容）
            import tempfile
            import uuid
            
            upload_dir = os.path.join("data/uploads", folder_path)
            os.makedirs(upload_dir, exist_ok=True)
            
            file_id = str(uuid.uuid4())
            safe_filename = f"{file_id}_{file.filename}"
            temp_file_path = os.path.join(upload_dir, safe_filename)
            
            with open(temp_file_path, "wb") as temp_file:
                temp_file.write(file_content)
            
            file_info = engine.add_file_to_session(
                file_path=temp_file_path,
                file_name=file.filename,
                session_id=session_id,
                file_type=None,
                metadata={
                    **file_metadata,
                    "content_type": file.content_type,
                    "size": len(file_content),
                    "folder_path": folder_path
                }
            )
        
        # 转换为API格式
        original_file_type = file_info.get("file_type", "other")
        normalized_file_type = normalize_file_type(original_file_type)
        upload_time = normalize_upload_time(file_info.get("upload_time"))
        
        api_file_info = FileInfo(
            file_id=file_info["file_id"],
            file_name=file_info["file_name"],
            file_type=normalized_file_type,
            file_size=len(file_content),
            content_type=file.content_type or "application/octet-stream",
            upload_time=upload_time,
            session_id=session_id,
            url=f"/api/v1/files/{file_info['file_id']}/download",
            metadata=file_info.get("metadata", {})
        )
        
        return FileUploadResponse(
            success=True,
            message=f"文件上传成功到文件夹: {folder_path}",
            data={"session_id": session_id, "folder_path": folder_path},
            file_info=api_file_info
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传文件到文件夹失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"上传文件到文件夹失败: {str(e)}") 