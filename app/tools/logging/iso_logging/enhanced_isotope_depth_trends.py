"""
增强版碳同位素深度趋势分析工具

该模块提供了用于分析碳同位素随深度变化趋势的工具，包括：
1. 深度分段趋势分析
2. 垂向分带识别
3. 同位素异常区检测
4. 趋势可视化和文本报告生成

这些工具能够从大量碳同位素数据中识别出垂向变化规律和异常区间。
"""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats
import logging
from typing import Dict, List, Tuple, Optional, Union, Any
import io
import base64
from pathlib import Path
import threading
import time
import gc
import uuid
import fnmatch
import platform
import matplotlib.font_manager as fm
import warnings
from datetime import datetime

from app.core.file_manager import file_manager
from app.tools.logging.iso_logging.isotope_depth_helpers import (
    preprocess_isotope_data,
    create_depth_segments,
    extract_isotope_features
)
from app.tools.registry import register_tool
# from app.core.task_decorator import task  # 不再需要，已迁移到MCP
from langgraph.config import get_stream_writer

# 全局绘图锁
PLOT_LOCK = threading.Lock()

# 配置工具执行时间间隔跟踪器
class ToolExecutionTracker:
    def __init__(self, min_interval=5.0):
        self.last_execution_time = 0
        self.min_interval = min_interval  # 最小执行间隔(秒)
        self.lock = threading.Lock()
        
    def wait_if_needed(self):
        """在工具执行前等待，确保与上次执行有足够间隔"""
        with self.lock:
            current_time = time.time()
            elapsed = current_time - self.last_execution_time
            
            if elapsed < self.min_interval and self.last_execution_time > 0:
                wait_time = self.min_interval - elapsed
                logging.info(f"等待 {wait_time:.2f} 秒以确保工具执行间隔")
                time.sleep(wait_time)
                
            self.last_execution_time = time.time()

# 创建工具执行跟踪器实例
tool_tracker = ToolExecutionTracker()

# 设置日志
logger = logging.getLogger(__name__)

# 临时图表存储目录
TEMP_PLOT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "generated")
if not os.path.exists(TEMP_PLOT_DIR):
    os.makedirs(TEMP_PLOT_DIR)

# 配置matplotlib确保稳定性
try:
    # 设置Agg后端，这是一个非交互式后端，更稳定用于生成图表文件
    import matplotlib
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
    
    logger.info("已配置matplotlib后端和优化设置")
except Exception as e:
    logger.warning(f"配置matplotlib后端失败: {str(e)}")

# 彻底禁用所有matplotlib字体警告
def setup_matplotlib_fonts():
    """彻底设置matplotlib字体，完全消除字体相关警告"""
    import logging
    
    # 设置matplotlib和字体管理器的日志级别为CRITICAL，避免字体警告
    logging.getLogger('matplotlib').setLevel(logging.CRITICAL)
    logging.getLogger('matplotlib.font_manager').setLevel(logging.CRITICAL)
    logging.getLogger('matplotlib.pyplot').setLevel(logging.CRITICAL)
    
    # 禁用所有字体相关警告
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore")
        
        try:
            # 直接设置最安全的字体配置
            plt.rcParams.clear()  # 清除所有之前的配置
            matplotlib.rcdefaults()  # 重置为默认配置
            
            # 使用最基本的字体设置
            plt.rcParams['font.family'] = 'sans-serif'
            plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Liberation Sans', 'sans-serif']
            plt.rcParams['axes.unicode_minus'] = False
            plt.rcParams['font.size'] = 10
            
            # 禁用字体缓存和查找
            matplotlib.rcParams['font.family'] = 'sans-serif'
            matplotlib.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Liberation Sans']
            
            logger.info("matplotlib字体配置完成，使用安全默认字体")
            
        except Exception as e:
            logger.warning(f"字体配置异常: {str(e)}")

# 执行字体设置
setup_matplotlib_fonts()

# 字体配置已简化，移除中文字体设置以避免警告

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

