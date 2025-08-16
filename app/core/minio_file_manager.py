"""
MinIO文件管理器 - 基于MinIO对象存储的文件管理系统
支持文件夹层级管理、自动分类、元数据存储等功能
"""

import os
import uuid
import json
import logging
import mimetypes
import io
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Union
from pathlib import Path
import threading
import urllib.parse
import base64

from minio import Minio
from minio.error import S3Error
from minio.commonconfig import CopySource

# 配置日志
logger = logging.getLogger(__name__)

class MinIOFileManager:
    """基于MinIO的文件管理器，支持文件夹层级和自动分类"""
    
    _instance = None
    _lock = threading.Lock()
    
    # 文件分类配置
    FILE_CATEGORIES = {
        "generated_charts": {
            "name": "生成图表",
            "path": "generated/charts",
            "filter": lambda meta: meta.get("category") == "analysis_result" and meta.get("file_type") == "image"
        },
        "generated_reports": {
            "name": "分析报告", 
            "path": "generated/reports",
            "filter": lambda meta: meta.get("category") == "analysis_result" and meta.get("file_type") in ["document", "text"]
        },
        "generated_models": {
            "name": "模型文件",
            "path": "generated/models",
            "filter": lambda meta: meta.get("category") == "model"
        },
        "isotope_analysis": {
            "name": "同位素分析",
            "path": "analysis/isotope",
            "filter": lambda meta: meta.get("analysis_type") and "isotope" in meta.get("analysis_type", "")
        },
        "input_data": {
            "name": "输入数据",
            "path": "input/data",
            "filter": lambda meta: meta.get("source") == "upload" and meta.get("file_type") in ["text", "spreadsheet", "data"]
        },
        "well_logs": {
            "name": "测井曲线",
            "path": "input/logs",
            "filter": lambda meta: meta.get("file_name", "").lower().endswith(".las")
        },
        "documents": {
            "name": "文档资料",
            "path": "input/documents", 
            "filter": lambda meta: meta.get("source") == "upload" and meta.get("file_type") == "document"
        },
        "images": {
            "name": "图片资料",
            "path": "input/images",
            "filter": lambda meta: meta.get("source") == "upload" and meta.get("file_type") == "image"
        },
        "temp": {
            "name": "临时文件",
            "path": "temp",
            "filter": lambda meta: meta.get("source") == "temp"
        }
    }
    
    @classmethod
    def get_instance(cls):
        """单例模式获取实例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        """初始化MinIO文件管理器"""
        # 从配置获取MinIO连接信息
        from app.core.config import ConfigManager
        config = ConfigManager().load_config()
        minio_config = config.get("minio", {})
        
        # MinIO连接参数
        # 支持两种配置格式：endpoint 或者 host:port
        if 'endpoint' in minio_config:
            self.endpoint = minio_config.get('endpoint')
        else:
            host = minio_config.get('host', 'localhost')
            port = minio_config.get('port', 9000)
            self.endpoint = f"{host}:{port}"
        
        self.access_key = minio_config.get("access_key", "minioadmin")
        self.secret_key = minio_config.get("secret_key", "minioadmin")
        self.secure = minio_config.get("secure", False)
        
        # 桶名称
        self.bucket_name = "isotope-workspace"
        
        # 初始化MinIO客户端
        try:
            self.client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure
            )
            
            # 确保桶存在
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"创建MinIO存储桶: {self.bucket_name}")
            
            self.available = True
            logger.info(f"MinIO文件管理器初始化成功: {self.endpoint}")
            
        except Exception as e:
            logger.error(f"MinIO文件管理器初始化失败: {str(e)}")
            self.available = False
            self.client = None
    
    def _get_category_path(self, metadata: Dict[str, Any]) -> str:
        """根据文件元数据自动确定分类路径"""
        for category_id, category_info in self.FILE_CATEGORIES.items():
            if category_info["filter"](metadata):
                return category_info["path"]
        
        # 默认路径
        source = metadata.get("source", "unknown")
        file_type = metadata.get("file_type", "other")
        return f"{source}/{file_type}"
    
    def _generate_file_id(self, source: str = "file") -> str:
        """生成文件ID"""
        source_prefix = {
            "upload": "u",
            "generated": "g",
            "temp": "t"
        }.get(source, "f")
        
        short_uuid = str(uuid.uuid4()).split('-')[0]
        return f"{source_prefix}-{short_uuid}"
    
    def save_file(self, 
                  file_data: Union[bytes, str, io.BytesIO],
                  file_name: str,
                  file_type: Optional[str] = None,
                  content_type: Optional[str] = None,
                  source: str = "upload",
                  session_id: Optional[str] = None,
                  metadata: Optional[Dict[str, Any]] = None,
                  folder_path: Optional[str] = None) -> Dict[str, Any]:
        """
        保存文件到MinIO
        
        Args:
            file_data: 文件数据（字节、字符串或BytesIO对象）
            file_name: 文件名
            file_type: 文件类型
            content_type: MIME类型
            source: 文件来源（upload/generated/temp）
            session_id: 会话ID
            metadata: 文件元数据
            folder_path: 自定义文件夹路径（如果指定，将覆盖自动分类）
            
        Returns:
            文件信息字典
        """
        if not self.available:
            raise RuntimeError("MinIO不可用")
        
        # 生成文件ID
        file_id = self._generate_file_id(source)
        
        # 准备文件数据
        if isinstance(file_data, str):
            file_data = file_data.encode('utf-8')
        elif isinstance(file_data, io.BytesIO):
            file_data = file_data.getvalue()
        
        file_size = len(file_data)
        
        # 确定文件类型
        if not file_type:
            extension = os.path.splitext(file_name)[1].lstrip(".")
            file_type = self._map_extension_to_type(extension)
        
        # 确定MIME类型
        if not content_type:
            content_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        
        # 构建完整的元数据
        full_metadata = {
            "file_id": file_id,
            "file_name": file_name,
            "file_type": file_type,
            "content_type": content_type,
            "size": file_size,
            "upload_time": datetime.now().isoformat(),
            "source": source,
            "session_id": session_id or ""
        }
        
        # 合并用户提供的元数据
        if metadata:
            full_metadata.update(metadata)
        
        # 如果指定了folder_path，添加到元数据中
        if folder_path:
            full_metadata["folder_path"] = folder_path
            full_metadata["path"] = folder_path
        
        # 确定对象路径
        if folder_path:
            # 使用自定义文件夹路径
            object_path = f"{folder_path}/{file_name}"
        else:
            # 自动分类
            category_path = self._get_category_path(full_metadata)
            object_path = f"{category_path}/{file_id}_{file_name}"
        
        # 保存到MinIO
        try:
            # 将数据转换为BytesIO对象
            data_stream = io.BytesIO(file_data)
            
            # 上传文件
            self.client.put_object(
                self.bucket_name,
                object_path,
                data_stream,
                file_size,
                content_type=content_type,
                metadata={k: self._encode_metadata_value(v) for k, v in full_metadata.items()}  # 编码元数据
            )
            
            logger.info(f"文件已保存到MinIO: {object_path} (ID: {file_id})")
            
            # 返回文件信息
            file_info = {
                "file_id": file_id,
                "file_name": file_name,
                "object_path": object_path,
                "file_type": file_type,
                "content_type": content_type,
                "size": file_size,
                "upload_time": full_metadata["upload_time"],
                "source": source,
                "session_id": session_id,
                "metadata": full_metadata.copy(),  # 使用包含所有字段的完整元数据
                "minio_url": f"minio://{self.bucket_name}/{object_path}"
            }
            
            # 如果有folder_path，确保它在metadata中
            if folder_path:
                file_info["metadata"]["folder_path"] = folder_path
                file_info["metadata"]["path"] = folder_path
            
            # 同时更新InfoHub索引
            self._update_info_hub_index(file_info)
            
            return file_info
            
        except Exception as e:
            logger.error(f"保存文件到MinIO失败: {str(e)}")
            raise
    
    def get_file(self, file_id: str) -> Optional[Tuple[bytes, Dict[str, Any]]]:
        """
        从MinIO获取文件
        
        Args:
            file_id: 文件ID
            
        Returns:
            (文件数据, 文件信息)元组，如果文件不存在则返回None
        """
        if not self.available:
            return None
        
        try:
            logger.info(f"开始查找文件: {file_id}")
            
            # 优化查找：首先尝试直接查找常见路径
            # 常见的文件路径模式
            common_patterns = [
                f"{file_id}_*",  # 直接在根目录
                f"*/{file_id}_*",  # 在任意文件夹中
                f"uploads/{file_id}_*",  # 在uploads文件夹中
                f"EBS/{file_id}_*",  # 在EBS文件夹中
                f"generated/{file_id}_*",  # 在generated文件夹中
            ]
            
            found_object = None
            
            # 首先使用prefix搜索，更高效
            try:
                # 尝试不同的前缀
                prefixes_to_try = ["", "uploads/", "EBS/", "generated/", "temp/"]
                
                for prefix in prefixes_to_try:
                    objects = self.client.list_objects(
                        self.bucket_name,
                        prefix=prefix,
                        recursive=True
                    )
                    
                    for obj in objects:
                        # 获取对象元数据
                        try:
                            stat = self.client.stat_object(self.bucket_name, obj.object_name)
                            metadata = stat.metadata
                            
                            stored_file_id = metadata.get("x-amz-meta-file_id")
                            decoded_file_id = self._decode_metadata_value(stored_file_id) if stored_file_id else None
                            
                            # 检查文件ID匹配
                            if decoded_file_id == file_id or stored_file_id == file_id:
                                logger.info(f"找到匹配文件: {obj.object_name}, file_id: {file_id}")
                                found_object = obj
                                break
                            
                            # 也检查文件名中是否包含file_id
                            if file_id in obj.object_name:
                                # 进一步验证是否确实是同一个文件
                                object_file_id = obj.object_name.split('/')[-1].split('_')[0]
                                if object_file_id == file_id:
                                    logger.info(f"通过文件名找到匹配文件: {obj.object_name}, file_id: {file_id}")
                                    found_object = obj
                                    # 如果元数据中没有file_id，补充上去
                                    if not stored_file_id:
                                        metadata["x-amz-meta-file_id"] = self._encode_metadata_value(file_id)
                                    break
                                    
                        except Exception as e:
                            logger.debug(f"检查对象元数据失败: {obj.object_name}, {str(e)}")
                            continue
                    
                    if found_object:
                        break
                
                if found_object:
                    # 找到文件，下载数据
                    response = self.client.get_object(self.bucket_name, found_object.object_name)
                    file_data = response.read()
                    response.close()
                    
                    # 重新获取元数据（确保是最新的）
                    stat = self.client.stat_object(self.bucket_name, found_object.object_name)
                    metadata = stat.metadata
                    
                    # 重构文件信息
                    file_info = {
                        "file_id": file_id,
                        "file_name": self._decode_metadata_value(metadata.get("x-amz-meta-file_name", found_object.object_name.split('/')[-1])),
                        "object_path": found_object.object_name,
                        "file_type": self._decode_metadata_value(metadata.get("x-amz-meta-file_type", "")),
                        "content_type": self._decode_metadata_value(metadata.get("x-amz-meta-content_type", "")),
                        "size": stat.size,
                        "upload_time": self._decode_metadata_value(metadata.get("x-amz-meta-upload_time", "")),
                        "source": self._decode_metadata_value(metadata.get("x-amz-meta-source", "")),
                        "session_id": self._decode_metadata_value(metadata.get("x-amz-meta-session_id", "")),
                        "minio_url": f"minio://{self.bucket_name}/{found_object.object_name}"
                    }
                    
                    # 添加自定义元数据字段
                    file_info["metadata"] = {}
                    for key, value in metadata.items():
                        if key.startswith("x-amz-meta-") and key not in [
                            "x-amz-meta-file_id", "x-amz-meta-file_name", "x-amz-meta-file_type",
                            "x-amz-meta-content_type", "x-amz-meta-size", "x-amz-meta-upload_time",
                            "x-amz-meta-source", "x-amz-meta-session_id"
                        ]:
                            # 提取自定义元数据
                            meta_key = key.replace("x-amz-meta-", "")
                            file_info["metadata"][meta_key] = self._decode_metadata_value(value)
                    
                    return file_data, file_info
                    
            except Exception as e:
                logger.error(f"优化查找失败，回退到全量搜索: {str(e)}")
            
            logger.warning(f"文件不存在: {file_id}")
            return None
            
        except Exception as e:
            logger.error(f"从MinIO获取文件失败: {str(e)}")
            import traceback
            logger.error(f"获取文件错误详情: {traceback.format_exc()}")
            return None
    
    def list_files(self, 
                   folder_path: Optional[str] = None,
                   session_id: Optional[str] = None,
                   category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        列出文件
        
        Args:
            folder_path: 文件夹路径
            session_id: 会话ID过滤
            category: 分类过滤
            
        Returns:
            文件信息列表
        """
        if not self.available:
            return []
        
        files = []
        
        try:
            # 确定搜索路径
            if category and category in self.FILE_CATEGORIES:
                prefix = self.FILE_CATEGORIES[category]["path"] + "/"
            elif folder_path:
                prefix = folder_path.rstrip("/") + "/"
            else:
                prefix = ""
            
            # 列出对象
            objects = self.client.list_objects(
                self.bucket_name,
                prefix=prefix,
                recursive=True
            )
            
            for obj in objects:
                # 跳过文件夹占位符文件
                if obj.object_name.endswith("/.folder") or obj.object_name.endswith(".folder"):
                    continue
                    
                # 跳过以/结尾的对象（文件夹标记）
                if obj.object_name.endswith("/"):
                    continue
                
                # 获取对象元数据
                stat = self.client.stat_object(self.bucket_name, obj.object_name)
                metadata = stat.metadata
                
                # 应用会话过滤
                if session_id and metadata.get("x-amz-meta-session_id") != session_id:
                    continue
                
                # 从object_path中提取文件夹路径
                path_parts = obj.object_name.split("/")
                folder_path = "/".join(path_parts[:-1]) if len(path_parts) > 1 else ""
                
                # 构建文件信息
                file_info = {
                    "file_id": self._decode_metadata_value(metadata.get("x-amz-meta-file_id", "")),
                    "file_name": self._decode_metadata_value(metadata.get("x-amz-meta-file_name", obj.object_name.split("/")[-1])),
                    "object_path": obj.object_name,
                    "file_path": folder_path,  # 添加file_path字段供前端使用
                    "file_type": self._decode_metadata_value(metadata.get("x-amz-meta-file_type", "")),
                    "content_type": self._decode_metadata_value(metadata.get("x-amz-meta-content_type", "")),
                    "size": stat.size,
                    "upload_time": self._decode_metadata_value(metadata.get("x-amz-meta-upload_time", "")),
                    "source": self._decode_metadata_value(metadata.get("x-amz-meta-source", "")),
                    "session_id": self._decode_metadata_value(metadata.get("x-amz-meta-session_id", "")),
                    "minio_url": f"minio://{self.bucket_name}/{obj.object_name}",
                    "is_generated": self._decode_metadata_value(metadata.get("x-amz-meta-source", "")) == "generated",
                    "metadata": {
                        "folder_path": folder_path,  # 添加到metadata中供前端使用
                        "path": folder_path  # 同时提供path字段作为备用
                    }
                }
                
                # 添加额外的元数据字段，合并到现有的metadata中
                for key, value in metadata.items():
                    if key.startswith("x-amz-meta-") and key not in [
                        "x-amz-meta-file_id", "x-amz-meta-file_name", "x-amz-meta-file_type",
                        "x-amz-meta-content_type", "x-amz-meta-size", "x-amz-meta-upload_time",
                        "x-amz-meta-source", "x-amz-meta-session_id"
                    ]:
                        # 提取自定义元数据
                        meta_key = key.replace("x-amz-meta-", "")
                        file_info["metadata"][meta_key] = self._decode_metadata_value(value)
                
                files.append(file_info)
            
            # 按上传时间排序
            files.sort(key=lambda x: x.get("upload_time", ""), reverse=True)
            
            return files
            
        except Exception as e:
            logger.error(f"列出MinIO文件失败: {str(e)}")
            return []
    
    def create_folder(self, folder_path: str) -> bool:
        """
        创建文件夹（在MinIO中通过创建占位符对象实现）
        
        Args:
            folder_path: 文件夹路径
            
        Returns:
            是否成功
        """
        if not self.available:
            return False
        
        try:
            # 确保路径以/结尾
            if not folder_path.endswith("/"):
                folder_path += "/"
            
            # 创建一个空的占位符对象
            placeholder_name = folder_path + ".folder"
            self.client.put_object(
                self.bucket_name,
                placeholder_name,
                io.BytesIO(b""),
                0,
                metadata={"folder": "true"}
            )
            
            logger.info(f"创建文件夹: {folder_path}")
            return True
            
        except Exception as e:
            logger.error(f"创建文件夹失败: {str(e)}")
            return False
    
    def delete_file(self, file_id: str) -> bool:
        """
        删除文件
        
        Args:
            file_id: 文件ID
            
        Returns:
            是否成功
        """
        if not self.available:
            return False
        
        try:
            logger.info(f"开始删除文件: {file_id}")
            
            # 查找文件
            file_data = self.get_file(file_id)
            if not file_data:
                logger.warning(f"要删除的文件不存在: {file_id}")
                # 尝试直接通过文件名查找并删除
                try:
                    objects = self.client.list_objects(
                        self.bucket_name,
                        recursive=True
                    )
                    
                    for obj in objects:
                        # 检查文件名是否包含file_id
                        if file_id in obj.object_name:
                            object_file_id = obj.object_name.split('/')[-1].split('_')[0]
                            if object_file_id == file_id:
                                logger.info(f"通过文件名找到要删除的文件: {obj.object_name}")
                                self.client.remove_object(self.bucket_name, obj.object_name)
                                logger.info(f"文件已删除: {file_id} ({obj.object_name})")
                                return True
                                
                except Exception as e:
                    logger.error(f"通过文件名查找删除失败: {str(e)}")
                
                return False
            
            _, file_info = file_data
            object_path = file_info["object_path"]
            
            # 删除对象
            self.client.remove_object(self.bucket_name, object_path)
            
            logger.info(f"文件已删除: {file_id} ({object_path})")
            return True
            
        except Exception as e:
            logger.error(f"删除文件失败: {str(e)}")
            import traceback
            logger.error(f"删除文件错误详情: {traceback.format_exc()}")
            return False
    
    def get_folder_tree(self, root_path: str = "") -> Dict[str, Any]:
        """
        获取文件夹树结构
        
        Args:
            root_path: 根路径
            
        Returns:
            文件夹树结构
        """
        if not self.available:
            return {"folders": [], "files": []}
        
        folders_set = set()
        files = []
        
        try:
            # 列出所有对象
            objects = self.client.list_objects(
                self.bucket_name,
                prefix=root_path,
                recursive=True
            )
            
            for obj in objects:
                # 获取相对路径
                rel_path = obj.object_name[len(root_path):] if root_path else obj.object_name
                parts = rel_path.split("/")
                
                # 检查是否是文件夹占位符
                if obj.object_name.endswith("/.folder"):
                    # 这是一个文件夹占位符，直接添加文件夹路径
                    folder_path = obj.object_name[:-8]  # 移除 "/.folder"
                    if folder_path:  # 确保不是空路径
                        folders_set.add(folder_path)
                    continue
                
                # 收集文件夹路径（从文件路径推断）
                current_path = ""
                for part in parts[:-1]:
                    if current_path:
                        current_path += "/"
                    current_path += part
                    if current_path:  # 确保不是空路径
                        folders_set.add(current_path)
                
                # 收集文件信息（排除占位符对象）
                if not obj.object_name.endswith("/") and not obj.object_name.endswith(".folder"):
                    try:
                        stat = self.client.stat_object(self.bucket_name, obj.object_name)
                        metadata = stat.metadata
                        
                        file_info = {
                            "file_id": self._decode_metadata_value(metadata.get("x-amz-meta-file_id", "")),
                            "file_name": self._decode_metadata_value(metadata.get("x-amz-meta-file_name", parts[-1])),
                            "path": obj.object_name,
                            "size": stat.size,
                            "upload_time": self._decode_metadata_value(metadata.get("x-amz-meta-upload_time", ""))
                        }
                        files.append(file_info)
                    except Exception as e:
                        logger.warning(f"获取文件信息失败: {obj.object_name}, {str(e)}")
            
            return {
                "folders": sorted(list(folders_set)),
                "files": files
            }
            
        except Exception as e:
            logger.error(f"获取文件夹树失败: {str(e)}")
            return {"folders": [], "files": []}
    
    def _map_extension_to_type(self, extension: str) -> str:
        """将文件扩展名映射到文件类型"""
        ext = extension.lower()
        
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp', 'tiff']:
            return "image"
        elif ext in ['pdf', 'doc', 'docx', 'rtf', 'odt']:
            return "document"
        elif ext in ['txt', 'md', 'markdown', 'log', 'conf', 'ini', 'cfg']:
            return "text"
        elif ext in ['py', 'js', 'html', 'css', 'java', 'cpp', 'c', 'h']:
            return "code"
        elif ext in ['xls', 'xlsx', 'csv', 'tsv', 'ods']:
            return "spreadsheet"
        elif ext in ['json', 'xml', 'yaml', 'yml', 'sql', 'db']:
            return "data"
        elif ext in ['zip', 'rar', '7z', 'tar', 'gz', 'bz2']:
            return "archive"
        else:
            return "other"
    
    def _update_info_hub_index(self, file_info: Dict[str, Any]):
        """更新InfoHub索引"""
        try:
            from app.core.info_hub import get_info_hub
            info_hub = get_info_hub()
            
            # 保存文件元数据到InfoHub
            info_hub.save_file_meta(file_info)
            
            # 如果是文本类文件，尝试索引内容
            if file_info["file_type"] in ["text", "document", "code", "data"]:
                info_hub.index_file_to_elasticsearch(
                    file_info["file_id"],
                    file_info
                )
            
        except Exception as e:
            logger.warning(f"更新InfoHub索引失败: {str(e)}")

    def _encode_metadata_value(self, value: Any) -> str:
        """将元数据值编码为URL编码"""
        if isinstance(value, str):
            # 使用URL编码处理中文
            return urllib.parse.quote(value, safe='')
        elif isinstance(value, (int, float, bool)):
            return str(value)
        elif isinstance(value, (list, tuple)):
            return ",".join(self._encode_metadata_value(item) for item in value)
        elif isinstance(value, dict):
            return ",".join(f"{k}={self._encode_metadata_value(v)}" for k, v in value.items())
        else:
            return str(value)
    
    def _decode_metadata_value(self, value: str) -> str:
        """解码元数据值"""
        try:
            return urllib.parse.unquote(value)
        except Exception:
            return value

    def _make_ascii_safe_filename(self, filename: str) -> str:
        """
        创建ASCII安全的文件名
        
        Args:
            filename: 原始文件名
            
        Returns:
            ASCII安全的文件名
        """
        try:
            # 检查文件名是否全部是ASCII字符
            filename.encode('ascii')
            # 如果是ASCII字符，直接返回
            return filename
        except UnicodeEncodeError:
            # 如果包含非ASCII字符，使用base64编码
            # 保留文件扩展名
            name_part, ext = os.path.splitext(filename)
            
            # 对文件名部分进行base64编码
            name_bytes = name_part.encode('utf-8')
            encoded_name = base64.b64encode(name_bytes).decode('ascii')
            
            # 添加前缀标识这是编码过的文件名
            safe_name = f"b64_{encoded_name}"
            
            # 重新组合文件名和扩展名
            return safe_name + ext
    
    def _decode_ascii_safe_filename(self, safe_filename: str) -> str:
        """
        解码ASCII安全的文件名
        
        Args:
            safe_filename: ASCII安全的文件名
            
        Returns:
            原始文件名
        """
        try:
            # 检查是否是编码过的文件名
            if safe_filename.startswith("b64_"):
                # 分离文件名和扩展名
                name_part, ext = os.path.splitext(safe_filename)
                
                # 移除前缀
                encoded_name = name_part[4:]  # 移除"b64_"前缀
                
                # 解码base64
                name_bytes = base64.b64decode(encoded_name.encode('ascii'))
                original_name = name_bytes.decode('utf-8')
                
                # 重新组合文件名和扩展名
                return original_name + ext
            else:
                # 如果不是编码过的，直接返回
                return safe_filename
        except Exception:
            # 如果解码失败，返回原文件名
            return safe_filename

    def move_file(self, file_id: str, target_folder: str) -> bool:
        """
        移动文件到指定文件夹
        
        Args:
            file_id: 文件ID
            target_folder: 目标文件夹路径
            
        Returns:
            是否成功
        """
        if not self.available:
            return False
        
        try:
            logger.info(f"开始移动文件: {file_id} -> {target_folder}")
            
            # 获取原文件信息
            file_data = self.get_file(file_id)
            if not file_data:
                logger.warning(f"要移动的文件不存在: {file_id}")
                return False
            
            data, file_info = file_data
            old_object_name = file_info["object_path"]
            file_name = file_info["file_name"]
            
            # **关键修复**：对目标文件夹路径进行ASCII安全处理
            target_folder_clean = target_folder.rstrip("/")
            
            # 检查目标文件夹是否包含非ASCII字符
            try:
                target_folder_clean.encode('ascii')
                safe_target_folder = target_folder_clean
                logger.info(f"目标文件夹ASCII兼容: {target_folder_clean}")
            except UnicodeEncodeError:
                # 如果包含非ASCII字符，使用base64编码
                import base64
                encoded_folder = base64.b64encode(target_folder_clean.encode('utf-8')).decode('ascii')
                safe_target_folder = f"b64_{encoded_folder}"
                logger.info(f"目标文件夹包含非ASCII字符，编码为: {safe_target_folder}")
                logger.info(f"原始文件夹名: {target_folder_clean}")
            
            # 检查是否存在路径冲突或特殊字符问题
            safe_file_name = self._sanitize_filename_for_path(file_name, safe_target_folder)
            new_object_name = f"{safe_target_folder}/{file_id}_{safe_file_name}"
            
            # 检查源路径和目标路径是否相同
            if old_object_name == new_object_name:
                logger.info(f"文件已在目标位置，无需移动: {new_object_name}")
                return True
            
            logger.info(f"移动路径: {old_object_name} -> {new_object_name}")
            
            # 获取原始元数据
            try:
                obj_stat = self.client.stat_object(self.bucket_name, old_object_name)
                original_metadata = obj_stat.metadata or {}
            except Exception as e:
                logger.warning(f"获取原始元数据失败: {str(e)}")
                original_metadata = {}
            
            # **关键修复**：元数据中保存原始文件夹路径（编码后）和安全文件夹路径
            updated_metadata = original_metadata.copy()
            updated_metadata["x-amz-meta-folder_path"] = self._encode_metadata_value(target_folder_clean)  # 原始路径（URL编码）
            updated_metadata["x-amz-meta-safe_folder_path"] = safe_target_folder  # ASCII安全路径
            updated_metadata["x-amz-meta-path"] = self._encode_metadata_value(target_folder_clean)  # 向后兼容
            
            # 确保原始文件名保存在元数据中
            if "x-amz-meta-file_name" not in updated_metadata or not updated_metadata["x-amz-meta-file_name"]:
                updated_metadata["x-amz-meta-file_name"] = self._encode_metadata_value(file_name)
            
            # 尝试多种复制策略
            copy_success = False
            actual_new_object_name = new_object_name  # 实际使用的新对象名
            actual_file_name = safe_file_name  # 实际使用的文件名
            
            # 策略1: 标准的 copy_object 方法
            try:
                logger.info("尝试策略1: 标准copy_object方法")
                copy_source = CopySource(self.bucket_name, old_object_name)
                
                self.client.copy_object(
                    bucket_name=self.bucket_name,
                    object_name=new_object_name,
                    source=copy_source,
                    metadata=updated_metadata,
                    metadata_directive="REPLACE"
                )
                
                copy_success = True
                logger.info(f"策略1成功: {old_object_name} -> {new_object_name}")
                
            except Exception as e:
                logger.warning(f"策略1失败: {str(e)}")
                
                # 策略2: 简化路径和文件名处理（针对编码问题）
                if "SignatureDoesNotMatch" in str(e) or "codec" in str(e):
                    try:
                        logger.info("策略2: 简化文件名和路径处理")
                        
                        # 使用更简单的文件名，避免特殊字符
                        simple_filename = self._create_simple_filename(file_name)
                        simplified_new_name = f"{safe_target_folder}/{file_id}_{simple_filename}"
                        
                        # 创建新的copy source
                        copy_source_retry = CopySource(self.bucket_name, old_object_name)
                        
                        # **修复**：使用ASCII安全的元数据
                        minimal_metadata = {
                            "x-amz-meta-folder_path": self._encode_metadata_value(target_folder_clean),  # URL编码的原始路径
                            "x-amz-meta-safe_folder_path": safe_target_folder,  # ASCII安全路径  
                            "x-amz-meta-file_name": self._encode_metadata_value(file_name),  # 保持原始文件名
                            "x-amz-meta-file_id": file_id
                        }
                        
                        self.client.copy_object(
                            bucket_name=self.bucket_name,
                            object_name=simplified_new_name,
                            source=copy_source_retry,
                            metadata=minimal_metadata,
                            metadata_directive="REPLACE"
                        )
                        
                        actual_new_object_name = simplified_new_name  # 更新实际对象名
                        actual_file_name = simple_filename  # 更新实际文件名
                        copy_success = True
                        logger.info(f"策略2成功: {old_object_name} -> {simplified_new_name}")
                        logger.info(f"策略2使用简化文件名: {simple_filename}")
                        logger.info(f"策略2使用安全文件夹路径: {safe_target_folder}")
                        
                    except Exception as e2:
                        logger.warning(f"策略2失败: {str(e2)}")
                        
                        # 策略3: 下载-上传方式（最后的备用方案）
                        try:
                            logger.info("策略3: 下载-上传方式")
                            
                            # 下载原文件
                            response = self.client.get_object(self.bucket_name, old_object_name)
                            file_data = response.read()
                            response.close()
                            
                            # 创建最简单的文件名和路径
                            ultra_simple_name = f"{safe_target_folder}/{file_id}.dat"
                            
                            # **修复**：使用完全ASCII安全的元数据
                            basic_metadata = {
                                "safe_folder_path": safe_target_folder,  # 不使用x-amz-meta前缀，避免编码问题
                                "original_folder": self._encode_metadata_value(target_folder_clean),
                                "original_file_name": self._encode_metadata_value(file_name),  
                                "file_id": file_id
                            }
                            
                            self.client.put_object(
                                bucket_name=self.bucket_name,
                                object_name=ultra_simple_name,
                                data=io.BytesIO(file_data),
                                length=len(file_data),
                                content_type=original_metadata.get("content-type", "application/octet-stream"),
                                metadata=basic_metadata
                            )
                            
                            actual_new_object_name = ultra_simple_name  # 更新实际对象名
                            actual_file_name = f"{file_id}.dat"  # 更新实际文件名（极简版）
                            copy_success = True
                            logger.info(f"策略3成功: {old_object_name} -> {ultra_simple_name}")
                            logger.info(f"策略3使用极简文件名: {file_id}.dat")
                            logger.info(f"策略3使用安全文件夹路径: {safe_target_folder}")
                            
                        except Exception as e3:
                            logger.error(f"所有复制策略都失败: 策略1={str(e)}, 策略2={str(e2)}, 策略3={str(e3)}")
                            return False
            
            if copy_success:
                # 删除原文件
                try:
                    self.client.remove_object(self.bucket_name, old_object_name)
                    logger.info(f"原文件删除成功: {old_object_name}")
                    
                    # **关键修复**: 如果使用了简化文件名，需要更新内部缓存或重新查找
                    if actual_file_name != safe_file_name:
                        logger.info(f"文件名已简化: {safe_file_name} -> {actual_file_name}")
                        logger.info(f"实际存储路径: {actual_new_object_name}")
                        
                        # 验证移动是否真的成功
                        try:
                            # 验证新文件是否存在
                            verify_stat = self.client.stat_object(self.bucket_name, actual_new_object_name)
                            logger.info(f"移动验证成功: 新文件存在，大小={verify_stat.size}")
                        except Exception as ve:
                            logger.error(f"移动验证失败: 新文件不存在 {actual_new_object_name}")
                            return False
                    
                    logger.info(f"文件移动完全成功: {old_object_name} -> {actual_new_object_name}")
                    logger.info(f"原始目标文件夹: {target_folder_clean}")
                    logger.info(f"安全存储路径: {safe_target_folder}")
                    return True
                    
                except Exception as e:
                    logger.error(f"删除原文件失败: {str(e)}")
                    # 即使删除失败，复制已经成功，可以认为移动基本成功
                    logger.warning(f"文件复制成功但原文件删除失败: {old_object_name} -> {actual_new_object_name}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"移动文件失败: {str(e)}")
            return False
    
    def _sanitize_filename_for_path(self, filename: str, target_path: str) -> str:
        """
        根据目标路径优化文件名，避免签名问题
        
        Args:
            filename: 原始文件名
            target_path: 目标路径
            
        Returns:
            优化后的文件名
        """
        # 检查是否是容易引起问题的路径（如 EBS）
        problematic_paths = ["EBS", "ebs", "System", "system", "Admin", "admin"]
        
        if any(prob_path in target_path for prob_path in problematic_paths):
            # 对于可能有问题的路径，使用更保守的文件名处理
            return self._create_simple_filename(filename)
        
        # 对于普通路径，使用原文件名
        return filename
    
    def _create_simple_filename(self, filename: str) -> str:
        """
        创建简化的文件名，避免特殊字符导致的签名问题
        
        Args:
            filename: 原始文件名
            
        Returns:
            简化的文件名
        """
        import re
        
        # 提取文件扩展名
        name_part, ext = os.path.splitext(filename)
        
        # 移除特殊字符，只保留字母、数字、下划线和点
        safe_name = re.sub(r'[^a-zA-Z0-9._-]', '', name_part)
        
        # 如果名称为空，使用默认名称
        if not safe_name:
            safe_name = "file"
        
        # 限制长度
        if len(safe_name) > 50:
            safe_name = safe_name[:50]
        
        return f"{safe_name}{ext}"

    def copy_file(self, file_id: str, target_folder: str, new_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        复制文件到指定文件夹
        
        Args:
            file_id: 文件ID
            target_folder: 目标文件夹路径
            new_name: 新文件名（可选）
            
        Returns:
            新文件信息，失败时返回None
        """
        if not self.available:
            return None
        
        try:
            logger.info(f"开始复制文件: {file_id} -> {target_folder}, 新名称: {new_name}")
            
            # 获取原文件信息
            file_data = self.get_file(file_id)
            if not file_data:
                logger.warning(f"要复制的文件不存在: {file_id}")
                return None
            
            data, file_info = file_data
            old_object_path = file_info["object_path"]
            
            # 确定新文件名
            final_name = new_name or file_info["file_name"]
            
            # 生成新的文件ID
            new_file_id = self._generate_file_id(file_info.get("source", "upload"))
            
            # 构建新的对象路径
            new_object_path = f"{target_folder.rstrip('/')}/{new_file_id}_{final_name}"
            
            logger.info(f"复制路径: {old_object_path} -> {new_object_path}")
            
            # 获取原对象的元数据
            stat = self.client.stat_object(self.bucket_name, old_object_path)
            
            # 创建新的元数据（更新文件ID和名称）
            new_metadata = dict(stat.metadata)
            new_metadata["x-amz-meta-file_id"] = self._encode_metadata_value(new_file_id)
            new_metadata["x-amz-meta-file_name"] = self._encode_metadata_value(final_name)
            new_metadata["x-amz-meta-upload_time"] = self._encode_metadata_value(datetime.now().isoformat())
            
            # 创建复制源
            copy_source = CopySource(self.bucket_name, old_object_path)
            
            # 复制对象到新位置
            self.client.copy_object(
                bucket_name=self.bucket_name,
                object_name=new_object_path,
                source=copy_source,
                metadata=new_metadata
            )
            
            # 构建返回的文件信息
            new_file_info = {
                "file_id": new_file_id,
                "file_name": final_name,
                "object_path": new_object_path,
                "file_type": file_info["file_type"],
                "content_type": file_info["content_type"],
                "size": stat.size,
                "upload_time": datetime.now().isoformat(),
                "source": file_info.get("source", "upload"),
                "session_id": file_info.get("session_id", ""),
                "minio_url": f"minio://{self.bucket_name}/{new_object_path}"
            }
            
            logger.info(f"文件复制成功: {old_object_path} -> {new_object_path}")
            return new_file_info
            
        except Exception as e:
            logger.error(f"复制文件失败: {str(e)}")
            import traceback
            logger.error(f"复制文件错误详情: {traceback.format_exc()}")
            return None

    def delete_folder(self, folder_path: str, recursive: bool = False) -> bool:
        """
        删除文件夹
        
        Args:
            folder_path: 文件夹路径
            recursive: 是否递归删除子文件夹和文件
            
        Returns:
            是否删除成功
        """
        if not self.available:
            return False
        
        try:
            folder_path = folder_path.strip('/')
            
            if recursive:
                # 递归删除：删除文件夹下所有对象
                objects = self.client.list_objects(
                    self.bucket_name,
                    prefix=f"{folder_path}/",
                    recursive=True
                )
                
                # 收集所有要删除的对象
                objects_to_delete = []
                for obj in objects:
                    objects_to_delete.append(obj.object_name)
                
                # 批量删除对象
                if objects_to_delete:
                    for obj_name in objects_to_delete:
                        self.client.remove_object(self.bucket_name, obj_name)
                
                # 删除文件夹占位符
                try:
                    self.client.remove_object(self.bucket_name, f"{folder_path}/.folder")
                except Exception:
                    pass  # 占位符可能不存在
                    
            else:
                # 非递归删除：检查文件夹是否为空
                objects = list(self.client.list_objects(
                    self.bucket_name,
                    prefix=f"{folder_path}/",
                    recursive=False
                ))
                
                # 检查是否只有.folder占位符
                non_placeholder_objects = [
                    obj for obj in objects 
                    if not obj.object_name.endswith('/.folder')
                ]
                
                if non_placeholder_objects:
                    logger.warning(f"文件夹不为空，无法删除: {folder_path}")
                    return False
                
                # 删除文件夹占位符
                try:
                    self.client.remove_object(self.bucket_name, f"{folder_path}/.folder")
                except Exception as e:
                    logger.warning(f"删除文件夹占位符失败: {str(e)}")
                    return False
            
            logger.info(f"文件夹删除成功: {folder_path}")
            return True
            
        except Exception as e:
            logger.error(f"删除文件夹失败: {str(e)}")
            return False

    def move_folder(self, source_path: str, target_parent: str, new_name: Optional[str] = None) -> bool:
        """
        移动文件夹
        
        Args:
            source_path: 源文件夹路径
            target_parent: 目标父文件夹路径
            new_name: 新文件夹名（可选）
            
        Returns:
            是否移动成功
        """
        if not self.available:
            return False
        
        try:
            source_path = source_path.strip('/')
            target_parent = target_parent.strip('/')
            
            # 确定新的文件夹名
            folder_name = new_name or source_path.split('/')[-1]
            target_path = f"{target_parent}/{folder_name}" if target_parent else folder_name
            
            # 列出源文件夹下的所有对象
            objects = self.client.list_objects(
                self.bucket_name,
                prefix=f"{source_path}/",
                recursive=True
            )
            
            # 移动所有对象
            moved_objects = []
            for obj in objects:
                try:
                    # 计算新的对象路径
                    relative_path = obj.object_name[len(source_path) + 1:]
                    new_object_path = f"{target_path}/{relative_path}"
                    
                    # 复制对象到新位置
                    copy_source = {
                        "Bucket": self.bucket_name,
                        "Object": obj.object_name
                    }
                    
                    stat = self.client.stat_object(self.bucket_name, obj.object_name)
                    self.client.copy_object(
                        self.bucket_name,
                        new_object_path,
                        copy_source,
                        metadata=stat.metadata
                    )
                    
                    moved_objects.append((obj.object_name, new_object_path))
                    
                except Exception as e:
                    logger.error(f"移动对象失败 {obj.object_name}: {str(e)}")
                    # 回滚已移动的对象
                    for old_path, new_path in moved_objects:
                        try:
                            self.client.remove_object(self.bucket_name, new_path)
                        except Exception:
                            pass
                    return False
            
            # 删除源文件夹的所有对象
            for old_path, new_path in moved_objects:
                try:
                    self.client.remove_object(self.bucket_name, old_path)
                except Exception as e:
                    logger.warning(f"删除源对象失败 {old_path}: {str(e)}")
            
            logger.info(f"文件夹移动成功: {source_path} -> {target_path}")
            return True
            
        except Exception as e:
            logger.error(f"移动文件夹失败: {str(e)}")
            return False

    def find_file_by_id(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        根据文件ID查找文件信息
        
        Args:
            file_id: 文件ID
            
        Returns:
            文件信息字典，如果文件不存在则返回None
        """
        if not self.available:
            return None
        
        try:
            logger.info(f"查找文件ID: {file_id}")
            
            # 查找文件
            objects = self.client.list_objects(
                self.bucket_name,
                recursive=True
            )
            
            for obj in objects:
                try:
                    # 获取对象元数据
                    stat = self.client.stat_object(self.bucket_name, obj.object_name)
                    metadata = stat.metadata
                    
                    stored_file_id = metadata.get("x-amz-meta-file_id")
                    decoded_file_id = self._decode_metadata_value(stored_file_id) if stored_file_id else None
                    
                    # 检查文件ID匹配
                    if decoded_file_id == file_id or stored_file_id == file_id:
                        # 从object_path中提取文件夹路径
                        path_parts = obj.object_name.split("/")
                        folder_path = "/".join(path_parts[:-1]) if len(path_parts) > 1 else ""
                        
                        file_info = {
                            "file_id": file_id,
                            "object_name": obj.object_name,
                            "file_name": self._decode_metadata_value(metadata.get("x-amz-meta-file_name", obj.object_name.split("/")[-1])),
                            "folder_path": folder_path,
                            "file_type": self._decode_metadata_value(metadata.get("x-amz-meta-file_type", "")),
                            "content_type": self._decode_metadata_value(metadata.get("x-amz-meta-content_type", "")),
                            "size": stat.size,
                            "metadata": metadata
                        }
                        
                        logger.info(f"找到文件: {obj.object_name}")
                        return file_info
                        
                    # 也检查文件名中是否包含file_id
                    if file_id in obj.object_name:
                        # 进一步验证是否确实是同一个文件
                        object_file_id = obj.object_name.split('/')[-1].split('_')[0]
                        if object_file_id == file_id:
                            path_parts = obj.object_name.split("/")
                            folder_path = "/".join(path_parts[:-1]) if len(path_parts) > 1 else ""
                            
                            file_info = {
                                "file_id": file_id,
                                "object_name": obj.object_name,
                                "file_name": self._decode_metadata_value(metadata.get("x-amz-meta-file_name", obj.object_name.split("/")[-1])),
                                "folder_path": folder_path,
                                "file_type": self._decode_metadata_value(metadata.get("x-amz-meta-file_type", "")),
                                "content_type": self._decode_metadata_value(metadata.get("x-amz-meta-content_type", "")),
                                "size": stat.size,
                                "metadata": metadata
                            }
                            
                            logger.info(f"通过文件名找到文件: {obj.object_name}")
                            return file_info
                            
                except Exception as e:
                    logger.debug(f"检查对象元数据失败: {obj.object_name}, {str(e)}")
                    continue
                    
        except Exception as e:
            logger.error(f"查找文件失败: {str(e)}")
        
        return None

    def get_file_location(self, file_id: str) -> str:
        """
        获取文件的当前位置（文件夹路径）
        
        Args:
            file_id: 文件ID
            
        Returns:
            文件的当前文件夹路径
        """
        try:
            # 查找文件
            file_info = self.find_file_by_id(file_id)
            if not file_info:
                return ""
            
            object_name = file_info.get("object_name", "")
            if not object_name:
                return ""
            
            # 从对象路径中提取文件夹路径
            # 对象路径格式：folder_path/file_id_filename
            if "/" in object_name:
                folder_path = "/".join(object_name.split("/")[:-1])
                return folder_path
            else:
                # 如果没有文件夹路径，说明在根目录
                return ""
                
        except Exception as e:
            logger.error(f"获取文件位置失败: {str(e)}")
            return ""

# 全局函数
def get_minio_file_manager() -> MinIOFileManager:
    """获取MinIO文件管理器实例"""
    return MinIOFileManager.get_instance() 