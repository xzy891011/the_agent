"""
工具参数的 Pydantic Schema 定义

为所有工具提供标准化的参数验证和文档
"""

from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field
from enum import Enum

# 代码安全级别枚举
class CodeSafetyLevel(str, Enum):
    """代码执行安全级别"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    SANDBOX = "sandbox"

# ===== 代码工具 Schema =====

class GenerateCodeSchema(BaseModel):
    """代码生成工具参数"""
    task_description: str = Field(
        description="详细的任务描述，包括要实现的功能、输入输出要求、处理逻辑等"
    )

class ExecuteCodeSchema(BaseModel):
    """代码执行工具参数"""
    code: str = Field(description="要执行的Python代码")
    safety_level: CodeSafetyLevel = Field(
        default=CodeSafetyLevel.MEDIUM,
        description="安全级别：low(低)、medium(中)、high(高)、sandbox(沙箱)"
    )

class CodeAssistantSchema(BaseModel):
    """代码助手工具参数"""
    task_description: str = Field(
        description="详细的任务描述，包括要实现的功能、输入输出要求、处理逻辑等"
    )
    safety_level: CodeSafetyLevel = Field(
        default=CodeSafetyLevel.MEDIUM,
        description="安全级别：low(低)、medium(中)、high(高)、sandbox(沙箱)"
    )

# ===== 河流建模工具 Schema =====

class GenerateFluvial3DModelSchema(BaseModel):
    """河流3D模型生成工具参数"""
    yaml_path: str = Field(
        default="./data/meanderpy/fluvial_params.yaml",
        description="YAML参数文件路径，包含河流建模的所有参数配置"
    )
    nit: Optional[int] = Field(
        default=2000,
        description="迭代次数，控制河道演化的时间步数"
    )
    channel_width: Optional[float] = Field(
        default=100.0,
        description="河道宽度(米)"
    )
    channel_depth: Optional[float] = Field(
        default=10.0,
        description="河道深度(米)"
    )
    n_bends: Optional[int] = Field(
        default=20,
        description="河道弯曲数量"
    )
    migration_rate: Optional[float] = Field(
        default=60.0,
        description="河道迁移速率常数"
    )

# ===== 岩心分析工具 Schema =====

class IdentifyCrackSchema(BaseModel):
    """岩心裂缝识别工具参数"""
    file_id: str = Field(description="岩心图像文件的ID")
    confidence_threshold: Optional[float] = Field(
        default=0.5,
        description="置信度阈值，用于过滤低置信度的裂缝检测结果"
    )
    min_crack_length: Optional[int] = Field(
        default=10,
        description="最小裂缝长度(像素)，过滤掉过短的裂缝"
    )
    output_format: Optional[str] = Field(
        default="image",
        description="输出格式：image(图像)、json(坐标数据)、both(两者都有)"
    )

# ===== 油藏建模工具 Schema =====

class ReservoirSchema(BaseModel):
    """油藏孔隙度模型预测工具参数"""
    model_config = {"protected_namespaces": ()}  # 允许使用model_前缀
    
    file_id: str = Field(description="地震数据文件ID")
    model_type: Optional[str] = Field(
        default="porosity",
        description="预测模型类型：porosity(孔隙度)、permeability(渗透率)、saturation(饱和度)"
    )
    grid_dimensions: Optional[str] = Field(
        default="(241, 246, 35)",
        description="网格维度，格式为'(nx, ny, nz)'"
    )
    output_format: Optional[str] = Field(
        default="dat",
        description="输出格式：dat、vtk、glb"
    )
    visualization: Optional[bool] = Field(
        default=True,
        description="是否生成3D可视化模型"
    )

# ===== 知识检索工具 Schema =====

class RagflowQuerySchema(BaseModel):
    """RAGFlow知识库查询工具参数"""
    query: str = Field(description="查询问题或关键词")
    assistant_id: Optional[str] = Field(
        default=None,
        description="指定的助手ID，不提供则使用默认助手"
    )
    max_tokens: Optional[int] = Field(
        default=4000,
        description="最大返回token数量"
    )
    include_references: Optional[bool] = Field(
        default=True,
        description="是否包含参考文献信息"
    )

class SqlQuerySchema(BaseModel):
    """SQL查询工具参数"""
    query: str = Field(description="SQL查询语句，仅支持SELECT语句")
    params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="参数化查询的参数字典"
    )
    limit: Optional[int] = Field(
        default=100,
        description="最大返回行数"
    )

class SearchFilesSchema(BaseModel):
    """文件搜索工具参数"""
    query: str = Field(description="搜索关键词")
    session_id: Optional[str] = Field(
        default=None,
        description="会话ID，限制在特定会话中搜索"
    )
    file_types: Optional[List[str]] = Field(
        default=None,
        description="文件类型过滤，如['pdf', 'docx', 'xlsx']"
    )
    max_results: Optional[int] = Field(
        default=10,
        description="最大返回结果数"
    )

class RetrieveInformationSchema(BaseModel):
    """综合信息检索工具参数"""
    query: str = Field(description="查询关键词")
    session_id: str = Field(description="会话ID")
    top_k: Optional[int] = Field(
        default=5,
        description="每类信息源返回的最大结果数"
    )
    sources: Optional[List[str]] = Field(
        default=["ragflow", "database", "files"],
        description="要检索的信息源列表"
    )

# ===== 文件工具 Schema =====

class PreviewFileContentSchema(BaseModel):
    """文件内容预览工具参数"""
    file_id: str = Field(description="文件ID")
    max_lines: Optional[int] = Field(
        default=50,
        description="最大预览行数（或页数，取决于文件类型）"
    )
    encoding: Optional[str] = Field(
        default="utf-8",
        description="文本文件编码格式"
    )

class SearchDocumentsRagSchema(BaseModel):
    """文档RAG检索工具参数"""
    query: str = Field(description="查询内容")
    file_ids: str = Field(description="要检索的文件ID列表，多个ID用逗号分隔")
    chunk_size: Optional[int] = Field(
        default=600,
        description="文档分块大小"
    )
    chunk_overlap: Optional[int] = Field(
        default=100,
        description="文档分块重叠大小"
    )
    top_k: Optional[int] = Field(
        default=10,
        description="返回的最相关文档数量"
    )
    rerank_with_llm: Optional[bool] = Field(
        default=False,
        description="是否使用LLM对结果进行重排序"
    )
    reranked_n: Optional[int] = Field(
        default=5,
        description="LLM重排序后保留的结果数量"
    )

# ===== 同位素分析工具 Schema =====

class EnhancedAnalyzeIsotopeDepthTrendsSchema(BaseModel):
    """增强版同位素深度趋势分析工具参数"""
    file_id: str = Field(description="文件ID，已上传到系统的数据文件")
    num_segments: Optional[int] = Field(
        default=5,
        description="自动分段数量"
    )
    highlight_anomalies: Optional[bool] = Field(
        default=True,
        description="是否自动检测并突出显示异常区间"
    )
    penalties: Optional[str] = Field(
        default="10,20,50,100,200,500,1000",
        description="变点检测算法惩罚值列表，用英文逗号分隔的字符串"
    )

class EnhancedPlotBernardDiagramSchema(BaseModel):
    """增强版Bernard图解工具参数"""
    file_id: str = Field(description="文件ID，已上传到系统的数据文件")
    depth_segments: Optional[bool] = Field(
        default=True,
        description="是否按深度分段"
    )
    num_segments: Optional[int] = Field(
        default=5,
        description="深度段数量"
    )

class EnhancedPlotCarbonNumberTrendSchema(BaseModel):
    """增强版碳数趋势图工具参数"""
    file_id: str = Field(description="文件ID，已上传到系统的数据文件")
    depth_segments: Optional[bool] = Field(
        default=True,
        description="是否按深度分段"
    )
    num_segments: Optional[int] = Field(
        default=5,
        description="深度段数量"
    )

class EnhancedPlotWhiticarDiagramSchema(BaseModel):
    """增强版Whiticar图解工具参数"""
    file_id: str = Field(description="文件ID，已上传到系统的数据文件")
    depth_segments: Optional[bool] = Field(
        default=True,
        description="是否按深度分段"
    )
    num_segments: Optional[int] = Field(
        default=5,
        description="深度段数量"
    )

class EnhancedClassifyGasSourceSchema(BaseModel):
    """增强版气源分类工具参数"""
    file_id: str = Field(description="文件ID，已上传到系统的数据文件")
    depth_segments: Optional[bool] = Field(
        default=True,
        description="是否按深度分段"
    )
    num_segments: Optional[int] = Field(
        default=5,
        description="深度段数量"
    )

class EnhancedAnalyzeGasMaturitySchema(BaseModel):
    """增强版气体成熟度分析工具参数"""
    file_id: str = Field(description="文件ID，已上传到系统的数据文件")
    depth_segments: Optional[bool] = Field(
        default=True,
        description="是否按深度分段"
    )
    num_segments: Optional[int] = Field(
        default=5,
        description="深度段数量"
    )

class GenerateIsotopeReportSchema(BaseModel):
    """同位素报告生成工具参数"""
    state_dict: Optional[Dict[str, Any]] = Field(
        default=None,
        description="系统状态字典，包含所有工具执行结果"
    )
    report_title: Optional[str] = Field(
        default="天然气碳同位素数据解释综合报告",
        description="报告标题"
    )
    include_charts: Optional[bool] = Field(
        default=True,
        description="是否包含图表"
    )
    output_format: Optional[str] = Field(
        default="docx",
        description="输出格式：docx、pdf、html"
    )

# Schema映射字典，用于工具注册时的快速查找
TOOL_SCHEMAS = {
    # 代码工具
    "generate_code": GenerateCodeSchema,
    "execute_code": ExecuteCodeSchema,
    "code_assistant": CodeAssistantSchema,
    
    # 河流建模工具
    "generate_fluvial_3d_model": GenerateFluvial3DModelSchema,
    
    # 岩心分析工具
    "identify_crack": IdentifyCrackSchema,
    
    # 油藏建模工具
    "reservior": ReservoirSchema,
    
    # 知识检索工具
    "ragflow_query": RagflowQuerySchema,
    "sql_query": SqlQuerySchema,
    "search_files": SearchFilesSchema,
    "retrieve_information": RetrieveInformationSchema,
    
    # 文件工具
    "preview_file_content": PreviewFileContentSchema,
    "search_documents_rag": SearchDocumentsRagSchema,
    
    # 同位素分析工具
    "enhanced_analyze_isotope_depth_trends": EnhancedAnalyzeIsotopeDepthTrendsSchema,
    "enhanced_plot_bernard_diagram": EnhancedPlotBernardDiagramSchema,
    "enhanced_plot_carbon_number_trend": EnhancedPlotCarbonNumberTrendSchema,
    "enhanced_plot_whiticar_diagram": EnhancedPlotWhiticarDiagramSchema,
    "enhanced_classify_gas_source": EnhancedClassifyGasSourceSchema,
    "enhanced_analyze_gas_maturity": EnhancedAnalyzeGasMaturitySchema,
    "generate_isotope_report": GenerateIsotopeReportSchema,
}

def get_tool_schema(tool_name: str) -> Optional[BaseModel]:
    """获取指定工具的Schema类
    
    Args:
        tool_name: 工具名称
        
    Returns:
        对应的Schema类，如果不存在则返回None
    """
    return TOOL_SCHEMAS.get(tool_name)

def validate_tool_args(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """验证工具参数
    
    Args:
        tool_name: 工具名称
        args: 参数字典
        
    Returns:
        验证后的参数字典
        
    Raises:
        ValueError: 参数验证失败时
    """
    schema_class = get_tool_schema(tool_name)
    if schema_class is None:
        # 如果没有定义schema，直接返回原参数
        return args
    
    try:
        # 使用pydantic验证参数
        validated = schema_class(**args)
        return validated.model_dump()
    except Exception as e:
        raise ValueError(f"工具 {tool_name} 参数验证失败: {str(e)}")

def get_tool_schema_info(tool_name: str) -> Dict[str, Any]:
    """获取工具Schema的详细信息
    
    Args:
        tool_name: 工具名称
        
    Returns:
        Schema信息字典，包含字段定义、类型、描述等
    """
    schema_class = get_tool_schema(tool_name)
    if schema_class is None:
        return {"error": f"工具 {tool_name} 没有定义Schema"}
    
    schema_info = {
        "tool_name": tool_name,
        "schema_class": schema_class.__name__,
        "fields": {}
    }
    
    # 获取字段信息
    for field_name, field_info in schema_class.model_fields.items():
        schema_info["fields"][field_name] = {
            "type": str(field_info.annotation),
            "description": field_info.description,
            "default": field_info.default if field_info.default is not None else "无默认值",
            "required": field_info.is_required()
        }
    
    return schema_info 