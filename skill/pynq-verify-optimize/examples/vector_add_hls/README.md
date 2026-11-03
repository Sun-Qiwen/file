# 独立案例：参数化向量加法 HLS IP 骨架

用于练习与具体神经网络无关的“接口契约 → 黄金参考 → 局部验证 → HLS IP 导出 → 项目适配”。包含真实 C++ 核、测试平台和可配置 Tcl；不是已生成的 PYNQ Overlay，也不提供跨板通用 bitstream。

## 文件和接口契约

|文件|作用|
|---|---|
|[vector_add.hpp](vector_add.hpp)、[vector_add.cpp](vector_add.cpp)|三个 m_axi 端口和一个 AXI-Lite 控制接口的向量加法核|
|[testbench.cpp](testbench.cpp)|独立宽位参考、首尾保护区、输入不变、重复调用和故意错误测试|
|[run_native.py](run_native.py)|GCC/Clang 本地编译、正负例执行、日志与源码指纹|
|[run_hls.tcl](run_hls.tcl)|按器件/周期/新输出目录运行 csim、综合、RTL 协仿或 IP 导出|

输入、输出均为 `uint32_t` 一维连续数组，地址至少 4 字节对齐，三个有效区域互不重叠；`out[i] = (a[i] + b[i]) mod 2^32`。`n` 为元素数而非字节数，合法范围 0～4096；`n=0` 不读写内存且成功，超限返回状态 1 且不访问内存，其余成功返回 0。非空调用必须提供覆盖 n 个元素的有效内存。核返回状态与 AXI 控制完成位是不同含义。

最大长度 4096 是此案例的接口上限，**不是通用板卡限制**；修改时同步头文件、接口 depth、测试规模和主机检查。`II=1` 仅为调度目标，实际 II、带宽、时序和资源要由对应报告证明。

## 先运行 CPU 本地验证

在本目录执行，输出选择不存在的新目录：

```text
python -B run_native.py --compiler g++ --out native-run-01
```

编译器不在 PATH 时，给 `--compiler` 传可执行文件绝对路径。Windows 的 MinGW 需要相应运行库可用；脚本只给本次子进程追加编译器目录和临时目录，不修改系统环境。GCC/Clang 命令参数不适用于 MSVC。编译器启动失败先检查工具路径与日志，不把环境失败当作算法失败。

正例共 36 次调用：0、1、3、63、64、65、1023、4095、4096 和超限长度，包含重复调用、溢出边界及固定种子输入；参考用 64 位求和后掩码。负例在核执行后破坏一个输出，必须由比较器报错且返回 1。正例通过只能证明本地 C++ 行为；编译器忽略 HLS pragma，不能证明接口、综合或 RTL 正确。

## 再运行配置过的 HLS 流程

安装支持 Tcl 流程的 Vitis HLS，设置真实目标器件和周期。以下为 PowerShell 模板，先替换尖括号内容，不要原样运行：

```powershell
$env:VADD_PART = '<目标器件完整 part>'
$env:VADD_CLOCK_NS = '<正数周期 ns>'
$env:VADD_OUT = '<尚不存在的 HLS 工程绝对路径>'
$env:VADD_STAGE = 'csim'
vitis-run --mode hls --tcl run_hls.tcl
```

|VADD_STAGE|累计执行步骤|
|---|---|
|`csim`（默认）|C 仿真|
|`synth`|C 仿真、C 综合|
|`cosim`|C 仿真、C 综合、Verilog RTL 协仿|
|`export`|前述步骤、IP catalog 导出|

每次用新输出目录，避免覆盖旧实验。脚本不调用 Vivado 实现，不生成板级 BD、XDC、bit 或 HWH。C/RTL 协仿的存储模型与实板 AXI 背压、缓存同步不同；不能替代实板验证。新工具版本先核对 Tcl 支持，不把命令替身测试当作真实 EDA 执行。

命令依据：[AMD Vitis-run 命令](https://docs.amd.com/r/en-US/ug1702-vitis-accelerated-reference/vitis-run-Command)、[AMD export_design](https://docs.amd.com/r/en-US/ug1399-vitis-hls/export_design)、[AMD HLS 官方入门案例](https://github.com/Xilinx/Vitis-HLS-Introductory-Examples)。本次只检查公开命令说明，未运行 HLS。

## 接入新板卡或题目

1. 在目标板的系统工程里实例化导出的 IP，连接三个 m_axi 主接口、AXI-Lite、时钟/复位及可访问的 PS 内存端口。是否合并 bundle 要按目标带宽和资源取舍重新验证。
2. 生成同一构建的 bit/HWH，记录实际 IP 名称、控制协议、寄存器偏移、地址位宽与时钟；从工具生成头文件和 `register_map` 核对，不手写假定的固定地址。
3. 按 [PYNQ 运行约定](../../references/pynq-runtime.md) 建立项目驱动：分配连续缓冲区、输入同步、写地址和 n、启动、等待带超时的完成、读取返回状态、输出同步、按实际访问状态释放。此核直接使用 m_axi，**不需要 AXI DMA 驱动**；改成 AXI Stream 后需重新设计契约。
4. 同时检查整数输出、保护区、重复/交替调用、完成与错误路径，再用 [实验模板](../../assets/templates/experiment-report.md) 记录真实 A/B/A。跨板复用的是源码、契约和验证方法，所有物理实现结果须重新取得。

## 当前验证边界

本包的验证记录见 [validation/report.md](../../validation/report.md)。本次运行本地 C++ 正负例及 Tcl 命令替身测试；未综合此 IP、未进行 RTL 协仿、未生成新 bitstream、未上板。目标板适配、II、资源、时序和性能均保持待验证。
