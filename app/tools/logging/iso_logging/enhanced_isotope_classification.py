"""
增强版碳同位素气源分类工具

该模块提供了基于深度分析的天然气碳同位素气源分类工具，包括：
1. 增强版Bernard气源分类
2. 增强版碳数趋势气源分类
3. 增强版综合分类模型

这些工具能够按深度分段分析不同深度区间的气源类型和成熟度，并生成全面的文本描述。
"""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats
import logging
from typing import Dict, List, Tuple, Optional, Union, Any
import uuid

from app.core.file_manager import file_manager
from app.tools.logging.iso_logging.isotope_depth_helpers import (
    preprocess_isotope_data,
    create_depth_segments,
    extract_isotope_features
)
from app.tools.registry import register_tool
from langgraph.config import get_stream_writer

# 设置日志
logger = logging.getLogger(__name__)

# 临时图表存储目录
TEMP_PLOT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "generated")
if not os.path.exists(TEMP_PLOT_DIR):
    os.makedirs(TEMP_PLOT_DIR)

# 配置matplotlib字体支持中文
try:
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'SimSun', 'DejaVu Sans']  # 优先使用的中文字体
    plt.rcParams['axes.unicode_minus'] = False  # 正确显示负号
    logger.info("已配置matplotlib字体支持中文")
except Exception as e:
    logger.warning(f"配置matplotlib字体支持中文失败: {str(e)}")

@register_tool(category="iso_logging")
def enhanced_classify_gas_source(file_id: str, depth_segments: bool = True, num_segments: int = 5) -> str:
    """增强版天然气气源分类工具
    
    基于碳同位素数据，对天然气样品进行气源分类。该增强版工具能够:
    1. 按深度分段分析不同深度区间的气源特征
    2. 综合Bernard图解和碳数趋势判断气源类型
    3. 检测同位素倒转和混合气迹象
    4. 生成全面的分析报告和深度剖面
    
    Args:
        file_id: 文件ID，已上传到系统的数据文件
        depth_segments: 是否按深度分段
        num_segments: 深度段数量
        
    Returns:
        包含气源分类结果的详细分析报告
    """
    # 获取流写入器
    writer = get_stream_writer()
    
    if writer:
        writer({"custom_step": f"正在进行增强版天然气气源分类分析(文件ID: {file_id})..."})
    
    try:
        # 获取文件信息并读取数据
        file_info = file_manager.get_file_info(file_id)
        if not file_info:
            return f"找不到ID为 {file_id} 的文件。"
            
        file_path = file_info.get("file_path")
        file_type = file_info.get("file_type", "").lower()
        file_name = file_info.get("file_name", "")
        
        df = None
        if file_type in ["csv"]:
            df = pd.read_csv(file_path)
        elif file_type in ["xlsx", "xls"]:
            df = pd.read_excel(file_path)
        else:
            return f"不支持的文件类型: {file_type}。请提供CSV或Excel格式的数据文件。"
        
        # 数据预处理
        df = preprocess_isotope_data(df)
        
        # 从isotope_analysis模块导入辅助函数
        from app.tools.logging.iso_logging.isotope_analysis import (_identify_isotope_columns, 
                                                       _identify_depth_column,
                                                       _extract_isotope_ratios)
        
        # 识别深度列和同位素列
        depth_col = _identify_depth_column(df)
        isotope_columns = _identify_isotope_columns(df)
        
        # 检查是否有足够的数据进行分析
        required_components = ["C1", "C2", "C3"]
        missing_components = []
        
        for component in required_components:
            if not isotope_columns.get(component, []):
                missing_components.append(component)
                
        if missing_components:
            return f"缺少必要的同位素数据列: {', '.join(missing_components)}。气源分类至少需要C1、C2、C3的碳同位素数据。"
        
        # 获取每个组分的碳同位素数据
        c1_col = isotope_columns["C1"][0]
        c2_col = isotope_columns["C2"][0]
        c3_col = isotope_columns["C3"][0]
        
        # 计算关键比值 C1/(C2+C3)
        try:
            peak_columns = _extract_isotope_ratios(df)
            
            # 确保返回的是嵌套字典格式
            if isinstance(peak_columns, str):
                logger.warning(f"_extract_isotope_ratios返回了字符串而不是字典: {peak_columns}")
                peak_columns = {}
        except Exception as e:
            logger.error(f"提取峰面积数据时出错: {str(e)}")
            peak_columns = {}
        
        # 提取峰面积或浓度数据
        c1_peak_col = None
        c2_peak_col = None
        c3_peak_col = None
        
        # 从嵌套字典中提取峰面积列
        if "C1" in peak_columns and isinstance(peak_columns["C1"], dict) and peak_columns["C1"].get("peak"):
            c1_peak_col = peak_columns["C1"]["peak"][0] if peak_columns["C1"]["peak"] else None
        if "C2" in peak_columns and isinstance(peak_columns["C2"], dict) and peak_columns["C2"].get("peak"):
            c2_peak_col = peak_columns["C2"]["peak"][0] if peak_columns["C2"]["peak"] else None
        if "C3" in peak_columns and isinstance(peak_columns["C3"], dict) and peak_columns["C3"].get("peak"):
            c3_peak_col = peak_columns["C3"]["peak"][0] if peak_columns["C3"]["peak"] else None
            
        # 如果找不到峰面积列，使用默认比例
        if not all([c1_peak_col, c2_peak_col, c3_peak_col]):
            if writer:
                writer({"custom_step": "未找到完整的峰面积或浓度数据列，将使用同位素值进行分类"})
            
            # 创建虚拟峰面积列用于计算比值
            df["c1_peak"] = 100.0  # 默认比例
            df["c2_peak"] = 10.0
            df["c3_peak"] = 1.0
            
            c1_peak_col = "c1_peak"
            c2_peak_col = "c2_peak"
            c3_peak_col = "c3_peak"
        
        # 计算 Bernard 比值
        df["c1_c2c3_ratio"] = df[c1_peak_col] / (df[c2_peak_col] + df[c3_peak_col])
        
        # 创建分段(如果启用)
        segments = None
        if depth_segments and depth_col and len(df) > 10:
            # 使用甲烷碳同位素列进行分段
            segments = create_depth_segments(
                df, 
                depth_col, 
                c1_col, 
                segment_method="change_point", 
                num_segments=num_segments
            )
            
            if writer:
                writer({"custom_step": f"已创建{len(segments)}个深度分段"})
                
        # 提取全局特征
        global_features = extract_isotope_features(df, isotope_columns, depth_col, segments=None)
        
        # 提取分段特征(如果启用)
        segment_features = []
        if segments:
            for i, (start, end) in enumerate(segments):
                segment_df = df[(df[depth_col] >= start) & (df[depth_col] <= end)]
                if len(segment_df) >= 3:  # 确保每段有足够的数据点
                    feature = extract_isotope_features(segment_df, isotope_columns, depth_col, segments=None)
                    feature["segment_id"] = i + 1
                    feature["depth_start"] = start
                    feature["depth_end"] = end
                    feature["data_points"] = len(segment_df)
                    segment_features.append(feature)
        
        # 基于特征进行气源分类
        # 全局气源分类
        global_source = classify_gas_source_by_features(global_features)
        
        # 分段气源分类
        segment_sources = []
        if segment_features:
            for feature in segment_features:
                source = classify_gas_source_by_features(feature)
                segment_sources.append({
                    "segment_id": feature["segment_id"],
                    "depth_start": feature["depth_start"],
                    "depth_end": feature["depth_end"],
                    "source_type": source["source_type"],
                    "maturity": source["maturity"],
                    "confidence": source["confidence"],
                    "evidence": source["evidence"],
                    "data_points": feature["data_points"]
                })
        
        # 可视化气源分类结果
        if depth_col and len(segment_sources) > 1:
            # 创建深度剖面图
            plt.figure(figsize=(12, 10))
            
            # 主图：深度-气源类型
            ax1 = plt.subplot2grid((1, 3), (0, 0), colspan=2)
            
            # 颜色映射
            source_colors = {
                "生物成因气": "green",
                "热成因气": "red",
                "混合成因气": "orange",
                "次生改造气": "purple"
            }
            
            # 定义深度范围
            depth_min = df[depth_col].min()
            depth_max = df[depth_col].max()
            
            # 绘制深度区间
            for segment in segment_sources:
                start = segment["depth_start"]
                end = segment["depth_end"]
                source = segment["source_type"]
                color = source_colors.get(source, "gray")
                
                # 绘制深度区间填充
                ax1.fill_betweenx([start, end], 0, 1, color=color, alpha=0.3)
                
                # 添加文本标签
                mid_depth = (start + end) / 2
                ax1.text(0.5, mid_depth, f"{source}\n({segment['maturity']})", 
                        ha='center', va='center', fontsize=9)
            
            # 设置深度轴
            ax1.set_ylim(depth_max * 1.05, depth_min * 0.95)  # 反转Y轴
            ax1.set_xlim(0, 1)
            ax1.set_xlabel("气源类型", fontsize=12)
            ax1.set_ylabel("深度 (m)", fontsize=12)
            ax1.set_xticks([])  # 隐藏X轴刻度
            ax1.grid(True, axis='y', linestyle='--', alpha=0.7)
            ax1.set_title("深度-气源分类剖面", fontsize=14)
            
            # 添加图例
            from matplotlib.patches import Patch
            legend_elements = [Patch(facecolor=c, alpha=0.5, label=s) 
                              for s, c in source_colors.items()]
            ax1.legend(handles=legend_elements, loc='upper right', fontsize=10)
            
            # 辅助图：同位素值随深度变化
            ax2 = plt.subplot2grid((1, 3), (0, 2))
            
            # 绘制甲烷碳同位素随深度变化
            ax2.scatter(df[c1_col], df[depth_col], c='blue', s=30, label='δ13C-CH4')
            ax2.set_xlabel("δ13C (‰)", fontsize=12)
            ax2.set_ylim(depth_max * 1.05, depth_min * 0.95)  # 反转Y轴
            ax2.grid(True, linestyle='--', alpha=0.7)
            
            # 添加次要X轴显示乙烷
            ax2_twin = ax2.twiny()
            ax2_twin.scatter(df[c2_col], df[depth_col], c='red', s=30, label='δ13C-C2H6')
            ax2_twin.set_xlabel("δ13C-C2H6 (‰)", fontsize=10, color='red')
            ax2_twin.tick_params(axis='x', colors='red')
            
            # 添加图例
            lines1, labels1 = ax2.get_legend_handles_labels()
            lines2, labels2 = ax2_twin.get_legend_handles_labels()
            ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper right', fontsize=9)
            
            # 保存图表
            output_filename = f"gas_source_profile_{os.path.splitext(file_name)[0]}.png"
            output_path = os.path.join(TEMP_PLOT_DIR, output_filename)
            plt.tight_layout()
            plt.savefig(output_path, dpi=300)
            plt.close()
            
            # 注册生成的图表为文件
            profile_file_id = file_manager.register_file(
                file_path=output_path,
                file_name=output_filename,
                file_type="png",
                metadata={"description": "天然气气源深度剖面图"},
                source="generated",
                session_id=None  # 暂不关联到特定会话
            )
            
            if writer:
                writer({"custom_step": "天然气气源深度剖面图创建完成"})
                
                # 发送图片消息，立即推送到前端显示
                image_message = {
                    "image_path": output_path,
                    "title": "天然气气源深度剖面图"
                }
                writer({"image_message": image_message})
        else:
            profile_file_id = None
        
        # 生成分析报告
        result = generate_gas_source_report(global_source, segment_sources, global_features, profile_file_id)
        
        if writer:
            writer({"custom_step": "增强版天然气气源分类分析完成\n"})
            
        return result
    except Exception as e:
        error_msg = f"进行增强版天然气气源分类分析时出错: {str(e)}"
        logger.error(error_msg, exc_info=True)
        if writer:
            writer({"custom_step": error_msg})
        return error_msg

