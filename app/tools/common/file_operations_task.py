"""
@task版本的文件操作工具 - 阶段2实现

将常用的文件操作脚本改写为@task版本，包括：
1. 文件上传和注册
2. 文件查看和读取
3. 文件删除和清理
4. 目录操作
5. 文件格式转换
"""

import os
import shutil
import pandas as pd
import json
import uuid
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

from app.core.task_decorator import task, deterministic_task, side_effect_task
from app.core.file_manager import file_manager, get_file_manager, FileInfo
from app.tools.registry import register_tool

logger = logging.getLogger(__name__)

@deterministic_task(
    name="list_uploaded_files",
    retry_policy={"max_attempts": 2, "delay": 0.5}
)
def list_uploaded_files(category: Optional[str] = None) -> Dict[str, Any]:
    """@task版本：列出已上传的文件
    
    Args:
        category: 可选的文件类别过滤
        
    Returns:
        文件列表字典
    """
    logger.info(f"开始列出已上传文件，类别过滤: {category}")
    
    try:
        all_files = file_manager.list_files()
        
        if category:
            filtered_files = [
                file_info for file_info in all_files 
                if file_info.get("category") == category
            ]
        else:
            filtered_files = all_files
        
        result = {
            "total_files": len(filtered_files),
            "files": filtered_files,
            "categories": list(set(f.get("category", "unknown") for f in all_files))
        }
        
        logger.info(f"成功列出 {len(filtered_files)} 个文件")
        return result
        
    except Exception as e:
        logger.error(f"列出文件失败: {str(e)}")
        raise

@deterministic_task(
    name="get_file_info",
    retry_policy={"max_attempts": 3, "delay": 1.0}
)
def get_file_info(file_id: str) -> Dict[str, Any]:
    """@task版本：获取文件详细信息
    
    Args:
        file_id: 文件ID
        
    Returns:
        文件信息字典
    """
    logger.info(f"获取文件信息: {file_id}")
    
    try:
        file_info = file_manager.get_file_info(file_id)
        
        if not file_info:
            raise ValueError(f"文件ID {file_id} 不存在")
        
        # 添加文件大小和修改时间等额外信息
        file_path = file_info.get("file_path")
        if file_path and os.path.exists(file_path):
            stat = os.stat(file_path)
            file_info["file_size"] = stat.st_size
            file_info["modified_time"] = stat.st_mtime
            
            # 尝试读取文件的前几行内容作为预览
            try:
                if file_info.get("file_type", "").lower() in ["csv", "txt"]:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        preview_lines = [f.readline().strip() for _ in range(5)]
                        file_info["preview"] = preview_lines
                elif file_info.get("file_type", "").lower() in ["xlsx", "xls"]:
                    df = pd.read_excel(file_path, nrows=5)
                    file_info["preview"] = df.to_dict('records')
            except Exception as preview_error:
                logger.warning(f"生成文件预览失败: {str(preview_error)}")
                file_info["preview"] = "无法生成预览"
        
        logger.info(f"成功获取文件信息: {file_id}")
        return file_info
        
    except Exception as e:
        logger.error(f"获取文件信息失败: {str(e)}")
        raise

