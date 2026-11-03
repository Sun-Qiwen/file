# PYNQ-Z2 手势控制金币游戏交付包

项目状态：**已完成构建，已完成多次上板测试**。完成状态由项目作者确认，现有硬件产物、实现报告和归档板测记录随包保留，依据见[构建状态](report/build_status.json)。

当前手动金币游戏软件策略为 `no_iou_conf015_single_frame_no_expiry`，硬件版本为 `ddr_coin_game_btn0`，目录包修订为 `gesture_coin_game_cleanup_20261103`。固定草地背景，准备3秒后开始默认60秒挑战；场上只有一枚随机金币，小车吃币加1分并立即生成下一枚，到时停车并显示分数，BTN0可在各阶段重开。

方向采用单帧有效结果、3度方向滞回；YOLOX手框阈值0.15、指向概率阈值0.5、跨帧IoU门槛关闭、NMS阈值0.45。指令超时和帧龄限制关闭；无手、多框歧义、无效手势、游戏结束和退出仍停车，丢手后保留3次恢复确认。小车方向由有效手势决定，不含目标方向辅助和自动寻路。

## 交付结构

|目录|内容|
|---|---|
|[src](src/README.md)|PS游戏、硬件推理接口、显示RTL和冻结HLS源码|
|[sim](sim/README.md)|56项Python测试（含11项HLS入口检查）、7类既有RTL场景及验证入口|
|[build](build/README.md)|构建脚本、约束、冻结IP、最终综合/布线检查点与报告|
|[board](board/README.md)|完整独立运行包，配对gesture_coin_game bit/HWH、模型与NPZ素材|
|[data](data/README.md)|冻结模型与数值参考、可编辑源图和DDR素材|
|[skill](skill/README.md)|可复用的PYNQ验证与优化方法|
|[report](report/README.md)|当前版本、离线复验、既有板测和物理实现证据|

## 在板上启动

将 `board/runtime/application/` 的全部内容复制到板端同一目录，例如 `/home/xilinx/coin_game/`，保留 `assets/` 和 `overlay/` 子目录。退出其他占用摄像头、推理核或显示的程序后，在Jupyter Terminal执行：

```sh
cd /home/xilinx/coin_game
sudo env XILINX_XRT=/usr OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /usr/local/share/pynq-venv/bin/python3 -B coin_game.py
```

BTN0重开，Ctrl+C退出。默认摄像头旋转180度，`--rotate 0`取消旋转。运行入口逐文件校验；完整替换运行目录，避免混入其他版本。配对文件为 `overlay/gesture_coin_game.bit` 和 `overlay/gesture_coin_game.hwh`。

## 实现与验证

PS通过NumPy/OpenCV预处理并绘制DDR画面，YOLOX和关键点CNN由PL执行。Pipeline显式使用硬件模型标识，不提供运动预测或ONNX Runtime备用路径；板端素材只需 `assets/images.npz`。

推理核保持64个实际整数MAC、100MHz；已有物理结果为Slice13163/13300、BRAM36等效119.5/140、DSP213/220，WNS+0.110ns、WHS+0.010ns、WPWS+0.538ns。硬件文件仅改名，模型、NPZ、冻结IP与DCP保持原字节。PS源码已清理，不能再称整个运行包与旧版本逐字节相同。

清理阶段离线复验包括45项Python测试、7类RTL场景、固定输入的推理/方向/渲染等价对比、清单和源码副本检查。既往构建及上板测试已完成，各次整理操作的执行范围分别记录，见[完整说明](report/final.md)、[构建状态](report/build_status.json)和[清理记录](report/cleanup.json)。复现时的构建与验证输出必须写到交付目录之外。

## 构建资料补齐

已补回与现有综合DCP对应的原始综合资源与控制集报告、原执行记录及文件绑定，综合和最终实现报告分别保存在build/reports/synthesis和build/reports/implementation。详情见[补齐记录](report/build_materials.json)。

构建资料已按现有正式成果整理，游戏源码、模型、素材、bit/HWH与DCP保持原内容。交付目录只保留正式材料，临时工程、日志和缓存使用包外目录。

## HLS入口路径适配

正式入口位于build/scripts/hls/build.py，使用当前包内源码与相对路径配置，不依赖旧D盘或历史common.py。原配置和脚本保留原字节；路径、准备模式和保护检查见[适配记录](report/hls_entry.json)，项目完成状态统一见[构建状态](report/build_status.json)。

HLS路径适配记录包含11项Python入口检查，随包Python测试共56项通过；7类RTL结果对应随包未改动的RTL源码。
