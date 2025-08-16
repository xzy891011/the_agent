"""
增强版碳同位素可视化工具 - 专为大量随深度变化的碳同位素数据定制
"""

import os
import logging
import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from typing import Dict, List, Optional, Union, Any, Tuple
import io
import base64
from pathlib import Path
import threading
import time
import gc
import uuid
import platform
import matplotlib.font_manager as fm
import seaborn as sns
from datetime import datetime
from matplotlib import font_manager as fm
from matplotlib.font_manager import FontProperties
import warnings

# 添加全局绘图锁，确保一次只进行一个绘图操作
PLOT_LOCK = threading.Lock()

# 配置matplotlib确保稳定性
try:
    # 设置Agg后端，这是一个非交互式后端，更稳定用于生成图表文件
    matplotlib.use('Agg')  # 设置为非交互式后端
    
    # 禁用matplotlib缓存以避免潜在的冲突
    matplotlib.rcParams['path.simplify'] = True
    matplotlib.rcParams['path.simplify_threshold'] = 1.0
    matplotlib.rcParams['agg.path.chunksize'] = 10000
    
    # 更精细的后端配置
    matplotlib.rcParams['savefig.dpi'] = 300
    matplotlib.rcParams['savefig.bbox'] = 'tight'
    matplotlib.rcParams['savefig.pad_inches'] = 0.1
    matplotlib.rcParams['figure.max_open_warning'] = 50
except Exception as e:
    logging.warning(f"配置matplotlib后端失败: {str(e)}")

from app.tools.registry import register_tool
# from app.core.task_decorator import task  # 不再需要，已迁移到MCP
from app.core.file_manager_adapter import get_file_manager
from app.core.stream_writer_helper import push_progress, push_thinking, push_error

# 导入辅助函数
from app.tools.logging.iso_logging.isotope_depth_helpers import (
    preprocess_isotope_data,
    create_depth_segments,
    extract_isotope_features,
    generate_isotope_description
)

# 配置日志
logger = logging.getLogger(__name__)

# 使用文件管理器适配器（支持MinIO存储）
file_manager = get_file_manager()

# 临时文件存储路径
TEMP_PLOT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "generated")
os.makedirs(TEMP_PLOT_DIR, exist_ok=True)

# 完全禁用字体相关警告和中文字体
import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='matplotlib')
warnings.filterwarnings('ignore', message='.*font.*')
warnings.filterwarnings('ignore', message='.*Glyph.*')

# 设置matplotlib日志级别为CRITICAL，彻底禁用字体警告
matplotlib_logger = logging.getLogger('matplotlib')
matplotlib_logger.setLevel(logging.CRITICAL)
font_manager_logger = logging.getLogger('matplotlib.font_manager')
font_manager_logger.setLevel(logging.CRITICAL)

# 只使用安全的英文字体，完全避免中文字体
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['DejaVu Sans', 'Arial'],
    'axes.unicode_minus': False,
    'font.size': 10
})

logger.info("已配置matplotlib使用英文字体，避免中文字体问题")

# 配置中文字体支持
def setup_chinese_font():
    """设置中文字体，适配Ubuntu系统"""
    try:
        # Ubuntu系统常见的中文字体（按优先级排序）
        chinese_fonts = [
            'WenQuanYi Zen Hei',    # 文泉驿正黑（已确认可用）
            'WenQuanYi Micro Hei',  # 文泉驿微米黑
            'Noto Sans CJK SC',     # Noto Sans中文简体
            'SimHei',               # 黑体（如果安装了）
            'Microsoft YaHei',      # 微软雅黑（如果安装了）
            'DejaVu Sans',          # DejaVu Sans (fallback)
        ]
        
        # 获取系统可用字体
        available_fonts = [f.name for f in fm.fontManager.ttflist]
        
        # 寻找可用的中文字体
        selected_font = None
        for font in chinese_fonts:
            if font in available_fonts:
                selected_font = font
                break
        
        if selected_font:
            plt.rcParams['font.sans-serif'] = [selected_font]
            plt.rcParams['axes.unicode_minus'] = False  # 解决坐标轴负号显示问题
            logging.info(f"✅ 使用中文字体: {selected_font}")
            
            # 验证字体是否真正支持中文
            test_chinese = "中文测试"
            try:
                # 这个测试可以帮助确认字体真正支持中文
                fig, ax = plt.subplots(figsize=(1, 1))
                ax.text(0.5, 0.5, test_chinese, fontsize=10)
                plt.close(fig)
                logging.info(f"✅ 字体 {selected_font} 验证通过，支持中文显示")
            except Exception as e:
                logging.warning(f"⚠️ 字体验证出现警告: {e}")
                
        else:
            # 如果没有找到中文字体，使用DejaVu Sans作为fallback
            plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
            plt.rcParams['axes.unicode_minus'] = False
            logging.warning("⚠️ 未找到合适的中文字体，使用DejaVu Sans，中文可能显示为方框")
            
            # 提供安装建议
            logging.info("💡 Ubuntu系统安装中文字体建议:")
            logging.info("   apt-get install fonts-wqy-zenhei fonts-wqy-microhei fonts-noto-cjk")
            
    except Exception as e:
        logging.error(f"❌ 字体配置失败: {e}")
        # 使用系统默认字体
        plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False

# 初始化中文字体
setup_chinese_font()

