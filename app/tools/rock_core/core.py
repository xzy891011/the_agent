# import tensorflow as tf

# print("Num GPUs Available: ", len(tf.config.experimental.list_physical_devices('GPU')))
# GPU_list = tf.config.list_physical_devices('GPU')
import numpy as np 
import os
import skimage.io as io
import skimage.transform as trans
from keras.api.models import *
from keras.api.layers import *
from keras.api.optimizers import *
from keras.api.callbacks import ModelCheckpoint, LearningRateScheduler,TensorBoard
from keras import backend as keras
import logging

from PIL import Image
import matplotlib.pyplot as plt
import tempfile
import traceback
import time
from app.core.file_manager import file_manager
from app.tools.registry import register_tool
from app.tools.schemas import IdentifyCrackSchema
from langgraph.config import get_stream_writer

logger = logging.getLogger(__name__)

def image_preprocess(image_path:str):
    # Load the image
    image = Image.open(image_path)
    
    # Assuming white background is on the outer edges
    np_image = np.array(image)
    
    # Find all rows and columns that are not completely white
    non_white_rows = np.where(np_image.min(axis=1) < 255)[0]
    non_white_cols = np.where(np_image.min(axis=0) < 255)[0]
    
    # Crop the image to these rows and columns
    cropped_image = image.crop((non_white_cols[0], non_white_rows[0], 
                                     non_white_cols[-1], non_white_rows[-1]))
    
    # Resize the image maintaining the height, change width to 448
    new_width = 448
    new_height = cropped_image.height
    resized_image = cropped_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Split the resized image into chunks of height 1024
    segments = []
    for i in range(0, new_height, 1024):
        # Check if the current crop will go beyond the image height
        if i + 1024 > new_height:
            segment = resized_image.crop((0, i, new_width, new_height))
        else:
            segment = resized_image.crop((0, i, new_width, i + 1024))
        segments.append(segment)
    
    return segments



    


