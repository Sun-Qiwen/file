# 资源方法的整合来源

本次将三份已有技能的方法去重改写为 [资源优化章节](resource-optimization.md)，核心文档可独立阅读，不要求安装原技能，也不依赖原工程盘符。源文件位置与本次读取的 SHA256 记录在 [resource_sources.json](evidence/resource_sources.json)。

|原技能|保留并提炼的内容|在新技能中的位置|
|---|---|---|
|amd-fpga-resource-audit|按实际层次定位；存储端口/生命周期、位宽、控制、AXI、资源交换；同阶段比较|资源章节 1–6、8–9|
|amd-fpga-slice-optimization|bank/row 映射与反馈证明；地址开销；控制集与 Slice 区别；测试平台未知值负例|资源章节 3、6、8|
|pynq-slice-compaction|状态保护、同映射点比较、真实 sites/Pblock、紧凑布局与全时序验收|资源章节 6–9|

去重时统一了以下边界：先按资源占用与实际根因选方法；局部证明通过后合并完整实现；硬件接口、并行度与数值限制以当前项目为准；历史 bank 数、频率、区域坐标、预留站点和百分比不成为通用限制。

原资源审计方法的 MIT 许可保留在 [resource_audit_license.txt](evidence/resource_audit_license.txt)，原紧凑布局方法的 MIT 许可保留在 [slice_case_license.txt](evidence/slice_case_license.txt)。原 `amd-fpga-slice-optimization` 交付目录未附独立许可，本次按用户要求提炼其提供的材料并保留来源，不宣称该原目录已获得新的开源许可。这些来源的许可均不自动覆盖原项目、模型或第三方 IP。

历史数值效果仍见 [来源、案例与验证边界](evidence.md) 及其冻结报告。新增资源章节整理方法与判据，本次没有执行资源优化、综合、布局布线或上板，没有新增资源降幅或跨板成功的声明。

原紧凑布局技能的 `check_reports.py`、`collect_sites.tcl` 和 `pynq_snapshot.py` 已逐字节迁入 `scripts/`，与 `evidence.py` 分工保留；用法和限制见 [资源与状态工具](resource-tools.md)。新工具测试覆盖保存的真实报告文本、合成 DCP 哈希、模拟 PYNQ 与 Tcl 命令替身，未新增硬件运行。

剩余有价值的历史案例、结果与原验证摘要见 [历史案例](legacy-cases.md)，赛事交付要求去重为 [交付对应](submission.md)。旧入口、重复正文、元数据及原始来源完整归档；逐文件去向见 [整合清单](evidence/consolidation_inventory.json)。综合技能无需依赖旧目录即可运行当前工具。