def enhance_savefig(fig, output_path, plot_name="图表", max_retries=3):
    """增强版图表保存函数，提供更好的错误处理和验证
    
    Args:
        fig: matplotlib图表对象
        output_path: 输出文件路径
        plot_name: 图表名称（用于日志）
        max_retries: 文件验证重试次数
        
    Returns:
        bool: 是否成功保存
    """
    # 确保目标目录存在
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # *** 关键修复：在保存图表前重新设置中文字体 ***
    try:
        # 重新调用字体配置函数，确保字体设置正确
        setup_chinese_font()
        logger.info("已重新设置中文字体配置用于图表保存")
    except Exception as e:
        logger.warning(f"设置中文字体失败: {e}")
        # Fallback到基本设置
        plt.rcParams['axes.unicode_minus'] = False
    
    with PLOT_LOCK:  # 使用锁确保一次只有一个函数在保存图表
        try:
            # 记录图表类型
            fig_type = type(fig).__name__
            logger.info(f"正在处理图表类型: {fig_type}")
            
            # 获取图表对象中的所有坐标轴
            if hasattr(fig, 'axes'):
                axes = fig.axes
            elif hasattr(fig, 'get_axes'):
                axes = fig.get_axes()
            else:
                # 如果无法获取轴，尝试使用当前图表
                logger.warning(f"无法从图表对象获取轴，尝试使用plt.gca()")
                axes = [plt.gca()]
            
            # 验证图表是否包含内容并记录详细信息
            has_data = any(len(ax.collections) > 0 or len(ax.lines) > 0 or len(ax.patches) > 0 or len(ax.texts) > 0 for ax in axes)
            if len(axes) == 0 or not has_data:
                logger.error(f"{plot_name}没有有效内容: axes数量={len(axes)}, 数据元素存在={has_data}")
                try:
                    plt.close(fig)
                except:
                    logger.warning("关闭无效图表失败")
                finally:
                    plt.close('all')
                return False
                
            # 记录更多图表状态信息进行诊断
            axes_info = []
            for i, ax in enumerate(axes):
                axes_info.append(f"轴{i+1}: collections={len(ax.collections)}, lines={len(ax.lines)}, patches={len(ax.patches)}")
            logger.info(f"图表状态: {', '.join(axes_info)}")
            
            # 确保图表已完成渲染
            try:
                fig.canvas.draw()
            except Exception as e:
                logger.warning(f"图表绘制错误: {e}，尝试继续处理")
                
            # 使用更安全的保存方法，确保文件完整写入
            logger.info(f"正在保存{plot_name}: {output_path}")
            
            # 清理之前的图表文件(如果存在)
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                    time.sleep(0.5)  # 增加等待时间，确保删除操作完成
                except Exception as e:
                    logger.warning(f"清理旧文件失败: {str(e)}")
                    # 尝试使用不同的文件名
                    base, ext = os.path.splitext(output_path)
                    output_path = f"{base}_{int(time.time())}{ext}"
                    logger.info(f"使用新文件名: {output_path}")
            
            # 第一次保存
            fig.savefig(output_path, dpi=300, bbox_inches='tight')
            time.sleep(0.8)  # 增加等待时间
            
            # 第二次保存，确保文件完整写入
            fig.savefig(output_path, dpi=300, bbox_inches='tight')
            time.sleep(0.8)  # 增加等待时间
            
            # 主动刷新并关闭文件
            try:
                fig.canvas.flush_events()
            except Exception as e:
                logger.warning(f"刷新图表缓存失败: {str(e)}")
            
            # 确保图表被正确关闭
            try:
                plt.close(fig)
            except:
                logger.warning("关闭图表对象失败，尝试关闭所有图表")
            finally:
                plt.close('all')  # 关闭所有图形对象，彻底清理
            
            # 主动触发垃圾回收
            gc.collect()
            
            # 验证保存的图片是否有效
            valid_file = False
            
            # 重试机制：确保文件被正确写入并验证图片内容
            for attempt in range(max_retries):
                if not os.path.exists(output_path):
                    logger.warning(f"图表文件不存在，等待后重试 (尝试 {attempt+1}/{max_retries})")
                    time.sleep(1.5)
                    continue
                    
                if os.path.getsize(output_path) < 5000:  # 提高最小文件大小限制
                    logger.warning(f"图表文件过小 ({os.path.getsize(output_path)} 字节)，可能无效，等待后重试 (尝试 {attempt+1}/{max_retries})")
                    time.sleep(1.5)
                    continue
                
                # 尝试使用PIL验证图片有效性
                try:
                    from PIL import Image
                    img = Image.open(output_path)
                    img.verify()  # 验证图片完整性
                    
                    # 进一步检查：打开并检查图像尺寸
                    img = Image.open(output_path)
                    width, height = img.size
                    if width < 50 or height < 50:
                        logger.warning(f"图片尺寸过小 ({width}x{height})，可能无效，等待后重试 (尝试 {attempt+1}/{max_retries})")
                        time.sleep(1.5)
                        continue
                        
                    logger.info(f"成功创建并验证{plot_name}: {output_path}, 文件大小: {os.path.getsize(output_path)}，尺寸: {width}x{height}")
                    valid_file = True
                    break
                    
                except Exception as img_error:
                    logger.warning(f"图片验证失败: {str(img_error)}，等待后重试 (尝试 {attempt+1}/{max_retries})")
                    time.sleep(1.5)
            
            if valid_file:
                # 发送图片消息
                from app.core.stream_writer_helper import push_file_generated
                push_file_generated(output_path, plot_name)
                return True
            else:
                logger.error(f"无法创建有效的{plot_name}图片，所有验证尝试都失败")
                return False
                
        except Exception as save_err:
            logger.error(f"保存{plot_name}时出错: {str(save_err)}", exc_info=True)
            # 确保关闭图表资源
            try:
                plt.close(fig)
            except:
                pass
            plt.close('all')
            return False

