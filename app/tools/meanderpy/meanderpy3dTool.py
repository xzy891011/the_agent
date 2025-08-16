import traceback
from typing import Dict, Any, Optional
import matplotlib.pyplot as plt
import numpy as np
import pickle
import trimesh
import tempfile
import os
import yaml
import app.tools.meanderpy.meanderpy as mp
from gradio import Progress
from app.tools.registry import register_tool
from app.tools.schemas import GenerateFluvial3DModelSchema
import logging
from app.core.file_manager import FileManager
from langgraph.config import get_stream_writer

logger = logging.getLogger(__name__)
file_manager_instance = FileManager.get_instance()
# 添加类型提示
ModelResult = Dict[str, Any]

@register_tool(category="meanderpy", use_structured_tool=True)
def generate_fluvial_3d_model(
    yaml_path: str,
) -> ModelResult:
    try:
        writer = get_stream_writer()
        if writer:
            writer({"custom_step": "开始生成河流模型..."})
            
        image_path = file_manager_instance.generated_path
        progress = Progress()
        
        print("开始生成河流模型...")
        progress(0.1, desc="正在初始化模型参数...")
        if writer:
            writer({"custom_step": "正在初始化模型参数..."})
        
        # 确保目录存在
        os.makedirs(os.path.dirname(yaml_path), exist_ok=True)
        os.makedirs(os.path.dirname(image_path), exist_ok=True)

        # 默认参数
        default_params = {
            'nit': 100,              # number of iterations
            'W': 100,                # channel width (m)
            'D': 10,                 # channel depth (m)
            'pad': 100,              # padding
            'deltas': 50,            # sampling distance
            'Cfs_weight': 0.1,       # Chezy friction factor weight
            'crdist_weight': 1.5,    # cutoff threshold weight
            'kl': 60.0,              # migration rate constant
            'kv': 1.0,               # vertical erosion rate constant
            'dt': 0.1,               # time step (years)
            'dens': 1000,            # water density
            'saved_ts': [0, -1],     # save first and last timestep
            'n_bends': 20,           # number of bends
            'Sl': 0.001,             # initial slope
            't1': 0,                 # incision start time
            't2': 1,                 # lateral migration start time
            't3': 50,                # aggradation start time
            'aggr_factor': 0.1,      # aggradation factor
            'h_mud': 1.0,            # mud thickness
            'dx': 10,                # grid cell size
            'diff_scale': 1.0,       # diffusion scale
            'v_coarse': 0.1,         # coarse sediment deposition rate
            'v_fine': 0.05,          # fine sediment deposition rate
        }

        # 读取或创建YAML文件
        if not os.path.exists(yaml_path):
            progress(0.15, desc="正在创建默认参数文件...")
            if writer:
                writer({"custom_step": "正在创建默认参数文件..."})
            with open(yaml_path, 'w') as file:
                yaml.dump(default_params, file, default_flow_style=False)
            params = default_params
        else:
            progress(0.15, desc="正在读取参数文件...")
            if writer:
                writer({"custom_step": "正在读取参数文件..."})
            with open(yaml_path, 'r') as file:
                params = yaml.safe_load(file) or default_params

        # 从参数中获取值
        nit = params['nit']
        W = params['W']
        D = params['D']
        depths = D * np.ones((nit,))
        pad = params['pad']
        deltas = params['deltas']
        Cfs = params['Cfs_weight'] * np.ones((nit,))
        crdist = params['crdist_weight'] * W
        kl = params['kl']
        kv = params['kv']
        dt = params['dt']
        dens = params['dens']
        saved_ts = params['saved_ts']
        n_bends = params['n_bends']
        Sl = params['Sl']
        t1 = params['t1']
        t2 = params['t2']
        t3 = params['t3']
        aggr_factor = params['aggr_factor']
        h_mud = params['h_mud']
        dx = params['dx']
        diff_scale = params['diff_scale']
        v_coarse = params['v_coarse']
        v_fine = params['v_fine']

        progress(0.2, desc="正在生成初始河道...")
        if writer:
            writer({"custom_step": "正在生成初始河道..."})
        ch = mp.generate_initial_channel(W, depths[0], Sl, deltas, pad, n_bends)
        chb = mp.ChannelBelt(channels=[ch], cutoffs=[], cl_times=[0.0], cutoff_times=[])
        
        # 修改 ChannelBelt 类的 migrate 方法来支持进度显示
        original_migrate = chb.migrate
        def migrate_with_progress(*args, **kwargs):
            # 保存原始的 trange 函数
            original_trange = mp.trange
            try:
                # 替换为自定义的进度显示函数
                def custom_trange(nit):
                    for i in range(nit):
                        progress_value = 0.2 + (0.7 - 0.2) * (i / nit)
                        progress(progress_value, desc=f"正在模拟河道迁移... {i+1}/{nit}")
                        if writer and i % 100 == 0:  # 每100次迭代推送一次消息，避免消息过多
                            writer({"custom_step": f"正在模拟河道迁移... {i+1}/{nit}"})
                        yield i
                # 替换 trange 函数
                mp.trange = custom_trange
                # 调用原始的 migrate 方法
                result = original_migrate(*args, **kwargs)
                return result
            finally:
                # 恢复原始的 trange 函数
                mp.trange = original_trange
        
        # 替换 migrate 方法
        chb.migrate = migrate_with_progress
        
        # 执行迁移模拟
        progress(0.2, desc="准备开始河道迁移模拟...")
        if writer:
            writer({"custom_step": "准备开始河道迁移模拟..."})
        nit = 2000  # 总迭代次数
        chb.migrate(nit, saved_ts, deltas, pad, crdist, depths, Cfs, kl, kv, dt, dens, t1, t2, t3, aggr_factor)

        progress(0.7, desc="正在计算模型范围...")
        if writer:
            writer({"custom_step": "正在计算模型范围..."})
        xmin = -W * 5
        xmax = W * 5
        ymin = -W * 5
        ymax = W * 5

        progress(0.75, desc="正在准备3D模型数据...")
        if writer:
            writer({"custom_step": "正在准备3D模型数据..."})
        h_mud_array = h_mud * np.ones(len(chb.channels))

        progress(0.8, desc="正在构建3D模型...")
        if writer:
            writer({"custom_step": "正在构建3D模型..."})
        chb_3d, xmin, xmax, ymin, ymax, dists, zmaps = mp.build_3d_model(
            chb, 'fluvial', 
            h_mud=h_mud_array,
            h=12.0, 
            w=W,
            bth=0.0, 
            dcr=10.0, 
            dx=dx, 
            delta_s=deltas, 
            dt=dt,
            starttime=chb.cl_times[0], 
            endtime=chb.cl_times[-1],
            diff_scale=diff_scale, 
            v_fine=v_fine, 
            v_coarse=v_coarse,
            xmin=xmin, 
            xmax=xmax, 
            ymin=ymin, 
            ymax=ymax
        )

        progress(0.9, desc="正在生成GLB文件...")
        if writer:
            writer({"custom_step": "正在生成GLB文件..."})
        # 确保输出目录存在
        os.makedirs(os.path.dirname(image_path), exist_ok=True)
        
        # 生成GLB文件路径
        glb_path = os.path.join(os.path.dirname(image_path), "fluvial_model.glb")
        
        # 创建和导出GLB文件
        vertices = []
        faces = []
        vertex_colors = []
        vertex_index = 0

        # 获取河道中心线
        centerline = chb.channels[-1]
        
        # 设置河道参数
        channel_width = W
        channel_depth = D
        resolution = 50  # 横向分辨率
        num_points = len(centerline.x)

        print("生成河道网格...")
        if writer:
            writer({"custom_step": "正在生成河道网格..."})
        # 生成河道表面
        for i in range(num_points - 1):
            # 计算当前段的方向向量
            dx = centerline.x[i+1] - centerline.x[i]
            dy = centerline.y[i+1] - centerline.y[i]
            dz = centerline.z[i+1] - centerline.z[i]
            
            # 计算单位向量
            length = np.sqrt(dx*dx + dy*dy)
            if length == 0:
                continue
                
            # 计算垂直于河道方向的向量
            perpx = -dy/length * channel_width/2
            perpy = dx/length * channel_width/2

            # 生成河道横截面
            for j in range(resolution):
                # 计算当前点和下一个点的位置
                t = j / (resolution-1)
                t_next = (j+1) / (resolution-1)
                
                # 当前横截面的点
                x1 = centerline.x[i] + perpx * (2*t - 1)
                y1 = centerline.y[i] + perpy * (2*t - 1)
                z1 = centerline.z[i]
                
                # 下一个横截面的点
                x2 = centerline.x[i+1] + perpx * (2*t - 1)
                y2 = centerline.y[i+1] + perpy * (2*t - 1)
                z2 = centerline.z[i+1]

                # 添加顶点
                vertices.extend([
                    [x1, y1, z1],
                    [x2, y2, z2]
                ])

                # 创建面（三角形）
                if j < resolution-1:
                    v_idx = vertex_index
                    faces.extend([
                        [v_idx, v_idx+1, v_idx+3],
                        [v_idx, v_idx+3, v_idx+2]
                    ])

                    # 设置颜色
                    t_norm = abs(2*t - 1)  # 归一化到0-1
                    if t_norm < 0.3:  # 河道中心
                        color = [0.2, 0.4, 0.8, 1.0]  # 深蓝色（水）
                    elif t_norm < 0.7:  # 过渡区
                        color = [0.3, 0.5, 0.7, 1.0]  # 中蓝色
                    else:  # 河岸
                        color = [0.7, 0.6, 0.5, 1.0]  # 浅褐色（沉积物）

                    vertex_colors.extend([color, color])
                    vertex_index += 2

        # 生成河床
        print("生成河床...")
        if writer:
            writer({"custom_step": "正在生成河床..."})
        # 首先生成河床底部
        for i in range(num_points - 1):
            # 计算当前段的方向向量
            dx = centerline.x[i+1] - centerline.x[i]
            dy = centerline.y[i+1] - centerline.y[i]
            length = np.sqrt(dx*dx + dy*dy)
            
            if length == 0:
                continue
                
            # 计算垂直向量，使用更宽的河床
            perpx = -dy/length * channel_width * 0.75  # 河床宽度为河道宽度的1.5倍
            perpy = dx/length * channel_width * 0.75

            # 生成河床底部
            x1 = centerline.x[i] - perpx
            y1 = centerline.y[i] - perpy
            z1 = centerline.z[i] - channel_depth

            x2 = centerline.x[i] + perpx
            y2 = centerline.y[i] + perpy
            z2 = centerline.z[i] - channel_depth

            x3 = centerline.x[i+1] - perpx
            y3 = centerline.y[i+1] - perpy
            z3 = centerline.z[i+1] - channel_depth

            x4 = centerline.x[i+1] + perpx
            y4 = centerline.y[i+1] + perpy
            z4 = centerline.z[i+1] - channel_depth

            # 添加河床顶点
            vertices.extend([
                [x1, y1, z1],
                [x2, y2, z2],
                [x3, y3, z3],
                [x4, y4, z4]
            ])

            # 创建河床面
            v_idx = vertex_index
            faces.extend([
                [v_idx, v_idx+1, v_idx+2],
                [v_idx+1, v_idx+3, v_idx+2]
            ])

            # 河床颜色（深褐色）
            bed_color = [0.4, 0.3, 0.2, 1.0]
            vertex_colors.extend([bed_color] * 4)
            vertex_index += 4

            # 生成河床侧壁
            # 左侧壁
            wall_vertices = [
                [x1, y1, z1],  # 底部前
                [x1, y1, centerline.z[i]],  # 顶部前
                [x3, y3, z3],  # 底部后
                [x3, y3, centerline.z[i+1]]  # 顶部后
            ]
            vertices.extend(wall_vertices)
            faces.extend([
                [vertex_index, vertex_index+1, vertex_index+2],
                [vertex_index+1, vertex_index+3, vertex_index+2]
            ])
            vertex_colors.extend([[0.45, 0.35, 0.25, 1.0]] * 4)  # 稍浅的褐色
            vertex_index += 4

            # 右侧壁
            wall_vertices = [
                [x2, y2, z2],  # 底部前
                [x2, y2, centerline.z[i]],  # 顶部前
                [x4, y4, z4],  # 底部后
                [x4, y4, centerline.z[i+1]]  # 顶部后
            ]
            vertices.extend(wall_vertices)
            faces.extend([
                [vertex_index, vertex_index+1, vertex_index+2],
                [vertex_index+1, vertex_index+3, vertex_index+2]
            ])
            vertex_colors.extend([[0.45, 0.35, 0.25, 1.0]] * 4)
            vertex_index += 4

        # 调整模型尺寸将所有坐标缩小更多
        scale_factor = 0.0001  # 进一步减小缩放因子

        print("创建3D模型...")
        if writer:
            writer({"custom_step": "正在创建3D模型..."})
        # 缩放所有顶点坐标
        scaled_vertices = np.array(vertices) * scale_factor
        
        # 计算模型中心点，用于调整位置
        center = np.mean(scaled_vertices, axis=0)
        # 将模型中心移到原点
        centered_vertices = scaled_vertices - center
        
        mesh = trimesh.Trimesh(
            vertices=centered_vertices,  # 使用居中后的顶点
            faces=np.array(faces),
            vertex_colors=np.array(vertex_colors),
            process=False
        )

        progress(0.95, desc="正在导出GLB文件...")
        if writer:
            writer({"custom_step": "正在导出GLB文件..."})
        mesh.export(glb_path)

        progress(1.0, desc="完成!")
        print(f"完成！文件已保存到: {glb_path}")
        
        # 推送模型完成消息和路径
        if writer:
            writer({"custom_step": "3D河流模型生成完成！"})
            # 推送模型文件路径
            writer({"image_message": {
                "image_path": glb_path,
                "title": "3D河流模型（GLB格式）"
            }})

        # 返回自然语言描述的结果
        model_filename = os.path.basename(glb_path)
        params_used = "\n".join([f"- {key}: {value}" for key, value in {
            "河道宽度": W,
            "河道深度": D, 
            "弯曲度": n_bends,
            "迭代次数": nit,
            "迁移速率": kl
        }.items()])
        
        return f"3D河流模型已成功生成。\n模型文件：{model_filename}\n模型使用以下主要参数：\n{params_used}\n您可以在3D可视化软件中查看此GLB格式文件。"

    except Exception as e:
        print(f"错误: {str(e)}")
        traceback.print_exc()
        if writer:
            writer({"custom_step": f"生成河流模型时出错: {str(e)}"})
        return f"生成3D河流模型失败。错误原因：{str(e)}"

