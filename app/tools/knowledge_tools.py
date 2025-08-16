"""
知识检索工具 - 提供对RAGFlow、数据库和文件信息的查询接口
"""

import logging
import json
from typing import Dict, List, Any, Optional

from app.core.info_hub import get_info_hub
from app.tools.registry import register_tool
# from app.core.task_decorator import task  # 不再需要，已迁移到MCP
from app.tools.schemas import RagflowQuerySchema
from langgraph.config import get_stream_writer
logger = logging.getLogger(__name__)

@register_tool(
    name="ragflow_query",
    description="查询知识库获取回答，知识库已经包含了大量相关的专业文档和知识",
    category="knowledge",
    use_structured_tool=True
)
def ragflow_query(query: str) -> Dict[str, Any]:
    """
    通过知识库进行问答查询
    
    Args:
        query: 查询字符串
        
    Returns:
        知识库的查询结果，包含answer和reference字段
    """
    writer = get_stream_writer()
    logger.info(f"执行知识库查询: {query}")
    
    try:
        info_hub = get_info_hub()
        result = info_hub.query_ragflow(query)
        writer({"custom_step": f"知识库查询结果: \n{result.get('answer', '')}\n参考文献: \n{result.get('references', '')}"})
        
        return {
            "status": "success",
            "query": query,
            "answer": result.get("answer", ""),
            "references": result.get("references", ""),
            "source": "ragflow"
        }
        
    except Exception as e:
        logger.error(f"知识库查询失败: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "source": "ragflow"
        }

# 为ragflow_query工具设置schema
ragflow_query.args_schema = RagflowQuerySchema

# @register_tool(
#     name="sql_query",
#     description="执行SQL查询以获取数据库中的结构化数据，支持参数化查询",
#     category="knowledge"
# )
# def sql_query(query: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
#     """执行SQL查询
    
#     对数据库执行SQL查询，获取数据。
    
#     Args:
#         query: SQL查询语句
#         params: 参数化查询的参数字典（可选）
        
#     Returns:
#         查询结果
#     """
#     try:
#         logger.info(f"执行SQL查询: {query}, 参数: {params}")
#         info_hub = get_info_hub()
        
#         # 如果有参数，直接在查询中替换参数，而不使用%s占位符
#         if params:
#             formatted_query = query
#             # 简单参数替换 - 适用于简单值类型
#             for key, value in params.items():
#                 if isinstance(value, (str)):
#                     # 字符串需要加引号
#                     formatted_query = formatted_query.replace(f":{key}", f"'{value}'")
#                     formatted_query = formatted_query.replace(f"%({key})s", f"'{value}'")
#                 else:
#                     # 数字等可以直接替换
#                     formatted_query = formatted_query.replace(f":{key}", str(value))
#                     formatted_query = formatted_query.replace(f"%({key})s", str(value))
            
#             # 处理查询中的简单%s占位符 - 直接替换为实际值
#             if '%s' in formatted_query and isinstance(params, dict) and 'name' in params:
#                 formatted_query = formatted_query.replace("%s", f"'{params['name']}'")
            
#             # 如果还有其他%s参数，尝试更通用的替换方式
#             if '%s' in formatted_query and len(params) > 0:
#                 # 获取第一个值作为默认值
#                 default_value = list(params.values())[0]
#                 if isinstance(default_value, str):
#                     formatted_query = formatted_query.replace("%s", f"'{default_value}'")
#                 else:
#                     formatted_query = formatted_query.replace("%s", str(default_value))
            
#             logger.info(f"最终SQL查询: {formatted_query}")
#             result = info_hub.query_sql(formatted_query)
#         else:
#             # 执行查询
#             result = info_hub.query_sql(query, params)
        
#         if "error" in result:
#             logger.error(f"SQL查询失败: {result['error']}")
#             return {
#                 "status": "error",
#                 "error": result["error"],
#                 "source": "mysql"
#             }
        
#         return {
#             "status": "success",
#             "columns": result.get("columns", []),
#             "rows": result.get("rows", []),
#             "row_count": result.get("row_count", 0)
#         }
#     except Exception as e:
#         logger.error(f"SQL查询失败: {str(e)}")
#         return {
#             "status": "error",
#             "error": str(e),
#             "source": "mysql"
#         }

# @register_tool(
#     name="search_files",
#     description="搜索系统中的文件，支持按关键词搜索文件名和内容",
#     category="knowledge"
# )
# def search_files(query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
#     """
#     搜索相关文件
    
#     Args:
#         query: 搜索关键词
#         session_id: 会话ID，限制在特定会话中搜索
        
#     Returns:
#         匹配的文件列表
#     """
#     logger.info(f"执行文件搜索: {query}, 会话ID: {session_id}")
    
#     try:
#         info_hub = get_info_hub()
#         # 使用info_hub的retrieval方法只获取文件部分
#         results = info_hub.retrieval(session_id or "", query)
#         files = results.get("files", [])
        
#         return {
#             "status": "success",
#             "files": files,
#             "count": len(files),
#             "source": "files"
#         }
        
#     except Exception as e:
#         logger.error(f"文件搜索失败: {str(e)}")
#         return {
#             "status": "error",
#             "error": str(e),
#             "source": "files"
#         }

# @register_tool(
#     name="retrieve_information",
#     description="综合检索各种信息源（RAGFlow知识库、数据库、文件系统）获取相关信息",
#     category="knowledge"
# )
# def retrieve_information(query: str, session_id: str, top_k: int = 5) -> Dict[str, Any]:
#     """
#     综合检索各类信息
    
#     同时从RAGFlow知识库、数据库记录和文件中检索相关信息
    
#     Args:
#         query: 查询关键词
#         session_id: 会话ID
#         top_k: 每类返回的最大结果数
        
#     Returns:
#         综合检索结果
#     """
#     logger.info(f"执行综合信息检索: {query}, 会话: {session_id}")
    
#     try:
#         info_hub = get_info_hub()
#         results = info_hub.retrieval(session_id, query, top_k)
        
#         return {
#             "status": "success",
#             "vector_docs": results.get("vector_docs", []),
#             "sql_rows": results.get("sql_rows", []),
#             "files": results.get("files", []),
#             "source": "combined"
#         }
        
#     except Exception as e:
#         logger.error(f"综合信息检索失败: {str(e)}")
#         return {
#             "status": "error",
#             "error": str(e),
#             "source": "combined"
#         }

# @register_tool(
#     name="save_numeric_data",
#     description="保存结构化数值数据到数据库和搜索引擎，便于后续检索",
#     category="knowledge"
# )
# def save_numeric_data(name: str, value: float, unit: str = "", 
#                      sample_id: str = "", metadata: Optional[Dict] = None) -> Dict[str, Any]:
#     """
#     保存数值型数据到数据库
    
#     Args:
#         name: 数据名称
#         value: 数值
#         unit: 单位
#         sample_id: 样本ID
#         metadata: 附加元数据
        
#     Returns:
#         保存结果
#     """
#     logger.info(f"保存数值数据: {name}={value}{unit}, 样本ID: {sample_id}")
    
#     try:
#         info_hub = get_info_hub()
#         sample_id = info_hub.save_numeric_data(
#             name=name,
#             value=value,
#             unit=unit,
#             sample_id=sample_id,
#             metadata=metadata or {}
#         )
        
#         return {
#             "status": "success",
#             "sample_id": sample_id,
#             "name": name,
#             "value": value,
#             "unit": unit
#         }
        
#     except Exception as e:
#         logger.error(f"保存数值数据失败: {str(e)}")
#         return {
#             "status": "error",
#             "error": str(e)
#         } 