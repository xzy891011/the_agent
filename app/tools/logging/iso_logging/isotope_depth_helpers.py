"""
碳同位素深度数据处理辅助函数 - 用于处理随深度变化的碳同位素数据
"""

import os
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Union, Any, Tuple
import ruptures as rpt
from scipy import signal
from scipy import stats

# 配置日志
logger = logging.getLogger(__name__)

def preprocess_isotope_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    预处理碳同位素数据，包括列名标准化、缺失值处理、异常值检测等
    
    Args:
        df: 输入的数据框
        
    Returns:
        预处理后的数据框
    """
    # 创建副本避免修改原始数据
    df_processed = df.copy()
    
    # 1. 列名标准化（转为小写并去除多余空格）
    df_processed.columns = [str(col).lower().strip() for col in df_processed.columns]
    
    # 2. 检测和转换非数值列
    for col in df_processed.columns:
        # 跳过明显的非数值列
        if col in ['id', 'name', 'description', 'sample', 'well', 'location']:
            continue
            
        # 尝试将可能的数值列转换为数值类型
        if df_processed[col].dtype == 'object':
            try:
                # 替换常见的占位符
                df_processed[col] = df_processed[col].replace(['n.d.', 'nd', '-', 'na', 'n/a'], np.nan)
                
                # 处理可能包含的千分位分隔符和不同的小数点符号
                if df_processed[col].dtype == 'object':
                    df_processed[col] = df_processed[col].astype(str)
                    df_processed[col] = df_processed[col].str.replace(',', '.')
                    
                # 转换为浮点数
                df_processed[col] = pd.to_numeric(df_processed[col], errors='coerce')
            except:
                pass  # 无法转换的列保持原样
    
    # 3. 检测和处理异常值（用于数值列）
    numeric_cols = df_processed.select_dtypes(include=['number']).columns
    
    for col in numeric_cols:
        # 跳过可能的ID或分类列
        if df_processed[col].nunique() < 10 or col in ['id', 'year', 'month', 'day']:
            continue
            
        # 使用IQR方法检测异常值
        Q1 = df_processed[col].quantile(0.25)
        Q3 = df_processed[col].quantile(0.75)
        IQR = Q3 - Q1
        
        # 设置宽松的边界以避免过度过滤
        lower_bound = Q1 - 3 * IQR
        upper_bound = Q3 + 3 * IQR
        
        # 标记异常值为NaN
        extreme_mask = (df_processed[col] < lower_bound) | (df_processed[col] > upper_bound)
        extreme_count = extreme_mask.sum()
        
        if extreme_count > 0 and extreme_count < len(df_processed) * 0.1:  # 限制异常值比例
            df_processed.loc[extreme_mask, col] = np.nan
            logger.info(f"列 {col} 中检测到 {extreme_count} 个异常值并替换为NaN")
    
    # 4. 处理峰面积/浓度列，转换为相对百分比
    # 检测可能的峰面积或浓度列
    area_columns = []
    for col in df_processed.columns:
        col_str = str(col).lower()
        if any(term in col_str for term in ['area', 'intensity', 'peak', 'abundance', 'concentration', 'content']):
            if 'c1' in col_str or 'ch4' in col_str or 'methane' in col_str:
                area_columns.append((col, 'C1'))
            elif 'c2' in col_str or 'c2h6' in col_str or 'ethane' in col_str:
                area_columns.append((col, 'C2'))
            elif 'c3' in col_str or 'c3h8' in col_str or 'propane' in col_str:
                area_columns.append((col, 'C3'))
            elif 'ic4' in col_str or 'i-c4' in col_str:
                area_columns.append((col, 'iC4'))
            elif 'nc4' in col_str or 'n-c4' in col_str:
                area_columns.append((col, 'nC4'))
            elif 'c4' in col_str or 'butane' in col_str:
                area_columns.append((col, 'C4'))
            elif 'ic5' in col_str or 'i-c5' in col_str:
                area_columns.append((col, 'iC5'))
            elif 'nc5' in col_str or 'n-c5' in col_str:
                area_columns.append((col, 'nC5'))
            elif 'c5' in col_str or 'pentane' in col_str:
                area_columns.append((col, 'C5'))
    
    # 如果检测到峰面积列，转换为相对百分比
    if area_columns:
        # 计算总峰面积
        peak_cols = [col for col, _ in area_columns]
        df_processed['total_peak'] = df_processed[peak_cols].sum(axis=1)
        
        # 转换为相对百分比
        for col, component in area_columns:
            df_processed[f'{component}_rel'] = df_processed[col] / df_processed['total_peak'] * 100
    
    # 5. 如果存在深度列，按深度排序
    depth_col = None
    for col in df_processed.columns:
        col_str = str(col).lower()
        if 'depth' in col_str or 'tiefe' in col_str or 'profundidad' in col_str:
            depth_col = col
            break
    
    if depth_col:
        df_processed = df_processed.sort_values(by=depth_col)
    
    return df_processed

def create_depth_segments(
    df: pd.DataFrame, 
    depth_col: str, 
    value_col: str, 
    segment_method: str = "equal", 
    num_segments: int = 5,
    min_segment_size: int = 3,
    change_point_sensitivity: float = 0.05,
    penalties: Any = [10, 20, 50, 100, 200, 500, 1000]
) -> List[Tuple[float, float]]:
    """
    基于深度列创建数据分段，使用改进的算法处理不同噪声和趋势情况
    
    Args:
        df: 输入的数据框
        depth_col: 深度列的名称
        value_col: 用于分段的值列的名称
        segment_method: 分段方法，可选值: "equal"(等距), "kmeans"(聚类), "change_point"(变化点)
        num_segments: 期望的分段数量
        min_segment_size: 每个分段的最小数据点数量
        change_point_sensitivity: 变化点检测的敏感度(仅用于change_point方法)
        penalties: 变点检测算法惩罚值列表
        
    Returns:
        分段列表，每个元素为(start_depth, end_depth)元组
    """
    # 确保深度列和值列存在
    if depth_col not in df.columns:
        logger.error(f"深度列 {depth_col} 不存在于数据框中")
        return [(df[depth_col].min(), df[depth_col].max())]
        
    if value_col not in df.columns:
        logger.error(f"值列 {value_col} 不存在于数据框中")
        return [(df[depth_col].min(), df[depth_col].max())]
    
    # 提取有效数据(同时有深度和值的行)
    valid_mask = ~df[depth_col].isna() & ~df[value_col].isna()
    valid_data = df.loc[valid_mask, [depth_col, value_col]].copy()
    
    # 数据点太少，返回单一分段
    if len(valid_data) < min_segment_size * 2:
        return [(df[depth_col].min(), df[depth_col].max())]
    
    # 按深度排序
    valid_data = valid_data.sort_values(by=depth_col)
    
    # 调整分段数量，避免分段过多
    adjusted_num_segments = min(num_segments, len(valid_data) // min_segment_size)
    if adjusted_num_segments < 2:
        return [(valid_data[depth_col].min(), valid_data[depth_col].max())]
    
    segments = []
    
    # 基于选择的方法创建分段
    if segment_method == "equal":
        # 等深度间隔分段
        depth_min = valid_data[depth_col].min()
        depth_max = valid_data[depth_col].max()
        depth_range = depth_max - depth_min
        
        segment_size = depth_range / adjusted_num_segments
        
        for i in range(adjusted_num_segments):
            start = depth_min + i * segment_size
            end = depth_min + (i + 1) * segment_size
            
            # 调整最后一个分段的结束深度
            if i == adjusted_num_segments - 1:
                end = depth_max
                
            segments.append((start, end))
            
    elif segment_method == "kmeans":
        # 基于K均值聚类的分段
        try:
            from sklearn.cluster import KMeans
            
            # 对深度值进行K均值聚类
            X = valid_data[depth_col].values.reshape(-1, 1)
            kmeans = KMeans(n_clusters=adjusted_num_segments, random_state=42)
            labels = kmeans.fit_predict(X)
            
            # 为每个聚类计算深度范围
            for i in range(adjusted_num_segments):
                cluster_depths = valid_data.loc[labels == i, depth_col]
                
                if len(cluster_depths) >= min_segment_size:
                    segments.append((cluster_depths.min(), cluster_depths.max()))
            
            # 按深度排序分段
            segments.sort(key=lambda x: x[0])
            
        except ImportError:
            logger.warning("未安装sklearn，无法使用kmeans分段方法。使用equal方法代替。")
            return create_depth_segments(df, depth_col, value_col, "equal", num_segments, min_segment_size)
            
    elif segment_method == "change_point":
        # 基于变化点检测的分段
        try:
            # 增强版变化点检测
            change_points = detect_change_points(
                valid_data[depth_col].values, 
                valid_data[value_col].values,
                sensitivity=change_point_sensitivity,
                min_size=min_segment_size,
                target_segments=adjusted_num_segments,
                penalties=penalties
            )
            
            # 如果检测到的变化点太少，使用等距分段
            if len(change_points) < 2:
                return create_depth_segments(df, depth_col, value_col, "equal", num_segments, min_segment_size)
            
            # 基于变化点创建分段
            depths = valid_data[depth_col].values
            indices = np.arange(len(depths))
            
            for i in range(len(change_points) - 1):
                start_idx = change_points[i]
                end_idx = change_points[i + 1] - 1  # 减1避免重叠
                
                # 确保索引在有效范围内
                start_idx = max(0, min(start_idx, len(indices) - 1))
                end_idx = max(0, min(end_idx, len(indices) - 1))
                
                # 将索引转换为实际深度
                start_depth = depths[start_idx] if start_idx < len(depths) else depths[0]
                end_depth = depths[end_idx] if end_idx < len(depths) else depths[-1]
                
                segments.append((start_depth, end_depth))
                
        except Exception as e:
            logger.warning(f"变化点检测失败: {str(e)}。使用equal方法代替。")
            return create_depth_segments(df, depth_col, value_col, "equal", num_segments, min_segment_size)
    else:
        logger.warning(f"未知的分段方法: {segment_method}。使用equal方法代替。")
        return create_depth_segments(df, depth_col, value_col, "equal", num_segments, min_segment_size)
    
    # 确保分段连续性(避免分段间的间隙)
    if len(segments) >= 2:
        continuous_segments = [segments[0]]
        
        for i in range(1, len(segments)):
            prev_end = continuous_segments[-1][1]
            curr_start = segments[i][0]
            
            # 如果存在间隙，调整前一个分段的结束深度
            if prev_end < curr_start:
                continuous_segments[-1] = (continuous_segments[-1][0], curr_start)
                
            continuous_segments.append(segments[i])
            
        segments = continuous_segments
    
    # 如果分段数量与期望不符，尝试调整
    if len(segments) > adjusted_num_segments:
        # 合并最小的相邻分段
        while len(segments) > adjusted_num_segments:
            # 计算每个分段的大小
            segment_sizes = [end - start for start, end in segments]
            
            # 找到最小的相邻分段
            min_size = float('inf')
            merge_idx = -1
            
            for i in range(len(segments) - 1):
                combined_size = segment_sizes[i] + segment_sizes[i + 1]
                if combined_size < min_size:
                    min_size = combined_size
                    merge_idx = i
            
            # 合并分段
            if merge_idx >= 0:
                segments[merge_idx] = (segments[merge_idx][0], segments[merge_idx + 1][1])
                segments.pop(merge_idx + 1)
            else:
                break
    
    # 确保分段数量不为0
    if not segments:
        segments = [(valid_data[depth_col].min(), valid_data[depth_col].max())]
    
    return segments

def detect_change_points(
    depths: np.ndarray, 
    values: np.ndarray,
    sensitivity: float = 0.05,
    min_size: int = 3,
    target_segments: int = 3,
    penalties: Any = [10, 20, 50, 100, 200, 500, 1000]
) -> List[int]:
    """
    检测值序列中的变化点，使用改进的算法处理不同噪声情况
    
    Args:
        depths: 深度数组
        values: 值数组
        sensitivity: 敏感度参数，值越小检测到的变化点越多
        min_size: 分段的最小大小
        target_segments: 目标段落数量
        penalties: 变点检测算法惩罚值列表
        
    Returns:
        变化点索引列表，包括起始点和结束点
    """
    n = len(depths)
    
    # 数据点太少，返回起始和结束点
    if n < min_size * 2:
        return [0, n]
    
    # 确保penalties是列表类型
    if not isinstance(penalties, (list, tuple, np.ndarray)):
        if isinstance(penalties, str):
            # 如果是字符串，尝试解析
            try:
                penalties = [int(p.strip()) for p in penalties.split(",") if p.strip().isdigit()]
                if not penalties:
                    penalties = [10, 20, 50, 100, 200, 500, 1000]  # 默认值
            except:
                penalties = [10, 20, 50, 100, 200, 500, 1000]  # 默认值
        else:
            # 如果是其他类型，使用默认值
            penalties = [10, 20, 50, 100, 200, 500, 1000]
    
    # 按深度排序数据
    sorted_indices = np.argsort(depths)
    sorted_depths = depths[sorted_indices]
    sorted_values = values[sorted_indices]
    
    # 增大默认平滑窗口，更好地滤除噪声
    # 根据数据点数量自适应调整平滑窗口大小
    min_smoothing = 5
    adaptive_window = max(min_smoothing, int(n * 0.05))  # 使用数据点5%作为窗口大小
    smoothing_window = max(min_smoothing, adaptive_window)
    
    # 应用平滑处理减少噪声
    if n >= smoothing_window * 2:
        try:
            # 尝试应用Savitzky-Golay滤波
            # 确保平滑窗口为奇数
            if smoothing_window % 2 == 0:
                smoothing_window += 1
            # Savitzky-Golay滤波，比简单移动平均保留更多原始特征
            smoothed_values = signal.savgol_filter(sorted_values, smoothing_window, 2)
        except:
            # 如果失败，使用简单的滑动平均
            smoothed_values = np.convolve(sorted_values, 
                                         np.ones(smoothing_window)/smoothing_window, 
                                         mode='valid')
            # 调整深度数组以匹配平滑后的同位素值数组长度
            offset = (smoothing_window - 1) // 2
            sorted_depths = sorted_depths[offset:offset+len(smoothed_values)]
            sorted_indices = sorted_indices[offset:offset+len(smoothed_values)]
    else:
        # 数据点不足以应用平滑，使用原始值
        smoothed_values = sorted_values
    
    # 估计噪声水平
    try:
        # 计算线性趋势
        slope, intercept, r_value, p_value, std_err = stats.linregress(sorted_depths, smoothed_values)
        trend_line = slope * sorted_depths + intercept
        residuals = smoothed_values - trend_line
        noise_level = np.std(residuals)
    except:
        # 简单估计
        noise_level = np.std(smoothed_values) / 2
    
    # 识别变点
    change_points = []
    
    try:
        # 尝试使用ruptures包进行变点检测（如果可用）
        
        # 准备数据
        signal = smoothed_values.reshape(-1, 1)
        
        # 使用基于惩罚的方法，手动尝试多个惩罚值找到合适的分段数
        algo = rpt.Pelt(model="rbf").fit(signal)
        
        # 使用用户指定的惩罚值列表
        for penalty in penalties:
            result = algo.predict(pen=penalty)
            # 结果是索引列表，最后一个是序列结尾
            tmp_change_points = result[:-1]
            
            # 如果变点数量接近目标，则选择当前惩罚值
            if len(tmp_change_points) <= target_segments + 1:
                change_points = tmp_change_points
                break
        
        # 兜底：如果所有惩罚值都不能产生足够少的变点，取最后一个结果
        if not change_points and tmp_change_points:
            change_points = tmp_change_points
            
    except Exception as e:
        logger.warning(f"PELT变点检测失败: {str(e)}，尝试基于方差变化的检测")
        # 如果ruptures不可用或失败，尝试基于方差变化进行检测
        try:
            # 计算移动方差
            window = max(20, len(smoothed_values) // 20)  # 使用较大窗口
            var_values = []
            
            for i in range(window, len(smoothed_values) - window):
                left_var = np.var(smoothed_values[i-window:i])
                right_var = np.var(smoothed_values[i:i+window])
                var_change = abs(right_var - left_var) / max(left_var, right_var, 1e-10)
                var_values.append((i, var_change))
            
            # 找出方差变化最大的几个点
            var_values.sort(key=lambda x: x[1], reverse=True)
            top_changes = var_values[:target_segments]
            change_points = [pos for pos, _ in sorted(top_changes)]
            
        except Exception as e:
            logger.warning(f"方差变化检测失败: {str(e)}，使用简单分段")
            # 如果方差分析失败，使用简单分段
            # 将数据简单地分为用户指定段数
            if len(smoothed_values) > 100:
                segment_size = len(smoothed_values) // target_segments
                change_points = [segment_size * i for i in range(1, target_segments)]
            else:
                mid_point = len(smoothed_values) // 2
                change_points = [mid_point]
    
    # 筛选变点，确保分段大小不小于最小值
    if change_points:
        filtered_points = [0]  # 总是包含起始点
        for cp in sorted(change_points):
            if cp - filtered_points[-1] >= min_size:
                filtered_points.append(cp)
        
        # 确保包含结束点
        if filtered_points[-1] != len(smoothed_values):
            filtered_points.append(len(smoothed_values))
            
        # 将变点位置映射回原始索引
        original_points = [sorted_indices[cp] for cp in filtered_points if cp < len(sorted_indices)]
        
        # 处理末尾点
        if filtered_points[-1] >= len(sorted_indices):
            original_points.append(n)
        
        return sorted(original_points)
    
    # 如果没有找到变点，根据数据长度均匀划分
    if n > 200 and target_segments > 1:
        points = [0]  # 起始点
        for i in range(1, target_segments):
            points.append(i * n // target_segments)
        points.append(n)  # 结束点
        return points
    else:
        # 简单地返回起始和结束点
        return [0, n]

def extract_isotope_features(
    df: pd.DataFrame, 
    isotope_columns: Dict[str, List[str]], 
    depth_col: Optional[str] = None,
    segments: Optional[List[Tuple[float, float]]] = None
) -> Dict[str, Any]:
    """
    从碳同位素数据中提取特征
    
    Args:
        df: 输入的数据框
        isotope_columns: 同位素列的映射字典 {组分:列名列表}
        depth_col: 深度列的名称(可选)
        segments: 深度分段列表(可选)，每个元素为(start_depth, end_depth)元组
        
    Returns:
        提取的特征字典
    """
    features = {}
    
    # 1. 提取基本统计特征
    for component, cols in isotope_columns.items():
        if cols:  # 确保组分有对应的列
            col = cols[0]  # 使用第一个匹配列
            
            if col in df.columns:
                valid_values = df[col].dropna().values
                
                if len(valid_values) > 0:
                    features[f"mean_{component.lower()}_d13c"] = float(np.mean(valid_values))
                    features[f"std_{component.lower()}_d13c"] = float(np.std(valid_values))
                    features[f"min_{component.lower()}_d13c"] = float(np.min(valid_values))
                    features[f"max_{component.lower()}_d13c"] = float(np.max(valid_values))
                    features[f"range_{component.lower()}_d13c"] = float(np.max(valid_values) - np.min(valid_values))
                    features[f"count_{component.lower()}_d13c"] = int(len(valid_values))
    
    # 2. 检测碳同位素倒转
    has_reversal = False
    reversal_components = []
    
    # 检查C1-C2倒转
    if "mean_c1_d13c" in features and "mean_c2_d13c" in features:
        if features["mean_c1_d13c"] > features["mean_c2_d13c"]:
            has_reversal = True
            reversal_components.append("C1-C2")
    
    # 检查C2-C3倒转
    if "mean_c2_d13c" in features and "mean_c3_d13c" in features:
        if features["mean_c2_d13c"] > features["mean_c3_d13c"]:
            has_reversal = True
            reversal_components.append("C2-C3")
    
    features["has_isotope_reversal"] = has_reversal
    if reversal_components:
        features["reversal_components"] = reversal_components
    
    # 3. 计算同位素差值特征
    if "mean_c1_d13c" in features and "mean_c2_d13c" in features:
        features["c1_c2_diff"] = features["mean_c2_d13c"] - features["mean_c1_d13c"]
    
    if "mean_c2_d13c" in features and "mean_c3_d13c" in features:
        features["c2_c3_diff"] = features["mean_c3_d13c"] - features["mean_c2_d13c"]
    
    # 4. 计算组分比例特征
    # 检查是否有组分浓度或峰面积相对比例
    c1_rel = next((col for col in df.columns if "c1_rel" in str(col).lower()), None)
    c2_rel = next((col for col in df.columns if "c2_rel" in str(col).lower()), None)
    c3_rel = next((col for col in df.columns if "c3_rel" in str(col).lower()), None)
    
    if c1_rel and c2_rel:
        features["mean_c1_c2_ratio"] = float(df[c1_rel].mean() / max(0.001, df[c2_rel].mean()))
    
    if c1_rel and c2_rel and c3_rel:
        c2c3_sum = df[c2_rel] + df[c3_rel]
        c1_c2c3_ratio = df[c1_rel] / c2c3_sum.replace(0, np.nan)
        features["mean_c1_c2c3_ratio"] = float(c1_c2c3_ratio.dropna().mean())
    
    # 5. 如果提供了深度列，添加深度相关特征
    if depth_col and depth_col in df.columns:
        # 检查深度差异
        depth_values = df[depth_col].dropna().values
        
        if len(depth_values) > 1:
            features["depth_min"] = float(np.min(depth_values))
            features["depth_max"] = float(np.max(depth_values))
            features["depth_range"] = float(np.max(depth_values) - np.min(depth_values))
        
        # 检查是否有深度趋势
        if "C1" in isotope_columns and isotope_columns["C1"]:
            c1_col = isotope_columns["C1"][0]
            valid_mask = ~df[depth_col].isna() & ~df[c1_col].isna()
            
            if valid_mask.sum() >= 3:  # 至少需要3个点才能计算趋势
                # 计算简单线性回归
                slope, intercept, r_value, p_value, std_err = stats.linregress(
                    df.loc[valid_mask, depth_col],
                    df.loc[valid_mask, c1_col]
                )
                
                features["c1_depth_slope"] = float(slope)
                features["c1_depth_r_value"] = float(r_value)
                features["c1_depth_p_value"] = float(p_value)
    
    # 6. 如果提供了分段，计算分段内差异
    if segments and depth_col and depth_col in df.columns:
        segment_diffs = []
        
        # 检查主要同位素组分(C1)在不同分段的差异
        if "C1" in isotope_columns and isotope_columns["C1"]:
            c1_col = isotope_columns["C1"][0]
            segment_means = []
            
            for start, end in segments:
                segment_df = df[(df[depth_col] >= start) & (df[depth_col] <= end)]
                
                if len(segment_df) >= 3:  # 确保段内有足够的样本
                    segment_mean = segment_df[c1_col].mean()
                    segment_means.append(segment_mean)
            
            # 计算分段间最大差异
            if len(segment_means) >= 2:
                features["c1_segment_max_diff"] = float(max(segment_means) - min(segment_means))
                
                # 检测是否有一致的趋势
                increasing = True
                decreasing = True
                
                for i in range(1, len(segment_means)):
                    if segment_means[i] <= segment_means[i-1]:
                        increasing = False
                    if segment_means[i] >= segment_means[i-1]:
                        decreasing = False
                
                features["c1_consistent_trend"] = increasing or decreasing
                features["c1_trend_direction"] = "increasing" if increasing else "decreasing" if decreasing else "mixed"
    
    return features

def generate_isotope_description(features: Dict[str, Any], analysis_type: str = "general") -> str:
    """生成碳同位素特征描述文本
    
    Args:
        features: 特征字典
        analysis_type: 分析类型
        
    Returns:
        描述文本
    """
    description = []
    
    # 总体描述
    description.append(f"## 碳同位素数据总体特征")
    
    # 甲烷碳同位素描述
    if "C1_mean" in features:
        c1_mean = features["C1_mean"]
        c1_min = features["C1_min"]
        c1_max = features["C1_max"]
        c1_range = c1_max - c1_min
        
        description.append(f"- 甲烷碳同位素(δ13C-CH4)平均值为{c1_mean:.2f}‰，变化范围{c1_range:.2f}‰（{c1_min:.2f}‰到{c1_max:.2f}‰）")
        
        # 气源初步判断
        if c1_mean < -60:
            description.append("- 甲烷碳同位素值总体较轻，指示可能以生物成因气为主")
        elif -60 <= c1_mean < -50:
            description.append("- 甲烷碳同位素值处于中等范围，可能为混合成因气或低熟热成因气")
        elif -50 <= c1_mean < -35:
            description.append("- 甲烷碳同位素值总体偏重，指示可能以热成因气为主")
        else:
            description.append("- 甲烷碳同位素值非常重，指示可能为高熟热成因气或经历过二次改造")
    
    # 乙烷和丙烷碳同位素描述
    if "C2_mean" in features:
        c2_mean = features["C2_mean"]
        description.append(f"- 乙烷碳同位素(δ13C-C2H6)平均值为{c2_mean:.2f}‰")
    
    if "C3_mean" in features:
        c3_mean = features["C3_mean"]
        description.append(f"- 丙烷碳同位素(δ13C-C3H8)平均值为{c3_mean:.2f}‰")
    
    # 碳同位素差值描述
    if "C1_C2_diff" in features:
        c1_c2_diff = features["C1_C2_diff"]
        if c1_c2_diff < 0:
            description.append(f"- 存在碳同位素倒转现象(δ13C-CH4 > δ13C-C2H6)，差值为{c1_c2_diff:.2f}‰，可能指示生物降解或混合成因")
        elif 0 <= c1_c2_diff < 10:
            description.append(f"- C1-C2同位素差值较小({c1_c2_diff:.2f}‰)，可能指示高成熟度气源")
        elif 10 <= c1_c2_diff < 15:
            description.append(f"- C1-C2同位素差值适中({c1_c2_diff:.2f}‰)，符合典型热成因气特征")
        else:
            description.append(f"- C1-C2同位素差值较大({c1_c2_diff:.2f}‰)，可能指示低成熟度气源")
    
    # 深度趋势描述
    if "C1_depth_trend" in features:
        c1_trend = features["C1_depth_trend"]
        c1_trend_sig = features.get("C1_trend_significance", False)
        
        trend_desc = ""
        if c1_trend > 0.5:
            trend_desc = "明显变重趋势"
        elif c1_trend > 0.3:
            trend_desc = "轻微变重趋势"
        elif c1_trend < -0.5:
            trend_desc = "明显变轻趋势"
        elif c1_trend < -0.3:
            trend_desc = "轻微变轻趋势"
        else:
            trend_desc = "无明显变化趋势"
            
        significance = "（统计显著）" if c1_trend_sig else "（统计不显著）"
        description.append(f"- 甲烷碳同位素值随深度增加呈{trend_desc}{significance}，相关系数为{c1_trend:.2f}")
        
        if c1_trend > 0.3:
            description.append("  - 碳同位素值随深度变重符合正常热演化规律")
        elif c1_trend < -0.3:
            description.append("  - 碳同位素值随深度变轻可能存在深部生物气或气体混合现象")
    
    # 分段描述
    if "segments" in features:
        description.append("\n## 分段特征描述")
        
        for segment in features["segments"]:
            segment_id = segment["segment_id"]
            start = segment["depth_start"]
            end = segment["depth_end"]
            description.append(f"\n### 深度段 {segment_id}: {start:.2f}-{end:.2f}米")
            
            # 每段甲烷特征
            if "C1_mean" in segment:
                c1_mean = segment["C1_mean"]
                description.append(f"- 甲烷碳同位素平均值: {c1_mean:.2f}‰")
                
                # 气源判断
                if c1_mean < -60:
                    description.append("  - 该段甲烷碳同位素较轻，指示可能为生物成因气")
                elif -60 <= c1_mean < -50:
                    description.append("  - 该段甲烷碳同位素值中等，可能为混合成因气或低熟热成因气")
                elif -50 <= c1_mean < -35:
                    description.append("  - 该段甲烷碳同位素较重，指示可能为热成因气")
                else:
                    description.append("  - 该段甲烷碳同位素非常重，指示可能为高熟热成因气")
                
                if "C1_trend" in segment:
                    c1_trend = segment["C1_trend"]
                    c1_trend_sig = segment.get("C1_trend_significance", False)
                    
                    if abs(c1_trend) > 0.3:
                        trend_dir = "变重" if c1_trend > 0 else "变轻"
                        sig_text = "显著" if c1_trend_sig else "不显著"
                        description.append(f"  - 本段内甲烷碳同位素呈{trend_dir}趋势(r={c1_trend:.2f})，统计{sig_text}")
                    else:
                        description.append(f"  - 本段内甲烷碳同位素相对稳定(r={c1_trend:.2f})")
            
            # 乙烷、丙烷特征
            if "C2_mean" in segment:
                c2_mean = segment["C2_mean"]
                description.append(f"- 乙烷碳同位素平均值: {c2_mean:.2f}‰")
            
            if "C3_mean" in segment:
                c3_mean = segment["C3_mean"]
                description.append(f"- 丙烷碳同位素平均值: {c3_mean:.2f}‰")
            
            # C1-C2差值特征
            if "c1_c2_diff" in segment:
                c1_c2_diff = segment["c1_c2_diff"]
                description.append(f"- C1-C2同位素差值: {c1_c2_diff:.2f}‰")
                
                if c1_c2_diff < 0:
                    description.append("  - 存在碳同位素倒转现象，可能指示生物降解或混合成因")
                elif 0 <= c1_c2_diff < 10:
                    description.append("  - C1-C2同位素差值较小，可能指示高成熟度气源")
                elif 10 <= c1_c2_diff < 15:
                    description.append("  - C1-C2同位素差值适中，符合典型热成因气特征")
                else:
                    description.append("  - C1-C2同位素差值较大，可能指示低成熟度气源")
    
    # 根据分析类型生成专门描述
    if analysis_type == "gas_source":
        description.append("\n## 气源判别结论")
        # 根据特征生成气源判别结论
        c1_mean = features.get("C1_mean")
        c1_c2_diff = features.get("C1_C2_diff")
        reversal = features.get("carbon_isotope_reversal", False)
        
        if c1_mean is not None:
            if c1_mean < -60:
                description.append("- 主要气源类型: **生物成因气**")
                description.append("  - 甲烷碳同位素值(<-60‰)落入典型生物成因气范围")
                if reversal:
                    description.append("  - 存在碳同位素倒转现象，可能混合有少量热解气或经历了微生物改造")
            elif -60 <= c1_mean < -50:
                if reversal:
                    description.append("- 主要气源类型: **混合成因气（生物+热解）**")
                    description.append("  - 甲烷碳同位素值(-60‰ ~ -50‰)处于生物气和热解气过渡区间")
                    description.append("  - 碳同位素倒转现象支持混合成因判断")
                else:
                    description.append("- 主要气源类型: **混合成因气或低熟热解气**")
                    description.append("  - 甲烷碳同位素值(-60‰ ~ -50‰)处于生物气和热解气过渡区间")
            elif -50 <= c1_mean < -35:
                description.append("- 主要气源类型: **热成因气**")
                description.append("  - 甲烷碳同位素值(-50‰ ~ -35‰)落入典型热成因气范围")
                if c1_c2_diff is not None:
                    if c1_c2_diff > 15:
                        description.append("  - C1-C2同位素差值较大，指示低-中熟热成因气")
                    elif 10 <= c1_c2_diff <= 15:
                        description.append("  - C1-C2同位素差值适中，指示中熟热成因气")
                    elif 0 <= c1_c2_diff < 10:
                        description.append("  - C1-C2同位素差值较小，指示高熟热成因气")
            else:
                description.append("- 主要气源类型: **高熟热成因气**")
                description.append("  - 甲烷碳同位素值(>-35‰)指示高熟气或经历了次生改造的气体")
                
    elif analysis_type == "maturity":
        description.append("\n## 成熟度分析结论")
        # 根据特征生成成熟度分析结论
        c1_mean = features.get("C1_mean")
        c1_c2_diff = features.get("C1_C2_diff")
        
        if c1_mean is not None and c1_c2_diff is not None and c1_c2_diff >= 0:
            if c1_mean < -50:
                description.append("- 成熟度评价: **低成熟**")
                description.append("  - 甲烷碳同位素值较轻，指示低成熟气体")
            elif -50 <= c1_mean < -40:
                description.append("- 成熟度评价: **中等成熟**")
                description.append("  - 甲烷碳同位素值适中，指示中等成熟气体")
            elif -40 <= c1_mean < -35:
                description.append("- 成熟度评价: **高成熟**")
                description.append("  - 甲烷碳同位素值较重，指示高成熟气体")
            else:
                description.append("- 成熟度评价: **过成熟**")
                description.append("  - 甲烷碳同位素值非常重，指示过成熟气体")
            
            if c1_c2_diff > 15:
                description.append("- C1-C2差值较大，进一步支持低成熟判断")
            elif 10 <= c1_c2_diff <= 15:
                description.append("- C1-C2差值适中，符合中等成熟气体特征")
            elif 0 <= c1_c2_diff < 10:
                description.append("- C1-C2差值较小，进一步支持高成熟判断")
        else:
            description.append("- 成熟度评价: **无法确定**")
            description.append("  - 数据不足或存在碳同位素倒转现象，不适用于常规成熟度评价")
    
    return "\n".join(description) 