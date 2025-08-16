"""
全烃TG评价油气水层工具

该工具基于全烃含量（TG）进行油气水层评价，综合考虑：
1. TG绝对值大小
2. 相对于背景值的异常倍数  
3. 随深度的变化趋势
4. 异常的连续性和厚度

评价标准：
层型         TG绝对值    相对异常倍数    趋势特征              连续性
水层         < 2%       < 2倍背景值     平稳，无明显变化       -
弱显示层     2-5%       2-3倍背景值     轻微上升              ≥ 0.5m
油层         5-15%      3-8倍背景值     持续上升或稳定高值     ≥ 1.0m  
气层         15-30%     8-20倍背景值    快速上升，峰值明显     ≥ 0.5m
强气层       > 30%      > 20倍背景值    急剧上升，极高峰值     ≥ 0.5m
"""

import os
import logging
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats
from scipy.ndimage import uniform_filter1d
from typing import Dict, List, Optional, Union, Any, Tuple
import io
import base64
from pathlib import Path
import uuid
import platform

from app.core.file_manager import file_manager
from app.tools.registry import register_tool
from langgraph.config import get_stream_writer

# 配置日志
logger = logging.getLogger(__name__)

# 配置中文字体
def setup_chinese_font():
    """设置中文字体"""
    try:
        if platform.system() == 'Windows':
            plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
        elif platform.system() == 'Darwin':  # macOS
            plt.rcParams['font.sans-serif'] = ['Hei', 'Arial Unicode MS']
        else:  # Linux
            plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'SimHei']
        plt.rcParams['axes.unicode_minus'] = False
    except Exception as e:
        logger.warning(f"设置中文字体失败: {e}")

def calculate_background_tg(tg_values: np.ndarray, window_size: int = 10) -> np.ndarray:
    """计算TG背景值
    
    使用移动窗口的中位数来计算背景值，避免异常高值的影响
    
    Args:
        tg_values: TG值数组
        window_size: 移动窗口大小
        
    Returns:
        背景TG值数组
    """
    # 使用滚动中位数计算背景值
    background = np.zeros_like(tg_values)
    half_window = window_size // 2
    
    for i in range(len(tg_values)):
        start_idx = max(0, i - half_window)
        end_idx = min(len(tg_values), i + half_window + 1)
        window_data = tg_values[start_idx:end_idx]
        
        # 去除异常高值后计算中位数
        q75 = np.percentile(window_data, 75)
        q25 = np.percentile(window_data, 25)
        iqr = q75 - q25
        upper_bound = q75 + 1.5 * iqr
        
        # 只使用不超过上界的数据计算背景值
        filtered_data = window_data[window_data <= upper_bound]
        if len(filtered_data) > 0:
            background[i] = np.median(filtered_data)
        else:
            background[i] = np.median(window_data)
    
    return background

def calculate_tg_anomaly_ratio(tg_values: np.ndarray, background_values: np.ndarray) -> np.ndarray:
    """计算TG异常倍数
    
    Args:
        tg_values: TG值数组
        background_values: 背景TG值数组
        
    Returns:
        异常倍数数组
    """
    # 避免除零错误，设置最小背景值
    min_background = 0.1
    safe_background = np.maximum(background_values, min_background)
    
    anomaly_ratio = tg_values / safe_background
    return anomaly_ratio

def classify_layer_type(tg_value: float, anomaly_ratio: float, depth_trend: str = 'stable') -> Dict[str, str]:
    """根据TG值和异常倍数分类层型
    
    Args:
        tg_value: TG绝对值
        anomaly_ratio: 相对异常倍数
        depth_trend: 深度趋势 ('rising', 'stable', 'falling')
        
    Returns:
        包含分类结果的字典
    """
    if pd.isna(tg_value) or tg_value < 0:
        return {
            "layer_type": "无效数据",
            "confidence": "低",
            "description": "数据无效"
        }
    
    # 基于TG绝对值和异常倍数的分类
    if tg_value < 2 and anomaly_ratio < 2:
        layer_type = "水层"
        confidence = "高"
        description = "TG值低，无明显异常"
    elif 2 <= tg_value < 5 and 2 <= anomaly_ratio < 3:
        layer_type = "弱显示层"
        confidence = "中"
        description = "TG值轻微异常"
    elif 5 <= tg_value < 15 and 3 <= anomaly_ratio < 8:
        if depth_trend == 'rising':
            layer_type = "油层"
            confidence = "高"
            description = "TG值持续上升，油层特征明显"
        else:
            layer_type = "油层"
            confidence = "中"
            description = "TG值异常，可能为油层"
    elif 15 <= tg_value < 30 and 8 <= anomaly_ratio < 20:
        layer_type = "气层"
        confidence = "高"
        description = "TG值显著异常，气层特征明显"
    elif tg_value >= 30 and anomaly_ratio >= 20:
        layer_type = "强气层"
        confidence = "高"
        description = "TG值极高异常，强气层特征"
    else:
        # 边界情况的综合判断
        if tg_value >= 15:
            layer_type = "气层"
            confidence = "中"
            description = "TG值高，疑似气层"
        elif tg_value >= 5:
            layer_type = "油层"
            confidence = "中"
            description = "TG值中等异常，疑似油层"
        elif tg_value >= 2:
            layer_type = "弱显示层"
            confidence = "低"
            description = "TG值轻微异常"
        else:
            layer_type = "水层"
            confidence = "中"
            description = "TG值较低"
    
    return {
        "layer_type": layer_type,
        "confidence": confidence,
        "description": description
    }

