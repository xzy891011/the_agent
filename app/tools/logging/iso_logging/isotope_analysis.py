"""
碳同位素分析工具 - 提供天然气碳同位素数据解析和分析功能
"""

import os
import logging
import traceback
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Union, Any, Tuple
from scipy import stats
from scipy.signal import savgol_filter
from scipy.optimize import curve_fit
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import warnings

from app.tools.registry import register_tool
from app.core.file_manager import file_manager
from app.core.stream_writer_helper import push_progress, push_thinking, push_error

# 配置日志
logger = logging.getLogger(__name__)


def _identify_isotope_columns(df: pd.DataFrame) -> Dict[str, List[str]]:
    """识别数据框中的同位素列
    
    寻找与甲烷、乙烷、丙烷碳同位素相关的列
    
    Args:
        df: 数据框
        
    Returns:
        {'C1': [列名], 'C2': [列名], 'C3': [列名]}形式的字典
    """
    isotope_columns = {"C1": [], "C2": [], "C3": []}
    
    # 常见的同位素列名模式
    patterns = {
        "C1": ["c1", "ch4", "甲烷", "methane", "δ13C1", "d13c1", "甲烷碳同位素"],
        "C2": ["c2", "c2h6", "乙烷", "ethane", "δ13C2", "d13c2", "乙烷碳同位素"],
        "C3": ["c3", "c3h8", "丙烷", "propane", "δ13C3", "d13c3", "丙烷碳同位素"]
    }
    
    # 优先尝试检测带有明确标签的列
    for component, keywords in patterns.items():
        for col in df.columns:
            col_str = str(col).lower().replace(" ", "").replace("-", "").replace("_", "")
            
            # 检查列名是否包含组分关键词和同位素关键词
            if any(k in col_str for k in keywords) and any(iso in col_str for iso in ["13c", "同位素", "isotope", "δ"]):
                isotope_columns[component].append(col)
                
    # 特殊处理图示中的格式：检查表头中的"甲烷碳同位素值"等类似列
    for col in df.columns:
        col_str = str(col)
        if "甲烷碳同位素值" in col_str or "甲烷碳同位素" in col_str or "甲烷同位素" in col_str:
            if col not in isotope_columns["C1"]:
                isotope_columns["C1"].append(col)
        elif "乙烷碳同位素值" in col_str or "乙烷碳同位素" in col_str or "乙烷同位素" in col_str:
            if col not in isotope_columns["C2"]:
                isotope_columns["C2"].append(col)
        elif "丙烷碳同位素值" in col_str or "丙烷碳同位素" in col_str or "丙烷同位素" in col_str:
            if col not in isotope_columns["C3"]:
                isotope_columns["C3"].append(col)
    
    # 如果没有找到任何组分的同位素列，尝试使用更通用的匹配
    if not any(isotope_columns.values()):
        # 打印所有列名用于调试
        logger.debug(f"列名: {list(df.columns)}")
        
        # 尝试更灵活的匹配
        for col in df.columns:
            col_str = str(col).lower()
            
            # 检查是否包含同位素词汇
            if "同位素" in col_str or "isotope" in col_str or "13c" in col_str or "δ" in col_str:
                # 根据是否包含组分关键词来分类
                if "甲" in col_str or "c1" in col_str or "ch4" in col_str or "methane" in col_str:
                    isotope_columns["C1"].append(col)
                elif "乙" in col_str or "c2" in col_str or "c2h6" in col_str or "ethane" in col_str:
                    isotope_columns["C2"].append(col)
                elif "丙" in col_str or "c3" in col_str or "c3h8" in col_str or "propane" in col_str:
                    isotope_columns["C3"].append(col)
    
    # 如果仍然没有找到，检查表格中包含碳同位素值的列
    # 特殊处理图片中显示的表格格式，使用列索引7-12
    if not any(isotope_columns.values()) and len(df.columns) >= 13:
        try:
            # 特殊处理图片中显示的表格结构
            c1_isotope_col = df.columns[7]  # 甲烷碳同位素值(‰)
            c2_isotope_col = df.columns[9]  # 乙烷碳同位素值(‰)
            c3_isotope_col = df.columns[11]  # 丙烷碳同位素值(‰)
            
            isotope_columns["C1"] = [c1_isotope_col]
            isotope_columns["C2"] = [c2_isotope_col]
            isotope_columns["C3"] = [c3_isotope_col]
            
            logger.info(f"通过表格结构识别同位素列: C1={c1_isotope_col}, C2={c2_isotope_col}, C3={c3_isotope_col}")
        except Exception as e:
            logger.warning(f"通过表格结构识别同位素列失败: {str(e)}")
    
    # 打印识别结果
    for component, cols in isotope_columns.items():
        if cols:
            logger.debug(f"识别到{component}同位素列: {cols}")
    
    return isotope_columns