def save_plot_file(output_path: str, output_filename: str, original_filename: str, 
                   plot_description: str, analysis_type: str, chart_type: str) -> Optional[str]:
    """保存图表文件到文件管理器（支持MinIO和本地存储）
    
    Args:
        output_path: 临时文件路径
        output_filename: 输出文件名
        original_filename: 原始数据文件名
        plot_description: 图表描述
        analysis_type: 分析类型（如isotope_bernard）
        chart_type: 图表类型（如bernard_diagram）
        
    Returns:
        文件ID，失败返回None
    """
    try:
        # 检查是否使用MinIO存储
        if hasattr(file_manager, 'use_minio') and file_manager.use_minio:
            # 读取图片文件并上传到MinIO
            with open(output_path, 'rb') as f:
                file_data = f.read()
            
            file_info = file_manager.save_file(
                file_data=file_data,
                file_name=output_filename,
                file_type="image",
                source="generated",
                metadata={
                    "description": plot_description,
                    "category": "analysis_result",  # 分析结果类别
                    "analysis_type": analysis_type,  # 分析类型
                    "chart_type": chart_type,  # 图表类型
                    "geological_model": "true",  # 标记为地质建模相关
                    "original_file": original_filename  # 原始文件名
                }
            )
            
            # 删除临时文件
            try:
                os.remove(output_path)
            except:
                pass
                
            plot_file_id = file_info.get('file_id')
        else:
            # 本地存储，使用原来的方式
            plot_file_id = file_manager.register_file(
                file_path=output_path,
                file_name=output_filename,
                file_type="png",
                metadata={
                    "description": plot_description,
                    "category": "analysis_result",  # 分析结果类别
                    "analysis_type": analysis_type,  # 分析类型
                    "chart_type": chart_type,  # 图表类型
                    "geological_model": "true",  # 标记为地质建模相关
                    "original_file": original_filename  # 原始文件名
                },
                source="generated",
                session_id=None
            )
            
        push_progress("save_plot_file", 1.0, f"{plot_description}创建完成")
            
        # 发送图片消息，确保图片在界面上显示
        from app.core.stream_writer_helper import push_file_generated
        push_file_generated(
            output_path if not (hasattr(file_manager, 'use_minio') and file_manager.use_minio) else None,
            plot_description
        )
            
        return plot_file_id
        
    except Exception as e:
        logger.error(f"保存{plot_description}文件时出错: {str(e)}", exc_info=True)
        return None