def classify_gas_source_by_features(features: Dict[str, Any]) -> Dict[str, Any]:
    """
    基于提取的特征对气源进行分类
    
    Args:
        features: 提取的碳同位素特征字典
        
    Returns:
        包含气源类型、成熟度、置信度和证据的字典
    """
    source_type = "未定"
    maturity = "未定"
    confidence = 0.0
    evidence = []
    
    # 提取关键特征
    c1_value = features.get("mean_c1_d13c")
    c2_value = features.get("mean_c2_d13c")
    c3_value = features.get("mean_c3_d13c")
    c1_c2c3_ratio = features.get("mean_c1_c2c3_ratio")
    has_reversal = features.get("has_isotope_reversal", False)
    
    # 检查是否有足够的特征进行分类
    if c1_value is None or c2_value is None:
        return {
            "source_type": "数据不足",
            "maturity": "未定",
            "confidence": 0.0,
            "evidence": ["关键同位素数据缺失，无法进行气源分类"]
        }
    
    # 计算关键指标
    c1_c2_diff = c2_value - c1_value
    
    # ==== 生物成因气判断 ====
    bio_score = 0
    
    # 基于甲烷碳同位素值
    if c1_value < -60:
        bio_score += 30
        evidence.append(f"甲烷碳同位素值(δ13C1 = {c1_value:.2f}‰)较轻，指示生物成因")
    elif c1_value < -55:
        bio_score += 15
        evidence.append(f"甲烷碳同位素值(δ13C1 = {c1_value:.2f}‰)偏轻，可能含有生物成因组分")
    
    # 基于C1/(C2+C3)比值
    if c1_c2c3_ratio is not None:
        if c1_c2c3_ratio > 1000:
            bio_score += 30
            evidence.append(f"C1/(C2+C3)比值极高({c1_c2c3_ratio:.2f})，符合生物气特征")
        elif c1_c2c3_ratio > 100:
            bio_score += 15
            evidence.append(f"C1/(C2+C3)比值较高({c1_c2c3_ratio:.2f})，可能含有生物气组分")
    
    # ==== 热成因气判断 ====
    therm_score = 0
    
    # 基于甲烷碳同位素值
    if -50 < c1_value < -20:
        therm_score += 25
        evidence.append(f"甲烷碳同位素值(δ13C1 = {c1_value:.2f}‰)适中，符合热成因气特征")
    elif -55 < c1_value <= -50:
        therm_score += 15
        evidence.append(f"甲烷碳同位素值(δ13C1 = {c1_value:.2f}‰)位于热成因区间下限")
    
    # 基于乙烷和丙烷碳同位素值
    if c2_value is not None and c3_value is not None:
        if -40 < c2_value < -20 and -35 < c3_value < -15:
            therm_score += 25
            evidence.append(f"乙烷和丙烷碳同位素值(δ13C2 = {c2_value:.2f}‰, δ13C3 = {c3_value:.2f}‰)符合热成因气特征")
    
    # 基于碳同位素正常分馏模式
    if not has_reversal and c1_value < c2_value and (c3_value is None or c2_value < c3_value):
        therm_score += 15
        evidence.append(f"碳同位素展示正常分馏模式(δ13C1 < δ13C2 < δ13C3)，符合热成因气特征")
    
    # 基于C1/(C2+C3)比值
    if c1_c2c3_ratio is not None:
        if 5 < c1_c2c3_ratio < 100:
            therm_score += 15
            evidence.append(f"C1/(C2+C3)比值适中({c1_c2c3_ratio:.2f})，符合热成因气特征")
            
    # ==== 混合成因气判断 ====
    mixed_score = 0
    
    # 基于甲烷碳同位素值
    if -60 < c1_value < -50:
        mixed_score += 20
        evidence.append(f"甲烷碳同位素值(δ13C1 = {c1_value:.2f}‰)处于混合区间")
    
    # 基于碳同位素倒转
    if has_reversal:
        mixed_score += 25
        evidence.append("检测到碳同位素倒转现象，指示可能的气源混合")
    
    # 基于C1/(C2+C3)比值
    if c1_c2c3_ratio is not None and 50 < c1_c2c3_ratio < 200:
        mixed_score += 15
        evidence.append(f"C1/(C2+C3)比值({c1_c2c3_ratio:.2f})处于混合区间")
    
    # ==== 次生改造气判断 ====
    secondary_score = 0
    
    # 基于同位素倒转和甲烷碳同位素值
    if has_reversal and c1_value > -50:
        secondary_score += 30
        evidence.append("同位素倒转结合较重的甲烷碳同位素值，强烈指示次生微生物改造")
    
    # 基于碳同位素差异
    if c3_value is not None and c2_value > c3_value:
        secondary_score += 20
        evidence.append(f"乙烷碳同位素(δ13C2 = {c2_value:.2f}‰)重于丙烷(δ13C3 = {c3_value:.2f}‰)，指示可能的次生改造")
    
    # 判断最终气源类型
    scores = {
        "生物成因气": bio_score,
        "热成因气": therm_score,
        "混合成因气": mixed_score,
        "次生改造气": secondary_score
    }
    
    max_score_type = max(scores.items(), key=lambda x: x[1])
    source_type = max_score_type[0]
    max_score = max_score_type[1]
    
    # 只有当分数达到一定阈值才确认分类
    if max_score < 20:
        source_type = "未定"
        evidence.append("没有足够强的证据支持特定气源类型")
    
    # 计算置信度
    total_score = sum(scores.values())
    confidence = max_score / 100 if total_score == 0 else max_score / total_score
    
    # 成熟度判断
    if source_type == "热成因气" or source_type == "混合成因气":
        if c1_c2_diff > 20:
            maturity = "低成熟"
            evidence.append(f"C1-C2同位素差值较大({c1_c2_diff:.2f}‰)，指示低成熟度")
        elif 10 < c1_c2_diff <= 20:
            maturity = "中等成熟"
            evidence.append(f"C1-C2同位素差值适中({c1_c2_diff:.2f}‰)，指示中等成熟度")
        elif 0 < c1_c2_diff <= 10:
            maturity = "高成熟"
            evidence.append(f"C1-C2同位素差值较小({c1_c2_diff:.2f}‰)，指示高成熟度")
        elif c1_c2_diff <= 0:
            maturity = "过成熟或次生改造"
            evidence.append(f"C1-C2同位素差值为负({c1_c2_diff:.2f}‰)，指示过成熟或次生改造")
    elif source_type == "生物成因气":
        if c1_value < -70:
            maturity = "CO2还原型"
            evidence.append(f"极轻的甲烷碳同位素值(δ13C1 = {c1_value:.2f}‰)，指示CO2还原型生物气")
        else:
            maturity = "乙酸发酵型"
            evidence.append(f"相对较重的甲烷碳同位素值(δ13C1 = {c1_value:.2f}‰)，指示乙酸发酵型生物气")
    
    return {
        "source_type": source_type,
        "maturity": maturity,
        "confidence": confidence,
        "evidence": evidence
    } 