def _identify_composition_columns(df: pd.DataFrame) -> Dict[str, List[str]]:
    """识别数据框中的组分含量列"""
    result = {
        "C1": [],  # 甲烷
        "C2": [],  # 乙烷
        "C3": [],  # 丙烷
        "iC4": [], # 异丁烷
        "nC4": [], # 正丁烷
        "C5+": [], # C5+
        "CO2": [], # 二氧化碳
    }
    
    # 常见的组分含量列名模式
    patterns = {
        "C1": ["ch4", "c1", "methane", "甲烷"],
        "C2": ["c2h6", "c2", "ethane", "乙烷"],
        "C3": ["c3h8", "c3", "propane", "丙烷"],
        "iC4": ["ic4h10", "ic4", "isobutane", "i-butane", "异丁烷"],
        "nC4": ["nc4h10", "nc4", "n-butane", "normal butane", "正丁烷"],
        "C5+": ["c5+", "c5plus", "heavies", "重烃"],
        "CO2": ["co2", "carbon dioxide", "二氧化碳"],
    }
    
    # 添加可能的量纲或属性关键词
    content_keywords = [
        "含量", "content", "浓度", "concentration", 
        "面积", "area", "峰面积", "peak area", "峰积分", "积分面积", 
        "分布", "distribution", "比例", "ratio", "百分比", "percent", "%", 
        "vol", "体积", "volume", "mol", "摩尔", "molar"
    ]
    
    # 遍历所有列名，进行模式匹配
    for col in df.columns:
        col_lower = str(col).lower().replace(" ", "").replace("-", "").replace("_", "")
        
        # 排除同位素列
        if "13c" in col_lower or "d13" in col_lower or "δ13" in col_lower:
            continue
            
        # 检查是否是组分含量列
        for component, component_patterns in patterns.items():
            for pattern in component_patterns:
                pattern_clean = pattern.lower().replace(" ", "").replace("-", "").replace("_", "")
                
                # 检查完全匹配
                if pattern_clean == col_lower:
                    result[component].append(col)
                    break
                
                # 检查模式 + 关键词组合
                matched = False
                for keyword in content_keywords:
                    keyword_clean = keyword.lower().replace(" ", "").replace("-", "").replace("_", "")
                    
                    # 检查常见组合方式
                    if (pattern_clean + keyword_clean) == col_lower or \
                       (keyword_clean + pattern_clean) == col_lower or \
                       (pattern_clean + "的" + keyword_clean) == col_lower or \
                       (pattern_clean + "_" + keyword_clean) == col_lower:
                        result[component].append(col)
                        matched = True
                        break
                    
                    # 检查列名中是否包含组分和内容关键词（部分匹配）
                    if pattern_clean in col_lower and keyword_clean in col_lower:
                        result[component].append(col)
                        matched = True
                        break
                
                if matched:
                    break
    
    # 尝试检测是否有显示组分数值的列（但列名未明确指出）
    if all(len(cols) == 0 for cols in result.values()):
        # 查找自动适配的组分列
        # 检查数值型列并根据列的相对位置推断
        numeric_cols = [col for col in df.columns if df[col].dtype.kind in 'ifc']
        
        if len(numeric_cols) >= 2:
            # 检查相邻的数值列是否可能是组分列
            # 通常甲烷(C1)数值会明显大于乙烷(C2)，可以用这个特性初步识别
            for i in range(len(numeric_cols) - 1):
                col1 = numeric_cols[i]
                col2 = numeric_cols[i+1]
                
                # 跳过同位素相关列
                col1_lower = str(col1).lower()
                col2_lower = str(col2).lower()
                if any(x in col1_lower for x in ["13c", "d13", "δ13", "isotope"]) or \
                   any(x in col2_lower for x in ["13c", "d13", "δ13", "isotope"]):
                    continue
                
                # 检查两列的平均值
                try:
                    col1_mean = df[col1].mean()
                    col2_mean = df[col2].mean()
                    
                    # 如果第一列均值明显大于第二列，可能代表C1和C2
                    if col1_mean > 0 and col2_mean > 0 and col1_mean > col2_mean * 2:
                        result["C1"].append(col1)
                        result["C2"].append(col2)
                        
                        # 如果还有第三列，检查是否可能是C3
                        if i+2 < len(numeric_cols):
                            col3 = numeric_cols[i+2]
                            col3_lower = str(col3).lower()
                            if not any(x in col3_lower for x in ["13c", "d13", "δ13", "isotope"]):
                                try:
                                    col3_mean = df[col3].mean()
                                    if col3_mean > 0 and col2_mean > col3_mean:
                                        result["C3"].append(col3)
                                except:
                                    pass
                        
                        break
                except:
                    continue
                    
    # 输出调试信息
    if all(len(cols) == 0 for cols in result.values()):
        logger.warning(f"未找到任何组分含量列。可用列名: {list(df.columns)}")
    else:
        logger.info(f"找到组分含量列: {result}")
    
    return result


