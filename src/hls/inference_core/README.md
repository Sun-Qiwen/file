# 冻结的YOLOX与关键点CNN推理核

本目录保存当前运行所用的冻结HLS源码，统一入口为 `yolox_int8`。`program.h`包含214条固定命令和arena布局。YOLOX使用INT8量化执行；CNN卷积为W8A8，GroupNorm等部分保留FP32，不能将整个系统称为纯INT8。

当前系统共享64个实际整数卷积MAC，运行100MHz，调度为8个输出乘8个像素；这一配置与[运行包](../../../board/runtime/application/README.md)的conv_configuration.json一致。预处理、手框/关键点后处理、游戏控制和DDR场景合成由PS执行。模型、量化参数和本目录C++在此次整理中均未修改。

正式复现使用[build目录](../../../build/README.md)中的冻结打包IP、约束和最终综合/布线检查点；旧开发目录下的sim/runs不作为本包依赖。当前bit/HWH、资源时序和已有板测边界见[最终报告](../../../report/final.md)，数值参考说明见[data目录](../../../data/README.md)。早期“尚未上板”的文字只属于当时开发阶段，不代表当前冻结核和整机已有证据。

本次未重新训练、重新量化、生成HLS IP或重新布局布线。已有PL运行与显示证据也不替代新的完整端到端数值A/B/A及HDMI目视/电气验收。

## 原生成资料

本目录12个C/C++文件与E盘原件及当时HLS源码封印逐SHA256核对一致。配套的[HLS配置](../../../build/config/hls/README.md)、[HLS综合报告](../../../build/reports/hls/README.md)和[原IP生成/插桩流程源码](../../../build/provenance/hls_original_flow/README.md)已恢复。[补回清单](../../../report/hls_restoration.json)记录来源与指纹。原流程中的历史路径保留用于追溯；此次没有生成IP。

## 当前路径入口

[正式HLS入口](../../../build/scripts/hls/README.md)从当前包定位这12份源码，并提供check、prepare和用户主动执行的build模式。当前配置使用相对路径；原配置保留在build/provenance/hls_original.cfg。本次仅适配与检查，未重新生成IP。
