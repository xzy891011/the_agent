"""
三角图版法解释含油气性质工具

该工具基于Q值计算进行含油气性质判别：
Q=1−(C2+C3+nC4)/(0.2∑C)

评价标准：
Q值范围        内三角形形状    含油气性质
75%～100%     大正三角形      水或气层
25%～75%      中正三角形      油气层或含油水层
0%～25%       小正三角形      油气转化带
-25%～0%      小倒三角形      油气转化带
-25%～-75%    中倒三角形      油层（高气油比）
-75%～-100%   大倒三角形      油层（高气油比）
"""

import os
import logging
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
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

def calculate_q_value(row: pd.Series) -> float:
    """计算Q值
    
    Q=1−(C2+C3+nC4)/(0.2∑C)
    
    Args:
        row: 包含气体组分数据的行
        
    Returns:
        计算得到的Q值
    """
    try:
        # 提取气体组分数据
        c1 = float(row.get('C1', 0) or 0)  # 甲烷
        c2 = float(row.get('C2', 0) or 0)  # 乙烷
        c3 = float(row.get('C3', 0) or 0)  # 丙烷
        ic4 = float(row.get('iC4', 0) or 0)  # 异丁烷
        nc4 = float(row.get('nC4', 0) or 0)  # 正丁烷
        ic5 = float(row.get('iC5', 0) or 0)  # 异戊烷
        nc5 = float(row.get('nC5', 0) or 0)  # 正戊烷
        
        # 计算总碳氢化合物含量 ∑C
        total_c = c1 + c2 + c3 + ic4 + nc4 + ic5 + nc5
        
        # 如果总碳氢化合物含量为0，返回None
        if total_c == 0:
            return None
            
        # 计算Q值：Q=1−(C2+C3+nC4)/(0.2∑C)
        q_value = 1 - (c2 + c3 + nc4) / (0.2 * total_c)
        
        return q_value
        
    except Exception as e:
        logger.warning(f"计算Q值时出错: {e}")
        return None

def classify_oil_gas_nature(q_value: float) -> Dict[str, str]:
    """根据Q值范围评价含油气性质
    
    Args:
        q_value: Q值
        
    Returns:
        包含分类结果的字典
    """
    if q_value is None:
        return {
            "q_range": "无效数据",
            "triangle_shape": "无法判断", 
            "oil_gas_nature": "无法判断"
        }
    
    # 转换为百分比进行判断
    q_percent = q_value * 100
    
    if 75 <= q_percent <= 100:
        return {
            "q_range": "75%～100%",
            "triangle_shape": "大正三角形",
            "oil_gas_nature": "水或气层"
        }
    elif 25 <= q_percent < 75:
        return {
            "q_range": "25%～75%", 
            "triangle_shape": "中正三角形",
            "oil_gas_nature": "油气层或含油水层"
        }
    elif 0 <= q_percent < 25:
        return {
            "q_range": "0%～25%",
            "triangle_shape": "小正三角形", 
            "oil_gas_nature": "油气转化带"
        }
    elif -25 <= q_percent < 0:
        return {
            "q_range": "-25%～0%",
            "triangle_shape": "小倒三角形",
            "oil_gas_nature": "油气转化带"
        }
    elif -75 <= q_percent < -25:
        return {
            "q_range": "-25%～-75%",
            "triangle_shape": "中倒三角形",
            "oil_gas_nature": "油层（高气油比）"
        }
    elif -100 <= q_percent < -75:
        return {
            "q_range": "-75%～-100%",
            "triangle_shape": "大倒三角形", 
            "oil_gas_nature": "油层（高气油比）"
        }
    else:
        return {
            "q_range": f"{q_percent:.1f}%",
            "triangle_shape": "异常值",
            "oil_gas_nature": "异常值"
        }