@register_tool(category="iso_logging")
def enhanced_analyze_isotope_depth_trends(file_id: str, num_segments: int = 5, highlight_anomalies: bool = True, penalties: str = "10,20,50,100,200,500,1000") -> str:
    """分析碳同位素随深度变化的趋势
    
    对大量碳同位素数据进行深度分析，识别垂向变化趋势，分带特征，和异常区间。
    该工具能够处理含有上百至上千数据点的大型碳同位素数据集，自动分段并提取特征。
    
    Args:
        file_id: 文件ID，已上传到系统的数据文件
        num_segments: 自动分段数量
        highlight_anomalies: 是否自动检测并突出显示异常区间
        penalties: 变点检测算法惩罚值列表，用英文逗号分隔的字符串，如"10,20,50,100,200,500,1000"
        
    Returns:
        包含深度趋势分析结果和图表的详细报告
    """
    # *** 关键修复：安全获取流写入器，避免上下文错误 ***
    writer = None
    try:
        writer = get_stream_writer()
    except RuntimeError:
        # 在测试环境或非LangGraph上下文中运行时，writer为None
        logger.debug(f"无法获取流式写入器，可能在测试环境中运行")
    
    if writer:
        writer({"custom_step": f"正在分析碳同位素深度趋势(文件ID: {file_id})..."})
    
    try:
        # 确保工具执行时间间隔
        tool_tracker.wait_if_needed()
        
        # 获取文件信息并读取数据
        file_info = file_manager.get_file_info(file_id)
        if not file_info:
            return f"找不到ID为 {file_id} 的文件。"
            
        file_path = file_info.get("file_path")
        file_type = file_info.get("file_type", "").lower()
        file_name = file_info.get("file_name", "")
        
        df = None
        # *** 关键修复：改进文件类型检查，支持spreadsheet类型 ***
        if file_type in ["csv"]:
            df = pd.read_csv(file_path)
        elif file_type in ["xlsx", "xls", "spreadsheet"]:
            # spreadsheet类型通常是Excel文件，尝试读取为Excel
            try:
                df = pd.read_excel(file_path)
                if writer:
                    writer({"custom_step": f"成功读取文件类型为 {file_type} 的数据，识别为Excel格式"})
            except Exception as excel_error:
                # 如果Excel读取失败，尝试CSV格式
                try:
                    df = pd.read_csv(file_path)
                    if writer:
                        writer({"custom_step": f"Excel读取失败，已成功按CSV格式读取文件类型为 {file_type} 的数据"})
                except Exception as csv_error:
                    return f"无法读取文件类型 {file_type} 的数据。Excel读取错误: {excel_error}; CSV读取错误: {csv_error}"
        else:
            # 对于未知文件类型，尝试智能识别
            try:
                # 首先尝试按文件扩展名判断
                file_ext = os.path.splitext(file_path)[1].lower()
                if file_ext in ['.xlsx', '.xls']:
                    df = pd.read_excel(file_path)
                    if writer:
                        writer({"custom_step": f"根据文件扩展名 {file_ext} 成功读取Excel格式数据"})
                elif file_ext in ['.csv']:
                    df = pd.read_csv(file_path)
                    if writer:
                        writer({"custom_step": f"根据文件扩展名 {file_ext} 成功读取CSV格式数据"})
                else:
                    # 尝试Excel格式
                    try:
                        df = pd.read_excel(file_path)
                        if writer:
                            writer({"custom_step": f"文件类型 {file_type} 已成功按Excel格式读取"})
                    except:
                        # 尝试CSV格式
                        df = pd.read_csv(file_path)
                        if writer:
                            writer({"custom_step": f"文件类型 {file_type} 已成功按CSV格式读取"})
            except Exception as e:
                return f"不支持的文件类型: {file_type}。尝试读取失败: {str(e)}。请提供CSV或Excel格式的数据文件。"
        
        # 数据预处理
        df = preprocess_isotope_data(df)
        
        # 从isotope_analysis模块导入辅助函数
        from app.tools.logging.iso_logging.isotope_analysis import (_identify_isotope_columns, 
                                                       _identify_depth_column)
        
        # 识别深度列和同位素列
        depth_col = _identify_depth_column(df)
        isotope_columns = _identify_isotope_columns(df)
        
        # 检查是否有深度列
        if not depth_col:
            return "未找到深度列。深度趋势分析需要有深度数据。"
            
        # 检查是否有足够的同位素数据
        if not isotope_columns:
            return "未找到任何同位素数据列。请确保数据包含碳同位素值列。"
            
        # 检查样本量是否足够
        if len(df) < 10:
            return "数据点数量不足，需要至少10个数据点才能进行深度趋势分析。"
        
        # 创建深度分段
        segments = create_depth_segments(
            df, 
            depth_col, 
            isotope_columns.get("C1", [isotope_columns.get("C2", [[list(isotope_columns.values())[0][0]]])][0])[0],
            segment_method="change_point",
            num_segments=num_segments,
            penalties=penalties
        )
        
        if writer:
            writer({"custom_step": f"已创建{len(segments)}个深度分段"})
            
        # 提取全局特征
        global_features = extract_isotope_features(df, isotope_columns, depth_col, segments=None)
        
        # 提取分段特征
        segment_features = []
        
        for i, (start, end) in enumerate(segments):
            segment_df = df[(df[depth_col] >= start) & (df[depth_col] <= end)]
            
            if len(segment_df) >= 3:  # 确保每段有足够的数据点
                feature = extract_isotope_features(segment_df, isotope_columns, depth_col, segments=None)
                feature["segment_id"] = i + 1
                feature["depth_start"] = start
                feature["depth_end"] = end
                feature["data_points"] = len(segment_df)
                segment_features.append(feature)
        
        # 创建深度趋势图
        trend_plot_id = create_depth_trend_plot(
            df, 
            isotope_columns, 
            depth_col, 
            segments, 
            highlight_anomalies,
            file_name
        )
        
        if writer:
            writer({"custom_step": "深度趋势图生成完成，正在准备创建剖面图..."})
            
        # 添加强制等待，确保第一个图表完全处理完毕
        time.sleep(3.0)  # 增加至少3秒等待时间
        
        # 强制清理所有matplotlib资源，确保下一个图表完全独立
        plt.close('all')
        gc.collect()
        
        # 创建同位素剖面图
        profile_plot_id = create_isotope_profile_plot(
            df, 
            isotope_columns, 
            depth_col, 
            segments,
            file_name
        )
        
        # 再次添加等待，确保第二个图表完全处理完毕
        time.sleep(1.5)
        
        # 分析趋势特征并生成报告
        report = generate_depth_trend_report(
            global_features, 
            segment_features, 
            isotope_columns,
            trend_plot_id,
            profile_plot_id
        )
        
        if writer:
            writer({"custom_step": "碳同位素深度趋势分析完成\n"})
            
        return report
    except Exception as e:
        error_msg = f"分析碳同位素深度趋势时出错: {str(e)}"
        logger.error(error_msg, exc_info=True)
        if writer:
            writer({"custom_step": error_msg})
        return error_msg