def analyze_depth_trend(depths: np.ndarray, tg_values: np.ndarray, window_size: int = 5) -> np.ndarray:
    """分析TG值随深度的变化趋势
    
    Args:
        depths: 深度数组
        tg_values: TG值数组
        window_size: 趋势分析窗口大小
        
    Returns:
        趋势数组 ('rising', 'stable', 'falling')
    """
    trends = np.full(len(tg_values), 'stable', dtype=object)
    half_window = window_size // 2
    
    for i in range(len(tg_values)):
        start_idx = max(0, i - half_window)
        end_idx = min(len(tg_values), i + half_window + 1)
        
        if end_idx - start_idx >= 3:  # 至少需要3个点计算趋势
            window_depths = depths[start_idx:end_idx]
            window_tg = tg_values[start_idx:end_idx]
            
            # 计算线性回归斜率
            try:
                slope, _, r_value, _, _ = stats.linregress(window_depths, window_tg)
                
                # 根据斜率和相关性判断趋势
                if abs(r_value) > 0.5:  # 相关性足够强
                    if slope > 0.1:  # 斜率阈值可调整
                        trends[i] = 'rising'
                    elif slope < -0.1:
                        trends[i] = 'falling'
                    else:
                        trends[i] = 'stable'
                else:
                    trends[i] = 'stable'
            except:
                trends[i] = 'stable'
    
    return trends

def check_layer_continuity(layer_types: np.ndarray, depths: np.ndarray, min_thickness: float = 0.5) -> np.ndarray:
    """检查层型的连续性
    
    Args:
        layer_types: 层型数组
        depths: 深度数组
        min_thickness: 最小厚度要求
        
    Returns:
        连续性校正后的层型数组
    """
    corrected_types = layer_types.copy()
    
    # 对于非水层的类型，检查连续性
    for layer_type in ['弱显示层', '油层', '气层', '强气层']:
        # 找到该类型的所有位置
        type_mask = layer_types == layer_type
        
        if not np.any(type_mask):
            continue
        
        # 找到连续段
        diff = np.diff(np.concatenate(([False], type_mask, [False])).astype(int))
        starts = np.where(diff == 1)[0]
        ends = np.where(diff == -1)[0]
        
        for start, end in zip(starts, ends):
            segment_thickness = depths[end-1] - depths[start]
            
            # 根据层型要求的最小厚度进行判断
            required_thickness = min_thickness
            if layer_type == '油层':
                required_thickness = 1.0  # 油层要求更厚的连续性
            
            if segment_thickness < required_thickness:
                # 厚度不足，降级处理
                if layer_type in ['气层', '强气层']:
                    corrected_types[start:end] = '弱显示层'
                elif layer_type == '油层':
                    corrected_types[start:end] = '弱显示层'
                else:
                    corrected_types[start:end] = '水层'
    
    return corrected_types

