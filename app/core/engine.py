"""
执行引擎模块 - 系统的中央协调组件
"""
from typing import Dict, List, Any, Optional, Callable, Union, Generator, Tuple
import logging
import uuid
import json
from datetime import datetime
import os
import traceback
import time
import hashlib
import copy

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage,ToolMessage,RemoveMessage
from langchain_core.tools import BaseTool
from langgraph.graph import START
from langgraph.graph import StateGraph

# 导入项目中的其他模块
# 导入新的专业智能体架构
from app.agents.specialized_agents import create_specialized_agent, recommend_agent_for_request
from app.agents.agent_adapter import UnifiedAgent
# 导入智能体注册表
from app.agents.registry import agent_registry, AgentProtocol
# 导入ReAct智能体基类
from app.agents.langgraph_agent import LangGraphAgent
# 导入核心智能体
from app.agents.meta_supervisor import MetaSupervisor
from app.agents.task_planner import TaskPlanner
from app.agents.runtime_supervisor import RuntimeSupervisor
from app.agents.smart_router import SmartRouter
from app.agents.task_dispatcher import TaskDispatcher
from app.agents.human_approval_gate import HumanApprovalGate
# 导入增强记忆系统
from app.core.memory.enhanced_memory_integration import EnhancedMemoryIntegration, create_enhanced_memory_integration
from app.core.memory.engine_adapter import MemoryAwareEngineAdapter, create_memory_aware_adapter
from app.core.memory.agent_memory_injector import AgentMemoryInjector, create_agent_memory_injector
# 导入信息中枢
from app.core.info_hub import InfoHub, get_info_hub
# 导入中断管理器
from app.core.interrupt_manager import InterruptManager, create_default_interrupt_manager
# 导入智能体通信协议
from app.core.agent_communication import MessageRouter, send_message, inject_message_to_state
# 导入系统能力注册表
from app.core.system_capability_registry import SystemCapabilityRegistry, system_capability_registry
from app.core.state import IsotopeSystemState, StateManager, TaskStatus
from app.core.enhanced_graph_builder import EnhancedGraphBuilder, TaskType
from app.tools.registry import get_tools_by_category
from app.utils.qwen_chat import SFChatOpenAI
from app.ui.streaming import LangGraphStreamer  # 使用自定义的LangGraphStreamer
from app.core.memory.store import MemoryStore, MemoryItem
from app.core.memory.history_manager import HistoryManager
from app.core.memory.persistence import IsotopeCheckpointer
from app.core.config import ConfigManager

# 导入PostgreSQL会话管理器
from app.core.postgres_session_manager import get_postgres_session_manager, PostgreSQLSessionManager

# 导入对话轮次管理器
from app.core.conversation_turn_manager import ConversationTurnManager, create_conversation_turn_manager

# 配置日志
logger = logging.getLogger(__name__)

