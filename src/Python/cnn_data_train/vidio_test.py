import numpy as np
from conv_net import *
from vidio_init import *

if __name__ == "__main__":
    # 1. 初始化空网络，结构必须和训练时完全匹配
    network = ConvNet(
        input_dim=(1, 96, 96),
        conv_param={'filter_num':30, 'filter_size':5, 'filter_pad':0, 'filter_stride':1},
        hidden_size=100,
        output_size=13,
        weight_init_std=0.01
    )

    # 2. 加载你之前训练好的已有params.pkl文件
    network.load_params("params.pkl")
    print("预训练参数加载完成")
    
    # 3. 传入图片得到最终手势识别结果
    input_img = result.reshape(1, 1, 96, 96)
    final_prob = network.predict(input_img)
    # 取最大概率下标，还原为你之前平移过的1~12手势编号
    pred_gesture_id = np.argmax(final_prob[0]) + 1
    confidence = np.round(np.max(final_prob[0]), 3)

    print(f"识别完成：手势编号 = {pred_gesture_id}，模型置信度 = {confidence}")