def create_depth_trend_plot(
    df: pd.DataFrame,
    isotope_columns: Dict[str, List[str]],
    depth_col: str,
    segments: List[Tuple[float, float]],
    highlight_anomalies: bool,
    file_name: str
) -> Optional[str]:
    """
    创建碳同位素深度趋势图
    
    Args:
        df: 数据框
        isotope_columns: 同位素列映射
        depth_col: 深度列名
        segments: 深度分段
        highlight_anomalies: 是否突出显示异常值
        file_name: 输入文件名
        
    Returns:
        图表文件ID
    """
    # *** 关键修复：安全获取流写入器，避免上下文错误 ***
    writer = None
    try:
        writer = get_stream_writer()
    except RuntimeError:
        # 在测试环境或非LangGraph上下文中运行时，writer为None
        logger.debug(f"无法获取流式写入器，可能在测试环境中运行")
    
    if writer:
        writer({"custom_step": "开始创建同位素深度趋势图..."})
    
    try:
        # 确保工具执行时间间隔
        tool_tracker.wait_if_needed()
        
        # 确保文件名不包含不安全字符
        safe_filename = os.path.basename(file_name).replace(" ", "_").replace(",", "_")
        
        # 从文件管理器获取正确的生成文件保存目录
        from app.core.file_manager_adapter import get_file_manager
        file_manager_adapter = get_file_manager()
        
        # 生成图表ID和文件名
        file_id = f"g-{uuid.uuid4().hex[:8]}"
        timestamp = int(time.time())  # 添加时间戳确保唯一性
        output_filename = f"{file_id}_isotope_depth_trend_{safe_filename}_{timestamp}.png"
        
        # 对于MinIO存储，使用临时目录
        if hasattr(file_manager_adapter, 'use_minio') and file_manager_adapter.use_minio:
            import tempfile
            output_dir = tempfile.gettempdir()
        else:
            from app.core.file_manager import FileManager
            output_dir = FileManager.get_instance().generated_path
        
        output_path = os.path.join(output_dir, output_filename)
        
        # 检查是否在短时间内生成过相同数据的图片
        time_threshold = 60  # 60秒内的图片认为是重复的
        current_time = time.time()
        
        # 对于MinIO存储，跳过重复检查
        if not (hasattr(file_manager_adapter, 'use_minio') and file_manager_adapter.use_minio):
            pattern = f"*_isotope_depth_trend_{safe_filename}_*.png"
            
            recent_files = []
            for f in os.listdir(output_dir):
                if fnmatch.fnmatch(f, pattern):
                    file_path = os.path.join(output_dir, f)
                    file_time = os.path.getctime(file_path)
                    if current_time - file_time < time_threshold:
                        # 这是最近60秒内创建的文件
                        recent_files.append((f, file_path, file_time))
            
            if recent_files:
                # 找到最近的文件
                recent_files.sort(key=lambda x: x[2], reverse=True)  # 按创建时间排序
                recent_file, recent_path, _ = recent_files[0]
                
                logger.warning(f"检测到最近创建的深度趋势图: {recent_file}，使用现有文件")
                
                # 使用现有文件
                existing_info = file_manager.get_file_by_path(recent_path)
                if existing_info and existing_info.get('file_id'):
                    logger.info(f"使用现有文件ID: {existing_info.get('file_id')}")
                    return existing_info.get('file_id')
        
        # 重新设置matplotlib后端，确保环境干净
        matplotlib.use('Agg', force=True)
        plt.close('all')  # 关闭所有之前的图表
        
        # *** 关键修复：重置后端后需要重新设置中文字体 ***
        setup_chinese_font()
        
        # 数据验证
        if depth_col not in df.columns:
            logger.error(f"深度列 '{depth_col}' 不在数据框中")
            return None
            
        if not isotope_columns:
            logger.error("未找到同位素列")
            return None
            
        # 确保深度列有数据
        valid_depth = df[~df[depth_col].isna()]
        if len(valid_depth) < 3:
            logger.error(f"深度列有效数据不足: {len(valid_depth)}行")
            return None
            
        # 确保至少有一个组分有数据
        has_valid_component = False
        for component in ["C1", "C2", "C3"]:
            if component in isotope_columns and len(isotope_columns[component]) > 0:
                col = isotope_columns[component][0]
                if col in df.columns and not df[col].isna().all():
                    has_valid_component = True
                    break
                    
        if not has_valid_component:
            logger.error("没有有效的同位素组分数据")
            return None
        
        # 创建图表
        plt.figure(figsize=(12, 10))
        
        # 主要同位素值的深度曲线
        components = ["C1", "C2", "C3"]
        colors = ["blue", "red", "green"]
        markers = ["o", "s", "^"]
        
        # 绘制同位素值随深度变化曲线
        ax1 = plt.subplot2grid((1, 3), (0, 0), colspan=2)
        
        # 记录有效数据
        valid_data_exists = False
        
        for i, component in enumerate(components):
            if component in isotope_columns and isotope_columns[component]:
                col = isotope_columns[component][0]
                
                if col in df.columns:
                    # 过滤有效数据
                    valid_data = df[(~df[col].isna()) & (~df[depth_col].isna())]
                    
                    if len(valid_data) >= 3:
                        valid_data_exists = True
                        
                        # 绘制数据点
                        ax1.scatter(valid_data[col], valid_data[depth_col], color=colors[i], marker=markers[i], 
                                  s=30, alpha=0.6, label=f'δ13C-{component}')
                        
                        # 添加趋势线
                        try:
                            z = np.polyfit(valid_data[col], valid_data[depth_col], 1)
                            p = np.poly1d(z)
                            x_trend = np.linspace(valid_data[col].min(), valid_data[col].max(), 100)
                            ax1.plot(x_trend, p(x_trend), '--', color=colors[i], alpha=0.7)
                            logger.info(f"成功为 {component} 添加趋势线")
                        except Exception as trend_err:
                            logger.warning(f"为 {component} 添加趋势线失败: {trend_err}")
                
        if not valid_data_exists:
            logger.error("没有足够的有效数据来绘制图表")
            plt.close()
            return None
            
        # 确保segments有效
        valid_segments = []
        if segments:
            for start, end in segments:
                # 检查segment是否有数据点
                segment_data = df[(df[depth_col] >= start) & (df[depth_col] <= end)]
                if len(segment_data) > 0:
                    valid_segments.append((start, end))
                    
            if not valid_segments and segments:
                logger.warning("所有深度分段都没有数据点，将使用整个深度范围")
                depth_min = df[depth_col].min()
                depth_max = df[depth_col].max()
                valid_segments = [(depth_min, depth_max)]
        
        # 标记深度分段
        for start, end in valid_segments:
            ax1.axhspan(start, end, color="gray", alpha=0.1)
            ax1.axhline(y=start, color="gray", linestyle="-", alpha=0.5)
        
        # 如果需要，标记异常区间
        if highlight_anomalies:
            # 对C1同位素值检测异常
            if "C1" in isotope_columns and isotope_columns["C1"]:
                c1_col = isotope_columns["C1"][0]
                valid_c1 = df[~df[c1_col].isna() & ~df[depth_col].isna()]
                
                if len(valid_c1) >= 10:
                    # 计算移动窗口的Z分数
                    window_size = max(5, len(valid_c1) // 20)
                    valid_c1 = valid_c1.sort_values(by=depth_col)
                    valid_c1['rolling_mean'] = valid_c1[c1_col].rolling(window=window_size, center=True).mean()
                    valid_c1['rolling_std'] = valid_c1[c1_col].rolling(window=window_size, center=True).std()
                    
                    # 处理标准差为0的情况
                    mask = valid_c1['rolling_std'] > 0
                    if mask.any():
                        valid_c1.loc[mask, 'z_score'] = (valid_c1.loc[mask, c1_col] - valid_c1.loc[mask, 'rolling_mean']) / valid_c1.loc[mask, 'rolling_std']
                        
                        # 标记异常点(|Z| > 2)
                        anomalies = valid_c1[abs(valid_c1['z_score']) > 2]
                        
                        if len(anomalies) > 0:
                            ax1.scatter(anomalies[c1_col], anomalies[depth_col], 
                                      color='black', marker='x', s=100, label='异常点')
                            logger.info(f"标记了{len(anomalies)}个异常点")
        
        # 设置轴标签和网格
        ax1.set_xlabel('δ13C (‰)', fontsize=12)
        ax1.set_ylabel('深度 (m)', fontsize=12)
        ax1.grid(True, linestyle='--', alpha=0.7)
        
        # 设置深度轴范围
        depth_min = df[depth_col].min()
        depth_max = df[depth_col].max()
        if not pd.isna(depth_min) and not pd.isna(depth_max):
            # 添加一些边距
            padding = (depth_max - depth_min) * 0.05
            ax1.set_ylim(depth_max + padding, depth_min - padding)  # 反转Y轴，使深度从浅到深
        
        # 添加图例，放在图内部右上角位置，减少右侧空白
        ax1.legend(loc='upper right', fontsize=12, bbox_to_anchor=(0.98, 0.98), 
                  borderaxespad=0)
        
        # 添加辅助图：同位素差值随深度变化
        ax2 = plt.subplot2grid((1, 3), (0, 2))
        
        # 计算同位素差值
        if "C1" in isotope_columns and "C2" in isotope_columns:
            c1_col = isotope_columns["C1"][0]
            c2_col = isotope_columns["C2"][0]
            
            # 计算C1-C2差值
            df['c1_c2_diff'] = df[c2_col] - df[c1_col]
            
            # 过滤有效数据
            valid_diff = df[(~df['c1_c2_diff'].isna()) & (~df[depth_col].isna())]
            
            if len(valid_diff) >= 3:
                # 绘制差值随深度变化
                ax2.scatter(valid_diff['c1_c2_diff'], valid_diff[depth_col], color='purple', marker='o', 
                          s=30, alpha=0.7, label='δ13C2-δ13C1')
                
                # 添加成熟度区间参考线
                ax2.axvline(x=20, color='blue', linestyle=':', alpha=0.7, label='低成熟边界')
                ax2.axvline(x=10, color='orange', linestyle=':', alpha=0.7, label='中成熟边界')
                ax2.axvline(x=5, color='red', linestyle=':', alpha=0.7, label='高成熟边界')
                
                # 设置深度轴范围与主图一致
                if not pd.isna(depth_min) and not pd.isna(depth_max):
                    padding = (depth_max - depth_min) * 0.05
                    ax2.set_ylim(depth_max + padding, depth_min - padding)  # 反转Y轴
                
                # 添加图例
                ax2.legend(loc='best', fontsize=9)
        
        # 设置轴标签和网格
        ax2.set_xlabel('同位素差值 (‰)', fontsize=12)
        ax2.grid(True, linestyle='--', alpha=0.7)
        
        # 添加标题
        plt.suptitle('碳同位素随深度变化趋势分析', fontsize=14)
        
        # 保存图表
        # 使用增强版图表保存函数
        from app.tools.logging.iso_logging.enhanced_isotope_visualization import enhance_savefig
        
        # 保存高分辨率图表
        success = enhance_savefig(plt.gcf(), output_path, plot_name="碳同位素深度趋势分析图")
        
        if not success:
            logger.error("保存深度趋势图失败")
            plt.close()
            return None
            
        if writer:
            writer({"custom_step": f"同位素深度趋势图创建完成，正在保存..."})
        
        # 对于MinIO存储，直接保存文件
        if hasattr(file_manager_adapter, 'use_minio') and file_manager_adapter.use_minio:
            # 读取图片文件并上传到MinIO
            with open(output_path, 'rb') as f:
                file_data = f.read()
            
            file_info = file_manager_adapter.save_file(
                file_data=file_data,
                file_name=output_filename,
                file_type="image",
                source="generated",
                metadata={
                    "description": f"碳同位素深度趋势分析图: {file_name}",
                    "category": "analysis_result",  # 分析结果类别
                    "analysis_type": "isotope_depth_trend",  # 分析类型
                    "chart_type": "trend_plot",  # 图表类型
                    "geological_model": "true",  # 标记为地质建模相关
                    "original_file": file_name  # 原始文件名
                }
            )
            
            # 删除临时文件
            try:
                os.remove(output_path)
            except:
                pass
        else:
            # 本地存储，使用原来的方式
            file_info = file_manager_adapter.register_file(
                file_path=output_path,
                file_name=output_filename,
                file_type="image",
                source="generated",
                metadata={
                    "description": f"碳同位素深度趋势分析图: {file_name}",
                    "category": "analysis_result",  # 分析结果类别
                    "analysis_type": "isotope_depth_trend",  # 分析类型
                    "chart_type": "trend_plot",  # 图表类型
                    "geological_model": "true",  # 标记为地质建模相关
                    "original_file": file_name  # 原始文件名
                },
                skip_copy=True
            )
        
        file_id = file_info.get('file_id')
        
        # 在文件注册后立即发送图片消息
        if writer:
            # 图片消息已在enhance_savefig函数中发送，这里不需要重复发送
            writer({"custom_step": f"图表已生成并保存: {output_filename}\n"})
        
        return file_id
    except Exception as e:
        logger.error(f"创建深度趋势图出错: {str(e)}")
        if writer:
            writer({"custom_step": f"创建深度趋势图失败: {str(e)}"})
        plt.close('all')  # 确保关闭所有图表
        return None


def create_isotope_profile_plot(
    df: pd.DataFrame,
    isotope_columns: Dict[str, List[str]],
    depth_col: str,
    segments: List[Tuple[float, float]],
    file_name: str
) -> Optional[str]:
    """
    创建碳同位素深度剖面图
    
    Args:
        df: 数据框
        isotope_columns: 同位素列映射
        depth_col: 深度列名
        segments: 深度分段
        file_name: 输入文件名
        
    Returns:
        图表文件ID
    """
    try:
        # *** 关键修复：安全获取流写入器，避免上下文错误 ***
        writer = None
        try:
            writer = get_stream_writer()
        except (RuntimeError, AttributeError, ImportError, Exception):
            # 在测试环境或非LangGraph上下文中运行时，writer为None
            logger.debug(f"无法获取流式写入器，可能在测试环境中运行")
        
        if writer:
            writer({"custom_step": "开始创建同位素深度剖面图..."})
        
        # 确保工具执行时间间隔
        tool_tracker.wait_if_needed()
        
        # 确保文件名不包含不安全字符
        safe_filename = os.path.splitext(os.path.basename(file_name))[0].replace(" ", "_").replace(",", "_")
        
        # 从文件管理器获取正确的生成文件保存目录
        from app.core.file_manager_adapter import get_file_manager
        file_manager_adapter = get_file_manager()
        
        # 保存图表，确保边界正确，减小右侧边距
        plot_id = f"g-{uuid.uuid4().hex[:8]}"
        timestamp = int(time.time())  # 添加时间戳确保唯一性
        output_filename = f"{plot_id}_isotope_depth_profile_{safe_filename}_{timestamp}.png"
        
        # 对于MinIO存储，使用临时目录
        if hasattr(file_manager_adapter, 'use_minio') and file_manager_adapter.use_minio:
            import tempfile
            output_dir = tempfile.gettempdir()
        else:
            from app.core.file_manager import FileManager
            output_dir = FileManager.get_instance().generated_path
        
        output_path = os.path.join(output_dir, output_filename)
        
        # 检查是否在短时间内生成过相同数据的图片
        time_threshold = 60  # 60秒内的图片认为是重复的
        current_time = time.time()
        
        # 对于MinIO存储，跳过重复检查
        if not (hasattr(file_manager_adapter, 'use_minio') and file_manager_adapter.use_minio):
            pattern = f"*_isotope_depth_profile_{safe_filename}_*.png"
            
            recent_files = []
            for f in os.listdir(output_dir):
                if fnmatch.fnmatch(f, pattern):
                    file_path = os.path.join(output_dir, f)
                    file_time = os.path.getctime(file_path)
                    if current_time - file_time < time_threshold:
                        # 这是最近60秒内创建的文件
                        recent_files.append((f, file_path, file_time))
            
            if recent_files:
                # 找到最近的文件
                recent_files.sort(key=lambda x: x[2], reverse=True)  # 按创建时间排序
                recent_file, recent_path, _ = recent_files[0]
                
                logger.warning(f"检测到最近创建的深度剖面图: {recent_file}，使用现有文件")
                
                # 使用现有文件
                existing_info = file_manager.get_file_by_path(recent_path)
                if existing_info and existing_info.get('file_id'):
                    logger.info(f"使用现有文件ID: {existing_info.get('file_id')}")
                    return existing_info.get('file_id')
        
        # 彻底清理matplotlib状态
        plt.close('all')
        matplotlib.rcParams.update(matplotlib.rcParamsDefault)
        matplotlib.use('Agg', force=True)
        
        # *** 关键修复：重置参数后需要重新设置中文字体 ***
        setup_chinese_font()
        
        # 设置更可靠的图形参数
        plt.ioff()  # 确保非交互模式
        
        # 数据验证 - 确保有足够的数据进行绘图
        if depth_col not in df.columns:
            logger.error(f"深度列 '{depth_col}' 不在数据框中")
            return None
        
        # 检查有效的深度值
        valid_depth = df[~df[depth_col].isna()]
        if len(valid_depth) < 3:
            logger.error(f"深度列有效数据不足: {len(valid_depth)}行")
            return None
        
        # 确保至少有一个组分有数据
        has_valid_component = False
        component_data = []
        
        for component in ["C1", "C2", "C3"]:
            if component in isotope_columns and len(isotope_columns[component]) > 0:
                col = isotope_columns[component][0]
                if col in df.columns and not df[col].isna().all():
                    # 提取有效数据
                    valid_data = df[(~df[col].isna()) & (~df[depth_col].isna())]
                    if len(valid_data) >= 3:
                        has_valid_component = True
                        component_data.append((component, col, len(valid_data)))
        
        if not has_valid_component:
            logger.error("没有足够的有效同位素数据来创建剖面图")
            plt.close('all')
            return None
        
        # 记录数据状态供调试
        logger.info(f"有效组分数据: {component_data}")
        
        # 创建图表 - 减小高度，使比例更合理
        fig = plt.figure(figsize=(12, 20))
        
        # 主要同位素值的深度剖面
        components = ["C1", "C2", "C3"]
        colors = ["blue", "red", "green"]
        labels = ["δ13C-CH4", "δ13C-C2H6", "δ13C-C3H8"]
        
        # 创建主坐标轴
        ax = plt.gca()
        
        # 定义深度范围
        depth_min = df[depth_col].min()
        depth_max = df[depth_col].max()
        
        if pd.isna(depth_min) or pd.isna(depth_max):
            logger.error("深度范围无效，无法创建剖面图")
            plt.close('all')
            return None
        
        logger.info(f"设置深度范围: {depth_min} - {depth_max}")
        
        # 设置深度轴范围
        ax.set_ylim(depth_max * 1.01, depth_min * 0.99)  # 反转Y轴
        
        # 计算所有同位素值的范围，用于统一x轴
        x_values = []
        valid_components = []
        
        # 收集所有有效的同位素值
        for i, component in enumerate(components):
            if component in isotope_columns and isotope_columns[component]:
                col = isotope_columns[component][0]
                
                if col in df.columns:
                    valid_data = df[col].dropna()
                    if len(valid_data) > 1:
                        x_values.extend(valid_data.tolist())
                        valid_components.append((component, col, colors[i], labels[i]))
        
        if not x_values:
            logger.warning("没有找到有效的同位素数据，创建空白剖面图")
            # 创建一个提示信息
            ax.text(0.5, 0.5, "未找到有效的同位素数据", 
                   ha='center', va='center', transform=ax.transAxes,
                   fontsize=14, color='gray')
            
            # 设置一个默认的x轴范围
            ax.set_xlim(-50, -20)
        else:
            # 计算x轴范围，考虑数据分布和适当的边距
            x_min = min(x_values)
            x_max = max(x_values)
            x_range = x_max - x_min
            
            logger.info(f"同位素值范围: {x_min} - {x_max}")
            
            # 更适中的边距，确保数据不挤在一起且右侧不留过多空白
            x_padding = max(x_range * 0.15, 2.0)  # 减小边距，最小为2‰的余量
            
            # 设置x轴范围，确保更平衡的视觉效果
            ax.set_xlim(x_min - x_padding, x_max + x_padding * 1.5)  # 增加右侧边距以容纳标签
            
            # 添加各组分同位素曲线（统一使用一个横坐标）
            for component, col, color, label in valid_components:
                # 排序数据以便绘制连续线
                plot_df = df[[depth_col, col]].dropna().sort_values(by=depth_col)
                
                if len(plot_df) > 1:
                    # 绘制线和点
                    ax.plot(plot_df[col], plot_df[depth_col], '-', color=color, 
                            linewidth=2.0, alpha=0.7)
                    ax.scatter(plot_df[col], plot_df[depth_col], color=color, 
                              marker='o', s=35, alpha=0.6, label=label)
                    logger.info(f"成功绘制组分 {component} 的剖面线，数据点: {len(plot_df)}")
                else:
                    logger.warning(f"组分 {component} 没有足够的数据点绘制线")
        
        # 标记深度分段 - 参考test_real_data.py中的方法
        max_x_value = max(x_values) if x_values else 0
        
        if segments and len(segments) > 0:
            logger.info(f"添加 {len(segments)} 个深度分段标记")
            
            for i, (start, end) in enumerate(segments):
                # 确保深度值有效
                if pd.isna(start) or pd.isna(end):
                    logger.warning(f"分段 {i+1} 深度值无效: {start}-{end}")
                    continue
                    
                # 绘制水平分段线
                ax.axhline(y=start, color='gray', linestyle='-', alpha=0.5)
                try:
                    ax.axhspan(start, end, color=f"C{i % 10}", alpha=0.1)
                except Exception as e:
                    logger.warning(f"绘制深度分段背景色失败: {e}")
                
                # 计算分段中心深度
                mid_depth = (start + end) / 2
                
                # 标记每个分段的平均同位素值（如果有数据）
                if valid_components:
                    main_col = valid_components[0][1]  # 使用第一个组分计算
                    segment_df = df[(df[depth_col] >= start) & (df[depth_col] <= end)]
                    if not segment_df.empty and main_col in segment_df.columns:
                        seg_mean = segment_df[main_col].mean()
                        if not pd.isna(seg_mean):
                            ax.vlines(x=seg_mean, ymin=start, ymax=end, 
                                    colors='darkgray', linestyles='dotted')
                
                # 添加分段标签 - 按照test_real_data.py的方法
                try:
                    label_offset = 0.5  # 固定偏移量
                    label_x = max_x_value + label_offset
                    ax.text(label_x, mid_depth, f"R{i+1}", 
                          ha='left', va='center',  # 改为左对齐
                          color='red',  # 改为红色以更加醒目
                          fontsize=10,  # 稍微减小字体
                          bbox=dict(facecolor='white', alpha=0.7, boxstyle="round,pad=0.3"))
                except Exception as e:
                    logger.warning(f"添加分段标签失败: {e}")
        else:
            logger.warning("没有深度分段信息，跳过添加分段标记")
        
        # 添加图例，放在图内部右上角位置，减少右侧空白
        if valid_components:
            try:
                ax.legend(loc='upper right', fontsize=12, bbox_to_anchor=(0.98, 0.02), 
                         borderaxespad=0)
            except Exception as e:
                logger.warning(f"添加图例失败: {e}")
        
        # 设置轴标签和网格
        ax.set_xlabel('δ13C值 (‰)', fontsize=14)
        ax.set_ylabel('深度 (m)', fontsize=14)
        ax.grid(True, linestyle='--', alpha=0.7)
        
        # 添加标题
        plt.title('碳同位素深度剖面图', fontsize=16)
        
        # 强制设置x轴刻度，增加可读性
        try:
            x_min, x_max = ax.get_xlim()
            plt.xticks(np.arange(np.floor(x_min), np.ceil(x_max) + 1, 5.0))
        except Exception as e:
            logger.warning(f"设置x轴刻度失败: {e}")
        
        # 添加水平网格线以增强可读性
        ax.grid(True, which='major', axis='both', linestyle='--', alpha=0.7)
        
        # 检查图表是否有内容
        has_data = len(ax.collections) > 0 or len(ax.lines) > 0 or len(ax.patches) > 0 or len(ax.texts) > 0 
        if not has_data:
            logger.warning("图表没有可视化元素，可能会生成空白图片")
            # 添加一个文本说明
            ax.text(0.5, 0.5, "未能生成有效的剖面图\n请检查数据质量", 
                  ha='center', va='center', transform=ax.transAxes,
                  fontsize=16, color='red')
        
        # 保存图表前强制绘制
        fig.canvas.draw()
        
        # 使用增强版图表保存函数
        from app.tools.logging.iso_logging.enhanced_isotope_visualization import enhance_savefig
        
        # 保存高分辨率图表
        success = enhance_savefig(fig, output_path, plot_name="碳同位素深度剖面图")
        
        if not success:
            logger.error("保存深度剖面图失败")
            plt.close('all')
            return None
            
        if writer:
            writer({"custom_step": f"同位素深度剖面图创建\n"})
        
        # 对于MinIO存储，直接保存文件
        try:
            if hasattr(file_manager_adapter, 'use_minio') and file_manager_adapter.use_minio:
                # 读取图片文件并上传到MinIO
                with open(output_path, 'rb') as f:
                    file_data = f.read()
                
                file_info = file_manager_adapter.save_file(
                    file_data=file_data,
                    file_name=output_filename,
                    file_type="image",
                    source="generated",
                    metadata={
                        "description": "碳同位素深度剖面图",
                        "category": "analysis_result",  # 分析结果类别
                        "analysis_type": "isotope_depth_profile",  # 分析类型
                        "chart_type": "profile_plot",  # 图表类型
                        "geological_model": "true",  # 标记为地质建模相关
                        "original_file": file_name  # 原始文件名
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
                plot_file_id = file_manager_adapter.register_file(
                    file_path=output_path,
                    file_name=output_filename,
                    file_type="image",
                    source="generated",
                    metadata={
                        "description": "碳同位素深度剖面图",
                        "category": "analysis_result",  # 分析结果类别
                        "analysis_type": "isotope_depth_profile",  # 分析类型
                        "chart_type": "profile_plot",  # 图表类型
                        "geological_model": "true",  # 标记为地质建模相关
                        "original_file": file_name  # 原始文件名
                    },
                    session_id=None,
                    skip_copy=True
                )
            
            return plot_file_id
        except Exception as register_err:
            logger.error(f"注册剖面图文件时出错: {str(register_err)}", exc_info=True)
            return None
    except Exception as e:
        logger.error(f"创建同位素剖面图时出错: {str(e)}", exc_info=True)
        plt.close('all')  # 确保关闭所有图表
        return None

def generate_depth_trend_report(
    global_features: Dict[str, Any],
    segment_features: List[Dict[str, Any]],
    isotope_columns: Dict[str, List[str]],
    trend_plot_id: Optional[str] = None,
    profile_plot_id: Optional[str] = None
) -> str:
    """
    生成碳同位素深度趋势分析报告，借鉴原有方法生成更详细的分段报告和地质解释
    
    Args:
        global_features: 全局特征字典
        segment_features: 分段特征列表
        isotope_columns: 同位素列映射
        trend_plot_id: 趋势图文件ID
        profile_plot_id: 剖面图文件ID
        
    Returns:
        格式化的分析报告
    """
    # 提取关键特征
    c1_mean = global_features.get("mean_c1_d13c")
    c2_mean = global_features.get("mean_c2_d13c")
    c3_mean = global_features.get("mean_c3_d13c")
    c1_c2_diff = global_features.get("c1_c2_diff")
    has_reversal = global_features.get("has_isotope_reversal", False)
    depth_range = global_features.get("depth_range")
    c1_depth_slope = global_features.get("c1_depth_slope")
    c1_depth_r_value = global_features.get("c1_depth_r_value")
    c1_min = global_features.get("min_c1_d13c")
    c1_max = global_features.get("max_c1_d13c")
    c1_std = global_features.get("std_c1_d13c")
    
    # 准备报告头部
    report = f"""## 碳同位素深度趋势分析报告

### 总体数据特征:
"""

    # 添加基本信息
    if c1_mean is not None:
        report += f"- 甲烷碳同位素(δ13C-CH4)平均值: {c1_mean:.2f}‰\n"
    if c2_mean is not None:
        report += f"- 乙烷碳同位素(δ13C-C2H6)平均值: {c2_mean:.2f}‰\n"
    if c3_mean is not None:
        report += f"- 丙烷碳同位素(δ13C-C3H8)平均值: {c3_mean:.2f}‰\n"
    if c1_c2_diff is not None:
        report += f"- C1-C2同位素差值: {c1_c2_diff:.2f}‰\n"
    
    report += f"- 同位素倒转现象: {'存在' if has_reversal else '不存在'}\n"
    
    if depth_range is not None:
        report += f"- 深度范围: {depth_range:.2f}米\n"
    
    # 添加数据概况，借鉴老方法
    if c1_mean is not None and c1_min is not None and c1_max is not None and c1_std is not None:
        report += f"- 甲烷碳同位素值范围: {c1_min:.2f}‰至{c1_max:.2f}‰\n"
        report += f"- 标准差: {c1_std:.2f}‰\n"
        
        # 估计噪声水平
        noise_level = c1_std / 2
        report += f"- 估计噪声水平: {noise_level:.2f}‰\n"
    
    # 添加总体趋势分析
    report += "\n### 总体趋势分析:\n"
    
    # 如果有深度相关性数据，分析总体趋势
    if c1_depth_slope is not None and c1_depth_r_value is not None:
        # 计算每千米的变化率（斜率乘以1000，因为深度通常以米为单位）
        change_per_km = c1_depth_slope * 1000
        r_squared = c1_depth_r_value**2
        
        # 趋势方向描述
        trend_direction = "增加" if c1_depth_slope > 0.0001 else ("减小" if c1_depth_slope < -0.0001 else "保持相对稳定")
        
        # 趋势强度描述
        if abs(change_per_km) < 0.01:
            trend_str = "基本无变化"
        elif change_per_km > 0:
            if change_per_km > 1.0:
                trend_str = "显著增加"
            elif change_per_km > 0.5:
                trend_str = "明显增加"
            else:
                trend_str = "轻微增加"
        else:
            if change_per_km < -1.0:
                trend_str = "显著减小"
            elif change_per_km < -0.5:
                trend_str = "明显减小"
            else:
                trend_str = "轻微减小"
        
        report += f"- 甲烷碳同位素值随深度整体呈{trend_str}趋势 (R² = {r_squared:.2f})，平均每千米变化约 {change_per_km:.2f}‰\n"
        
        # 相关性强度描述
        if r_squared > 0.6:
            correlation_str = "强相关"
        elif r_squared > 0.3:
            correlation_str = "中等相关"
        elif r_squared > 0.1:
            correlation_str = "弱相关"
        else:
            correlation_str = "几乎无相关"
            
        report += f"- 深度与甲烷碳同位素值呈{correlation_str} (R² = {r_squared:.2f})\n"
    else:
        report += "- 无法确定甲烷碳同位素值与深度的相关性，可能是由于数据点不足或数据质量问题\n"
    
    # 添加变化趋势分段分析
    report += "\n### 变化趋势分段分析:\n"
    
    if segment_features and len(segment_features) > 1:
        report += f"识别出{len(segment_features)}个深度分段，各分段特征如下：\n\n"
        
        for i, segment in enumerate(segment_features):
            segment_id = segment.get("segment_id", i+1)
            depth_start = segment.get("depth_start")
            depth_end = segment.get("depth_end")
            c1_mean = segment.get("mean_c1_d13c")
            c1_std = segment.get("std_c1_d13c")
            c1_min = segment.get("min_c1_d13c")
            c1_max = segment.get("max_c1_d13c")
            data_points = segment.get("data_points", 0)
            
            report += f"**分段{segment_id}** (深度: {depth_start:.2f}米 - {depth_end:.2f}米, 数据点: {data_points}个):\n"
            
            if c1_mean is not None:
                report += f"- 甲烷碳同位素平均值: {c1_mean:.2f}‰"
                if c1_std is not None:
                    report += f", 标准差: {c1_std:.2f}‰"
                if c1_min is not None and c1_max is not None:
                    report += f", 范围: {c1_min:.2f}‰ 至 {c1_max:.2f}‰"
                report += "\n"
            
            # 如果有足够数据，分析段内趋势
            c1_depth_slope = segment.get("c1_depth_slope")
            c1_depth_r_value = segment.get("c1_depth_r_value")
            
            if c1_depth_slope is not None and c1_depth_r_value is not None:
                # 计算每千米的变化率
                change_per_km = c1_depth_slope * 1000
                r_squared = c1_depth_r_value**2
                
                # 判断趋势类型
                if abs(change_per_km) < 0.5:
                    trend_desc = "保持相对稳定"
                    rate_desc = ""
                else:
                    if change_per_km > 0:
                        if change_per_km > 5.0:
                            trend_desc = "快速增加"
                        elif change_per_km > 2.0:
                            trend_desc = "中速增加"
                        else:
                            trend_desc = "缓慢增加"
                    else:
                        if change_per_km < -5.0:
                            trend_desc = "快速减小"
                        elif change_per_km < -2.0:
                            trend_desc = "中速减小"
                        else:
                            trend_desc = "缓慢减小"
                    
                    rate_desc = f"（平均每千米{abs(change_per_km):.2f}‰）"
                
                # 相关性强度
                if r_squared > 0.6:
                    reliability = "高可靠性"
                elif r_squared > 0.3:
                    reliability = "中等可靠性"
                else:
                    reliability = "低可靠性"
                
                report += f"- 段内趋势: 甲烷碳同位素值{trend_desc}{rate_desc}, {reliability} (R² = {r_squared:.2f})\n"
            
            # 检测同位素倒转现象
            has_reversal = segment.get("has_isotope_reversal", False)
            if has_reversal:
                report += "- 该段存在同位素倒转现象，可能指示混合成因气或微生物改造作用\n"
                
            # 检测特殊特征
            c1_c2_diff = segment.get("c1_c2_diff")
            if c1_c2_diff is not None:
                if c1_c2_diff < 0:
                    report += f"- C1-C2同位素差值为负({c1_c2_diff:.2f}‰)，强烈指示同位素倒转，可能与微生物过程相关\n"
                elif c1_c2_diff < 5:
                    report += f"- C1-C2同位素差值较小({c1_c2_diff:.2f}‰)，可能指示高成熟度气体\n"
                elif c1_c2_diff > 15:
                    report += f"- C1-C2同位素差值较大({c1_c2_diff:.2f}‰)，可能指示低成熟度气体\n"
            
            report += "\n"
        
        # 如果有足够的分段，对分段之间的变化进行分析
        if len(segment_features) >= 2:
            report += "**分段间对比分析**:\n"
            
            # 提取分段的甲烷碳同位素平均值
            c1_values = []
            c1_depths = []
            c1_c2_diffs = []
            c1_c2_depths = []
            
            for segment in segment_features:
                if "mean_c1_d13c" in segment:
                    c1_values.append(segment["mean_c1_d13c"])
                    c1_depths.append((segment["depth_start"] + segment["depth_end"]) / 2)
                
                if "c1_c2_diff" in segment:
                    c1_c2_diffs.append(segment["c1_c2_diff"])
                    c1_c2_depths.append((segment["depth_start"] + segment["depth_end"]) / 2)
            
            # 分析甲烷碳同位素值在不同分段的趋势
            if len(c1_values) >= 3:
                # 分析趋势连续性
                is_increasing = all(c1_values[i] <= c1_values[i+1] for i in range(len(c1_values)-1))
                is_decreasing = all(c1_values[i] >= c1_values[i+1] for i in range(len(c1_values)-1))
                
                if is_increasing:
                    report += "- 甲烷碳同位素值随深度**持续变重**，呈现典型的成熟度随深度增加的特征\n"
                elif is_decreasing:
                    report += "- 甲烷碳同位素值随深度**持续变轻**，可能指示深部不同气源的贡献或反常的成熟度分布\n"
                else:
                    # 检查是否有明显的拐点
                    peaks = []
                    valleys = []
                    
                    for i in range(1, len(c1_values)-1):
                        if c1_values[i] > c1_values[i-1] and c1_values[i] > c1_values[i+1]:
                            peaks.append((c1_depths[i], c1_values[i], i+1))
                        elif c1_values[i] < c1_values[i-1] and c1_values[i] < c1_values[i+1]:
                            valleys.append((c1_depths[i], c1_values[i], i+1))
                    
                    if peaks or valleys:
                        report += "- 检测到甲烷碳同位素值随深度的**非线性变化**:\n"
                        
                        if peaks:
                            report += "  - **峰值点**:\n"
                            for depth, value, idx in peaks:
                                report += f"    + 深度约{depth:.1f}米(段{idx})处达到局部最重值{value:.2f}‰\n"
                        
                        if valleys:
                            report += "  - **谷值点**:\n"
                            for depth, value, idx in valleys:
                                report += f"    + 深度约{depth:.1f}米(段{idx})处达到局部最轻值{value:.2f}‰\n"
                        
                        report += "  这种波动模式可能指示多期次气源充注、断裂带流体活动或沉积环境变化等地质过程\n"
                    else:
                        report += "- 甲烷碳同位素值随深度呈**不规则变化**，可能受多种因素影响\n"
            
            # 分析C1-C2差值的变化趋势
            if len(c1_c2_diffs) >= 3:
                # 分析差值趋势
                is_diff_decreasing = all(c1_c2_diffs[i] >= c1_c2_diffs[i+1] for i in range(len(c1_c2_diffs)-1))
                
                if is_diff_decreasing:
                    report += "- C1-C2同位素差值随深度**持续减小**，符合成熟度随深度增加的典型模式\n"
                else:
                    # 检查是否有异常大的变化点
                    anomalies = []
                    for i in range(1, len(c1_c2_diffs)):
                        change = c1_c2_diffs[i] - c1_c2_diffs[i-1]
                        if abs(change) > 5:  # 判断差值变化显著的阈值
                            anomalies.append((c1_c2_depths[i], change, i+1))
                    
                    if anomalies:
                        report += "- 检测到C1-C2同位素差值的**显著变化点**:\n"
                        
                        for depth, change, idx in anomalies:
                            direction = "增大" if change > 0 else "减小"
                            report += f"  - 在深度约{depth:.1f}米(段{idx})处差值突然{direction}{abs(change):.2f}‰\n"
                        
                        report += "  这种突变可能指示不同气源的界面或成熟度的突变带\n"
            
            # 检查倒转现象的分布
            reversal_segments = [s for s in segment_features if s.get("has_isotope_reversal", False)]
            non_reversal_segments = [s for s in segment_features if not s.get("has_isotope_reversal", False)]
            
            if reversal_segments and non_reversal_segments:
                report += "- 同位素倒转现象在深度上呈**不均匀分布**，可能指示局部改造过程或断层封闭单元\n"
                
                reversal_depths = []
                for s in reversal_segments:
                    reversal_depths.append(f"{s['depth_start']:.1f}-{s['depth_end']:.1f}米")
                
                report += f"  - 存在倒转的深度段: {', '.join(reversal_depths)}\n"
    else:
        # 如果只有一个分段或没有分段
        report += "未检测到明显的变化分段，整体趋势分析已在上节描述。\n"
    
    # 添加关键深度区间识别
    report += "\n### 关键深度区间:\n"
    
    # 检测特殊区间
    special_intervals = []
    
    # 如果有分段
    if segment_features and len(segment_features) > 1:
        # 找出异常的分段
        c1_means = [s.get("mean_c1_d13c") for s in segment_features if s.get("mean_c1_d13c") is not None]
        
        if c1_means:
            global_mean = np.mean(c1_means)
            global_std = np.std(c1_means)
            
            for i, segment in enumerate(segment_features):
                c1_mean = segment.get("mean_c1_d13c")
                if c1_mean is not None and global_std > 0:
                    z_score = (c1_mean - global_mean) / global_std
                    
                    if abs(z_score) > 1.5:
                        depth_start = segment.get("depth_start")
                        depth_end = segment.get("depth_end")
                        if depth_start is not None and depth_end is not None:
                            direction = "重" if c1_mean > global_mean else "轻"
                            special_intervals.append({
                                "start": depth_start,
                                "end": depth_end,
                                "type": "异常" + direction,
                                "z_score": z_score,
                                "value": c1_mean
                            })
    
    # 如果发现了特殊区间
    if special_intervals:
        report += "识别出以下关键深度区间:\n\n"
        
        for interval in special_intervals:
            report += f"- {interval['start']:.1f}米至{interval['end']:.1f}米: 甲烷碳同位素值**{interval['type']}**异常"
            report += f" ({interval['value']:.2f}‰, Z值={interval['z_score']:.1f})\n"
    else:
        report += "未检测到特殊的异常区间，整体趋势平稳。\n"
    
    # 添加地质意义解释
    report += "\n### 地质意义解释:\n"
    
    # 根据整体特征和分段特征添加解释
    if segment_features and len(segment_features) <= 1:
        # 单一趋势
        if c1_depth_slope is not None:
            if abs(c1_depth_slope * 1000) > 1.0:
                report += f"- 整个井段碳同位素值呈{trend_str}趋势，可能反映了气源岩热演化程度随深度的{trend_direction}\n"
            else:
                report += "- 整个井段碳同位素值相对稳定，表明气源条件较为一致\n"
    else:
        # 多段趋势
        report += f"- 井段内碳同位素值存在{len(segment_features)}个明显不同的变化区段，可能反映了：\n"
        report += "  1. 不同深度区间储层气源条件的差异\n"
        report += "  2. 地层中可能存在的断层或不整合面\n"
        report += "  3. 不同成熟度气体的混合或差异迁移\n"
    
    # 根据同位素特征添加气源和成熟度解释
    if c1_mean is not None:
        report += "\n**气源类型推断**:\n"
        
        if c1_mean < -60:
            report += "- 甲烷碳同位素平均值较轻(< -60‰)，指示以**生物成因气**为主\n"
        elif c1_mean > -40:
            report += "- 甲烷碳同位素平均值较重(> -40‰)，指示以**高成熟热成因气**为主\n"
        elif c1_mean > -50:
            report += "- 甲烷碳同位素平均值位于-50‰至-40‰之间，指示以**热成因气**为主\n"
        else:
            report += "- 甲烷碳同位素平均值位于-60‰至-50‰之间，可能为**混合成因气**或**低熟热成因气**\n"
    
    if has_reversal:
        report += "- 检测到同位素倒转现象，可能与以下因素有关：\n"
        report += "  1. 微生物氧化作用导致的甲烷同位素重积累\n"
        report += "  2. 高成熟度气源的贡献\n"
        report += "  3. 不同成因气体的混合\n"
    
    # 添加图表引用
    report += "\n### 可视化分析:\n"
    
    if trend_plot_id:
        report += f"- 深度趋势分析图 (文件ID: {trend_plot_id})\n"
    
    if profile_plot_id:
        report += f"- 同位素深度剖面图 (文件ID: {profile_plot_id})\n"
    
    return report 