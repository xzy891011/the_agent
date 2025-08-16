import logging
from gradio import Progress
import numpy as np
from swputest import SeisNet, DownSampling, UpConvAndCrop, DoubleSameConv,predict,analysis
import torch
import os

import trimesh
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
from app.core.file_manager import file_manager
from app.tools.registry import register_tool
# from app.core.task_decorator import task  # 不再需要，已迁移到MCP
from langgraph.config import get_stream_writer
import traceback

logger = logging.getLogger(__name__)

# 获取当前文件所在目录的绝对路径
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# 项目根目录（可能需要根据实际项目结构调整）
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", ".."))

@register_tool(category="reservior", use_structured_tool=True)
def reservior(file_id: str):
    '''油藏孔隙度模型预测
    Args:
        file_id: 文件ID
    Returns:
        油藏孔隙度模型预测结果
    '''

    writer = get_stream_writer()
    file_info = file_manager.get_file_info(file_id)
    if not file_info:
        return f"找不到ID为 {file_id} 的文件。"
    file_path = file_info.get("file_path")
    file_type = file_info.get("file_type", "").lower()
    file_name = file_info.get("file_name", "")
    
    try:
        # 使用第2块GPU
        device = 'cuda:2' if torch.cuda.is_available() else 'cpu'
        logger.info(device)
        input_path=file_path
        output_path=file_manager.generated_path
        
        # 使用os.path.join构建路径，确保跨平台兼容性
        pklpath = os.path.join(CURRENT_DIR, "test2.pkl")
        outpath = os.path.join(output_path, "reservior", "poro.DAT")
        
        # 确保输出目录存在
        os.makedirs(os.path.dirname(outpath), exist_ok=True)
        
        parm1 = {'inpath': input_path,
                'outpath': outpath,
                'pklpath': pklpath,
                'device': device,
                'dimens': "(241, 246, 35)"}
        predict(parm1)
        logger.info(f"油藏模型物性预测完成,孔隙度模型已保存到{outpath}")
        writer({"custom_step": f"油藏模型物性预测完成,孔隙度模型已保存到{outpath}"})
    except Exception as e:
        logger.error(f"油藏模型物性预测失败: {str(e)}")
        writer({"custom_step": f"油藏模型物性预测失败: {str(e)}\n{traceback.format_exc()}"})
        return f"油藏模型物性预测失败: {str(e)}"

    
    try:
        
        # 确保输出路径以.glb结尾
        glb_output_path = os.path.join(output_path, 'reservoir_model.glb')
        
        writer({"custom_step": "正在准备数据..."})
            
        try:
            writer({"custom_step": "正在读取网格文件..."})
            # 检查文件路径是否存在
            coord_file = os.path.join(CURRENT_DIR, "data_COORD.GRDECL")
            zcorn_file = os.path.join(CURRENT_DIR, "data_ZCORN.GRDECL")
            poro_file = os.path.join(output_path, "reservior", "poro.DAT")
            actnum_file = os.path.join(CURRENT_DIR, "data_ACTNUM.GRDECL")
            
            # 检查文件是否存在
            for file_path in [coord_file, zcorn_file, actnum_file]:
                if not os.path.exists(file_path):
                    error_msg = f"文件不存在: {file_path}"
                    logger.error(error_msg)
                    writer({"custom_step": error_msg})
                    return error_msg
            
            writer({"custom_step": "正在读取ACTNUM数据..."})
            # 读取ACTNUM数据，处理压缩格式
            actnum_data = []
            reading_data = False
            with open(actnum_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('ACTNUM'):
                        reading_data = True
                        continue
                    if reading_data:
                        if line.startswith('/'):
                            break
                        if line and not line.startswith('--'):
                            parts = line.split()
                            for part in parts:
                                try:
                                    if '*' in part:
                                        count, value = part.split('*')
                                        actnum_data.extend([int(value)] * int(count))
                                    elif part != '/':  # 跳过结束符号
                                        actnum_data.append(int(part))
                                except ValueError:
                                    continue  # 跳过无法转换的值
            actnum = np.array(actnum_data)
            
            writer({"custom_step": "正在读取COORD数据..."})
            # 读取COORD数据，跳过关键字行
            coord_data = []
            reading_data = False
            with open(coord_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('COORD'):
                        reading_data = True
                        continue
                    if reading_data and line and not line.startswith('--') and not line.startswith('/'):
                        try:
                            coord_data.extend([float(x) for x in line.split()])
                        except ValueError:
                            continue
            coord = np.array(coord_data)
            
            writer({"custom_step": "正在读取ZCORN数据..."})
            # 读取ZCORN数据，跳过关键字行
            zcorn_data = []
            reading_data = False
            with open(zcorn_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('ZCORN'):
                        reading_data = True
                        continue
                    if reading_data and line and not line.startswith('--') and not line.startswith('/'):
                        try:
                            zcorn_data.extend([float(x) for x in line.split()])
                        except ValueError:
                            continue
            zcorn = np.array(zcorn_data)
            
            writer({"custom_step": "正在读取孔隙度数据..."})
            try:
                # 首先尝试普通读取
                try:
                    writer({"custom_step": "尝试直接读取孔隙度数据..."})
                    poro = np.loadtxt(poro_file)
                except:
                    writer({"custom_step": "直接读取失败，正在尝试逐行读取..."})
                    with open(poro_file, 'r') as f:
                        lines = [line.strip() for line in f if line.strip() and not line.startswith('--')]
                        total_lines = len(lines)
                        poro_data = []
                        
                        for i, line in enumerate(lines):
                            try:
                                poro_data.extend([float(x) for x in line.split()])
                            except ValueError:
                                continue
                        
                        writer({"custom_step": "正在转换数据格式..."})
                        poro = np.array(poro_data)
                    
                    writer({"custom_step": "正在验证数据完整性..."})
                    if len(poro) == 0:
                        raise ValueError("孔隙度数据为空")
                
                writer({"custom_step": "正在计算网格尺寸..."})
                # 使用实际的网格尺寸
                nx, ny, nz = 241, 246, 35
                
                # 检查数组大小是否匹配
                expected_size = nx * ny * nz
                logger.info(f"期望的数组大小: {expected_size}, actnum大小: {len(actnum)}, poro大小: {len(poro)}")
                
                # 如果数组大小不匹配，调整到相同大小
                if len(actnum) != len(poro):
                    writer({"custom_step": f"警告: 数组大小不匹配，actnum长度={len(actnum)}，poro长度={len(poro)}，正在尝试调整..."})
                    logger.warning(f"数组大小不匹配: actnum长度={len(actnum)}，poro长度={len(poro)}")
                    
                    # 截断到较小的尺寸
                    min_size = min(len(actnum), len(poro))
                    actnum = actnum[:min_size]
                    poro = poro[:min_size]
                    
                    logger.info(f"调整后: actnum长度={len(actnum)}，poro长度={len(poro)}")
                    writer({"custom_step": f"数组已调整为相同长度: {min_size}"})
                
                writer({"custom_step": "正在计算坐标范围..."})
                # 计算坐标范围
                x_coords = coord[0::6]
                y_coords = coord[1::6]
                z_coords = coord[2::6]
                
                writer({"custom_step": "正在计算网格单元大小..."})
                # 计算网格单元的大小
                dx = (max(x_coords) - min(x_coords)) / nx
                dy = (max(y_coords) - min(y_coords)) / ny
                dz = (max(zcorn) - min(zcorn)) / nz
                
                writer({"custom_step": "正在获取网格原点..."})
                # 获取网格原点
                x0, y0, z0 = min(x_coords), min(y_coords), min(zcorn)
                
                writer({"custom_step": "正在设置采样参数..."})
                # 创建降采样的网格
                sample_rate = 8
                nx_sample = nx // sample_rate
                ny_sample = ny // sample_rate
                nz_sample = max(nz // 2, 1)
                
                writer({"custom_step": "正在初始化网格数据结构..."})
                vertices = []
                faces = []
                vertex_colors = []
                vertex_index = 0
                
                writer({"custom_step": "开始成网格..."})
                
                # 计算总的网格单元数量用于进度显示
                total_cells = nz_sample * ny_sample * nx_sample
                cells_processed = 0
                
                # 为每个采样的活动单元创建一个立方体
                for k in range(nz_sample):
                    k_actual = k * 2  # 实际的k索引
                    for j in range(ny_sample):
                        j_actual = j * sample_rate  # 实际的j索引
                        for i in range(nx_sample):
                            i_actual = i * sample_rate  # 实际的i索引
                            
                            # 更新进度，从0.6到0.8的范围
                            cells_processed += 1
                            
                            idx = i_actual + j_actual * nx + k_actual * nx * ny
                            if idx < len(actnum) and actnum[idx] == 1:  # 只处理活动单元
                                # 计算实际的空间坐标
                                x = x0 + i_actual * dx
                                y = y0 + j_actual * dy
                                z = z0 + k_actual * dz
                                
                                # 立方体的8个顶点，使用实际坐标
                                cube_vertices = [
                                    [x, y, z],
                                    [x + dx * sample_rate, y, z],
                                    [x + dx * sample_rate, y + dy * sample_rate, z],
                                    [x, y + dy * sample_rate, z],
                                    [x, y, z + dz * 2],  # 垂向使用2倍采样率
                                    [x + dx * sample_rate, y, z + dz * 2],
                                    [x + dx * sample_rate, y + dy * sample_rate, z + dz * 2],
                                    [x, y + dy * sample_rate, z + dz * 2]
                                ]
                                
                                # 立方体的12个三角形（6个面）
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
                                
                                # 获取该单元的孔隙度值并创建颜色
                                if idx < len(poro):
                                    porosity = poro[idx]
                                    # 使用更好的颜色映射
                                    import matplotlib.pyplot as plt
                                    cmap = plt.cm.jet  # 使用jet颜色映射
                                    normalized_poro = (porosity - np.min(poro)) / (np.max(poro) - np.min(poro))
                                    color = list(cmap(normalized_poro))  # 转换为RGBA颜色
                                    vertex_colors.extend([color] * 8)  # 每个顶点使用相同的颜色
                                
                                vertices.extend(cube_vertices)
                                faces.extend(cube_faces)
                                vertex_index += 8
                
                writer({"custom_step": "正在计算模型缩放比例..."})
                
                # 计算模型的边界框
                vertices_array = np.array(vertices)
                bbox_min = np.min(vertices_array, axis=0)
                bbox_max = np.max(vertices_array, axis=0)
                bbox_size = bbox_max - bbox_min
                
                # 计算合适的缩放比例，使模型适合视野
                target_size = 2.0  # 期望的模型大小
                scale_factor = target_size / max(bbox_size)
                
                # 计算模型中心点
                center = (bbox_max + bbox_min) / 2
                
                # 对顶点进行缩放和居中
                vertices_array = (vertices_array - center) * scale_factor
                
                writer({"custom_step": "正在创建3D模型..."})
                # 创建trimesh对象
                mesh = trimesh.Trimesh(
                    vertices=vertices_array,  # 使用缩放后的顶点
                    faces=np.array(faces),
                    vertex_colors=np.array(vertex_colors),
                    process=False
                )
                
                # 创建场景设置相机
                scene = trimesh.Scene()
                scene.add_geometry(mesh)
                
                # 设置相机视角
                # 计算相机位置
                camera_distance = max(bbox_size) * 2.0  # 相机距离是模型尺寸的2倍
                camera_position = np.array([1.0, 1.0, 1.0])
                camera_position = camera_position / np.linalg.norm(camera_position) * camera_distance
                
                # 设置相机参数
                scene.camera.fov = [45.0, 45.0]  # 水平和垂直视场角
                scene.camera.resolution = [800, 600]  # 分辨率
                scene.camera.focal = [400, 300]  # 焦点
                
                # 设置相机变换矩阵
                camera_transform = np.eye(4)
                camera_transform[:3, 3] = camera_position  # 设置相机位置
                scene.camera_transform = camera_transform
                
                writer({"custom_step": "正在导出GLB文件..."})
                # 导出为GLB格式
                scene.export(glb_output_path, file_type='glb')
                
                writer({"custom_step": "完成!"})
                
                # 推送3D模型到前端进行可视化
                if os.path.exists(glb_output_path):
                    try:
                        # 计算安全的统计信息
                        try:
                            # 确保使用正确的布尔索引
                            valid_indices = (actnum == 1)
                            if sum(valid_indices) > 0:
                                average_porosity = np.mean(poro[valid_indices])
                                min_porosity = np.min(poro[valid_indices])
                                max_porosity = np.max(poro[valid_indices])
                            else:
                                # 如果没有有效索引，使用全部数据
                                average_porosity = np.mean(poro)
                                min_porosity = np.min(poro)
                                max_porosity = np.max(poro)
                        except Exception as e:
                            logger.error(f"计算统计数据时出错: {str(e)}")
                            # 使用全部数据
                            average_porosity = np.mean(poro)
                            min_porosity = np.min(poro)
                            max_porosity = np.max(poro)
                        
                        # 推送3D可视化消息
                        writer({"3d_model_message": {
                            "model_path": glb_output_path,
                            "title": "油藏3D模型可视化",
                            "type": "3d_model"  # 指定类型为3D模型，前端可据此弹出3D可视化框
                        }})
                        
                        # 返回自然语言描述的结果
                        return f"油藏模型物性预测完成!\n\n孔隙度模型统计信息:\n- 平均孔隙度: {average_porosity:.4f}\n- 最小孔隙度: {min_porosity:.4f}\n- 最大孔隙度: {max_porosity:.4f}\n\n3D模型已生成并推送到前端可视化窗口，您可以在3D视图中交互查看模型。"
                    except Exception as e:
                        logger.error(f"处理3D可视化时出错: {str(e)}\n{traceback.format_exc()}")
                        return f"油藏模型生成完成，但可视化处理过程中出错: {str(e)}"
                else:
                    return f"油藏模型3D可视化失败，未能生成模型文件。"
                    
                    
            except Exception as e:
                error_msg = f"无法读取或处理数据: {str(e)}"
                logger.error(error_msg)
                logger.error(f"错误详情: {traceback.format_exc()}")
                print(error_msg)
                print(f"错误详情: {str(e)}")
                return "可视化失败：数据处理错误"
                
        except Exception as e:
            error_msg = f"可视化过程中出现错误: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            print(error_msg)
            traceback.print_exc()
            return {"type": "error", "content": f"可视化失败：{str(e)}"}
            
    except Exception as e:
        error_msg = f"可视化过程中出现错误: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        print(error_msg)
        traceback.print_exc()
        return {"type": "error", "content": f"可视化失败：{str(e)}"}


