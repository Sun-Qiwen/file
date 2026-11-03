# 板端运行包

[runtime/application/](runtime/application/README.md)包含当前手动金币游戏运行所需的PS程序、模型数据、NPZ图片素材和配对 `gesture_coin_game.bit/.hwh`。完整复制该目录并保留子目录即可按根目录说明启动。

包修订为 `gesture_coin_game_cleanup_20261103`。运行流程已移除未使用的运动预测和ONNX备用路径；图片仅保留实际加载的NPZ。位流、HWH、模型和NPZ的内容保持不变，游戏与手势控制参数保持不变。程序不包含目标方向辅助、自动寻路或直线辅助。

项目作者确认已完成构建并多次上板测试，统一状态见[report/build_status.json](../report/build_status.json)。[report/verification.json](../report/verification.json)记录清理阶段离线复验；[report/board](../report/board/README.md)保留已归档板测的具体版本、场景和指标。
