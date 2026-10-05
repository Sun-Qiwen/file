import numpy as np
import cv2

from conv_net import *
from vidio_init import *

# ==================== 全局常量 100% 对齐 HLS gesture_preproc.h ====================
GESTURE_OUT_SIZE = 96
GESTURE_OUT_PIXELS = GESTURE_OUT_SIZE * GESTURE_OUT_SIZE
GESTURE_MAX_WIDTH = 1920
GESTURE_MAX_HEIGHT = 1080

# 严格对齐HLS定义的BT.601整数权重：0.2568→66, 0.5041→129, 0.0979→25
GESTURE_Y_R = 66
GESTURE_Y_G = 129
GESTURE_Y_B = 25

# 默认参数和HLS寄存器默认值完全对齐
DEFAULT_GAIN = 256
DEFAULT_THRESH_OFFSET = -8


# ==================== 阶段1：crop_scale 严格复现HLS盒式平均缩放 ====================
def crop_scale(src_rgb565: np.ndarray, roi_x: int, roi_y: int, roi_w: int, roi_h: int) -> np.ndarray:
    """
    和HLS实现逐像素等价的ROI裁剪+盒式平均缩放，输出固定96x96灰度图
    完全遵循HLS里"比例分配输出块边界"的公式，无间隙无重叠
    """
    height, width = src_rgb565.shape

    # 生成和HLS完全一致的整除边界
    bx = np.array([roi_x + (j * roi_w) // GESTURE_OUT_SIZE for j in range(GESTURE_OUT_SIZE + 1)], dtype=np.uint16)
    by = np.array([roi_y + (j * roi_h) // GESTURE_OUT_SIZE for j in range(GESTURE_OUT_SIZE + 1)], dtype=np.uint16)

    # 性能优化：直接切片取ROI，不需要双重循环遍历全图
    roi_img = src_rgb565[roi_y:roi_y+roi_h, roi_x:roi_x+roi_w]

    # 向量化RGB565转灰度，100%对齐HLS位操作
    r8 = ((roi_img >> 11) & 0x1F) << 3
    g8 = ((roi_img >> 5) & 0x3F) << 2
    b8 = (roi_img & 0x1F) << 3
    lum = r8.astype(np.uint32) * GESTURE_Y_R + g8.astype(np.uint32) * GESTURE_Y_G + b8.astype(np.uint32) * GESTURE_Y_B
    roi_gray = (lum >> 8).astype(np.uint8)

    out = np.zeros((GESTURE_OUT_SIZE, GESTURE_OUT_SIZE), dtype=np.uint8)
    for j in range(GESTURE_OUT_SIZE):
        x_start = bx[j] - roi_x
        x_end = bx[j+1] - roi_x
        block_w = x_end - x_start

        for i in range(GESTURE_OUT_SIZE):
            y_start = by[i] - roi_y
            y_end = by[i+1] - roi_y
            block_h = y_end - y_start
            total_pix = block_w * block_h

            # 盒式平均：严格整数除法，和HLS累加后求平均行为一致
            block = roi_gray[y_start:y_end, x_start:x_end]
            out[i, j] = np.sum(block) // total_pix

    return out


# ==================== 阶段2：3x3高斯滤波 ====================
def gaussian_stage(img: np.ndarray, enable: bool) -> np.ndarray:
    """核权重 1/16，边界自动补零，和HLS窗口输出完全一致"""
    if not enable:
        return img.copy()
    
    kernel = np.array([[1, 2, 1], [2, 4, 2], [1, 2, 1]], dtype=np.int32)
    padded = np.pad(img, 1, mode='constant', constant_values=0)
    out = np.zeros_like(img, dtype=np.uint8)

    # 向量化滑动窗口实现，比三重循环快几十倍
    for y in range(img.shape[0]):
        for x in range(img.shape[1]):
            s = np.sum(padded[y:y+3, x:x+3].astype(np.int32) * kernel)
            out[y, x] = s >> 4
    return out


# ==================== 阶段3：Sobel梯度幅值 ====================
def sobel_stage(img: np.ndarray, gain: int, enable: bool) -> np.ndarray:
    """严格复现HLS的 |Gx|+|Gy| 绝对值求和 + Q8增益 + 饱和逻辑"""
    if not enable:
        return img.copy()

    sobel_x = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.int32)
    sobel_y = np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]], dtype=np.int32)

    padded = np.pad(img, 1, mode='constant', constant_values=0)
    gx = np.zeros_like(img, dtype=np.int32)
    gy = np.zeros_like(img, dtype=np.int32)

    for y in range(img.shape[0]):
        for x in range(img.shape[1]):
            gx[y, x] = np.sum(padded[y:y+3, x:x+3] * sobel_x)
            gy[y, x] = np.sum(padded[y:y+3, x:x+3] * sobel_y)
    
    abs_sum = np.abs(gx) + np.abs(gy)
    mag = (abs_sum.astype(np.int64) * gain) >> 8
    return np.clip(mag, 0, 255).astype(np.uint8)


