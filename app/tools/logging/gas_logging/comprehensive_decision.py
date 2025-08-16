#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
综合分析判定工具（气测录井）

融合全烃TG、三角图版法、3H比值法三类解释结果，对每个深度样品给出综合层型与综合置信度，
并将结果以追加列的方式写回现有解释文件，保持原始两行表头格式。同时生成综合可视化图表。
"""

import os
import re
import platform
from io import BytesIO
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import logging

from langgraph.config import get_stream_writer
from app.tools.registry import register_tool
from app.core.file_manager import file_manager

logger = logging.getLogger(__name__)


def setup_chinese_font() -> None:
    try:
        if platform.system() == 'Windows':
            plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
        elif platform.system() == 'Darwin':
            plt.rcParams['font.sans-serif'] = ['Hei', 'Arial Unicode MS']
        else:
            plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'SimHei']
        plt.rcParams['axes.unicode_minus'] = False
    except Exception as e:
        logger.warning(f"设置中文字体失败: {e}")


def is_interpreted_file(filename: str) -> bool:
    return "interpreted" in filename.lower() or "解释" in filename


def remove_file_id_prefix(filename: str) -> str:
    pattern = r'^[a-z]-[a-z0-9]+_'
    return re.sub(pattern, '', filename)


def _map_tg_layer(layer: str) -> str:
    if not isinstance(layer, str):
        return "无效数据"
    layer = layer.strip()
    mapping = {
        "水层": "水层",
        "弱显示层": "弱显示层",
        "油层": "油层",
        "气层": "气层",
        "强气层": "强气层",
        "无效数据": "无效数据",
    }
    return mapping.get(layer, layer)


def _map_tri_nature(nature: str) -> Dict[str, float]:
    """将三角图版法的含油气性质映射为类别得分分配。返回类别->权重的字典。"""
    if not isinstance(nature, str):
        return {}
    nature = nature.strip()
    if nature == "水或气层":
        return {"水层": 0.5, "气层": 0.5}
    if nature == "油气层或含油水层":
        return {"油层": 0.5, "气层": 0.3, "水层": 0.2}
    if "油层" in nature:
        return {"油层": 1.0}
    if "转化带" in nature:
        return {"过渡层": 1.0}
    return {}


def _map_3h_result(res: str) -> str:
    if not isinstance(res, str):
        return "无效数据"
    res = res.strip()
    if res in ["干层", "疑似干层"]:
        return "干层"
    if res in ["干气层", "湿气层", "凝析气层"]:
        return "气层"
    if res in ["油层", "轻质油层"]:
        return "油层"
    if res == "过渡层":
        return "过渡层"
    return "无效数据"


def _tg_conf_to_num(conf: str) -> float:
    if not isinstance(conf, str):
        return 0.6
    conf = conf.strip()
    if conf == "高":
        return 0.9
    if conf == "中":
        return 0.75
    if conf == "低":
        return 0.6
    return 0.6


def _decide_row(tg_layer: str, tg_conf_str: str, tri_nature: str, res_3h: str, res_3h_conf: float,
                weights: Tuple[float, float, float] = (0.5, 0.2, 0.3)) -> Tuple[str, float, str]:
    wt_tg, wt_tri, wt_3h = weights
    scores: Dict[str, float] = {k: 0.0 for k in ["水层", "弱显示层", "油层", "气层", "强气层", "干层", "过渡层", "无效数据"]}

    # TG 投票
    tg_cat = _map_tg_layer(tg_layer)
    tg_conf = _tg_conf_to_num(tg_conf_str)
    if tg_cat in scores:
        scores[tg_cat] += wt_tg * tg_conf

    # 三角图投票（分配）
    tri_dist = _map_tri_nature(tri_nature)
    if tri_dist:
        for cat, frac in tri_dist.items():
            if cat in scores:
                scores[cat] += wt_tri * 0.6 * frac  # 三角图基线置信度0.6

    # 3H 投票
    h3_cat = _map_3h_result(res_3h)
    h3_conf = float(res_3h_conf) / 100.0 if pd.notna(res_3h_conf) else 0.7
    if h3_cat in scores:
        scores[h3_cat] += wt_3h * max(0.5, min(1.0, h3_conf))

    # 决策
    # 合并同类：将“无效数据”仅在其他全为0时生效
    best_cat = max((k for k in scores if k != "无效数据"), key=lambda k: scores[k])
    best_score = scores[best_cat]
    total_w = wt_tg + wt_tri + wt_3h
    base_conf = (best_score / total_w) if total_w > 0 else 0

    # 冲突惩罚：次优接近则降低置信度
    sorted_scores = sorted([(k, v) for k, v in scores.items() if k != "无效数据"], key=lambda x: x[1], reverse=True)
    if len(sorted_scores) > 1:
        gap = sorted_scores[0][1] - sorted_scores[1][1]
        if gap < 0.05:
            base_conf *= 0.85
        elif gap < 0.10:
            base_conf *= 0.9

    final_conf_pct = float(np.clip(round(base_conf * 100, 1), 0, 100))

    # 决策依据摘要
    reason_parts = []
    if isinstance(tg_layer, str) and tg_layer:
        reason_parts.append(f"TG={tg_layer}({tg_conf_str or '中'})")
    if isinstance(tri_nature, str) and tri_nature:
        reason_parts.append(f"三角图={tri_nature}")
    if isinstance(res_3h, str) and res_3h:
        reason_parts.append(f"3H={res_3h}({int(round(h3_conf*100))}%)")
    reason = "; ".join(reason_parts)

    return best_cat, final_conf_pct, reason


def _create_visualization(df: pd.DataFrame, output_path: str) -> str:
    try:
        setup_chinese_font()
        plt.clf(); plt.close('all')

        plt.rcParams['figure.facecolor'] = 'white'
        plt.rcParams['axes.facecolor'] = 'white'
        plt.rcParams['text.color'] = 'black'
        plt.rcParams['axes.labelcolor'] = 'black'
        plt.rcParams['xtick.color'] = 'black'
        plt.rcParams['ytick.color'] = 'black'

        fig = plt.figure(figsize=(16, 10), facecolor='white')
        fig.suptitle('综合解释结果', fontsize=16, fontweight='bold', color='black')

        # 图1：综合层型深度剖面
        ax1 = plt.subplot(2, 2, 1)
        ax1.set_facecolor('white')
        depths = pd.to_numeric(df['Depth'], errors='coerce')
        final_layers = df['综合层型']
        color_map = {"水层": '#87CEEB', "弱显示层": '#FFE4B5', "油层": '#90EE90', "气层": '#FFA07A',
                     "强气层": '#FF6347', "干层": '#D3D3D3', "过渡层": '#DDA0DD', "无效数据": '#696969'}
        try:
            for cat, color in color_map.items():
                m = (final_layers == cat) & pd.notna(depths)
                if m.any():
                    ax1.scatter(np.full(m.sum(), 1), depths[m], s=8, c=color, label=cat, alpha=0.8, edgecolors='black', linewidths=0.2)
            ax1.invert_yaxis()
            ax1.set_xlim(0.5, 1.5)
            ax1.set_xticks([])
            ax1.set_ylabel('深度 (m)', fontsize=12)
            ax1.set_title('综合层型深度剖面', fontsize=14, fontweight='bold')
            ax1.grid(True, alpha=0.2)
            ax1.legend(fontsize=8, loc='center left', bbox_to_anchor=(1.02, 0.5))
        except Exception as e:
            logger.error(f"绘制图1失败: {e}")
            ax1.text(0.5, 0.5, f'图1失败: {str(e)}', transform=ax1.transAxes, ha='center', va='center', fontsize=12, color='red')

        # 图2：综合层型分布饼图
        ax2 = plt.subplot(2, 2, 2)
        ax2.set_facecolor('white')
        try:
            dist = final_layers.value_counts()
            if len(dist) > 0:
                pie_colors = [color_map.get(k, '#CCCCCC') for k in dist.index]
                total = dist.sum()
                def autopct(p):
                    return f'{p:.1f}%' if p >= 1 else ''
                wedges, texts, autotexts = ax2.pie(dist.values, labels=[k if (v/total*100) >= 2 else '' for k, v in dist.items()],
                                                   autopct=autopct, colors=pie_colors, startangle=45,
                                                   labeldistance=1.15, pctdistance=0.85,
                                                   wedgeprops=dict(edgecolor='white', linewidth=1))
                for t in texts: t.set_color('black'); t.set_fontsize(9)
                for at in autotexts: at.set_color('black'); at.set_fontsize(8); at.set_weight('bold')
                ax2.set_title('综合层型分布', fontsize=14, fontweight='bold', color='black')
            else:
                ax2.text(0.5, 0.5, '无数据', transform=ax2.transAxes, ha='center', va='center', fontsize=14, color='red')
        except Exception as e:
            logger.error(f"绘制图2失败: {e}")
            ax2.text(0.5, 0.5, f'图2失败: {str(e)}', transform=ax2.transAxes, ha='center', va='center', fontsize=12, color='red')

        # 图3：方法一致性统计（与综合结果一致的比例）
        ax3 = plt.subplot(2, 1, 2)
        ax3.set_facecolor('white')
        try:
            final_cat = df['综合层型']
            # TG一致：使用连续性校正后层型
            tg_cat = df.get('连续性校正后层型', df.get('层型'))
            tri_nature = df.get('含油气性质')
            h3_res = df.get('3H解释结果')

            def tri_to_simple(s):
                d = _map_tri_nature(s or '')
                if not d:
                    return None
                # 取权重最大者
                return max(d.items(), key=lambda x: x[1])[0]

            agree_tg = (tg_cat == final_cat).mean() if tg_cat is not None else 0.0
            tri_simple = tri_nature.apply(tri_to_simple) if tri_nature is not None else None
            agree_tri = (tri_simple == final_cat).mean() if tri_simple is not None else 0.0
            agree_h3 = (_map_series(h3_res, _map_3h_result) == final_cat).mean() if h3_res is not None else 0.0

            methods = ['TG', '三角图', '3H']
            rates = [agree_tg*100, agree_tri*100, agree_h3*100]
            bars = ax3.bar(methods, rates, color=['#1f77b4','#ff7f0e','#2ca02c'], edgecolor='black')
            for b, r in zip(bars, rates):
                ax3.text(b.get_x()+b.get_width()/2, b.get_height()+1, f"{r:.1f}%", ha='center', va='bottom', fontsize=10, color='black')
            ax3.set_ylim(0, 100)
            ax3.set_ylabel('一致率 (%)', fontsize=12)
            ax3.set_title('方法与综合结果一致率', fontsize=14, fontweight='bold', color='black')
            ax3.grid(axis='y', alpha=0.3)
        except Exception as e:
            logger.error(f"绘制图3失败: {e}")
            ax3.text(0.5, 0.5, f'图3失败: {str(e)}', transform=ax3.transAxes, ha='center', va='center', fontsize=12, color='red')

        plt.tight_layout(rect=[0, 0.02, 1, 0.95])
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none', format='png', transparent=False)
        plt.close('all')
        return output_path
    except Exception as e:
        logger.error(f"创建可视化图表失败: {e}")
        plt.close('all')
        return ""


def _map_series(series: pd.Series, fn) -> pd.Series:
    return series.apply(lambda x: fn(x) if pd.notna(x) else x)


@register_tool(category="gas_logging")
def comprehensive_layer_decision(file_id: str) -> str:
    """气测录井综合分析判定工具

    融合全烃TG、三角图版法、3H比值法的解释结果，生成每行样品的综合层型与综合置信度，
    并在原有（或已解释）文件基础上追加列保存。返回简要结果并推送图片与文件。

    使用说明：
    - 输入应为前序工具生成的解释文件ID（NEXT_FILE_ID）。
    - 本工具会在文件尾部追加列：Final_layer/综合层型、Final_confidence/综合置信度、Final_reason/综合判据。
    - 结果图片将以“综合解释结果_文件名.png”形式生成并推送。
    """
    writer = get_stream_writer()
    try:
        if writer:
            writer({"custom_step": "开始综合分析判定..."})

        file_info = file_manager.get_file_info(file_id)
        if not file_info:
            return f"找不到ID为 {file_id} 的文件"

        file_path = file_info.get("file_path")
        file_name = file_info.get("file_name", "")
        if writer:
            writer({"custom_step": f"正在处理文件: {file_name}"})

        # 读取表头判断跳行
        header_df = pd.read_excel(file_path, nrows=2)
        first_row = header_df.iloc[0].tolist()
        second_row = header_df.iloc[1].tolist() if len(header_df) > 1 else []

        chinese_headers = ['井名', '井深', '钻时', '全量', '甲烷', '乙烷', '丙烷', '异丁烷', '正丁烷', '异戊烷', '正戊烷', '二氧化碳', '其它非烃']
        is_chinese_header = any(str(c) in chinese_headers for c in first_row if not pd.isna(c))
        second_is_data = len(second_row) > 0 and sum(1 for cell in second_row if isinstance(cell, (int, float)) and not pd.isna(cell)) > len(second_row)/2
        skip_rows = 1 if (is_chinese_header and second_is_data) else 2

        data_df = pd.read_excel(file_path, skiprows=skip_rows)

        # 列名映射
        chinese_to_english = {
            '井名': 'Well', '井深': 'Depth', '钻时': 'Rop', '全量': 'Tg',
            '甲烷': 'C1', '乙烷': 'C2', '丙烷': 'C3', '异丁烷': 'iC4', '正丁烷': 'nC4',
            '异戊烷': 'iC5', '正戊烷': 'nC5', '二氧化碳': 'CO2', '其它非烃': 'Other'
        }
        is_chinese_header_for_columns = any(str(cell) in chinese_to_english for cell in first_row if not pd.isna(cell))

        if is_chinese_header_for_columns:
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
                        english_headers.append(cell_str)
                        chinese_headers_list.append(cell_str)
            if len(english_headers) >= len(data_df.columns):
                data_df.columns = english_headers[:len(data_df.columns)]
            else:
                data_df.columns = english_headers + [f"Col{i}" for i in range(len(english_headers), len(data_df.columns))]
            original_english_headers = list(data_df.columns)
            original_chinese_headers = chinese_headers_list[:len(data_df.columns)]
        else:
            original_english_headers = list(data_df.columns)
            # 尝试从第二行作为中文标题
            original_chinese_headers = second_row[:len(data_df.columns)] if second_row else [""]*len(data_df.columns)

        # 计算综合判定
        tg_layer_series = data_df.get('连续性校正后层型', data_df.get('层型'))
        tg_conf_series = data_df.get('可信度')  # TG工具中的可信度（高/中/低）
        tri_nature_series = data_df.get('含油气性质')
        h3_res_series = data_df.get('3H解释结果')
        h3_conf_series = data_df.get('置信度')  # 3H中的数值置信度

        # 缺列兼容
        if tg_layer_series is None: tg_layer_series = pd.Series([np.nan]*len(data_df))
        if tg_conf_series is None: tg_conf_series = pd.Series([np.nan]*len(data_df))
        if tri_nature_series is None: tri_nature_series = pd.Series([np.nan]*len(data_df))
        if h3_res_series is None: h3_res_series = pd.Series([np.nan]*len(data_df))
        if h3_conf_series is None: h3_conf_series = pd.Series([70]*len(data_df))

        finals = []
        confs = []
        reasons = []
        for i in range(len(data_df)):
            final_cat, final_conf, reason = _decide_row(
                tg_layer=str(tg_layer_series.iloc[i]) if pd.notna(tg_layer_series.iloc[i]) else '',
                tg_conf_str=str(tg_conf_series.iloc[i]) if pd.notna(tg_conf_series.iloc[i]) else '中',
                tri_nature=str(tri_nature_series.iloc[i]) if pd.notna(tri_nature_series.iloc[i]) else '',
                res_3h=str(h3_res_series.iloc[i]) if pd.notna(h3_res_series.iloc[i]) else '',
                res_3h_conf=float(h3_conf_series.iloc[i]) if pd.notna(h3_conf_series.iloc[i]) else 70.0,
            )
            finals.append(final_cat)
            confs.append(final_conf)
            reasons.append(reason)

        data_df['综合层型'] = finals
        data_df['综合置信度'] = confs
        data_df['综合判据'] = reasons

        # 重建两行表头
        original_data_columns = len(original_english_headers)
        clean_en = original_english_headers[:original_data_columns]
        clean_zh = original_chinese_headers[:original_data_columns]
        while len(clean_en) < original_data_columns: clean_en.append(f"Col{len(clean_en)+1}")
        while len(clean_zh) < original_data_columns: clean_zh.append(f"列{len(clean_zh)+1}")

        new_en = ['Final_layer', 'Final_confidence', 'Final_reason']
        new_zh = ['综合层型', '综合置信度', '综合判据']

        full_en = clean_en + new_en
        full_zh = clean_zh + new_zh

        row1 = [full_en[i] if i < len(full_en) else '' for i in range(len(data_df.columns))]
        row2 = [full_zh[i] if i < len(full_zh) else '' for i in range(len(data_df.columns))]

        all_data = [row1, row2]
        for _, r in data_df.iterrows():
            all_data.append([str(v) if not pd.isna(v) else '' for v in r])
        final_df = pd.DataFrame(all_data)

        # 保存Excel
        if is_interpreted_file(file_name):
            output_excel_path = file_path
            with pd.ExcelWriter(output_excel_path, engine='openpyxl') as excel_writer:
                final_df.to_excel(excel_writer, sheet_name='Sheet1', index=False, header=False)
            new_file_id = file_id
        else:
            base_name = remove_file_id_prefix(file_name)
            if base_name.endswith('.xls'):
                base_name = base_name[:-4] + '.xlsx'
            elif base_name.endswith('.xlsx'):
                base_name = base_name[:-5] + '.xlsx'
            if not base_name.endswith('_interpreted.xlsx'):
                new_filename = base_name[:-5] + '_interpreted.xlsx' if base_name.endswith('.xlsx') else base_name + '_interpreted.xlsx'
            else:
                new_filename = base_name
            excel_buffer = BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as excel_writer:
                final_df.to_excel(excel_writer, sheet_name='Sheet1', index=False, header=False)
            excel_data = excel_buffer.getvalue()
            new_file_id = file_manager.save_file(
                file_data=excel_data,
                file_name=new_filename,
                file_type="xlsx",
                source="generated",
            )
            new_file_info = file_manager.get_file_info(new_file_id)
            output_excel_path = new_file_info.get("file_path")

        if writer:
            writer({"custom_step": f"综合结果已写入: {Path(output_excel_path).name}"})

        # 生成可视化
        base_name = remove_file_id_prefix(Path(file_name).name)
        base_stem = Path(base_name).stem
        image_filename = f"综合解释结果_{base_stem}.png"
        temp_image_path = os.path.join(file_manager.temp_path, f"temp_{image_filename}")
        chart_path = _create_visualization(data_df, temp_image_path)

        final_image_path = None
        if chart_path and os.path.exists(chart_path):
            with open(chart_path, 'rb') as f:
                image_data = f.read()
            image_file_id = file_manager.save_file(
                file_data=image_data,
                file_name=image_filename,
                file_type="png",
                source="generated",
            )
            image_info = file_manager.get_file_info(image_file_id)
            final_image_path = image_info.get("file_path")
            try:
                os.remove(temp_image_path)
            except Exception:
                pass

        # 推送图片与文件
        if writer and final_image_path and os.path.exists(final_image_path):
            writer({"image_message": {"image_path": final_image_path, "title": "综合解释结果图表"}})

        if writer:
            writer({"file_message": {"file_path": output_excel_path, "file_name": Path(output_excel_path).name, "file_type": "xlsx"}})

        # 结果摘要
        total = len(data_df)
        dist = data_df['综合层型'].value_counts()
        main_cat = dist.index[0] if len(dist) else '无'
        main_pct = (dist.iloc[0] / total * 100) if len(dist) else 0

        result_message = f"""✅ 综合分析判定完成
🆔 **NEXT_FILE_ID: {new_file_id}** (后续工具请使用此file_id)
📏 样品数: {total}
🎯 主导层型: {main_cat}({main_pct:.1f}%)
📁 结果文件: {Path(output_excel_path).name}
📈 图表: {image_filename}

⚠️ 重要: 后续工具必须使用file_id: {new_file_id} 以在此结果基础上继续分析"""

        if writer:
            writer({"custom_step": result_message})

        return result_message

    except Exception as e:
        logger.error("综合分析判定失败", exc_info=True)
        if writer:
            writer({"custom_step": f"❌ 综合分析判定失败: {str(e)}"})
        return f"综合分析判定失败: {str(e)}"


