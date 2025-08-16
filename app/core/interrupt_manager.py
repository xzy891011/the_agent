"""
中断管理器模块 - Stage 5实现

该模块实现LangGraph的中断机制，支持：
1. 在关键节点设置中断点
2. 人机交互（Human-in-the-Loop）
3. 中断状态管理和恢复
4. 条件性中断（基于Critic审查结果）
"""

import logging
import time
from typing import Dict, List, Any, Optional, Callable, Union
from datetime import datetime
from enum import Enum

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from pydantic import BaseModel, Field

from app.core.state import IsotopeSystemState, StateManager

logger = logging.getLogger(__name__)

class InterruptType(str, Enum):
    """中断类型枚举"""
    USER_INPUT = "user_input"          # 需要用户输入
    APPROVAL = "approval"              # 需要用户批准
    CLARIFICATION = "clarification"    # 需要澄清
    ERROR_HANDLING = "error_handling"  # 错误处理
    QUALITY_CHECK = "quality_check"    # 质量检查
    CAPABILITY_CHECK = "capability_check"  # 能力检查

class InterruptReason(BaseModel):
    """中断原因模型"""
    type: InterruptType = Field(description="中断类型")
    reason: str = Field(description="中断原因说明")
    context: Dict[str, Any] = Field(default_factory=dict, description="中断上下文")
    options: Optional[List[str]] = Field(default=None, description="可选项（如批准/拒绝）")
    default_action: Optional[str] = Field(default=None, description="默认动作")
    timeout: Optional[int] = Field(default=None, description="超时时间（秒）")

class InterruptPoint(BaseModel):
    """中断点配置"""
    node_name: str = Field(description="节点名称")
    condition: Optional[Callable[[IsotopeSystemState], bool]] = Field(default=None, description="中断条件函数")
    interrupt_before: bool = Field(default=True, description="是否在节点执行前中断")
    interrupt_after: bool = Field(default=False, description="是否在节点执行后中断")
    interrupt_type: InterruptType = Field(default=InterruptType.USER_INPUT, description="中断类型")

