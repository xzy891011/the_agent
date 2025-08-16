"""
配置管理模块 - 负责应用程序配置的加载、获取和环境变量管理
"""

import os
import json
import yaml
import logging
from typing import Dict, Any, Optional, List, Union
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from app.prompts.custom_prompts import get_custom_agent_system_prompt
# 配置日志
logger = logging.getLogger(__name__)

class ConfigManager:
    """配置管理器类，负责加载、获取和更新应用程序配置"""
    
    def __init__(self, config_dir: Optional[str] = None):
        """初始化配置管理器
        
        Args:
            config_dir: 配置文件目录，默认为项目根目录下的config文件夹
        """
        # 确定配置目录
        if config_dir is None:
            # 默认使用项目根目录下的config文件夹
            self.config_dir = Path(os.path.abspath(os.path.join(
                os.path.dirname(__file__), "../..", "config")))
        else:
            self.config_dir = Path(config_dir)
        
        # 确保配置目录存在
        os.makedirs(self.config_dir, exist_ok=True)
        
        # 初始化配置字典
        self.config = {}
        self.default_config = {
            "model": {
                "provider": "qwen",
                "model_name": "Qwen/Qwen2.5-72B-Instruct",
                "temperature": 0.1,
                "max_tokens": 4000,  # 修复：合理的回复长度，为输入留出足够空间
                "timeout": 120
            },
            "tools": {
                "enabled": ["file_reader", "data_visualizer"],
                "default_timeout": 30,
                "categories": {
                    "file": True,
                    "isotope": False,
                    "code": True,
                }
            },
            "ui": {
                "theme": "light",
                "chat_history_limit": 50,
                "show_debug_info": False,
                "default_language": "zh-CN",
                "show_thinking": True,
                "stream_mode": "messages,custom",
                "manage_history": True,
                "port": 7860,
                "alternate_ports": [7868, 7869, 7870, 7871, 7872]
            },
            "system": {
                "log_level": "INFO",
                "max_history_messages": 100,
                "checkpoint_interval": 5,
                "data_dir": "data",
                "callbacks_enabled": True
            },
            "agent": {
                # 统一智能体配置
                "use_custom_agent": True,    # 是否使用自定义Agent
                "max_iterations": 10,        # 自定义Agent最大迭代次数
                "debug": False,              # 是否启用调试模式
                "graph_recursion_limit": 50, # LangGraph递归限制
                "graph_timeout": 60,         # LangGraph超时时间(秒)
                
                # 主智能体配置
                "supervisor": {
                    "name": "【监督者supervisor】",
                    "verbose": True,
                    "system_prompt_override": None  # 可选，覆盖默认提示词
                },
                
                # 移除传统智能体配置，改为专业智能体配置
                # "data_agent": {
                #     "name": "【数据智能体data_agent】",
                #     "verbose": True,
                #     "system_prompt_override": None  # 可选，覆盖默认提示词
                # },
                # 
                # "expert_agent": {
                #     "name": "【专家智能体expert_agent】",
                #     "verbose": True,
                #     "system_prompt_override": None  # 可选，覆盖默认提示词
                # }
                
                # 专业智能体配置
                "specialized_agents": {
                    "geophysics": {
                        "name": "【地球物理智能体】",
                        "verbose": True,
                        "system_prompt_override": None
                    },
                    "reservoir": {
                        "name": "【油藏工程智能体】",
                        "verbose": True,
                        "system_prompt_override": None
                    },
                    "economics": {
                        "name": "【经济评价智能体】",
                        "verbose": True,
                        "system_prompt_override": None
                    },
                    "quality_control": {
                        "name": "【质量控制智能体】",
                        "verbose": True,
                        "system_prompt_override": None
                    },
                    "general_analysis": {
                        "name": "【通用分析智能体】",
                    "verbose": True,
                        "system_prompt_override": None
                    }
                }
            },
            
            # LangGraph工作流配置
            "graph": {
                "human_in_loop": True,          # 是否启用人在回路
                "checkpoint_enabled": True,      # 是否启用检查点
                "checkpoint_dir": "./checkpoints"  # 检查点目录
            },
            
            # 内存管理配置
            "memory": {
                "semantic_enabled": True,       # 是否启用语义记忆
                "episodic_enabled": True,       # 是否启用情景记忆
                "max_size": 1000,               # 记忆最大条目数
                "similarity_threshold": 0.7,    # 相似度阈值
                "memory_type": "semantic",      # 记忆类型
                "store_type": "postgres",       # 记忆存储类型
                "connection_string": "postgresql://sweet:yqtdscsdmx666@localhost:5432/isotope"       # 数据库连接字符串
            },
            
            # 数据库配置
            "mysql": {
                "user": "root",
                "password": "yqtdscsdmx666",
                "host": "localhost",
                "port": 3306,
                "database": "isotope",
                "max_connections": 100,
                "stale_timeout": 30
            },
            
            # PostgreSQL数据库配置
            "postgresql": {
                "user": "sweet",
                "password": "yqtdscsdmx666",
                "host": "localhost",
                "port": 5432,
                "database": "isotope",
                "max_connections": 100,
                "stale_timeout": 30
            },
            
            # RAGFlow配置
            "ragflow": {
                "base_url": "http://localhost:7101",
                "api_key": "ragflow-VkNmQ4ZTJhMjAyNDExZjA4YWNiNDI5MD",
                "assistant_id": "331407561f4f11f0ad0642908fa85cbc",
                "timeout": 30
            },
            
            # MinIO配置
            "minio": {
                "endpoint": "localhost:9000",
                "access_key": "yqtdscsdmx666",
                "secret_key": "yqtdscsdmx666",
                "secure": False,
                "bucket": "isotope"
            },
            
            # Elasticsearch配置
            "es": {
                "hosts": ["http://localhost:9200"],
                "username": "elastic",
                "password": "waHNHI41JbjbGpTCLdh6",
                "verify_certs": False
            },
            
            # Redis配置
            "redis": {
                "host": "localhost",
                "port": 6379,
                "db": 0,
                "password": None
            },
            
            # 存储配置
            "storage": {
                "use_minio": True,  # 启用MinIO存储
                "auto_migrate": False  # 是否自动迁移本地文件到MinIO
            }
        }
    
    def load_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """加载配置文件
        
        Args:
            config_path: 配置文件路径，如果未提供则加载默认配置文件
            
        Returns:
            加载的配置字典
            
        Raises:
            FileNotFoundError: 当配置文件不存在时
            ValueError: 当配置文件格式不正确时
        """
        # 如果未提供配置文件路径，使用默认路径
        if config_path is None:
            config_path = self.config_dir / "config.yaml"
        else:
            config_path = Path(config_path)
        
        # 检查配置文件是否存在
        if not config_path.exists():
            logger.warning(f"配置文件不存在: {config_path}，将使用默认配置")
            self.config = self.default_config.copy()
            return self.config
        
        # 根据文件扩展名加载配置
        try:
            suffix = config_path.suffix.lower()
            if suffix == '.json':
                with open(config_path, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
            elif suffix in ['.yaml', '.yml']:
                with open(config_path, 'r', encoding='utf-8') as f:
                    loaded_config = yaml.safe_load(f)
            else:
                raise ValueError(f"不支持的配置文件格式: {suffix}")
            
            # 合并配置与默认配置
            config = self.default_config.copy()
            self._merge_configs(config, loaded_config)
            self.config = config
            logger.info(f"成功加载配置文件: {config_path}")
            return self.config
            
        except Exception as e:
            logger.error(f"加载配置文件失败: {str(e)}")
            raise
    
    def _merge_configs(self, base_config: Dict[str, Any], override_config: Dict[str, Any]) -> None:
        """递归合并配置字典
        
        Args:
            base_config: 基础配置字典（会被修改）
            override_config: 覆盖配置字典
        """
        for key, override_value in override_config.items():
            if (key in base_config and isinstance(base_config[key], dict) 
                    and isinstance(override_value, dict)):
                # 递归合并嵌套字典
                self._merge_configs(base_config[key], override_value)
            else:
                # 直接覆盖值
                base_config[key] = override_value
    
    def get_model_config(self) -> Dict[str, Any]:
        """获取模型配置
        
        Returns:
            模型配置字典
        """
        return self.config.get("model", self.default_config["model"])
    
    def get_tools_config(self) -> Dict[str, Any]:
        """获取工具配置
        
        Returns:
            工具配置字典
        """
        return self.config.get("tools", self.default_config["tools"])
    
    def get_agent_config(self) -> Dict[str, Any]:
        """获取智能体配置
        
        Returns:
            智能体配置字典
        """
        return self.config.get("agent", self.default_config["agent"])
    
    def get_supervisor_config(self) -> Dict[str, Any]:
        """获取主智能体（Supervisor）配置
        
        Returns:
            主智能体配置字典
        """
        agent_config = self.get_agent_config()
        return agent_config.get("supervisor", self.default_config["agent"]["supervisor"])
    
    # 移除传统智能体配置方法，标记为已弃用
    def get_data_agent_config(self) -> Dict[str, Any]:
        """获取数据处理智能体配置（已弃用，使用专业智能体配置）
        
        Returns:
            空配置字典
        """
        logger.warning("get_data_agent_config已弃用，请使用get_specialized_agents_config")
        return {}
    
    def get_expert_agent_config(self) -> Dict[str, Any]:
        """获取专家智能体配置（已弃用，使用专业智能体配置）
        
        Returns:
            空配置字典
        """
        logger.warning("get_expert_agent_config已弃用，请使用get_specialized_agents_config")
        return {}
    
    def get_specialized_agents_config(self) -> Dict[str, Any]:
        """获取专业智能体配置
        
        Returns:
            专业智能体配置字典
        """
        agent_config = self.get_agent_config()
        return agent_config.get("specialized_agents", self.default_config["agent"]["specialized_agents"])
    
    def get_graph_config(self) -> Dict[str, Any]:
        """获取图工作流配置
        
        Returns:
            图工作流配置字典
        """
        return self.config.get("graph", self.default_config["graph"])
    
    def get_memory_config(self) -> Dict[str, Any]:
        """获取内存管理配置
        
        Returns:
            内存管理配置字典
        """
        return self.config.get("memory", self.default_config["memory"])
    
    def get_ui_config(self) -> Dict[str, Any]:
        """获取UI配置
        
        Returns:
            UI配置字典
        """
        return self.config.get("ui", self.default_config["ui"])
    
    def get_system_config(self) -> Dict[str, Any]:
        """获取系统配置
        
        Returns:
            系统配置字典
        """
        return self.config.get("system", self.default_config["system"])
    
    def get_config_value(self, key_path: str, default: Any = None) -> Any:
        """获取配置值
        
        Args:
            key_path: 配置键路径，以点分隔，如 "model.temperature"
            default: 如果键不存在，返回的默认值
            
        Returns:
            配置值，如果键不存在则返回默认值
        """
        # 分割键路径
        keys = key_path.split('.')
        
        # 逐层查找配置值
        config = self.config
        for key in keys:
            if isinstance(config, dict) and key in config:
                config = config[key]
            else:
                return default
        
        return config
    
    def get_environment_variables(self, prefix: Optional[str] = None) -> Dict[str, str]:
        """获取环境变量
        
        Args:
            prefix: 环境变量前缀，如果提供则只返回以该前缀开头的环境变量
            
        Returns:
            环境变量字典
        """
        if prefix is None:
            # 返回所有环境变量
            return dict(os.environ)
        else:
            # 返回指定前缀的环境变量
            return {k: v for k, v in os.environ.items() if k.startswith(prefix)}
    
    def update_config(self, key_path: str, value: Any) -> None:
        """更新配置值
        
        Args:
            key_path: 配置键路径，以点分隔，如 "model.temperature"
            value: 新的配置值
        """
        # 分割键路径
        keys = key_path.split('.')
        
        # 找到最后一层之前的配置字典
        config = self.config
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        
        # 更新值
        config[keys[-1]] = value
        logger.debug(f"更新配置: {key_path} = {value}")
    
    def save_config(self, config_path: Optional[str] = None) -> None:
        """保存配置到文件
        
        Args:
            config_path: 配置文件路径，如果未提供则保存到默认配置文件
            
        Raises:
            IOError: 当无法写入配置文件时
        """
        # 如果未提供配置文件路径，使用默认路径
        if config_path is None:
            config_path = self.config_dir / "config.yaml"
        else:
            config_path = Path(config_path)
        
        # 确保父目录存在
        os.makedirs(config_path.parent, exist_ok=True)
        
        # 根据文件扩展名保存配置
        try:
            suffix = config_path.suffix.lower()
            if suffix == '.json':
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=2, ensure_ascii=False)
            elif suffix in ['.yaml', '.yml']:
                with open(config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True)
            else:
                raise ValueError(f"不支持的配置文件格式: {suffix}")
            
            logger.info(f"配置已保存到: {config_path}")
            
        except Exception as e:
            logger.error(f"保存配置文件失败: {str(e)}")
            raise
    
    def get_mysql_config(self) -> Dict[str, Any]:
        """获取MySQL数据库配置
        
        Returns:
            MySQL配置字典
        """
        return self.config.get("mysql", self.default_config["mysql"])
    
    def get_postgresql_config(self) -> Dict[str, Any]:
        """获取PostgreSQL数据库配置
        
        Returns:
            PostgreSQL配置字典
        """
        return self.config.get("postgresql", self.default_config["postgresql"])
    
    def get_ragflow_config(self) -> Dict[str, Any]:
        """获取RAGFlow配置
        
        Returns:
            RAGFlow配置字典
        """
        return self.config.get("ragflow", self.default_config["ragflow"])
    
    def get_minio_config(self) -> Dict[str, Any]:
        """获取MinIO配置
        
        Returns:
            MinIO配置字典
        """
        return self.config.get("minio", self.default_config["minio"])
    
    def get_es_config(self) -> Dict[str, Any]:
        """获取Elasticsearch配置
        
        Returns:
            Elasticsearch配置字典
        """
        return self.config.get("es", self.default_config["es"])
    
    def get_redis_config(self) -> Dict[str, Any]:
        """获取Redis配置
        
        Returns:
            Redis配置字典
        """
        return self.config.get("redis", self.default_config["redis"])


