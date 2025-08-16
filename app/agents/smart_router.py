"""
智能路由器智能体 - 基于LLM和MCP工具能力画像进行智能体路由
"""

import logging
import time
from typing import Dict, List, Any, Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from app.core.state import IsotopeSystemState, StateManager
from app.agents.registry import AgentProtocol, agent_registry

logger = logging.getLogger(__name__)

class SmartRouter(AgentProtocol):
    """智能路由器 - 基于LLM决策和MCP工具能力画像选择最佳智能体路径"""
    
    def __init__(self, llm: BaseChatModel, config: Optional[Dict[str, Any]] = None, memory_integration: Optional[Any] = None, info_hub: Optional[Any] = None, message_router: Optional[Any] = None):
        self.llm = llm
        self.config = config or {}
        self.name = "smart_router"
        self.description = "智能路由器，基于任务分析和工具能力画像选择最佳的执行路径"
        
        # 增强功能模块
        self.memory_integration = memory_integration
        self.info_hub = info_hub
        self.message_router = message_router
        
        # 路由历史和统计
        self.routing_history = []
        self.agent_performance_stats = {}
        
        # MCP工具能力缓存
        self._tool_capabilities_cache = {}
        self._cache_refresh_interval = self.config.get("cache_refresh_interval", 3600)  # 1小时
        self._last_cache_refresh = 0
    
    def run(self, state: IsotopeSystemState) -> IsotopeSystemState:
        """执行智能路由决策"""
        logger.info("SmartRouter开始智能路由分析")
        
        try:
            # 直接分析用户意图并做路由决策（集成MetaSupervisor功能）
            user_intent_analysis = self._analyze_user_intent(state)
            
            # 刷新MCP工具能力画像
            self._refresh_tool_capabilities()
            
            # 执行智能路由决策
            routing_decision = self._make_routing_decision(user_intent_analysis, state)
            
            # 更新状态
            state["metadata"]["routing_decision"] = routing_decision
            state["metadata"]["routed_by"] = self.name
            state["metadata"]["routing_timestamp"] = time.time()
            
            # 明确设置策略为ReAct模式（新架构默认）
            state["metadata"]["execution_strategy"] = "reactive"
            state["metadata"]["recommended_agent"] = routing_decision.get("primary_route", "")
            
            # 记录路由历史
            self._record_routing_decision(routing_decision, user_intent_analysis)
            
            logger.info(f"SmartRouter路由决策完成: {routing_decision.get('primary_route', 'unknown')}")
            return state
            
        except Exception as e:
            logger.error(f"SmartRouter执行失败: {str(e)}")
            # 使用fallback路由
            fallback_routing = self._fallback_routing(state)
            state["metadata"]["routing_decision"] = fallback_routing
            state["metadata"]["routing_error"] = str(e)
            return state
    
    def get_name(self) -> str:
        return self.name
    
    def get_description(self) -> str:
        return self.description
    
    def _analyze_user_intent(self, state: IsotopeSystemState) -> Dict[str, Any]:
        """分析用户意图（集成MetaSupervisor功能）"""
        try:
            # 获取用户消息
            last_human_msg = StateManager.get_last_human_message(state)
            user_input = last_human_msg.content if last_human_msg else ""
            
            if not user_input.strip():
                return {
                    "task_type": "consultation",
                    "complexity": "simple",
                    "confidence": 0.5,
                    "suggested_agents": ["logging"],
                    "required_capabilities": [],
                    "reasoning": "空消息，使用默认设置"
                }
            
            # 使用LLM分析用户意图
            intent_prompt = f"""
            你是油气勘探专业智能体系统的意图分析器。请分析用户请求并返回JSON格式的分析结果。
            
            用户请求: {user_input}
            
            可用的专业智能体:
            - logging: 录井资料处理与解释专家
            - seismic: 地震数据处理与解释专家
            - assistant: 系统助手，负责咨询问答和知识检索
            
            请分析并返回:
            {{
                "task_type": "任务类型（seismic_processing/logging_analysis/consultation等）",
                "complexity": "复杂度（simple/medium/complex）",
                "confidence": 0.0-1.0,
                "suggested_agents": ["推荐的智能体列表"],
                "required_capabilities": ["需要的工具能力"],
                "reasoning": "分析推理过程"
            }}
            """
            
            llm_response = self.llm.invoke(intent_prompt)
            content = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
            
            # 解析LLM响应
            import json
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                intent_analysis = json.loads(json_match.group())
                logger.info(f"用户意图分析完成: {intent_analysis.get('task_type', 'unknown')}")
                return intent_analysis
            else:
                raise ValueError("无法解析LLM响应")
                
        except Exception as e:
            logger.warning(f"用户意图分析失败: {str(e)}，使用关键词匹配")
            return self._fallback_intent_analysis(user_input)
    
    def _fallback_intent_analysis(self, user_input: str) -> Dict[str, Any]:
        """基于关键词的fallback意图分析"""
        user_lower = user_input.lower()
        
        # 关键词匹配
        if any(keyword in user_lower for keyword in ['录井', '测井', 'logging', 'well']):
            return {
                "task_type": "logging_analysis",
                "complexity": "medium", 
                "confidence": 0.7,
                "suggested_agents": ["logging"],
                "required_capabilities": ["data_processing", "interpretation"],
                "reasoning": "基于关键词匹配识别为录井任务"
            }
        elif any(keyword in user_lower for keyword in ['地震', 'seismic', '地球物理']):
            return {
                "task_type": "seismic_processing",
                "complexity": "medium",
                "confidence": 0.7, 
                "suggested_agents": ["seismic"],
                "required_capabilities": ["signal_processing", "interpretation"],
                "reasoning": "基于关键词匹配识别为地震任务"
            }
        elif any(keyword in user_lower for keyword in ['咨询', '介绍', '帮助', '功能', '怎么用', '问题']):
            return {
                "task_type": "consultation",
                "complexity": "simple",
                "confidence": 0.8,
                "suggested_agents": ["assistant"],
                "required_capabilities": ["knowledge_search", "consultation"],
                "reasoning": "基于关键词匹配识别为咨询任务"
            }
        else:
            return {
                "task_type": "consultation",
                "complexity": "simple",
                "confidence": 0.5,
                "suggested_agents": ["assistant"],
                "required_capabilities": [],
                "reasoning": "未匹配到特定关键词，推荐助手处理"
            }
    
    def _make_routing_decision(
        self,
        user_intent_analysis: Dict[str, Any],
        state: IsotopeSystemState
    ) -> Dict[str, Any]:
        """基于LLM和工具能力画像做路由决策"""
        
        # 获取可用智能体信息
        available_agents = self._get_available_agents()
        
        # 获取MCP工具能力画像
        tool_capabilities = self._get_tool_capabilities_summary()
        
        # 构建LLM路由决策提示
        routing_prompt = self._build_routing_prompt(
            user_intent_analysis, available_agents, tool_capabilities, state
        )
        
        try:
            # LLM路由决策
            llm_response = self.llm.invoke(routing_prompt)
            content = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
            
            # 解析LLM响应
            routing_decision = self._parse_routing_response(content, available_agents)
            
            # 验证路由决策
            validated_decision = self._validate_routing_decision(routing_decision, available_agents)
            
            # 添加置信度和备选方案
            enhanced_decision = self._enhance_routing_decision(validated_decision, user_intent_analysis, available_agents)
            
            return enhanced_decision
            
        except Exception as e:
            logger.error(f"LLM路由决策失败: {str(e)}")
            return self._fallback_routing_decision(user_intent_analysis, available_agents)
    
    def _build_routing_prompt(
        self,
        user_intent_analysis: Dict[str, Any],
        available_agents: Dict[str, Dict[str, Any]],
        tool_capabilities: Dict[str, Any],
        state: IsotopeSystemState
    ) -> str:
        """构建路由决策提示词"""
        
        # 获取用户消息
        last_human_msg = StateManager.get_last_human_message(state)
        user_input = last_human_msg.content if last_human_msg else "未知请求"
        
        # 构建智能体能力描述
        agents_info = []
        for agent_name, agent_info in available_agents.items():
            agents_info.append(
                f"- {agent_name}: {agent_info.get('description', '无描述')} "
                f"(性能评分: {agent_info.get('performance_score', 0.5):.2f})"
            )
        
        # 构建工具能力摘要
        tools_summary = []
        for category, tools in tool_capabilities.items():
            available_count = sum(1 for tool in tools if tool.get('available', False))
            tools_summary.append(f"- {category}: {available_count}/{len(tools)} 工具可用")
        
        prompt = f"""
        你是油气勘探多智能体系统的智能路由器。当前系统采用ReAct（Reasoning+Acting）模式，专业智能体根据用户需求动态选择和执行工具。

        ## 用户请求
        {user_input}

        ## 用户意图分析结果
        - 任务类型: {user_intent_analysis.get('task_type', 'unknown')}
        - 复杂度: {user_intent_analysis.get('complexity', 'unknown')}
        - 所需能力: {', '.join(user_intent_analysis.get('required_capabilities', []))}
        - 建议智能体: {', '.join(user_intent_analysis.get('suggested_agents', []))}
        - 置信度: {user_intent_analysis.get('confidence', 0.0):.2f}

        ## 可用专业智能体（ReAct模式）
        {chr(10).join(agents_info)}

        ## MCP工具能力概况
        {chr(10).join(tools_summary)}

        ## ReAct路由规则
        1. 根据任务内容选择最合适的专业智能体
        2. 智能体将自主决定需要使用哪些工具
        3. 支持部分任务执行（不需要完整工作流）
        4. 优先考虑智能体的专业能力匹配度
        5. 重要任务建议选择性能评分更高的智能体

        请分析并返回JSON格式的路由决策：
        {{
            "primary_route": "主要智能体名称（如logging或seismic）",
            "confidence": 0.0-1.0,
            "reasoning": "选择理由（说明为什么这个智能体最适合）",
            "alternative_routes": ["备选智能体1", "备选智能体2"],
            "execution_strategy": "reactive",
            "tool_requirements": ["智能体预期使用的工具类型"],
            "estimated_success_rate": 0.0-1.0
        }}
        """
        
        return prompt
    
    def _parse_routing_response(self, llm_response: str, available_agents: Dict[str, Any]) -> Dict[str, Any]:
        """解析LLM的路由响应"""
        import json
        import re
        
        try:
            # 提取JSON部分
            json_match = re.search(r'\{.*\}', llm_response, re.DOTALL)
            if json_match:
                routing_data = json.loads(json_match.group())
                return routing_data
            else:
                raise ValueError("无法在LLM响应中找到JSON格式的路由决策")
        
        except json.JSONDecodeError as e:
            logger.warning(f"解析LLM路由响应JSON失败: {str(e)}")
            # 尝试关键词提取
            return self._extract_routing_from_text(llm_response, available_agents)
    
    def _extract_routing_from_text(self, response_text: str, available_agents: Dict[str, Any]) -> Dict[str, Any]:
        """从文本中提取路由信息（fallback方法）"""
        
        response_lower = response_text.lower()
        
        # 智能体名称匹配
        primary_route = "general_analysis"  # 默认
        confidence = 0.5
        
        for agent_name in available_agents.keys():
            if agent_name.lower() in response_lower:
                primary_route = agent_name
                confidence = 0.7
                break
        
        # 执行模式识别
        execution_mode = "sequential"
        if any(keyword in response_lower for keyword in ["parallel", "并行", "同时"]):
            execution_mode = "parallel"
        elif any(keyword in response_lower for keyword in ["hybrid", "混合", "协作"]):
            execution_mode = "hybrid"
        
        return {
            "primary_route": primary_route,
            "confidence": confidence,
            "reasoning": "基于关键词匹配的fallback路由",
            "alternative_routes": [],
            "execution_mode": execution_mode,
            "collaboration_needed": "协作" in response_text or "collaboration" in response_lower,
            "collaborating_agents": [],
            "tool_requirements": [],
            "estimated_success_rate": confidence
        }
    
    def _validate_routing_decision(
        self, 
        routing_decision: Dict[str, Any], 
        available_agents: Dict[str, Any]
    ) -> Dict[str, Any]:
        """验证路由决策的有效性"""
        
        # 验证主要路由
        primary_route = routing_decision.get("primary_route", "")
        if primary_route not in available_agents:
            logger.warning(f"主要路由{primary_route}不在可用智能体中，使用general_analysis")
            routing_decision["primary_route"] = "general_analysis"
        
        # 验证备选路由
        alternative_routes = routing_decision.get("alternative_routes", [])
        valid_alternatives = [
            route for route in alternative_routes 
            if route in available_agents and route != routing_decision["primary_route"]
        ]
        routing_decision["alternative_routes"] = valid_alternatives[:2]  # 最多2个备选
        
        # 验证协作智能体
        collaborating_agents = routing_decision.get("collaborating_agents", [])
        valid_collaborators = [
            agent for agent in collaborating_agents 
            if agent in available_agents and agent != routing_decision["primary_route"]
        ]
        routing_decision["collaborating_agents"] = valid_collaborators
        
        # 验证置信度范围
        confidence = routing_decision.get("confidence", 0.5)
        routing_decision["confidence"] = max(0.0, min(1.0, confidence))
        
        return routing_decision
    
    def _enhance_routing_decision(
        self,
        routing_decision: Dict[str, Any],
        user_intent_analysis: Dict[str, Any],
        available_agents: Dict[str, Any]
    ) -> Dict[str, Any]:
        """增强路由决策，添加额外信息"""
        
        primary_route = routing_decision["primary_route"]
        
        # 添加智能体性能信息
        agent_info = available_agents.get(primary_route, {})
        routing_decision["agent_performance"] = {
            "historical_success_rate": agent_info.get("success_rate", 0.8),
            "avg_execution_time": agent_info.get("avg_execution_time", 300),
            "load_factor": agent_info.get("load_factor", 0.5)
        }
        
        # 添加工具匹配度
        required_tools = user_intent_analysis.get("required_capabilities", [])
        if required_tools:
            tool_match_score = self._calculate_tool_match_score(primary_route, required_tools)
            routing_decision["tool_match_score"] = tool_match_score
        
        # 添加路由标签
        routing_decision["routing_tags"] = self._generate_routing_tags(routing_decision, user_intent_analysis)
        
        # 添加预期结果
        routing_decision["expected_outcomes"] = self._predict_routing_outcomes(routing_decision, user_intent_analysis)
        
        return routing_decision
    
    def _calculate_tool_match_score(self, agent_name: str, required_tools: List[str]) -> float:
        """计算智能体与所需工具的匹配度"""
        
        # 获取智能体支持的工具类型
        agent_tool_mapping = {
            "seismic_agent": ["seismic_processing", "geophysics", "imaging"],
            "logging_agent": ["well_logging", "data_reconstruction", "lithology"],
            "geophysics_agent": ["geophysics", "structure_analysis", "modeling"],
            "reservoir_agent": ["reservoir_modeling", "simulation", "flow_analysis"],
            "economics_agent": ["economic_analysis", "optimization", "reporting"],
            "quality_control": ["data_validation", "quality_assessment", "testing"]
        }
        
        supported_tools = agent_tool_mapping.get(agent_name, [])
        
        if not required_tools or not supported_tools:
            return 0.5  # 默认匹配度
        
        matches = sum(1 for tool in required_tools if any(supported in tool for supported in supported_tools))
        return matches / len(required_tools)
    
    def _generate_routing_tags(
        self, 
        routing_decision: Dict[str, Any], 
        user_intent_analysis: Dict[str, Any]
    ) -> List[str]:
        """生成路由标签用于监控和分析"""
        
        tags = []
        
        # 基于任务类型的标签
        task_type = user_intent_analysis.get("task_type", "")
        if task_type:
            tags.append(f"task:{task_type}")
        
        # 基于复杂度的标签
        complexity = user_intent_analysis.get("complexity", "")
        if complexity:
            tags.append(f"complexity:{complexity}")
        
        # 基于执行模式的标签
        execution_mode = routing_decision.get("execution_mode", "")
        if execution_mode:
            tags.append(f"mode:{execution_mode}")
        
        # 基于协作需求的标签
        if routing_decision.get("collaboration_needed", False):
            tags.append("collaborative")
        
        # 基于置信度的标签
        confidence = routing_decision.get("confidence", 0.5)
        if confidence > 0.8:
            tags.append("high_confidence")
        elif confidence < 0.5:
            tags.append("low_confidence")
        
        return tags
    
    def _predict_routing_outcomes(
        self,
        routing_decision: Dict[str, Any],
        user_intent_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """预测路由决策的结果"""
        
        primary_route = routing_decision["primary_route"]
        execution_mode = routing_decision.get("execution_mode", "sequential")
        
        # 预测执行时间
        base_time = 300  # 5分钟基准
        complexity_multiplier = {
            "simple": 0.5,
            "medium": 1.0,
            "complex": 2.0
        }.get(user_intent_analysis.get("complexity", "medium"), 1.0)
        
        estimated_time = base_time * complexity_multiplier
        
        if execution_mode == "parallel":
            estimated_time *= 0.6  # 并行执行预期减少40%时间
        elif routing_decision.get("collaboration_needed", False):
            estimated_time *= 1.3  # 协作增加30%时间
        
        return {
            "estimated_execution_time": int(estimated_time),
            "expected_success_rate": routing_decision.get("estimated_success_rate", 0.8),
            "resource_intensity": "high" if user_intent_analysis.get("complexity") == "complex" else "medium",
            "output_types": self._predict_output_types(primary_route, user_intent_analysis)
        }
    
    def _predict_output_types(self, agent_name: str, user_intent_analysis: Dict[str, Any]) -> List[str]:
        """预测输出类型"""
        
        # 基于智能体类型预测输出
        output_predictions = {
            "seismic_agent": ["processed_seismic_data", "attribute_volumes", "interpretation_maps"],
            "logging_agent": ["reconstructed_curves", "lithology_analysis", "show_reports"],
            "geophysics_agent": ["structural_models", "property_maps", "analysis_reports"],
            "reservoir_agent": ["3d_models", "simulation_results", "production_forecasts"],
            "economics_agent": ["economic_analysis", "optimization_results", "financial_reports"]
        }
        
        predicted_outputs = output_predictions.get(agent_name, ["analysis_results", "reports"])
        
        # 基于任务类型调整
        task_type = user_intent_analysis.get("task_type", "")
        if "modeling" in task_type:
            predicted_outputs.append("3d_models")
        if "analysis" in task_type:
            predicted_outputs.append("analysis_reports")
        
        return list(set(predicted_outputs))
    
    def _get_available_agents(self) -> Dict[str, Dict[str, Any]]:
        """获取可用智能体列表和能力信息"""
        
        available_agents = {}
        
        # 从注册表获取所有智能体
        all_agents = agent_registry.get_all_agents()
        
        for agent_name, agent_instance in all_agents.items():
            try:
                # 获取智能体基本信息
                agent_info = {
                    "name": agent_instance.get_name(),
                    "description": agent_instance.get_description(),
                    "available": True
                }
                
                # 添加性能统计信息
                stats = self.agent_performance_stats.get(agent_name, {})
                agent_info.update({
                    "success_rate": stats.get("success_rate", 0.8),
                    "avg_execution_time": stats.get("avg_execution_time", 300),
                    "load_factor": stats.get("current_load", 0.0),
                    "performance_score": stats.get("performance_score", 0.5)
                })
                
                available_agents[agent_name] = agent_info
                
            except Exception as e:
                logger.debug(f"获取智能体{agent_name}信息失败: {str(e)}")
                continue
        
        return available_agents
    
    def _refresh_tool_capabilities(self):
        """刷新MCP工具能力画像"""
        
        current_time = time.time()
        if current_time - self._last_cache_refresh < self._cache_refresh_interval:
            return  # 缓存仍然有效
        
        try:
            from app.tools.mcp_client_manager import mcp_client_manager
            
            # 获取所有工具信息
            all_tools = mcp_client_manager.list_all_tools()
            
            # 按类别分组工具能力
            capabilities = {}
            for tool in all_tools:
                tool_name = tool.get("name", "unknown")
                category = self._categorize_tool(tool)
                
                if category not in capabilities:
                    capabilities[category] = []
                
                # 检查工具可用性
                available = self._check_tool_availability(tool_name)
                
                capabilities[category].append({
                    "name": tool_name,
                    "description": tool.get("description", ""),
                    "available": available,
                    "schema": tool.get("schema", {})
                })
            
            self._tool_capabilities_cache = capabilities
            self._last_cache_refresh = current_time
            
            logger.info(f"MCP工具能力画像已刷新，共{len(all_tools)}个工具，{len(capabilities)}个类别")
            
        except Exception as e:
            logger.warning(f"刷新MCP工具能力画像失败: {str(e)}")
    
    def _categorize_tool(self, tool: Dict[str, Any]) -> str:
        """对MCP工具进行分类"""
        
        tool_name = tool.get("name", "").lower()
        description = tool.get("description", "").lower()
        
        # 基于工具名称和描述的关键词分类
        categories = {
            "seismic_processing": ["seismic", "wave", "migration", "decon", "imaging"],
            "well_logging": ["log", "curve", "well", "depth", "drilling"],
            "geophysics": ["gravity", "magnetic", "electromagnetic", "geophys"],
            "reservoir": ["reservoir", "simulation", "flow", "permeability", "porosity"],
            "data_processing": ["process", "filter", "transform", "convert", "clean"],
            "visualization": ["plot", "chart", "image", "visual", "display"],
            "modeling": ["model", "predict", "simulate", "forecast"],
            "analysis": ["analyze", "calculate", "compute", "statistics"],
            "io_operations": ["read", "write", "save", "load", "export", "import"]
        }
        
        for category, keywords in categories.items():
            if any(keyword in tool_name or keyword in description for keyword in keywords):
                return category
        
        return "general"
    
    def _check_tool_availability(self, tool_name: str) -> bool:
        """检查MCP工具可用性"""
        try:
            from app.tools.mcp_client_manager import mcp_client_manager
            schema = mcp_client_manager.get_tool_schema(tool_name)
            return schema is not None
        except Exception:
            return False
    
    def _get_tool_capabilities_summary(self) -> Dict[str, Any]:
        """获取工具能力摘要"""
        return self._tool_capabilities_cache.copy()
    
    def _fallback_routing(self, state: IsotopeSystemState) -> Dict[str, Any]:
        """fallback路由决策"""
        
        # 尝试从任务分析中获取建议
        task_analysis = state.get("metadata", {}).get("task_analysis", {})
        suggested_agents = task_analysis.get("suggested_agents", ["general_analysis"])
        
        return {
            "primary_route": suggested_agents[0] if suggested_agents else "logging",
            "confidence": 0.3,
            "reasoning": "系统fallback路由决策（ReAct模式）",
            "alternative_routes": suggested_agents[1:3] if len(suggested_agents) > 1 else ["seismic"],
            "execution_strategy": "reactive",
            "tool_requirements": [],
            "estimated_success_rate": 0.6,
            "fallback": True
        }
    
    def _fallback_routing_decision(
        self, 
        user_intent_analysis: Dict[str, Any], 
        available_agents: Dict[str, Any]
    ) -> Dict[str, Any]:
        """基于规则的fallback路由决策"""
        
        task_type = user_intent_analysis.get("task_type", "consultation")
        
        # 简单的规则映射
        route_mapping = {
            "seismic_processing": "seismic_agent",
            "logging_reconstruction": "logging_agent", 
            "well_logging_analysis": "logging_agent",
            "structure_recognition": "geophysics_agent",
            "reservoir_modeling": "reservoir_agent",
            "reservoir_simulation": "reservoir_agent",
            "consultation": "general_analysis"
        }
        
        primary_route = route_mapping.get(task_type, "general_analysis")
        
        # 检查智能体是否可用
        if primary_route not in available_agents:
            primary_route = "general_analysis"
        
        return {
            "primary_route": primary_route,
            "confidence": 0.6,
            "reasoning": f"基于任务类型{task_type}的规则映射（ReAct模式）",
            "alternative_routes": ["seismic"] if primary_route != "seismic" else ["logging"],
            "execution_strategy": "reactive",
            "tool_requirements": user_intent_analysis.get("required_capabilities", []),
            "estimated_success_rate": 0.7,
            "fallback": True
        }
    
    def _record_routing_decision(self, routing_decision: Dict[str, Any], user_intent_analysis: Dict[str, Any]):
        """记录路由决策用于性能分析"""
        
        record = {
            "timestamp": time.time(),
            "task_type": user_intent_analysis.get("task_type", "unknown"),
            "primary_route": routing_decision.get("primary_route"),
            "confidence": routing_decision.get("confidence", 0.5),
            "execution_mode": routing_decision.get("execution_mode", "sequential"),
            "collaboration_needed": routing_decision.get("collaboration_needed", False)
        }
        
        self.routing_history.append(record)
        
        # 保持历史记录在合理范围内
        if len(self.routing_history) > 1000:
            self.routing_history = self.routing_history[-500:]
    
    def get_routing_statistics(self) -> Dict[str, Any]:
        """获取路由统计信息"""
        
        if not self.routing_history:
            return {"message": "暂无路由历史数据"}
        
        # 统计路由分布
        route_distribution = {}
        execution_mode_distribution = {}
        
        for record in self.routing_history:
            route = record.get("primary_route", "unknown")
            mode = record.get("execution_mode", "unknown")
            
            route_distribution[route] = route_distribution.get(route, 0) + 1
            execution_mode_distribution[mode] = execution_mode_distribution.get(mode, 0) + 1
        
        # 计算平均置信度
        confidences = [record.get("confidence", 0.5) for record in self.routing_history]
        avg_confidence = sum(confidences) / len(confidences)
        
        return {
            "total_routing_decisions": len(self.routing_history),
            "route_distribution": route_distribution,
            "execution_mode_distribution": execution_mode_distribution,
            "average_confidence": avg_confidence,
            "collaboration_rate": sum(1 for r in self.routing_history if r.get("collaboration_needed")) / len(self.routing_history)
        }
