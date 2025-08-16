"""
文件管理模块 - 提供统一的文件存储、读取和元数据管理功能
"""

import os
import uuid
import shutil
import logging
import json
import mimetypes
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Union
from pathlib import Path
import time
import threading

from app.core.state import FileInfo

# 配置日志
logger = logging.getLogger(__name__)

class FileManager:
    """文件管理类，提供统一的文件管理服务"""
    
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls):
        """单例模式获取实例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        """初始化文件管理器"""
        # 获取项目根目录
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_file_dir, "..", ".."))
        
        # 基础路径，使用项目根目录下的data目录
        self.base_path = os.path.join(project_root, "data")
        self.temp_path = os.path.join(self.base_path, "temp")  # 临时文件目录
        self.upload_path = os.path.join(self.base_path, "uploads")  # 上传的文件
        self.generated_path = os.path.join(self.base_path, "generated")  # 生成的文件
        self.files_path = os.path.join(self.base_path, "files")  # 通用文件存储
        
        # 确保目录存在
        self._ensure_directories()
        
        # 文件索引
        self.file_index = {}
        
        # 从索引文件加载现有索引
        self._load_index()
        
        # 执行一次文件系统检查，确保文件夹结构一致
        self._check_and_migrate_files()
        
        logger.info(f"文件管理器初始化完成，基础路径: {self.base_path}")
    
    def _ensure_directories(self):
        """确保所有必要的目录都存在"""
        os.makedirs(self.base_path, exist_ok=True)
        os.makedirs(self.temp_path, exist_ok=True)
        os.makedirs(self.upload_path, exist_ok=True)
        os.makedirs(self.generated_path, exist_ok=True)
        os.makedirs(self.files_path, exist_ok=True)
        
        # 添加任务目录结构
        os.makedirs(os.path.join(self.base_path, "tasks"), exist_ok=True)
        
        # 标记tmp目录为废弃（该目录与temp重复）
        tmp_path = os.path.join(self.base_path, "tmp")
        if os.path.exists(tmp_path):
            with open(os.path.join(tmp_path, "DEPRECATED.txt"), "w") as f:
                f.write("此目录已废弃，请使用temp目录代替。")
        
        logger.info("文件目录结构检查并创建完成")
    
    def _check_and_migrate_files(self):
        """检查文件系统并迁移文件到正确的目录"""
        # 检查是否存在旧的tmp目录的文件，将其迁移到新的temp目录
        tmp_path = os.path.join(self.base_path, "tmp")
        if os.path.exists(tmp_path):
            try:
                # 获取tmp目录中的所有文件（不包括DEPRECATED.txt）
                files = [f for f in os.listdir(tmp_path) if os.path.isfile(os.path.join(tmp_path, f)) and f != "DEPRECATED.txt"]
                
                # 迁移文件到temp目录
                for file_name in files:
                    source_path = os.path.join(tmp_path, file_name)
                    target_path = os.path.join(self.temp_path, file_name)
                    
                    # 如果目标文件不存在，则复制
                    if not os.path.exists(target_path):
                        shutil.copy2(source_path, target_path)
                        logger.info(f"从tmp迁移文件到temp: {file_name}")
                
                logger.info(f"检查并迁移了 {len(files)} 个文件从tmp到temp目录")
            except Exception as e:
                logger.error(f"迁移tmp目录文件时出错: {str(e)}")
        
        # 更新文件索引中的路径，确保与当前文件夹结构一致
        for file_id, file_info in list(self.file_index.items()):
            # 获取文件路径
            file_path = file_info.get("file_path")
            if not file_path or not os.path.exists(file_path):
                continue
                
            # 检查文件路径是否指向正确的子目录
            source = file_info.get("source", "")
            file_name = file_info.get("file_name", "")
            
            # 根据source字段确定文件应该在哪个目录
            target_dir = self.upload_path if source == "upload" else \
                         self.generated_path if source == "generated" else \
                         self.temp_path
            
            # 如果文件不在正确的目录中，则移动它
            if not file_path.startswith(target_dir):
                # 构建新路径
                new_file_path = os.path.join(target_dir, os.path.basename(file_path))
                
                # 如果目标文件不存在，则移动文件
                if not os.path.exists(new_file_path) and os.path.exists(file_path):
                    try:
                        shutil.move(file_path, new_file_path)
                        
                        # 更新索引中的路径
                        file_info["file_path"] = new_file_path
                        self.file_index[file_id] = file_info
                        
                        logger.info(f"移动文件 {file_id} 到正确的目录: {new_file_path}")
                    except Exception as e:
                        logger.error(f"移动文件 {file_id} 时出错: {str(e)}")
        
        # 保存更新后的索引
        self._save_index()
        
        logger.info("文件系统检查和迁移完成")
    
    def _get_index_file_path(self):
        """获取索引文件路径"""
        return os.path.join(self.base_path, "file_index.json")
    
    def _load_index(self):
        """加载文件索引"""
        index_path = self._get_index_file_path()
        if os.path.exists(index_path):
            try:
                with open(index_path, 'r', encoding='utf-8') as f:
                    self.file_index = json.load(f)
                logger.info(f"成功加载文件索引，包含 {len(self.file_index)} 个文件记录")
            except Exception as e:
                logger.error(f"加载文件索引出错: {str(e)}")
                self.file_index = {}
        else:
            logger.info("文件索引不存在，创建新索引")
            self.file_index = {}
    
    def _save_index(self):
        """保存文件索引"""
        index_path = self._get_index_file_path()
        try:
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(self.file_index, f, ensure_ascii=False, indent=2)
            logger.info(f"成功保存文件索引，包含 {len(self.file_index)} 个文件记录")
        except Exception as e:
            logger.error(f"保存文件索引出错: {str(e)}")
    
    def get_file_mime_type(self, file_path: str) -> str:
        """获取文件MIME类型"""
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type or "application/octet-stream"
    
    def get_file_extension(self, file_path: str) -> str:
        """获取文件扩展名"""
        return os.path.splitext(file_path)[1].lstrip(".")

    def map_extension_to_type(self, extension: str) -> str:
        """将文件扩展名映射到文件类型
        
        Args:
            extension: 文件扩展名
            
        Returns:
            映射后的文件类型
        """
        # 转换为小写进行比较
        ext = extension.lower()
        
        # 图片文件
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp', 'tiff']:
            return "image"
        
        # 文档文件
        elif ext in ['pdf', 'doc', 'docx', 'rtf', 'odt']:
            return "document"
        
        # 文本文件
        elif ext in ['txt', 'md', 'markdown', 'log', 'conf', 'ini', 'cfg']:
            return "text"
            
        # 代码文件
        elif ext in ['py', 'js', 'html', 'css', 'java', 'cpp', 'c', 'h', 'php', 'rb', 'go', 'rs', 'swift', 'kt', 'ts', 'jsx', 'tsx', 'vue', 'scss', 'sass', 'less']:
            return "code"
            
        # 表格文件
        elif ext in ['xls', 'xlsx', 'csv', 'tsv', 'ods']:
            return "spreadsheet"
            
        # 演示文件
        elif ext in ['ppt', 'pptx', 'odp']:
            return "presentation"
            
        # 数据文件
        elif ext in ['json', 'xml', 'yaml', 'yml', 'sql', 'db', 'sqlite']:
            return "data"
            
        # 压缩文件
        elif ext in ['zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz']:
            return "archive"
            
        # 默认类型
        else:
            return "other"
    
    def register_file(self, file_path: str, file_name: Optional[str] = None, 
                      file_type: Optional[str] = None, source: str = "upload", 
                      session_id: Optional[str] = None, metadata: Optional[Dict] = None,
                      skip_copy: bool = False) -> FileInfo:
        """注册文件到管理系统
        
        Args:
            file_path: 文件路径
            file_name: 文件名，如果为None则使用路径中的文件名
            file_type: 文件类型，如果为None则自动检测
            source: 文件来源，upload（上传）或generated（生成）
            session_id: 会话ID，用于关联文件和会话
            metadata: 其他元数据
            skip_copy: 是否跳过复制操作，适用于文件已经在目标目录的情况
            
        Returns:
            文件信息对象
        """
        # 处理文件名和路径
        if not file_name:
            file_name = os.path.basename(file_path)
        
        # 生成更短的文件ID - 使用UUID的前8位十六进制字符，足够确保唯一性
        # 并添加来源前缀以增强可读性: u-上传文件, g-生成文件, t-临时文件
        source_prefix = "u" if source == "upload" else ("g" if source == "generated" else "t")
        short_uuid = str(uuid.uuid4()).split('-')[0]  # 取UUID的第一段
        file_id = f"{source_prefix}-{short_uuid}"
        
        # 确定目标目录
        if source == "upload":
            target_dir = self.upload_path
        elif source == "generated":
            target_dir = self.generated_path
        else:
            target_dir = self.temp_path
        
        # 确保源文件存在
        if not os.path.exists(file_path):
            logger.error(f"源文件不存在: {file_path}")
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        # 文件路径处理
        if skip_copy:
            # 如果跳过复制，检查文件是否已经在目标目录中
            if os.path.dirname(os.path.abspath(file_path)) != os.path.abspath(target_dir):
                logger.warning(f"文件不在目标目录，但要求跳过复制: {file_path}")
            # 使用原始文件名作为目标路径
            target_path = file_path
        else:
            # 确定目标路径 - 使用文件ID作为文件名前缀避免冲突
            target_name = f"{file_id}_{file_name}"
            target_path = os.path.join(target_dir, target_name)
            
            # 复制文件到目标位置（如果源文件不在目标位置）
            if os.path.abspath(file_path) != os.path.abspath(target_path):
                try:
                    shutil.copy2(file_path, target_path)
                    logger.info(f"文件已复制: {file_path} -> {target_path}")
                except Exception as e:
                    logger.error(f"复制文件时出错: {str(e)}")
                    raise
        
        # 获取文件信息
        file_size = os.path.getsize(target_path)
        
        # 确定文件类型
        if not file_type:
            extension = self.get_file_extension(file_name)
            file_type = self.map_extension_to_type(extension)
        
        content_type = self.get_file_mime_type(target_path)
        
        # 构建original_path (仅作为参考，不再复制文件)
        original_path = os.path.join(self.generated_path, file_name)
        
        # 创建文件信息
        file_info = {
            "file_id": file_id,
            "file_name": file_name,
            "file_path": target_path,
            "original_path": original_path,  # 保留这个字段，但不会实际复制
            "file_type": file_type,
            "content_type": content_type,
            "size": file_size,
            "upload_time": datetime.now().isoformat(),
            "source": source,
            "session_id": session_id,
            "metadata": metadata or {}
        }
        
        # 添加到索引
        self.file_index[file_id] = file_info
        
        # 保存索引
        self._save_index()
        
        logger.info(f"文件已注册: {file_name} (ID: {file_id})")
        
        return file_info
    
    def get_file_info(self, file_id: str) -> Optional[FileInfo]:
        """根据文件ID获取文件信息
        
        Args:
            file_id: 文件ID
            
        Returns:
            文件信息对象，如果不存在则返回None
        """
        # 检查文件是否在索引中
        if file_id in self.file_index:
            file_info = self.file_index[file_id]
            
            # 检查文件是否仍然存在
            if os.path.exists(file_info["file_path"]):
                return file_info
            else:
                logger.warning(f"文件已从磁盘删除: {file_info['file_path']}")
                # 从索引中删除
                del self.file_index[file_id]
                self._save_index()
        
        logger.warning(f"找不到文件: {file_id}")
        return None
    
    def get_all_files(self, session_id: Optional[str] = None, 
                      file_type: Optional[str] = None, 
                      source: Optional[str] = None) -> List[FileInfo]:
        """获取所有文件信息
        
        Args:
            session_id: 会话ID，如果不为None，只返回该会话的文件
            file_type: 文件类型，如果不为None，只返回指定类型的文件
            source: 文件来源，如果不为None，只返回指定来源的文件
            
        Returns:
            文件信息列表
        """
        filtered_files = []
        
        for file_id, file_info in self.file_index.items():
            # 过滤会话
            if session_id is not None and file_info.get("session_id") != session_id:
                continue
                
            # 过滤文件类型
            if file_type is not None and file_info.get("file_type") != file_type:
                continue
                
            # 过滤文件来源
            if source is not None and file_info.get("source") != source:
                continue
                
            # 添加到结果列表
            filtered_files.append(file_info)
        
        # 按上传时间排序
        filtered_files.sort(key=lambda x: x.get("upload_time", ""), reverse=True)
        
        return filtered_files
    
    def delete_file(self, file_id: str, remove_from_disk: bool = True) -> bool:
        """删除文件
        
        Args:
            file_id: 文件ID
            remove_from_disk: 是否从磁盘删除文件
            
        Returns:
            是否成功删除
        """
        # 检查文件是否在索引中
        if file_id in self.file_index:
            file_info = self.file_index[file_id]
            file_path = file_info["file_path"]
            
            # 从索引中删除
            del self.file_index[file_id]
            
            # 保存索引
            self._save_index()
            
            # 如果需要，从磁盘删除
            if remove_from_disk and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"文件已从磁盘删除: {file_path}")
                except Exception as e:
                    logger.error(f"从磁盘删除文件时出错: {str(e)}")
                    return False
            
            logger.info(f"文件已删除: {file_id}")
            return True
        
        logger.warning(f"找不到要删除的文件: {file_id}")
        return False
    
    def update_file_metadata(self, file_id: str, metadata: Dict[str, Any]) -> bool:
        """更新文件元数据
        
        Args:
            file_id: 文件ID
            metadata: 元数据字典，将与现有元数据合并
            
        Returns:
            是否成功更新
        """
        # 检查文件是否在索引中
        if file_id in self.file_index:
            file_info = self.file_index[file_id]
            
            # 更新元数据
            current_metadata = file_info.get("metadata", {})
            updated_metadata = {**current_metadata, **metadata}
            file_info["metadata"] = updated_metadata
            
            # 更新索引
            self.file_index[file_id] = file_info
            
            # 保存索引
            self._save_index()
            
            logger.info(f"文件元数据已更新: {file_id}")
            return True
        
        logger.warning(f"找不到要更新的文件: {file_id}")
        return False
    
    def search_files(self, query: str, session_id: Optional[str] = None) -> List[FileInfo]:
        """搜索文件
        
        Args:
            query: 搜索关键词
            session_id: 可选的会话ID过滤
            
        Returns:
            匹配的文件信息列表
        """
        results = []
        query = query.lower()
        
        for file_id, file_info in self.file_index.items():
            # 应用会话过滤
            if session_id and file_info.get("session_id") != session_id:
                continue
                
            # 检查文件是否仍然存在
            if not os.path.exists(file_info["file_path"]):
                continue
                
            # 搜索文件名和元数据
            file_name = file_info["file_name"].lower()
            if query in file_name:
                results.append(file_info)
                continue
                
            # 搜索元数据
            metadata = file_info.get("metadata", {})
            for key, value in metadata.items():
                if isinstance(value, str) and query in value.lower():
                    results.append(file_info)
                    break
        
        return results
    
    def organize_files_by_session(self):
        """按会话整理文件索引"""
        session_files = {}
        
        for file_id, file_info in self.file_index.items():
            session_id = file_info.get("session_id")
            if session_id:
                if session_id not in session_files:
                    session_files[session_id] = []
                session_files[session_id].append(file_info)
        
        return session_files
    
    def get_session_files(self, session_id: str) -> List[FileInfo]:
        """获取指定会话的所有文件
        
        Args:
            session_id: 会话ID
            
        Returns:
            文件信息列表
        """
        return self.get_all_files(session_id=session_id)
    
    def create_task_directory(self, task_id: str) -> str:
        """为任务创建目录
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务目录路径
        """
        task_dir = os.path.join(self.base_path, "tasks", task_id)
        os.makedirs(task_dir, exist_ok=True)
        logger.info(f"为任务 {task_id} 创建目录: {task_dir}")
        return task_dir
    
    def save_file_for_task(self, task_id: str, file_path: str, 
                          file_name: Optional[str] = None) -> FileInfo:
        """保存文件到任务目录
        
        Args:
            task_id: 任务ID
            file_path: 源文件路径
            file_name: 文件名，如果为None则使用源文件名
            
        Returns:
            文件信息
        """
        # 创建任务目录
        task_dir = self.create_task_directory(task_id)
        
        # 处理文件名
        if not file_name:
            file_name = os.path.basename(file_path)
        
        # 目标路径
        target_path = os.path.join(task_dir, file_name)
        
        # 复制文件
        shutil.copy2(file_path, target_path)
        
        # 注册文件
        metadata = {"task_id": task_id}
        return self.register_file(
            target_path, 
            file_name=file_name, 
            source="generated", 
            metadata=metadata
        )

    def _generate_file_id(self, source="file"):
        """生成唯一的文件ID
        
        Args:
            source: 文件来源类型，默认为通用文件
            
        Returns:
            唯一的文件ID字符串
        """
        # 确定前缀，使用的前缀:
        # u-上传文件, g-生成文件, t-临时文件, f-通用文件
        source_prefix = {
            "upload": "u",
            "generated": "g",
            "temp": "t",
            "file": "f"
        }.get(source, "f")
        
        # 生成短UUID - 使用UUID的前8位十六进制字符，足够确保唯一性
        short_uuid = str(uuid.uuid4()).split('-')[0]  # 取UUID的第一段
        
        # 组合ID
        file_id = f"{source_prefix}-{short_uuid}"
        
        return file_id

    def save_file(self, file_data, file_name, file_type=None, content_type=None, source="upload", session_id=None, metadata=None):
        """保存文件并记录到索引
        
        Args:
            file_data: 文件数据（字节流或字符串）
            file_name: 文件名
            file_type: 文件类型（如 csv, json 等）
            content_type: 内容类型 MIME
            source: 文件来源（upload/generated/temp）
            session_id: 会话ID
            metadata: 附加元数据
            
        Returns:
            文件ID
        """
        # 确保文件类型存在
        if not file_type and file_name:
            file_type = os.path.splitext(file_name)[1].lstrip('.')
        
        if not file_type:
            file_type = "text"  # 默认文件类型，使用API兼容的类型
            
        # 生成唯一文件ID
        file_id = self._generate_file_id(source)
        
        # 确定目标目录（根据source）
        if source == "upload":
            target_dir = self.upload_path
        elif source == "generated":
            target_dir = self.generated_path
        elif source == "temp":
            target_dir = self.temp_path
        else:
            # 默认使用files目录
            target_dir = self.files_path
        
        # 确保目录存在
        os.makedirs(target_dir, exist_ok=True)
        
        # 构建文件路径
        file_path = os.path.join(target_dir, f"{file_id}_{file_name}")
        
        try:
            # 写入文件内容
            if isinstance(file_data, str):
                # 文本内容
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(file_data)
                file_size = os.path.getsize(file_path)
            else:
                # 二进制内容
                with open(file_path, 'wb') as f:
                    f.write(file_data)
                file_size = os.path.getsize(file_path)
            
            # 记录到文件索引
            file_info = {
                "file_id": file_id,
                "file_name": file_name,
                "file_type": file_type,
                "content_type": content_type,
                "file_path": file_path,
                "size": file_size,
                "upload_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "source": source
            }
            
            # 添加会话关联
            if session_id:
                file_info["session_id"] = session_id
            
            # 添加元数据
            if metadata:
                file_info["metadata"] = metadata
            
            # 保存到索引
            self.file_index[file_id] = file_info
            self._save_index()
            
            logger.info(f"文件已保存: {file_id}, 路径: {file_path}")
            return file_info
            
        except Exception as e:
            logger.error(f"保存文件失败: {str(e)}")
            # 如果文件已创建，尝试删除
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            raise e

    # 添加便捷方法:

    def save_uploaded_file(self, file_data, file_name, file_type=None, content_type=None, session_id=None, metadata=None):
        """保存上传的文件 - 便捷方法
        
        Args:
            同save_file方法
            
        Returns:
            文件ID
        """
        return self.save_file(
            file_data=file_data, 
            file_name=file_name, 
            file_type=file_type,
            content_type=content_type,
            source="upload",
            session_id=session_id,
            metadata=metadata
        )
        
    def save_generated_file(self, file_data, file_name, file_type=None, content_type=None, session_id=None, metadata=None):
        """保存生成的文件 - 便捷方法
        
        Args:
            同save_file方法
            
        Returns:
            文件ID
        """
        return self.save_file(
            file_data=file_data, 
            file_name=file_name, 
            file_type=file_type,
            content_type=content_type,
            source="generated",
            session_id=session_id,
            metadata=metadata
        )
        
    def save_temp_file(self, file_data, file_name, file_type=None, content_type=None, session_id=None, metadata=None):
        """保存临时文件 - 便捷方法
        
        Args:
            同save_file方法
            
        Returns:
            文件ID
        """
        return self.save_file(
            file_data=file_data, 
            file_name=file_name, 
            file_type=file_type,
            content_type=content_type,
            source="temp",
            session_id=session_id,
            metadata=metadata
        )

    def get_file_content(self, file_id: str) -> Optional[str]:
        """获取文件内容
        
        Args:
            file_id: 文件ID
            
        Returns:
            文件内容字符串，如果文件不存在或不是文本文件则返回None
        """
        file_info = self.get_file_info(file_id)
        if not file_info:
            logger.warning(f"找不到文件: {file_id}")
            return None
            
        file_path = file_info.get("file_path")
        if not file_path or not os.path.exists(file_path):
            logger.warning(f"文件路径不存在: {file_path}")
            return None
            
        # 检查文件类型
        content_type = file_info.get("content_type", "")
        file_type = file_info.get("file_type", "").lower()
        
        # 文本文件类型
        text_content_types = ['text/', 'application/json', 'application/xml', 'application/javascript']
        text_file_types = ['txt', 'md', 'csv', 'json', 'py', 'js', 'html', 'css', 'xml']
        
        is_text = any(content_type.startswith(t) for t in text_content_types) or file_type in text_file_types
        
        if not is_text:
            logger.warning(f"文件不是文本类型: {content_type}/{file_type}")
            return None
            
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
        except Exception as e:
            logger.error(f"读取文件内容失败: {str(e)}")
            return None
            
    def get_file_path(self, file_id: str) -> Optional[str]:
        """获取文件的物理路径
        
        Args:
            file_id: 文件ID
            
        Returns:
            文件的物理路径，如果文件不存在则返回None
        """
        file_info = self.get_file_info(file_id)
        if not file_info:
            logger.warning(f"找不到文件: {file_id}")
            return None
            
        file_path = file_info.get("file_path")
        if not file_path or not os.path.exists(file_path):
            logger.warning(f"文件路径不存在: {file_path}")
            return None
            
        return file_path

    def get_file_by_path(self, file_path: str) -> Optional[FileInfo]:
        """根据文件路径获取文件信息
        
        Args:
            file_path: 文件的完整路径
            
        Returns:
            文件信息对象，如果不存在则返回None
        """
        # 标准化路径
        normalized_path = os.path.abspath(file_path)
        
        # 在索引中查找匹配的文件
        for file_id, file_info in self.file_index.items():
            stored_path = file_info.get("file_path", "")
            if os.path.abspath(stored_path) == normalized_path:
                # 检查文件是否仍然存在
                if os.path.exists(stored_path):
                    return file_info
                else:
                    # 文件已被删除，从索引中移除
                    logger.warning(f"文件已从磁盘删除: {stored_path}")
                    del self.file_index[file_id]
                    self._save_index()
                    break
        
        logger.warning(f"未找到路径对应的文件: {file_path}")
        return None

    def list_files(self, category: Optional[str] = None) -> List[FileInfo]:
        """列出所有文件信息，是get_all_files的别名，用于与task兼容
        
        Args:
            category: 文件类别/来源，如果不为None，只返回指定类别的文件
            
        Returns:
            文件信息列表
        """
        return self.get_all_files(source=category)

# 初始化文件管理器单例
file_manager = FileManager.get_instance()

def get_file_manager():
    """获取文件管理器实例
    
    Returns:
        FileManager实例
    """
    return file_manager 