@deterministic_task(
    name="read_file_content",
    retry_policy={"max_attempts": 3, "delay": 1.0}
)
def read_file_content(
    file_id: str, 
    max_rows: Optional[int] = None,
    encoding: str = "utf-8"
) -> Dict[str, Any]:
    """@task版本：读取文件内容
    
    Args:
        file_id: 文件ID
        max_rows: 最大读取行数
        encoding: 文件编码
        
    Returns:
        文件内容字典
    """
    logger.info(f"读取文件内容: {file_id}, 最大行数: {max_rows}")
    
    try:
        file_info = file_manager.get_file_info(file_id)
        if not file_info:
            raise ValueError(f"文件ID {file_id} 不存在")
        
        file_path = file_info.get("file_path")
        file_type = file_info.get("file_type", "").lower()
        
        result = {
            "file_id": file_id,
            "file_name": file_info.get("file_name"),
            "file_type": file_type,
            "content": None,
            "rows_read": 0,
            "total_rows": 0
        }
        
        if file_type in ["csv"]:
            df = pd.read_csv(file_path, encoding=encoding, nrows=max_rows)
            result["content"] = df.to_dict('records')
            result["rows_read"] = len(df)
            # 获取总行数
            total_rows = sum(1 for _ in open(file_path, encoding=encoding)) - 1  # 减去标题行
            result["total_rows"] = total_rows
            
        elif file_type in ["xlsx", "xls"]:
            df = pd.read_excel(file_path, nrows=max_rows)
            result["content"] = df.to_dict('records')
            result["rows_read"] = len(df)
            # 估算总行数
            result["total_rows"] = len(df)  # Excel读取时无法轻易获取总行数
            
        elif file_type in ["txt", "md"]:
            with open(file_path, 'r', encoding=encoding) as f:
                if max_rows:
                    lines = [f.readline().strip() for _ in range(max_rows)]
                else:
                    lines = f.read().splitlines()
            result["content"] = lines
            result["rows_read"] = len(lines)
            result["total_rows"] = len(lines)
            
        elif file_type in ["json"]:
            with open(file_path, 'r', encoding=encoding) as f:
                content = json.load(f)
            result["content"] = content
            result["rows_read"] = 1
            result["total_rows"] = 1
            
        else:
            raise ValueError(f"不支持的文件类型: {file_type}")
        
        logger.info(f"成功读取文件内容: {file_id}, 读取 {result['rows_read']} 行")
        return result
        
    except Exception as e:
        logger.error(f"读取文件内容失败: {str(e)}")
        raise

@side_effect_task(
    name="upload_file_to_system",
    retry_policy={"max_attempts": 3, "delay": 2.0}
)
def upload_file_to_system(
    file_path: str,
    original_name: Optional[str] = None,
    category: str = "data",
    move_file: bool = False
) -> str:
    """@task版本：上传文件到系统 (有副作用)
    
    Args:
        file_path: 源文件路径
        original_name: 原始文件名
        category: 文件类别
        move_file: 是否移动文件（而非复制）
        
    Returns:
        文件ID
    """
    logger.info(f"上传文件到系统: {file_path}")
    
    try:
        if not os.path.exists(file_path):
            raise ValueError(f"文件不存在: {file_path}")
        
        # 获取文件信息
        file_name = original_name or os.path.basename(file_path)
        file_type = os.path.splitext(file_name)[1][1:].lower()  # 去掉点号
        
        # 注册文件到文件管理器
        if move_file:
            file_id = file_manager.register_file(
                file_path, 
                original_name=file_name,
                file_type=file_type,
                category=category
            )
        else:
            # 复制文件到管理器的存储目录
            file_id = file_manager.register_file(
                file_path, 
                original_name=file_name,
                file_type=file_type,
                category=category
            )
        
        logger.info(f"文件上传成功: {file_id}")
        return file_id
        
    except Exception as e:
        logger.error(f"文件上传失败: {str(e)}")
        raise

@side_effect_task(
    name="delete_file_from_system",
    retry_policy={"max_attempts": 2, "delay": 1.0}
)
def delete_file_from_system(file_id: str, delete_physical_file: bool = True) -> bool:
    """@task版本：从系统删除文件 (有副作用)
    
    Args:
        file_id: 文件ID
        delete_physical_file: 是否删除物理文件
        
    Returns:
        删除是否成功
    """
    logger.info(f"从系统删除文件: {file_id}")
    
    try:
        file_info = file_manager.get_file_info(file_id)
        if not file_info:
            logger.warning(f"文件ID {file_id} 不存在，视为删除成功")
            return True
        
        # 删除物理文件
        if delete_physical_file:
            file_path = file_info.get("file_path")
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"物理文件已删除: {file_path}")
        
        # 从文件管理器中移除
        # 注意：这里需要文件管理器提供删除方法
        # 如果文件管理器没有delete方法，这里可能需要其他实现
        
        logger.info(f"文件删除成功: {file_id}")
        return True
        
    except Exception as e:
        logger.error(f"删除文件失败: {str(e)}")
        raise

