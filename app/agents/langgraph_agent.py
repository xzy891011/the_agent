"""
LangGraph-based Agent Implementation
基于LangGraph的智能体实现，完全使用新架构
"""

import json
import logging
import traceback
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from app.core.state import IsotopeSystemState, StateManager
from app.core.task_decorator import task_registry
from app.core.system_capability_registry import system_capability_registry, CapabilityType
from app.tools.registry import get_tool_registry
import time

# 导入记忆系统模块
from app.core.memory.enhanced_memory_integration import EnhancedMemoryIntegration
from app.core.memory.agent_memory_injector import AgentMemoryInjector
from app.core.memory.agent_memory_filter import AgentMemoryFilter
from app.core.stream_writer_helper import push_thinking, push_error,push_progress
logger = logging.getLogger(__name__)


from app.agents.registry import AgentProtocol

class LangGraphAgent(AgentProtocol):
    """基于LangGraph的智能体实现"""
    
    def __init__(
        self,
        name: str,
        role: str,
        llm: Any,
        capabilities: Optional[List[str]] = None,
        config: Optional[Dict[str, Any]] = None,
        memory_integration: Optional[EnhancedMemoryIntegration] = None,
        info_hub: Optional[Any] = None,
        interrupt_manager: Optional[Any] = None,
        message_router: Optional[Any] = None
    ):
        """
        初始化LangGraph智能体
        
        Args:
            name: 智能体名称
            role: 智能体角色 (data_processing, expert_analysis, visualization等)
            llm: 语言模型实例
            capabilities: 智能体能力列表
            config: 配置参数
        """
        self.name = name
        self.role = role
        self.llm = llm
        self.capabilities = capabilities or []
        self.config = config or {}
        
        # 增强功能模块
        self.memory_integration = memory_integration
        self.info_hub = info_hub
        self.interrupt_manager = interrupt_manager
        self.message_router = message_router
        
        # 记忆注入器
        self.memory_injector = None
        if self.memory_integration:
            try:
                from app.core.memory.agent_memory_injector import create_agent_memory_injector
                self.memory_injector = create_agent_memory_injector(self.memory_integration)
                logger.info(f"智能体 {self.name} 记忆注入器初始化完成")
            except Exception as e:
                logger.warning(f"智能体 {self.name} 记忆注入器初始化失败: {str(e)}")
        
        # 获取该智能体可用的任务
        self._available_tools = self._get_available_tools()
        
        # 初始化记忆系统组件
        self._init_memory_system()
        
        # 构建智能体的子图
        self.graph = self._build_graph()
        
        logger.info(f"初始化LangGraphAgent: {name}, 角色: {role}, 可用工具数: {len(self._available_tools)}")
    
    def __call__(self, state: IsotopeSystemState) -> IsotopeSystemState:
        """使智能体对象可调用，委托给run方法"""
        return self.run(state)
    
    def get_name(self) -> str:
        """获取智能体名称"""
        return self.name
    
    def get_description(self) -> str:
        """获取智能体描述"""
        return f"{self.name} - 角色: {self.role}"
    
    def _init_memory_system(self):
        """初始化记忆系统"""
        try:
            # 确保config不为None
            if self.config is None:
                self.config = {}
            
            # 初始化记忆集成
            self.memory_integration = EnhancedMemoryIntegration(self.config)
            
            # 初始化记忆注入器
            self.memory_injector = AgentMemoryInjector(self.memory_integration)
            
            # 初始化记忆筛选器
            self.memory_filter = AgentMemoryFilter()
            
            # 记忆配置
            self.memory_config = self.config.get('memory', {})
            self.use_memory = self.memory_config.get('enabled', True)
            
            if self.use_memory:
                logger.info(f"智能体 {self.name} 记忆系统初始化成功")
            else:
                logger.info(f"智能体 {self.name} 记忆系统已禁用")
                
        except Exception as e:
            logger.warning(f"智能体 {self.name} 记忆系统初始化失败: {e}")
            self.use_memory = False
            self.memory_integration = None
            self.memory_injector = None
            self.memory_filter = None
    
    def _get_available_tools(self) -> Dict[str, Callable]:
        """获取该智能体可用的工具（基于角色和能力）"""
        available_tools = {}
        
        # ============ MCP工具集成 ============
        # 优先使用MCP工具（如果已启用）
        if self._is_mcp_enabled():
            logger.info(f"智能体 {self.name} 启用MCP工具支持")
            
            # 获取混合工具列表（传统任务 + MCP工具）
            all_tools = self._get_mixed_tools()
            
            # 将工具转换为任务接口
            for tool in all_tools:
                # 创建工具包装函数
                def create_tool_wrapper(tool_instance):
                    def tool_task(**kwargs):
                        """MCP工具包装器"""
                        try:
                            # 使用统一的工具调用接口
                            return self._invoke_any_tool(tool_instance.name, prefer_mcp=True, **kwargs)
                        except Exception as e:
                            logger.error(f"MCP工具调用失败 {tool_instance.name}: {e}")
                            raise
                    
                    tool_task.__name__ = f"mcp_{tool_instance.name}"
                    tool_task.__doc__ = tool_instance.description
                    return tool_task
                
                # 检查工具是否适合当前智能体角色
                if self._tool_matches_role(tool):
                    wrapper_func = create_tool_wrapper(tool)
                    available_tools[f"mcp_{tool.name}"] = wrapper_func
                    logger.debug(f"智能体 {self.name} 添加MCP工具: {tool.name}")
        

        
        logger.info(f"智能体 {self.name} 总共可用工具数: {len(available_tools)} "
                   f"(MCP启用: {self._is_mcp_enabled()})")
        
        return available_tools
    
    def _capability_matches_role(self, capability_type: CapabilityType) -> bool:
        """检查能力类型是否匹配智能体角色"""
        role_capability_mapping = {
            "data_processing": [CapabilityType.DATA_PROCESSING, CapabilityType.TOOL],
            "expert_analysis": [CapabilityType.ANALYSIS, CapabilityType.TOOL],
            "visualization": [CapabilityType.VISUALIZATION, CapabilityType.TOOL],
            "supervisor": [CapabilityType.TOOL, CapabilityType.ANALYSIS, CapabilityType.DATA_PROCESSING],
            # 新增地球物理分析相关角色
            "geophysics_analysis": [CapabilityType.ANALYSIS, CapabilityType.DATA_PROCESSING, CapabilityType.VISUALIZATION, CapabilityType.TOOL],
            "reservoir_engineering": [CapabilityType.ANALYSIS, CapabilityType.DATA_PROCESSING, CapabilityType.TOOL],
            "economic_evaluation": [CapabilityType.ANALYSIS, CapabilityType.TOOL],
            "quality_assurance": [CapabilityType.DATA_PROCESSING, CapabilityType.TOOL],
            "general_analysis": [CapabilityType.ANALYSIS, CapabilityType.DATA_PROCESSING, CapabilityType.VISUALIZATION, CapabilityType.TOOL]
        }
        
        allowed_types = role_capability_mapping.get(self.role, [CapabilityType.TOOL])
        return capability_type in allowed_types
    
    def _tool_matches_role(self, tool) -> bool:
        """检查MCP工具是否匹配智能体角色"""
        # 获取工具的元数据
        tool_registry = get_tool_registry()
        tool_metadata = tool_registry.get_tool_metadata(tool.name)
        
        if not tool_metadata:
            # 如果没有元数据，默认允许所有角色使用
            return True
        
        tool_category = tool_metadata.get("category", "")
        
        # 角色与工具分类的匹配规则
        role_category_mapping = {
            "data_processing": ["file", "data", "isotope", "mcp"],
            "expert_analysis": ["analysis", "isotope", "knowledge", "mcp"],
            "visualization": ["visualization", "data", "file", "mcp"],
            "supervisor": ["file", "data", "analysis", "knowledge", "isotope", "mcp"],
            # 专业角色
            "geophysics_analysis": ["isotope", "data", "analysis", "visualization", "mcp"],
            "reservoir_engineering": ["data", "analysis", "isotope", "mcp"],
            "economic_evaluation": ["analysis", "data", "mcp"],
            "quality_assurance": ["data", "file", "analysis", "mcp"],
            "general_analysis": ["file", "data", "analysis", "knowledge", "isotope", "visualization", "mcp"],
            # 中文角色映射（新增）
            "录井资料处理专家": ["iso_logging", "gas_logging", "file", "data", "analysis", "mcp"],
            "地震数据处理专家": ["data", "analysis", "visualization", "mcp"],
            "系统助手与咨询专家": ["file", "knowledge", "data", "analysis", "mcp"]
        }
        
        allowed_categories = role_category_mapping.get(self.role, ["mcp"])
        
        # 检查工具分类是否匹配
        if tool_category in allowed_categories:
            return True
        
        # 检查工具名称是否包含角色相关关键词
        tool_name_lower = tool.name.lower()
        role_keywords = {
            "data_processing": ["data", "file", "read", "write", "process"],
            "expert_analysis": ["analysis", "analyze", "isotope", "interpret"],
            "visualization": ["plot", "chart", "visual", "graph", "image"],
            "geophysics_analysis": ["isotope", "carbon", "data", "analysis"],
            "reservoir_engineering": ["reservoir", "pressure", "flow", "simulation"],
            "economic_evaluation": ["economic", "cost", "npv", "irr", "evaluation"],
            "quality_assurance": ["validate", "check", "quality", "verify"],
            "general_analysis": ["analysis", "data", "file", "isotope"],
            # 中文角色关键词（新增）
            "录井资料处理专家": ["isotope", "logging", "gas", "carbon", "analysis", "plot", "enhanced"],
            "地震数据处理专家": ["seismic", "data", "analysis", "visualization", "processing"],
            "系统助手与咨询专家": ["file", "search", "knowledge", "rag", "preview", "query"]
        }
        
        keywords = role_keywords.get(self.role, [])
        for keyword in keywords:
            if keyword in tool_name_lower:
                return True
        
        # 默认情况下，如果是MCP工具且没有明确限制，允许使用
        return tool_category == "mcp"
    
    def _is_mcp_enabled(self) -> bool:
        """动态检查MCP是否启用，避免循环导入"""
        try:
            from app.tools.registry import is_mcp_enabled
            return is_mcp_enabled()
        except ImportError:
            return False
    
    def _get_mixed_tools(self):
        """动态获取混合工具，避免循环导入"""
        try:
            from app.tools.registry import get_mixed_tools
            return get_mixed_tools()
        except ImportError:
            return []
    
    def _invoke_any_tool(self, tool_name: str, prefer_mcp: bool = False, **kwargs):
        """动态调用任何工具，避免循环导入"""
        try:
            from app.tools.registry import invoke_any_tool
            return invoke_any_tool(tool_name, prefer_mcp=prefer_mcp, **kwargs)
        except ImportError:
            raise RuntimeError(f"无法导入 invoke_any_tool 函数: {tool_name}")
    
    def _fallback_task_identification(self, response_content: str) -> List[Dict[str, Any]]:
        """
        降级处理：当JSON解析失败时，基于关键词识别任务
        
        Args:
            response_content: LLM的原始响应内容
            
        Returns:
            识别出的任务列表
        """
        fallback_tasks = []
        
        # 基于关键词匹配任务
        keyword_task_mapping = {
            "分析": ["task_carbon_isotope_analysis", "task_isotope_data_analysis"],
            "可视化": ["task_create_visualization", "task_plot_data"],
            "搜索": ["task_search_files", "task_search_knowledge"],
            "处理": ["task_process_data", "task_clean_data"],
            "计算": ["task_calculate_statistics", "task_compute_metrics"],
            "读取": ["task_read_file", "task_load_data"],
            "报告": ["task_generate_report", "task_create_summary"]
        }
        
        response_lower = response_content.lower()
        
        for keyword, task_names in keyword_task_mapping.items():
            if keyword in response_lower:
                for task_name in task_names:
                    if task_name in self._available_tools:
                        fallback_tasks.append({
                            "task_name": task_name,
                            "parameters": {},
                            "source": "keyword_fallback"
                        })
                        break  # 每个关键词只匹配一个任务
        
        # 如果没有匹配到任何任务，返回一个默认的通用任务
        if not fallback_tasks and self._available_tools:
            first_task = list(self._available_tools.keys())[0]
            fallback_tasks.append({
                "task_name": first_task,
                "parameters": {},
                "source": "default_fallback"
            })
        
        return fallback_tasks
    
    def _extract_json_from_response(self, response_content: str) -> str:
        """从LLM响应中提取JSON内容"""
        import re
        
        # 尝试多种JSON提取模式
        patterns = [
            r'```json\s*(.*?)\s*```',  # ```json ... ```
            r'```\s*(.*?)\s*```',      # ``` ... ```
            r'`(.*?)`',                # `...`
            r'(\{.*\})',               # 直接的JSON对象
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, response_content, re.DOTALL | re.IGNORECASE)
            if matches:
                json_content = matches[0].strip()
                # 验证是否为有效JSON
                try:
                    import json
                    json.loads(json_content)
                    return json_content
                except json.JSONDecodeError:
                    continue
        
        # 如果没有找到JSON模式，返回原始内容
        return response_content.strip()
    
    def _build_graph(self) -> StateGraph:
        """构建智能体的LangGraph子图"""
        # 创建状态图
        workflow = StateGraph(IsotopeSystemState)
        
        # 添加节点
        workflow.add_node(self.name + "_analyze", self._analyze_request)
        workflow.add_node(self.name + "_execute_task", self._execute_task)
        workflow.add_node(self.name + "_respond", self._generate_response)
        
        # 设置入口点
        workflow.set_entry_point(self.name + "_analyze")
        
        # 添加边
        workflow.add_edge(self.name + "_analyze", self.name + "_execute_task")
        workflow.add_edge(self.name + "_execute_task", self.name + "_respond")
        workflow.add_edge(self.name + "_respond", END)
        
        # 编译图
        return workflow.compile()
    
    def _analyze_request(self, state: IsotopeSystemState) -> IsotopeSystemState:
        """分析请求并决定执行哪些任务"""
        # *** 修复：安全获取流式写入器，避免上下文错误 ***

        push_thinking(agent_name=self.name, content=f"🔍 {self.name} 正在分析您的请求...", thinking_type="analysis")
        # 获取最新的用户消息
        last_human_msg = StateManager.get_last_human_message(state)
        if not last_human_msg:
            return state
        
        # 使用记忆系统增强分析
        enhanced_prompt = self._enhance_prompt_with_memories(last_human_msg.content, state)
        
        # 获取可用文件信息，用于任务参数（支持字典和列表格式）
        available_files = state.get("files", [])
        file_list = []
        
        if isinstance(available_files, dict):
            # 如果是字典格式，转换为列表
            for file_id, file_info in available_files.items():
                file_name = file_info.get("name", file_id)
                file_type = file_info.get("type", "未知")
                file_size = file_info.get("size", 0)
                file_list.append(f"  - {file_name} (ID: {file_id}, 类型: {file_type}, 大小: {file_size})")
        elif isinstance(available_files, list):
            # 如果是列表格式，直接使用
            for file_info in available_files:
                file_id = file_info.get("file_id", "未知")
                file_name = file_info.get("name", file_id)
                file_type = file_info.get("type", "未知")
                file_size = file_info.get("size", 0)
                file_list.append(f"  - {file_name} (ID: {file_id}, 类型: {file_type}, 大小: {file_size})")
        
        # 构建工具描述
        available_tools_desc = []
        for tool_name, tool_func in self._available_tools.items():
            # 获取工具的文档字符串或描述
            tool_desc = getattr(tool_func, "__doc__", "").strip() if hasattr(tool_func, "__doc__") else ""
            if not tool_desc:
                tool_desc = f"执行{tool_name}工具"
            available_tools_desc.append(f"  - {tool_name}: {tool_desc}")
        
        # 构建基础提示词
        base_prompt = f"""你是{self.name}，角色是{self.role}。

用户请求: {last_human_msg.content}

可用文件:
{chr(10).join(file_list) if file_list else "- 暂无可用文件"}

你可以使用以下任务:
{chr(10).join(available_tools_desc)}

请分析用户请求，决定需要执行哪些任务。如果任务需要文件ID参数，请使用上面列出的实际文件ID。

**重要：必须严格按照以下JSON格式输出，不要添加任何其他文本：**

```json
{{
    "tasks_to_execute": [
        {{"task_name": "任务名称", "parameters": {{"file_id": "实际的文件ID"}}}},
        {{"task_name": "另一个任务名称", "parameters": {{}}}}
    ],
    "reasoning": "你的分析和推理过程"
}}
```

注意：
1. 只输出JSON，不要有其他解释文字
2. task_name必须从上面的可用任务列表中选择
3. 如果需要file_id参数，请使用实际的文件ID，不要使用占位符
4. 如果不需要执行任何任务，tasks_to_execute设为空数组[]"""
        
        # 使用记忆增强的提示词
        final_prompt = enhanced_prompt if enhanced_prompt else base_prompt
        
        # 调用LLM
        response = self.llm.invoke([HumanMessage(content=final_prompt)])
        
        # 解析JSON响应
        try:
            # 提取JSON内容
            json_content = self._extract_json_from_response(response.content)
            
            # 解析JSON
            analysis = json.loads(json_content)
            
            # 验证JSON结构
            if not isinstance(analysis, dict) or "tasks_to_execute" not in analysis:
                raise ValueError("JSON格式不正确")
                
            # 保存分析结果
            state["agent_analysis"] = {
                "agent": self.name,
                "tasks": analysis.get("tasks_to_execute", []),
                "reasoning": analysis.get("reasoning", ""),
                "analysis_success": True
            }
            
            # 通知用户任务分析结果
            task_count = len(analysis.get("tasks_to_execute", []))
            
            if task_count > 0:
                task_names = [task.get("task_name", "") for task in analysis.get("tasks_to_execute", [])]
                push_thinking(agent_name=self.name, content=f"📋 分析完成！识别出 {task_count} 个相关任务：{', '.join(task_names[:3])}{'...' if len(task_names) > 3 else ''}", thinking_type="analysis")
                
                # 记录详细的调试信息
                logger.info(f"✅ {self.name} 任务分析成功：识别到 {task_count} 个任务")
                for i, task in enumerate(analysis.get("tasks_to_execute", [])):
                    logger.info(f"  任务 {i+1}: {task.get('task_name')} - 参数: {task.get('parameters', {})}")
            else:
                push_thinking(agent_name=self.name, content=f"💭 理解了您的需求，正在准备相应的回复", thinking_type="analysis")
                logger.info(f"ℹ️ {self.name} 任务分析：无需执行特定任务")
            
            # 保存记忆（如果启用）
            if self.use_memory and self.memory_integration:
                self._save_analysis_to_memory(state, analysis)
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            logger.error(f"响应内容: {response.content}")
            
            # 降级处理：基于关键词识别任务
            fallback_tasks = self._fallback_task_identification(response.content)
            
            state["agent_analysis"] = {
                "agent": self.name,
                "tasks": fallback_tasks,
                "reasoning": f"使用智能分析识别任务",
                "fallback": True,
                "error": str(e),
                "analysis_success": False
            }
            
            push_thinking(agent_name=self.name, content=f"🔄 JSON解析失败，使用智能分析识别到 {len(fallback_tasks)} 个相关任务", thinking_type="analysis")
            
        except Exception as e:
            logger.error(f"分析请求失败: {e}")
            state["agent_analysis"] = {
                "agent": self.name,
                "tasks": [],
                "error": str(e),
                "analysis_success": False
            }
            
            push_thinking(agent_name=self.name, content=f"⚠️ 分析过程遇到问题，将提供通用回复", thinking_type="analysis")
        
        return state
    
    def _execute_task(self, state: IsotopeSystemState) -> IsotopeSystemState:
        """执行识别出的任务"""
        # *** 修复：安全获取流式写入器 ***

        
        # *** 关键修复：直接从原始状态读取任务信息 ***
        analysis = state.get("agent_analysis", {})
        tasks = analysis.get("tasks", [])
        
        # 添加详细的调试日志
        logger.info(f"[DEBUG] _execute_task - 智能体: {self.name}")
        logger.info(f"[DEBUG] state keys: {list(state.keys())}")
        logger.info(f"[DEBUG] agent_analysis: {analysis}")
        logger.info(f"[DEBUG] tasks count: {len(tasks)}")
        logger.info(f"[DEBUG] available_tools count: {len(self._available_tools)}")
        logger.info(f"[DEBUG] available_tools: {list(self._available_tools.keys())}")
        
        # *** 修复：检查分析是否成功 ***
        if analysis.get("analysis_success", False):
            logger.info(f"✅ {self.name} 成功获取任务分析结果")
        else:
            logger.warning(f"⚠️ {self.name} 任务分析可能失败或不完整")
        
        if not tasks:
            # *** 修复：检查是否有任务但因为状态传递问题丢失了 ***
            if analysis:
                logger.warning(f"⚠️ 有分析结果但无任务：{analysis}")
                push_thinking(agent_name=self.name, content=f"💭 分析完成但无需执行特定任务，将直接生成回复", thinking_type="analysis")
            else:
                logger.warning(f"⚠️ 未找到任务分析结果，可能是状态传递问题")
            push_thinking(agent_name=self.name, content=f"💭 无需执行特定任务，将直接生成回复", thinking_type="analysis")
            push_thinking(agent_name=self.name, content=f"[调试] 原因：无分析结果或任务列表为空", thinking_type="analysis")
            return state
        
        # 初始化任务执行结果
        if "task_results" not in state or state["task_results"] is None:
            state["task_results"] = []
        
        push_thinking(agent_name=self.name, content=f"🔄 开始执行 {len(tasks)} 个任务...", thinking_type="analysis")
        
        # 执行每个任务
        success_count = 0
        for i, task_info in enumerate(tasks, 1):
            task_name = task_info.get("task_name")
            parameters = task_info.get("parameters", {})
            
            if task_name not in self._available_tools:
                logger.warning(f"任务 {task_name} 不可用")
                push_thinking(agent_name=self.name, content=f"⚠️ 任务 {task_name} 不在可用任务列表中，跳过", thinking_type="analysis")
                continue
            
            push_thinking(agent_name=self.name, content=f"🚀 正在执行任务 {i}/{len(tasks)}: {task_name}", thinking_type="analysis")
            
            # *** 关键修复：记录任务执行开始时间 ***
            start_time = time.time()
            
            try:
                # 获取任务函数
                task_func = self._available_tools[task_name]
                
                logger.info(f"⏱️ 开始执行任务 {task_name}，参数: {parameters}")
                
                # *** 关键修复：在LangGraph上下文中执行任务，确保流式输出传递 ***
                # 如果task函数有_task_config属性，说明它是被@task装饰的
                if hasattr(task_func, '_task_config'):
                    # 尝试应用LangGraph装饰器来确保流式输出正确传递
                    from app.core.task_decorator import apply_langgraph_decorator
                    try:
                        # 在当前LangGraph上下文中应用装饰器
                        enhanced_task_func = apply_langgraph_decorator(task_func)
                        result = enhanced_task_func(**parameters)
                    except Exception as decorator_error:
                        logger.warning(f"LangGraph装饰器应用失败，使用原始函数: {decorator_error}")
                        # 直接执行原始任务函数
                        result = task_func(**parameters)
                else:
                    # 直接执行任务函数
                    result = task_func(**parameters)
                
                # *** 关键修复：记录任务执行时间 ***
                execution_time = time.time() - start_time
                logger.info(f"✅ 任务 {task_name} 执行成功，耗时: {execution_time:.2f}秒")
                
                # *** 关键修复：详细记录执行结果，确保可序列化 ***
                # 确保result是可序列化的，避免Future等不可序列化对象
                serializable_result = result
                if hasattr(result, '__dict__'):
                    try:
                        # 尝试转换为字符串形式，避免复杂对象
                        serializable_result = str(result)
                    except Exception:
                        serializable_result = f"<{type(result).__name__} object>"
                
                execution_record = {
                    "task_name": task_name,
                    "parameters": parameters,
                    "result": serializable_result,  # 保存可序列化的结果内容
                    "execution_time": execution_time,
                    "status": "success",
                    "timestamp": datetime.now().isoformat()
                }
                
                state["task_results"].append(execution_record)
                success_count += 1
                
                push_thinking(agent_name=self.name, content=f"✅ 任务 {task_name} 执行成功", thinking_type="analysis")
                # *** 关键修复：提供更详细的工具输出信息 ***
                push_progress({
                        "tool_name": task_name,
                        "progress": 100,
                        "details": str(result)[:500] + "..." if len(str(result)) > 500 else str(result),
                        "source": "task"
                    })
                
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(f"执行任务 {task_name} 失败: {e}")
                logger.error(f"任务执行异常详情: {traceback.format_exc()}")
                
                execution_record = {
                    "task_name": task_name,
                    "parameters": parameters,
                    "error": str(e),
                    "execution_time": execution_time,
                    "status": "failed",
                    "timestamp": datetime.now().isoformat()
                }
                
                state["task_results"].append(execution_record)
                
                push_thinking(agent_name=self.name, content=f"❌ 任务 {task_name} 执行失败: {str(e)[:100]}...", thinking_type="analysis")
                push_progress({
                        "tool_name": task_name,
                        "progress": 0,
                        "details": str(e)[:500] + "..." if len(str(e)) > 500 else str(e),
                        "source": "task"
                    })
        
        # 总结执行结果
        if success_count == len(tasks):
            push_thinking(agent_name=self.name, content=f"🎉 所有任务执行完成！成功完成 {success_count} 个任务", thinking_type="analysis")
        elif success_count > 0:
            push_thinking(agent_name=self.name, content=f"⚡ 任务执行完成！成功 {success_count} 个，失败 {len(tasks) - success_count} 个", thinking_type="analysis")
        else:
            push_thinking(agent_name=self.name, content=f"⚠️ 任务执行遇到问题，所有任务都未能成功完成", thinking_type="analysis")
        
        # *** 关键修复：记录最终的任务执行统计 ***
        logger.info(f"📊 任务执行统计 - 总数: {len(tasks)}, 成功: {success_count}, 失败: {len(tasks) - success_count}")
        
        return state
    
    def _generate_response(self, state: IsotopeSystemState) -> IsotopeSystemState:
        """基于任务执行结果生成响应"""
        # *** 修复：安全获取流式写入器 ***
        push_thinking(agent_name=self.name, content=f"📝 {self.name} 正在整理分析结果并生成回复...", thinking_type="analysis")
        
        # 获取任务执行结果
        task_results = state.get("task_results", [])
        analysis = state.get("agent_analysis", {})
        
        # 获取用户原始请求
        last_human_msg = StateManager.get_last_human_message(state)
        user_request = last_human_msg.content if last_human_msg else "用户请求"
        
        # 准备结果摘要
        success_tasks = [r for r in task_results if r["status"] == "success"]
        failed_tasks = [r for r in task_results if r["status"] == "failed"]
        
        results_summary = []
        detailed_results = []  # *** 新增：存储详细的任务结果 ***
        
        if success_tasks:
            results_summary.append("✅ 成功完成的任务:")
            for result in success_tasks:
                execution_time = result.get('execution_time', 0)
                results_summary.append(f"  • {result['task_name']} (耗时: {execution_time:.2f}秒)")
                
                # *** 关键修复：提取task的具体结果内容 ***
                task_result_content = result.get('result', '')
                if task_result_content and isinstance(task_result_content, str):
                    # 限制每个任务结果的长度，避免提示词过长
                    max_result_length = 2000
                    if len(task_result_content) > max_result_length:
                        task_result_summary = task_result_content[:max_result_length] + "...(结果已截断)"
                    else:
                        task_result_summary = task_result_content
                    
                    detailed_results.append(f"""
**任务 {result['task_name']} 的执行结果:**
参数: {result.get('parameters', {})}
执行时间: {execution_time:.2f}秒
结果内容:
{task_result_summary}
""")
        
        if failed_tasks:
            results_summary.append("❌ 执行失败的任务:")
            for result in failed_tasks:
                error_msg = result.get('error', '未知错误')[:50]
                execution_time = result.get('execution_time', 0)
                results_summary.append(f"  • {result['task_name']} - {error_msg}... (耗时: {execution_time:.2f}秒)")
        
        # *** 关键修复：基于具体的任务结果内容生成回复 ***
        if not task_results:
            prompt = f"""用户请求: {user_request}

作为{self.name}（{self.role}），请直接回答用户的问题。

请用专业、友好的语言回复，确保：
1. 直接解答用户的疑问
2. 如果是专业问题，提供准确的技术信息  
3. 如果是咨询类问题，给出清晰的指导
4. 语气自然，避免过于机械化
"""
        else:
            # *** 关键修复：基于详细的任务执行结果生成响应 ***
            detailed_results_text = "\n".join(detailed_results)
            
            prompt = f"""用户请求: {user_request}

任务执行概要:
{chr(10).join(results_summary)}

详细任务执行结果:
{detailed_results_text}

作为专业的{self.role}，请基于以上任务的具体执行结果，生成一个全面、专业的回复。要求：

1. **准确理解用户需求**：首先确认理解了用户的具体请求
2. **基于实际结果回复**：重点基于任务的具体执行结果和分析内容进行回复，不要编造信息
3. **突出关键发现**：如果任务产生了具体的分析结论、数据洞察或图表，请重点说明
4. **专业术语适度**：使用专业但易懂的语言，避免过于技术化的表述
5. **实用建议**：如果合适，提供下一步的操作建议或分析方向
6. **文件和图表说明**：如果任务生成了图表或文件，明确告知用户如何查看和利用这些结果

注意事项：
- 不要直接复制粘贴原始任务执行数据
- 要用自然语言总结和解释关键信息
- 如果有多个任务结果，要综合分析并给出整体结论
- 保持回复的逻辑性和专业性
- 如果某些任务失败，要诚实说明但不要过分强调技术细节
"""
        
        response = self.llm.invoke([HumanMessage(content=prompt)])
        
        # 提供更友好的完成提示
        if len(success_tasks) == len(task_results) and task_results:
            push_thinking(agent_name=self.name, content=f"🎯 分析完成！为您生成了基于实际结果的全面分析报告", thinking_type="analysis")
        elif success_tasks and failed_tasks:
            push_thinking(agent_name=self.name, content=f"📊 分析基本完成，已基于成功任务的结果生成报告", thinking_type="analysis")
        elif not task_results:
            push_thinking(agent_name=self.name, content=f"💬 为您准备了详细的回复", thinking_type="analysis")
        else:
            push_thinking(agent_name=self.name, content=f"⚡ 已为您生成回复，如需更详细分析请上传相关文件", thinking_type="analysis")
        
        # *** 关键修复：在AI消息中包含更多的执行统计信息 ***
        total_execution_time = sum(r.get('execution_time', 0) for r in task_results)
        
        ai_message = AIMessage(
            content=response.content,
            additional_kwargs={
                "source": self.name,
                "role": self.role,
                "tasks_executed": len(task_results),
                "success_count": len(success_tasks),
                "failed_count": len(failed_tasks),
                "total_execution_time": f"{total_execution_time:.2f}秒",
                "has_detailed_results": len(detailed_results) > 0,
                "task_names": [r['task_name'] for r in success_tasks]
            }
        )
        
        # 更新消息历史
        state = StateManager.update_messages(state, ai_message)
        
        return state
    
    def run(self, state: IsotopeSystemState) -> IsotopeSystemState:
        """运行智能体"""
        logger.info(f"LangGraphAgent {self.name} 开始运行")
        
        # *** 关键修复：确保输入状态完整 ***
        if not isinstance(state, dict):
            logger.error(f"⚠️ {self.name} 接收到的状态不是字典格式: {type(state)}")
            state = {}
        
        # 记忆增强预处理
        if self.memory_integration:
            try:
                # 提取和存储记忆
                extracted_memories = self.memory_integration.extract_memories_from_state(
                    state, self.role
                )
                if extracted_memories:
                    logger.info(f"智能体 {self.name} 提取到 {len(extracted_memories)} 条记忆")
                
                # 增强状态
                memory_context = self.memory_integration.enhance_state_with_agent_memories(
                    state, self.role
                )
                
                # 将记忆上下文注入到状态中
                if hasattr(memory_context, 'memory_summary') and memory_context.memory_summary:
                    if 'metadata' not in state:
                        state['metadata'] = {}
                    state['metadata']['agent_memory_context'] = {
                        'summary': memory_context.memory_summary,
                        'confidence': memory_context.confidence_score,
                        'domain_coverage': memory_context.domain_coverage
                    }
                    logger.info(f"智能体 {self.name} 记忆增强完成")
                    
            except Exception as e:
                logger.warning(f"智能体 {self.name} 记忆增强失败: {str(e)}")
        
        # 信息中枢日志记录
        if self.info_hub:
            try:
                session_id = state.get('metadata', {}).get('session_id', 'default')
                self.info_hub.log_event(session_id, {
                    'event_type': 'agent_execution_start',
                    'agent_name': self.name,
                    'agent_role': self.role,
                    'timestamp': datetime.now().isoformat()
                })
            except Exception as e:
                logger.warning(f"信息中枢日志记录失败: {str(e)}")
        
        # 确保状态包含必要字段（修复None值问题）
        if "agent_analysis" not in state or state["agent_analysis"] is None:
            state["agent_analysis"] = {}
        if "task_results" not in state or state["task_results"] is None:
            state["task_results"] = []
        
        try:
            # *** 修复：记录运行前的状态 ***
            logger.info(f"📊 {self.name} 运行前状态检查:")
            logger.info(f"  - messages: {len(state.get('messages', []))}")
            logger.info(f"  - files: {len(state.get('files', {}))}")
            logger.info(f"  - agent_analysis存在: {'agent_analysis' in state}")
            if 'agent_analysis' in state:
                analysis = state['agent_analysis']
                logger.info(f"  - analysis内容: {analysis}")
                # *** 关键修复：处理analysis为None的情况 ***
                if analysis is not None and isinstance(analysis, dict):
                    logger.info(f"  - tasks数量: {len(analysis.get('tasks', []))}")
                else:
                    logger.info(f"  - tasks数量: 0 (analysis为None或非字典格式)")
            
            # 运行编译后的图
            result = self.graph.invoke(state)
            
            # *** 修复：记录运行后的状态 ***
            logger.info(f"📊 {self.name} 运行后状态检查:")
            logger.info(f"  - messages: {len(result.get('messages', []))}")
            logger.info(f"  - agent_analysis存在: {'agent_analysis' in result}")
            if 'agent_analysis' in result:
                analysis = result['agent_analysis']
                logger.info(f"  - analysis内容: {analysis}")
                # *** 关键修复：处理analysis为None的情况 ***
                if analysis is not None and isinstance(analysis, dict):
                    logger.info(f"  - 分析成功: {analysis.get('analysis_success', False)}")
                    logger.info(f"  - 识别的任务数: {len(analysis.get('tasks', []))}")
                else:
                    logger.info(f"  - analysis为None或非字典格式，可能存在状态传递问题")
            
            return result
        except Exception as e:
            logger.error(f"LangGraphAgent {self.name} 运行失败: {e}")
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            # 添加错误消息
            error_msg = AIMessage(
                content=f"抱歉，{self.name}在处理请求时遇到错误: {str(e)}",
                additional_kwargs={"error": True, "source": self.name}
            )
            return StateManager.update_messages(state, error_msg)
    
    def _enhance_prompt_with_memories(self, user_query: str, state: IsotopeSystemState) -> Optional[str]:
        """使用记忆系统增强提示词"""
        if not self.use_memory or not self.memory_injector:
            return None
            
        try:
            # 提取当前用户ID和会话ID
            user_id = state.get('metadata', {}).get('user_id', 'default_user')
            session_id = state.get('metadata', {}).get('session_id', 'default_session')
            
            # 获取记忆上下文
            memory_context = self.memory_integration.enhance_state_with_agent_memories(
                state, 
                agent_role=self.role,
                query=user_query
            )
            
            # 如果没有相关记忆，返回None
            if memory_context.confidence_score < 0.3:
                return None
            
            # 构建记忆增强的提示词
            memory_section = self._format_memory_context(memory_context)
            
            # 获取基础提示词组件
            base_prompt = self._build_base_prompt(user_query, state)
            
            # 注入记忆到提示词中
            enhanced_prompt = f"""基于以下相关记忆信息和当前请求，进行分析：

{memory_section}

---

{base_prompt}

请结合上述记忆信息，进行更准确的任务分析。"""
            
            logger.info(f"智能体 {self.name} 使用记忆增强提示词 (置信度: {memory_context.confidence_score:.2f})")
            return enhanced_prompt
            
        except Exception as e:
            logger.warning(f"记忆增强提示词失败: {e}")
            return None
    
    def _format_memory_context(self, memory_context) -> str:
        """格式化记忆上下文为可读文本"""
        sections = []
        
        if memory_context.semantic_memories:
            semantic_items = []
            for memory in memory_context.semantic_memories[:3]:  # 取最相关的3个
                semantic_items.append(f"- {memory.content[:100]}...")
            sections.append(f"相关语义记忆:\n" + "\n".join(semantic_items))
        
        if memory_context.episodic_memories:
            episodic_items = []
            for memory in memory_context.episodic_memories[:2]:  # 取最相关的2个
                episodic_items.append(f"- {memory.content[:100]}...")
            sections.append(f"相关情节记忆:\n" + "\n".join(episodic_items))
        
        if memory_context.procedural_memories:
            procedural_items = []
            for memory in memory_context.procedural_memories[:2]:  # 取最相关的2个
                procedural_items.append(f"- {memory.content[:100]}...")
            sections.append(f"相关程序记忆:\n" + "\n".join(procedural_items))
        
        if memory_context.memory_summary:
            sections.append(f"记忆摘要: {memory_context.memory_summary}")
        
        return "\n\n".join(sections)
    
    def _build_base_prompt(self, user_query: str, state: IsotopeSystemState) -> str:
        """构建基础提示词"""
        # 获取文件信息
        available_files = state.get("files", [])
        file_list = []
        
        if isinstance(available_files, dict):
            for file_id, file_info in available_files.items():
                file_name = file_info.get("name", file_id)
                file_type = file_info.get("type", "未知")
                file_size = file_info.get("size", 0)
                file_list.append(f"  - {file_name} (ID: {file_id}, 类型: {file_type}, 大小: {file_size})")
        elif isinstance(available_files, list):
            for file_info in available_files:
                file_id = file_info.get("file_id", "未知")
                file_name = file_info.get("name", file_id)
                file_type = file_info.get("type", "未知")
                file_size = file_info.get("size", 0)
                file_list.append(f"  - {file_name} (ID: {file_id}, 类型: {file_type}, 大小: {file_size})")
        
        # 构建任务描述
        available_tools_desc = []
        for tool_name, tool_func in self._available_tasks.items():
            tool_desc = getattr(tool_func, "__doc__", "").strip() if hasattr(tool_func, "__doc__") else ""
            if not tool_desc:
                tool_desc = f"执行{tool_name}工具"
            available_tools_desc.append(f"  - {tool_name}: {tool_desc}")
        
        return f"""你是{self.name}，角色是{self.role}。

用户请求: {user_query}

可用文件:
{chr(10).join(file_list) if file_list else "- 暂无可用文件"}

你可以使用以下任务:
{chr(10).join(available_tools_desc)}

请分析用户请求，决定需要执行哪些任务。如果任务需要文件ID参数，请使用上面列出的实际文件ID。

**重要：必须严格按照以下JSON格式输出，不要添加任何其他文本：**

```json
{{
    "tasks_to_execute": [
        {{"task_name": "任务名称", "parameters": {{"file_id": "实际的文件ID"}}}},
        {{"task_name": "另一个任务名称", "parameters": {{}}}}
    ],
    "reasoning": "你的分析和推理过程"
}}
```

注意：
1. 只输出JSON，不要有其他解释文字
2. task_name必须从上面的可用任务列表中选择
3. 如果需要file_id参数，请使用实际的文件ID，不要使用占位符
4. 如果不需要执行任何任务，tasks_to_execute设为空数组[]"""
    
    def _save_analysis_to_memory(self, state: IsotopeSystemState, analysis: Dict[str, Any]):
        """保存分析结果到记忆系统"""
        try:
            # 获取用户信息
            user_id = state.get('metadata', {}).get('user_id', 'default_user')
            session_id = state.get('metadata', {}).get('session_id', 'default_session')
            
            # 构建记忆内容
            memory_content = f"智能体 {self.name} 分析结果:\n"
            memory_content += f"推理过程: {analysis.get('reasoning', '')}\n"
            memory_content += f"识别任务: {[task.get('task_name') for task in analysis.get('tasks_to_execute', [])]}"
            
            # 保存到记忆系统
            self.memory_integration.save_agent_interaction_memory(
                state=state,
                agent_role=self.role,
                interaction_summary=memory_content,
                session_id=session_id
            )
            
            logger.debug(f"智能体 {self.name} 分析结果已保存到记忆系统")
            
        except Exception as e:
            logger.warning(f"保存分析结果到记忆系统失败: {e}")


def create_langgraph_agent(
    name: str,
    role: str,
    llm: Any,
    capabilities: Optional[List[str]] = None,
    config: Optional[Dict[str, Any]] = None
) -> LangGraphAgent:
    """
    工厂函数：创建LangGraph智能体
    
    Args:
        name: 智能体名称
        role: 智能体角色
        llm: 语言模型实例
        capabilities: 能力列表
        config: 配置参数
        
    Returns:
        LangGraphAgent实例
    """
    return LangGraphAgent(
        name=name,
        role=role,
        llm=llm,
        capabilities=capabilities,
        config=config
    ) 