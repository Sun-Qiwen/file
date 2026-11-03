# PYNQ 验证与性能优化技能包

面向使用 PYNQ 加载自定义 Overlay 的 FPGA 项目，提炼接口核验、数值回归、PS/PL 耗时分析、资源诊断与优化、A/B/A 验证的方法。资源部分整合三份既有技能，覆盖存储与 bank、位宽和算术、控制集、紧凑布局与拥塞处理。应用可为神经网络、滤波、图像或其他加速核；核心脚本不依赖其中任何一种模型。

## 从这里开始

给协作模型读取 [SKILL.md](SKILL.md)，然后提供项目当前报告、构建入口及允许的操作范围。需要按技能目录管理时，整个文件夹作为一个单元使用。`README.md` 用于参赛交付阅读，`SKILL.md` 保留技能入口；没有修改机器的全局技能配置。

推荐请求：

> 使用 pynq-verify-optimize，根据当前报告和源码查明 PYNQ 应用的主要延迟。冻结当前数值与接口规则，先做局部验证，再合并有证据支持的修改统一实现。只完成本地工作，不连接板卡；明确列出待实板验证内容。

综合实施提示词见 [assets/task-prompt.md](assets/task-prompt.md)，八类专项任务直接使用 [提示词工作流](prompts/README.md)，需要填写的报告见 [模板目录](assets/templates/README.md)。项目输入字段见 [assets/project-contract.json](assets/project-contract.json)。

## 包内内容

|材料|作用|
|---|---|
|[SKILL.md](SKILL.md)|协作模型的判断规则与操作流程|
|[运行约定](references/pynq-runtime.md)|Overlay 所有权、IP/register_map、缓存同步、超时与释放|
|[工作顺序、优化与故障定位](references/workflow.md)|先稳定目标精度/布局/接口，核对旧成果继承，再按收益筛选、局部验证和合并实现|
|[资源诊断与优化](references/resource-optimization.md)|实际原语归因、存储/位宽/控制优化、完整系统预算、物理实现与全时序验收|
|[资源方法来源](references/resource-sources.md)|三份旧技能的提炼映射、许可与验证边界|
|[工具说明](references/tools.md)|身份/数组/A/B/A 离线检查命令、输入格式、退出码和限制|
|[资源与状态工具](references/resource-tools.md)|保存的 Vivado 报告检查、DCP 真实站点统计、PYNQ 只读状态采集|
|[历史案例与失败经验](references/legacy-cases.md)|旧技能独有案例、测试平台负例、原验证摘要与运行故障处理|
|[八类专项提示词](prompts/README.md)|基线诊断、精度迁移、联合优化、资源优化、布线停止与恢复、集成、验收、交付归档|
|[六份文档模板与样本表](assets/templates/README.md)|诊断、继承矩阵、实验验收、资源实验、集成检查和交付清单；另附 CSV 字段表|
|[参赛对应](references/submission.md)|技能材料、复用证明、协作记录及工程交付的边界|
|[来源与效果](references/evidence.md)|从实际优化失败和验收中提炼的经验、验证范围|
|`scripts/evidence.py`|bit/HWH 指纹核验、NPY 黄金参考比较、CSV A/B/A 统计|
|`scripts/check_reports.py`、`collect_sites.tcl`、`pynq_snapshot.py`|从旧技能迁入的三个专用工具，保留原许可和适用范围|
|`tests/test_evidence.py`|输出错误、形状/类型、非法样本、漂移与身份改变等负例|
|`tests/test_resource_tools.py`|保存报告解析及篡改负例、模拟 PYNQ、Tcl 站点统计替身测试|
|[独立 HLS 案例](examples/vector_add_hls/README.md)|向量加法 C++ 核、参考/保护区测试平台、配置式 Tcl、原生编译校验；尚未综合或上板|
|`examples/run_demo.py`|向量加法的离线证据工具演示，性能与工件数据明确为合成|
|`validation/`|本次实际执行的检查结果与范围说明|

## 快速运行

需要 Python 3.9+；数组比较与测试另需 NumPy。文件指纹和 A/B/A 统计只用 Python 标准库。以下命令从技能包根目录执行：

```text
python -B examples/run_demo.py --out demo-output
python -B -m unittest discover -s tests -v
```

演示会建立新的输出目录，并运行身份/数组/A/B/A 三类检查；它不生成可上板 bitstream、不打开摄像头、不连接网络、不调用 Vivado。43 项测试在 `validation/tmp` 下建立并清理本次专用临时目录；资源与 HLS 流程测试使用保存的报告、合成 DCP、模拟 PYNQ 和 Tcl 命令替身。Tcl 测试需 Tkinter/Tcl，缺少时明确跳过。现有结果文件不覆盖。

需要实际 C++ 工程骨架时，按 [HLS 案例说明](examples/vector_add_hls/README.md) 先运行 `run_native.py`（需 GCC/Clang）。它检查 36 次原生调用和一个故意损坏输出的负例，不能替代 HLS 综合或 RTL 协仿。板卡 part、周期与系统集成留给目标工程配置。

## 复用方式与失效条件

换题目时，替换输入/参考函数、输出形状与数值规则、计时边界；换板卡时，额外替换器件与工具版本、时钟、兼容 bit/HWH、IP/寄存器和内存接口配置。保留相同的证据判定与离线工具。

通用性来自参数化和适配器分离，不意味着同一个 bit 可跨器件加载。AXI DMA 与 HLS `m_axi` 不是同一调用接口；未知控制协议、缓冲区所有权或完成语义时，先补齐适配器。新 PYNQ/器件架构的 API、时钟和资源解释须重新核对。

本包提供工作流、模板、故障清单、离线检查和限定范围的状态/站点采集工具，未实现任意 HWH 的自动驱动生成、完整通用 DMA 驱动或跨板硬件测试框架。实际 PYNQ 状态工具需要目标板环境，站点工具需要 Vivado；本次未执行两者的真实硬件/EDA 采集。已经完成什么、仍待证明什么，见 [验证记录](validation/report.md)。

## 参赛使用

本目录完整导入交付物的 `skill/pynq-verify-optimize/`，作为统一技能入口；独立副本和压缩包同步维护。三份旧技能的方法、独有工具、必要案例/许可已经整合，原目录移至交付目录之外归档。各项适用范围、使用方法、失败条件、实际提炼来源和效果均有入口链接；历史项目效果与本包工具的离线验证分别标记，不把脚本测试包装成新增实板成绩。