class IsotopeEngine:
    """天然气碳同位素系统执行引擎
    
    该引擎作为系统的中央协调组件，负责：
    1. 管理智能体的创建和初始化
    2. 处理用户输入并生成响应
    3. 管理系统状态和会话
    4. 协调工具的调用和执行
    5. 处理错误和异常情况
    """
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        llm: Optional[BaseChatModel] = None,
        tools: Optional[List[BaseTool]] = None,
        checkpoint_dir: Optional[str] = None,
        verbose: bool = False,
        enable_postgres_sessions: bool = True  # 新增：启用PostgreSQL会话持久化
    ):
        """初始化执行引擎
        
        Args:
            config: 引擎配置参数
            llm: 语言模型，如果为None则创建默认模型
            tools: 可用工具列表
            checkpoint_dir: 检查点保存目录，如果为None则使用内存保存
            verbose: 是否输出详细日志
            enable_postgres_sessions: 是否启用PostgreSQL会话持久化
        """
        self.verbose = verbose
        self.streamer = LangGraphStreamer()
        self.enable_postgres_sessions = enable_postgres_sessions  # 保存PostgreSQL会话选项
        
        # 初始化配置
        self.config = config or {}
        
        # 从配置中获取PostgreSQL会话设置
        if "postgres_sessions" in self.config:
            self.enable_postgres_sessions = self.config.get("postgres_sessions", enable_postgres_sessions)
        
        # 保存检查点目录为实例属性
        self.checkpoint_dir = checkpoint_dir or self.config.get("checkpoint_dir", "./checkpoints")
        
        # 初始化会话持久化管理器
        self._init_session_persistence()
        
        # 核心智能体（极简架构）
        self.smart_router = None
        
        # 增强记忆系统
        self.enhanced_memory_integration = None
        self.memory_adapter = None
        self.memory_injector = None
        
        # 信息中枢
        self.info_hub = None
        
        # 中断管理器
        self.interrupt_manager = None
        
        # 智能体通信
        self.message_router = None
        
        # 系统能力注册表
        self.capability_registry = system_capability_registry
        
        # 导入工具系统
        try:
            from app.tools import get_all_tools, get_tools_by_category, registry
            
            # 获取注册中心的所有工具
            registered_tools = get_all_tools()
            
            # 如果传入了工具列表，合并两者
            if tools:
                # 避免工具重复
                tool_names = {t.name for t in tools}
                # 只添加未包含的工具
                additional_tools = [t for t in registered_tools if t.name not in tool_names]
                self.tools = tools + additional_tools
                logger.info(f"合并传入工具和注册工具，共 {len(self.tools)} 个工具")
            else:
                # 直接使用注册中心的工具
                self.tools = registered_tools
                logger.info(f"使用注册中心的工具，共 {len(self.tools)} 个工具")
                
            # 按类别记录工具数量（工具已在注册时自动注册到能力注册表，无需重复注册）
            categories = registry.get_all_categories()
            for category in categories:
                category_tools = get_tools_by_category(category)
                logger.info(f"已加载 {category} 类工具 {len(category_tools)} 个")
                
        except ImportError as e:
            logger.warning(f"导入工具系统失败: {e}，将使用默认工具")
            self.tools = tools or []
        
        # 初始化内存管理组件
        memory_config = config.get("memory", {}) if config else {}
        
        # 1. 初始化持久化管理
        # 默认使用内存存储，避免SQLite多线程问题
        # 如果使用文件存储，可能会导致"SQLite objects created in a thread can only be used in that same thread"错误
        storage_type = memory_config.get("storage_type", "memory")  # 默认使用内存存储
        connection_string = memory_config.get("connection_string", None)
        
        self.checkpointer = IsotopeCheckpointer(
            storage_type=storage_type,
            connection_string=connection_string,
            checkpoint_dir=checkpoint_dir
        ).get_checkpointer()
        
        # 2. 初始化长期记忆存储
        # 记忆存储可以使用不同于检查点的存储类型
        # 这里我们使用文件存储作为默认，因为文件存储更可靠且不受多线程影响
        store_type = memory_config.get("store_type", "file")  # 默认使用文件存储
        self.memory_store = MemoryStore(
            store_type=store_type,
            connection_string=connection_string
        )
        
        if self.verbose:
            logger.info(f"初始化长期记忆存储: 类型={store_type}")
        
        # 设置自动保存间隔（秒）
        self.autosave_interval = self.config.get("autosave_interval", 300)  # 默认5分钟
        self.last_autosave = time.time()
        
        # 添加测试记忆，确认记忆存储功能正常
        try:
            test_memory_id = self.add_to_memory(
                session_id="system",
                content="这是一条系统测试记忆，用于验证记忆存储功能是否正常工作。",
                memory_type="system"
            )
            logger.info(f"系统测试记忆已添加，ID: {test_memory_id}")
            
            # 尝试检索测试记忆
            test_memories = self.memory_store.search_memories(
                user_id="system",
                query="测试记忆",
                limit=1
            )
            if test_memories:
                logger.info("记忆存储功能正常工作")
            else:
                logger.warning("记忆存储功能可能不正常，无法检索测试记忆")
        except Exception as e:
            logger.error(f"测试记忆存储功能时出错: {str(e)}")
        
        # 创建LLM实例
        if llm:
            self.llm = llm
            logger.info(f"使用传入的LLM: {llm}")
        else:
            self.llm = self._create_default_llm()
            logger.info(f"使用默认LLM: {self.llm}")
                    
        
        # 初始化会话管理
        self.sessions = {}
        
        # 初始化对话轮次管理器字典（每个会话一个管理器）
        self.turn_managers = {}
        
        # 创建图构建器
        self.graph_builder = self._create_graph_builder()
        
        # 编译工作流图
        # 使用增强版图构建器的build_graph方法（智能体路由架构）
        self.workflow_graph = self.graph_builder.compile_enhanced_graph()
        
        # 恢复现有会话
        self._restore_existing_sessions()
        
        if self.verbose:
            logger.info("执行引擎初始化完成")
            # 可视化图结构
            try:
                # 传递已编译的workflow_graph
                graph_viz, _ = self.graph_builder.visualize_graph(self.workflow_graph)
                if graph_viz:
                    logger.info(f"工作流图结构:\n{graph_viz}")
                else:
                    logger.info("无法可视化工作流图结构")
            except Exception as e:
                logger.warning(f"可视化图结构失败: {str(e)}")
    
    def _init_session_persistence(self):
        """初始化会话持久化管理器"""
        self.postgres_session_manager = None
        self.session_persistence_enabled = False
        
        if self.enable_postgres_sessions:
            try:
                # 尝试初始化PostgreSQL会话管理器
                self.postgres_session_manager = get_postgres_session_manager(
                    config=ConfigManager() if not hasattr(self, 'config') or not self.config 
                    else ConfigManager()
                )
                
                # 测试连接
                if self.postgres_session_manager.test_connection():
                    self.session_persistence_enabled = True
                    logger.info("✅ PostgreSQL会话持久化已启用")
                else:
                    logger.warning("⚠️ PostgreSQL连接测试失败，会话持久化已禁用")
                    self.postgres_session_manager = None
                    
            except Exception as e:
                logger.error(f"❌ 初始化PostgreSQL会话管理器失败: {str(e)}")
                self.postgres_session_manager = None
        else:
            logger.info("📁 PostgreSQL会话持久化已禁用，将使用文件存储")
    
    def _create_default_llm(self) -> BaseChatModel:
        """创建默认的语言模型
        
        Returns:
            默认配置的语言模型
        """
        model_config = self.config.get("llm", {})
        model_name = model_config.get("model_name", "Qwen/Qwen2.5-72B-Instruct")
        temperature = model_config.get("temperature", 0.1)
        
        try:
            # 创建默认LLM
            llm = SFChatOpenAI(
                model=model_name,
                temperature=temperature,
                max_tokens=4000,  # 修复：适配模型上下文限制
                request_timeout=60,
            )
            logger.info(f"已创建默认LLM: {model_name}")
            return llm
        except Exception as e:
            logger.error(f"创建默认LLM失败: {str(e)}")
            raise RuntimeError(f"无法创建语言模型: {str(e)}")
    
    def _create_graph_builder(self) -> EnhancedGraphBuilder:
        """创建图构建器
        
        Returns:
            EnhancedGraphBuilder实例
        """
        # 从配置中获取图配置
        graph_config = self.config.get("graph", {})
        
        # 获取图配置参数
        human_in_loop = graph_config.get("human_in_loop", True)
        
        # 初始化增强功能模块
        self._init_enhanced_modules()
        
        # 创建核心智能体
        self._create_core_agents()
        
        # 创建专业智能体管理器
        specialized_agents = self._create_specialized_agents()
        
        # 使用增强版图构建器
        logger.info("使用增强版图构建器（阶段1：任务-子图框架）")
        
        # 使用EnhancedGraphBuilder创建极简版图
        graph_builder = EnhancedGraphBuilder(
            # 核心智能体（极简架构）
            smart_router=self.smart_router,
            
            # 专业智能体
            specialized_agents=specialized_agents,
            
            # 配置和基础设施
            config=self.config,
            checkpointer=self.checkpointer,
            enable_postgres_checkpoint=True,
            enable_mysql_checkpoint=False
        )
        
        return graph_builder
    
    def _init_enhanced_modules(self):
        """初始化增强功能模块"""
        logger.info("初始化增强功能模块")
        
        try:
            # 1. 初始化增强记忆系统
            self.enhanced_memory_integration = create_enhanced_memory_integration(self.config)
            logger.info("✅ 增强记忆系统初始化完成")
            
            # 2. 初始化记忆适配器
            self.memory_adapter = create_memory_aware_adapter(self.config)
            logger.info("✅ 记忆适配器初始化完成")
            
            # 3. 初始化记忆注入器
            self.memory_injector = create_agent_memory_injector(self.enhanced_memory_integration)
            logger.info("✅ 记忆注入器初始化完成")
            
            # 4. 初始化信息中枢
            try:
                self.info_hub = get_info_hub()
                logger.info("✅ 信息中枢初始化完成")
            except Exception as e:
                logger.warning(f"信息中枢初始化失败: {str(e)}，将跳过该功能")
                self.info_hub = None
            
            # 5. 初始化中断管理器
            try:
                self.interrupt_manager = create_default_interrupt_manager(self.config)
                logger.info("✅ 中断管理器初始化完成")
            except Exception as e:
                logger.warning(f"中断管理器初始化失败: {str(e)}，将跳过该功能")
                self.interrupt_manager = None
            
            # 6. 初始化智能体通信
            try:
                self.message_router = MessageRouter()
                logger.info("✅ 智能体通信系统初始化完成")
            except Exception as e:
                logger.warning(f"智能体通信初始化失败: {str(e)}，将跳过该功能")
                self.message_router = None
                
        except Exception as e:
            logger.error(f"增强功能模块初始化失败: {str(e)}")
            # 不抛出异常，允许系统以基础模式运行
    
    def _create_core_agents(self):
        """创建核心智能体（极简架构）"""
        logger.info("创建核心智能体（极简架构）")
        
        try:
            # 统一智能路由器 - 集成用户意图识别和智能体路由功能
            self.smart_router = SmartRouter(
                llm=self.llm,
                config=self.config,
                memory_integration=self.enhanced_memory_integration,
                info_hub=self.info_hub,
                message_router=self.message_router
            )
            agent_registry.register(
                key="smart_router",
                agent=self.smart_router,
                config=self.config,
                override=True
            )
            logger.info("✅ 统一智能路由器创建完成")
            
        except Exception as e:
            logger.error(f"创建核心智能体失败: {str(e)}")
            raise RuntimeError(f"无法创建核心智能体: {str(e)}")
        
    def _create_specialized_agents(self) -> Dict[str, Any]:
        """创建专业智能体并注册到全局注册表
        
        Returns:
            专业智能体字典
        """
        specialized_agents = {}
        
        try:
            # 创建传统专业智能体
            # agent_types = [
            #     'geophysics',      # 地球物理智能体
            #     'reservoir',       # 油藏工程智能体  
            #     'economics',       # 经济评价智能体
            #     'quality_control', # 质量控制智能体
            #     'general_analysis' # 通用分析智能体
            # ]
            
            # for agent_type in agent_types:
            #     try:
            #         agent = create_specialized_agent(
            #             agent_type=agent_type,
            #             llm=self.llm,
            #             config=self.config
            #         )
            #         if agent:
            #             specialized_agents[agent_type] = agent
            #             # 注册到全局注册表
            #             agent_registry.register(
            #                 key=agent_type,
            #                 agent=agent,
            #                 config=self.config,
            #                 override=True
            #             )
            #             logger.info(f"成功创建并注册{agent_type}专业智能体")
            #     except Exception as e:
            #         logger.warning(f"创建{agent_type}智能体失败: {str(e)}")
            
            # 创建ReAct专业智能体
            try:
                # 创建录井智能体（ReAct模式）
                logging_agent = self._create_react_specialist_agent(
                    agent_name="logging",
                    role="录井资料处理专家",
                    capabilities=self._get_logging_capabilities()
                )
                specialized_agents['logging'] = logging_agent
                agent_registry.register(
                    key='logging',
                    agent=logging_agent,
                    config=self.config,
                    override=True
                )
                logger.info("成功创建并注册录井资料处理智能体（ReAct模式）")
            except Exception as e:
                logger.warning(f"创建录井智能体失败: {str(e)}")
            
            try:
                # 创建地震智能体（ReAct模式）
                seismic_agent = self._create_react_specialist_agent(
                    agent_name="seismic",
                    role="地震数据处理专家",
                    capabilities=self._get_seismic_capabilities()
                )
                specialized_agents['seismic'] = seismic_agent
                agent_registry.register(
                    key='seismic',
                    agent=seismic_agent,
                    config=self.config,
                    override=True
                )
                logger.info("成功创建并注册地震处理智能体（ReAct模式）")
            except Exception as e:
                logger.warning(f"创建地震智能体失败: {str(e)}")
            
            try:
                # 创建助手智能体（咨询和知识检索）
                from app.agents.assistant_agent import create_assistant_agent
                assistant_agent = create_assistant_agent(
                    llm=self.llm,
                    config=self.config,
                    memory_integration=self.enhanced_memory_integration,
                    info_hub=self.info_hub,
                    interrupt_manager=self.interrupt_manager,
                    message_router=self.message_router
                )
                specialized_agents['assistant'] = assistant_agent
                agent_registry.register(
                    key='assistant',
                    agent=assistant_agent,
                    config=self.config,
                    override=True
                )
                logger.info("成功创建并注册助手智能体（咨询与知识检索）")
            except Exception as e:
                logger.warning(f"创建助手智能体失败: {str(e)}")
                    
        except Exception as e:
            logger.error(f"创建专业智能体管理器失败: {str(e)}")
            
        logger.info(f"专业智能体管理器创建完成，共{len(specialized_agents)}个智能体")
        return specialized_agents
    
    def _create_react_specialist_agent(self, agent_name: str, role: str, capabilities: List[str]) -> LangGraphAgent:
        """创建专业ReAct智能体
        
        Args:
            agent_name: 智能体名称
            role: 智能体角色描述
            capabilities: 智能体能力列表（工具名称）
            
        Returns:
            配置好的LangGraphAgent实例
        """
        try:
            # 创建LangGraphAgent实例
            agent = LangGraphAgent(
                name=agent_name,
                role=role,
                llm=self.llm,
                capabilities=capabilities,
                config=self.config,
                memory_integration=self.enhanced_memory_integration,
                info_hub=self.info_hub,
                interrupt_manager=self.interrupt_manager,
                message_router=self.message_router
            )
            
            logger.info(f"成功创建{role}ReAct智能体，具备{len(capabilities)}种能力")
            return agent
            
        except Exception as e:
            logger.error(f"创建{role}ReAct智能体失败: {str(e)}")
            raise
    
    def _get_logging_capabilities(self) -> List[str]:
        """获取录井智能体的能力列表"""
        # 从工具注册中心获取录井相关工具
        try:
            from app.tools.registry import get_tools_by_category
            
            # 录井相关工具类别
            logging_categories = ['logging', 'well_logging', '录井', '测井']
            capabilities = []
            
            for category in logging_categories:
                try:
                    tools = get_tools_by_category(category)
                    capabilities.extend([tool.name for tool in tools])
                except Exception as e:
                    logger.debug(f"获取{category}类别工具失败: {str(e)}")
            
            # 如果没有找到专门的录井工具，使用一些通用的数据处理工具
            if not capabilities:
                capabilities = [
                    'file_processor',
                    'data_analyzer', 
                    'chart_generator',
                    'report_generator',
                    'data_validator'
                ]
                logger.info("使用默认录井工具能力列表")
            
            logger.info(f"录井智能体获得{len(capabilities)}种能力: {capabilities}")
            return capabilities
            
        except Exception as e:
            logger.warning(f"获取录井工具能力失败: {str(e)}，使用默认能力")
            return ['file_processor', 'data_analyzer', 'chart_generator']
    
    def _get_seismic_capabilities(self) -> List[str]:
        """获取地震智能体的能力列表"""
        # 从工具注册中心获取地震相关工具
        try:
            from app.tools.registry import get_tools_by_category
            
            # 地震相关工具类别
            seismic_categories = ['seismic', 'geophysics', '地震', '地球物理']
            capabilities = []
            
            for category in seismic_categories:
                try:
                    tools = get_tools_by_category(category)
                    capabilities.extend([tool.name for tool in tools])
                except Exception as e:
                    logger.debug(f"获取{category}类别工具失败: {str(e)}")
            
            # 如果没有找到专门的地震工具，使用一些通用的数据处理工具
            if not capabilities:
                capabilities = [
                    'signal_processor',
                    'data_analyzer',
                    'visualization_generator', 
                    'geological_interpreter',
                    'structure_analyzer'
                ]
                logger.info("使用默认地震工具能力列表")
            
            logger.info(f"地震智能体获得{len(capabilities)}种能力: {capabilities}")
            return capabilities
            
        except Exception as e:
            logger.warning(f"获取地震工具能力失败: {str(e)}，使用默认能力")
            return ['signal_processor', 'data_analyzer', 'visualization_generator']

    def create_session(self, session_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> str:
        """创建新的会话
        
        Args:
            session_id: 会话ID，如果为None则生成新ID
            metadata: 会话元数据，包括名称、描述等信息
            
        Returns:
            会话ID
        """
        # 如果没有提供会话ID，生成一个新的
        if session_id is None:
            session_id = str(uuid.uuid4())
        
        # 创建初始状态
        initial_state = StateManager.create_initial_state()
        initial_state["metadata"]["session_id"] = session_id
        
        # 合并用户提供的元数据
        if metadata:
            initial_state["metadata"].update(metadata)
            logger.info(f"创建会话 {session_id}，名称: {metadata.get('name', '未指定')}")
        
        # 存储会话到内存
        self.sessions[session_id] = {
            "state": initial_state,
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "metadata": metadata or {}  # 在会话级别也保存元数据
        }
        
        # 为新会话创建对话轮次管理器
        self.turn_managers[session_id] = create_conversation_turn_manager(session_id)
        
        # 如果启用了PostgreSQL会话持久化，同时保存到数据库
        if self.session_persistence_enabled and self.postgres_session_manager:
            try:
                success = self.postgres_session_manager.save_session(
                    session_id=session_id,
                    session_data=initial_state,
                    metadata=metadata,
                    expires_in_hours=24 * 7  # 默认7天过期
                )
                if success:
                    logger.info(f"会话 {session_id} 已保存到PostgreSQL")
                else:
                    logger.warning(f"会话 {session_id} 保存到PostgreSQL失败")
            except Exception as e:
                logger.error(f"保存会话到PostgreSQL时出错: {str(e)}")
        
        logger.info(f"创建会话: {session_id}")
        return session_id
    
    def get_session_state(self, session_id: str) -> Optional[IsotopeSystemState]:
        """获取会话状态
        
        Args:
            session_id: 会话ID
            
        Returns:
            会话状态，如果会话不存在则返回None
        """
        session = self.sessions.get(session_id)
        if not session:
            logger.warning(f"会话不存在: {session_id}")
            return None
        
        return session["state"]
       
    def _refresh_session_files(self, state: IsotopeSystemState, session_id: str) -> IsotopeSystemState:
        """刷新会话状态中的文件信息
        
        Args:
            state: 当前系统状态
            session_id: 会话ID
            
        Returns:
            更新后的状态
        """
        try:
            # 导入文件管理器
            from app.core.file_manager import file_manager
            
            # 获取会话文件
            session_files = file_manager.get_session_files(session_id)
            
            # 转换为文件字典
            files_dict = {}
            for file_info in session_files:
                file_id = file_info.get("file_id")
                if file_id:
                    files_dict[file_id] = file_info
            
            # 更新状态中的文件信息
            if files_dict:
                logger.info(f"刷新会话 {session_id} 的文件信息，共 {len(files_dict)} 个文件")
                state["files"] = files_dict
        except ImportError:
            logger.warning("无法导入文件管理器，会话状态将不包含文件信息")
        except Exception as e:
            logger.error(f"刷新会话文件信息时出错: {str(e)}")
        
        return state
    
    def resume_workflow(
        self, 
        user_input: str, 
        session_id: str, 
        stream: bool = False
    ) -> Union[IsotopeSystemState, Generator[Dict[str, Any], None, None]]:
        """恢复工作流
        
        Args:
            user_input: 用户输入消息
            session_id: 会话ID
            stream: 是否使用流式处理
            
        Returns:
            处理结果，如果stream为True则返回生成器
        """
        # 确保会话存在
        if session_id not in self.sessions:
            logger.warning(f"尝试恢复不存在的会话: {session_id}")
            # 尝试从PostgreSQL或检查点加载会话
            if not self._load_session_from_persistence(session_id):
                logger.warning(f"无法从持久化存储恢复会话: {session_id}，创建新会话")
                session_id = self.create_session(session_id)
        
        # 获取会话状态
        state = self.get_session_state(session_id)
        if state is None:
            logger.warning(f"无法获取会话状态: {session_id}，尝试从持久化存储恢复")
            # 尝试从持久化存储加载
            if self._load_session_from_persistence(session_id):
                state = self.get_session_state(session_id)
            
            if state is None:
                logger.warning(f"持久化存储恢复失败，创建初始状态")
                state = self._create_initial_state(session_id)
        
        # 更新状态中的文件信息
        self._refresh_session_files(state, session_id)
        
        # 添加新的用户消息到状态
        user_message = HumanMessage(content=user_input)
        updated_state = StateManager.update_messages(state, user_message)
        
        # 更新会话状态
        self.sessions[session_id]["state"] = updated_state
        
        # 创建配置
        config = self.graph_builder.create_thread_config(session_id)
        
        # 从配置获取图工作流参数
        agent_config = self.config.get("agent", {})
        recursion_limit = agent_config.get("graph_recursion_limit")
        timeout = agent_config.get("graph_timeout")
        
        # 准备运行时参数
        invoke_kwargs = {}
        if recursion_limit is not None:
            invoke_kwargs["recursion_limit"] = recursion_limit
            logger.info(f"设置工作流递归限制: {recursion_limit}")
        if timeout is not None:
            invoke_kwargs["timeout"] = timeout
            logger.info(f"设置工作流执行超时: {timeout}秒")
        
        if stream:
            # 流式处理恢复
            stream_generator = self.workflow_graph.stream(
                updated_state,  # 使用更新后的状态
                config=config,
                stream_mode=self.config.get("ui", {}).get("stream_mode", ["messages", "custom", "updates", "values"]),
                **invoke_kwargs
            )
            
            # 记录最后接收到的状态
            final_state = updated_state
            message_count = 0
            
            # 处理流
            for message in self.streamer.process_stream(stream_generator):
                message_count += 1
                
                # 如果消息包含状态更新，记录最新状态
                if hasattr(message, 'get') and 'state' in message:
                    final_state = message['state']
                elif hasattr(message, '_original_state'):
                    final_state = getattr(message, '_original_state')
                
                # 产生处理后的消息
                yield message
            
            # 更新会话状态
            self.sessions[session_id]["state"] = final_state
            self.sessions[session_id]["last_updated"] = datetime.now().isoformat()
            
            # 保存到PostgreSQL（如果启用）
            self._save_session_to_persistence(session_id, final_state)
            
            logger.info(f"流式恢复完成，处理了 {message_count} 条消息")
        else:
            # 同步处理恢复
            try:
                # 恢复工作流
                result = self.workflow_graph.invoke(
                    updated_state,  # 使用更新后的状态
                    config=config,
                    **invoke_kwargs
                )
                
                # 更新会话状态
                self.sessions[session_id]["state"] = result
                self.sessions[session_id]["last_updated"] = datetime.now().isoformat()
                
                # 保存到PostgreSQL（如果启用）
                self._save_session_to_persistence(session_id, result)
                
                logger.info(f"同步恢复完成")
                return result
            except Exception as e:
                logger.error(f"恢复工作流出错: {str(e)}")
                # 获取当前状态
                current_state = self.sessions[session_id]["state"]
                # 添加错误消息
                error_message = AIMessage(content=f"很抱歉，恢复处理时出现错误: {str(e)}")
                updated_state = StateManager.update_messages(current_state, error_message)
                
                # 更新会话状态
                self.sessions[session_id]["state"] = updated_state
                self.sessions[session_id]["last_updated"] = datetime.now().isoformat()
                
                # 保存到PostgreSQL（如果启用）
                self._save_session_to_persistence(session_id, updated_state)
                
                return updated_state
    
    def _load_session_from_persistence(self, session_id: str) -> bool:
        """从持久化存储加载会话状态
        
        Args:
            session_id: 会话ID
            
        Returns:
            是否成功加载
        """
        # 1. 优先尝试从PostgreSQL加载
        if self.session_persistence_enabled and self.postgres_session_manager:
            try:
                session_data = self.postgres_session_manager.load_session(session_id)
                if session_data:
                    # 重建会话
                    self.sessions[session_id] = {
                        "state": session_data["state"],
                        "created_at": session_data["created_at"],
                        "last_updated": session_data["last_updated"],
                        "metadata": session_data["metadata"]
                    }
                    
                    logger.info(f"从PostgreSQL成功加载会话: {session_id}")
                    return True
            except Exception as e:
                logger.error(f"从PostgreSQL加载会话失败: {str(e)}")
        
        # 2. 回退到文件检查点加载
        return self._load_session_from_checkpoint(session_id)
    
    def _save_session_to_persistence(self, session_id: str, state: IsotopeSystemState):
        """保存会话状态到持久化存储
        
        Args:
            session_id: 会话ID
            state: 会话状态
        """
        if self.session_persistence_enabled and self.postgres_session_manager:
            try:
                # 获取会话元数据
                session = self.sessions.get(session_id, {})
                metadata = session.get("metadata", {})
                
                success = self.postgres_session_manager.save_session(
                    session_id=session_id,
                    session_data=state,
                    metadata=metadata,
                    expires_in_hours=24 * 7  # 7天过期
                )
                
                if success:
                    logger.debug(f"会话 {session_id} 已保存到PostgreSQL")
                else:
                    logger.warning(f"会话 {session_id} 保存到PostgreSQL失败")
                    
            except Exception as e:
                logger.error(f"保存会话到PostgreSQL时出错: {str(e)}")
    
    def _load_session_from_checkpoint(self, session_id: str) -> bool:
        """从检查点加载会话状态
        
        Args:
            session_id: 会话ID
            
        Returns:
            是否成功加载
        """
        try:
            # 1. 尝试从文件检查点加载
            checkpoint_file = os.path.join(self.checkpoint_dir, f"session_{session_id}.json")
            if os.path.exists(checkpoint_file):
                with open(checkpoint_file, 'r', encoding='utf-8') as f:
                    checkpoint_data = json.load(f)
                
                # 检查数据格式
                if "state" in checkpoint_data:
                    state = checkpoint_data["state"]
                    
                    # 重建会话
                    self.sessions[session_id] = {
                        "session_id": session_id,
                        "state": state,
                        "created_at": checkpoint_data.get("timestamp", datetime.now().isoformat()),
                        "last_updated": checkpoint_data.get("timestamp", datetime.now().isoformat()),
                        "interrupt_state": None
                    }
                    
                    logger.info(f"从文件检查点成功加载会话: {session_id}")
                    return True
            
            # 2. 尝试从PostgreSQL检查点加载
            if hasattr(self, 'use_enhanced_graph') and self.use_enhanced_graph:
                try:
                    config = self.graph_builder.create_thread_config(session_id)
                    # 这里可以尝试从PostgreSQL检查点器获取状态
                    # 具体实现取决于checkpointer的API
                    logger.info(f"尝试从PostgreSQL检查点加载会话: {session_id}")
                except Exception as pg_error:
                    logger.warning(f"PostgreSQL检查点加载失败: {str(pg_error)}")
            
            return False
            
        except Exception as e:
            logger.error(f"从检查点加载会话失败: {str(e)}")
            return False
    
    def _process_sync(self, state: IsotopeSystemState, session_id: str) -> IsotopeSystemState:
        """同步处理用户输入
        
        Args:
            state: 当前状态
            session_id: 会话ID
            
        Returns:
            更新后的状态
        """
        try:
            # 从配置获取图工作流参数
            agent_config = self.config.get("agent", {})
            recursion_limit = agent_config.get("graph_recursion_limit")
            timeout = agent_config.get("graph_timeout")
            
            # 创建工作流配置
            workflow_config = self.graph_builder.create_thread_config(session_id)
            
            # 添加递归限制和超时设置（如果配置了）到工作流配置
            # 这些参数在运行时使用，而不是在编译时
            if recursion_limit is not None:
                workflow_config.setdefault("recursion_limit", recursion_limit)
                logger.info(f"设置工作流递归限制: {recursion_limit}")
            
            if timeout is not None:
                workflow_config.setdefault("timeout", timeout)
                logger.info(f"设置工作流执行超时: {timeout}秒")
            
            # 运行工作流图
            invoke_kwargs = {}
            # 为invoke方法准备递归限制和超时参数
            if recursion_limit is not None:
                invoke_kwargs["recursion_limit"] = recursion_limit
            if timeout is not None:
                invoke_kwargs["timeout"] = timeout
                
            result = self.workflow_graph.invoke(
                state,
                config=workflow_config,
                **invoke_kwargs  # 在运行时传递这些参数
            )
            
            # 更新会话状态
            self.sessions[session_id]["state"] = result
            self.sessions[session_id]["last_updated"] = datetime.now().isoformat()
            
            # 检查是否需要自动保存
            current_time = time.time()
            if current_time - self.last_autosave > self.autosave_interval:
                try:
                    self._auto_save_session(session_id, result)
                    self.last_autosave = current_time
                except Exception as auto_save_err:
                    logger.error(f"自动保存会话时出错: {str(auto_save_err)}")
            
            return result
        except Exception as e:
            logger.error(f"处理用户输入时出错: {str(e)}")
            error_message = AIMessage(content=f"处理您的消息时出现错误: {str(e)}")
            updated_state = StateManager.update_messages(state, error_message)
            
            # 尽管发生错误，仍然更新会话状态
            self.sessions[session_id]["state"] = updated_state
            self.sessions[session_id]["last_updated"] = datetime.now().isoformat()
            
            return updated_state
    
    
    
    def register_tool(self, tool: BaseTool, category: Optional[str] = None) -> None:
        """注册工具
        
        Args:
            tool: 要注册的工具
            category: 工具分类，可选
        """
        # 向全局注册中心注册
        try:
            from app.tools.registry import registry
            registry.register_tool(tool, category)
            logger.info(f"工具 '{tool.name}' 已注册到全局工具注册中心")
        except ImportError:
            logger.warning("工具注册中心导入失败，只注册到引擎")
        
        # 添加工具到工具列表(避免重复)
        tool_exists = False
        for existing_tool in self.tools:
            if existing_tool.name == tool.name:
                tool_exists = True
                break
                
        if not tool_exists:
            self.tools.append(tool)
            logger.info(f"工具 '{tool.name}' 已添加到引擎工具列表")
        
    
    def register_tools(self, tools: List[BaseTool], category: Optional[str] = None) -> None:
        """批量注册工具
        
        Args:
            tools: 要注册的工具列表
            category: 工具分类，可选
        """
        for tool in tools:
            self.register_tool(tool, category)
    
    def get_available_tools(self) -> List[Dict[str, str]]:
        """获取可用工具信息
        
        Returns:
            工具信息列表，包含名称和描述
        """
        return [{"name": tool.name, "description": tool.description} for tool in self.tools]
    
       
    def reset_session(self, session_id: str) -> bool:
        """重置会话状态
        
        Args:
            session_id: 会话ID
            
        Returns:
            操作是否成功
        """
        if session_id not in self.sessions:
            logger.warning(f"会话不存在: {session_id}")
            return False
        
        # 创建初始状态
        initial_state = StateManager.create_initial_state()
        initial_state["metadata"]["session_id"] = session_id
        
        # 更新会话
        self.sessions[session_id]["state"] = initial_state
        self.sessions[session_id]["last_updated"] = datetime.now().isoformat()
        
        logger.info(f"重置会话: {session_id}")
        return True
    
    def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        """获取会话历史
        
        Args:
            session_id: 会话ID
            
        Returns:
            会话消息历史（API格式，适合前端显示）
        """
        if session_id not in self.sessions:
            logger.warning(f"会话不存在: {session_id}")
            return []
        
        # 优先从轮次管理器获取完整对话历史
        if session_id in self.turn_managers:
            turn_manager = self.turn_managers[session_id]
            api_history = turn_manager.get_api_conversation_history()
            
            if api_history:
                logger.info(f"从轮次管理器获取到 {len(api_history)} 条完整对话记录")
                # 添加调试日志：显示消息类型分布
                user_msgs = [msg for msg in api_history if msg.get('role') == 'user']
                assistant_msgs = [msg for msg in api_history if msg.get('role') == 'assistant']
                logger.info(f"消息类型分布: 用户消息 {len(user_msgs)} 条, 助手消息 {len(assistant_msgs)} 条")
                return api_history
            else:
                logger.info(f"轮次管理器中没有完整对话记录，使用传统方式")
        
        # 回退到传统方式（向后兼容）
        state = self.sessions[session_id]["state"]
        messages = state.get("messages", [])
        
        # 转换消息为API格式
        result = []
        for i, msg in enumerate(messages):
            try:
                if isinstance(msg, BaseMessage):
                    # 映射消息类型到角色
                    role_mapping = {
                        "human": "user",
                        "ai": "assistant", 
                        "system": "system",
                        "tool": "tool"
                    }
                    
                    api_msg = {
                        "id": getattr(msg, "id", f"msg_{i}_{session_id}"),
                        "role": role_mapping.get(msg.type, msg.type),
                        "content": msg.content,
                        "timestamp": datetime.now().isoformat(),
                        "type": "text",
                        "metadata": {
                            "source": "legacy_conversion",
                            "original_type": msg.type
                        }
                    }
                    
                    # 添加额外属性
                    if hasattr(msg, "name") and msg.name:
                        api_msg["metadata"]["name"] = msg.name
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        api_msg["metadata"]["tool_calls"] = msg.tool_calls
                    
                    result.append(api_msg)
                elif isinstance(msg, dict):
                    # 检查是否已经是API格式（来自轮次管理器）
                    if "role" in msg and msg["role"] in ["user", "assistant", "system", "tool"]:
                        # 已经是正确的API格式，直接使用
                        result.append(msg)
                    else:
                        # 需要转换的字典格式
                        api_msg = {
                            "id": msg.get("id", f"msg_{i}_{session_id}"),
                            "role": msg.get("role", msg.get("type", "unknown")),
                            "content": msg.get("content", ""),
                            "timestamp": msg.get("timestamp", datetime.now().isoformat()),
                            "type": msg.get("message_type", msg.get("type", "text")),
                            "metadata": msg.get("metadata", {})
                        }
                        result.append(api_msg)
            except Exception as e:
                logger.warning(f"转换消息 {i} 时出错: {str(e)}")
                continue
        
        logger.info(f"使用传统方式获取到 {len(result)} 条历史消息")
        return result
    
    def handle_error(self, error: Exception, session_id: Optional[str]) -> Tuple[IsotopeSystemState, str]:
        """处理异常
        
        Args:
            error: 异常对象
            session_id: 会话ID
            
        Returns:
            (更新后的状态, 错误消息)
        """
        error_message = f"执行出错: {str(error)}"
        logger.error(error_message)
        traceback.print_exc()
        
        # 如果有会话ID，更新会话状态
        if session_id and session_id in self.sessions:
            state = self.sessions[session_id]["state"]
            error_ai_msg = AIMessage(content=f"很抱歉，系统遇到了问题: {error_message}")
            updated_state = StateManager.update_messages(state, error_ai_msg)
            
            # 更新会话
            self.sessions[session_id]["state"] = updated_state
            self.sessions[session_id]["last_updated"] = datetime.now().isoformat()
            
            return updated_state, error_message
        
        # 如果没有会话ID，创建新状态
        initial_state = StateManager.create_initial_state()
        error_ai_msg = AIMessage(content=f"很抱歉，系统遇到了问题: {error_message}")
        updated_state = StateManager.update_messages(initial_state, error_ai_msg)
        
        return updated_state, error_message
    
    def save_session_state(self, session_id: str, file_path: Optional[str] = None) -> bool:
        """保存会话状态到检查点
        
        Args:
            session_id: 会话ID
            file_path: 文件路径（可选，如果不提供则使用默认路径）
            
        Returns:
            保存是否成功
        """
        try:
            # 获取会话状态
            if session_id not in self.sessions:
                logger.warning(f"尝试保存不存在的会话: {session_id}")
                return False
            
            session_info = self.sessions[session_id]
            state = session_info.get("state")
            
            if state is None:
                logger.warning(f"会话 {session_id} 没有状态数据")
                return False
            
            saved_any = False
            
            # 1. 尝试保存到PostgreSQL检查点（如果使用增强图构建器）
            if hasattr(self, 'use_enhanced_graph') and self.use_enhanced_graph:
                try:
                    # 获取checkpointer
                    if hasattr(self.checkpointer, 'conn') or hasattr(self.checkpointer, 'sync_connection'):
                        # 这是PostgreSQL检查点器，直接使用状态保存
                        config = self.graph_builder.create_thread_config(session_id)
                        
                        # 手动创建检查点
                        from langchain_core.runnables import RunnableConfig
                        from langgraph.checkpoint.base import Checkpoint
                        
                        checkpoint_data = {
                            "v": 1,
                            "ts": str(time.time()),
                            "id": str(uuid.uuid4()),
                            "channel_values": state,
                            "channel_versions": {},
                            "versions_seen": {}
                        }
                        
                        checkpoint = Checkpoint(**checkpoint_data)
                        self.checkpointer.put(config, checkpoint, {}, {})
                        
                        logger.info(f"PostgreSQL检查点保存成功: {session_id}")
                        saved_any = True
                        
                except Exception as pg_error:
                    logger.warning(f"PostgreSQL检查点保存失败: {str(pg_error)}")
            
            # 2. 保存到文件检查点（作为备份）
            try:
                # 确保检查点目录存在
                os.makedirs(self.checkpoint_dir, exist_ok=True)
                
                # 确定文件路径
                if file_path is None:
                    file_path = os.path.join(self.checkpoint_dir, f"session_{session_id}.json")
                
                # 准备序列化的状态
                serializable_state = self._prepare_state_for_serialization(state)
                
                # 添加元数据
                checkpoint_data = {
                    "session_id": session_id,
                    "timestamp": datetime.now().isoformat(),
                    "state": serializable_state,
                    "metadata": {
                        "engine_version": "2.0",
                        "checkpoint_type": "interrupt_recovery",
                        "created_by": "engine.save_session_state"
                    }
                }
                
                # 保存到文件
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)
                
                logger.info(f"会话状态已保存到文件: {file_path}")
                saved_any = True
                
            except Exception as file_error:
                logger.error(f"文件检查点保存失败: {str(file_error)}")
            
            # 3. 如果有持久化器，也尝试通过它保存
            if hasattr(self, 'checkpointer') and self.checkpointer is not None:
                try:
                    # 持久化器的保存方法可能不同，但尝试一下
                    if hasattr(self.checkpointer, 'get_checkpointer'):
                        actual_checkpointer = self.checkpointer.get_checkpointer()
                        if actual_checkpointer and hasattr(actual_checkpointer, 'put'):
                            # 尝试使用checkpointer的put方法
                            config = self.graph_builder.create_thread_config(session_id)
                            logger.info(f"尝试使用持久化器保存状态")
                            saved_any = True
                    else:
                        logger.warning("持久化器不支持get_checkpointer方法，使用简单文件存储")
                        
                except Exception as checkpointer_error:
                    logger.error(f"持久化器保存失败: {str(checkpointer_error)}")
            
            if saved_any:
                logger.info(f"会话 {session_id} 状态保存成功")
                return True
            else:
                logger.error(f"会话 {session_id} 状态保存失败 - 所有方法都失败了")
                return False
                
        except Exception as e:
            logger.error(f"保存会话状态时出错: {str(e)}")
            logger.error(f"错误详情: {traceback.format_exc()}")
            return False
    
    def _prepare_state_for_serialization(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """将状态转换为可序列化格式
        
        Args:
            state: 系统状态
            
        Returns:
            可序列化的状态字典
        """
        if state is None:
            return {}
        
        # 创建状态的深拷贝
        serializable_state = {}
        
        # 递归处理每个键值对
        for key, value in state.items():
            serializable_state[key] = self._make_serializable(value)
        
        return serializable_state

    def _make_serializable(self, obj):
        """递归地将对象转换为可序列化格式
        
        Args:
            obj: 任意对象
            
        Returns:
            可序列化的对象
        """
        # 处理None
        if obj is None:
            return None
        
        # 处理基本类型
        if isinstance(obj, (str, int, float, bool)):
            return obj
        
        # 跳过不可序列化的已知类型
        from app.core.memory.store import MemoryStore
        if isinstance(obj, MemoryStore):
            return "<MemoryStore实例，已跳过序列化>"
        
        # 处理Gradio Image对象
        try:
            import gradio as gr
            if isinstance(obj, gr.Image):
                # 如果是Gradio图片对象，尝试保存图片路径
                if hasattr(obj, "value") and obj.value:
                    image_path = str(obj.value)
                    return f"__IMAGE_PATH__:{image_path}"
                return "<gradio.Image对象，无法获取路径>"
        except ImportError:
            pass
        
        # 检查字符串是否包含图片对象描述
        if isinstance(obj, str) and "<gradio.components.image.Image object at" in obj:
            # 尝试从字符串中提取图片路径
            import re
            #不要使用绝对路径，要兼容Windows和Linux路径,程序路径在/xuzhiyao/code/the_agent/
            path_match = re.search(r'[\'"](?:[a-zA-Z]:\\|/)?(?:[\w\-\.]+[/\\])*[\w\-\.]+\.(?:jpg|jpeg|png|gif|bmp|webp)[\'"]', obj)
            if path_match:
                image_path = path_match.group(0)
                return f"__IMAGE_PATH__:{image_path}"
        
        # 处理消息对象
        if isinstance(obj, BaseMessage):
            msg_dict = {
                "type": obj.type,
                "content": self._make_serializable(obj.content)  # 递归处理内容
            }
            # 添加额外属性
            if hasattr(obj, "name") and obj.name:
                msg_dict["name"] = obj.name
            if hasattr(obj, "tool_calls") and obj.tool_calls:
                msg_dict["tool_calls"] = obj.tool_calls
            if hasattr(obj, "additional_kwargs") and obj.additional_kwargs:
                msg_dict["additional_kwargs"] = self._make_serializable(obj.additional_kwargs)
            return msg_dict
        
        # 处理列表
        if isinstance(obj, list):
            return [self._make_serializable(item) for item in obj]
        
        # 处理字典
        if isinstance(obj, dict):
            # 特殊处理字典中的图片路径
            if "image_path" in obj and isinstance(obj.get("content"), str) and "<gradio.components.image.Image object at" in obj.get("content"):
                # 已经处理过的图片消息，保留图片路径
                serialized_dict = {k: self._make_serializable(v) for k, v in obj.items()}
                serialized_dict["content"] = f"__IMAGE_PATH__:{obj['image_path']}"
                return serialized_dict
            return {k: self._make_serializable(v) for k, v in obj.items()}
        
        # 处理其他类型
        try:
            # 尝试转换为字典
            if hasattr(obj, "__dict__"):
                return self._make_serializable(obj.__dict__)
            # 尝试转换为字符串
            return str(obj)
        except:
            # 如果无法序列化，则转换为字符串
            return f"<不可序列化的对象: {type(obj).__name__}>"
    
    def load_session_state(self, file_path: str) -> Optional[str]:
        """从文件加载会话状态
        
        Args:
            file_path: 会话状态文件路径
            
        Returns:
            加载成功的会话ID，失败则返回None
        """
        try:
            # 从文件加载状态
            with open(file_path, 'r', encoding='utf-8') as f:
                serialized_state = json.load(f)
            
            # 检查是否包含会话ID
            session_id = None
            if "session_id" in serialized_state:
                session_id = serialized_state["session_id"]
            else:
                # 尝试从文件名提取会话ID
                try:
                    filename = os.path.basename(file_path)
                    if filename.startswith("session_") and filename.endswith(".json"):
                        session_id = filename[8:-5]  # 去除"session_"前缀和".json"后缀
                    else:
                        session_id = str(uuid.uuid4())
                except:
                    session_id = str(uuid.uuid4())
            
            # 准备要恢复的会话数据
            session_data = {}
            
            # 如果会话已存在，复制现有的memory_store
            existing_memory_store = None
            if session_id in self.sessions and "memory_store" in self.sessions[session_id]:
                existing_memory_store = self.sessions[session_id]["memory_store"]
            # 如果不存在，使用全局memory_store
            elif hasattr(self, 'memory_store') and self.memory_store:
                existing_memory_store = self.memory_store
            
            # 首先复制序列化状态中的所有数据
            for key, value in serialized_state.items():
                session_data[key] = value
            
            # 不要恢复memory_store到状态中，因为它不能被序列化
            # memory_store应该从引擎实例中获取
            # if existing_memory_store:
            #     session_data["memory_store"] = existing_memory_store
            
            # 更新会话
            self.sessions[session_id] = session_data
            
            logger.info(f"从文件 {file_path} 成功加载会话: {session_id}")
            return session_id
        except Exception as e:
            logger.error(f"从文件加载会话时出错: {str(e)}")
            return None
    
    def add_to_memory(self, session_id: str, content: str, memory_type: str = "semantic") -> str:
        """添加内容到长期记忆
        
        Args:
            session_id: 会话ID
            content: 记忆内容
            memory_type: 记忆类型
            
        Returns:
            记忆ID
        """
        if not hasattr(self, 'memory_store') or not self.memory_store:
            logger.error("记忆存储未初始化")
            return ""
            
        try:
            # 创建记忆项
            from app.core.memory.store import MemoryItem
            memory_item = MemoryItem(
                content=content,
                type=memory_type,
                metadata={"session_id": session_id, "source": "manual_add"}
            )
            
            # 保存记忆
            memory_id = self.memory_store.save_memory(session_id, memory_item)
            
            if self.verbose:
                logger.info(f"已手动添加记忆: {memory_id}")
            
            return memory_id
        except Exception as e:
            logger.error(f"添加记忆时出错: {str(e)}")
            return ""
    
    def get_relevant_memories(self, session_id: Optional[str], query: str, limit: int = 3) -> List[str]:
        """获取与查询相关的记忆
        
        Args:
            session_id: 会话ID，如果为None则使用系统默认命名空间
            query: 查询文本
            limit: 结果数量限制
            
        Returns:
            相关记忆列表
        """
        if not hasattr(self, 'memory_store') or not self.memory_store:
            logger.error("记忆存储未初始化")
            return []
        
        try:
            # 如果session_id为None，使用"system"作为默认命名空间
            user_id = session_id if session_id is not None else "system"
            
            # 搜索记忆
            memories = self.memory_store.search_memories(user_id, query, limit)
            
            # 返回记忆内容
            return [memory.content for memory in memories]
        except Exception as e:
            logger.error(f"获取相关记忆时出错: {str(e)}")
            return []
    
    def summarize_history(self, session_id: str) -> Optional[str]:
        """总结会话历史
        
        Args:
            session_id: 会话ID
            
        Returns:
            总结文本，失败返回None
        """
        try:
            # 获取会话状态
            state = self.get_session_state(session_id)
            if not state:
                return None
            
            # 获取消息历史
            messages = state.get("messages", [])
            if not messages:
                return "会话历史为空"
            
            # 使用HistoryManager总结历史
            from app.core.memory.history_manager import HistoryManager
            
            # 检查是否应该总结
            if HistoryManager.should_summarize(messages):
                summary = HistoryManager.summarize_messages(messages, self.llm)
                
                # 将总结保存为记忆
                if hasattr(self, 'memory_store') and self.memory_store:
                    from app.core.memory.store import MemoryItem
                    memory_item = MemoryItem(
                        content=summary,
                        type="summary",
                        metadata={"source": "history_summary", "session_id": session_id}
                    )
                    self.memory_store.save_memory(session_id, memory_item)
                    
                    if self.verbose:
                        logger.info(f"已将会话总结保存为记忆: {session_id}")
                
                return summary
            else:
                return "会话太短，无需总结"
        except Exception as e:
            logger.error(f"总结会话历史时出错: {str(e)}")
            return None
    
    def process_message_streaming(
        self, 
        message: str, 
        session_id: Optional[str] = None,
        stream_mode: Union[str, List[str]] = "all",
        manage_history: bool = True  # 添加历史管理参数
    ) -> Generator[Dict[str, Any], None, None]:
        """处理用户消息并流式返回结果
        
        Args:
            message: 用户消息内容
            session_id: 会话ID，如果不提供则创建新会话
            stream_mode: 流模式，可以是单一模式(str)或多种模式组合
            manage_history: 是否管理对话历史
            
        Yields:
            流式消息，格式为{"role": "", "content": ""}
        """
        # 标准化流模式参数
        if isinstance(stream_mode, str):
            if stream_mode.lower() == "all":
                modes = ["messages", "custom", "updates", "values", "events"]
            elif "," in stream_mode:
                modes = [mode.strip() for mode in stream_mode.split(",")]
            else:
                modes = [stream_mode]
        elif isinstance(stream_mode, list):
            modes = stream_mode
        else:
            modes = ["messages", "custom", "updates", "values", "events"]
            
        logger.info(f"流式处理模式: {modes}")
            
        # 确保用户消息非空
        if not message or message.strip() == "":
            yield {"role": "system", "content": "用户消息不能为空"}
            return
        
        # 创建或获取会话
        if not session_id:
            session_id = self.create_session()
            logger.info(f"为流式处理创建新会话: {session_id}")
        else:
            logger.info(f"使用现有会话进行流式处理: {session_id}")
        
        # 获取当前状态
        state = self.get_session_state(session_id)
        if not state:
            logger.info(f"为会话创建初始状态: {session_id}")
            state = self._create_initial_state(session_id)
        
        # 在处理消息前，检查是否需要管理对话历史
        if manage_history:
            messages = state.get("messages", [])
            
            # 检查是否需要总结/删减历史
            if HistoryManager.should_summarize(messages):
                # 总结历史对话
                summary = HistoryManager.summarize_messages(messages, self.llm)
                
                # 添加总结为系统消息，并删减历史
                to_remove = HistoryManager.trim_messages(messages, max_messages=8)
                summary_message = SystemMessage(content=f"对话历史总结: {summary}")
                
                # 更新状态
                if to_remove:
                    for msg in to_remove:
                        if isinstance(msg, RemoveMessage) and "messages" in state:
                            state["messages"] = [m for m in state["messages"] 
                                                if not (hasattr(m, "id") and m.id == msg.id)]
                
                # 添加总结消息
                if "messages" in state:
                    state["messages"].append(summary_message)
                
                # 保存到长期记忆
                self.add_to_memory(
                    session_id=session_id,
                    content=summary,
                    memory_type="episodic"
                )
                
                logger.info(f"会话 {session_id} 历史已总结和优化")
        
        # 获取或创建对话轮次管理器
        if session_id not in self.turn_managers:
            self.turn_managers[session_id] = create_conversation_turn_manager(session_id)
        
        turn_manager = self.turn_managers[session_id]
        
        # 记录用户输入轮次
        user_turn_id = turn_manager.start_user_turn(message)
        logger.info(f"用户输入轮次: {user_turn_id}")
        
        # 记忆增强：使用记忆适配器进行预处理
        if self.memory_adapter and hasattr(self.memory_adapter, 'pre_execution_hook'):
            try:
                state = self.memory_adapter.pre_execution_hook(state, "system")
                logger.info("✅ 记忆增强预处理完成")
            except Exception as e:
                logger.warning(f"记忆增强预处理失败: {str(e)}")
        
        # 添加用户消息（使用传统方式，保持向后兼容）
        user_message = HumanMessage(content=message)
        
        # 更新状态消息
        if "messages" not in state:
            state["messages"] = []
        state["messages"].append(user_message)
        
        # 保存初始状态用于后续更新
        latest_state = copy.deepcopy(state)
        
        try:
            logger.info(f"开始流式处理用户消息: {message[:30]}...")
            
            # 使用stream方法执行工作流图
            stream_generator = self.workflow_graph.stream(
                state,
                config=self.graph_builder.create_thread_config(session_id),
                stream_mode=modes
            )
            
            # 根据环境变量设置调试模式
            if os.environ.get("ISOTOPE_DEBUG", "0") == "1":
                self.streamer.debug_mode = True
                logger.info("开启详细流处理日志")
            
            # 临时启用调试日志来排查问题
            logger.setLevel(logging.DEBUG)
            logging.getLogger("app.ui.streaming").setLevel(logging.DEBUG)
            logger.info("临时启用调试级别日志以排查流式输出问题")
            
            # 使用LangGraphStreamer处理流，返回格式化消息
            yielded_count = 0
            last_messages = []
            current_ai_message = None
            assistant_turn_started = False
            
            # 跟踪工具执行结果，确保能够向前端传递
            tool_executions = []
            
            for message_item in self.streamer.process_stream(stream_generator):
                yielded_count += 1            
                
                # 调试：记录每个消息项的结构
                logger.debug(f"[DEBUG] 收到消息项 #{yielded_count}: type={type(message_item)}, keys={list(message_item.keys()) if isinstance(message_item, dict) else 'N/A'}")
                if isinstance(message_item, dict):
                    logger.debug(f"[DEBUG] 消息内容: role={message_item.get('role')}, content_length={len(str(message_item.get('content', '')))}, has_content={bool(message_item.get('content'))}")
                
                # 处理消息并更新状态
                if message_item and isinstance(message_item, dict):
                    role = message_item.get("role")
                    content = message_item.get("content")
                    source = message_item.get("source", "unknown")
                    
                    # 调试：记录角色和内容
                    logger.debug(f"[DEBUG] 提取字段: role='{role}', content_exists={content is not None}, content_length={len(str(content)) if content else 0}")
                    
                    if role and content:
                        logger.info(f"✅ 有效消息: role={role}, content={str(content)[:100]}...")
                        
                        # 根据角色创建相应的消息对象
                        if role == "assistant":
                            # 开始助手轮次（如果还没有开始）
                            if not assistant_turn_started:
                                turn_manager.start_assistant_turn(source=source)
                                assistant_turn_started = True
                                logger.info(f"助手回复轮次开始")
                            
                            # 添加内容到轮次管理器
                            turn_manager.add_assistant_content(content, message_item)
                            
                            # 传统状态管理（保持向后兼容）
                            if current_ai_message is None:
                                current_ai_message = AIMessage(content=content)
                                latest_state["messages"].append(current_ai_message)
                            else:
                                        current_ai_message.content = content
                            last_messages.append(message_item)
                        elif role == "system":
                            system_message = SystemMessage(content=content)
                            latest_state["messages"].append(system_message)
                        elif role == "tool":
                            tool_message = ToolMessage(
                                content=content,
                                tool_call_id=message_item.get("tool_call_id", ""),
                                name=message_item.get("name", "")
                            )
                            latest_state["messages"].append(tool_message)
                            
                            # 记录工具执行结果
                            tool_executions.append(message_item)
                    else:
                        logger.warning(f"⚠️ 跳过消息: role='{role}', content_exists={content is not None}")
                logger.info(f"打包后message_item: {message_item}")
                # 产生消息
                yield message_item
            
            logger.info(f"流处理完成，共生成 {yielded_count} 个响应")
            
            # 完成助手轮次
            if assistant_turn_started:
                completed_turn_id = turn_manager.complete_assistant_turn()
                logger.info(f"助手轮次完成: {completed_turn_id}")
            else:
                # 关键修复：即使没有检测到assistant消息，也要尝试完成潜在的轮次
                if turn_manager.current_assistant_turn:
                    logger.warning("检测到未完成的助手轮次，强制完成")
                    completed_turn_id = turn_manager.complete_assistant_turn()
                    logger.info(f"强制完成助手轮次: {completed_turn_id}")
            
            # 更新会话状态 - 修复：正确处理轮次管理器的历史记录
            if session_id in self.sessions:
                # 关键修复：从轮次管理器获取LangChain格式的完整对话历史，而不是API格式
                complete_conversation = turn_manager.get_conversation_history()
                latest_state["messages"] = complete_conversation
                
                logger.info(f"从轮次管理器更新会话历史: {len(complete_conversation)} 条消息")
                
                self.sessions[session_id]["state"] = latest_state
                self.sessions[session_id]["last_updated"] = datetime.now().isoformat()
                
                # 保存对话内容到记忆
                try:
                    # 获取最后一条完整的AI消息用于保存
                    if turn_manager.completed_turns:
                        last_turn = turn_manager.completed_turns[-1]
                        if hasattr(last_turn, 'complete_content') and last_turn.complete_content:
                            last_message = last_turn.complete_content
                        # 保存完整对话
                        memory_id = self.add_to_memory(
                            session_id=session_id,
                            content=f"用户: {message}\n助手: {last_message}",
                            memory_type="semantic"
                        )
                        logger.info(f"已保存对话到记忆，ID: {memory_id}")
                        
                        # 如果对话内容较长，保存一个摘要版本方便检索
                        if len(message) > 20 and len(last_message) > 100:
                            summary_id = self.add_to_memory(
                                session_id=session_id,
                                content=f"用户问题: {message}\n回答要点: {last_message[:200]}",
                                memory_type="semantic"
                            )
                            logger.info(f"已保存对话摘要到记忆，ID: {summary_id}")
                except Exception as mem_error:
                    logger.error(f"保存对话记忆失败: {str(mem_error)}")
            
        except Exception as e:
            # 错误处理
            error_msg = f"流处理错误: {str(e)}"
            logger.error(error_msg, exc_info=True)
            yield {"role": "system", "content": error_msg}
            
            # 尝试保留会话状态
            if session_id in self.sessions:
                self.sessions[session_id]["state"] = latest_state
                self.sessions[session_id]["last_error"] = str(e)
                self.sessions[session_id]["last_updated"] = datetime.now().isoformat()
    
    def _is_image_result(self, content: str, tool_name: str) -> bool:
        """检查工具结果是否包含图片
        
        Args:
            content: 工具执行结果内容
            tool_name: 工具名称
            
        Returns:
            是否包含图片
        """
        # 检查工具名称是否包含图像相关关键词
        image_related_names = [
            "generate_test_image", "plot", "chart", "image", "figure", 
            "visualization", "图片", "图像", "可视化"
        ]
        
        # 检查内容是否包含图片路径相关关键词
        image_path_indicators = [
            "png", "jpg", "jpeg", "gif", "bmp", 
            "image", "图片已保存", "图片地址", "图片路径", 
            "data/generated", "/generated/", "file_id"
        ]
        
        # 检查工具名称
        name_match = any(keyword in tool_name.lower() for keyword in image_related_names)
        
        # 检查内容
        content_match = isinstance(content, str) and any(
            indicator in content.lower() for indicator in image_path_indicators
        )
        
        return name_match or content_match
    
    def _extract_image_path(self, content: str) -> Optional[str]:
        """从工具结果中提取图片路径
        
        Args:
            content: 工具执行结果内容
            
        Returns:
            提取的图片路径，如果未找到则返回None
        """
        # 使用正则表达式提取路径
        import re
        
        # 匹配可能的文件路径
        path_patterns = [
            r"(data/generated/[\w\-\.]+\.(png|jpg|jpeg|gif|bmp))",  # 相对路径
            r"(/[\w\-\.\/]+\.(png|jpg|jpeg|gif|bmp))",  # 绝对路径
            r"(D:/[\w\-\.\/]+\.(png|jpg|jpeg|gif|bmp))"  # Windows路径
        ]
        
        for pattern in path_patterns:
            matches = re.findall(pattern, content)
            if matches:
                # 匹配结果可能是元组 (完整匹配, 扩展名)
                if isinstance(matches[0], tuple):
                    return matches[0][0]
                return matches[0]
        
        return None

    def _create_initial_state(self, session_id: str) -> Dict[str, Any]:
        """创建会话初始状态
        
        Args:
            session_id: 会话ID
            
        Returns:
            初始状态字典
        """
        # 创建基本状态结构
        state = {
            "messages": [],
            "metadata": {
                "session_id": session_id,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
        }
        
        # 不要将记忆存储对象直接放入状态，因为它不能被msgpack序列化
        # 如果需要访问记忆存储，应该从引擎实例中获取
        # state["memory_store"] = self.memory_store  # 注释掉这行
        state["session_id"] = session_id
        
        return state

    def get_session_by_id(self, session_id):
        """根据会话ID获取会话
        
        Args:
            session_id: 会话ID
            
        Returns:
            会话对象，如果不存在则返回None
        """
        if not session_id:
            return None
        
        return self.sessions.get(session_id)

    def set_thinking_mode(self, show_thinking: bool) -> None:
        """设置是否显示思考过程
        
        Args:
            show_thinking: 是否显示思考过程
        """
        self.config["show_thinking"] = show_thinking
        logger.info(f"引擎思考模式已{'启用' if show_thinking else '禁用'}")
        
        # 更新流处理器的设置
        if hasattr(self, 'stream_manager'):
            self.stream_manager.show_thinking = show_thinking
            
    def delete_session(self, session_id: str) -> bool:
        """删除会话
        
        Args:
            session_id: 会话ID
            
        Returns:
            是否成功删除
        """
        if session_id not in self.sessions:
            logger.warning(f"会话不存在: {session_id}")
            return False
            
        try:
            # 1. 从内存中删除会话
            del self.sessions[session_id]
            logger.info(f"从内存中删除会话: {session_id}")
            
            # 2. 如果启用了PostgreSQL会话持久化，也从数据库中删除
            if self.session_persistence_enabled and self.postgres_session_manager:
                try:
                    postgres_success = self.postgres_session_manager.delete_session(session_id, soft_delete=False)
                    if postgres_success:
                        logger.info(f"从PostgreSQL中删除会话: {session_id}")
                    else:
                        logger.warning(f"从PostgreSQL删除会话失败: {session_id}")
                except Exception as e:
                    logger.error(f"从PostgreSQL删除会话时出错: {str(e)}")
            
            # 3. 删除文件检查点（如果存在）
            try:
                checkpoint_file = os.path.join(self.checkpoint_dir, f"session_{session_id}.json")
                if os.path.exists(checkpoint_file):
                    os.remove(checkpoint_file)
                    logger.info(f"删除检查点文件: {checkpoint_file}")
            except Exception as e:
                logger.warning(f"删除检查点文件失败: {str(e)}")
            
            logger.info(f"会话删除完成: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除会话失败: {str(e)}")
            return False
            
    def get_enhanced_dag_visualization(self) -> Optional[str]:
        """获取增强DAG可视化"""
        if hasattr(self.graph_builder, 'get_dag_visualization'):
            return self.graph_builder.get_dag_visualization()
        return None
    
    def get_enhanced_dag_html_visualization(self) -> Optional[str]:
        """获取增强DAG HTML可视化"""
        if hasattr(self.graph_builder, 'get_dag_html_visualization'):
            return self.graph_builder.get_dag_html_visualization()
        return None
    
    def generate_graph_image(self) -> Union[str, bytes, None]:
        """生成工作流图结构的可视化图像
        
        Returns:
            图像数据，可能是base64编码字符串或二进制数据
        """
        try:
            if not hasattr(self, 'graph_builder') or not self.graph_builder:
                logger.warning("图构建器不存在，无法生成图像")
                return None
                
            if not hasattr(self, 'workflow_graph') or not self.workflow_graph:
                logger.warning("工作流图不存在，无法生成图像")
                return None
                
            logger.info("开始生成工作流图结构图像...")
            
            # 获取图对象
            try:
                graph_obj = self.workflow_graph.get_graph()
                logger.info("成功获取图对象")
            except Exception as e:
                logger.error(f"获取图对象失败: {str(e)}")
                return None
            
            # 首先获取Mermaid文本 - 这是所有可视化的基础
            try:
                mermaid_text = graph_obj.draw_mermaid()
                logger.info("成功获取Mermaid文本表示")
            except Exception as e:
                logger.error(f"获取Mermaid文本表示失败: {str(e)}")
                return None
            
            # 尝试不同的方法生成图像

            # 1. 尝试使用Graphviz生成PNG图像（速度最快，质量最好）
            try:
                logger.info("尝试使用Graphviz生成PNG图像...")
                png_data = graph_obj.draw_png()
                logger.info("成功生成Graphviz PNG图像")
                
                # 将二进制图像转换为base64编码，以便在Gradio界面中显示
                import base64
                from io import BytesIO
                
                # 转换为base64编码
                base64_png = base64.b64encode(png_data).decode('utf-8')
                data_url = f"data:image/png;base64,{base64_png}"
                logger.info("成功生成base64编码的PNG图像")
                return data_url
            except Exception as e:
                logger.warning(f"使用Graphviz生成PNG失败: {str(e)}")
            
            # 2. 尝试使用mermaid-py模块（如果安装了）
            try:
                import importlib
                if importlib.util.find_spec("mermaid"):
                    logger.info("尝试使用mermaid-py生成图像...")
                    from mermaid import compile_mermaid
                    
                    # 编译mermaid文本为图像
                    png_data = compile_mermaid(mermaid_text, output_format="png")
                    
                    # 编码为base64
                    import base64
                    base64_png = base64.b64encode(png_data).decode('utf-8')
                    data_url = f"data:image/png;base64,{base64_png}"
                    logger.info("成功使用mermaid-py生成图像")
                    return data_url
            except Exception as e:
                logger.warning(f"使用mermaid-py生成图像失败: {str(e)}")
            
            # 3. 尝试使用LangGraph内置方法生成PNG
            try:
                logger.info("尝试使用LangGraph内置方法生成PNG图像...")
                
                # 使用MermaidDrawMethod.API可能依赖外部服务，因此如果失败可能是网络原因
                from langchain_core.runnables.graph import CurveStyle, MermaidDrawMethod, NodeStyles
                
                png_data = graph_obj.draw_mermaid_png(
                    curve_style=CurveStyle.LINEAR,
                    node_colors=NodeStyles(first="#ffdfba", last="#baffc9", default="#f2f0ff"),
                    draw_method=MermaidDrawMethod.API,
                )
                
                # 检查结果是否为二进制数据
                if png_data and isinstance(png_data, bytes):
                    # 转换为base64
                    import base64
                    base64_png = base64.b64encode(png_data).decode('utf-8')
                    data_url = f"data:image/png;base64,{base64_png}"
                    logger.info("成功使用LangGraph API生成PNG图像")
                    return data_url
            except Exception as e:
                logger.warning(f"使用LangGraph内置方法生成PNG失败: {str(e)}")
            
            # 4. 最后的备选方案：创建嵌入Mermaid的HTML
            logger.info("使用HTML嵌入Mermaid作为备选方案")
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
                <script>
                    mermaid.initialize({{
                        startOnLoad: true,
                        theme: 'default',
                        flowchart: {{
                            curve: 'linear'
                        }}
                    }});
                </script>
                <style>
                    body {{ margin: 0; padding: 10px; background: white; }}
                    .mermaid {{ max-width: 100%; }}
                </style>
            </head>
            <body>
                <div class="mermaid">
                {mermaid_text}
                </div>
            </body>
            </html>
            """
            
            # 编码为base64
            import base64
            encoded_html = base64.b64encode(html_content.encode('utf-8')).decode('utf-8')
            data_url = f"data:text/html;base64,{encoded_html}"
            logger.info("返回嵌入Mermaid的HTML Data URL")
            
            return data_url
                
        except Exception as e:
            logger.error(f"生成图结构图像失败: {str(e)}")
            return None

    def add_file_to_session(self, file_path: str, file_name: str, session_id: Optional[str] = None, file_type: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """添加文件到会话
        
        Args:
            file_path: 文件路径
            file_name: 文件名
            session_id: 会话ID，如果为None则使用默认会话
            file_type: 文件类型，如果为None则自动推断
            metadata: 文件元数据
            
        Returns:
            文件信息字典
        """
        # 导入文件管理器
        from app.core.file_manager import file_manager
        
        # 处理会话ID
        if session_id is None:
            session_id = self._get_default_session_id()
            if session_id is None:
                logger.warning("未指定会话ID且没有默认会话，创建新会话")
                session_id = self.create_session()
        
        # 检查会话是否存在
        session = self.get_session_by_id(session_id)
        if not session:
            raise ValueError(f"会话ID无效: {session_id}")
        
        try:
            # 准备文件元数据
            if metadata is None:
                metadata = {}
            
            # 添加ID格式说明到元数据
            metadata["id_format"] = "简短ID格式: u-上传文件, g-生成文件, t-临时文件"
            
            # 使用文件管理器注册文件
            file_info = file_manager.register_file(
                file_path=file_path,
                file_name=file_name,
                file_type=file_type,
                source="upload",
                session_id=session_id,
                metadata=metadata
            )
            
            # 获取会话状态
            state = self.get_session_state(session_id)
            if state is not None:
                # 更新状态中的文件信息
                files = state.get("files", {})
                file_id = file_info["file_id"]
                files[file_id] = file_info
                
                # 更新状态
                state["files"] = files
                
                # 保存会话状态
                self._update_session_state(session_id, state)
                
                logger.info(f"文件 {file_name} (ID: {file_id}) 已添加到会话 {session_id}")
            
            # 返回文件信息
            return file_info
        
        except Exception as e:
            logger.error(f"添加文件到会话 {session_id} 时出错: {str(e)}")
            raise

    def get_session_files(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取会话的所有文件
        
        Args:
            session_id: 会话ID，如果为None则使用默认会话
            
        Returns:
            文件信息列表
        """
        # 导入文件管理器
        from app.core.file_manager import file_manager
        
        # 处理会话ID
        if session_id is None:
            session_id = self._get_default_session_id()
            if session_id is None:
                logger.warning("未指定会话ID且没有默认会话")
                return []
        
        try:
            # 使用文件管理器获取会话文件
            files = file_manager.get_session_files(session_id)
            return files
        except Exception as e:
            logger.error(f"获取会话 {session_id} 的文件时出错: {str(e)}")
            return []

    def get_file_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """获取文件信息
        
        Args:
            file_id: 文件ID
            
        Returns:
            文件信息字典，如果文件不存在则返回None
        """
        # 导入文件管理器
        from app.core.file_manager import file_manager
        
        try:
            # 使用文件管理器获取文件信息
            file_info = file_manager.get_file_info(file_id)
            return file_info
        except Exception as e:
            logger.error(f"获取文件 {file_id} 的信息时出错: {str(e)}")
            return None

    def delete_file(self, file_id: str, session_id: Optional[str] = None) -> bool:
        """从会话中删除文件
        
        Args:
            file_id: 文件ID
            session_id: 会话ID，如果为None则使用默认会话
            
        Returns:
            是否成功删除
        """
        # 导入文件管理器
        from app.core.file_manager import file_manager
        
        # 处理会话ID
        if session_id is None:
            session_id = self._get_default_session_id()
            if session_id is None:
                logger.warning("未指定会话ID且没有默认会话")
                return False
        
        try:
            # 获取会话状态
            state = self.get_session_state(session_id)
            if state is None:
                return False
            
            # 更新状态中的文件信息
            files = state.get("files", {})
            if file_id in files:
                del files[file_id]
                
                # 更新状态
                state["files"] = files
                
                # 保存会话状态
                self._update_session_state(session_id, state)
                
                logger.info(f"文件 {file_id} 已从会话 {session_id} 移除")
            
            # 使用文件管理器删除文件
            return file_manager.delete_file(file_id)
        except Exception as e:
            logger.error(f"删除文件 {file_id} 时出错: {str(e)}")
            return False

    def _update_session_state(self, session_id: str, state: IsotopeSystemState) -> bool:
        """更新会话状态
        
        Args:
            session_id: 会话ID
            state: 新的会话状态
            
        Returns:
            是否成功更新
        """
        if session_id not in self.sessions:
            logger.warning(f"会话不存在: {session_id}")
            return False
        
        try:
            # 更新会话状态
            self.sessions[session_id]["state"] = state
            self.sessions[session_id]["last_updated"] = datetime.now().isoformat()
            
            logger.info(f"会话 {session_id} 状态已更新")
            return True
        except Exception as e:
            logger.error(f"更新会话状态时出错: {str(e)}")
            return False

    def _get_default_session_id(self) -> Optional[str]:
        """获取默认会话ID
        
        Returns:
            默认会话ID，如果找不到则返回None
        """
        # 实现获取默认会话ID的逻辑
        # 这里可以根据需要实现不同的逻辑来获取默认会话ID
        # 例如，可以返回第一个会话ID，或者根据某些条件返回特定的会话ID
        return next(iter(self.sessions), None)
    

    
    def _auto_save_session(self, session_id: str, state: IsotopeSystemState) -> None:
        """自动保存会话状态
        
        Args:
            session_id: 会话ID
            state: 当前会话状态
        """
        logger.info(f"达到自动保存间隔 ({self.autosave_interval}秒)，正在保存会话状态...")
        self.save_session_state(session_id)
        logger.info(f"会话状态已自动保存，最后保存时间更新为: {datetime.fromtimestamp(self.last_autosave)}")
    
    def _restore_existing_sessions(self) -> None:
        """恢复现有会话状态
        
        优先从PostgreSQL恢复会话，如果PostgreSQL不可用则从文件检查点恢复
        """
        restored_count = 0
        failed_count = 0
        
        try:
            # 1. 优先尝试从PostgreSQL恢复会话
            if self.session_persistence_enabled and self.postgres_session_manager:
                logger.info("开始从PostgreSQL恢复会话...")
                
                try:
                    restore_result = self.postgres_session_manager.restore_all_sessions()
                    
                    if restore_result.get("success", False):
                        # 恢复成功，将会话加载到内存
                        postgres_sessions = restore_result.get("sessions", {})
                        
                        for session_id, session_data in postgres_sessions.items():
                            try:
                                # 重建会话结构
                                self.sessions[session_id] = {
                                    "state": session_data["state"],
                                    "created_at": session_data["created_at"],
                                    "last_updated": session_data["last_updated"],
                                    "metadata": session_data["metadata"]
                                }
                                restored_count += 1
                                logger.debug(f"从PostgreSQL成功恢复会话: {session_id}")
                                
                            except Exception as e:
                                failed_count += 1
                                logger.error(f"处理PostgreSQL会话 {session_id} 时出错: {str(e)}")
                        
                        logger.info(f"PostgreSQL会话恢复完成: 成功 {restored_count} 个，失败 {failed_count} 个")
                        
                        # 如果PostgreSQL恢复成功，就不需要从文件恢复了
                        if restored_count > 0:
                            self._log_restored_sessions_info(restored_count, failed_count)
                            return

                        
                    else:
                        logger.warning(f"PostgreSQL会话恢复失败: {restore_result.get('error', '未知错误')}")
                        
                except Exception as e:
                    logger.error(f"从PostgreSQL恢复会话时出错: {str(e)}")
            
            # 2. 回退到文件检查点恢复
            logger.info("开始从文件检查点恢复会话...")
            self._restore_sessions_from_files()
            
        except Exception as e:
            logger.error(f"恢复现有会话时出错: {str(e)}")
            logger.error(f"错误详情: {traceback.format_exc()}")
    
    def _restore_sessions_from_files(self) -> None:
        """从文件检查点恢复会话"""
        restored_count = 0
        failed_count = 0
        
        try:
            # 确保检查点目录存在
            if not os.path.exists(self.checkpoint_dir):
                logger.info(f"检查点目录不存在: {self.checkpoint_dir}，跳过文件会话恢复")
                return
            
            logger.info(f"开始扫描检查点目录: {self.checkpoint_dir}")
            
            # 扫描检查点目录中的所有会话文件
            session_files = []
            for filename in os.listdir(self.checkpoint_dir):
                if filename.startswith("session_") and filename.endswith(".json"):
                    session_files.append(filename)
            
            if not session_files:
                logger.info("检查点目录中没有找到会话文件")
                return
            
            logger.info(f"找到 {len(session_files)} 个会话文件，开始恢复...")
            
            # 逐个加载会话文件
            for filename in session_files:
                try:
                    file_path = os.path.join(self.checkpoint_dir, filename)
                    session_id = self._restore_single_session(file_path)
                    
                    if session_id:
                        restored_count += 1
                        logger.debug(f"成功恢复会话: {session_id}")
                    else:
                        failed_count += 1
                        logger.warning(f"恢复会话文件失败: {filename}")
                        
                except Exception as e:
                    failed_count += 1
                    logger.error(f"处理会话文件 {filename} 时出错: {str(e)}")
            
            # 记录恢复结果
            logger.info(f"文件会话恢复完成: 成功 {restored_count} 个，失败 {failed_count} 个")
            self._log_restored_sessions_info(restored_count, failed_count)
            
        except Exception as e:
            logger.error(f"从文件恢复会话时出错: {str(e)}")
    
    def _log_restored_sessions_info(self, restored_count: int, failed_count: int) -> None:
        """记录恢复的会话信息"""
        if restored_count > 0:
            logger.info(f"当前活跃会话数: {len(self.sessions)}")
            
            # 显示恢复的会话信息
            if self.verbose:
                for session_id, session_data in self.sessions.items():
                    state = session_data.get("state", {})
                    messages_count = len(state.get("messages", []))
                    created_at = session_data.get("created_at", "未知")
                    metadata = session_data.get("metadata", {})
                    session_name = metadata.get("name", "未命名")
                    
                    logger.info(f"  会话 {session_id[:8]}... ({session_name}): "
                              f"{messages_count} 条消息, 创建于 {created_at}")
    
    def _restore_single_session(self, file_path: str) -> Optional[str]:
        """恢复单个会话状态
        
        Args:
            file_path: 会话文件路径
            
        Returns:
            成功恢复的会话ID，失败返回None
        """
        try:
            # 读取会话文件
            with open(file_path, 'r', encoding='utf-8') as f:
                checkpoint_data = json.load(f)
            
            # 验证文件格式
            if not isinstance(checkpoint_data, dict):
                logger.warning(f"会话文件格式错误（不是字典）: {file_path}")
                return None
            
            # 提取会话ID
            session_id = checkpoint_data.get("session_id")
            if not session_id:
                # 尝试从文件名提取会话ID
                filename = os.path.basename(file_path)
                if filename.startswith("session_") and filename.endswith(".json"):
                    session_id = filename[8:-5]  # 去除"session_"前缀和".json"后缀
                else:
                    logger.warning(f"无法从文件中提取会话ID: {file_path}")
                    return None
            
            # 检查会话是否已经存在（避免重复加载）
            if session_id in self.sessions:
                logger.debug(f"会话 {session_id} 已存在，跳过恢复")
                return session_id
            
            # 提取状态数据
            state = checkpoint_data.get("state")
            if not state:
                logger.warning(f"会话文件中没有状态数据: {file_path}")
                return None
            
            # 重建会话数据结构
            session_data = {
                "state": state,
                "created_at": checkpoint_data.get("timestamp", datetime.now().isoformat()),
                "last_updated": checkpoint_data.get("timestamp", datetime.now().isoformat()),
                "metadata": checkpoint_data.get("metadata", {})
            }
            
            # 如果状态中有metadata，合并到会话级别的metadata
            state_metadata = state.get("metadata", {})
            if state_metadata:
                session_data["metadata"].update(state_metadata)
            
            # 添加到会话字典
            self.sessions[session_id] = session_data
            
            # 验证恢复的数据
            restored_state = self.get_session_state(session_id)
            if restored_state is None:
                logger.warning(f"恢复后无法获取会话状态: {session_id}")
                # 清理失败的会话
                if session_id in self.sessions:
                    del self.sessions[session_id]
                return None
            
            # 刷新会话中的文件信息（如果有文件管理器）
            try:
                self._refresh_session_files(restored_state, session_id)
            except Exception as refresh_error:
                logger.debug(f"刷新会话文件信息时出错: {str(refresh_error)}")
            
            return session_id
            
        except json.JSONDecodeError as e:
            logger.error(f"会话文件JSON格式错误: {file_path}, 错误: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"恢复会话文件时出错: {file_path}, 错误: {str(e)}")
            return None
    
    def _refresh_session_files(self, state: IsotopeSystemState, session_id: str) -> None:
        """刷新会话中的文件信息
        
        Args:
            state: 会话状态
            session_id: 会话ID
        """
        try:
            # 检查会话中的文件是否仍然存在
            files = state.get("files", {})
            if not files:
                return
            
            updated_files = {}
            missing_files = []
            
            for file_id, file_info in files.items():
                file_path = file_info.get("file_path")
                if file_path and os.path.exists(file_path):
                    # 更新文件的修改时间等信息
                    try:
                        file_stat = os.stat(file_path)
                        file_info["last_modified"] = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
                        file_info["file_size"] = file_stat.st_size
                        updated_files[file_id] = file_info
                    except Exception as e:
                        logger.debug(f"更新文件信息失败 {file_path}: {str(e)}")
                        updated_files[file_id] = file_info  # 保留原信息
                else:
                    missing_files.append(file_id)
                    logger.debug(f"会话 {session_id} 中的文件已丢失: {file_path}")
            
            # 更新状态中的文件信息
            if updated_files != files:
                state["files"] = updated_files
                
            # 记录丢失的文件
            if missing_files:
                logger.info(f"会话 {session_id} 中有 {len(missing_files)} 个文件已丢失")
                
        except Exception as e:
            logger.debug(f"刷新会话文件信息时出错: {str(e)}")
    
    def get_restored_sessions_info(self) -> Dict[str, Any]:
        """获取已恢复会话的统计信息
        
        Returns:
            会话统计信息字典
        """
        total_sessions = len(self.sessions)
        total_messages = 0
        sessions_with_files = 0
        sessions_info = []
        
        for session_id, session_data in self.sessions.items():
            state = session_data.get("state", {})
            messages = state.get("messages", [])
            files = state.get("files", {})
            metadata = session_data.get("metadata", {})
            
            message_count = len(messages)
            file_count = len(files)
            total_messages += message_count
            
            if file_count > 0:
                sessions_with_files += 1
            
            session_info = {
                "session_id": session_id,
                "name": metadata.get("name", "未命名"),
                "message_count": message_count,
                "file_count": file_count,
                "created_at": session_data.get("created_at"),
                "last_updated": session_data.get("last_updated")
            }
            sessions_info.append(session_info)
        
        # 按最后更新时间排序
        sessions_info.sort(key=lambda x: x.get("last_updated", ""), reverse=True)
        
        return {
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "sessions_with_files": sessions_with_files,
            "average_messages_per_session": total_messages / total_sessions if total_sessions > 0 else 0,
            "sessions": sessions_info
        }
    
    # 增强方法 - 人类在环交互
    def process_human_approval(
        self, 
        request_id: str, 
        human_input: str, 
        user_id: str = "user",
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """处理人类审批响应
        
        Args:
            request_id: 审批请求ID
            human_input: 人类输入
            user_id: 用户ID
            session_id: 会话ID
            
        Returns:
            审批处理结果
        """
        logger.info(f"处理人类审批响应: {request_id}")
        
        try:
            if not self.human_approval_gate:
                return {
                    "status": "error",
                    "message": "人类审批门未初始化"
                }
            
            # 处理审批响应
            approval_result = self.human_approval_gate.process_human_response(
                request_id=request_id,
                human_input=human_input,
                user_id=user_id
            )
            
            # 如果有会话ID，更新会话状态
            if session_id and session_id in self.sessions:
                session_state = self.sessions[session_id]["state"]
                session_state["metadata"]["last_approval_result"] = approval_result
                session_state["metadata"]["last_approval_timestamp"] = time.time()
            
            return approval_result
            
        except Exception as e:
            logger.error(f"处理人类审批失败: {str(e)}")
            return {
                "status": "error",
                "message": f"处理审批失败: {str(e)}"
            }
    
    def get_pending_approvals(self) -> Dict[str, Any]:
        """获取待审批请求"""
        if self.human_approval_gate:
            return self.human_approval_gate.get_pending_approvals()
        else:
            return {}
    
    def get_routing_statistics(self) -> Dict[str, Any]:
        """获取路由统计信息"""
        if self.smart_router:
            return self.smart_router.get_routing_statistics()
        else:
            return {"message": "智能路由器未初始化"}
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态信息"""
        
        # 基础状态
        base_status = {
            "sessions_count": len(self.sessions),
            "total_messages": sum(
                len(session["state"].get("messages", [])) 
                for session in self.sessions.values()
            ),
            "agents_registered": len(agent_registry.get_all_agents()),
            "tools_available": len(self.tools),
            "checkpointer_backend": getattr(self.graph_builder, "checkpoint_backend", "unknown"),
            "timestamp": time.time()
        }
        
        # 核心智能体状态
        core_agents_status = {
            "meta_supervisor": self.meta_supervisor is not None,
            "task_planner": self.task_planner is not None,
            "runtime_supervisor": self.runtime_supervisor is not None,
            "smart_router": self.smart_router is not None,
            "task_dispatcher": self.task_dispatcher is not None,
            "human_approval_gate": self.human_approval_gate is not None
        }
        
        # 执行统计
        execution_stats = {}
        if hasattr(self.graph_builder, "get_execution_statistics"):
            execution_stats = self.graph_builder.get_execution_statistics()
        
        # 路由统计
        routing_stats = self.get_routing_statistics()
        
        # 待审批请求
        pending_approvals = self.get_pending_approvals()
        
        return {
            **base_status,
            "core_agents": core_agents_status,
            "execution_statistics": execution_stats,
            "routing_statistics": routing_stats,
            "pending_approvals_count": len(pending_approvals),
            "pending_approval_ids": list(pending_approvals.keys())
        }
    
    def interrupt_task(
        self, 
        session_id: str, 
        reason: str = "用户中断",
        save_checkpoint: bool = True
    ) -> Dict[str, Any]:
        """中断任务执行
        
        Args:
            session_id: 会话ID
            reason: 中断原因
            save_checkpoint: 是否保存检查点
            
        Returns:
            中断结果
        """
        logger.info(f"中断任务执行: {session_id}, 原因: {reason}")
        
        try:
            if session_id not in self.sessions:
                return {
                    "status": "error",
                    "message": f"会话不存在: {session_id}"
                }
            
            # 保存当前状态检查点
            if save_checkpoint:
                checkpoint_saved = self.save_session_state(session_id)
                if not checkpoint_saved:
                    logger.warning(f"会话{session_id}检查点保存失败")
            
            # 更新会话状态
            session_state = self.sessions[session_id]["state"]
            session_state["metadata"]["interrupted"] = True
            session_state["metadata"]["interrupt_reason"] = reason
            session_state["metadata"]["interrupt_timestamp"] = time.time()
            
            # 添加中断消息
            interrupt_message = SystemMessage(
                content=f"⚠️ 任务已被中断: {reason}"
            )
            session_state["messages"].append(interrupt_message)
            
            return {
                "status": "success",
                "message": f"任务已成功中断: {reason}",
                "checkpoint_saved": save_checkpoint,
                "interrupt_timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"中断任务失败: {str(e)}")
            return {
                "status": "error", 
                "message": f"中断任务失败: {str(e)}"
            }
    
    def resume_interrupted_task(
        self, 
        session_id: str,
        user_modifications: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """恢复中断的任务
        
        Args:
            session_id: 会话ID
            user_modifications: 用户修改的参数
            
        Returns:
            恢复结果
        """
        logger.info(f"恢复中断任务: {session_id}")
        
        try:
            if session_id not in self.sessions:
                return {
                    "status": "error",
                    "message": f"会话不存在: {session_id}"
                }
            
            session_state = self.sessions[session_id]["state"]
            
            # 检查是否为中断状态
            if not session_state.get("metadata", {}).get("interrupted", False):
                return {
                    "status": "error",
                    "message": "任务未处于中断状态"
                }
            
            # 应用用户修改
            if user_modifications:
                logger.info(f"应用用户修改: {user_modifications}")
                for key, value in user_modifications.items():
                    if key in ["task_plan", "execution_strategy"]:
                        session_state["metadata"][key].update(value)
                    else:
                        session_state["metadata"][key] = value
            
            # 清除中断标志
            session_state["metadata"]["interrupted"] = False
            session_state["metadata"]["resumed"] = True
            session_state["metadata"]["resume_timestamp"] = time.time()
            
            # 添加恢复消息
            resume_message = SystemMessage(
                content="🔄 任务已恢复执行"
            )
            session_state["messages"].append(resume_message)
            
            return {
                "status": "success",
                "message": "任务已成功恢复",
                "modifications_applied": user_modifications is not None,
                "resume_timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"恢复中断任务失败: {str(e)}")
            return {
                "status": "error",
                "message": f"恢复任务失败: {str(e)}"
            }
    
    def cleanup_expired_approvals(self):
        """清理过期的审批请求"""
        if self.human_approval_gate:
            self.human_approval_gate.cleanup_expired_approvals()
    