def generate_gas_source_report(
    global_source: Dict[str, Any], 
    segment_sources: List[Dict[str, Any]],
    global_features: Dict[str, Any],
    profile_file_id: Optional[str] = None
) -> str:
    """
    生成天然气气源分类报告
    
    Args:
        global_source: 全局气源分类结果
        segment_sources: 分段气源分类结果列表
        global_features: 全局特征
        profile_file_id: 深度剖面图的文件ID
        
    Returns:
        格式化的分析报告
    """
    # 提取全局特征
    c1_value = global_features.get("mean_c1_d13c")
    c2_value = global_features.get("mean_c2_d13c")
    c3_value = global_features.get("mean_c3_d13c")
    c1_c2c3_ratio = global_features.get("mean_c1_c2c3_ratio")
    has_reversal = global_features.get("has_isotope_reversal", False)
    
    # 准备报告头部
    report = f"""## 增强版天然气气源分类分析报告

### 总体气源特征:
- **气源类型**: {global_source["source_type"]}
- **成熟度**: {global_source["maturity"]}
- **置信度**: {global_source["confidence"]*100:.1f}%

### 关键指标:
- 甲烷碳同位素(δ13C-CH4): {c1_value:.2f}‰
"""

    if c2_value is not None:
        report += f"- 乙烷碳同位素(δ13C-C2H6): {c2_value:.2f}‰\n"
    if c3_value is not None:
        report += f"- 丙烷碳同位素(δ13C-C3H8): {c3_value:.2f}‰\n"
    if c1_c2c3_ratio is not None:
        report += f"- C1/(C2+C3)比值: {c1_c2c3_ratio:.2f}\n"
    
    report += f"- 同位素倒转现象: {'存在' if has_reversal else '不存在'}\n"
    
    # 添加分类依据
    report += "\n### 分类依据:\n"
    for evidence in global_source["evidence"]:
        report += f"- {evidence}\n"
    
    # 添加深度分段分析
    if segment_sources:
        report += "\n### 深度分段分析:\n"
        
        for segment in segment_sources:
            report += f"#### 深度段 {segment['segment_id']}: {segment['depth_start']:.1f}-{segment['depth_end']:.1f}米\n"
            report += f"- **气源类型**: {segment['source_type']}\n"
            report += f"- **成熟度**: {segment['maturity']}\n"
            report += f"- **置信度**: {segment['confidence']*100:.1f}%\n"
            report += f"- **数据点数量**: {segment['data_points']}\n"
            report += "- **分类依据**:\n"
            
            for evidence in segment["evidence"]:
                report += f"  - {evidence}\n"
    
    # 添加深度变化分析
    if len(segment_sources) > 1:
        report += "\n### 随深度变化分析:\n"
        
        # 检查气源类型变化
        source_types = [s["source_type"] for s in segment_sources]
        unique_sources = set(source_types)
        
        if len(unique_sources) > 1:
            report += "- **气源类型随深度变化明显**\n"
            
            # 气源变化详情
            changes = []
            for i in range(1, len(segment_sources)):
                if segment_sources[i]["source_type"] != segment_sources[i-1]["source_type"]:
                    change_depth = segment_sources[i]["depth_start"]
                    from_type = segment_sources[i-1]["source_type"]
                    to_type = segment_sources[i]["source_type"]
                    changes.append((change_depth, from_type, to_type))
            
            if changes:
                report += "  气源变化位置:\n"
                for depth, from_type, to_type in changes:
                    report += f"  - 深度约{depth:.1f}米: 从{from_type}变为{to_type}\n"
                
                # 变化模式解释
                pattern_desc = ""
                if any("生物成因" in change[1] and "热成因" in change[2] for change in changes):
                    pattern_desc += "  - 存在从生物成因气向热成因气的过渡，可能指示随深度成熟度增加\n"
                elif any("热成因" in change[1] and "生物成因" in change[2] for change in changes):
                    pattern_desc += "  - 存在从热成因气向生物成因气的过渡，可能指示不同来源的气体充注\n"
                
                if any("次生改造" in change[2] for change in changes):
                    pattern_desc += "  - 发现次生改造气，指示可能经历了微生物降解过程\n"
                
                if pattern_desc:
                    report += "\n  变化模式解释:\n" + pattern_desc
        else:
            report += f"- 气源类型在整个研究深度范围内相对稳定，均为**{source_types[0]}**\n"
        
        # 成熟度变化趋势
        maturity_changes = []
        maturity_trend = None
        
        maturity_types = ["低成熟", "中等成熟", "高成熟", "过成熟或次生改造"]
        maturity_ranks = {m: i for i, m in enumerate(maturity_types)}
        
        valid_segments = [s for s in segment_sources if s["maturity"] in maturity_ranks]
        
        if len(valid_segments) > 1:
            depths = [(s["depth_start"] + s["depth_end"]) / 2 for s in valid_segments]
            maturity_values = [maturity_ranks[s["maturity"]] for s in valid_segments]
            
            # 简单线性回归分析趋势
            if len(maturity_values) >= 3:
                slope, _, r_value, _, _ = stats.linregress(depths, maturity_values)
                
                if abs(slope) > 0.001 and abs(r_value) > 0.5:
                    if slope > 0:
                        maturity_trend = "增加"
                        report += "- **成熟度随深度增加**，符合正常埋藏演化规律\n"
                    else:
                        maturity_trend = "降低"
                        report += "- **成熟度随深度降低**，指示可能存在多期充注或垂向运移\n"
            
            # 检查是否有显著变化点
            for i in range(1, len(valid_segments)):
                curr_rank = maturity_ranks[valid_segments[i]["maturity"]]
                prev_rank = maturity_ranks[valid_segments[i-1]["maturity"]]
                
                if abs(curr_rank - prev_rank) >= 2:  # 跨越多个等级
                    change_depth = valid_segments[i]["depth_start"]
                    from_mat = valid_segments[i-1]["maturity"]
                    to_mat = valid_segments[i]["maturity"]
                    maturity_changes.append((change_depth, from_mat, to_mat))
            
            if maturity_changes:
                report += "  成熟度显著变化位置:\n"
                for depth, from_mat, to_mat in maturity_changes:
                    report += f"  - 深度约{depth:.1f}米: 从{from_mat}变为{to_mat}\n"
    
    # 添加资源评价建议
    report += "\n### 资源评价建议:\n"
    
    if global_source["source_type"] == "热成因气":
        report += """- 热成因气具有较好的开发价值，特别是在伴生凝析油或湿气时
- 建议重点关注烃源岩分布、生烃演化史和运移通道
- 评估气藏物性和可采储量"""
        
        if global_source["maturity"] == "高成熟":
            report += "\n- 高成熟气藏通常产气量大，但可能存在氢硫化物等问题，建议评估气体成分"
    elif global_source["source_type"] == "生物成因气":
        report += """- 生物成因气通常位于浅部，开发成本相对较低
- 应重点评估微生物活动区域、有机质分布和封盖条件
- 生物气藏多为连续型，建议评估气体产出的稳定性"""
    elif global_source["source_type"] == "混合成因气":
        report += """- 混合成因气需要综合评估各组分的来源和比例
- 建议进行多样本分析，确定混合气的空间分布规律
- 评估不同气源的贡献及其稳定性"""
    elif global_source["source_type"] == "次生改造气":
        report += """- 次生改造气可能物性复杂，应评估改造程度
- 重点分析微生物活动区域和改造作用强度
- 改造气通常C1含量高但重烃被降解，建议评估经济价值"""
    
    # 如果存在深度分带现象
    if len(segment_sources) > 1 and len(unique_sources) > 1:
        report += "\n- **建议分区开展资源评价，不同深度段可能需要不同的开发策略**"
    
    # 添加图表引用
    if profile_file_id:
        report += f"\n\n### 深度剖面图:\n天然气气源深度剖面图已生成，文件ID：{profile_file_id}\n"
    
    return report

