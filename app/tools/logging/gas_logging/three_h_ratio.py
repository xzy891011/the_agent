#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
3H比值法解释气层、油层、干层工具

基于湿度比(WH)、平衡比(BH)、特征比(CH)进行地层含油气水情况综合判断
"""

import os
import re
import platform
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from io import BytesIO
import logging
from typing import Optional

from langgraph.config import get_stream_writer
from app.tools.registry import register_tool
from app.core.file_manager import FileManager

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

def calculate_3h_ratios(c1: np.ndarray, c2: np.ndarray, c3: np.ndarray, 
                       c4: np.ndarray, c5: np.ndarray) -> tuple:
    """计算3H比值
    
    Args:
        c1-c5: 各组分含量数组
        
    Returns:
        (湿度比WH, 平衡比BH, 特征比CH)
    """
    # 避免除零错误，将零值替换为极小数
    epsilon = 1e-10
    
    # 湿度比：WH=(C2+C3+C4+C5)/(C1+C2+C3+C4+C5)
    total_hydrocarbons = c1 + c2 + c3 + c4 + c5
    wet_components = c2 + c3 + c4 + c5
    wh = wet_components / np.maximum(total_hydrocarbons, epsilon)
    wh = wh * 100  # 转换为百分比
    
    # 平衡比：BH=(C1+C2)/(C3+C4+C5)
    light_components = c1 + c2
    heavy_components = c3 + c4 + c5
    bh = light_components / np.maximum(heavy_components, epsilon)
    
    # 特征比：CH=(C4+C5)/C3
    c45_components = c4 + c5
    ch = c45_components / np.maximum(c3, epsilon)
    
    return wh, bh, ch

def interpret_3h_ratios(wh: np.ndarray, bh: np.ndarray, ch: np.ndarray) -> np.ndarray:
    """根据3H比值进行解释
    
    Args:
        wh: 湿度比数组
        bh: 平衡比数组  
        ch: 特征比数组
        
    Returns:
        解释结果数组
    """
    results = np.full(len(wh), '', dtype=object)
    
    for i in range(len(wh)):
        wh_val = wh[i]
        bh_val = bh[i]
        ch_val = ch[i]
        
        # 检查是否为有效数值
        if np.isnan(wh_val) or np.isnan(bh_val) or np.isnan(ch_val):
            results[i] = '无效数据'
            continue
            
        # 解释规则
        if wh_val < 0.5 and bh_val > 100:
            results[i] = '干层'
        elif 0.5 <= wh_val <= 12.5 and ch_val < 0.6:
            if wh_val < 2:
                results[i] = '干气层'
            elif wh_val < 8:
                results[i] = '湿气层'
            else:
                results[i] = '凝析气层'
        elif 12.5 < wh_val <= 40 and ch_val >= 0.6:
            if 30 <= wh_val <= 40:
                results[i] = '轻质油层'
            else:
                results[i] = '油层'
        elif wh_val > 40:
            results[i] = '干层'
        else:
            # 边界条件或不符合标准规则的情况
            if wh_val <= 0.5:
                results[i] = '疑似干层'
            elif wh_val > 40:
                results[i] = '疑似干层'
            else:
                results[i] = '过渡层'
    
    return results

def get_interpretation_confidence(wh: np.ndarray, bh: np.ndarray, ch: np.ndarray, 
                                interpretation: np.ndarray) -> np.ndarray:
    """计算解释置信度
    
    Args:
        wh, bh, ch: 3H比值数组
        interpretation: 解释结果数组
        
    Returns:
        置信度数组(0-100)
    """
    confidence = np.zeros(len(wh))
    
    for i in range(len(wh)):
        wh_val = wh[i]
        bh_val = bh[i] 
        ch_val = ch[i]
        interp = interpretation[i]
        
        if np.isnan(wh_val) or np.isnan(bh_val) or np.isnan(ch_val):
            confidence[i] = 0
            continue
            
        # 根据距离判别边界的远近计算置信度
        if interp == '干层':
            if wh_val < 0.2 and bh_val > 200:
                confidence[i] = 95
            elif wh_val < 0.5 and bh_val > 100:
                confidence[i] = 85
            elif wh_val > 40:
                confidence[i] = 80
            else:
                confidence[i] = 70
        elif '气层' in interp:
            if 1 <= wh_val <= 10 and ch_val < 0.4:
                confidence[i] = 90
            elif 0.5 <= wh_val <= 12.5 and ch_val < 0.6:
                confidence[i] = 80
            else:
                confidence[i] = 70
        elif '油层' in interp:
            if 15 <= wh_val <= 35 and ch_val > 0.8:
                confidence[i] = 90
            elif 12.5 < wh_val <= 40 and ch_val >= 0.6:
                confidence[i] = 80
            else:
                confidence[i] = 70
        else:
            confidence[i] = 50  # 过渡层等不确定情况
    
    return confidence

def create_3h_visualization(df: pd.DataFrame, output_path: str) -> str:
    """创建3H比值法可视化图表
    
    Args:
        df: 包含3H比值解释结果的数据框
        output_path: 输出图片路径
        
    Returns:
        图片文件路径
    """
    try:
        # 设置matplotlib使用Agg后端
        import matplotlib
        matplotlib.use('Agg')
        
        setup_chinese_font()
        
        # 清理matplotlib状态
        plt.clf()
        plt.close('all')
        
        logger.info("开始创建3H比值法可视化图表")
        logger.info(f"数据行数: {len(df)}, 列名: {list(df.columns)}")
        
        # 数据预处理
        depths = pd.to_numeric(df['Depth'], errors='coerce')
        wh_values = pd.to_numeric(df['湿度比WH'], errors='coerce') if '湿度比WH' in df.columns else None
        bh_values = pd.to_numeric(df['平衡比BH'], errors='coerce') if '平衡比BH' in df.columns else None
        ch_values = pd.to_numeric(df['特征比CH'], errors='coerce') if '特征比CH' in df.columns else None
        
        # 过滤有效数据
        if depths is not None and wh_values is not None:
            valid_mask = pd.notna(depths) & pd.notna(wh_values) & (depths > 0)
            valid_depths = depths[valid_mask]
            valid_wh = wh_values[valid_mask]
            valid_bh = bh_values[valid_mask] if bh_values is not None else None
            valid_ch = ch_values[valid_mask] if ch_values is not None else None
            
            logger.info(f"有效数据点数: {len(valid_depths)}")
            logger.info(f"深度范围: {valid_depths.min():.1f} - {valid_depths.max():.1f} m")
            logger.info(f"WH值范围: {valid_wh.min():.3f} - {valid_wh.max():.3f} %")
        else:
            logger.error("缺少深度或WH数据，无法创建图表")
            return ""
        
        # 强制设置图形参数确保可见性
        plt.rcParams['figure.facecolor'] = 'white'
        plt.rcParams['axes.facecolor'] = 'white'
        plt.rcParams['text.color'] = 'black'
        plt.rcParams['axes.labelcolor'] = 'black'
        plt.rcParams['xtick.color'] = 'black'
        plt.rcParams['ytick.color'] = 'black'
        
        # 创建图表
        fig = plt.figure(figsize=(16, 12), facecolor='white')
        fig.patch.set_facecolor('white')
        fig.suptitle('3H比值法气层油层解释图表', fontsize=16, fontweight='bold', color='black')
        
        # 图1：湿度比WH深度剖面图
        ax1 = plt.subplot(2, 2, 1)
        ax1.set_facecolor('white')
        logger.info("绘制图1：湿度比WH深度剖面图")
        try:
            ax1.plot(valid_wh, valid_depths, linewidth=1, color='blue', alpha=0.8)
            ax1.invert_yaxis()
            ax1.set_xlabel('湿度比WH (%)', fontsize=12, color='black')
            ax1.set_ylabel('深度 (m)', fontsize=12, color='black')
            ax1.set_title('湿度比WH深度剖面图', fontsize=14, fontweight='bold', color='black')
            ax1.grid(True, alpha=0.3)
            
            # 智能设置坐标轴范围，确保数据可见
            wh_min, wh_max = valid_wh.min(), valid_wh.max()
            logger.info(f"WH值统计: min={wh_min:.3f}, max={wh_max:.3f}")
            
            if wh_max > wh_min:
                x_min = 0
                x_max = max(50, wh_max + 5)  # 至少显示到50%
                ax1.set_xlim(x_min, x_max)
                logger.info(f"设置图1 X轴范围: {x_min} - {x_max}")
            else:
                ax1.set_xlim(0, 50)
            
            # 添加解释标准参考线
            ax1.axvline(x=0.5, color='red', linestyle='--', alpha=0.8, linewidth=2, label='0.5%')
            ax1.axvline(x=12.5, color='orange', linestyle='--', alpha=0.8, linewidth=2, label='12.5%')
            ax1.axvline(x=30, color='green', linestyle='--', alpha=0.8, linewidth=2, label='30%')
            ax1.axvline(x=40, color='purple', linestyle='--', alpha=0.8, linewidth=2, label='40%')
            ax1.legend(fontsize=9)
            
        except Exception as e:
            logger.error(f"绘制图1失败: {e}")
            ax1.text(0.5, 0.5, f'图1绘制失败: {str(e)}', transform=ax1.transAxes, 
                    ha='center', va='center', fontsize=12, color='red')
        
        # 图2：平衡比BH深度剖面图
        ax2 = plt.subplot(2, 2, 2)
        ax2.set_facecolor('white')
        logger.info("绘制图2：平衡比BH深度剖面图")
        try:
            if valid_bh is not None and len(valid_bh) > 0:
                # 处理极值，避免对数刻度问题
                valid_bh_clean = valid_bh[valid_bh > 0]  # 只取正值
                valid_depths_clean = valid_depths[valid_bh > 0]
                
                if len(valid_bh_clean) > 0:
                    # 对数刻度更适合显示平衡比的大范围变化
                    ax2.semilogx(valid_bh_clean, valid_depths_clean, linewidth=1, color='green', alpha=0.8)
                    ax2.invert_yaxis()
                    ax2.set_xlabel('平衡比BH (对数刻度)', fontsize=12, color='black')
                    ax2.set_ylabel('深度 (m)', fontsize=12, color='black')
                    ax2.set_title('平衡比BH深度剖面图', fontsize=14, fontweight='bold', color='black')
                    ax2.grid(True, alpha=0.3)
                    
                    # 记录BH数据范围
                    bh_min, bh_max = valid_bh_clean.min(), valid_bh_clean.max()
                    logger.info(f"BH值统计: min={bh_min:.3f}, max={bh_max:.3f}")
                    
                    # 添加参考线
                    if 100 >= bh_min and 100 <= bh_max * 10:  # 确保参考线在合理范围内
                        ax2.axvline(x=100, color='red', linestyle='--', alpha=0.8, linewidth=2, label='100')
                        ax2.legend(fontsize=9)
                else:
                    ax2.text(0.5, 0.5, '无有效平衡比数据(≤0)', transform=ax2.transAxes, 
                            ha='center', va='center', fontsize=14, color='red', weight='bold')
                    ax2.set_xlabel('平衡比BH (对数刻度)', fontsize=12, color='black')
                    ax2.set_ylabel('深度 (m)', fontsize=12, color='black')
                    ax2.set_title('平衡比BH深度剖面图', fontsize=14, fontweight='bold', color='black')
            else:
                ax2.text(0.5, 0.5, '无平衡比数据', transform=ax2.transAxes, 
                        ha='center', va='center', fontsize=14, color='red', weight='bold')
                ax2.set_xlabel('平衡比BH (对数刻度)', fontsize=12, color='black')
                ax2.set_ylabel('深度 (m)', fontsize=12, color='black')
                ax2.set_title('平衡比BH深度剖面图', fontsize=14, fontweight='bold', color='black')
        except Exception as e:
            logger.error(f"绘制图2失败: {e}")
            ax2.text(0.5, 0.5, f'图2绘制失败: {str(e)}', transform=ax2.transAxes, 
                    ha='center', va='center', fontsize=12, color='red')
        
        # 图3：解释结果分布饼图
        ax3 = plt.subplot(2, 2, 3)
        ax3.set_facecolor('white')
        logger.info("绘制图3：解释结果分布饼图")
        try:
            if '3H解释结果' in df.columns:
                result_counts = df['3H解释结果'].value_counts()
                logger.info(f"解释结果统计: {dict(result_counts)}")
                
                if len(result_counts) > 0:
                    colors = {'干层': '#D3D3D3', '干气层': '#87CEEB', '湿气层': '#FFE4B5', 
                             '凝析气层': '#98FB98', '油层': '#90EE90', '轻质油层': '#FFA07A',
                             '过渡层': '#DDA0DD', '疑似干层': '#F0F0F0', '无效数据': '#696969'}
                    pie_colors = [colors.get(result, '#D3D3D3') for result in result_counts.index]
                    
                    # 计算百分比，调整标签显示
                    total = result_counts.sum()
                    percentages = (result_counts / total * 100).round(1)
                    
                    def autopct_format(pct):
                        return f'{pct:.1f}%' if pct >= 1.0 else ''
                    
                    labels = []
                    for i, (result, count) in enumerate(result_counts.items()):
                        pct = percentages.iloc[i]
                        if pct >= 2.0:
                            labels.append(result)
                        elif pct >= 0.5:
                            labels.append(result[:3])  # 简化标签
                        else:
                            labels.append('')
                    
                    wedges, texts, autotexts = ax3.pie(
                        result_counts.values, 
                        labels=labels,
                        autopct=autopct_format,
                        colors=pie_colors, 
                        startangle=45,
                        labeldistance=1.15,
                        pctdistance=0.85,
                        wedgeprops=dict(edgecolor='white', linewidth=1)  # 添加白色边框分隔
                    )
                    
                    # 设置文字样式
                    for text in texts:
                        text.set_color('black')
                        text.set_fontsize(9)
                        text.set_weight('normal')
                    for autotext in autotexts:
                        autotext.set_color('black')
                        autotext.set_fontsize(8)
                        autotext.set_weight('bold')
                    
                    # 添加图例
                    if any(percentages < 2.0):
                        legend_labels = []
                        for i, (result, count) in enumerate(result_counts.items()):
                            pct = percentages.iloc[i]
                            legend_labels.append(f'{result}: {pct:.1f}%')
                        
                        ax3.legend(wedges, legend_labels, 
                                  loc='upper center', bbox_to_anchor=(0.5, -0.05),
                                  ncol=2, fontsize=7)
                    
                    ax3.set_title('3H解释结果分布统计', fontsize=14, fontweight='bold', color='black')
                    logger.info(f"图3绘制完成，层型数量: {len(result_counts)}")
                else:
                    ax3.text(0.5, 0.5, '无解释结果数据', transform=ax3.transAxes, 
                            ha='center', va='center', fontsize=14, color='red', weight='bold')
                    ax3.set_title('3H解释结果分布统计', fontsize=14, fontweight='bold', color='black')
            else:
                ax3.text(0.5, 0.5, '缺少解释结果列', transform=ax3.transAxes, 
                        ha='center', va='center', fontsize=14, color='red', weight='bold')
                ax3.set_title('3H解释结果分布统计', fontsize=14, fontweight='bold', color='black')
        except Exception as e:
            logger.error(f"绘制图3失败: {e}")
            ax3.text(0.5, 0.5, f'图3绘制失败: {str(e)}', transform=ax3.transAxes, 
                    ha='center', va='center', fontsize=12, color='red')
        
        # 图4：特征比CH vs 湿度比WH散点图
        ax4 = plt.subplot(2, 2, 4)
        ax4.set_facecolor('white')
        logger.info("绘制图4：CH-WH关系散点图")
        try:
            if valid_ch is not None and len(valid_ch) > 0:
                # 过滤有效的CH数据
                valid_ch_mask = pd.notna(valid_ch) & (valid_ch >= 0)
                valid_ch_clean = valid_ch[valid_ch_mask]
                valid_wh_clean = valid_wh[valid_ch_mask]
                
                if len(valid_ch_clean) > 0:
                    # 根据解释结果着色
                    if '3H解释结果' in df.columns:
                        results = df['3H解释结果'][valid_mask]
                        results_clean = results[valid_ch_mask]
                        color_map = {'干层': 'gray', '干气层': 'lightblue', '湿气层': 'yellow', 
                                   '凝析气层': 'lightgreen', '油层': 'green', '轻质油层': 'orange',
                                   '过渡层': 'purple', '疑似干层': 'lightgray', '无效数据': 'black'}
                        colors_scatter = [color_map.get(r, 'blue') for r in results_clean]
                    else:
                        colors_scatter = 'blue'
                    
                    ax4.scatter(valid_wh_clean, valid_ch_clean, c=colors_scatter, alpha=0.6, s=20, edgecolors='black', linewidth=0.3)
                    ax4.set_xlabel('湿度比WH (%)', fontsize=12, color='black')
                    ax4.set_ylabel('特征比CH', fontsize=12, color='black')
                    ax4.set_title('CH-WH关系散点图', fontsize=14, fontweight='bold', color='black')
                    ax4.grid(True, alpha=0.3)
                    
                    # 设置坐标轴范围
                    wh_range = valid_wh_clean.max() - valid_wh_clean.min()
                    ch_range = valid_ch_clean.max() - valid_ch_clean.min()
                    
                    x_min = max(0, valid_wh_clean.min() - wh_range * 0.1)
                    x_max = min(50, valid_wh_clean.max() + wh_range * 0.1)
                    y_min = max(0, valid_ch_clean.min() - ch_range * 0.1)
                    y_max = valid_ch_clean.max() + ch_range * 0.1
                    
                    ax4.set_xlim(x_min, x_max)
                    ax4.set_ylim(y_min, y_max)
                    
                    logger.info(f"散点图范围 - X: {x_min:.2f}-{x_max:.2f}, Y: {y_min:.2f}-{y_max:.2f}")
                    
                    # 添加判别区域分界线
                    if x_min <= 0.5 <= x_max:
                        ax4.axvline(x=0.5, color='red', linestyle='--', alpha=0.8, linewidth=1)
                    if x_min <= 12.5 <= x_max:
                        ax4.axvline(x=12.5, color='red', linestyle='--', alpha=0.8, linewidth=1)
                    if x_min <= 40 <= x_max:
                        ax4.axvline(x=40, color='red', linestyle='--', alpha=0.8, linewidth=1)
                    if y_min <= 0.6 <= y_max:
                        ax4.axhline(y=0.6, color='red', linestyle='--', alpha=0.8, linewidth=1)
                    
                    # 添加区域标注（只在合理范围内）
                    if x_min <= 0.25 <= x_max and y_min <= 0.8 <= y_max:
                        ax4.text(0.25, 0.8, '干层区', fontsize=10, ha='center', color='red', weight='bold', 
                                bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.7))
                    if x_min <= 6 <= x_max and y_min <= 0.3 <= y_max:
                        ax4.text(6, 0.3, '气层区', fontsize=10, ha='center', color='blue', weight='bold',
                                bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.7))
                    if x_min <= 25 <= x_max and y_min <= 0.8 <= y_max:
                        ax4.text(25, 0.8, '油层区', fontsize=10, ha='center', color='green', weight='bold',
                                bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.7))
                    
                    logger.info(f"图4绘制完成，数据点数: {len(valid_ch_clean)}")
                else:
                    ax4.text(0.5, 0.5, '无有效特征比数据(CH<0)', transform=ax4.transAxes, 
                            ha='center', va='center', fontsize=14, color='red', weight='bold')
                    ax4.set_xlabel('湿度比WH (%)', fontsize=12, color='black')
                    ax4.set_ylabel('特征比CH', fontsize=12, color='black')
                    ax4.set_title('CH-WH关系散点图', fontsize=14, fontweight='bold', color='black')
            else:
                ax4.text(0.5, 0.5, '无特征比数据', transform=ax4.transAxes, 
                        ha='center', va='center', fontsize=14, color='red', weight='bold')
                ax4.set_xlabel('湿度比WH (%)', fontsize=12, color='black')
                ax4.set_ylabel('特征比CH', fontsize=12, color='black')
                ax4.set_title('CH-WH关系散点图', fontsize=14, fontweight='bold', color='black')
        except Exception as e:
            logger.error(f"绘制图4失败: {e}")
            ax4.text(0.5, 0.5, f'图4绘制失败: {str(e)}', transform=ax4.transAxes, 
                    ha='center', va='center', fontsize=12, color='red')
        
        # 调整布局并保存
        logger.info("调整布局并保存图片...")
        plt.tight_layout(rect=[0, 0.02, 1, 0.96])
        
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # 保存图片
        plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white', 
                   edgecolor='none', format='png', transparent=False)
        
        # 检查图片是否成功生成
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            logger.info(f"3H比值法可视化图表已保存: {output_path}, 文件大小: {file_size} 字节")
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
    """判断文件是否为已解释的文件"""
    return "_interpreted" in filename

def remove_file_id_prefix(filename: str) -> str:
    """移除文件名中的file_id前缀"""
    pattern = r'^[ug]-[a-f0-9]{8}_'
    return re.sub(pattern, '', filename)

@register_tool(category="gas_logging")
def three_h_ratio_analysis(file_id: str) -> str:
    """气测录井分析第三步-3H比值法解释气层油层干层工具
    
    基于湿度比(WH)、平衡比(BH)、特征比(CH)进行地层含油气水情况综合判断
    
    计算公式：
    - 湿度比：WH=(C2+C3+C4+C5)/(C1+C2+C3+C4+C5)  
    - 平衡比：BH=(C1+C2)/(C3+C4+C5)
    - 特征比：CH=(C4+C5)/C3
    
    解释规则：
    - WH<0.5 且 BH>100：干层
    - 0.5<WH<12.5 且 CH<0.6：可采气（根据WH细分为干气、湿气、凝析气）
    - 12.5<WH<40 且 CH>0.6：可采油
    - 30<WH<40：轻质油层  
    - WH>40：干层
    
    Args:
        file_id: Excel文件ID，可以是原始上传文件或前一工具生成的解释文件。
                如果是在其他录井工具之后执行，应使用前一工具返回信息中的NEXT_FILE_ID，
                以在已有解释结果基础上追加新的分析列。
                文件应包含Well、Depth、C1、C2、C3、C4、C5等列。
        
    Returns:
        分析结果报告，包含新生成文件的NEXT_FILE_ID供后续工具使用
    """
    writer = get_stream_writer()
    
    try:
        if writer:
            writer({"custom_step": "开始3H比值法解释分析..."})
        
        file_manager = FileManager()
        
        # 获取文件信息并读取数据
        file_info = file_manager.get_file_info(file_id)
        if not file_info:
            raise ValueError(f"未找到文件ID: {file_id}")
        
        file_path = file_info.get("file_path")
        file_name = file_info.get("file_name", "")
        
        if writer:
            writer({"custom_step": f"正在处理文件: {file_name}"})
        
        logger.info(f"开始处理文件: {file_path}")
        
        # 智能读取Excel文件头部结构
        header_df = pd.read_excel(file_path, nrows=2)
        logger.info(f"原始表头结构: {header_df.shape}")
        
        # 检查第一行是否是表头，第二行是否是数据
        first_row = header_df.iloc[0].tolist()
        second_row = header_df.iloc[1].tolist() if len(header_df) > 1 else []
        
        # 判断是否为中文表头
        chinese_headers_list_for_detection = ['井名', '井深', '钻时', '全量', '甲烷', '乙烷', '丙烷', '异丁烷', '正丁烷', '异戊烷', '正戊烷']
        is_chinese_header = any(str(cell) in chinese_headers_list_for_detection for cell in first_row if not pd.isna(cell))
        
        # 判断第二行是否是数据（主要包含数值）
        second_row_is_data = len(second_row) > 0 and sum(1 for cell in second_row if isinstance(cell, (int, float)) and not pd.isna(cell)) > len(second_row) / 2
        
        if is_chinese_header and second_row_is_data:
            skip_rows = 1
            logger.info("检测到单行中文表头，跳过1行读取数据")
        else:
            skip_rows = 2
            logger.info("使用默认设置，跳过2行读取数据")
        
        # 读取数据部分
        data_df = pd.read_excel(file_path, skiprows=skip_rows)
        logger.info(f"成功读取Excel文件，跳过{skip_rows}行表头，共{len(data_df)}行数据")
        
        logger.info(f"第一行内容: {first_row}")
        logger.info(f"第二行内容: {second_row}")
        
        # 中文到英文的列名映射
        chinese_to_english = {
            '井名': 'Well', '井深': 'Depth', '钻时': 'Rop', '全量': 'Tg',
            '甲烷': 'C1', '乙烷': 'C2', '丙烷': 'C3', '异丁烷': 'iC4', '正丁烷': 'nC4',
            '异戊烷': 'iC5', '正戊烷': 'nC5', '二氧化碳': 'CO2', '其它非烃': 'Other'
        }
        
        # 检查第一行是否是中文表头（用于列名转换）
        is_chinese_header_for_columns = any(str(cell) in chinese_to_english for cell in first_row if not pd.isna(cell))
        
        if is_chinese_header_for_columns:
            logger.info("检测到中文表头，转换为英文列名")
            english_headers = []
            chinese_headers_list = []
            
            for i, cell in enumerate(first_row):
                if pd.isna(cell) or str(cell).strip() == '':
                    english_headers.append(f"Col{i}")
                    chinese_headers_list.append(f"列{i}")
                else:
                    cell_str = str(cell).strip()
                    if cell_str in chinese_to_english:
                        english_headers.append(chinese_to_english[cell_str])
                        chinese_headers_list.append(cell_str)
                    else:
                        english_headers.append(f"Col{i}")
                        chinese_headers_list.append(cell_str)
            
            # 使用英文列名
            if len(english_headers) >= len(data_df.columns):
                data_df.columns = english_headers[:len(data_df.columns)]
                logger.info(f"使用转换后的英文列名: {list(data_df.columns)}")
            else:
                final_columns = english_headers + [f"Col{i}" for i in range(len(english_headers), len(data_df.columns))]
                data_df.columns = final_columns
                logger.info(f"补充列名后使用: {list(data_df.columns)}")
                
            # 保存原始表头用于重建
            original_chinese_headers = chinese_headers_list[:len(data_df.columns)]
            original_english_headers = english_headers[:len(data_df.columns)]
            
        else:
            logger.info("未检测到标准中文表头，使用默认列名")
            default_columns = ["Well", "Depth", "Rop", "Tg", "C1", "C2", "C3", "iC4", "nC4", "iC5", "nC5", "CO2", "Other"]
            data_df.columns = default_columns[:len(data_df.columns)]
            logger.info(f"使用默认英文列名: {list(data_df.columns)}")
            
            original_english_headers = list(data_df.columns)
            original_chinese_headers = ['井名', '井深', '钻时', '全量', '甲烷', '乙烷', '丙烷', '异丁烷', '正丁烷', '异戊烷', '正戊烷', '二氧化碳', '其它非烃'][:len(data_df.columns)]
        
        # 数据清理和验证
        df = data_df.dropna(subset=['Well', 'Depth'])
        logger.info(f"数据清理后，共{len(df)}行有效数据")
        
        # 检查必需的组分列
        required_components = ['C1', 'C2', 'C3']
        missing_components = [col for col in required_components if col not in df.columns]
        if missing_components:
            raise ValueError(f"缺少必需的组分列: {missing_components}")
        
        # 处理C4和C5组分（可能是iC4+nC4, iC5+nC5）
        added_c4 = False
        added_c5 = False
        
        if 'C4' not in df.columns:
            if 'iC4' in df.columns and 'nC4' in df.columns:
                df['C4'] = pd.to_numeric(df['iC4'], errors='coerce') + pd.to_numeric(df['nC4'], errors='coerce')
                logger.info("通过iC4+nC4计算C4组分")
                added_c4 = True
            else:
                logger.warning("缺少C4组分数据，将使用0值")
                df['C4'] = 0
                added_c4 = True
        
        if 'C5' not in df.columns:
            if 'iC5' in df.columns and 'nC5' in df.columns:
                df['C5'] = pd.to_numeric(df['iC5'], errors='coerce') + pd.to_numeric(df['nC5'], errors='coerce')
                logger.info("通过iC5+nC5计算C5组分")
                added_c5 = True
            else:
                logger.warning("缺少C5组分数据，将使用0值")
                df['C5'] = 0
                added_c5 = True
        
        # 转换组分数据为数值类型
        for comp in ['C1', 'C2', 'C3', 'C4', 'C5']:
            df[comp] = pd.to_numeric(df[comp], errors='coerce').fillna(0)
        
        logger.info("开始计算3H比值...")
        
        # 计算3H比值
        wh, bh, ch = calculate_3h_ratios(
            df['C1'].values, df['C2'].values, df['C3'].values,
            df['C4'].values, df['C5'].values
        )
        
        logger.info("开始进行3H解释...")
        
        # 进行解释
        interpretation = interpret_3h_ratios(wh, bh, ch)
        confidence = get_interpretation_confidence(wh, bh, ch, interpretation)
        
        # 添加计算结果到数据框
        df['湿度比WH'] = wh
        df['平衡比BH'] = bh
        df['特征比CH'] = ch
        df['3H解释结果'] = interpretation
        df['置信度'] = confidence
        
        logger.info("开始重建Excel文件结构...")
        
        # 重建Excel文件，保持原始两行表头格式
        # 1. 计算原始数据列数（排除新增列）
        original_data_columns = len(data_df.columns)
        clean_english_headers = original_english_headers[:original_data_columns]
        clean_chinese_headers = original_chinese_headers[:original_data_columns]
        
        # 确保长度足够
        while len(clean_english_headers) < original_data_columns:
            clean_english_headers.append(f"Col{len(clean_english_headers)+1}")
        while len(clean_chinese_headers) < original_data_columns:
            clean_chinese_headers.append(f"列{len(clean_chinese_headers)+1}")
        
        # 2. 为新增列添加表头
        new_english_headers = []
        new_chinese_headers = []
        
        # 为新添加的C4列添加表头
        if added_c4:
            new_english_headers.append('C4')
            new_chinese_headers.append('丁烷C4')
            
        # 为新添加的C5列添加表头  
        if added_c5:
            new_english_headers.append('C5')
            new_chinese_headers.append('戊烷C5')
        
        # 添加3H分析结果的表头
        new_english_headers.extend(['WH', 'BH', 'CH', '3H_Result', 'Confidence'])
        new_chinese_headers.extend(['湿度比WH', '平衡比BH', '特征比CH', '3H解释结果', '置信度'])
        
        # 3. 合并表头（原始表头 + 新增表头）
        full_english_headers = clean_english_headers + new_english_headers
        full_chinese_headers = clean_chinese_headers + new_chinese_headers
        
        logger.info(f"最终表头长度 - 英文: {len(full_english_headers)}, 中文: {len(full_chinese_headers)}, 数据列: {len(df.columns)}")
        
        # 4. 构建最终的DataFrame
        row1_data = [full_english_headers[i] if i < len(full_english_headers) else '' for i in range(len(df.columns))]
        row2_data = [full_chinese_headers[i] if i < len(full_chinese_headers) else '' for i in range(len(df.columns))]
        
        all_data = []
        all_data.append(row1_data)  # 第一行：英文表头
        all_data.append(row2_data)  # 第二行：中文表头
        
        for _, row in df.iterrows():
            all_data.append([str(val) if not pd.isna(val) else '' for val in row])
        
        final_df = pd.DataFrame(all_data)
        logger.info(f"最终DataFrame形状: {final_df.shape}")
        
        # 保存Excel文件
        if is_interpreted_file(file_name):
            # 如果是已解释的文件，直接更新
            logger.info("检测到已解释文件，将更新现有文件")
            output_excel_path = file_path
            with pd.ExcelWriter(output_excel_path, engine='openpyxl') as excel_writer:
                final_df.to_excel(excel_writer, sheet_name='Sheet1', index=False, header=False)
            
            # 使用原文件ID
            new_file_id = file_id
            logger.info(f"文件已更新: {output_excel_path}")
        else:
            # 如果是原始文件，生成新的解释文件
            base_name = remove_file_id_prefix(file_name)
            if base_name.endswith('.xls'):
                base_name = base_name[:-4] + '.xlsx'  # 转换为xlsx格式
            elif base_name.endswith('.xlsx'):
                base_name = base_name[:-5] + '.xlsx'
            
            if not base_name.endswith('_interpreted.xlsx'):
                if base_name.endswith('.xlsx'):
                    new_filename = base_name[:-5] + '_interpreted.xlsx'
                else:
                    new_filename = base_name + '_interpreted.xlsx'
            else:
                new_filename = base_name
            
            logger.info(f"检测到原始文件，将生成新的解释文件: {new_filename}")
            
            # 保存到BytesIO，然后使用file_manager保存
            excel_buffer = BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as excel_writer:
                final_df.to_excel(excel_writer, sheet_name='Sheet1', index=False, header=False)
            excel_data = excel_buffer.getvalue()
            
            # 使用file_manager保存文件
            new_file_id = file_manager.save_file(
                file_data=excel_data,
                file_name=new_filename,
                file_type="xlsx",
                source="generated"
            )
            
            # 获取保存后的文件路径
            new_file_info = file_manager.get_file_info(new_file_id)
            output_excel_path = new_file_info.get("file_path")
            
        logger.info(f"处理完成，结果已保存到: {output_excel_path}")
        
        if writer:
            writer({"custom_step": f"成功处理{len(df)}行数据，完成3H比值分析"})
        
        # 创建可视化图表
        base_name = Path(file_name).stem
        if base_name.endswith('_interpreted'):
            base_name = base_name[:-12]
        
        image_filename = f"3H比值法解释图表_{base_name}.png"
        temp_image_path = os.path.join("data", "temp", f"temp_{image_filename}")
        
        final_image_path = create_3h_visualization(df, temp_image_path)
        
        if final_image_path and os.path.exists(final_image_path):
            # 读取图片文件
            with open(final_image_path, 'rb') as f:
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
        
        # 统计各解释结果的样品数量
        result_stats = df['3H解释结果'].value_counts()
        
        # 计算厚度统计
        depth_range = df['Depth'].max() - df['Depth'].min()
        
        if writer:
            writer({"custom_step": f"生成可视化图表: {image_filename}"})
        
        # 推送图片到UI
        if final_image_path and os.path.exists(final_image_path):
            image_message = {
                "image_path": final_image_path,
                "title": "3H比值法解释图表"
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
        
        if len(result_stats) > 0:
            main_result = result_stats.index[0]
            main_percentage = (result_stats.iloc[0] / total_samples) * 100
            result_summary = f"主要层型：{main_result}({main_percentage:.1f}%)"
        else:
            result_summary = "无有效分类结果"
        
        # 统计油气层比例
        oil_gas_count = (result_stats.get('油层', 0) + result_stats.get('轻质油层', 0) + 
                        result_stats.get('干气层', 0) + result_stats.get('湿气层', 0) + 
                        result_stats.get('凝析气层', 0))
        oil_gas_percentage = (oil_gas_count / total_samples) * 100 if total_samples > 0 else 0
        
        result_message = f"""✅ 3H比值法解释完成
🆔 **NEXT_FILE_ID: {new_file_id}** (后续工具请使用此file_id)
📏 分析井段: {depth_range_str} ({total_samples}个样品)
🎯 {result_summary}
⛽ 油气层比例: {oil_gas_percentage:.1f}%
📁 解释结果文件: {Path(output_excel_path).name}
📈 可视化图表: {image_filename}

⚠️ 重要: 后续工具必须使用file_id: {new_file_id} 以在此结果基础上追加分析"""
        
        if writer:
            writer({"custom_step": "3H比值法解释分析完成"})
        
        logger.info("3H比值法解释分析完成")
        return result_message
        
    except Exception as e:
        error_msg = f"3H比值法分析失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        if writer:
            writer({"custom_step": f"❌ {error_msg}"})
        
        return error_msg