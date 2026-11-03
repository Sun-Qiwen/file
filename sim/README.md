# 当前金币游戏验证

`tests/`共56项Python测试，其中原45项覆盖：金币生成/碰撞/结算、BTN0重开/旧帧隔离、资源清理、DDR显示、单帧控制、无IoU与0.15阈值，以及硬件模型标识路由、未知模型拒绝和无运动/ONNX后端依赖的Pipeline执行。

`rtl/tb_ddr_hdmi.sv`覆盖按键消抖/长按、1280像素行读取、提前/缺失/延迟RLAST、错误RID和SLVERR，共7类RTL场景。

安装与板端代码兼容的NumPy和OpenCV；RTL验证需Icarus Verilog。所有输出写到新的外部目录：

```powershell
python -B sim/run_checks.py --output E:/coin_game_checks/run01 --iverilog D:/iverilog/bin/iverilog.exe --vvp D:/iverilog/bin/vvp.exe
```

新增11项覆盖HLS入口路径、配置准备、迁移与输出保护。只运行Python可添加 `--skip-rtl`。交付目录内不生成日志、编译产物或pyc。清理阶段45项Python和7类RTL结果见[验证摘要](../report/verification.json)，本次56项Python复验见[入口适配记录](../report/hls_entry.json)，清理前后等价对比与文件身份见[清理记录](../report/cleanup.json)。神经推理和硬件执行替身只用于PS策略/接口边界验证，不替代真实识别准确率、HDMI目视或数值A/B/A验收。

本次HLS路径适配新增11项Python入口检查，随包Python测试共56项通过；本次未调用RTL编译，7类既有RTL结果仍对应未改动的RTL源码。