@register_tool(category="iso_logging")
def enhanced_analyze_gas_maturity(file_id: str, depth_segments: bool = True, num_segments: int = 5) -> str:
    """增强版天然气成熟度分析工具
    
    基于碳同位素数据，对天然气样品进行成熟度分析。该增强版工具能够:
    1. 按深度分段分析不同深度区间的成熟度特征
    2. 结合多种成熟度指标进行综合评估
    3. 检测异常成熟度现象和演化模式
    4. 生成成熟度随深度变化的趋势报告
    
    Args:
        file_id: 文件ID，已上传到系统的数据文件
        depth_segments: 是否按深度分段
        num_segments: 深度段数量
        
    Returns:
        包含成熟度分析结果的详细分析报告
    """
    # 获取流写入器
    writer = get_stream_writer()
    
    if writer:
        writer({"custom_step": f"正在进行增强版天然气成熟度分析(文件ID: {file_id})..."})
    
    try:
        # 获取文件信息并读取数据
        file_info = file_manager.get_file_info(file_id)
        if not file_info:
            return f"找不到ID为 {file_id} 的文件。"
            
        file_path = file_info.get("file_path")
        file_type = file_info.get("file_type", "").lower()
        file_name = file_info.get("file_name", "")
        
        df = None
        if file_type in ["csv"]:
            df = pd.read_csv(file_path)
        elif file_type in ["xlsx", "xls"]:
            df = pd.read_excel(file_path)
        else:
            return f"不支持的文件类型: {file_type}。请提供CSV或Excel格式的数据文件。"
        
        # 数据预处理
        df = preprocess_isotope_data(df)
        
        # 从isotope_analysis模块导入辅助函数
        from app.tools.logging.iso_logging.isotope_analysis import (_identify_isotope_columns, 
                                                       _identify_depth_column)
        
        # 识别深度列和同位素列
        depth_col = _identify_depth_column(df)
        isotope_columns = _identify_isotope_columns(df)
        
        # 检查是否有足够的数据进行分析
        required_components = ["C1", "C2"]
        missing_components = []
        
        for component in required_components:
            if not isotope_columns.get(component, []):
                missing_components.append(component)
                
        if missing_components:
            return f"缺少必要的同位素数据列: {', '.join(missing_components)}。成熟度分析至少需要C1、C2的碳同位素数据。"
        
        # 获取碳同位素数据列
        c1_col = isotope_columns["C1"][0]
        c2_col = isotope_columns["C2"][0]
        c3_col = isotope_columns.get("C3", [None])[0]
        
        # 创建分段(如果启用)
        segments = None
        if depth_segments and depth_col and len(df) > 10:
            # 使用甲烷碳同位素列进行分段
            segments = create_depth_segments(
                df, 
                depth_col, 
                c1_col, 
                segment_method="change_point", 
                num_segments=num_segments
            )
            
            if writer:
                writer({"custom_step": f"已创建{len(segments)}个深度分段"})
        
        # 提取全局特征
        global_features = extract_isotope_features(df, isotope_columns, depth_col, segments=None)
        
        # 提取分段特征(如果启用)
        segment_features = []
        if segments:
            for i, (start, end) in enumerate(segments):
                segment_df = df[(df[depth_col] >= start) & (df[depth_col] <= end)]
                if len(segment_df) >= 3:  # 确保每段有足够的数据点
                    feature = extract_isotope_features(segment_df, isotope_columns, depth_col, segments=None)
                    feature["segment_id"] = i + 1
                    feature["depth_start"] = start
                    feature["depth_end"] = end
                    feature["data_points"] = len(segment_df)
                    segment_features.append(feature)
        
        # 基于特征分析成熟度
        # 全局成熟度分析
        global_maturity = analyze_maturity_by_features(global_features)
        
        # 分段成熟度分析
        segment_maturities = []
        if segment_features:
            for feature in segment_features:
                maturity = analyze_maturity_by_features(feature)
                segment_maturities.append({
                    "segment_id": feature["segment_id"],
                    "depth_start": feature["depth_start"],
                    "depth_end": feature["depth_end"],
                    "maturity_level": maturity["maturity_level"],
                    "ro_equivalent": maturity["ro_equivalent"],
                    "confidence": maturity["confidence"],
                    "evidence": maturity["evidence"],
                    "data_points": feature["data_points"]
                })
        
        # 可视化成熟度结果
        if depth_col and len(segment_maturities) > 1:
            # 创建深度-成熟度剖面图
            plt.figure(figsize=(10, 12))
            
            # 成熟度等级颜色映射
            maturity_colors = {
                "未熟": "blue",
                "低成熟": "green",
                "中等成熟": "orange",
                "高成熟": "red",
                "过成熟": "purple"
            }
            
            # Ro当量区间
            ro_ranges = {
                "未熟": (0, 0.5),
                "低成熟": (0.5, 0.8),
                "中等成熟": (0.8, 1.2),
                "高成熟": (1.2, 2.0),
                "过成熟": (2.0, 4.0)
            }
            
            # 定义深度范围
            depth_min = df[depth_col].min()
            depth_max = df[depth_col].max()
            
            # 主图：深度-成熟度
            ax1 = plt.subplot2grid((1, 2), (0, 0))
            
            # 绘制成熟度区间背景
            for level, (min_ro, max_ro) in ro_ranges.items():
                color = maturity_colors.get(level, "gray")
                ax1.axhspan(min_ro, max_ro, color=color, alpha=0.2, label=level)
            
            # 绘制各段Ro当量
            depths = []
            ro_values = []
            
            for segment in segment_maturities:
                mid_depth = (segment["depth_start"] + segment["depth_end"]) / 2
                ro = segment["ro_equivalent"]
                depths.append(mid_depth)
                ro_values.append(ro)
                
                # 绘制点和标签
                ax1.scatter(mid_depth, ro, c=maturity_colors.get(segment["maturity_level"], "gray"), 
                           s=80, edgecolor="black", zorder=5)
                
                ax1.text(mid_depth, ro + 0.1, f"{segment['maturity_level']}\n(Ro={ro:.2f})", 
                        ha='center', va='bottom', fontsize=8)
            
            # 绘制趋势线
            if len(depths) >= 3:
                z = np.polyfit(depths, ro_values, 1)
                p = np.poly1d(z)
                trend_x = np.linspace(min(depths), max(depths), 100)
                ax1.plot(trend_x, p(trend_x), 'k--', alpha=0.7)
                
                # 计算R²
                correlation = np.corrcoef(depths, ro_values)[0, 1]
                r_squared = correlation**2
                ax1.text(0.05, 0.95, f"R² = {r_squared:.2f}", transform=ax1.transAxes, 
                        fontsize=10, va='top')
            
            # 设置轴标签
            ax1.set_xlabel("深度 (m)", fontsize=12)
            ax1.set_ylabel("等效镜质体反射率 (Ro%)", fontsize=12)
            ax1.set_title("深度-成熟度关系", fontsize=14)
            
            # 设置X轴范围
            ax1.set_xlim(depth_min * 0.95, depth_max * 1.05)
            
            # 设置Y轴范围和网格
            ax1.set_ylim(0, 4.0)
            ax1.grid(True, linestyle='--', alpha=0.7)
            
            # 添加图例
            from matplotlib.patches import Patch
            legend_elements = [Patch(facecolor=c, alpha=0.5, label=m) 
                              for m, c in maturity_colors.items()]
            ax1.legend(handles=legend_elements, loc='upper right', fontsize=9)
            
            # 辅助图：同位素差值随深度变化
            ax2 = plt.subplot2grid((1, 2), (0, 1))
            
            # 数据验证
            valid_data_exists = False
            
            # 计算同位素差值
            df["c1_c2_diff"] = df[c2_col] - df[c1_col]
            
            # 过滤有效数据
            valid_diff = df[(~df["c1_c2_diff"].isna()) & (~df[depth_col].isna())]
            
            if len(valid_diff) >= 3:
                valid_data_exists = True
                # 绘制C1-C2差值随深度变化
                ax2.scatter(valid_diff["c1_c2_diff"], valid_diff[depth_col], c='blue', s=30, label='δ13C2-δ13C1')
            else:
                logger.warning("C1-C2差值有效数据点不足")
            
            # 绘制C2-C3差值随深度变化
            if c3_col:
                df["c2_c3_diff"] = df[c3_col] - df[c2_col]
                valid_c2c3_diff = df[(~df["c2_c3_diff"].isna()) & (~df[depth_col].isna())]
                
                if len(valid_c2c3_diff) >= 3:
                    valid_data_exists = True
                    ax2.scatter(valid_c2c3_diff["c2_c3_diff"], valid_c2c3_diff[depth_col], c='red', s=30, label='δ13C3-δ13C2')
                else:
                    logger.warning("C2-C3差值有效数据点不足")
            
            # 如果没有有效数据，添加一个虚拟数据点和文本说明
            if not valid_data_exists:
                # 添加文本说明
                ax2.text(0.5, 0.5, "数据不足", ha='center', va='center', transform=ax2.transAxes,
                       fontsize=12, color='gray')
                logger.warning("同位素差值图表没有足够的有效数据")
            
            # 设置轴标签
            ax2.set_xlabel("同位素差值 (‰)", fontsize=12)
            ax2.set_ylabel("深度 (m)", fontsize=12)
            ax2.set_title("同位素差值-深度关系", fontsize=14)
            
            # 设置Y轴范围和网格
            if valid_data_exists:
                ax2.set_ylim(depth_max * 1.05, depth_min * 0.95)  # 反转Y轴
            else:
                # 使用与左图相同的深度范围
                ax2.set_ylim(ax1.get_ylim())
                
            ax2.grid(True, linestyle='--', alpha=0.7)
            
            # 添加成熟度区间参考线
            ax2.axvline(x=20, color='blue', linestyle=':', alpha=0.7, label='低成熟边界')
            ax2.axvline(x=10, color='orange', linestyle=':', alpha=0.7, label='中成熟边界')
            ax2.axvline(x=5, color='red', linestyle=':', alpha=0.7, label='高成熟边界')
            
            # 添加图例
            ax2.legend(loc='lower right', fontsize=9)
            
            # 保存图表
            output_filename = f"gas_maturity_profile_{os.path.splitext(file_name)[0]}.png"
            output_path = os.path.join(TEMP_PLOT_DIR, output_filename)
            plt.tight_layout()
            plt.savefig(output_path, dpi=300)
            plt.close()
            
            logger.info(f"成功创建天然气成熟度深度剖面图: {output_path}")
            
            # 注册生成的图表为文件
            profile_file_id = file_manager.register_file(
                file_path=output_path,
                file_name=output_filename,
                file_type="png",
                metadata={"description": "天然气成熟度深度剖面图"},
                source="generated",
                session_id=None  # 暂不关联到特定会话
            )
            
            if writer:
                writer({"custom_step": "天然气成熟度深度剖面图创建完成"})
                
                # 发送图片消息，立即推送到前端显示
                image_message = {
                    "image_path": output_path,
                    "title": "天然气成熟度深度剖面图"
                }
                writer({"image_message": image_message})
        else:
            profile_file_id = None
        
        # 生成成熟度分析报告
        result = generate_maturity_report(global_maturity, segment_maturities, global_features, profile_file_id)
        
        if writer:
            writer({"custom_step": "增强版天然气成熟度分析完成\n"})
            
        return result
    except Exception as e:
        error_msg = f"进行增强版天然气成熟度分析时出错: {str(e)}"
        logger.error(error_msg, exc_info=True)
        if writer:
            writer({"custom_step": error_msg})
        return error_msg 