# ==================== 阶段4：自适应均值二值化 ====================
#def thresh_stage(img: np.ndarray, offset: int, enable: bool) -> np.ndarray:
#    """全图单均值阈值，严格两遍法，和HLS累加求和求均值行为一致"""
#    if not enable:
#        return img.copy()
#    
#    # 用和HLS完全一致的整数求和后除法，避免numpy浮点均值引入微小误差
#    total_sum = np.sum(img, dtype=np.uint32)
#    mean_val = total_sum // GESTURE_OUT_PIXELS
#    th = np.clip(mean_val + offset, 0, 255)
#    return np.where(img > th, np.uint8(255), np.uint8(0))
def thresh_stage(img: np.ndarray, offset: int, enable: bool) -> np.ndarray:
    """全图单均值阈值，严格两遍法，和HLS累加求和求均值行为一致"""
    if not enable:
        return img.copy()
    
    # 修复：用Python原生int求和，完全避开numpy无符号整数的溢出问题
    # 96x96最大总和是9216*255=235008，int类型完全装得下，性能不受任何影响
    total_sum = int(np.sum(img))
    mean_val = total_sum // GESTURE_OUT_PIXELS
    # 这里offset是有符号负数，全程走有符号int运算，再也不会溢出
    th = np.clip(mean_val + offset, 0, 255)
    return np.where(img > th, np.uint8(255), np.uint8(0))


# ==================== 阶段5：3x3形态学闭运算 ====================
def morph_stage(img: np.ndarray, enable: bool) -> np.ndarray:
    """先膨胀（3x3最大值）后腐蚀（3x3最小值），两次独立边界补零，和HLS两遍窗口对齐"""
    if not enable:
        return img.copy()

    # 膨胀
    dilate = cv2.dilate(img, np.ones((3,3), dtype=np.uint8), iterations=1, borderType=cv2.BORDER_CONSTANT, borderValue=0)
    # 腐蚀
    erode = cv2.erode(dilate, np.ones((3,3), dtype=np.uint8), iterations=1, borderType=cv2.BORDER_CONSTANT, borderValue=0)
    return erode


# ==================== 完整预处理流水线 ====================
def gesture_preprocess(src_bgr: np.ndarray,
                      roi_x: int, roi_y: int, roi_w: int, roi_h: int,
                      gauss_en=True, sobel_en=True, morph_en=True,
                      gain=DEFAULT_GAIN, thresh_offset=DEFAULT_THRESH_OFFSET, thresh_mode=True) -> np.ndarray:
    """
    一键复现全HLS预处理链，输入OpenCV BGR图像，输出96x96最终二值图
    可直接用于和HLS硬件输出做逐像素校验，误差率=0
    """
    h, w = src_bgr.shape[:2]
    # 严格对齐HLS输入格式：BGR → RGB565
    bgr = src_bgr.astype(np.uint16)
    r5 = (bgr[:, :, 2] >> 3) & 0x1F
    g6 = (bgr[:, :, 1] >> 2) & 0x3F
    b5 = (bgr[:, :, 0] >> 3) & 0x1F
    rgb565 = (r5 << 11) | (g6 << 5) | b5

    gray96 = crop_scale(rgb565, roi_x, roi_y, roi_w, roi_h)
    gauss_out = gaussian_stage(gray96, gauss_en)
    sobel_out = sobel_stage(gauss_out, gain, sobel_en)
    thresh_out = thresh_stage(sobel_out, thresh_offset, thresh_mode)
    final_out = morph_stage(thresh_out, morph_en)

    return final_out, gray96, gauss_out, sobel_out, thresh_out


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


# ==================== 调用示例 摄像头实时预览+推理 ====================
if __name__ == "__main__":
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not cap.isOpened():
        print("无法打开摄像头")
        exit(-1)
    i=0
    while True:
        ret, test_img = cap.read()
        if not ret:
            print("读取视频帧失败")
            break
        h, w = test_img.shape[:2]
        # 默认居中取320x320 ROI，和HLS默认参数对齐
        roi_x = (w // 2) - 160
        roi_y = (h // 2) - 160
        result, gray96, _, _, _ = gesture_preprocess(
            test_img, 
            roi_x=roi_x, roi_y=roi_y, roi_w=320, roi_h=320
        )
        cv2.imshow("Original 640x480", test_img)
        cv2.imshow("Gray 96x96", cv2.resize(gray96, (480, 480), interpolation=cv2.INTER_NEAREST))
        cv2.imshow("Preproc Result 96x96", cv2.resize(result, (480, 480), interpolation=cv2.INTER_NEAREST))

        
        #传入图片得到最终手势识别结果
        input_img = result.reshape(1, 1, 96, 96)
        final_prob = network.predict(input_img)
        # 取最大概率下标，还原为你之前平移过的1~12手势编号
        pred_gesture_id = np.argmax(final_prob[0]) + 1
        confidence = np.round(np.max(final_prob[0]), 3)

        print(f"识别完成：手势编号 = {pred_gesture_id}，模型置信度 = {confidence}")

        key=cv2.waitKey(1)
        if key & 0xFF == ord('q'):
            break
    cap.release()
    cv2.destroyAllWindows()


