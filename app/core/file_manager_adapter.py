"""
文件管理适配器 - 提供统一的文件管理接口，支持本地存储和MinIO存储的无缝切换
"""

import os
import logging
from typing import Dict, List, Any, Optional, Union
import io
from datetime import datetime

from app.core.file_manager import FileManager
from app.core.minio_file_manager import MinIOFileManager, get_minio_file_manager

logger = logging.getLogger(__name__)

class FileManagerAdapter:
    """文件管理适配器，提供统一接口"""
    
    def __init__(self, use_minio: bool = None):
        """
        初始化文件管理适配器
        
        Args:
            use_minio: 是否使用MinIO存储，None时从配置读取
        """
        if use_minio is None:
            # 从配置决定是否使用MinIO
            from app.core.config import ConfigManager
            config = ConfigManager().load_config()
            use_minio = config.get("storage", {}).get("use_minio", False)
        
        self.use_minio = use_minio
        
        if self.use_minio:
            # 使用MinIO存储
            self.minio_manager = get_minio_file_manager()
            self.local_manager = None
            
            # 检查MinIO是否可用
            if not self.minio_manager.available:
                logger.warning("MinIO不可用，回退到本地存储")
                self.use_minio = False
                self.local_manager = FileManager.get_instance()
        else:
            # 使用本地存储
            self.local_manager = FileManager.get_instance()
            self.minio_manager = None
        
        logger.info(f"文件管理适配器初始化完成，使用{'MinIO' if self.use_minio else '本地'}存储")
    
    def register_file(self, 
                     file_path: str, 
                     file_name: Optional[str] = None,
                     file_type: Optional[str] = None,
                     source: str = "upload",
                     session_id: Optional[str] = None,
                     metadata: Optional[Dict] = None,
                     skip_copy: bool = False,
                     folder_path: Optional[str] = None) -> Dict[str, Any]:
        """
        注册文件（兼容接口）
        
        对于MinIO存储，如果文件在本地，会先上传到MinIO
        """
        if self.use_minio:
            # 对于MinIO，需要读取文件内容并上传
            if not file_name:
                file_name = os.path.basename(file_path)
            
            # 读取文件内容
            try:
                with open(file_path, 'rb') as f:
                    file_data = f.read()
                
                # 保存到MinIO
                return self.minio_manager.save_file(
                    file_data=file_data,
                    file_name=file_name,
                    file_type=file_type,
                    source=source,
                    session_id=session_id,
                    metadata=metadata,
                    folder_path=folder_path
                )
            except Exception as e:
                logger.error(f"上传文件到MinIO失败: {str(e)}")
                # 如果MinIO失败，回退到本地存储
                if self.local_manager is None:
                    self.local_manager = FileManager.get_instance()
                return self.local_manager.register_file(
                    file_path=file_path,
                    file_name=file_name,
                    file_type=file_type,
                    source=source,
                    session_id=session_id,
                    metadata=metadata,
                    skip_copy=skip_copy
                )
        else:
            # 使用本地存储
            # 如果指定了folder_path，添加到metadata中
            local_metadata = metadata.copy() if metadata else {}
            if folder_path:
                local_metadata["folder_path"] = folder_path
                local_metadata["path"] = folder_path
            
            return self.local_manager.register_file(
                file_path=file_path,
                file_name=file_name,
                file_type=file_type,
                source=source,
                session_id=session_id,
                metadata=local_metadata,
                skip_copy=skip_copy
            )
    
    def save_file(self,
                  file_data: Union[bytes, str, io.BytesIO],
                  file_name: str,
                  file_type: Optional[str] = None,
                  content_type: Optional[str] = None,
                  source: str = "upload",
                  session_id: Optional[str] = None,
                  metadata: Optional[Dict] = None,
                  folder_path: Optional[str] = None) -> Dict[str, Any]:
        """
        保存文件
        """
        if self.use_minio:
            return self.minio_manager.save_file(
                file_data=file_data,
                file_name=file_name,
                file_type=file_type,
                content_type=content_type,
                source=source,
                session_id=session_id,
                metadata=metadata,
                folder_path=folder_path
            )
        else:
            # 本地存储接口适配
            # 如果指定了folder_path，添加到metadata中
            local_metadata = metadata.copy() if metadata else {}
            if folder_path:
                local_metadata["folder_path"] = folder_path
                local_metadata["path"] = folder_path
            
            return self.local_manager.save_file(
                file_data=file_data,
                file_name=file_name,
                file_type=file_type,
                content_type=content_type,
                source=source,
                session_id=session_id,
                metadata=local_metadata
            )
    
    def get_file_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """获取文件信息"""
        if self.use_minio:
            file_data = self.minio_manager.get_file(file_id)
            if file_data:
                _, file_info = file_data
                return file_info
            return None
        else:
            return self.local_manager.get_file_info(file_id)
    
    def get_file_path(self, file_id: str) -> Optional[str]:
        """
        获取文件路径
        
        对于MinIO存储，会返回一个临时下载的本地路径
        """
        if self.use_minio:
            # 从MinIO下载到临时目录
            file_data = self.minio_manager.get_file(file_id)
            if file_data:
                data, file_info = file_data
                
                # 创建临时文件
                import tempfile
                temp_dir = tempfile.gettempdir()
                temp_path = os.path.join(temp_dir, f"minio_{file_id}_{file_info['file_name']}")
                
                # 写入文件
                with open(temp_path, 'wb') as f:
                    f.write(data)
                
                return temp_path
            return None
        else:
            return self.local_manager.get_file_path(file_id)
    
    def get_file_content(self, file_id: str) -> Optional[str]:
        """获取文件内容（文本）"""
        if self.use_minio:
            file_data = self.minio_manager.get_file(file_id)
            if file_data:
                data, _ = file_data
                try:
                    return data.decode('utf-8')
                except:
                    return None
            return None
        else:
            return self.local_manager.get_file_content(file_id)
    
    def get_all_files(self,
                      session_id: Optional[str] = None,
                      file_type: Optional[str] = None,
                      source: Optional[str] = None,
                      category: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取所有文件"""
        if self.use_minio:
            return self.minio_manager.list_files(
                session_id=session_id,
                category=category
            )
        else:
            files = self.local_manager.get_all_files(
                session_id=session_id,
                file_type=file_type,
                source=source
            )
            # 适配文件信息格式
            for file in files:
                file['is_generated'] = file.get('source') == 'generated'
                file['file_size'] = file.get('size', 0)
            return files
    
    def delete_file(self, file_id: str) -> bool:
        """删除文件"""
        if self.use_minio:
            return self.minio_manager.delete_file(file_id)
        else:
            return self.local_manager.delete_file(file_id)
    
    def create_folder(self, folder_path: str) -> bool:
        """创建文件夹（仅MinIO支持）"""
        if self.use_minio:
            return self.minio_manager.create_folder(folder_path)
        else:
            logger.warning("本地存储不支持创建文件夹")
            return False
    
    def get_folder_tree(self, root_path: str = "") -> Dict[str, Any]:
        """获取文件夹树结构（仅MinIO支持）"""
        if self.use_minio:
            return self.minio_manager.get_folder_tree(root_path)
        else:
            # 本地存储返回扁平结构
            files = self.local_manager.get_all_files()
            return {
                "folders": {},
                "files": [{
                    "file_id": f.get("file_id"),
                    "file_name": f.get("file_name"),
                    "size": f.get("size", 0),
                    "upload_time": f.get("upload_time")
                } for f in files]
            }

    def move_file(self, file_id: str, target_folder: str) -> bool:
        """移动文件到指定文件夹（仅MinIO支持）"""
        if self.use_minio:
            return self.minio_manager.move_file(file_id, target_folder)
        else:
            logger.warning("本地存储不支持移动文件")
            return False

    def copy_file(self, file_id: str, target_folder: str, new_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """复制文件到指定文件夹（仅MinIO支持）"""
        if self.use_minio:
            return self.minio_manager.copy_file(file_id, target_folder, new_name)
        else:
            logger.warning("本地存储不支持复制文件")
            return None
    
    def delete_folder(self, folder_path: str, recursive: bool = False) -> bool:
        """删除文件夹（仅MinIO支持）"""
        if self.use_minio:
            return self.minio_manager.delete_folder(folder_path, recursive)
        else:
            logger.warning("本地存储不支持删除文件夹")
            return False
    
    def move_folder(self, source_path: str, target_parent: str, new_name: Optional[str] = None) -> bool:
        """移动文件夹（仅MinIO支持）"""
        if self.use_minio:
            return self.minio_manager.move_folder(source_path, target_parent, new_name)
        else:
            logger.warning("本地存储不支持移动文件夹")
            return False
    
    def get_file_location(self, file_id: str) -> str:
        """获取文件当前位置（仅MinIO支持）"""
        if self.use_minio:
            return self.minio_manager.get_file_location(file_id)
        else:
            # 本地存储返回空字符串
            return ""
    
    def migrate_to_minio(self) -> int:
        """
        将本地文件迁移到MinIO
        
        Returns:
            迁移的文件数量
        """
        if not self.use_minio or not self.minio_manager.available:
            logger.error("MinIO不可用，无法迁移")
            return 0
        
        if self.local_manager is None:
            self.local_manager = FileManager.get_instance()
        
        # 获取所有本地文件
        local_files = self.local_manager.get_all_files()
        migrated_count = 0
        
        for file_info in local_files:
            try:
                file_path = file_info.get("file_path")
                if not file_path or not os.path.exists(file_path):
                    continue
                
                # 读取文件内容
                with open(file_path, 'rb') as f:
                    file_data = f.read()
                
                # 保存到MinIO
                self.minio_manager.save_file(
                    file_data=file_data,
                    file_name=file_info.get("file_name"),
                    file_type=file_info.get("file_type"),
                    content_type=file_info.get("content_type"),
                    source=file_info.get("source", "upload"),
                    session_id=file_info.get("session_id"),
                    metadata=file_info.get("metadata")
                )
                
                migrated_count += 1
                logger.info(f"迁移文件到MinIO: {file_info.get('file_name')}")
                
            except Exception as e:
                logger.error(f"迁移文件失败: {file_info.get('file_id')} - {str(e)}")
        
        logger.info(f"文件迁移完成，共迁移 {migrated_count} 个文件")
        return migrated_count

# 全局实例
_adapter_instance = None

def get_file_manager() -> FileManagerAdapter:
    """获取文件管理器实例"""
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = FileManagerAdapter()
    return _adapter_instance 