class InterruptManager:
    """中断管理器
    
    负责管理LangGraph的中断机制，支持条件性中断和人机交互
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化中断管理器
        
        Args:
            config: 配置参数
        """
        self.config = config or {}
        self.interrupt_points: Dict[str, List[InterruptPoint]] = {}
        self.active_interrupts: Dict[str, InterruptReason] = {}
        self.interrupt_history: List[Dict[str, Any]] = []
        
        # 配置参数
        self.enable_auto_approve = self.config.get("enable_auto_approve", False)
        self.default_timeout = self.config.get("default_timeout", 300)  # 5分钟
        self.max_retry_on_timeout = self.config.get("max_retry_on_timeout", 3)
        
        logger.info("中断管理器已初始化")
    
    def register_interrupt_point(self, interrupt_point: InterruptPoint):
        """注册中断点
        
        Args:
            interrupt_point: 中断点配置
        """
        node_name = interrupt_point.node_name
        if node_name not in self.interrupt_points:
            self.interrupt_points[node_name] = []
        
        self.interrupt_points[node_name].append(interrupt_point)
        logger.debug(f"注册中断点: {node_name} (before={interrupt_point.interrupt_before}, after={interrupt_point.interrupt_after})")
    
    def register_critical_nodes(self, node_names: List[str]):
        """注册关键节点的中断点
        
        Args:
            node_names: 关键节点名称列表
        """
        for node_name in node_names:
            # 在关键节点前设置中断点
            self.register_interrupt_point(InterruptPoint(
                node_name=node_name,
                interrupt_before=True,
                interrupt_type=InterruptType.APPROVAL,
                condition=lambda state: self._should_interrupt_critical_node(state)
            ))
    
    def check_interrupt_before(self, node_name: str, state: IsotopeSystemState) -> Optional[InterruptReason]:
        """检查节点执行前的中断
        
        Args:
            node_name: 节点名称
            state: 当前状态
            
        Returns:
            中断原因，如果不需要中断则返回None
        """
        if node_name not in self.interrupt_points:
            return None
        
        for interrupt_point in self.interrupt_points[node_name]:
            if not interrupt_point.interrupt_before:
                continue
            
            # 检查中断条件
            if interrupt_point.condition:
                try:
                    should_interrupt = interrupt_point.condition(state)
                    if should_interrupt:
                        reason = self._create_interrupt_reason(interrupt_point, state, "before")
                        self._record_interrupt(node_name, reason, "before")
                        return reason
                except Exception as e:
                    logger.error(f"检查中断条件失败: {str(e)}")
            else:
                # 无条件中断
                reason = self._create_interrupt_reason(interrupt_point, state, "before")
                self._record_interrupt(node_name, reason, "before")
                return reason
        
        return None
    
    def check_interrupt_after(self, node_name: str, state: IsotopeSystemState) -> Optional[InterruptReason]:
        """检查节点执行后的中断
        
        Args:
            node_name: 节点名称
            state: 当前状态
            
        Returns:
            中断原因，如果不需要中断则返回None
        """
        if node_name not in self.interrupt_points:
            return None
        
        for interrupt_point in self.interrupt_points[node_name]:
            if not interrupt_point.interrupt_after:
                continue
            
            # 检查中断条件
            if interrupt_point.condition:
                try:
                    should_interrupt = interrupt_point.condition(state)
                    if should_interrupt:
                        reason = self._create_interrupt_reason(interrupt_point, state, "after")
                        self._record_interrupt(node_name, reason, "after")
                        return reason
                except Exception as e:
                    logger.error(f"检查中断条件失败: {str(e)}")
            else:
                # 无条件中断
                reason = self._create_interrupt_reason(interrupt_point, state, "after")
                self._record_interrupt(node_name, reason, "after")
                return reason
        
        return None
    
    def create_interrupt_for_critic(self, critic_result: Dict[str, Any]) -> Optional[InterruptReason]:
        """基于Critic审查结果创建中断
        
        Args:
            critic_result: Critic审查结果
            
        Returns:
            中断原因，如果不需要中断则返回None
        """
        next_action = critic_result.get("next_action")
        
        if next_action != "interrupt":
            return None
        
        # 根据审查结果创建中断原因
        issues = critic_result.get("issues", [])
        level = critic_result.get("level", "warning")
        reasoning = critic_result.get("reasoning", "Critic审查未通过")
        
        # 确定中断类型
        if level == "critical":
            interrupt_type = InterruptType.ERROR_HANDLING
        elif "质量" in reasoning or "quality" in reasoning.lower():
            interrupt_type = InterruptType.QUALITY_CHECK
        elif "能力" in reasoning or "capability" in reasoning.lower():
            interrupt_type = InterruptType.CAPABILITY_CHECK
        else:
            interrupt_type = InterruptType.CLARIFICATION
        
        # 创建中断原因
        reason = InterruptReason(
            type=interrupt_type,
            reason=reasoning,
            context={
                "critic_result": critic_result,
                "issues": issues,
                "level": level
            },
            options=["继续执行", "修改计划", "终止任务"],
            default_action="修改计划",
            timeout=self.default_timeout
        )
        
        self._record_interrupt("critic", reason, "result")
        return reason
    
    def handle_user_response(self, interrupt_id: str, user_response: str) -> Dict[str, Any]:
        """处理用户响应
        
        Args:
            interrupt_id: 中断ID
            user_response: 用户响应
            
        Returns:
            处理结果
        """
        if interrupt_id not in self.active_interrupts:
            return {
                "success": False,
                "error": "中断ID无效或已过期"
            }
        
        interrupt_reason = self.active_interrupts[interrupt_id]
        
        # 记录用户响应
        self._record_user_response(interrupt_id, user_response)
        
        # 移除活动中断
        del self.active_interrupts[interrupt_id]
        
        # 返回处理结果
        return {
            "success": True,
            "interrupt_type": interrupt_reason.type,
            "user_response": user_response,
            "next_action": self._determine_next_action(interrupt_reason, user_response)
        }
    
    def _should_interrupt_critical_node(self, state: IsotopeSystemState) -> bool:
        """判断是否应该在关键节点中断
        
        Args:
            state: 当前状态
            
        Returns:
            是否中断
        """
        # 检查是否有高风险操作
        current_task = state.get("current_task", {})
        task_type = current_task.get("task_type", "")
        
        # 高风险任务类型
        high_risk_tasks = ["data_deletion", "system_modification", "external_api_call"]
        if task_type in high_risk_tasks:
            return True
        
        # 检查是否有多次失败
        action_history = state.get("action_history", [])
        recent_failures = [
            action for action in action_history[-5:]
            if action.get("status") == "error"
        ]
        if len(recent_failures) >= 3:
            return True
        
        # 检查是否有不确定性
        metadata = state.get("metadata", {})
        confidence = metadata.get("confidence", 1.0)
        if confidence < 0.7:
            return True
        
        return False
    
    def _create_interrupt_reason(
        self, 
        interrupt_point: InterruptPoint, 
        state: IsotopeSystemState,
        timing: str
    ) -> InterruptReason:
        """创建中断原因
        
        Args:
            interrupt_point: 中断点配置
            state: 当前状态
            timing: 中断时机（before/after）
            
        Returns:
            中断原因
        """
        current_task = state.get("current_task", {})
        task_description = current_task.get("description", "未知任务")
        
        # 根据中断类型生成原因说明
        if interrupt_point.interrupt_type == InterruptType.APPROVAL:
            reason = f"即将执行节点 '{interrupt_point.node_name}'，需要您的批准"
            options = ["批准执行", "跳过", "修改参数"]
        elif interrupt_point.interrupt_type == InterruptType.CLARIFICATION:
            reason = f"任务 '{task_description}' 需要更多信息"
            options = None
        else:
            reason = f"节点 '{interrupt_point.node_name}' {timing}执行中断"
            options = ["继续", "终止"]
        
        return InterruptReason(
            type=interrupt_point.interrupt_type,
            reason=reason,
            context={
                "node_name": interrupt_point.node_name,
                "timing": timing,
                "task": current_task,
                "state_summary": self._summarize_state(state)
            },
            options=options,
            timeout=self.default_timeout
        )
    
    def _summarize_state(self, state: IsotopeSystemState) -> Dict[str, Any]:
        """总结当前状态
        
        Args:
            state: 当前状态
            
        Returns:
            状态摘要
        """
        messages = state.get("messages", [])
        recent_messages = messages[-3:] if len(messages) > 3 else messages
        
        return {
            "message_count": len(messages),
            "recent_messages": [
                {
                    "role": getattr(msg, "type", "unknown"),
                    "content": getattr(msg, "content", "")[:100] + "..."
                    if hasattr(msg, "content") and len(getattr(msg, "content", "")) > 100
                    else getattr(msg, "content", "")
                }
                for msg in recent_messages
            ],
            "current_task": state.get("current_task", {}),
            "metadata": state.get("metadata", {})
        }
    
    def _record_interrupt(self, node_name: str, reason: InterruptReason, timing: str):
        """记录中断事件
        
        Args:
            node_name: 节点名称
            reason: 中断原因
            timing: 中断时机
        """
        interrupt_id = f"{node_name}_{timing}_{int(time.time() * 1000)}"
        
        interrupt_record = {
            "interrupt_id": interrupt_id,
            "node_name": node_name,
            "timing": timing,
            "reason": reason.dict(),
            "timestamp": datetime.now().isoformat(),
            "status": "active"
        }
        
        self.interrupt_history.append(interrupt_record)
        self.active_interrupts[interrupt_id] = reason
        
        logger.info(f"记录中断: {interrupt_id} - {reason.reason}")
    
    def _record_user_response(self, interrupt_id: str, user_response: str):
        """记录用户响应
        
        Args:
            interrupt_id: 中断ID
            user_response: 用户响应
        """
        for record in self.interrupt_history:
            if record["interrupt_id"] == interrupt_id:
                record["user_response"] = user_response
                record["response_time"] = datetime.now().isoformat()
                record["status"] = "resolved"
                break
    
    def _determine_next_action(self, interrupt_reason: InterruptReason, user_response: str) -> str:
        """根据用户响应决定下一步动作
        
        Args:
            interrupt_reason: 中断原因
            user_response: 用户响应
            
        Returns:
            下一步动作
        """
        # 标准化用户响应
        response_lower = user_response.lower().strip()
        
        # 根据中断类型和用户响应决定动作
        if interrupt_reason.type == InterruptType.APPROVAL:
            if "批准" in response_lower or "approve" in response_lower or "yes" in response_lower:
                return "continue"
            elif "跳过" in response_lower or "skip" in response_lower:
                return "skip"
            elif "修改" in response_lower or "modify" in response_lower:
                return "modify"
            else:
                return "abort"
        
        elif interrupt_reason.type == InterruptType.ERROR_HANDLING:
            if "重试" in response_lower or "retry" in response_lower:
                return "retry"
            elif "跳过" in response_lower or "skip" in response_lower:
                return "skip"
            else:
                return "abort"
        
        else:
            # 默认继续执行
            return "continue"
    
    def get_interrupt_statistics(self) -> Dict[str, Any]:
        """获取中断统计信息
        
        Returns:
            统计信息
        """
        total_interrupts = len(self.interrupt_history)
        active_interrupts = len(self.active_interrupts)
        resolved_interrupts = len([r for r in self.interrupt_history if r["status"] == "resolved"])
        
        # 按类型统计
        type_stats = {}
        for record in self.interrupt_history:
            interrupt_type = record["reason"]["type"]
            type_stats[interrupt_type] = type_stats.get(interrupt_type, 0) + 1
        
        # 按节点统计
        node_stats = {}
        for record in self.interrupt_history:
            node_name = record["node_name"]
            node_stats[node_name] = node_stats.get(node_name, 0) + 1
        
        return {
            "total_interrupts": total_interrupts,
            "active_interrupts": active_interrupts,
            "resolved_interrupts": resolved_interrupts,
            "by_type": type_stats,
            "by_node": node_stats,
            "recent_interrupts": self.interrupt_history[-5:]
        }