def create_triangular_chart_visualization(df: pd.DataFrame, output_path: str) -> str:
    """创建三角图版法可视化图表
    
    Args:
        df: 包含Q值和分类结果的数据框
        output_path: 输出图片路径
        
    Returns:
        图片文件路径
    """
    try:
        # 设置matplotlib使用Agg后端，避免显示问题
        import matplotlib
        matplotlib.use('Agg')
        
        setup_chinese_font()
        
        # 创建图表
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
        
        # 左图：Q值深度剖面图
        depths = df['Depth'].values
        q_values = df['Q值'].values
        
        # 过滤有效的Q值
        valid_mask = pd.notna(q_values) & pd.notna(depths)
        valid_depths = depths[valid_mask]
        valid_q_values = q_values[valid_mask]
        
        if len(valid_q_values) > 0:
            ax1.plot(valid_q_values, valid_depths, 'bo-', linewidth=2, markersize=4)
            ax1.invert_yaxis()  # 深度轴反向
            ax1.set_xlabel('Q值', fontsize=12)
            ax1.set_ylabel('深度 (m)', fontsize=12)
            ax1.set_title('Q值深度剖面图', fontsize=14, fontweight='bold')
            ax1.grid(True, alpha=0.3)
            
            # 添加Q值分区线
            x_min, x_max = ax1.get_xlim()
            for q_threshold in [1.0, 0.75, 0.25, 0, -0.25, -0.75, -1.0]:
                if x_min <= q_threshold <= x_max:
                    ax1.axvline(x=q_threshold, color='red', linestyle='--', alpha=0.7)
                    # 添加标签
                    y_pos = (valid_depths.min() + valid_depths.max()) / 2
                    ax1.text(q_threshold, y_pos, f'{q_threshold}', rotation=90, 
                            fontsize=8, color='red', ha='center')
        else:
            ax1.text(0.5, 0.5, '无有效数据', transform=ax1.transAxes, 
                    ha='center', va='center', fontsize=12)
        
        # 右图：含油气性质统计饼图
        nature_counts = df['含油气性质'].value_counts()
        
        if len(nature_counts) > 0:
            colors = ['#ff9999', '#66b3ff', '#99ff99', '#ffcc99', '#ff99cc', '#c2c2f0']
            ax2.pie(nature_counts.values, labels=nature_counts.index, autopct='%1.1f%%',
                   colors=colors[:len(nature_counts)], startangle=90)
            ax2.set_title('含油气性质分布', fontsize=14, fontweight='bold')
        else:
            ax2.text(0.5, 0.5, '无分类数据', transform=ax2.transAxes, 
                    ha='center', va='center', fontsize=12)
        
        plt.tight_layout()
        
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # 保存图片
        plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close()
        
        logger.info(f"三角图版法可视化图表已保存: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"创建可视化图表失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        if 'fig' in locals():
            plt.close(fig)
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

def process_excel_file(file_path: str) -> Tuple[pd.DataFrame, str]:
    """处理Excel文件，计算Q值和分类结果
    
    Args:
        file_path: Excel文件路径
        
    Returns:
        处理后的数据框和输出文件路径
    """
    try:
        # 读取完整的Excel文件包括表头
        full_df = pd.read_excel(file_path)
        
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
        data_df = pd.read_excel(file_path, skiprows=skip_rows)
        logger.info(f"成功读取Excel文件，跳过{skip_rows}行表头，共{len(data_df)}行数据")
        logger.info(f"第一行内容: {first_row}")
        if second_row:
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
            # 第一行是中文表头，转换为英文列名
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
            
            # 使用英文列名设置DataFrame
            if len(english_headers) >= len(data_df.columns):
                data_df.columns = english_headers[:len(data_df.columns)]
                logger.info(f"使用转换后的英文列名: {list(data_df.columns)}")
            else:
                # 补充列名
                final_columns = english_headers + [f"Col{i}" for i in range(len(english_headers), len(data_df.columns))]
                data_df.columns = final_columns
                logger.info(f"补充列名后使用: {list(data_df.columns)}")
                
            # 保存原始表头用于重建
            original_chinese_headers = chinese_headers_list[:len(data_df.columns)]
            original_english_headers = english_headers[:len(data_df.columns)]
            
        else:
            # 可能是英文表头或其他格式，使用默认处理
            logger.info("未检测到标准中文表头，使用默认列名")
            default_columns = ["Well", "Depth", "Rop", "Tg", "C1", "C2", "C3", "iC4", "nC4", "iC5", "nC5", "CO2", "Other"]
            data_df.columns = default_columns[:len(data_df.columns)]
            logger.info(f"使用默认英文列名: {list(data_df.columns)}")
            
            # 创建默认的中英文表头
            original_english_headers = list(data_df.columns)
            original_chinese_headers = ['井名', '井深', '钻时', '全量', '甲烷', '乙烷', '丙烷', '异丁烷', '正丁烷', '异戊烷', '正戊烷', '二氧化碳', '其它非烃'][:len(data_df.columns)]
        
        # 清理数据：删除空行和无效数据
        data_df = data_df.dropna(subset=['Well', 'Depth'])
        
        # 确保数值列是数值类型
        numeric_columns = ['Depth', 'Rop', 'Tg', 'C1', 'C2', 'C3', 'iC4', 'nC4', 'iC5', 'nC5', 'CO2', 'Other']
        for col in numeric_columns:
            if col in data_df.columns:
                data_df[col] = pd.to_numeric(data_df[col], errors='coerce')
        
        # 再次删除转换后的无效行
        data_df = data_df.dropna(subset=['C1', 'C2', 'C3', 'nC4'])
        
        logger.info(f"数据清理后，共{len(data_df)}行有效数据")
        
        # 检查必需的列是否存在
        required_columns = ['Well', 'Depth', 'C1', 'C2', 'C3', 'nC4']
        missing_columns = [col for col in required_columns if col not in data_df.columns]
        
        if missing_columns:
            raise ValueError(f"缺少必需的列: {missing_columns}")
        
        # 计算Q值
        logger.info("开始计算Q值...")
        data_df['Q值'] = data_df.apply(calculate_q_value, axis=1)
        
        # 计算分类结果
        logger.info("开始进行含油气性质分类...")
        classification_results = data_df['Q值'].apply(classify_oil_gas_nature)
        
        # 展开分类结果到单独的列
        data_df['Q值范围'] = [result['q_range'] for result in classification_results]
        data_df['内三角形形状'] = [result['triangle_shape'] for result in classification_results]
        data_df['含油气性质'] = [result['oil_gas_nature'] for result in classification_results]
        
        # 判断是否为已解释的文件
        input_filename = Path(file_path).name
        is_interpreted = is_interpreted_file(input_filename)
        
        # 重建完整的Excel文件结构，保持原始双行表头格式
        logger.info("开始重建Excel文件结构...")
        
        # 1. 使用之前保存的原始表头数据
        # original_english_headers和original_chinese_headers已经在上面定义
        
        # 2. 清理原始表头，确保数量匹配原始数据列数
        original_data_columns = len(data_df.columns) - 4  # 减去新增的4列
        clean_english_headers = original_english_headers[:original_data_columns]
        clean_chinese_headers = original_chinese_headers[:original_data_columns]
        
        # 确保长度足够
        while len(clean_english_headers) < original_data_columns:
            clean_english_headers.append(f"Col{len(clean_english_headers)+1}")
        while len(clean_chinese_headers) < original_data_columns:
            clean_chinese_headers.append(f"列{len(clean_chinese_headers)+1}")
        
        # 3. 为新增列添加表头
        new_english_headers = ['Q_value', 'Q_range', 'Triangle_shape', 'Oil_gas_nature']
        new_chinese_headers = ['Q值', 'Q值范围', '内三角形形状', '含油气性质']
        
        # 4. 合并表头（原始表头 + 新增表头）
        full_english_headers = clean_english_headers + new_english_headers
        full_chinese_headers = clean_chinese_headers + new_chinese_headers
        
        logger.info(f"最终表头长度 - 英文: {len(full_english_headers)}, 中文: {len(full_chinese_headers)}, 数据列: {len(data_df.columns)}")
        
        # 5. 构建最终的DataFrame
        # 创建表头行（保持原始格式：第一行英文，第二行中文）
        row1_data = [full_english_headers[i] if i < len(full_english_headers) else '' for i in range(len(data_df.columns))]
        row2_data = [full_chinese_headers[i] if i < len(full_chinese_headers) else '' for i in range(len(data_df.columns))]
        
        # 创建完整的DataFrame，包含表头和数据
        all_data = []
        all_data.append(row1_data)  # 第一行：英文表头
        all_data.append(row2_data)  # 第二行：中文表头
        
        # 添加所有数据行（转换为字符串避免类型问题）
        for _, row in data_df.iterrows():
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
        return data_df, output_path
        
    except Exception as e:
        logger.error(f"处理Excel文件失败: {e}")
        raise

@register_tool(category="gas_logging")
def triangular_chart_analysis(file_id: str) -> str:
    """气测录井分析第二步-三角图版法解释含油气性质工具
    
    基于Q值计算进行含油气性质判别。Q值计算公式：Q=1−(C2+C3+nC4)/(0.2∑C)
    
    根据Q值范围评价含油气性质：
    - 75%～100%：水或气层（大正三角形）
    - 25%～75%：油气层或含油水层（中正三角形）  
    - 0%～25%：油气转化带（小正三角形）
    - -25%～0%：油气转化带（小倒三角形）
    - -25%～-75%：油层（高气油比）（中倒三角形）
    - -75%～-100%：油层（高气油比）（大倒三角形）
    
    Args:
        file_id: Excel文件ID，可以是原始上传文件或前一工具生成的解释文件。
                如果是在其他录井工具之后执行，应使用前一工具返回信息中的NEXT_FILE_ID，
                以在已有解释结果基础上追加新的分析列。
                文件应包含Well、Depth、C1、C2、C3、nC4等列。
        
    Returns:
        分析结果报告，包含新生成文件的NEXT_FILE_ID供后续工具使用
    """
    writer = get_stream_writer()
    
    try:
        if writer:
            writer({"custom_step": "开始三角图版法含油气性质分析..."})
        
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
        df, output_excel_path = process_excel_file(file_path)
        
        if writer:
            writer({"custom_step": f"成功处理{len(df)}行数据，计算Q值并进行分类"})
        
        # 生成可视化图表
        # 去掉文件名中的ID前缀，生成清洁的图片文件名
        clean_filename = remove_file_id_prefix(file_name)
        base_name = Path(clean_filename).stem
        # 使用更直观的文件名
        image_filename = f"三角图版法解释图表_{base_name}.png"
        
        # 临时路径用于生成图片
        temp_image_path = os.path.join(file_manager.temp_path, f"temp_{image_filename}")
        chart_path = create_triangular_chart_visualization(df, temp_image_path)
        
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
        valid_samples = df['Q值'].notna().sum()
        
        # 统计各类型的样品数量
        nature_stats = df['含油气性质'].value_counts()
        
        if writer:
            writer({"custom_step": f"生成可视化图表: {image_filename}"})
        
        # 推送图片到UI
        if final_image_path and os.path.exists(final_image_path):
            image_message = {
                "image_path": final_image_path,
                "title": "三角图版法解释图表"
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
        if len(nature_stats) > 0:
            main_nature = nature_stats.index[0]
            main_percentage = (nature_stats.iloc[0] / total_samples) * 100
            nature_summary = f"主要层型：{main_nature}({main_percentage:.1f}%)"
        else:
            nature_summary = "无有效分类结果"
        
        result_message = f"""✅ 三角图版法分析完成
🆔 **NEXT_FILE_ID: {file_id}** (后续工具请使用此file_id)
📊 处理样品: {total_samples}个 (有效: {valid_samples}个)
🎯 {nature_summary}
📁 解释结果文件: {Path(output_excel_path).name}
📈 可视化图表: {image_filename}

⚠️ 重要: 后续工具必须使用file_id: {file_id} 以在此结果基础上追加分析"""
        
        if writer:
            writer({"custom_step": "三角图版法分析完成"})
        
        logger.info("三角图版法含油气性质分析完成")
        return result_message
        
    except Exception as e:
        error_msg = f"三角图版法分析失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        if writer:
            writer({"custom_step": f"❌ {error_msg}"})
        
        return error_msg 