def _identify_depth_column(df: pd.DataFrame) -> Optional[str]:
    """识别数据框中的深度列"""
    # 常见的深度列名模式
    depth_patterns = [
        "depth", "井深", "深度", "埋深", "钻井深度", "sample_depth", 
        "well_depth", "md", "tvd", "measured_depth", "true_vertical_depth"
    ]
    
    # 检查各列名是否匹配深度模式
    for col in df.columns:
        col_lower = str(col).lower().replace(" ", "").replace("-", "").replace("_", "")
        for pattern in depth_patterns:
            pattern_clean = pattern.lower().replace(" ", "").replace("-", "").replace("_", "")
            if pattern_clean in col_lower:
                return col
    
    # 如果没找到匹配的列名，尝试基于数据特征识别
    # 深度列通常是单调递增或递减的数值列
    for col in df.columns:
        if df[col].dtype.kind in 'ifc':  # 数值类型
            # 计算差值的绝对值和
            diff_sum = np.abs(np.diff(df[col].dropna())).sum()
            # 如果差值和不为零且列名不包含同位素相关词汇
            col_lower = str(col).lower()
            if diff_sum > 0 and not any(x in col_lower for x in ["13c", "d13", "δ13", "isotope"]):
                # 检查是否大致单调
                is_increasing = np.all(np.diff(df[col].dropna()) >= 0)
                is_decreasing = np.all(np.diff(df[col].dropna()) <= 0)
                if is_increasing or is_decreasing:
                    return col
    
    return None





