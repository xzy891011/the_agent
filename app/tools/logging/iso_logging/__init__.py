"""
天然气碳同位素分析工具包 - 提供专业的碳同位素数据分析和解释功能
"""

# 导入所有工具模块以确保它们被注册


from app.tools.logging.iso_logging.enhanced_isotope_depth_trends import (
    enhanced_analyze_isotope_depth_trends
)

from app.tools.logging.iso_logging.enhanced_isotope_visualization import (
    enhanced_plot_bernard_diagram,
    enhanced_plot_carbon_number_trend,
    enhanced_plot_whiticar_diagram
)

from app.tools.logging.iso_logging.enhanced_isotope_classification import (
    enhanced_classify_gas_source,
    enhanced_analyze_gas_maturity
)

# 导入报告生成工具
from app.tools.logging.iso_logging.reports import generate_isotope_report

# 工具能力已通过 @register_tool 装饰器自动注册，无需重复注册

# 定义导出的工具函数
__all__ = [

    
    # 增强工具
    "enhanced_analyze_isotope_depth_trends",
    "enhanced_plot_bernard_diagram",
    "enhanced_plot_carbon_number_trend",
    "enhanced_plot_whiticar_diagram",
    
    # 增强分类工具
    "enhanced_classify_gas_source",
    "enhanced_analyze_gas_maturity",
    
    # 报告生成工具
    "generate_isotope_report"
] 