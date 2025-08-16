"""
人类审批门智能体 - 负责人类在环控制和审批流程
"""

import logging
import time
import json
from typing import Dict, List, Any, Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from app.core.state import IsotopeSystemState, StateManager
from app.agents.registry import AgentProtocol

logger = logging.getLogger(__name__)

class HumanApprovalGate(AgentProtocol):
    """人类审批门 - 处理需要人工审批的关键决策点"""
    
    def __init__(self, llm: Optional[BaseChatModel] = None, config: Optional[Dict[str, Any]] = None, memory_integration: Optional[Any] = None, info_hub: Optional[Any] = None):
        self.llm = llm
        self.config = config or {}
        self.name = "human_approval_gate"
        self.description = "人类审批门，负责处理需要人工审批的关键任务和决策点"
        
        # 增强功能模块
        self.memory_integration = memory_integration
        self.info_hub = info_hub
        
        # 审批配置
        self.approval_timeout = self.config.get("approval_timeout", 1800)  # 30分钟超时
        self.auto_approve_simple = self.config.get("auto_approve_simple", False)
        self.require_reason = self.config.get("require_reason", True)
        
        # 审批历史
        self.approval_history = []
        self.pending_approvals = {}
    
    def run(self, state: IsotopeSystemState) -> IsotopeSystemState:
        """执行人类审批流程"""
        logger.info("HumanApprovalGate开始处理审批请求")
        
        try:
            # 检查是否需要审批
            approval_request = self._generate_approval_request(state)
            
            if not approval_request.get("requires_approval", False):
                logger.info("HumanApprovalGate判断不需要审批，直接通过")
                state["metadata"]["approval_status"] = "auto_approved"
                state["metadata"]["approval_reason"] = "系统判断为简单操作，无需人工审批"
                return state
            
            # 检查是否已有审批结果
            existing_approval = self._check_existing_approval(state, approval_request)
            if existing_approval:
                logger.info("HumanApprovalGate发现已有审批结果")
                state = self._apply_approval_result(state, existing_approval)
                return state
            
            # 等待人类审批
            approval_result = self._request_human_approval(state, approval_request)
            state = self._apply_approval_result(state, approval_result)
            
            return state
            
        except Exception as e:
            logger.error(f"HumanApprovalGate执行失败: {str(e)}")
            # 安全模式：默认需要审批
            state["metadata"]["approval_status"] = "pending"
            state["metadata"]["approval_error"] = str(e)
            return state
    
    def get_name(self) -> str:
        return self.name
    
    def get_description(self) -> str:
        return self.description
    
    def _generate_approval_request(self, state: IsotopeSystemState) -> Dict[str, Any]:
        """生成审批请求"""
        
        # 获取当前任务信息
        task_plan = state.get("metadata", {}).get("task_plan", {})
        current_step = state.get("metadata", {}).get("current_step", {})
        task_analysis = state.get("metadata", {}).get("task_analysis", {})
        
        # 判断是否需要审批
        requires_approval = self._should_require_approval(task_plan, current_step, task_analysis)
        
        if not requires_approval:
            return {"requires_approval": False}
        
        # 生成用户友好的审批请求
        approval_request = {
            "requires_approval": True,
            "request_id": f"approval_{int(time.time())}",
            "timestamp": time.time(),
            "task_type": task_plan.get("task_type", "unknown"),
            "task_description": task_plan.get("description", "未知任务"),
            "current_step": current_step,
            "approval_points": [],
            "risks": [],
            "recommendations": [],
            "expected_outcomes": [],
            "resource_requirements": {}
        }
        
        # 分析具体的审批点
        approval_points = self._identify_approval_points(task_plan, current_step, state)
        approval_request["approval_points"] = approval_points
        
        # 风险评估
        risks = self._assess_risks(task_plan, current_step, state)
        approval_request["risks"] = risks
        
        # 生成建议
        recommendations = self._generate_recommendations(task_plan, current_step, risks)
        approval_request["recommendations"] = recommendations
        
        # 预期结果
        expected_outcomes = self._predict_outcomes(task_plan, current_step, state)
        approval_request["expected_outcomes"] = expected_outcomes
        
        # 资源需求
        resource_requirements = self._estimate_resource_requirements(task_plan, current_step)
        approval_request["resource_requirements"] = resource_requirements
        
        return approval_request
    
    def _should_require_approval(
        self, 
        task_plan: Dict[str, Any], 
        current_step: Dict[str, Any], 
        task_analysis: Dict[str, Any]
    ) -> bool:
        """判断是否需要人类审批"""
        
        # 1. 任务级别的审批要求
        if task_plan.get("requires_human_approval", False):
            return True
        
        # 2. 步骤级别的审批要求
        if current_step.get("requires_human", False):
            return True
        
        # 3. 基于任务复杂度
        complexity = task_analysis.get("complexity", "simple")
        if complexity == "complex":
            return True
        
        # 4. 基于风险评估
        high_risk_indicators = [
            "reservoir_simulation",  # 油藏模拟
            "reservoir_modeling",    # 储层建模
            "critical_interpretation"  # 关键解释
        ]
        
        task_type = task_plan.get("task_type", "")
        if any(indicator in task_type for indicator in high_risk_indicators):
            return True
        
        # 5. 基于MCP工具风险
        mcp_tools = current_step.get("mcp_tools", [])
        high_risk_tools = ["data_deletion", "model_deployment", "production_update"]
        if any(tool in high_risk_tools for tool in mcp_tools):
            return True
        
        # 6. 自动审批简单任务
        if self.auto_approve_simple and complexity == "simple" and task_type == "consultation":
            return False
        
        # 默认需要审批
        return True
    
    def _identify_approval_points(
        self, 
        task_plan: Dict[str, Any], 
        current_step: Dict[str, Any], 
        state: IsotopeSystemState
    ) -> List[Dict[str, Any]]:
        """识别具体的审批点"""
        
        approval_points = []
        
        # 数据访问审批
        if current_step.get("mcp_tools") and any("data" in tool for tool in current_step.get("mcp_tools", [])):
            approval_points.append({
                "type": "data_access",
                "description": "任务需要访问数据文件和数据库",
                "details": f"将使用工具: {', '.join(current_step.get('mcp_tools', []))}",
                "impact": "medium"
            })
        
        # 模型训练/执行审批
        model_related_actions = ["training", "modeling", "simulation", "reconstruction"]
        if any(action in current_step.get("action", "").lower() for action in model_related_actions):
            approval_points.append({
                "type": "model_execution",
                "description": "任务将执行机器学习模型或数值模拟",
                "details": f"执行动作: {current_step.get('action', '未知')}",
                "impact": "high"
            })
        
        # 解释结果审批
        if "interpretation" in current_step.get("action", "").lower():
            approval_points.append({
                "type": "interpretation",
                "description": "任务将生成专业解释结果",
                "details": "解释结果可能影响后续决策",
                "impact": "high"
            })
        
        # 并行执行审批
        if current_step.get("parallel_execution", False):
            approval_points.append({
                "type": "parallel_execution",
                "description": "任务将并行执行多个子任务",
                "details": f"并行组: {current_step.get('parallel_group', '未知')}",
                "impact": "medium"
            })
        
        return approval_points
    
    def _assess_risks(
        self, 
        task_plan: Dict[str, Any], 
        current_step: Dict[str, Any], 
        state: IsotopeSystemState
    ) -> List[Dict[str, Any]]:
        """评估执行风险"""
        
        risks = []
        
        # 数据风险
        if "files" in state and len(state["files"]) > 0:
            risks.append({
                "category": "data_risk",
                "level": "medium",
                "description": "任务将处理用户上传的数据文件",
                "mitigation": "建议备份原始数据"
            })
        
        # 计算资源风险
        estimated_duration = current_step.get("estimated_duration", 0)
        if estimated_duration > 1800:  # 30分钟以上
            risks.append({
                "category": "resource_risk", 
                "level": "medium",
                "description": f"任务预计耗时{estimated_duration//60}分钟，可能消耗大量计算资源",
                "mitigation": "建议在系统负载较低时执行"
            })
        
        # 并发风险
        if current_step.get("parallel_execution", False):
            risks.append({
                "category": "concurrency_risk",
                "level": "low",
                "description": "并行执行可能导致资源竞争",
                "mitigation": "系统将自动管理并发控制"
            })
        
        # 工具可用性风险
        mcp_tools = current_step.get("mcp_tools", [])
        if len(mcp_tools) > 3:
            risks.append({
                "category": "dependency_risk",
                "level": "medium", 
                "description": f"任务依赖{len(mcp_tools)}个外部工具",
                "mitigation": "将在执行前检查工具可用性"
            })
        
        return risks
    
    def _generate_recommendations(
        self,
        task_plan: Dict[str, Any],
        current_step: Dict[str, Any], 
        risks: List[Dict[str, Any]]
    ) -> List[str]:
        """生成审批建议"""
        
        recommendations = []
        
        # 基于风险级别的建议
        high_risk_count = sum(1 for risk in risks if risk.get("level") == "high")
        if high_risk_count > 0:
            recommendations.append("建议仔细审查高风险项目后再批准")
        
        # 基于任务类型的建议
        task_type = task_plan.get("task_type", "")
        if "simulation" in task_type:
            recommendations.append("油藏模拟任务建议在确认模型参数无误后执行")
        elif "seismic" in task_type:
            recommendations.append("地震处理任务建议确认数据质量后执行")
        elif "logging" in task_type:
            recommendations.append("录井分析任务建议核实样品信息后执行")
        
        # 基于执行时间的建议
        estimated_duration = current_step.get("estimated_duration", 0)
        if estimated_duration > 3600:  # 1小时以上
            recommendations.append("长时间任务建议选择合适时间执行，避免影响其他用户")
        
        # 默认建议
        if not recommendations:
            recommendations.append("任务看起来正常，可以批准执行")
        
        return recommendations
    
    def _predict_outcomes(
        self,
        task_plan: Dict[str, Any],
        current_step: Dict[str, Any],
        state: IsotopeSystemState
    ) -> List[str]:
        """预测任务执行结果"""
        
        outcomes = []
        
        action = current_step.get("action", "")
        task_type = task_plan.get("task_type", "")
        
        # 基于任务类型预测
        outcome_predictions = {
            "seismic_processing": [
                "生成处理后的地震数据体",
                "输出地震属性分析结果", 
                "可能生成解释图件"
            ],
            "logging_reconstruction": [
                "补全缺失的测井曲线",
                "生成数据质量报告",
                "输出重构后的测井数据"
            ],
            "well_logging_analysis": [
                "生成岩性分析结果",
                "识别油气显示层段",
                "输出综合录井解释报告"
            ],
            "reservoir_modeling": [
                "构建三维地质模型",
                "生成储层参数分布",
                "输出建模质量评估报告"
            ]
        }
        
        predicted_outcomes = outcome_predictions.get(task_type, ["执行指定的分析任务", "生成相应的结果文件"])
        outcomes.extend(predicted_outcomes)
        
        # 基于MCP工具预测
        mcp_tools = current_step.get("mcp_tools", [])
        if any("visualization" in tool for tool in mcp_tools):
            outcomes.append("生成可视化图表和图件")
        
        if any("report" in tool for tool in mcp_tools):
            outcomes.append("生成专业分析报告")
        
        return outcomes
    
    def _estimate_resource_requirements(
        self,
        task_plan: Dict[str, Any], 
        current_step: Dict[str, Any]
    ) -> Dict[str, Any]:
        """估算资源需求"""
        
        estimated_duration = current_step.get("estimated_duration", 60)
        mcp_tools_count = len(current_step.get("mcp_tools", []))
        
        return {
            "estimated_time": f"{estimated_duration // 60}分钟{estimated_duration % 60}秒",
            "cpu_intensive": "modeling" in current_step.get("action", "") or "simulation" in current_step.get("action", ""),
            "memory_usage": "high" if mcp_tools_count > 5 else "medium",
            "disk_space": "可能生成大量临时文件" if "processing" in task_plan.get("task_type", "") else "正常",
            "network_usage": "需要访问MCP工具服务" if mcp_tools_count > 0 else "minimal"
        }
    
    def _check_existing_approval(
        self, 
        state: IsotopeSystemState, 
        approval_request: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """检查是否已有审批结果"""
        
        # 检查状态中的审批信息
        approval_status = state.get("metadata", {}).get("approval_status")
        if approval_status in ["approved", "rejected"]:
            return {
                "status": approval_status,
                "timestamp": state.get("metadata", {}).get("approval_timestamp", time.time()),
                "reason": state.get("metadata", {}).get("approval_reason", ""),
                "source": "state_cache"
            }
        
        # 检查审批历史
        task_id = state.get("metadata", {}).get("task_plan", {}).get("task_id")
        if task_id:
            for approval in self.approval_history:
                if approval.get("task_id") == task_id and approval.get("status") in ["approved", "rejected"]:
                    return approval
        
        return None
    
    def _request_human_approval(
        self,
        state: IsotopeSystemState,
        approval_request: Dict[str, Any]
    ) -> Dict[str, Any]:
        """请求人类审批"""
        
        logger.info(f"HumanApprovalGate请求人类审批: {approval_request['request_id']}")
        
        # 生成审批消息
        approval_message = self._format_approval_message(approval_request)
        
        # 添加审批请求消息到状态
        system_msg = SystemMessage(content=approval_message)
        if "messages" not in state:
            state["messages"] = []
        state["messages"].append(system_msg)
        
        # 设置等待审批状态
        approval_result = {
            "status": "pending",
            "request_id": approval_request["request_id"],
            "timestamp": time.time(),
            "message": "等待人类审批",
            "timeout": time.time() + self.approval_timeout
        }
        
        # 记录待审批请求
        self.pending_approvals[approval_request["request_id"]] = {
            "request": approval_request,
            "state_snapshot": state.copy(),
            "created_at": time.time()
        }
        
        return approval_result
    
    def _format_approval_message(self, approval_request: Dict[str, Any]) -> str:
        """格式化审批消息"""
        
        message_parts = [
            "🔍 **需要您的审批** 🔍",
            "",
            f"**任务类型**: {approval_request.get('task_description', '未知任务')}",
            f"**任务ID**: {approval_request.get('request_id')}",
            ""
        ]
        
        # 审批点
        approval_points = approval_request.get("approval_points", [])
        if approval_points:
            message_parts.extend([
                "**需要审批的关键点:**",
                ""
            ])
            for i, point in enumerate(approval_points, 1):
                impact_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(point.get("impact", "low"), "⚪")
                message_parts.append(f"{i}. {impact_emoji} **{point.get('description')}**")
                message_parts.append(f"   详情: {point.get('details', '无')}")
                message_parts.append("")
        
        # 风险评估
        risks = approval_request.get("risks", [])
        if risks:
            message_parts.extend([
                "**风险评估:**",
                ""
            ])
            for risk in risks:
                level_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk.get("level", "low"), "⚪")
                message_parts.append(f"• {level_emoji} {risk.get('description')}")
                if risk.get("mitigation"):
                    message_parts.append(f"  缓解措施: {risk.get('mitigation')}")
            message_parts.append("")
        
        # 预期结果
        expected_outcomes = approval_request.get("expected_outcomes", [])
        if expected_outcomes:
            message_parts.extend([
                "**预期执行结果:**",
                ""
            ])
            for outcome in expected_outcomes:
                message_parts.append(f"• {outcome}")
            message_parts.append("")
        
        # 资源需求
        resource_req = approval_request.get("resource_requirements", {})
        if resource_req:
            message_parts.extend([
                "**资源需求:**",
                f"• 预计耗时: {resource_req.get('estimated_time', '未知')}",
                f"• 内存使用: {resource_req.get('memory_usage', '正常')}",
                f"• 计算密集: {'是' if resource_req.get('cpu_intensive') else '否'}",
                ""
            ])
        
        # 建议
        recommendations = approval_request.get("recommendations", [])
        if recommendations:
            message_parts.extend([
                "**系统建议:**",
                ""
            ])
            for rec in recommendations:
                message_parts.append(f"• {rec}")
            message_parts.append("")
        
        # 操作指引
        message_parts.extend([
            "---",
            "**请回复以下选项之一：**",
            "• `批准` 或 `approve` - 批准执行此任务",
            "• `拒绝` 或 `reject` - 拒绝执行此任务", 
            "• `修改 [说明]` - 需要修改任务参数",
            "",
            f"⏰ 此审批请求将在 {self.approval_timeout // 60} 分钟后超时"
        ])
        
        return "\n".join(message_parts)
    
    def _apply_approval_result(
        self,
        state: IsotopeSystemState,
        approval_result: Dict[str, Any]
    ) -> IsotopeSystemState:
        """应用审批结果"""
        
        status = approval_result.get("status", "pending")
        
        # 更新状态元数据
        state["metadata"]["approval_status"] = status
        state["metadata"]["approval_timestamp"] = approval_result.get("timestamp", time.time())
        state["metadata"]["approval_reason"] = approval_result.get("reason", "")
        state["metadata"]["approval_source"] = approval_result.get("source", "human")
        
        # 记录到审批历史
        if status in ["approved", "rejected"]:
            task_id = state.get("metadata", {}).get("task_plan", {}).get("task_id")
            approval_record = {
                "task_id": task_id,
                "request_id": approval_result.get("request_id"),
                "status": status,
                "timestamp": approval_result.get("timestamp", time.time()),
                "reason": approval_result.get("reason", ""),
                "approver": approval_result.get("approver", "system")
            }
            self.approval_history.append(approval_record)
        
        # 根据审批结果添加消息
        if status == "approved":
            approval_msg = AIMessage(content="✅ 任务已获得批准，继续执行。")
        elif status == "rejected":
            approval_msg = AIMessage(content="❌ 任务被拒绝，已停止执行。")
        elif status == "pending":
            approval_msg = AIMessage(content="⏳ 任务等待审批中...")
        else:
            approval_msg = AIMessage(content=f"审批状态: {status}")
        
        if "messages" not in state:
            state["messages"] = []
        state["messages"].append(approval_msg)
        
        logger.info(f"HumanApprovalGate应用审批结果: {status}")
        
        return state
    
    def process_human_response(self, request_id: str, human_input: str, user_id: str = "user") -> Dict[str, Any]:
        """处理人类的审批响应"""
        
        logger.info(f"HumanApprovalGate处理人类响应: {request_id}")
        
        if request_id not in self.pending_approvals:
            return {
                "status": "error",
                "message": "未找到对应的审批请求"
            }
        
        # 解析人类响应
        human_input_lower = human_input.lower().strip()
        
        if any(word in human_input_lower for word in ["批准", "approve", "同意", "ok"]):
            status = "approved"
            reason = "用户批准"
        elif any(word in human_input_lower for word in ["拒绝", "reject", "不同意", "no"]):
            status = "rejected" 
            reason = "用户拒绝"
        elif human_input_lower.startswith("修改"):
            status = "modification_requested"
            reason = human_input
        else:
            # 无法识别的响应，要求澄清
            return {
                "status": "clarification_needed",
                "message": "无法识别您的回复，请明确回复'批准'或'拒绝'"
            }
        
        # 创建审批结果
        approval_result = {
            "status": status,
            "request_id": request_id,
            "timestamp": time.time(),
            "reason": reason,
            "approver": user_id,
            "source": "human_response"
        }
        
        # 移除待审批请求
        del self.pending_approvals[request_id]
        
        return approval_result
    
    def get_pending_approvals(self) -> Dict[str, Dict[str, Any]]:
        """获取待审批请求列表"""
        return self.pending_approvals.copy()
    
    def cleanup_expired_approvals(self):
        """清理过期的审批请求"""
        current_time = time.time()
        expired_requests = []
        
        for request_id, approval_info in self.pending_approvals.items():
            created_at = approval_info.get("created_at", current_time)
            if current_time - created_at > self.approval_timeout:
                expired_requests.append(request_id)
        
        for request_id in expired_requests:
            logger.warning(f"清理过期的审批请求: {request_id}")
            del self.pending_approvals[request_id]