@register_tool(category="iso_logging")
def enhanced_plot_bernard_diagram(file_id: str, depth_segments: bool = True, num_segments: int = 5) -> str:
    """绘制增强版Bernard图解
    
    支持深度分段的Bernard图解，可显示不同深度段的点集，并且为每个段落标注颜色和深度信息。
    分析数据中的甲烷碳同位素(δ13C-CH4)与C1/(C2+C3)比值关系，用于判别天然气气源类型。
    
    Args:
        file_id: 文件ID，已上传到系统的数据文件
        depth_segments: 是否按深度分段
        num_segments: 深度段数量
        
    Returns:
        包含图表和分析文字的结果
    """
    # 推送工具开始执行
    push_progress("enhanced_plot_bernard_diagram", 0.1, f"正在创建增强版Bernard图解(文件ID: {file_id})...")
    
    try:
        # 获取文件信息并读取数据
        file_info = file_manager.get_file_info(file_id)
        if not file_info:
            push_error(f"找不到ID为 {file_id} 的文件", "enhanced_plot_bernard_diagram")
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
                                                        _identify_composition_columns,
                                                        _identify_depth_column)
        
        # 识别深度列、同位素列和组分列
        depth_col = _identify_depth_column(df)
        isotope_columns = _identify_isotope_columns(df)
        composition_columns = _identify_composition_columns(df)
        
        # 检查是否有足够的数据绘图
        c1_isotope_cols = isotope_columns.get("C1", [])
        if not c1_isotope_cols:
            return "未找到甲烷碳同位素(δ13C-CH4)数据列，无法创建Bernard图解。"
            
        c1_comp_cols = composition_columns.get("C1", [])
        c2_comp_cols = composition_columns.get("C2", [])
        if not c1_comp_cols or not c2_comp_cols:
            return "未找到甲烷(C1)或乙烷(C2)的组分含量数据列，无法创建Bernard图解。"
            
        # 提取数据列
        d13c_ch4_col = c1_isotope_cols[0]
        c1_col = c1_comp_cols[0]
        c2_col = c2_comp_cols[0]
        
        # 检查是否有C3数据
        c3_col = None
        c3_comp_cols = composition_columns.get("C3", [])
        if c3_comp_cols:
            c3_col = c3_comp_cols[0]
            
        # 计算C1/(C2+C3)比值
        if c3_col:
            df['C1/(C2+C3)'] = df[c1_col] / (df[c2_col] + df[c3_col])
        else:
            df['C1/(C2+C3)'] = df[c1_col] / df[c2_col]
            
        # 选择有效数据
        mask = (~df[d13c_ch4_col].isna()) & (~df['C1/(C2+C3)'].isna()) & (df['C1/(C2+C3)'] > 0)
        if mask.sum() == 0:
            return "数据中没有可用的有效值对，无法创建Bernard图解。"
            
        plot_df = df[mask].copy()
        
        # 创建分段(如果启用)
        segments = None
        if depth_segments and depth_col and len(plot_df) > 10:
            push_progress("enhanced_plot_bernard_diagram", 0.3, "正在对数据进行深度分段分析...")
                
            # 使用甲烷碳同位素列进行分段
            segments = create_depth_segments(
                plot_df, 
                depth_col, 
                d13c_ch4_col, 
                segment_method="change_point", 
                num_segments=num_segments
            )
        
        # 提取特征
        isotope_features = {}
        if segments:
            isotope_features = extract_isotope_features(
                plot_df,
                {"C1": [d13c_ch4_col]},
                depth_col,
                segments
            )
            
            # 添加C1/(C2+C3)比值特征
            for segment_feature in isotope_features.get("segments", []):
                segment_id = segment_feature["segment_id"]
                start = segment_feature["depth_start"]
                end = segment_feature["depth_end"]
                
                segment_df = plot_df[(plot_df[depth_col] >= start) & (plot_df[depth_col] <= end)]
                segment_feature["C1_C2C3_ratio_mean"] = segment_df["C1/(C2+C3)"].mean()
                segment_feature["C1_C2C3_ratio_min"] = segment_df["C1/(C2+C3)"].min()
                segment_feature["C1_C2C3_ratio_max"] = segment_df["C1/(C2+C3)"].max()
        
        # 创建Bernard图解
        plt.figure(figsize=(12, 9))
        
        # 设置刻度为对数刻度
        plt.xscale('log')
        
        # 绘制数据点 - 按深度分段着色
        if segments and depth_col:
            # 创建颜色映射
            cmap = plt.cm.viridis
            norm = mcolors.Normalize(vmin=plot_df[depth_col].min(), vmax=plot_df[depth_col].max())
            
            if num_segments <= 10:
                # 使用离散颜色
                colors = plt.cm.tab10(np.linspace(0, 1, num_segments))
                
                for i, (start, end) in enumerate(segments):
                    segment_df = plot_df[(plot_df[depth_col] >= start) & (plot_df[depth_col] <= end)]
                    if len(segment_df) > 0:
                        plt.scatter(
                            segment_df['C1/(C2+C3)'], 
                            segment_df[d13c_ch4_col],
                            marker='o', 
                            color=colors[i], 
                            alpha=0.7, 
                            s=60, 
                            edgecolor='k',
                            label=f'深度: {start:.1f}-{end:.1f}m'
                        )
            else:
                # 使用连续颜色映射
                scatter = plt.scatter(
                    plot_df['C1/(C2+C3)'], 
                    plot_df[d13c_ch4_col],
                    marker='o', 
                    c=plot_df[depth_col], 
                    cmap=cmap,
                    alpha=0.7, 
                    s=60, 
                    edgecolor='k'
                )
                
                # 添加颜色条
                cbar = plt.colorbar(scatter)
                cbar.set_label('深度 (m)', fontsize=12)
        else:
            # 不分段，使用单一颜色
            plt.scatter(
                plot_df['C1/(C2+C3)'], 
                plot_df[d13c_ch4_col],
                marker='o', 
                color='blue', 
                alpha=0.7, 
                s=60, 
                edgecolor='k'
            )
        
        # 添加气源区域标注
        # 生物气区域
        plt.axvspan(1000, 1e5, alpha=0.2, color='green', label='生物气')
        plt.axhspan(-110, -50, alpha=0.2, color='green')
        
        # 热解气区域
        plt.axvspan(1, 100, alpha=0.2, color='red', label='热解气')
        plt.axhspan(-50, -20, alpha=0.2, color='red')
        
        # 混合气区域
        plt.axvspan(100, 1000, alpha=0.2, color='orange', label='混合气')
        
        # 添加标题和轴标签
        plt.title('增强版Bernard图解: δ13C-CH4 vs C1/(C2+C3)', fontsize=14)
        plt.xlabel('C1/(C2+C3)', fontsize=12)
        plt.ylabel('δ13C-CH4 (‰)', fontsize=12)
        
        # 添加网格线
        plt.grid(True, alpha=0.3, linestyle='--')
        
        # 添加图例
        plt.legend(loc='best', fontsize=10)
        
        # 反转y轴（使同位素值按常规显示，负值在上）
        plt.gca().invert_yaxis()
        
        # 保存图表
        output_filename = f"enhanced_bernard_plot_{os.path.splitext(file_name)[0]}.png"
        output_path = os.path.join(TEMP_PLOT_DIR, output_filename)
        if enhance_savefig(plt.gcf(), output_path, "增强版Bernard图解"):
            # 注册生成的图表为文件
            plot_file_id = save_plot_file(output_path, output_filename, file_name, "增强版Bernard图解", "isotope_bernard", "bernard_diagram")
            
            if plot_file_id:
                # 生成分析报告
                description = generate_isotope_description(isotope_features, "bernard")
                
                return f"""## 增强版Bernard图解分析

已生成Bernard图解(文件ID: {plot_file_id})，该图基于甲烷碳同位素值(δ13C-CH4)和C1/(C2+C3)的关系进行天然气类型判别。

### 数据分析:
{description}

### 使用指南:
- Bernard图解通过甲烷碳同位素和C1/(C2+C3)比值，区分生物气、混合气和热解气。
- C1/(C2+C3)比值大于1000通常指示生物成因气，而热解气该比值通常小于50。
- 生物成因气的δ13C-CH4值通常较轻(<-60‰)，热解气δ13C-CH4值相对较重(>-50‰)。
- 数据点的位置和趋势可以显示气源混合和次生改造过程。
"""
            else:
                return "创建Bernard图解失败，图表生成过程出现错误。请检查日志获取详细信息。"
        else:
            return "创建Bernard图解失败，图表生成过程出现错误。请检查日志获取详细信息。"
    except Exception as e:
        error_msg = f"创建增强版Bernard图解时出错: {str(e)}"
        logger.error(error_msg, exc_info=True)
        push_error(error_msg, "enhanced_plot_bernard_diagram")
        return error_msg 