# 为generate_fluvial_3d_model工具设置schema
generate_fluvial_3d_model.args_schema = GenerateFluvial3DModelSchema

def generate_submarine_3d_model(
    yaml_path: str = "./data/generate3DSubmarine/generate3DSubmarine_Parametrs.yaml",
    image_path: str = "./data/generate3DSubmarine/saveImg/3d_submarine_model.png"
) -> ModelResult:
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(yaml_path), exist_ok=True)
        os.makedirs(os.path.dirname(image_path), exist_ok=True)

        # 使用相同的默认参数结构，但可以调整一些值以适应海底环境
        default_params = {
            'nit': 100,
            'W': 100,
            'D': 15,                 # 海底河道通常更深
            'pad': 100,
            'deltas': 50,
            'Cfs_weight': 0.1,
            'crdist_weight': 1.5,
            'kl': 60.0,
            'kv': 1.0,
            'dt': 0.1,
            'dens': 1000,
            'saved_ts': [0, -1],
            'n_bends': 20,
            'Sl': 0.002,             # 海底坡度通常更
            't1': 0,
            't2': 1,
            't3': 50,
            'aggr_factor': 0.15,     # 海底沉积速率通常更高
            'h_mud': 1.5,            # 海底泥质层通常更厚
            'dx': 10,
            'diff_scale': 1.2,       # 海底扩散作用通常更强
            'v_coarse': 0.12,
            'v_fine': 0.06,
        }

        # 读取或创建YAML文件
        if not os.path.exists(yaml_path):
            with open(yaml_path, 'w') as file:
                yaml.dump(default_params, file, default_flow_style=False)
            params = default_params
        else:
            with open(yaml_path, 'r') as file:
                params = yaml.safe_load(file) or default_params

        # 从参数中获取值
        nit = params['nit']
        W = params['W']
        D = params['D']
        depths = D * np.ones((nit,))
        pad = params['pad']
        deltas = params['deltas']
        Cfs = params['Cfs_weight'] * np.ones((nit,))
        crdist = params['crdist_weight'] * W
        kl = params['kl']
        kv = params['kv']
        dt = params['dt']
        dens = params['dens']
        saved_ts = params['saved_ts']
        n_bends = params['n_bends']
        Sl = params['Sl']
        t1 = params['t1']
        t2 = params['t2']
        t3 = params['t3']
        aggr_factor = params['aggr_factor']
        h_mud = params['h_mud']
        dx = params['dx']
        diff_scale = params['diff_scale']
        v_coarse = params['v_coarse']
        v_fine = params['v_fine']

        # 生成海底河道模型
        ch = mp.generate_initial_channel(W, depths[0], Sl, deltas, pad, n_bends)
        chb = mp.ChannelBelt(channels=[ch], cutoffs=[], cl_times=[0.0], cutoff_times=[])
        chb.migrate(nit, saved_ts, deltas, pad, crdist, depths, Cfs, kl, kv, dt, dens, t1, t2, t3, aggr_factor)

        # 计算模型范围
        xmin = -W * 5
        xmax = W * 5
        ymin = -W * 5
        ymax = W * 5

        # 创建h_mud数组，长度与channels相同
        h_mud_array = h_mud * np.ones(len(chb.channels))

        # 生成3D模型数据
        chb_3d, xmin, xmax, ymin, ymax, dists, zmaps = mp.build_3d_model(
            chb, 'submarine', 
            h_mud=h_mud_array,  # 使用数组而不是单个值
            h=15.0,      
            w=W,
            bth=4.0,     
            dcr=6.0,     
            dx=dx, 
            delta_s=deltas, 
            dt=dt,
            starttime=chb.cl_times[0],
            endtime=chb.cl_times[-1],
            diff_scale=diff_scale * 1.2,
            v_fine=v_fine * 1.2,
            v_coarse=v_coarse * 1.2,
            xmin=xmin, 
            xmax=xmax, 
            ymin=ymin, 
            ymax=ymax
        )

        # 生成3D模型数据后，直接创建简单的网格
        # 准备3D可视化数据
        vertices = []
        faces = []
        vertex_colors = []
        vertex_index = 0

        # 简化的网格生成
        nx, ny = 50, 50  # 使用固定的网格大小
        dx = (xmax - xmin) / nx
        dy = (ymax - ymin) / ny

        # 获取地层值范围
        strat_min = np.min(chb_3d.strat)
        strat_max = np.max(chb_3d.strat)

        # 生成网格
        for j in range(ny):
            for i in range(nx):
                x = xmin + i * dx
                y = ymin + j * dy
                
                # 获取当前位置的地层值
                index = i + j * nx
                if index >= len(chb_3d.strat):
                    continue

                try:
                    strat_value = float(np.nanmean(chb_3d.strat[index]))
                    facies = int(chb_3d.facies[index])
                except (IndexError, ValueError):
                    continue

                if np.isnan(strat_value):
                    continue

                # 创建一个简单的方块
                z = strat_value
                size = min(dx, dy) * 0.9  # 略小于网格间距
                height = size * 0.5

                # 顶点坐标
                cube_vertices = [
                    [x - size/2, y - size/2, z],
                    [x + size/2, y - size/2, z],
                    [x + size/2, y + size/2, z],
                    [x - size/2, y + size/2, z],
                    [x - size/2, y - size/2, z + height],
                    [x + size/2, y - size/2, z + height],
                    [x + size/2, y + size/2, z + height],
                    [x - size/2, y + size/2, z + height]
                ]

                # 面的定义
                cube_faces = [
                    [vertex_index, vertex_index+1, vertex_index+2],
                    [vertex_index, vertex_index+2, vertex_index+3],
                    [vertex_index+4, vertex_index+5, vertex_index+6],
                    [vertex_index+4, vertex_index+6, vertex_index+7],
                    [vertex_index, vertex_index+1, vertex_index+5],
                    [vertex_index, vertex_index+5, vertex_index+4],
                    [vertex_index+1, vertex_index+2, vertex_index+6],
                    [vertex_index+1, vertex_index+6, vertex_index+5],
                    [vertex_index+2, vertex_index+3, vertex_index+7],
                    [vertex_index+2, vertex_index+7, vertex_index+6],
                    [vertex_index+3, vertex_index, vertex_index+4],
                    [vertex_index+3, vertex_index+4, vertex_index+7]
                ]

                # 根据相值设置颜色
                colors = {
                    0: [0.2, 0.5, 0.8, 1.0],  # 深蓝色（海底砂）
                    1: [0.3, 0.6, 0.7, 1.0],  # 蓝色（海底泥）
                    2: [0.1, 0.3, 0.6, 1.0],  # 深海蓝
                    3: [0.4, 0.4, 0.7, 1.0],  # 紫蓝色（深水沉积）
                    4: [0.2, 0.4, 0.5, 1.0],  # 灰蓝色（浊流沉积）
                }
                color = colors.get(facies, [0.2, 0.4, 0.5, 1.0])

                # 添加到列表
                vertices.extend(cube_vertices)
                faces.extend(cube_faces)
                vertex_colors.extend([color] * 8)
                vertex_index += 8

        # 调整模型尺寸，将所有坐标缩小更多
        scale_factor = 0.001  # 进一步减小缩放因子

        print("创建3D模型...")
        # 缩放所有顶点坐标
        scaled_vertices = np.array(vertices) * scale_factor
        
        # 计算模型中心点，用于调整位置
        center = np.mean(scaled_vertices, axis=0)
        # 将模型中心移到原点
        centered_vertices = scaled_vertices - center
        
        mesh = trimesh.Trimesh(
            vertices=centered_vertices,  # 使用居中后的顶点
            faces=np.array(faces),
            vertex_colors=np.array(vertex_colors),
            process=False
        )

        # 导出为GLB文件
        glb_path = os.path.join(os.path.dirname(image_path), "submarine_model.glb")
        mesh.export(glb_path, file_type='glb')

        print(f"Debug: Exported GLB file to {glb_path}")
        print(f"Debug: File size: {os.path.getsize(glb_path)} bytes")

        return {
            "type": "3d_visualization",
            "content": glb_path,
            "message": "状态成功\n备注：3D海底河道模型已生成（GLB格式）"
        }

    except Exception as e:
        import traceback
        print("Error occurred:")
        print(traceback.format_exc())
        raise Exception(f"Error in generate_submarine_3d_model: {str(e)}")

# 确保这些函数可以被导入
__all__ = ['generate_fluvial_3d_model', 'generate_submarine_3d_model']
