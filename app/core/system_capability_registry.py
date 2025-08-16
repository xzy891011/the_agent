"""
系统能力注册表 - 记录系统所有可用的工具、任务和子图能力
"""
from typing import Dict, List, Any, Optional, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class CapabilityType(str, Enum):
    """能力类型"""
    TOOL = "tool"
    TASK = "task"
    SUBGRAPH = "subgraph"
    ANALYSIS = "analysis"
    VISUALIZATION = "visualization"
    DATA_PROCESSING = "data_processing"

@dataclass
class SystemCapability:
    """系统能力定义"""
    name: str
    type: CapabilityType
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    required_inputs: List[str] = field(default_factory=list)
    expected_outputs: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "name": self.name,
            "type": self.type.value,
            "description": self.description,
            "parameters": self.parameters,
            "required_inputs": self.required_inputs,
            "expected_outputs": self.expected_outputs,
            "dependencies": self.dependencies,
            "examples": self.examples,
            "metadata": self.metadata
        }

class SystemCapabilityRegistry:
    """系统能力注册表单例"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SystemCapabilityRegistry, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.capabilities: Dict[str, SystemCapability] = {}
        self.capability_types: Dict[CapabilityType, Set[str]] = {
            cap_type: set() for cap_type in CapabilityType
        }
        self._initialized = True
        
        # 自动注册系统内置能力
        self._register_builtin_capabilities()
    
    def register_capability(self, capability: SystemCapability) -> bool:
        """注册系统能力"""
        try:
            if capability.name in self.capabilities:
                logger.warning(f"能力 {capability.name} 已存在，将被覆盖")
            
            self.capabilities[capability.name] = capability
            self.capability_types[capability.type].add(capability.name)
            
            logger.info(f"注册系统能力: {capability.name} (类型: {capability.type})")
            return True
            
        except Exception as e:
            logger.error(f"注册能力失败: {str(e)}")
            return False
    
    def get_capability(self, name: str) -> Optional[SystemCapability]:
        """获取指定能力"""
        return self.capabilities.get(name)
    
    def get_capabilities_by_type(self, cap_type: CapabilityType) -> List[SystemCapability]:
        """按类型获取能力列表"""
        names = self.capability_types.get(cap_type, set())
        return [self.capabilities[name] for name in names if name in self.capabilities]
    
    def search_capabilities(self, query: str) -> List[SystemCapability]:
        """搜索相关能力"""
        query_lower = query.lower()
        results = []
        
        for cap in self.capabilities.values():
            # 搜索名称、描述和示例
            if (query_lower in cap.name.lower() or 
                query_lower in cap.description.lower() or
                any(query_lower in ex.lower() for ex in cap.examples)):
                results.append(cap)
        
        return results
    
    def get_all_capabilities(self) -> Dict[str, SystemCapability]:
        """获取所有能力"""
        return self.capabilities.copy()
    
    def get_capability_summary(self) -> Dict[str, Any]:
        """获取能力摘要"""
        summary = {
            "total_count": len(self.capabilities),
            "by_type": {}
        }
        
        for cap_type in CapabilityType:
            caps = self.get_capabilities_by_type(cap_type)
            summary["by_type"][cap_type.value] = {
                "count": len(caps),
                "names": [cap.name for cap in caps]
            }
        
        return summary
    
    def _register_builtin_capabilities(self):
        """注册系统内置能力"""
        # 数据分析能力
        self.register_capability(SystemCapability(
            name="analyze_carbon_isotope_data",
            type=CapabilityType.ANALYSIS,
            description="分析天然气碳同位素数据，判断成因类型",
            required_inputs=["isotope_data", "sample_info"],
            expected_outputs=["analysis_result", "gas_origin_type"],
            examples=[
                "请分析这个碳同位素数据文件",
                "判断天然气的成因类型"
            ]
        ))
        
        # 可视化能力
        self.register_capability(SystemCapability(
            name="generate_bernard_diagram",
            type=CapabilityType.VISUALIZATION,
            description="生成Bernard图解用于天然气成因判别",
            required_inputs=["c1_c2_ratio", "delta_c1"],
            expected_outputs=["diagram_image", "interpretation"],
            examples=[
                "生成Bernard图解",
                "创建天然气成因判别图"
            ]
        ))
        
        # 数据处理能力
        self.register_capability(SystemCapability(
            name="process_las_file",
            type=CapabilityType.DATA_PROCESSING,
            description="处理LAS格式的测井数据文件",
            required_inputs=["las_file_path"],
            expected_outputs=["processed_data", "data_summary"],
            examples=[
                "处理这个LAS文件",
                "读取测井数据"
            ]
        ))

# 全局单例实例
_system_capability_registry = None

def get_system_capability_registry() -> SystemCapabilityRegistry:
    """获取系统能力注册表的单例实例
    
    Returns:
        SystemCapabilityRegistry: 系统能力注册表实例
    """
    global _system_capability_registry
    if _system_capability_registry is None:
        _system_capability_registry = SystemCapabilityRegistry()
    return _system_capability_registry

# 全局注册表实例 - 使用函数获取确保单例
system_capability_registry = get_system_capability_registry()

# 辅助函数
def register_capability(capability: SystemCapability) -> bool:
    """注册系统能力的便捷函数"""
    return system_capability_registry.register_capability(capability)

def get_system_capabilities() -> Dict[str, SystemCapability]:
    """获取所有系统能力"""
    return system_capability_registry.get_all_capabilities()

def search_capabilities(query: str) -> List[SystemCapability]:
    """搜索系统能力"""
    return system_capability_registry.search_capabilities(query) 