@register_tool(category="iso_logging")
def enhanced_plot_carbon_number_trend(file_id: str, depth_segments: bool = True, num_segments: int = 5) -> str:
    """绘制增强版碳同位素值与碳数关系图
    
    对不同深度段分别分析碳数趋势，并生成多曲线图表和变化描述。
    该工具能够揭示随深度变化的碳同位素分馏模式，有助于判断气源类型、成熟度和次生改造程度。
    
    Args:
        file_id: 文件ID，已上传到系统的数据文件
        depth_segments: 是否按深度分段
        num_segments: 深度段数量
        
    Returns:
        包含图表和分析文字的结果
    """
    # 推送工具开始执行
    push_progress("enhanced_plot_carbon_number_trend", 0.1, f"正在创建增强版碳同位素值与碳数关系图(文件ID: {file_id})...")
    
    try:
        # 获取文件信息并读取数据
        file_info = file_manager.get_file_info(file_id)
        if not file_info:
            logger.error(f"找不到ID为 {file_id} 的文件")
            push_error(f"找不到ID为 {file_id} 的文件", "enhanced_plot_carbon_number_trend")
            return f"找不到ID为 {file_id} 的文件。"
            
        file_path = file_info.get("file_path")
        file_type = file_info.get("file_type", "").lower()
        file_name = file_info.get("file_name", "")
        
        df = None
        try:
            if file_type in ["csv"]:
                df = pd.read_csv(file_path)
                logger.info(f"成功读取CSV文件: {file_path}, 大小: {df.shape}")
            elif file_type in ["xlsx", "xls"]:
                df = pd.read_excel(file_path)
                logger.info(f"成功读取Excel文件: {file_path}, 大小: {df.shape}")
            else:
                logger.error(f"不支持的文件类型: {file_type}")
                return f"不支持的文件类型: {file_type}。请提供CSV或Excel格式的数据文件。"
        except Exception as file_err:
            logger.error(f"读取文件时出错: {file_err}")
            return f"读取文件时出错: {str(file_err)}"
        
        # 数据预处理
        df = preprocess_isotope_data(df)
        
        # 从isotope_analysis模块导入辅助函数
        from app.tools.logging.iso_logging.isotope_analysis import (_identify_isotope_columns, 
                                                       _identify_depth_column)
        
        # 识别深度列和同位素列
        depth_col = _identify_depth_column(df)
        isotope_columns = _identify_isotope_columns(df)
        
        logger.info(f"识别到的深度列: {depth_col}")
        logger.info(f"识别到的同位素列: {str(isotope_columns)}")
        
        # 检查是否有足够的数据绘图
        required_components = ["C1", "C2", "C3"]
        missing_components = []
        
        for component in required_components:
            if not isotope_columns.get(component, []):
                missing_components.append(component)
                
        if missing_components:
            logger.error(f"缺少必要的同位素数据列: {', '.join(missing_components)}")
            return f"缺少必要的同位素数据列: {', '.join(missing_components)}。至少需要C1、C2、C3的碳同位素数据。"
        
        # 检查每个组分是否有足够的有效数据
        valid_data_counts = {}
        for component in required_components:
            if component in isotope_columns and isotope_columns[component]:
                col = isotope_columns[component][0]
                valid_count = (~df[col].isna()).sum()
                valid_data_counts[component] = valid_count
                logger.info(f"{component} 有效数据点数: {valid_count}")
                
                if valid_count < 3:
                    logger.warning(f"{component} 有效数据点不足: {valid_count}")
        
        # 如果所有组分都没有足够的有效数据，则退出
        if all(count < 3 for count in valid_data_counts.values()):
            logger.error("所有组分都没有足够的有效数据")
            return f"所有组分的有效数据点都不足，无法创建有意义的碳数关系图。至少需要3个有效数据点。"
        
        # 创建分段(如果启用)
        segments = None
        if depth_segments and depth_col and len(df) > 10:
            try:
                # 使用甲烷碳同位素列进行分段
                c1_col = isotope_columns["C1"][0]
                segments = create_depth_segments(
                    df, 
                    depth_col, 
                    c1_col, 
                    segment_method="change_point", 
                    num_segments=num_segments
                )
                
                push_progress("enhanced_plot_carbon_number_trend", 0.3, f"已创建{len(segments)}个深度分段")
                logger.info(f"已创建{len(segments)}个深度分段")
            except Exception as seg_err:
                logger.error(f"创建深度分段时出错: {seg_err}")
                segments = None
        
        # 定义碳数映射
        carbon_numbers = {"C1": 1, "C2": 2, "C3": 3, "iC4": 4, "nC4": 4, "C4": 4, "iC5": 5, "nC5": 5, "C5": 5, "C5+": 5}
        
        # 创建图表
        plt.figure(figsize=(12, 9))
        
        # 绘制总体碳数趋势线
        global_isotope_data = {}
        
        for component, cols in isotope_columns.items():
            if cols and component in carbon_numbers:
                col = cols[0]
                valid_data = df[~df[col].isna()]
                if len(valid_data) >= 3:
                    global_isotope_data[component] = {
                        "carbon_number": carbon_numbers[component],
                        "d13C": valid_data[col].mean(),
                        "std": valid_data[col].std(),
                        "count": len(valid_data)
                    }
                    logger.info(f"{component} 平均值: {valid_data[col].mean():.2f}‰, 标准差: {valid_data[col].std():.2f}‰, 数据点: {len(valid_data)}")
        
        if len(global_isotope_data) < 3:
            logger.error(f"有效的同位素数据点不足，仅有 {len(global_isotope_data)} 个组分有效")
            return f"有效的同位素数据点不足，无法创建有意义的碳数关系图。至少需要3个有效数据点。目前只有 {len(global_isotope_data)} 个有效组分。"
        
        # 提取绘图数据
        components = list(global_isotope_data.keys())
        x_values = [global_isotope_data[comp]["carbon_number"] for comp in components]
        y_values = [global_isotope_data[comp]["d13C"] for comp in components]
        errors = [global_isotope_data[comp]["std"] for comp in components]
        
        # 绘制总体趋势线
        plt.errorbar(x_values, y_values, yerr=errors, fmt='o-', capsize=5, 
                   markersize=10, color='black', ecolor='gray', linewidth=2,
                   label='总体平均值')
        
        # 判断总体是否存在同位素倒转
        global_is_reversed = False
        for i in range(1, len(x_values)):
            if y_values[i-1] > y_values[i]:
                global_is_reversed = True
                break
        
        logger.info(f"总体是否存在同位素倒转: {global_is_reversed}")
        
        # 如果有分段，绘制每个段的趋势线
        segment_is_reversed = []
        segment_features = []
        
        if segments and depth_col:
            # 使用不同颜色
            colors = plt.cm.tab10(np.linspace(0, 1, len(segments)))
            
            for i, (start, end) in enumerate(segments):
                segment_df = df[(df[depth_col] >= start) & (df[depth_col] <= end)]
                
                # 跳过数据点过少的段
                if len(segment_df) < 3:
                    logger.warning(f"段 {i+1} (深度: {start:.1f}-{end:.1f}m) 数据点不足, 跳过")
                    continue
                
                # 为该段准备数据
                segment_isotope_data = {}
                
                for component, cols in isotope_columns.items():
                    if cols and component in carbon_numbers:
                        col = cols[0]
                        valid_segment_data = segment_df[~segment_df[col].isna()]
                        if len(valid_segment_data) >= 3:
                            segment_isotope_data[component] = {
                                "carbon_number": carbon_numbers[component],
                                "d13C": valid_segment_data[col].mean(),
                                "std": valid_segment_data[col].std(),
                                "count": len(valid_segment_data)
                            }
                
                # 如果该段数据足够，绘制趋势线
                if len(segment_isotope_data) >= 3:
                    logger.info(f"段 {i+1} (深度: {start:.1f}-{end:.1f}m) 有 {len(segment_isotope_data)} 个有效组分")
                    
                    seg_components = list(segment_isotope_data.keys())
                    seg_x_values = [segment_isotope_data[comp]["carbon_number"] for comp in seg_components]
                    seg_y_values = [segment_isotope_data[comp]["d13C"] for comp in seg_components]
                    seg_errors = [segment_isotope_data[comp]["std"] for comp in seg_components]
                    
                    # 绘制该段趋势线
                    plt.errorbar(seg_x_values, seg_y_values, yerr=seg_errors, fmt='o--', capsize=3, 
                               markersize=8, color=colors[i], ecolor='lightgray', alpha=0.8,
                               label=f'深度: {start:.1f}-{end:.1f}m')
                    
                    # 判断该段是否存在同位素倒转
                    is_reversed = False
                    for j in range(1, len(seg_x_values)):
                        if seg_y_values[j-1] > seg_y_values[j]:
                            is_reversed = True
                            break
                    
                    segment_is_reversed.append(is_reversed)
                    
                    # 记录该段特征
                    segment_features.append({
                        "segment_id": i + 1,
                        "depth_start": start,
                        "depth_end": end,
                        "components": seg_components,
                        "values": seg_y_values,
                        "is_reversed": is_reversed,
                        "c1_value": next((seg_y_values[idx] for idx, comp in enumerate(seg_components) if comp == "C1"), None),
                        "c2_value": next((seg_y_values[idx] for idx, comp in enumerate(seg_components) if comp == "C2"), None),
                        "c3_value": next((seg_y_values[idx] for idx, comp in enumerate(seg_components) if comp == "C3"), None)
                    })
        
        # 添加趋势区域说明文本
        if global_is_reversed:
            plt.text(0.05, 0.05, "总体呈现碳同位素倒转现象\n可能指示: 1.混合成因 2.细菌改造 3.高成熟度", 
                    transform=plt.gca().transAxes, fontsize=10, 
                    bbox=dict(facecolor='yellow', alpha=0.2))
        else:
            # 正常趋势（轻到重）
            if y_values[0] < y_values[-1]:
                plt.text(0.05, 0.05, "总体呈正常碳同位素分馏趋势 (轻→重)\n指示正常热成熟过程", 
                        transform=plt.gca().transAxes, fontsize=10,
                        bbox=dict(facecolor='lightgreen', alpha=0.2))
            else:
                plt.text(0.05, 0.05, "总体呈碳同位素逆向分馏趋势 (重→轻)\n可能与有机质类型或成熟度相关", 
                        transform=plt.gca().transAxes, fontsize=10,
                        bbox=dict(facecolor='orange', alpha=0.2))
        
        # 添加标题和轴标签
        plt.title('增强版碳同位素值与碳数关系图', fontsize=14)
        plt.xlabel('碳数', fontsize=12)
        plt.ylabel('δ13C (‰)', fontsize=12)
        
        # 设置x轴刻度
        x_max = max(x_values) if x_values else 5
        plt.xticks(range(1, x_max+1))
        
        # 设置y轴范围，确保图形不会过于拉伸
        if y_values:
            y_min, y_max = min(y_values), max(y_values)
            y_range = y_max - y_min
            if y_range < 5:  # 如果范围太小，扩大显示范围
                y_center = (y_min + y_max) / 2
                plt.ylim(y_center - 5, y_center + 5)
        
        # 添加组分标签
        for i, comp in enumerate(components):
            plt.annotate(comp, (x_values[i], y_values[i]), 
                        xytext=(5, 5), textcoords='offset points', fontsize=9)
        
        # 添加网格线
        plt.grid(True, alpha=0.3, linestyle='--')
        
        # 反转y轴（使同位素值按常规显示，负值在上）
        plt.gca().invert_yaxis()
        
        # 添加图例
        plt.legend(loc='best', fontsize=10)
        
        # 保存图表
        output_filename = f"enhanced_carbon_number_trend_{os.path.splitext(file_name)[0]}.png"
        output_path = os.path.join(TEMP_PLOT_DIR, output_filename)
        if enhance_savefig(plt.gcf(), output_path, "增强版碳同位素值与碳数关系图"):
            logger.info(f"成功创建碳同位素值与碳数关系图: {output_path}")
            
            # 注册生成的图表为文件
            plot_file_id = save_plot_file(output_path, output_filename, file_name, "增强版碳同位素值与碳数关系图", "isotope_carbon_number", "carbon_number_trend")
            
            if plot_file_id:
                # 创建特征数据结构
                isotope_features = {
                    "overall": {
                        "is_reversed": global_is_reversed,
                        "c1_value": y_values[0] if len(y_values) > 0 else None,
                        "c2_value": y_values[1] if len(y_values) > 1 else None,
                        "c3_value": y_values[2] if len(y_values) > 2 else None
                    },
                    "segments": segment_features
                }
                
                # 生成分析报告
                description = generate_isotope_description(isotope_features, "carbon_number")
                
                return f"""## 增强版碳同位素值与碳数关系图分析

已生成碳同位素值与碳数关系图(文件ID: {plot_file_id})，该图展示了不同碳数组分的同位素值分布规律。

### 数据分析:
{description}

### 使用指南:
- 碳同位素值与碳数关系图可用于判断烃源类型、成熟度和次生改造程度。
- 正常热成因气通常碳同位素值随碳数增加而变重(正序列)。
- 如果C2组分碳同位素值比C1和C3都重，表现为倒"V"型，则可能指示高成熟度气或次生改造。
- 异常的同位素分布类型通常指示特殊的地球化学过程，如生物降解或多源混合。
"""
            else:
                return "创建碳同位素值与碳数关系图失败，图表生成过程出现错误。请检查日志获取详细信息。"
        else:
            return "创建碳同位素值与碳数关系图失败，图表生成过程出现错误。请检查日志获取详细信息。"
    except Exception as e:
        error_msg = f"创建增强版碳同位素值与碳数关系图时出错: {str(e)}"
        logger.error(error_msg, exc_info=True)
        push_error(error_msg, "enhanced_plot_carbon_number_trend")
        return error_msg 

