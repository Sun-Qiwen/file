# 资源报告、站点与 PYNQ 状态工具

三个工具从原 `pynq-slice-compaction` 逐字节迁入，保留 [MIT 许可](evidence/slice_case_license.txt)。它们有各自适用边界，不是通用的一键验收器。新任务先复用已有报告，只有缺少必要证据时才执行相应采集。

## 静态资源与时序报告

```text
python scripts/check_reports.py baseline_route --clock kernel_clk=125 --out baseline.json
python scripts/check_reports.py candidate_route --clock kernel_clk=125 --seal candidate_route/execution.json --baseline baseline.json --out candidate.json
```

只依赖 Python 3.9+ 标准库。输入目录须含 `utilization.rpt`、`timing.rpt`、`check_timing.rpt`、`route_status.rpt`、`drc.rpt`、`routed.dcp`。原名不同时，在独立证据目录按名称组织并保留原文件路径/哈希，不修改原始报告。每个预期时钟分别给出 `--clock NAME=MHz`。

解析器针对已验证的 Vivado 2025.2 / 7-series 报告布局：资源表、12 类 check_timing、setup/hold/pulse、路由和 DRC 摘要。器件字段必须符合脚本支持的 `xc7...` 形式；其他架构、缺字段或不同表格需明确适配，不以缺失值当零。DCP 只计算文件哈希，并未打开验证内部结构。

`--seal` 可选。不提供时标记 `report_snapshot_unbound_to_execution`。提供时要求实际执行记录含 `started`、`ended`、`exit_code=0`、带 `-source` 的命令、脚本 SHA 和含全部六个输入的 `output_sha256`；记录与当前文件必须一致。此检查不能证明记录真实，更不能把事后编写的记录当成历史运行封存。

`--baseline` 核对同器件、容量、时钟与基线文件当前身份，然后报告资源变化。源码、工具版本与物理约束的可比性仍需人工或项目验证；是否允许 DSP/BRAM 交换由当前契约决定。基线摘要含原文件路径，搬迁后要在新位置重新生成摘要。

成功退出 0 只代表脚本范围内的静态检查通过；失败返回非零。指定 `--out` 时必须是新文件。`static_checks_passed` 不等于功能正确、bit/HWH 配对、实板通过或整个作品验收。完整设计中存在未约束外部接口时，该严格检查可能拒绝，应如实补约束或说明验证边界，不改原始报告绕过检查。

## 从 DCP 统计真实站点

```text
vivado -mode batch -source scripts/collect_sites.tcl -tclargs candidate_route/routed.dcp sites.txt compact_logic
```

需要目标机器的 Vivado。脚本只打开检查点读取，不综合、不布局布线、不写 bit、不连接板卡。输出必须为新文件。不指定 Pblock 时统计 device/occupied；指定时按实际 SLICEL/SLICEM 站点集合计算 SLICE 矩形区域的并集，输出 allowed/reserved/outside 与 IS_SOFT。

脚本不自动解释 DSP/BRAM 混合范围，也不验证 Pblock 成员是否覆盖全部目标逻辑；空区域或软约束不等于硬预留成功。器件/架构、完整 CLB、成员及约束语义按 [资源章节](resource-optimization.md) 另外核对。迁入时只执行了 Tcl 命令替身测试，未在本次运行 Vivado；旧技能的历史只读 Vivado 测试见 [原验证摘要](history/pynq-slice-compaction/validation.json)。

## PYNQ 只读状态快照

```text
python scripts/pynq_snapshot.py --out state.json --clock-id 0
```

此命令需在已获当前任务授权的目标板本地执行，使用该板已有 PYNQ 环境与权限。可重复指定 `--clock-id` 读取 0–3 的 FCLK；板卡/架构未暴露这些属性时记录未知和错误，而不猜频率。

脚本读取 boot ID、PYNQ 版本、现有 PL 位流记录、磁盘 bit/HWH 哈希和可见时钟。不下载 Overlay、不改频、不启动 DMA、不清缓存、不杀进程，也不自动 SSH、sudo 或扫描网络。

缺库、路径、权限或时钟不可见时返回部分观察结果和非零状态。PYNQ 元数据不能独立证明物理配置，磁盘文件哈希也不能证明当前加载内容。`overlay_pair_verified` 与 `dma_idle_verified` 固定为 false；由项目适配器核对实际硬件和完成语义。本次只用模拟 PYNQ 对象测试，没有连接板卡。

## 本次迁入验证

新增 12 项测试与原 24 项一起通过：已保存的 fc70 报告文本解析、错误时钟、负 hold、缺时序类别、非支持器件、工件/脚本被修改；模拟 PYNQ 的正常/缺时钟/缺 HWH；Tcl 替身的非连续站点计数、区域并集、区外占用与混合资源拒绝。报告测试使用明确标为合成的 DCP 字节验证哈希路径，不声称验证实际 DCP 内容。

运行 `python -B -m unittest discover -s tests -v`。Tcl 替身测试需要 Python 的 Tkinter/Tcl；未安装时标记跳过，其余测试可运行。PYNQ 模拟测试不需要安装 PYNQ。证据见 [consolidated_tests.log](../validation/consolidated_tests.txt) 与 [验证记录](../validation/report.md)。