class EnvironmentManager:
    """环境管理器类，负责环境变量的设置和验证"""
    
    def __init__(self, env_file: Optional[str] = None):
        """初始化环境管理器
        
        Args:
            env_file: .env文件路径，如果未提供则自动查找
        """
        self.env_file = env_file
        self.required_vars = {
            "OPENAI_API_KEY": "OpenAI API密钥，用于与OpenAI模型交互",
            "ISOTOPE_DATA_PATH": "同位素数据存储路径"
        }
        
        # 可选的环境变量
        self.optional_vars = {
            "LOG_LEVEL": "日志级别（DEBUG, INFO, WARNING, ERROR）",
            "MODEL_PROVIDER": "模型提供商（openai, azure, 等）",
            "MODEL_NAME": "模型名称",
            "PROXY_URL": "代理服务器URL"
        }
    
    def load_dotenv(self, env_file: Optional[str] = None) -> bool:
        """加载.env文件
        
        Args:
            env_file: .env文件路径，如果未提供则使用初始化时设置的路径或自动查找
            
        Returns:
            是否成功加载.env文件
        """
        # 确定.env文件路径
        if env_file is not None:
            dotenv_path = env_file
        elif self.env_file is not None:
            dotenv_path = self.env_file
        else:
            # 自动查找.env文件
            dotenv_path = find_dotenv(usecwd=True)
        
        # 加载.env文件
        if dotenv_path:
            loaded = load_dotenv(dotenv_path, override=True)
            if loaded:
                logger.info(f"已加载环境变量文件: {dotenv_path}")
            else:
                logger.warning(f"无法加载环境变量文件: {dotenv_path}")
            return loaded
        else:
            logger.warning("未找到.env文件")
            return False
    
    def setup_environment(self) -> None:
        """设置环境变量
        
        此方法调用load_dotenv并执行必要的环境配置
        """
        # 加载.env文件
        self.load_dotenv()
        
        # 设置默认的LOG_LEVEL（如果未设置）
        if "LOG_LEVEL" not in os.environ:
            os.environ["LOG_LEVEL"] = "INFO"
        
        # 配置日志级别
        log_level = os.environ.get("LOG_LEVEL", "INFO")
        numeric_level = getattr(logging, log_level.upper(), None)
        if isinstance(numeric_level, int):
            logging.basicConfig(level=numeric_level)
            logger.setLevel(numeric_level)
        
        # 配置代理（如果提供）
        proxy_url = os.environ.get("PROXY_URL")
        if proxy_url:
            os.environ["HTTP_PROXY"] = proxy_url
            os.environ["HTTPS_PROXY"] = proxy_url
        
        logger.info("环境已设置")
    
    def validate_environment(self) -> List[str]:
        """验证环境变量是否正确设置
        
        Returns:
            缺失的必需环境变量列表
        """
        missing_vars = []
        
        # 检查必需的环境变量
        for var in self.required_vars:
            if var not in os.environ or not os.environ[var]:
                missing_vars.append(var)
                logger.warning(f"缺少必需的环境变量: {var} - {self.required_vars[var]}")
        
        # 检查可选但推荐的环境变量
        for var in self.optional_vars:
            if var not in os.environ or not os.environ[var]:
                logger.debug(f"未设置可选环境变量: {var} - {self.optional_vars[var]}")
        
        if not missing_vars:
            logger.info("所有必需的环境变量已正确设置")
        
        return missing_vars
    
    def get_required_vars_info(self) -> Dict[str, str]:
        """获取必需环境变量的信息
        
        Returns:
            环境变量名称和描述的字典
        """
        return self.required_vars
    
    def get_optional_vars_info(self) -> Dict[str, str]:
        """获取可选环境变量的信息
        
        Returns:
            环境变量名称和描述的字典
        """
        return self.optional_vars 

def get_llm():
    """获取默认LLM实例
    
    Returns:
        BaseChatModel: LLM实例
    """
    try:
        from app.utils.qwen_chat import SFChatOpenAI
        from langchain_core.language_models import BaseChatModel
        
        # 创建配置管理器并加载配置
        config_manager = ConfigManager()
        config_manager.load_config()
        
        # 获取模型配置
        model_config = config_manager.get_model_config()
        
        # 创建LLM实例
        llm = SFChatOpenAI(
            model=model_config.get("model_name", "Qwen/Qwen2.5-72B-Instruct"),
            temperature=model_config.get("temperature", 0.1),
        )
        
        return llm
        
    except Exception as e:
        logger.error(f"获取默认LLM失败: {str(e)}")
        raise RuntimeError(f"无法创建LLM实例: {str(e)}")

# 创建全局配置管理器实例
config_manager = ConfigManager()
environment_manager = EnvironmentManager()

# 便利函数
def get_config():
    """获取配置管理器实例"""
    return config_manager

def get_env_manager():
    """获取环境管理器实例"""
    return environment_manager 