class InterruptRecovery:
    """中断恢复处理器"""
    
    def __init__(self, interrupt_manager: InterruptManager):
        """初始化中断恢复处理器
        
        Args:
            interrupt_manager: 中断管理器实例
        """
        self.interrupt_manager = interrupt_manager
        self.recovery_strategies = {
            InterruptType.USER_INPUT: self._recover_from_user_input,
            InterruptType.APPROVAL: self._recover_from_approval,
            InterruptType.CLARIFICATION: self._recover_from_clarification,
            InterruptType.ERROR_HANDLING: self._recover_from_error,
            InterruptType.QUALITY_CHECK: self._recover_from_quality_check,
            InterruptType.CAPABILITY_CHECK: self._recover_from_capability_check
        }
        
        logger.info("中断恢复处理器初始化完成")
    
    def recover_from_interrupt(
        self, 
        interrupt_reason: InterruptReason,
        user_response: Optional[str] = None,
        recovery_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """从中断中恢复
        
        Args:
            interrupt_reason: 中断原因
            user_response: 用户响应（如果有）
            recovery_context: 恢复上下文
            
        Returns:
            恢复结果，包含下一步行动和更新的状态
        """
        logger.info(f"开始从中断恢复: {interrupt_reason.interrupt_type}")
        
        try:
            # 获取恢复策略
            recovery_func = self.recovery_strategies.get(
                interrupt_reason.interrupt_type,
                self._default_recovery
            )
            
            # 执行恢复
            result = recovery_func(interrupt_reason, user_response, recovery_context)
            
            logger.info(f"中断恢复成功: {result.get('next_action', 'unknown')}")
            return result
            
        except Exception as e:
            logger.error(f"中断恢复失败: {str(e)}")
            return {
                "status": "failed",
                "next_action": "abort",
                "error": str(e)
            }
    
    def _recover_from_user_input(
        self, 
        interrupt_reason: InterruptReason,
        user_response: Optional[str],
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """从用户输入中断恢复"""
        if not user_response:
            return {
                "status": "waiting",
                "next_action": "wait",
                "message": "等待用户输入"
            }
        
        return {
            "status": "recovered",
            "next_action": "continue",
            "user_input": user_response,
            "update_state": {
                "user_response": user_response,
                "interrupt_resolved": True
            }
        }
    
    def _recover_from_approval(
        self, 
        interrupt_reason: InterruptReason,
        user_response: Optional[str],
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """从批准中断恢复"""
        if not user_response:
            return {
                "status": "waiting",
                "next_action": "wait",
                "message": "等待用户批准"
            }
        
        # 解析批准响应
        approved = user_response.lower() in ["yes", "approve", "确认", "批准", "同意"]
        
        if approved:
            return {
                "status": "recovered",
                "next_action": "continue",
                "approved": True,
                "update_state": {
                    "approval_status": "approved",
                    "approved_by_user": True,
                    "approval_time": datetime.now().isoformat()
                }
            }
        else:
            return {
                "status": "recovered",
                "next_action": "abort",
                "approved": False,
                "update_state": {
                    "approval_status": "rejected",
                    "rejected_reason": user_response
                }
            }
    
    def _recover_from_clarification(
        self, 
        interrupt_reason: InterruptReason,
        user_response: Optional[str],
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """从澄清中断恢复"""
        if not user_response:
            return {
                "status": "waiting",
                "next_action": "wait",
                "message": interrupt_reason.message
            }
        
        return {
            "status": "recovered",
            "next_action": "replan",
            "clarification": user_response,
            "update_state": {
                "clarified_input": user_response,
                "needs_replanning": True
            }
        }
    
    def _recover_from_error(
        self, 
        interrupt_reason: InterruptReason,
        user_response: Optional[str],
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """从错误中断恢复"""
        error_context = interrupt_reason.context or {}
        error_count = error_context.get("error_count", 1)
        
        if error_count >= 3:
            # 错误次数过多，终止执行
            return {
                "status": "failed",
                "next_action": "abort",
                "message": "错误次数过多，终止执行"
            }
        
        # 尝试恢复
        recovery_action = "retry" if error_count < 2 else "replan"
        
        return {
            "status": "recovered",
            "next_action": recovery_action,
            "error_count": error_count,
            "update_state": {
                "error_recovery_attempted": True,
                "recovery_action": recovery_action
            }
        }
    
    def _recover_from_quality_check(
        self, 
        interrupt_reason: InterruptReason,
        user_response: Optional[str],
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """从质量检查中断恢复"""
        quality_context = interrupt_reason.context or {}
        quality_score = quality_context.get("quality_score", 0)
        
        if user_response and user_response.lower() in ["continue", "继续", "忽略"]:
            # 用户选择忽略质量问题
            return {
                "status": "recovered",
                "next_action": "continue",
                "quality_override": True,
                "update_state": {
                    "quality_check_overridden": True,
                    "override_reason": "用户选择继续"
                }
            }
        
        # 根据质量分数决定下一步
        if quality_score < 0.3:
            next_action = "replan"
        elif quality_score < 0.6:
            next_action = "retry"
        else:
            next_action = "continue"
        
        return {
            "status": "recovered",
            "next_action": next_action,
            "quality_score": quality_score,
            "update_state": {
                "quality_improvement_needed": quality_score < 0.6
            }
        }
    
    def _recover_from_capability_check(
        self, 
        interrupt_reason: InterruptReason,
        user_response: Optional[str],
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """从能力检查中断恢复"""
        capability_context = interrupt_reason.context or {}
        missing_capabilities = capability_context.get("missing_capabilities", [])
        
        if not missing_capabilities:
            # 没有缺失能力，可以继续
            return {
                "status": "recovered",
                "next_action": "continue",
                "message": "能力检查通过"
            }
        
        # 需要重新规划以避开缺失的能力
        return {
            "status": "recovered",
            "next_action": "replan",
            "missing_capabilities": missing_capabilities,
            "update_state": {
                "capability_constraints": missing_capabilities,
                "needs_alternative_plan": True
            }
        }
    
    def _default_recovery(
        self, 
        interrupt_reason: InterruptReason,
        user_response: Optional[str],
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """默认恢复策略"""
        logger.warning(f"使用默认恢复策略: {interrupt_reason.interrupt_type}")
        
        if user_response:
            return {
                "status": "recovered",
                "next_action": "continue",
                "default_recovery": True
            }
        else:
            return {
                "status": "waiting",
                "next_action": "wait",
                "message": "等待用户响应"
            }


def create_default_interrupt_manager(config: Optional[Dict[str, Any]] = None) -> InterruptManager:
    """创建默认的中断管理器
    
    Args:
        config: 配置参数
        
    Returns:
        中断管理器实例
    """
    manager = InterruptManager(config)
    
    # 注册默认的关键节点
    critical_nodes = [
        "data_agent",  # 数据处理节点
        "expert_agent",  # 专家分析节点
        "tool_execution",  # 工具执行节点
    ]
    manager.register_critical_nodes(critical_nodes)
    
    # 注册Critic节点的条件性中断
    manager.register_interrupt_point(InterruptPoint(
        node_name="critic",
        interrupt_after=True,
        interrupt_type=InterruptType.QUALITY_CHECK,
        condition=lambda state: state.get("metadata", {}).get("critic_result", {}).get("next_action") == "interrupt"
    ))
    
    return manager 