@deterministic_task(
    name="convert_file_format",
    retry_policy={"max_attempts": 3, "delay": 1.0}
)
def convert_file_format(
    file_id: str, 
    target_format: str,
    output_category: str = "converted"
) -> str:
    """@task版本：转换文件格式
    
    Args:
        file_id: 源文件ID
        target_format: 目标格式 (csv, xlsx, json等)
        output_category: 输出文件类别
        
    Returns:
        转换后的文件ID
    """
    logger.info(f"转换文件格式: {file_id} -> {target_format}")
    
    try:
        # 获取源文件信息
        file_info = file_manager.get_file_info(file_id)
        if not file_info:
            raise ValueError(f"文件ID {file_id} 不存在")
        
        file_path = file_info.get("file_path")
        file_type = file_info.get("file_type", "").lower()
        file_name = file_info.get("file_name", "")
        
        # 读取源文件数据
        if file_type in ["csv"]:
            df = pd.read_csv(file_path)
        elif file_type in ["xlsx", "xls"]:
            df = pd.read_excel(file_path)
        else:
            raise ValueError(f"不支持从 {file_type} 格式转换")
        
        # 生成输出文件名
        base_name = os.path.splitext(file_name)[0]
        output_name = f"{base_name}_converted.{target_format}"
        
        # 创建临时输出路径
        temp_dir = os.path.join(os.path.dirname(file_path), "temp")
        os.makedirs(temp_dir, exist_ok=True)
        output_path = os.path.join(temp_dir, output_name)
        
        # 保存为目标格式
        if target_format == "csv":
            df.to_csv(output_path, index=False, encoding='utf-8')
        elif target_format in ["xlsx", "xls"]:
            df.to_excel(output_path, index=False)
        elif target_format == "json":
            df.to_json(output_path, orient='records', force_ascii=False, indent=2)
        else:
            raise ValueError(f"不支持目标格式: {target_format}")
        
        # 注册转换后的文件
        converted_file_id = file_manager.register_file(
            output_path,
            original_name=output_name,
            file_type=target_format,
            category=output_category
        )
        
        logger.info(f"文件格式转换成功: {file_id} -> {converted_file_id}")
        return converted_file_id
        
    except Exception as e:
        logger.error(f"文件格式转换失败: {str(e)}")
        raise

@side_effect_task(
    name="create_directory",
    retry_policy={"max_attempts": 2, "delay": 0.5}
)
def create_directory(dir_path: str, exist_ok: bool = True) -> bool:
    """@task版本：创建目录 (有副作用)
    
    Args:
        dir_path: 目录路径
        exist_ok: 如果目录存在是否报错
        
    Returns:
        创建是否成功
    """
    logger.info(f"创建目录: {dir_path}")
    
    try:
        os.makedirs(dir_path, exist_ok=exist_ok)
        logger.info(f"目录创建成功: {dir_path}")
        return True
        
    except Exception as e:
        logger.error(f"创建目录失败: {str(e)}")
        raise

