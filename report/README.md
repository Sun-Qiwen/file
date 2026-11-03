# 当前交付证据

项目状态：**已完成构建，已完成多次上板测试**。完成状态由项目作者确认，现有硬件产物、实现报告和归档板测记录随包保留，依据见[构建状态](build_status.json)。

- [build_status.json](build_status.json)：作者确认的已完成构建、多次上板测试状态，以及归档资料依据。
- [final.md](final.md)：当前软件、硬件资源与验证范围。
- [cleanup.json](cleanup.json)：本次清理范围、二进制身份和清理前后等价对比。
- [verification.json](verification.json)：清理后45项Python测试与7类RTL场景的新离线结果。
- [release.json](release.json)：当前交付范围；[summary.json](summary.json)：硬件及验证摘要。
- [board/](board/README.md)：清理前手动策略的真实摄像头短测、板端策略与退出状态原始证据。
- [physical/](physical/README.md)：当前位流的已有物理报告，build中保留对应副本。
- [cdc_review.md](cdc_review.md)：原始CDC分类与精确约束解释。

`test_evidence.json`、`control_update.json`和 `history/packaging_verification_before_cleanup.json`保留清理前的源码哈希、测试和策略变更记录，其42项测试与旧运行清单哈希不代表当前源码的新验证。原始板测和物理记录保持原内容。

项目作者确认此前已完成构建并多次上板测试。清理、材料恢复和入口适配记录分别描述对应整理操作；其中的执行标志不表示项目尚未完成构建。当前PS源码有清理变更，bit/HWH、模型、NPZ与冻结IP/DCP保持原字节；归档板测保留其原有版本和场景范围。

- [build_materials.json](build_materials.json)：原始综合报告、来源和检查点身份核对；其执行标志描述材料恢复操作。

## HLS原始资料补回

已保留原HLS C/C++源码，并补回E盘原HLS配置、HLS综合报告及生成IP/插桩源码存档。原文件逐SHA256核对，详见[补回清单](hls_restoration.json)。历史路径与使用边界在存档README说明。

## HLS入口路径适配

正式入口位于build/scripts/hls/build.py，使用当前包内源码与相对路径配置，不依赖旧D盘或历史common.py。原配置和脚本保留原字节；路径、准备模式和保护检查见[适配记录](hls_entry.json)。项目整体完成状态见[build_status.json](build_status.json)。