def analyze_maturity_by_features(features: Dict[str, Any]) -> Dict[str, Any]:
    """
    基于提取的特征分析天然气成熟度
    
    Args:
        features: 提取的碳同位素特征字典
        
    Returns:
        包含成熟度等级、Ro当量、置信度和证据的字典
    """
    maturity_level = "未定"
    ro_equivalent = 0.0
    confidence = 0.0
    evidence = []
    
    # 提取关键特征
    c1_value = features.get("mean_c1_d13c")
    c2_value = features.get("mean_c2_d13c")
    c3_value = features.get("mean_c3_d13c")
    has_reversal = features.get("has_isotope_reversal", False)
    
    # 检查是否有足够的特征进行分析
    if c1_value is None or c2_value is None:
        return {
            "maturity_level": "数据不足",
            "ro_equivalent": 0.0,
            "confidence": 0.0,
            "evidence": ["关键同位素数据缺失，无法进行成熟度分析"]
        }
    
    # 计算同位素差值
    c1_c2_diff = c2_value - c1_value
    c2_c3_diff = None
    if c3_value is not None:
        c2_c3_diff = c3_value - c2_value
    
    # 检测同位素倒转现象
    if has_reversal:
        evidence.append("检测到碳同位素倒转现象，可能影响成熟度评估的准确性")
    
    # ==== 基于δ13C1-δ13C2差值的成熟度判断 ====
    if c1_c2_diff > 20:
        maturity_level = "低成熟"
        ro_equivalent = 0.5 + (25 - c1_c2_diff) * 0.02  # 估算Ro值: 0.5-0.8
        evidence.append(f"C1-C2同位素差值较大({c1_c2_diff:.2f}‰)，指示低成熟")
    elif 10 < c1_c2_diff <= 20:
        maturity_level = "中等成熟"
        ro_equivalent = 0.8 + (20 - c1_c2_diff) * 0.04  # 估算Ro值: 0.8-1.2
        evidence.append(f"C1-C2同位素差值适中({c1_c2_diff:.2f}‰)，指示中等成熟")
    elif 0 < c1_c2_diff <= 10:
        maturity_level = "高成熟"
        ro_equivalent = 1.2 + (10 - c1_c2_diff) * 0.08  # 估算Ro值: 1.2-2.0
        evidence.append(f"C1-C2同位素差值较小({c1_c2_diff:.2f}‰)，指示高成熟")
    elif c1_c2_diff <= 0:
        if c1_value < -50:
            maturity_level = "混合或改造气"
            ro_equivalent = 1.0  # 默认中等值
            evidence.append(f"C1-C2同位素差值为负({c1_c2_diff:.2f}‰)，同时C1值较轻，指示可能的混合或次生改造")
        else:
            maturity_level = "过成熟"
            ro_equivalent = 2.0 + min(2.0, abs(c1_c2_diff * 0.5))  # 估算Ro值: >2.0
            evidence.append(f"C1-C2同位素差值为负({c1_c2_diff:.2f}‰)，同时C1值较重，指示可能的过成熟")
    
    # ==== 基于甲烷碳同位素值的成熟度判断 ====
    if -70 < c1_value <= -55:
        if maturity_level == "未定":
            maturity_level = "低成熟"
            ro_equivalent = 0.5 + (-55 - c1_value) * 0.02
        evidence.append(f"甲烷碳同位素值({c1_value:.2f}‰)较轻，支持低成熟判断")
    elif -55 < c1_value <= -40:
        if maturity_level == "未定" or maturity_level == "低成熟":
            maturity_level = "中等成熟"
            ro_equivalent = 0.8 + (-40 - c1_value) * 0.027
        evidence.append(f"甲烷碳同位素值({c1_value:.2f}‰)适中，支持中等成熟判断")
    elif -40 < c1_value <= -30:
        if maturity_level == "未定" or maturity_level in ["低成熟", "中等成熟"]:
            maturity_level = "高成熟"
            ro_equivalent = 1.2 + (-30 - c1_value) * 0.08
        evidence.append(f"甲烷碳同位素值({c1_value:.2f}‰)偏重，支持高成熟判断")
    elif c1_value > -30:
        if maturity_level == "未定" or maturity_level in ["低成熟", "中等成熟", "高成熟"]:
            maturity_level = "过成熟"
            ro_equivalent = 2.0 + min(2.0, (-25 - c1_value) * -0.2)
        evidence.append(f"甲烷碳同位素值({c1_value:.2f}‰)非常重，支持过成熟判断")
    elif c1_value <= -70:
        if "混合或改造气" not in maturity_level:
            evidence.append(f"甲烷碳同位素值({c1_value:.2f}‰)极轻，可能指示生物成因组分或C1选择性富集的影响")
    
    # ==== 基于C2-C3同位素差值的辅助判断 ====
    if c2_c3_diff is not None:
        if c2_c3_diff > 5:
            if maturity_level in ["低成熟", "中等成熟"]:
                evidence.append(f"C2-C3同位素差值较大({c2_c3_diff:.2f}‰)，符合低-中成熟特征")
            else:
                evidence.append(f"C2-C3同位素差值较大({c2_c3_diff:.2f}‰)，与基于C1-C2判断的高成熟存在矛盾")
        elif 0 < c2_c3_diff <= 5:
            if maturity_level in ["中等成熟", "高成熟"]:
                evidence.append(f"C2-C3同位素差值适中({c2_c3_diff:.2f}‰)，符合中-高成熟特征")
        elif c2_c3_diff <= 0:
            if c2_value > c3_value:
                if maturity_level in ["高成熟", "过成熟"]:
                    evidence.append(f"C2-C3同位素差值为负({c2_c3_diff:.2f}‰)，符合高-过成熟或次生改造特征")
                else:
                    evidence.append(f"C2-C3同位素差值为负({c2_c3_diff:.2f}‰)，但与基于C1-C2的低-中成熟判断矛盾")
    
    # 计算置信度
    # 基于证据数量和证据一致性
    evidence_count = len(evidence)
    
    # 检查证据中的矛盾
    contradiction = any("矛盾" in e for e in evidence)
    
    if contradiction:
        confidence = 0.5 + min(0.3, 0.05 * evidence_count)
    else:
        confidence = 0.7 + min(0.3, 0.05 * evidence_count)
    
    # 如果有同位素倒转，降低置信度
    if has_reversal:
        confidence = max(0.3, confidence - 0.2)
    
    # 检查C1-C2差值是否在正常范围内
    if 5 <= c1_c2_diff <= 25:
        confidence = min(0.95, confidence + 0.1)
    elif c1_c2_diff < 0 or c1_c2_diff > 30:
        confidence = max(0.3, confidence - 0.2)
    
    return {
        "maturity_level": maturity_level,
        "ro_equivalent": ro_equivalent,
        "confidence": confidence,
        "evidence": evidence
    }


