# 当前版本源码

- `ps/game/`：金币游戏、计分、BTN0重开、PS DDR渲染与显示控制。
- `ps/inference_core/`：硬件推理会话、YOLOX前后处理、手框选择和关键点解码；模型标识为 `yolox`、`cnn`，会话工厂必须显式提供。
- `ps/common/`：几何、量化输出和硬件/数值契约工具。
- `ps/hdmi/legacy/`：当前运行复用的摄像头采集和通用方向控制模块；目录名不改变运行行为。
- `rtl/ddr_hdmi.v`：DDR扫描输出和BTN0事件寄存器；`rtl/hdmi/rgb2dvi/`：TMDS发送。
- `hls/inference_core/`：冻结64MAC推理核源码，顶层IP标识保持不变。

PS源码与板端运行副本逐文件一致。已移除运动预测模块、预测结果字段、ONNX Runtime备用路径及其独立图片CLI；游戏入口继续使用 `coin_game.py`。手势控制和游戏参数不变，未重新训练或量化模型。

配对硬件交付名为 `gesture_coin_game.bit/.hwh`，构建入口在build，验证入口在sim。数值舍入、缓存同步和DMA生命周期相关约束保留。