@register_tool(category="iso_logging")
def enhanced_plot_whiticar_diagram(file_id: str, depth_segments: bool = True, num_segments: int = 5) -> str:
    """绘制增强版Whiticar甲烷成因分类图解
    
    基于δ13C-CH4和δD-CH4数据，结合不同深度分段，绘制Whiticar成因分类图解。
    该增强版工具能够展示不同深度段甲烷的成因差异，并提供详细的来源分析。
    
    Args:
        file_id: 文件ID，已上传到系统的数据文件
        depth_segments: 是否按深度分段
        num_segments: 深度段数量
        
    Returns:
        包含图表和分析文字的结果
    """
    # 推送工具开始执行
    push_progress("enhanced_plot_whiticar_diagram", 0.1, f"正在创建增强版Whiticar甲烷成因分类图解(文件ID: {file_id})...")
    
    try:
        # 获取文件信息并读取数据
        file_info = file_manager.get_file_info(file_id)
        if not file_info:
            push_error(f"找不到ID为 {file_id} 的文件", "enhanced_plot_whiticar_diagram")
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
        
        # 检查是否有甲烷的碳同位素数据
        if "C1" not in isotope_columns or not isotope_columns["C1"]:
            return "未找到甲烷(C1)的碳同位素(δ13C)数据列。"
        
        c1_d13c_col = isotope_columns["C1"][0]
        
        # 检查是否有甲烷的氢同位素数据
        dh_col = None
        for col in df.columns:
            col_name = str(col).lower()
            if any(term in col_name for term in ["δd", "dd", "d-h", "δh", "dh", "deltaD"]) and "ch4" in col_name:
                dh_col = col
                break
                
        if dh_col is None:
            return "未找到甲烷(CH4)的氢同位素(δD)数据列。Whiticar图解需要同时具有碳同位素和氢同位素数据。"
            
        # 创建分段(如果启用)
        segments = None
        if depth_segments and depth_col and len(df) > 10:
            # 使用甲烷碳同位素列进行分段
            segments = create_depth_segments(
                df, 
                depth_col, 
                c1_d13c_col, 
                segment_method="change_point", 
                num_segments=num_segments
            )
            
            push_progress("enhanced_plot_whiticar_diagram", 0.3, f"已创建{len(segments)}个深度分段")
                
        # 创建图表
        plt.figure(figsize=(12, 10))
        
        # 定义Whiticar图解的区域
        # 生物成因气区域
        bio_x = [-110, -60, -60, -110, -110]
        bio_y = [-400, -400, -150, -150, -400]
        
        # 热成因气区域
        thermogenic_x = [-50, -20, -20, -50, -50]
        thermogenic_y = [-275, -275, -100, -100, -275]
        
        # 混合成因区域
        mixed_x = [-60, -50, -50, -60, -60]
        mixed_y = [-400, -275, -100, -150, -400]
        
        # 绘制区域
        plt.fill(bio_x, bio_y, alpha=0.2, color='green', label='生物成因气区')
        plt.fill(thermogenic_x, thermogenic_y, alpha=0.2, color='red', label='热成因气区')
        plt.fill(mixed_x, mixed_y, alpha=0.2, color='orange', label='混合成因区')
        
        # 添加箭头指示趋势线
        plt.annotate('成熟度增加', xy=(-35, -180), xytext=(-47, -230),
                    arrowprops=dict(facecolor='black', shrink=0.05, width=1.5, headwidth=8),
                    fontsize=10)
                    
        plt.annotate('微生物成因', xy=(-80, -280), xytext=(-55, -320),
                    arrowprops=dict(facecolor='green', shrink=0.05, width=1.5, headwidth=8),
                    fontsize=10)
        
        # 绘制总体数据点
        all_d13c = df[c1_d13c_col].dropna().values
        all_dh = df[dh_col].dropna().values
        
        # 确保两个数据列长度匹配
        valid_indices = np.logical_and(~np.isnan(df[c1_d13c_col]), ~np.isnan(df[dh_col]))
        valid_d13c = df.loc[valid_indices, c1_d13c_col].values
        valid_dh = df.loc[valid_indices, dh_col].values
        valid_depths = df.loc[valid_indices, depth_col].values if depth_col else None
        
        if len(valid_d13c) == 0:
            return "没有足够的有效数据点绘制Whiticar图解。确保碳同位素和氢同位素数据在相同深度存在。"
            
        # 计算总体平均值
        mean_d13c = np.mean(valid_d13c)
        mean_dh = np.mean(valid_dh)
        std_d13c = np.std(valid_d13c)
        std_dh = np.std(valid_dh)
        
        # 绘制总体平均点（更大尺寸）
        plt.scatter(mean_d13c, mean_dh, s=150, c='black', marker='*', label='总体平均值')
        
        # 绘制误差椭圆
        from matplotlib.patches import Ellipse
        ell = Ellipse(xy=(mean_d13c, mean_dh), width=std_d13c*2, height=std_dh*2,
                     fill=False, edgecolor='black', linestyle='--', linewidth=1.5)
        plt.gca().add_patch(ell)
        
        # 如果有分段，绘制每个段的数据点
        segment_results = []
        
        if segments and depth_col:
            # 使用不同颜色
            colors = plt.cm.tab10(np.linspace(0, 1, len(segments)))
            
            for i, (start, end) in enumerate(segments):
                # 筛选该段数据
                segment_indices = np.logical_and(valid_indices, 
                                                np.logical_and(df[depth_col] >= start, 
                                                             df[depth_col] <= end))
                
                segment_d13c = df.loc[segment_indices, c1_d13c_col].values
                segment_dh = df.loc[segment_indices, dh_col].values
                
                # 跳过数据点过少的段
                if len(segment_d13c) < 3:
                    continue
                    
                # 计算该段平均值和标准差
                seg_mean_d13c = np.mean(segment_d13c)
                seg_mean_dh = np.mean(segment_dh)
                seg_std_d13c = np.std(segment_d13c)
                seg_std_dh = np.std(segment_dh)
                
                # 绘制该段平均点
                plt.scatter(seg_mean_d13c, seg_mean_dh, s=100, c=[colors[i]], 
                           marker='o', label=f'深度: {start:.1f}-{end:.1f}m')
                
                # 绘制该段所有数据点
                plt.scatter(segment_d13c, segment_dh, s=30, c=[colors[i]], alpha=0.5)
                
                # 绘制误差椭圆
                seg_ell = Ellipse(xy=(seg_mean_d13c, seg_mean_dh), 
                                 width=seg_std_d13c*2, height=seg_std_dh*2,
                                 fill=False, edgecolor=colors[i], linestyle=':')
                plt.gca().add_patch(seg_ell)
                
                # 判断该段甲烷成因
                source_type = "未定"
                if -110 <= seg_mean_d13c <= -60 and -400 <= seg_mean_dh <= -150:
                    source_type = "生物成因气"
                elif -50 <= seg_mean_d13c <= -20 and -275 <= seg_mean_dh <= -100:
                    source_type = "热成因气"
                elif -60 <= seg_mean_d13c <= -50 and -400 <= seg_mean_dh <= -100:
                    source_type = "混合成因气"
                else:
                    # 检查最近的区域
                    min_dist = float('inf')
                    
                    # 检查到生物成因区的距离
                    bio_center_x = np.mean(bio_x[:-1])
                    bio_center_y = np.mean(bio_y[:-1])
                    bio_dist = np.sqrt((seg_mean_d13c - bio_center_x)**2 + (seg_mean_dh - bio_center_y)**2)
                    
                    # 检查到热成因区的距离
                    therm_center_x = np.mean(thermogenic_x[:-1])
                    therm_center_y = np.mean(thermogenic_y[:-1])
                    therm_dist = np.sqrt((seg_mean_d13c - therm_center_x)**2 + (seg_mean_dh - therm_center_y)**2)
                    
                    # 检查到混合区的距离
                    mixed_center_x = np.mean(mixed_x[:-1])
                    mixed_center_y = np.mean(mixed_y[:-1])
                    mixed_dist = np.sqrt((seg_mean_d13c - mixed_center_x)**2 + (seg_mean_dh - mixed_center_y)**2)
                    
                    min_dist_type = min((bio_dist, "生物成因气(边缘)"), 
                                        (therm_dist, "热成因气(边缘)"), 
                                        (mixed_dist, "混合成因气(边缘)"))
                    
                    source_type = min_dist_type[1]
                
                # 记录该段分析结果
                segment_results.append({
                    "segment_id": i + 1,
                    "depth_start": start,
                    "depth_end": end,
                    "mean_d13c": seg_mean_d13c,
                    "mean_dh": seg_mean_dh,
                    "std_d13c": seg_std_d13c,
                    "std_dh": seg_std_dh,
                    "source_type": source_type,
                    "data_points": len(segment_d13c)
                })
        
        # 添加标题和轴标签
        plt.title('增强版Whiticar甲烷成因分类图解', fontsize=14)
        plt.xlabel('δ13C-CH4 (‰)', fontsize=12)
        plt.ylabel('δD-CH4 (‰)', fontsize=12)
        
        # 设置坐标范围
        plt.xlim([-120, -10])
        plt.ylim([-450, -50])
        
        # 添加网格线
        plt.grid(True, alpha=0.3, linestyle='--')
        
        # 添加图例
        plt.legend(loc='lower right', fontsize=10)
        
        # 保存图表
        output_filename = f"enhanced_whiticar_diagram_{os.path.splitext(file_name)[0]}.png"
        output_path = os.path.join(TEMP_PLOT_DIR, output_filename)
        if enhance_savefig(plt.gcf(), output_path, "增强版Whiticar甲烷成因分类图解"):
            # 注册生成的图表为文件
            plot_file_id = save_plot_file(output_path, output_filename, file_name, "增强版Whiticar甲烷成因分类图解", "isotope_whiticar", "whiticar_diagram")
            
            if plot_file_id:
                # 创建特征数据结构
                isotope_features = {
                    "overall": {
                        "mean_d13c": mean_d13c,
                        "mean_dh": mean_dh,
                        "std_d13c": std_d13c,
                        "std_dh": std_dh,
                        "data_points": len(valid_d13c)
                    },
                    "segments": segment_results
                }
                
                # 生成分析报告
                description = generate_isotope_description(isotope_features, "whiticar")
                
                return f"""## 增强版Whiticar甲烷成因分类图解分析

已生成Whiticar甲烷成因分类图解(文件ID: {plot_file_id})，该图基于甲烷碳氢同位素特征进行气源类型判别。

### 数据分析:
{description}

### 使用指南:
- Whiticar图解通过甲烷的碳同位素(δ13C-CH4)和氢同位素(δD-CH4)进行天然气气源类型判别。
- 图中不同区域代表不同气源类型：生物成因气、热解成因气和混合型气体。
- 生物成因气通常碳同位素值较轻(<-60‰)，热解气碳同位素值相对较重(>-50‰)。
- 纯CO2还原型生物气和发酵型生物气在图解中也有明确区分。
"""
            else:
                return "创建Whiticar甲烷成因分类图解失败，图表生成过程出现错误。请检查日志获取详细信息。"
        else:
            return "创建Whiticar甲烷成因分类图解失败，图表生成过程出现错误。请检查日志获取详细信息。"
    except Exception as e:
        error_msg = f"创建增强版Whiticar甲烷成因分类图解时出错: {str(e)}"
        logger.error(error_msg, exc_info=True)
        push_error(error_msg, "enhanced_plot_whiticar_diagram")
        return error_msg 