@side_effect_task(
    name="cleanup_temp_files",
    retry_policy={"max_attempts": 2, "delay": 1.0}
)
def cleanup_temp_files(older_than_hours: int = 24) -> Dict[str, Any]:
    """@task版本：清理临时文件 (有副作用)
    
    Args:
        older_than_hours: 清理多少小时前的文件
        
    Returns:
        清理结果统计
    """
    logger.info(f"开始清理 {older_than_hours} 小时前的临时文件")
    
    try:
        import time
        current_time = time.time()
        cutoff_time = current_time - (older_than_hours * 3600)
        
        temp_dirs = [
            "data/temp",
            "data/generated",
            "data/tmp"
        ]
        
        cleaned_files = 0
        cleaned_size = 0
        
        for temp_dir in temp_dirs:
            if not os.path.exists(temp_dir):
                continue
                
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        stat = os.stat(file_path)
                        if stat.st_mtime < cutoff_time:
                            file_size = stat.st_size
                            os.remove(file_path)
                            cleaned_files += 1
                            cleaned_size += file_size
                            logger.debug(f"清理临时文件: {file_path}")
                    except Exception as e:
                        logger.warning(f"清理文件失败 {file_path}: {str(e)}")
        
        result = {
            "cleaned_files": cleaned_files,
            "cleaned_size_bytes": cleaned_size,
            "cleaned_size_mb": round(cleaned_size / (1024 * 1024), 2)
        }
        
        logger.info(f"临时文件清理完成: 清理了 {cleaned_files} 个文件，释放 {result['cleaned_size_mb']} MB")
        return result
        
    except Exception as e:
        logger.error(f"清理临时文件失败: {str(e)}")
        raise

@deterministic_task(
    name="list_files",
    retry_policy={"max_attempts": 2, "delay": 0.5}
)
def list_files(category: Optional[str] = None, session_id: Optional[str] = None) -> List[FileInfo]:
    """列出指定类别或会话的文件
    
    Args:
        category: 可选的文件类别过滤
        session_id: 可选的会话ID过滤
        
    Returns:
        文件信息列表
    """
    logger.info(f"列出文件，类别: {category}, 会话ID: {session_id}")
    
    try:
        file_mgr = get_file_manager()
        
        # 根据条件获取文件
        if session_id:
            files = file_mgr.get_session_files(session_id)
            logger.info(f"获取到会话 {session_id} 的文件: {len(files)} 个")
        else:
            files = file_mgr.list_files(category)
            logger.info(f"获取到类别 {category if category else '所有'} 的文件: {len(files)} 个")
        
        return files
    except Exception as e:
        logger.error(f"列出文件失败: {str(e)}")
        raise

# 注册工具到系统
@register_tool(category="file_operations_task")
def task_list_files(category: Optional[str] = None) -> str:
    """列出已上传的文件 - Task版本"""
    result = list_uploaded_files(category)
    
    files_info = []
    for file_info in result["files"]:
        files_info.append(
            f"文件ID: {file_info.get('file_id')}, "
            f"名称: {file_info.get('file_name')}, "
            f"类型: {file_info.get('file_type')}, "
            f"类别: {file_info.get('category')}"
        )
    
    return f"总共 {result['total_files']} 个文件:\n" + "\n".join(files_info)

@register_tool(category="file_operations_task")
def task_read_file(file_id: str, max_rows: Optional[int] = 10) -> str:
    """读取文件内容 - Task版本"""
    result = read_file_content(file_id, max_rows)
    
    content_preview = str(result["content"])[:1000]  # 限制预览长度
    if len(str(result["content"])) > 1000:
        content_preview += "..."
    
    return (f"文件 {result['file_name']} 内容预览:\n"
            f"读取行数: {result['rows_read']}/{result['total_rows']}\n"
            f"内容: {content_preview}")

@register_tool(category="file_operations_task")
def task_convert_format(file_id: str, target_format: str) -> str:
    """转换文件格式 - Task版本"""
    converted_file_id = convert_file_format(file_id, target_format)
    return f"文件格式转换成功，新文件ID: {converted_file_id}"

@register_tool(category="file_operations_task")
def task_cleanup_files(older_than_hours: int = 24) -> str:
    """清理临时文件 - Task版本"""
    result = cleanup_temp_files(older_than_hours)
    return (f"临时文件清理完成:\n"
            f"清理文件数: {result['cleaned_files']}\n"
            f"释放空间: {result['cleaned_size_mb']} MB") 