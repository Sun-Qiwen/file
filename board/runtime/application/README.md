# 手势控制金币游戏板端运行包

入口为 `coin_game.py`，依赖板端PYNQ、NumPy和OpenCV。完整复制本目录，保留 `overlay/` 和 `assets/`，在PYNQ Python环境运行：

```sh
cd /home/xilinx/coin_game
sudo env XILINX_XRT=/usr OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /usr/local/share/pynq-venv/bin/python3 -B coin_game.py
```

准备3秒，默认游戏60秒；吃币加1分，BTN0在各阶段重开，Ctrl+C停车并退出。默认摄像头0、640x480，旋转180度；可添加 `--rotate 0`、`--camera 1` 或 `--duration 60`。日志默认写到板端用户目录的 `coin_game_logs/时间戳/`。

`overlay/gesture_coin_game.bit` 与同名HWH必须配对，包含YOLOX、关键点CNN、DDR显示和按键接口。`weights.bin`、`params.bin`及JSON描述供硬件推理驱动读取；模型会话使用 `yolox`、`cnn`标识。Pipeline由主程序注入硬件会话，不提供ONNX Runtime备用路径或独立图片命令行入口，也不依赖运动预测模块。

绘图读取 `assets/images.npz`，其内部包含背景、小车、轮胎、金币和透明遮罩；板端不需要PNG源图。修改素材需重新生成NPZ，并更新运行清单。

手框阈值0.15、指向概率0.5、NMS阈值0.45；唯一达标手框可跨位置继续，多个手框仍视为歧义，丢手或歧义后需3次恢复确认。方向单帧有效即生效，滞回3度。指令过期和帧龄上限关闭；显式无手、无效结果、结束、重开和退出仍停车。

`runtime_manifest.json`记录当前配置和逐文件SHA-256，主程序启动时校验。包修订为 `gesture_coin_game_cleanup_20261103`；软件策略为 `no_iou_conf015_single_frame_no_expiry`。