def create_tg_evaluation_visualization(df: pd.DataFrame, output_path: str) -> str:
    """创建TG评价可视化图表
    
    Args:
        df: 包含TG评价结果的数据框
        output_path: 输出图片路径
        
    Returns:
        图片文件路径
    """
    try:
        # 设置matplotlib使用Agg后端，避免显示问题
        import matplotlib
        matplotlib.use('Agg')
        
        setup_chinese_font()
        
        # 清理所有matplotlib状态
        plt.clf()
        plt.close('all')
        
        # 记录原始数据信息
        logger.info(f"开始创建TG可视化图表")
        logger.info(f"原始数据行数: {len(df)}, 列名: {list(df.columns)}")
        
        # 数据预处理
        logger.info("开始数据预处理...")
        depths = pd.to_numeric(df['Depth'], errors='coerce') if 'Depth' in df.columns else None
        tg_values = pd.to_numeric(df['Tg'], errors='coerce') if 'Tg' in df.columns else None
        background_values = pd.to_numeric(df['TG背景值'], errors='coerce') if 'TG背景值' in df.columns else None
        anomaly_ratios = pd.to_numeric(df['异常倍数'], errors='coerce') if '异常倍数' in df.columns else None
        
        # 过滤有效数据
        if depths is not None and tg_values is not None:
            valid_mask = pd.notna(tg_values) & pd.notna(depths) & (tg_values >= 0) & (depths > 0)
            valid_depths = depths[valid_mask]
            valid_tg = tg_values[valid_mask]
            valid_background = background_values[valid_mask] if background_values is not None else None
            valid_anomaly = anomaly_ratios[valid_mask] if anomaly_ratios is not None else None
            
            logger.info(f"有效数据点数: {len(valid_depths)}")
            logger.info(f"深度范围: {valid_depths.min():.1f} - {valid_depths.max():.1f} m")
            logger.info(f"TG值范围: {valid_tg.min():.3f} - {valid_tg.max():.3f} %")
            logger.info(f"非零TG值数量: {(valid_tg > 0).sum()}")
        else:
            logger.error("缺少深度或TG数据，无法创建图表")
            return ""
        
        # 创建子图
        logger.info("创建子图...")
        ax1 = plt.subplot(2, 2, 1)
        ax2 = plt.subplot(2, 2, 2)
        ax3 = plt.subplot(2, 2, 3)
        ax4 = plt.subplot(2, 2, 4)
        
        # 图1：TG值深度剖面图
        logger.info("绘制图1：TG值深度剖面图")
        try:
            ax1.plot(valid_tg, valid_depths, linewidth=1, label='TG实测值', color='blue')
            if valid_background is not None and len(valid_background) > 0:
                ax1.plot(valid_background, valid_depths, linewidth=1, label='TG背景值', color='red', linestyle='--')
                # 填充异常区
                anomaly_mask = valid_tg > valid_background
                if anomaly_mask.any():
                    ax1.fill_betweenx(valid_depths, valid_background, valid_tg, 
                                     where=anomaly_mask, alpha=0.3, color='orange', label='异常区')
            
            ax1.invert_yaxis()
            ax1.set_xlabel('TG值 (%)', fontsize=12, color='black')
            ax1.set_ylabel('深度 (m)', fontsize=12, color='black')
            ax1.set_title('TG值深度剖面图', fontsize=14, fontweight='bold', color='black')
            ax1.legend(fontsize=10)
            ax1.grid(True, alpha=0.3)
            ax1.set_facecolor('white')
            
            # 设置X轴范围
            tg_max = valid_tg.max()
            ax1.set_xlim(0, max(5, tg_max + 1))
            
            # 添加参考线
            for threshold in [2, 5, 15]:
                if threshold <= ax1.get_xlim()[1]:
                    ax1.axvline(x=threshold, color='red', linestyle=':', alpha=0.7, linewidth=1)
            
            logger.info(f"图1绘制完成，数据点数: {len(valid_tg)}")
        except Exception as e:
            logger.error(f"绘制图1失败: {e}")
            ax1.text(0.5, 0.5, f'图1绘制失败: {str(e)}', transform=ax1.transAxes, 
                    ha='center', va='center', fontsize=12, color='red')
        
        # 图2：异常倍数深度剖面图
        logger.info("绘制图2：异常倍数深度剖面图")
        try:
            if valid_anomaly is not None and len(valid_anomaly) > 0:
                ax2.plot(valid_anomaly, valid_depths, linewidth=1, color='green')
                ax2.invert_yaxis()
                ax2.set_xlabel('异常倍数', fontsize=12, color='black')
                ax2.set_ylabel('深度 (m)', fontsize=12, color='black')
                ax2.set_title('TG异常倍数深度剖面图', fontsize=14, fontweight='bold', color='black')
                ax2.grid(True, alpha=0.3)
                ax2.set_facecolor('white')
                logger.info(f"图2绘制完成，数据点数: {len(valid_anomaly)}")
            else:
                ax2.text(0.5, 0.5, '无异常倍数数据', transform=ax2.transAxes, 
                        ha='center', va='center', fontsize=14, color='red')
                ax2.set_title('TG异常倍数深度剖面图', fontsize=14, fontweight='bold', color='black')
        except Exception as e:
            logger.error(f"绘制图2失败: {e}")
            ax2.text(0.5, 0.5, f'图2绘制失败: {str(e)}', transform=ax2.transAxes, 
                    ha='center', va='center', fontsize=12, color='red')
        
        # 图3：层型分布统计饼图
        logger.info("绘制图3：层型分布统计饼图")
        try:
            if '层型' in df.columns:
                layer_counts = df['层型'].value_counts()
                logger.info(f"层型统计: {dict(layer_counts)}")
                
                if len(layer_counts) > 0:
                    colors = {'水层': '#87CEEB', '弱显示层': '#FFE4B5', '油层': '#90EE90', 
                             '气层': '#FFA07A', '强气层': '#FF6347', '无效数据': '#D3D3D3'}
                    pie_colors = [colors.get(layer, '#D3D3D3') for layer in layer_counts.index]
                    
                    # 计算百分比，用于决定是否显示小扇形的标签
                    total = layer_counts.sum()
                    percentages = (layer_counts / total * 100).round(1)
                    
                    # 自定义autopct函数，小于1%的不显示百分比
                    def autopct_format(pct):
                        return f'{pct:.1f}%' if pct >= 1.0 else ''
                    
                    # 为小扇形调整标签显示
                    labels = []
                    for i, (layer, count) in enumerate(layer_counts.items()):
                        pct = percentages.iloc[i]
                        if pct >= 2.0:  # 大于2%显示完整标签
                            labels.append(layer)
                        elif pct >= 0.5:  # 0.5%-2%显示简化标签
                            labels.append(layer[:2])  # 只显示前两个字
                        else:  # 小于0.5%不显示标签
                            labels.append('')
                    
                    # 绘制饼图，调整参数避免标签重叠
                    wedges, texts, autotexts = ax3.pie(
                        layer_counts.values, 
                        labels=labels,
                        autopct=autopct_format,
                        colors=pie_colors, 
                        startangle=45,  # 调整起始角度，优化标签分布
                        labeldistance=1.15,  # 标签距离圆心的倍数
                        pctdistance=0.85,    # 百分比标签距离圆心的倍数
                        wedgeprops=dict(edgecolor='white', linewidth=1)  # 添加白色边框分隔
                    )
                    
                    # 设置文字颜色和大小
                    for text in texts:
                        text.set_color('black')
                        text.set_fontsize(9)  # 稍微减小字体
                        text.set_weight('normal')
                    for autotext in autotexts:
                        autotext.set_color('black')
                        autotext.set_fontsize(8)  # 百分比字体更小
                        autotext.set_weight('bold')
                    
                    # 为小扇形添加图例，放在饼图下方
                    if any(percentages < 2.0):
                        legend_labels = []
                        for i, (layer, count) in enumerate(layer_counts.items()):
                            pct = percentages.iloc[i]
                            legend_labels.append(f'{layer}: {pct:.1f}%')
                        
                        ax3.legend(wedges, legend_labels, 
                                  loc='upper center', bbox_to_anchor=(0.5, -0.05),
                                  ncol=2, fontsize=7)
                    
                    ax3.set_title('层型分布统计', fontsize=14, fontweight='bold', color='black')
                    logger.info(f"图3绘制完成，层型数量: {len(layer_counts)}, 百分比: {dict(percentages)}")
                else:
                    ax3.text(0.5, 0.5, '无层型数据', transform=ax3.transAxes, 
                            ha='center', va='center', fontsize=14, color='red')
                    ax3.set_title('层型分布统计', fontsize=14, fontweight='bold', color='black')
            else:
                ax3.text(0.5, 0.5, '缺少层型列', transform=ax3.transAxes, 
                        ha='center', va='center', fontsize=14, color='red')
                ax3.set_title('层型分布统计', fontsize=14, fontweight='bold', color='black')
        except Exception as e:
            logger.error(f"绘制图3失败: {e}")
            ax3.text(0.5, 0.5, f'图3绘制失败: {str(e)}', transform=ax3.transAxes, 
                    ha='center', va='center', fontsize=12, color='red')
        
        # 图4：TG值直方图分布
        logger.info("绘制图4：TG值直方图分布")
        try:
            n, bins, patches = ax4.hist(valid_tg, bins=30, alpha=0.7, color='skyblue', edgecolor='black')
            
            # 添加参考线
            ax4.axvline(x=2, color='red', linestyle='--', alpha=0.8, linewidth=2, label='2%')
            ax4.axvline(x=5, color='orange', linestyle='--', alpha=0.8, linewidth=2, label='5%')
            ax4.axvline(x=15, color='green', linestyle='--', alpha=0.8, linewidth=2, label='15%')
            
            ax4.set_xlabel('TG值 (%)', fontsize=12, color='black')
            ax4.set_ylabel('样品数量', fontsize=12, color='black')
            ax4.set_title('TG值分布直方图', fontsize=14, fontweight='bold', color='black')
            ax4.legend(fontsize=10)
            ax4.grid(True, alpha=0.3)
            ax4.set_facecolor('white')
            
            logger.info(f"图4绘制完成，最大频数: {n.max()}")
        except Exception as e:
            logger.error(f"绘制图4失败: {e}")
            ax4.text(0.5, 0.5, f'图4绘制失败: {str(e)}', transform=ax4.transAxes, 
                    ha='center', va='center', fontsize=12, color='red')
        
        # 调整布局并保存
        logger.info("调整布局并保存图片...")
        plt.tight_layout(rect=[0, 0.02, 1, 0.96])  # 为图例留出空间
        
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # 保存图片
        plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white', 
                   edgecolor='none', format='png', transparent=False)
        
        # 检查图片是否成功生成
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            logger.info(f"TG评价可视化图表已保存: {output_path}, 文件大小: {file_size} 字节")
        else:
            logger.error(f"图片保存失败: {output_path}")
            
        plt.close('all')
        return output_path
        
    except Exception as e:
        logger.error(f"创建可视化图表失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        plt.close('all')
        return ""

def is_interpreted_file(filename: str) -> bool:
    """判断文件是否为已解释的文件
    
    Args:
        filename: 文件名
        
    Returns:
        是否为已解释的文件
    """
    return "interpreted" in filename.lower() or "解释" in filename

def remove_file_id_prefix(filename: str) -> str:
    """去掉文件名中的ID前缀
    
    Args:
        filename: 原始文件名（可能包含ID前缀）
        
    Returns:
        去掉ID前缀后的文件名
    """
    import re
    # 匹配类似 "u-abc123_" 或 "g-abc123_" 这样的前缀
    pattern = r'^[a-z]-[a-z0-9]+_'
    clean_filename = re.sub(pattern, '', filename)
    return clean_filename

def process_tg_excel_file(file_path: str) -> Tuple[pd.DataFrame, str]:
    """处理Excel文件，进行TG评价分析
    
    Args:
        file_path: Excel文件路径
        
    Returns:
        处理后的数据框和输出文件路径
    """
    try:
        # 先获取原始表头，判断表头结构
        header_df = pd.read_excel(file_path, nrows=2)
        logger.info(f"原始表头结构: {header_df.shape}")
        
        # 检查第一行是否是表头，第二行是否是数据
        first_row = header_df.iloc[0].tolist()
        second_row = header_df.iloc[1].tolist() if len(header_df) > 1 else []
        
        # 判断是否为中文表头
        chinese_headers = ['井名', '井深', '钻时', '全量', '甲烷', '乙烷', '丙烷', '异丁烷', '正丁烷', '异戊烷', '正戊烷', '二氧化碳', '其它非烃']
        is_chinese_header = any(str(cell) in chinese_headers for cell in first_row if not pd.isna(cell))
        
        # 判断第二行是否是数据（主要包含数值）
        second_row_is_data = len(second_row) > 0 and sum(1 for cell in second_row if isinstance(cell, (int, float)) and not pd.isna(cell)) > len(second_row) / 2
        
        if is_chinese_header and second_row_is_data:
            # 单行表头，第二行开始是数据
            skip_rows = 1
            logger.info("检测到单行中文表头，跳过1行读取数据")
        else:
            # 双行表头或其他格式
            skip_rows = 2
            logger.info("使用默认设置，跳过2行读取数据")
        
        # 读取数据部分
        df = pd.read_excel(file_path, skiprows=skip_rows)
        logger.info(f"成功读取Excel文件，跳过{skip_rows}行表头，共{len(df)}行数据")
        logger.info(f"第一行内容: {first_row}")
        if second_row:
            logger.info(f"第二行内容: {second_row}")
        
        # 中文到英文的列名映射
        chinese_to_english = {
            '井名': 'Well', '井深': 'Depth', '钻时': 'Rop', '全量': 'Tg',
            '甲烷': 'C1', '乙烷': 'C2', '丙烷': 'C3', '异丁烷': 'iC4', '正丁烷': 'nC4',
            '异戊烷': 'iC5', '正戊烷': 'nC5', '二氧化碳': 'CO2', '其它非烃': 'Other'
        }
        
        # 重新检查第一行是否是中文表头（用于列名转换）
        is_chinese_header_for_columns = any(str(cell) in chinese_to_english for cell in first_row if not pd.isna(cell))
        
        if is_chinese_header_for_columns:
            # 第一行是中文表头，转换为英文列名
            logger.info("检测到中文表头，转换为英文列名")
            english_headers = []
            chinese_headers = []
            
            for i, cell in enumerate(first_row):
                if pd.isna(cell) or str(cell).strip() == '':
                    english_headers.append(f"Col{i}")
                    chinese_headers.append(f"列{i}")
                else:
                    cell_str = str(cell).strip()
                    if cell_str in chinese_to_english:
                        english_headers.append(chinese_to_english[cell_str])
                        chinese_headers.append(cell_str)
                    else:
                        english_headers.append(f"Col{i}")
                        chinese_headers.append(cell_str)
            
            # 使用英文列名设置DataFrame
            if len(english_headers) >= len(df.columns):
                df.columns = english_headers[:len(df.columns)]
                logger.info(f"使用转换后的英文列名: {list(df.columns)}")
            else:
                # 补充列名
                final_columns = english_headers + [f"Col{i}" for i in range(len(english_headers), len(df.columns))]
                df.columns = final_columns
                logger.info(f"补充列名后使用: {list(df.columns)}")
                
            # 保存原始表头用于重建
            original_chinese_headers = chinese_headers[:len(df.columns)]
            original_english_headers = english_headers[:len(df.columns)]
            
        else:
            # 可能是英文表头或其他格式，使用默认处理
            logger.info("未检测到标准中文表头，使用默认列名")
            default_columns = ["Well", "Depth", "Rop", "Tg", "C1", "C2", "C3", "iC4", "nC4", "iC5", "nC5", "CO2", "Other"]
            df.columns = default_columns[:len(df.columns)]
            logger.info(f"使用默认英文列名: {list(df.columns)}")
            
            # 创建默认的中英文表头
            original_english_headers = list(df.columns)
            original_chinese_headers = ['井名', '井深', '钻时', '全量', '甲烷', '乙烷', '丙烷', '异丁烷', '正丁烷', '异戊烷', '正戊烷', '二氧化碳', '其它非烃'][:len(df.columns)]
        
        # 统一列名（Tg或TG都转换为Tg）
        if 'TG' in df.columns and 'Tg' not in df.columns:
            df = df.rename(columns={'TG': 'Tg'})
        
        # 清理数据：删除空行和无效数据
        df = df.dropna(subset=['Well', 'Depth'])
        
        # 确保数值列是数值类型
        numeric_columns = ['Depth', 'Rop', 'Tg']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 再次删除转换后的无效行
        df = df.dropna(subset=['Depth', 'Tg'])
        
        logger.info(f"数据清理后，共{len(df)}行有效数据")
        
        # 检查必需的列是否存在
        required_columns = ['Well', 'Depth', 'Tg']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            raise ValueError(f"缺少必需的列: {missing_columns}")
        
        # 按深度排序
        df = df.sort_values('Depth').reset_index(drop=True)
        
        # 计算TG背景值
        logger.info("开始计算TG背景值...")
        tg_values = df['Tg'].values
        background_values = calculate_background_tg(tg_values)
        df['TG背景值'] = background_values
        
        # 计算异常倍数
        logger.info("开始计算异常倍数...")
        anomaly_ratios = calculate_tg_anomaly_ratio(tg_values, background_values)
        df['异常倍数'] = anomaly_ratios
        
        # 分析深度趋势
        logger.info("开始分析深度趋势...")
        depths = df['Depth'].values
        trends = analyze_depth_trend(depths, tg_values)
        df['深度趋势'] = trends
        
        # 进行层型分类
        logger.info("开始进行层型分类...")
        classifications = []
        for _, row in df.iterrows():
            classification = classify_layer_type(
                tg_value=row['Tg'],
                anomaly_ratio=row['异常倍数'],
                depth_trend=row['深度趋势']
            )
            classifications.append(classification)
        
        # 展开分类结果到单独的列
        df['层型'] = [result['layer_type'] for result in classifications]
        df['可信度'] = [result['confidence'] for result in classifications]
        df['描述'] = [result['description'] for result in classifications]
        
        # 连续性校正
        logger.info("开始连续性校正...")
        layer_types = df['层型'].values
        corrected_types = check_layer_continuity(layer_types, depths)
        df['连续性校正后层型'] = corrected_types
        
        # 判断是否为已解释的文件
        input_filename = Path(file_path).name
        is_interpreted = is_interpreted_file(input_filename)
        
        # 重建完整的Excel文件结构，保持原始双行表头格式
        logger.info("开始重建Excel文件结构...")
        
        # 1. 使用之前保存的原始表头数据
        # original_english_headers和original_chinese_headers已经在上面定义
        
        # 2. 清理原始表头，确保数量匹配原始数据列数
        original_data_columns = len(df.columns) - 7  # 减去新增的7列
        clean_english_headers = original_english_headers[:original_data_columns]
        clean_chinese_headers = original_chinese_headers[:original_data_columns]
        
        # 确保长度足够
        while len(clean_english_headers) < original_data_columns:
            clean_english_headers.append(f"Col{len(clean_english_headers)+1}")
        while len(clean_chinese_headers) < original_data_columns:
            clean_chinese_headers.append(f"列{len(clean_chinese_headers)+1}")
        
        # 3. 为新增列添加表头
        new_english_headers = ['TG_background', 'Anomaly_ratio', 'Depth_trend', 'Layer_type', 'Confidence', 'Description', 'Corrected_layer_type']
        new_chinese_headers = ['TG背景值', '异常倍数', '深度趋势', '层型', '可信度', '描述', '连续性校正后层型']
        
        # 4. 合并表头（原始表头 + 新增表头）
        full_english_headers = clean_english_headers + new_english_headers
        full_chinese_headers = clean_chinese_headers + new_chinese_headers
        
        logger.info(f"最终表头长度 - 英文: {len(full_english_headers)}, 中文: {len(full_chinese_headers)}, 数据列: {len(df.columns)}")
        
        # 5. 构建最终的DataFrame
        # 创建表头行（保持原始格式：第一行英文，第二行中文）
        row1_data = [full_english_headers[i] if i < len(full_english_headers) else '' for i in range(len(df.columns))]
        row2_data = [full_chinese_headers[i] if i < len(full_chinese_headers) else '' for i in range(len(df.columns))]
        
        # 创建完整的DataFrame，包含表头和数据
        all_data = []
        all_data.append(row1_data)  # 第一行：英文表头
        all_data.append(row2_data)  # 第二行：中文表头
        
        # 添加所有数据行（转换为字符串避免类型问题）
        for _, row in df.iterrows():
            all_data.append([str(val) if not pd.isna(val) else '' for val in row])
        
        # 构建最终DataFrame
        final_df = pd.DataFrame(all_data)
        logger.info(f"最终DataFrame形状: {final_df.shape}")
        
        if is_interpreted:
            # 已解释文件，保持原文件名和路径
            output_path = file_path
            logger.info("检测到已解释文件，将在原文件基础上更新")
            
            # 保存处理后的数据到Excel文件
            with pd.ExcelWriter(output_path, engine='openpyxl') as excel_writer:
                final_df.to_excel(excel_writer, sheet_name='Sheet1', index=False, header=False)
        else:
            # 原始文件，生成新的解释文件，使用file_manager来保存
            original_filename = Path(file_path).name
            # 去掉原始文件的ID前缀，只保留实际文件名
            clean_filename = remove_file_id_prefix(original_filename)
            # 去掉扩展名后添加_interpreted
            stem = Path(clean_filename).stem
            new_filename = f"{stem}_interpreted.xlsx"
            logger.info(f"检测到原始文件，将生成新的解释文件: {new_filename}")
            
            # 先将DataFrame保存到字节流
            import io
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as excel_writer:
                final_df.to_excel(excel_writer, sheet_name='Sheet1', index=False, header=False)
            excel_data = excel_buffer.getvalue()
            
            # 使用file_manager保存文件
            file_id = file_manager.save_file(
                file_data=excel_data,
                file_name=new_filename,
                file_type="xlsx",
                source="generated"
            )
            
            # 获取生成的文件路径
            file_info = file_manager.get_file_info(file_id)
            output_path = file_info.get("file_path")
        logger.info(f"处理完成，结果已保存到: {output_path}")
        return df, output_path,file_id
        
    except Exception as e:
        logger.error(f"处理Excel文件失败: {e}")
        raise

@register_tool(category="gas_logging")
def tg_layer_evaluation(file_id: str) -> str:
    """气测录井分析的第一步-全烃TG评价油气水层工具
    
    基于全烃含量（TG）进行油气水层综合评价，考虑：
    1. TG绝对值大小
    2. 相对于背景值的异常倍数
    3. 随深度的变化趋势  
    4. 异常的连续性和厚度
    
    评价标准：
    - 水层：TG < 2%，异常倍数 < 2倍，平稳无异常
    - 弱显示层：TG 2-5%，异常倍数 2-3倍，轻微异常
    - 油层：TG 5-15%，异常倍数 3-8倍，持续异常
    - 气层：TG 15-30%，异常倍数 8-20倍，显著异常
    - 强气层：TG > 30%，异常倍数 > 20倍，极强异常
    
    Args:
        file_id: Excel文件ID，可以是原始上传文件或前一工具生成的解释文件。
                如果是在其他录井工具之后执行，应使用前一工具返回信息中的NEXT_FILE_ID，
                以在已有解释结果基础上追加新的分析列。
                文件应包含Well、Depth、Tg等列。
        
    Returns:
        分析结果报告，包含新生成文件的NEXT_FILE_ID供后续工具使用
    """
    writer = get_stream_writer()
    
    try:
        if writer:
            writer({"custom_step": "开始TG油气水层评价分析..."})
        
        # 获取文件信息
        file_info = file_manager.get_file_info(file_id)
        if not file_info:
            error_msg = f"找不到ID为 {file_id} 的文件"
            logger.error(error_msg)
            return error_msg
        
        file_path = file_info.get("file_path")
        file_name = file_info.get("file_name", "")
        
        if writer:
            writer({"custom_step": f"正在处理文件: {file_name}"})
        
        # 处理Excel文件
        df, output_excel_path,new_file_id = process_tg_excel_file(file_path)
        
        if writer:
            writer({"custom_step": f"成功处理{len(df)}行数据，完成TG评价分析"})
        
        # 生成可视化图表
        # 去掉文件名中的ID前缀，生成清洁的图片文件名
        clean_filename = remove_file_id_prefix(file_name)
        base_name = Path(clean_filename).stem
        # 使用更直观的文件名
        image_filename = f"TG全烃综合解释图表_{base_name}.png"
        
        # 临时路径用于生成图片
        temp_image_path = os.path.join(file_manager.temp_path, f"temp_{image_filename}")
        chart_path = create_tg_evaluation_visualization(df, temp_image_path)
        
        # 如果图片生成成功，使用file_manager保存
        if chart_path and os.path.exists(chart_path):
            # 读取图片数据
            with open(chart_path, 'rb') as f:
                image_data = f.read()
            
            # 使用file_manager保存图片
            image_file_id = file_manager.save_file(
                file_data=image_data,
                file_name=image_filename,
                file_type="png",
                source="generated"
            )
            
            # 获取保存后的图片路径
            image_file_info = file_manager.get_file_info(image_file_id)
            final_image_path = image_file_info.get("file_path")
            
            # 删除临时文件
            try:
                os.remove(temp_image_path)
            except:
                pass
        else:
            final_image_path = None
        
        # 统计分析结果
        total_samples = len(df)
        
        # 统计各层型的样品数量（使用校正后的结果）
        layer_stats = df['连续性校正后层型'].value_counts()
        
        # 计算厚度统计
        depth_range = df['Depth'].max() - df['Depth'].min()
        
        if writer:
            writer({"custom_step": f"生成可视化图表: {image_filename}"})
        
        # 推送图片到UI
        if final_image_path and os.path.exists(final_image_path):
            image_message = {
                "image_path": final_image_path,
                "title": "TG全烃综合解释图表"
            }
            if writer:
                writer({"image_message": image_message})
        
        # 推送Excel文件到UI
        file_message = {
            "file_path": output_excel_path,
            "file_name": Path(output_excel_path).name,
            "file_type": "xlsx"
        }
        if writer:
            writer({"file_message": file_message})
        
        # 生成简洁的执行结果信息
        depth_range_str = f"{df['Depth'].min():.1f}-{df['Depth'].max():.1f}m"
        
        if len(layer_stats) > 0:
            main_layer = layer_stats.index[0]
            main_percentage = (layer_stats.iloc[0] / total_samples) * 100
            layer_summary = f"主要层型：{main_layer}({main_percentage:.1f}%)"
        else:
            layer_summary = "无有效分类结果"
        
        # 统计油气层比例
        oil_gas_count = layer_stats.get('油层', 0) + layer_stats.get('气层', 0) + layer_stats.get('强气层', 0)
        oil_gas_percentage = (oil_gas_count / total_samples) * 100 if total_samples > 0 else 0
        
        result_message = f"""✅ TG油气水层评价完成
🆔 **NEXT_FILE_ID: {new_file_id}** (后续工具请使用此file_id)
📏 分析井段: {depth_range_str} ({total_samples}个样品)
🎯 {layer_summary}
⛽ 油气层比例: {oil_gas_percentage:.1f}%
📁 解释结果文件: {Path(output_excel_path).name}
📈 可视化图表: {image_filename}

⚠️ 重要: 后续工具必须使用file_id: {new_file_id} 以在此结果基础上追加分析"""
        
        if writer:
            writer({"custom_step": result_message})
        
        logger.info("TG油气水层评价分析完成")
        return result_message
        
    except Exception as e:
        error_msg = f"TG评价分析失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        if writer:
            writer({"custom_step": f"❌ {error_msg}"})
        
        return error_msg