def generate_maturity_report(
    global_maturity: Dict[str, Any], 
    segment_maturities: List[Dict[str, Any]],
    global_features: Dict[str, Any],
    profile_file_id: Optional[str] = None
) -> str:
    """
    生成天然气成熟度分析报告
    
    Args:
        global_maturity: 全局成熟度分析结果
        segment_maturities: 分段成熟度分析结果列表
        global_features: 全局特征
        profile_file_id: 深度剖面图的文件ID
        
    Returns:
        格式化的分析报告
    """
    # 提取全局特征
    c1_value = global_features.get("mean_c1_d13c")
    c2_value = global_features.get("mean_c2_d13c")
    c3_value = global_features.get("mean_c3_d13c")
    has_reversal = global_features.get("has_isotope_reversal", False)
    
    # 计算差值
    c1_c2_diff = None
    c2_c3_diff = None
    
    if c1_value is not None and c2_value is not None:
        c1_c2_diff = c2_value - c1_value
    
    if c2_value is not None and c3_value is not None:
        c2_c3_diff = c3_value - c2_value
    
    # 准备报告头部
    report = f"""## 增强版天然气成熟度分析报告

### 总体成熟度特征:
- **成熟度等级**: {global_maturity["maturity_level"]}
- **等效镜质体反射率(Ro)**: {global_maturity["ro_equivalent"]:.2f}%
- **置信度**: {global_maturity["confidence"]*100:.1f}%

### 关键指标:
- 甲烷碳同位素(δ13C-CH4): {c1_value:.2f}‰
"""

    if c2_value is not None:
        report += f"- 乙烷碳同位素(δ13C-C2H6): {c2_value:.2f}‰\n"
    if c3_value is not None:
        report += f"- 丙烷碳同位素(δ13C-C3H8): {c3_value:.2f}‰\n"
    if c1_c2_diff is not None:
        report += f"- C1-C2同位素差值: {c1_c2_diff:.2f}‰\n"
    if c2_c3_diff is not None:
        report += f"- C2-C3同位素差值: {c2_c3_diff:.2f}‰\n"
    
    report += f"- 同位素倒转现象: {'存在' if has_reversal else '不存在'}\n"
    
    # 添加分析依据
    report += "\n### 分析依据:\n"
    for evidence in global_maturity["evidence"]:
        report += f"- {evidence}\n"
    
    # 添加深度分段分析
    if segment_maturities:
        report += "\n### 深度分段分析:\n"
        
        for segment in segment_maturities:
            report += f"#### 深度段 {segment['segment_id']}: {segment['depth_start']:.1f}-{segment['depth_end']:.1f}米\n"
            report += f"- **成熟度等级**: {segment['maturity_level']}\n"
            report += f"- **等效镜质体反射率(Ro)**: {segment['ro_equivalent']:.2f}%\n"
            report += f"- **置信度**: {segment['confidence']*100:.1f}%\n"
            report += f"- **数据点数量**: {segment['data_points']}\n"
            report += "- **分析依据**:\n"
            
            for evidence in segment["evidence"]:
                report += f"  - {evidence}\n"
    
    # 添加深度变化分析
    if len(segment_maturities) > 1:
        report += "\n### 随深度变化分析:\n"
        
        # 检查成熟度等级变化
        maturity_levels = [s["maturity_level"] for s in segment_maturities]
        unique_levels = set(maturity_levels)
        
        if len(unique_levels) > 1:
            report += "- **成熟度等级随深度变化明显**\n"
            
            # 分析变化模式
            depths = [(s["depth_start"] + s["depth_end"]) / 2 for s in segment_maturities]
            ro_values = [s["ro_equivalent"] for s in segment_maturities]
            
            # 简单线性回归分析趋势
            if len(ro_values) >= 3:
                slope, intercept, r_value, p_value, std_err = stats.linregress(depths, ro_values)
                
                if abs(slope) > 0.0005 and abs(r_value) > 0.5:  # 有显著变化
                    trend_dir = "增加" if slope > 0 else "降低"
                    report += f"- 成熟度随深度{trend_dir}，平均每100米变化{abs(slope)*100:.2f} Ro\n"
                    
                    # 解释成熟度变化
                    if slope > 0:
                        report += "  - 成熟度随深度增加符合正常埋藏演化规律\n"
                        report += f"  - 该趋势相关性为R={r_value:.2f}，统计学显著性p={p_value:.4f}\n"
                    else:
                        report += "  - 成熟度随深度降低不符合正常埋藏规律，可能指示:\n"
                        report += "    1. 多期不同成熟度气体充注\n"
                        report += "    2. 断层或岩浆活动导致的温度异常\n"
                        report += "    3. 倒置地层或构造运动影响\n"
                else:
                    report += "- 成熟度随深度变化不明显或不规则\n"
            
            # 检查是否有明显的成熟度跃变带
            maturity_ranks = {"低成熟": 1, "中等成熟": 2, "高成熟": 3, "过成熟": 4}
            
            changes = []
            for i in range(1, len(segment_maturities)):
                curr = segment_maturities[i]["maturity_level"]
                prev = segment_maturities[i-1]["maturity_level"]
                
                if curr in maturity_ranks and prev in maturity_ranks:
                    if abs(maturity_ranks[curr] - maturity_ranks[prev]) >= 2:  # 跨越多个等级
                        change_depth = segment_maturities[i]["depth_start"]
                        changes.append((change_depth, prev, curr))
            
            if changes:
                report += "  成熟度显著跃变位置:\n"
                for depth, from_mat, to_mat in changes:
                    report += f"  - 深度约{depth:.1f}米: 从{from_mat}跃变为{to_mat}\n"
                
                report += "  这种明显跃变可能指示:\n"
                report += "  - 构造活动导致的地层错断\n"
                report += "  - 不同来源气体的充注界面\n"
                report += "  - 次生改造强度的明显变化\n"
        else:
            report += f"- 成熟度等级在整个研究深度范围内相对稳定，均为**{maturity_levels[0]}**\n"
    
    # 添加资源评价建议
    report += "\n### 勘探开发建议:\n"
    
    if global_maturity["maturity_level"] == "低成熟":
        report += """- 低成熟天然气通常含烃组分相对较少，但含凝析油可能性高
- 重点关注：
  1. 烃源岩有机质类型和丰度
  2. 运移通道和圈闭条件
  3. 油气比评估，可能的凝析油资源
- 开发建议：低成熟气通常压力较低，初期产量可能不高，需设计合适的开发方案"""
    elif global_maturity["maturity_level"] == "中等成熟":
        report += """- 中等成熟天然气是常规油气勘探的主要目标，综合性状较好
- 重点关注：
  1. 储层物性和非均质性
  2. 圈闭类型和封盖条件
  3. 气体组分评估
- 开发建议：中等成熟气通常开发经济性较好，建议综合评价各类储层类型"""
    elif global_maturity["maturity_level"] == "高成熟":
        report += """- 高成熟天然气通常含甲烷比例高，重烃含量低，产量可能较大
- 重点关注：
  1. 储层保存条件
  2. 裂缝发育程度
  3. 可能的非烃组分(如H2S、CO2)含量
- 开发建议：高成熟气藏可能存在腐蚀性组分，注意材料选择和环保问题"""
    elif global_maturity["maturity_level"] == "过成熟":
        report += """- 过成熟天然气以干气为主，甲烷含量极高
- 重点关注：
  1. 储层超压条件
  2. 非烃组分含量(CO2可能较高)
  3. 深层储层物性
- 开发建议：过成熟气藏通常埋深大，开发难度和成本高，需特别关注工程技术挑战"""
    elif "混合" in global_maturity["maturity_level"] or "改造" in global_maturity["maturity_level"]:
        report += """- 混合气或次生改造气组分和产能特性复杂
- 重点关注：
  1. 各组分来源和混合比例
  2. 改造程度评估
  3. 微生物活动带边界
- 开发建议：需进行详细的气体组分分析和试采测试，评估稳定产气能力"""
    
    # 如果存在深度分带现象
    if len(segment_maturities) > 1 and len(unique_levels) > 1:
        report += "\n- **建议分区开展成熟度评价，针对不同深度段制定差异化开发策略**"
    
    # 添加图表引用
    if profile_file_id:
        report += f"\n\n### 深度剖面图:\n天然气成熟度深度剖面图已生成，文件ID：{profile_file_id}\n"
    
    return report 