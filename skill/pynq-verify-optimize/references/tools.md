# 离线工具与数据格式

本页说明 `evidence.py` 的三类检查。迁入的 Vivado 报告检查、真实站点和 PYNQ 状态工具见 [资源与状态工具](resource-tools.md)。

`scripts/evidence.py` 读取本地文件并输出新的 JSON；不连接 PYNQ、不加载 bit、不修改输入文件、不调用 EDA。各命令共有 `--out NEW.json`，父目录须已存在，拒绝覆盖现有输出。

退出码：0 表示该工具范围内的检查通过；1 表示已发现不一致/漂移/错误输出；2 表示输入格式、依赖、读取或写入错误。0 不代表功能完整、已上板或最终验收通过。

## 黄金参考比较

```text
python scripts/evidence.py compare reference.npy actual.npy --mode exact --out compare.json
python scripts/evidence.py compare reference.npy actual.npy --mode float --atol 0.000001 --rtol 0.00001 --out compare-float.json
```

需要 NumPy。仅接受单个 NPY 数组，关闭 pickle。shape 和 dtype 必须相同，不广播、不自动量化、不截断到共同长度。支持布尔、整数、实数浮点；拒绝空输出、NaN/Inf 和不支持的数据类型。

`exact` 逐元素值相等，整数比较不经过浮点转换；浮点 ±0 视为相等，不是位级浮点编码比较。`float` 只用于浮点数组，规则为 `abs(actual - reference) <= atol + rtol * abs(reference)`；容差从原项目契约确定，不能为使候选通过而放宽。中间算术溢出会报输入/计算错误，不用 Inf 比较得出通过。

示例容差不是任何网络的默认门槛。多个输出头分别运行；全部必要输出都通过才构成该样本的正确性结果。混合精度系统按输出分别选规则。

输出绑定两个输入文件 SHA256，并提供元素数量、不一致数量、首个错误索引和值；它不证明输入是从指定板上工件采集，采集来源由实验记录绑定。

## A/B/A 数据统计

```text
python scripts/evidence.py aba samples.csv --drift-pct 5 --out performance.json
```

只需要 Python 标准库。CSV 必需列如下：

|列|含义|
|---|---|
|case|同一输入与参考下的测试场景|
|group|A1、B、A2；每个场景按此顺序连续分组|
|iteration|组内唯一的非负整数；采样顺序以 CSV 行为准|
|warmup|1 为预热，0 为正式样本；预热排在该组正式样本之前|
|correct|1 或 0；由外部正确性比对产生，不由时间推断|
|elapsed_ms|严格正有限数，单位毫秒|
|run_id|本轮实验 ID|
|environment_id|实际器件/时钟/软件环境记录的身份标识|
|artifact_id|软件与硬件共同身份，例如完整构建清单 SHA；A1/A2 必须相同|
|timing_boundary|相同起止边界的名称|
|input_id、reference_id|输入和参考身份|

建议用可追溯文件哈希作身份字段，并在实验记录中绑定 boot、实际频率、温度/负载等有影响的条件。工具只比较声明值相同，不证明声明是真实测量；环境变化时不能靠填相同字符串“修复”结果。

每个场景每组至少一条正式样本；少于 10 条会提示样本不足，10 也不是长期稳定性的证明。每组全部正式样本进入统计，无异常值删除；预热保留数量且不计入耗时分布。任何行标记错误结果，都使数据检查失败，包括预热。

按组给出 n/mean/median/min/max/总体 std 和 nearest-rank P95。小样本 P95 很不稳定，不应当作服务等级指标。按组均值计算：

- 两 A 平均收益：`(mean(A1)+mean(A2))/2 - mean(B)`。
- 保守收益：`min(mean(A1),mean(A2)) - mean(B)`；负值照常报告。
- 漂移：`abs(mean(A1)-mean(A2))/min(mean(A1),mean(A2)) × 100%`。

5% 只是工具默认漂移阈值；应按项目噪声和验收契约选择。超过阈值仍保存统计，但退出 1。工具不会因为候选变慢而删除结果；退出 0 也不意味着加速成立。不同场景独立统计，不拼成一帧、不相加阶段收益。多个身份不同的输入请使用不同 case。

## 工件身份核验

```text
python scripts/evidence.py artifacts contract.json --out artifacts.json
python scripts/evidence.py artifacts contract.json --root /path/to/artifacts --out artifacts.json
```

契约最低结构：

```json
{
  "build_id": "my-build-001",
  "artifacts": {
    "bit": {"path": "design.bit", "sha256": "填写文件实际的64位十六进制SHA256"},
    "hwh": {"path": "design.hwh", "sha256": "填写文件实际的64位十六进制SHA256"}
  }
}
```

相对路径默认从契约文件所在目录解析，`--root` 可替换根目录；也允许明确绝对路径。上述文字是格式说明，直接运行会因缺少真实哈希而失败。

脚本流式计算文件哈希，不解析 HWH、不读取板卡寄存器、不证明来源声明或接口等价。因此输出固定包含 `semantic_pairing: not_proven` 和 `board_verified_by_this_tool: false`。核验接口、地址、寄存器、时钟及加载后硬件状态仍由项目适配器完成。

## 输出解释

保留工具 JSON、原始输入和实验记录。JSON 的 SHA 绑定读取的文件，无法替代受控采集流程。并发写入中的文件不适合作为证据输入；先冻结样本和工件再运行。

`examples/run_demo.py` 展示三个命令的离线串联，并用损坏输出演示退出 1。示例 CSV 和工件是人为构造，只证明脚本可运行和判定规则，不能用来报告硬件性能。