def unet(pretrained_weights = None,input_size = (1024,448,3)):
    inputs = Input(input_size,name='input')
    conv1 = Conv2D(8, 3, activation = 'relu', padding = 'same', kernel_initializer = 'he_normal',name='1_conv1')(inputs)
    conv1 = Conv2D(8, 3, activation = 'relu', padding = 'same', kernel_initializer = 'he_normal',name='1_conv2')(conv1)
    pool1 = MaxPooling2D(pool_size=(2, 2),name='1_pool')(conv1)
    conv2 = Conv2D(16, 3, activation = 'relu', padding = 'same', kernel_initializer = 'he_normal',name='2_conv1')(pool1)
    conv2 = Conv2D(16, 3, activation = 'relu', padding = 'same', kernel_initializer = 'he_normal',name='2_conv2')(conv2)
    pool2 = MaxPooling2D(pool_size=(2, 2),name='2_pool')(conv2)
    conv3 = Conv2D(32, 3, activation = 'relu', padding = 'same', kernel_initializer = 'he_normal',name='3_conv1')(pool2)
    conv3 = Conv2D(32, 3, activation = 'relu', padding = 'same', kernel_initializer = 'he_normal',name='3_conv2')(conv3)
    pool3 = MaxPooling2D(pool_size=(2, 2),name='3_pool')(conv3)
    conv4 = Conv2D(64, 3, activation = 'relu', padding = 'same', kernel_initializer = 'he_normal',name='4_conv1')(pool3)
    conv4 = Conv2D(64, 3, activation = 'relu', padding = 'same', kernel_initializer = 'he_normal',name='4_conv2')(conv4)
    drop4 = Dropout(0.5,name='4_drop')(conv4)
    pool4 = MaxPooling2D(pool_size=(2, 2),name='4_pool')(drop4)

    conv5 = Conv2D(128, 3, activation = 'relu', padding = 'same', kernel_initializer = 'he_normal',name='5_conv1')(pool4)
    conv5 = Conv2D(128, 3, activation = 'relu', padding = 'same', kernel_initializer = 'he_normal',name='5_conv2')(conv5)
    drop5 = Dropout(0.5,name='5_drop')(conv5)

    up6 = Conv2D(64, 2, activation = 'relu', padding = 'same', kernel_initializer = 'he_normal',name='6_conv1')(UpSampling2D(size = (2,2),name='6_upsampling')(drop5))
    merge6 = concatenate([drop4,up6], axis = 3, name='6_merge')
    conv6 = Conv2D(64, 3, activation = 'relu', padding = 'same', kernel_initializer = 'he_normal', name='6_conv2')(merge6)
    conv6 = Conv2D(64, 3, activation = 'relu', padding = 'same', kernel_initializer = 'he_normal', name='6_conv3')(conv6)

    up7 = Conv2D(32, 2, activation = 'relu', padding = 'same', kernel_initializer = 'he_normal',name='7_cpnv1')(UpSampling2D(size = (2,2),name='7_upsampling')(conv6))
    merge7 = concatenate([conv3,up7], axis = 3, name='7_merge')
    conv7 = Conv2D(32, 3, activation = 'relu', padding = 'same', kernel_initializer = 'he_normal', name='7_conv2')(merge7)
    conv7 = Conv2D(32, 3, activation = 'relu', padding = 'same', kernel_initializer = 'he_normal', name='7_conv3')(conv7)

    up8 = Conv2D(16, 2, activation = 'relu', padding = 'same', kernel_initializer = 'he_normal',name='8_conv1')(UpSampling2D(size = (2,2),name='8_upsampling')(conv7))
    merge8 = concatenate([conv2,up8], axis = 3, name='8_merge')
    conv8 = Conv2D(16, 3, activation = 'relu', padding = 'same', kernel_initializer = 'he_normal', name='8_conv2')(merge8)
    conv8 = Conv2D(16, 3, activation = 'relu', padding = 'same', kernel_initializer = 'he_normal', name='8_conv3')(conv8)

    up9 = Conv2D(8, 2, activation = 'relu', padding = 'same', kernel_initializer = 'he_normal',name='9_conv1')(UpSampling2D(size = (2,2),name='9_upsampling')(conv8))
    merge9 = concatenate([conv1,up9], axis = 3, name='9_merge')
    conv9 = Conv2D(8, 3, activation = 'relu', padding = 'same', kernel_initializer = 'he_normal', name='9_conv2')(merge9)
    conv9 = Conv2D(8, 3, activation = 'relu', padding = 'same', kernel_initializer = 'he_normal', name='9_conv3')(conv9)
    conv9 = Conv2D(2, 3, activation = 'relu', padding = 'same', kernel_initializer = 'he_normal', name='9_conv4')(conv9)
    
    conv10 = Conv2D(1, 1, activation = 'sigmoid', name='10_conv')(conv9)

    model = Model(inputs,conv10)
    #model.compile(optimizer = Adam(lr = 1e-4), loss = 'binary_crossentropy', metrics = ['accuracy'])
    #model.summary()

    
    if(pretrained_weights):
        model.load_weights(pretrained_weights)

    return model

def join_segments(segments, output_path,additional_height:int):
    # 计算拼接后的总高度
    total_height = sum(segment.height for segment in segments)-additional_height
    max_width = max(segment.width for segment in segments)  # 假设宽度相同或取最大宽度
    
    # 创建一个新的图像，背景为黑色（或您想要的任何颜色）
    new_image = Image.new('L', (max_width, total_height))
    
    # 在新图像上依次贴上每个部分
    y_offset = 0
    for segment in segments:
        new_image.paste(segment, (0, y_offset))
        y_offset += segment.height
    
    # 保存为JPG格式
    new_image.save(output_path, 'JPEG')