def _extract_isotope_ratios(df: pd.DataFrame) -> Dict[str, Dict[str, List[str]]]:
    """
    从数据框中提取同位素比率和峰面积相关列
    
    Args:
        df: 数据框
        
    Returns:
        嵌套字典，第一层键为组分名称(C1、C2等)，第二层包含"isotope"和"peak"两个键，
        值分别为该组分的同位素列名列表和峰面积列名列表
    """
    result = {
        "C1": {"isotope": [], "peak": []},  # 甲烷
        "C2": {"isotope": [], "peak": []},  # 乙烷
        "C3": {"isotope": [], "peak": []},  # 丙烷
        "iC4": {"isotope": [], "peak": []}, # 异丁烷
        "nC4": {"isotope": [], "peak": []}, # 正丁烷
        "CO2": {"isotope": [], "peak": []}, # 二氧化碳
    }
    
    # 同位素列名模式
    isotope_patterns = {
        "C1": ["δ13c1", "δ13c-c1", "δ13ch4", "d13c1", "d13c-c1", "d13ch4", "13c-ch4", "甲烷碳同位素", "c1碳同位素"],
        "C2": ["δ13c2", "δ13c-c2", "δ13c2h6", "d13c2", "d13c-c2", "d13c2h6", "13c-c2h6", "乙烷碳同位素", "c2碳同位素"],
        "C3": ["δ13c3", "δ13c-c3", "δ13c3h8", "d13c3", "d13c-c3", "d13c3h8", "13c-c3h8", "丙烷碳同位素", "c3碳同位素"],
        "iC4": ["δ13ic4", "δ13c-ic4", "d13ic4", "d13c-ic4", "异丁烷碳同位素", "ic4碳同位素"],
        "nC4": ["δ13nc4", "δ13c-nc4", "d13nc4", "d13c-nc4", "正丁烷碳同位素", "nc4碳同位素"],
        "CO2": ["δ13co2", "δ13c-co2", "d13co2", "d13c-co2", "二氧化碳碳同位素", "co2碳同位素"],
    }
    
    # 峰面积列名模式
    peak_patterns = {
        "C1": ["ch4", "c1", "methane", "甲烷"],
        "C2": ["c2h6", "c2", "ethane", "乙烷"],
        "C3": ["c3h8", "c3", "propane", "丙烷"],
        "iC4": ["ic4h10", "ic4", "isobutane", "i-butane", "异丁烷"],
        "nC4": ["nc4h10", "nc4", "n-butane", "normal butane", "正丁烷"],
        "CO2": ["co2", "carbon dioxide", "二氧化碳"],
    }
    
    # 峰面积相关关键词
    peak_keywords = ["面积", "area", "峰面积", "peak area", "峰积分", "积分面积", "含量", "content", "浓度", "concentration"]
    
    # 检查同位素列
    for col in df.columns:
        col_lower = str(col).lower().replace(" ", "").replace("-", "").replace("_", "")
        
        # 检查是否是同位素列
        for component, patterns in isotope_patterns.items():
            for pattern in patterns:
                pattern_clean = pattern.lower().replace(" ", "").replace("-", "").replace("_", "")
                if pattern_clean in col_lower:
                    result[component]["isotope"].append(col)
                    break
    
    # 检查峰面积列
    for col in df.columns:
        col_lower = str(col).lower().replace(" ", "").replace("-", "").replace("_", "")
        
        # 排除已识别的同位素列
        is_isotope_col = False
        for comp_data in result.values():
            if col in comp_data["isotope"]:
                is_isotope_col = True
                break
        
        if is_isotope_col:
            continue
        
        # 检查是否是峰面积列
        for component, patterns in peak_patterns.items():
            matched = False
            for pattern in patterns:
                pattern_clean = pattern.lower().replace(" ", "").replace("-", "").replace("_", "")
                
                # 直接匹配
                if pattern_clean == col_lower:
                    result[component]["peak"].append(col)
                    matched = True
                    break
                
                # 检查是否有峰面积关键词
                for keyword in peak_keywords:
                    keyword_clean = keyword.lower().replace(" ", "").replace("-", "").replace("_", "")
                    if (pattern_clean + keyword_clean) in col_lower or \
                       (keyword_clean + pattern_clean) in col_lower or \
                       (pattern_clean in col_lower and keyword_clean in col_lower):
                        result[component]["peak"].append(col)
                        matched = True
                        break
                
                if matched:
                    break
    
    # 如果没有找到峰面积列，尝试使用组分含量列数据作为替代
    if all(len(comp_data["peak"]) == 0 for comp_data in result.values()):
        composition_columns = _identify_composition_columns(df)
        for component, columns in composition_columns.items():
            if component in result and columns:
                result[component]["peak"] = columns
    
    # 调试输出
    logger.info(f"提取到的同位素比率列: {result}")
    
    return result