@register_tool(category="rock_core", use_structured_tool=True)
def identify_crack(file_id: str):
    """
    识别岩心裂缝的函数
    """
    try:
        writer = get_stream_writer()
        # 推送开始处理的消息
        if writer:
            writer({"custom_step": "开始岩心裂缝识别过程..."})
        
        file_info = file_manager.get_file_info(file_id)
        if not file_info:
            return f"找不到ID为 {file_id} 的文件。"
            
        file_path = file_info.get("file_path")
        file_type = file_info.get("file_type", "").lower()
        file_name = file_info.get("file_name", "")
            
        best_weights_path = "app/tools/rock_core/best_weights.h5"
        output_path = file_manager.generated_path
        
        # 检查权重文件格式
        if writer:
            writer({"custom_step": "正在检查模型权重文件..."})
            
        if not best_weights_path.endswith(('.h5', '.keras', '.weights.h5')):
            # 如果不是支持的格式，尝试转换或使用替代路径
            base_path = os.path.splitext(best_weights_path)[0]
            best_weights_path = base_path + '.h5'
            
            if not os.path.exists(best_weights_path):
                raise ValueError(f"找不到支持的权重文件格式。需要.h5、.keras或.weights.h5格式的文件: {best_weights_path}")
        
        image_name = os.path.splitext(os.path.basename(file_path))[0]
        
        if writer:
            writer({"custom_step": "正在加载神经网络模型..."})
            
        model = unet()
        model.load_weights(best_weights_path)
        
        if writer:
            writer({"custom_step": "正在预处理图像..."})
            
        segments = image_preprocess(file_path)
        current_width, current_height = segments[-1].size
        additional_height = 0
        
        if(current_height < 1024):
            additional_height = 1024 - current_height
            black_part = Image.new('RGB', (current_width, additional_height), (0, 0, 0))
            new_segment = Image.new('RGB', (current_width, 1024))
            new_segment.paste(segments[-1], (0, 0))
            new_segment.paste(black_part, (0, current_height))
            segments[-1] = new_segment
        
        if writer:
            writer({"custom_step": "正在进行岩心裂缝预测..."})
            
        segment_np_arrays = np.array([np.array(segment) for segment in segments])
        predict_segment_array = model.predict(segment_np_arrays)
        predict_normalized = [(predict_segment[:,:,0] - predict_segment[:,:,0].min()) / 
                            (predict_segment[:,:,0].max() - predict_segment[:,:,0].min()) 
                            for predict_segment in predict_segment_array]
        data_uint8 = [(predict * 255).astype(np.uint8) for predict in predict_normalized]
        predict_segments = [Image.fromarray(data, 'L') for data in data_uint8]

        if writer:
            writer({"custom_step": "正在组合图像结果..."})
            
        # 建临时图像对象
        origin_image = Image.new('RGB', (segments[0].width, sum(segment.height for segment in segments) - additional_height))
        result_image = Image.new('L', (predict_segments[0].width, sum(segment.height for segment in predict_segments) - additional_height))

        # 直接在内存中拼接图像
        y_offset = 0
        for segment in segments:
            origin_image.paste(segment, (0, y_offset))
            y_offset += segment.height

        y_offset = 0
        for segment in predict_segments:
            result_image.paste(segment, (0, y_offset))
            y_offset += segment.height

        # 保存图片到输出路径
        origin_save_path = os.path.join(output_path, f"{image_name}-origin.jpg")
        result_save_path = os.path.join(output_path, f"{image_name}-predicted.jpg")
        
        if writer:
            writer({"custom_step": "正在保存图像结果..."})
            
        # 保存图片
        origin_image.save(origin_save_path)
        result_image.save(result_save_path)
        
        logger.info(f"Debug: Saving images to {origin_save_path} and {result_save_path}")
        logger.info(f"Debug: Image sizes - Origin: {origin_image.size}, Result: {result_image.size}")
        
        # 推送图像结果到前端
        if writer:
            # 推送原始图像
            writer({"image_message": {
                "image_path": origin_save_path,
                "title": "岩心原始图像"
            }})
            
            # 推送预测结果图像
            writer({"image_message": {
                "image_path": result_save_path,
                "title": "岩心裂缝识别结果"
            }})
            
            writer({"custom_step": "岩心裂缝识别完成！"})
        
        # 返回自然语言描述的结果
        return f"岩心裂缝识别已成功完成。\n已处理图像：{image_name}\n结果已保存为两个图像文件：\n- 原始图像：{os.path.basename(origin_save_path)}\n- 裂缝识别结果：{os.path.basename(result_save_path)}"

    except Exception as e:
        print(f"Error in identify_crack: {str(e)}")
        traceback.print_exc()
        if writer:
            writer({"custom_step": f"岩心裂缝识别失败: {str(e)}"})
        return f"岩心裂缝识别失败。错误原因：{str(e)}"

# 为identify_crack工具设置schema
identify_crack.args_schema = IdentifyCrackSchema



