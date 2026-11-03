# 已验证案例与提炼依据

本文件提供本队工程证据，主技能不依赖这些工程路径。将技能目录复制到另一题目后，按相同方法重新取得自己的数据。环境：XC7Z020CLG400-1、Vivado/Vitis 2025.2、100MHz。

## 1. 非 2 的幂 bank 的地址开销

观察：HLS 为 5 个并行输入读取自动推断 cyclic5；实际生成 RTL 中出现宽余5/商计算，综合层次确认地址路径开销。

处理：在原 16384×64bit 容量上显式 cyclic8，证明合法地址映射为 `(index%8,index/8)`，任意5个连续字落入不同bank，保留有符号边界判断。不是把源程序的 `%5` 直接替换为 `&7`。

完整设计同阶段综合 ci04→cb81：LUT 50515→46935，FF 62798→57928，DSP 176→159，BRAM Tile 66→60.5。8-bank 不一定比更少 bank 浪费 BRAM；本例因深度与原语分配反而下降，但不能外推到别的容量/器件。

证据入口（工程根目录相对路径）：`report/runs/cache_banks_20261030_01/report.md`、`sim/runs/cache_banks_20261030_01/address_proof.md`。旧报告的策略标签有误：本轮复核 cb81 的实际引擎/顶层 `synth_design` 日志未含 AreaOptimized directive；复现按实际命令，不按旧文案标签。旧顶层测试高地址范围的限制见第5节。

## 2. 逻辑容量与真实寄存器副本

`int32_t sums[8][16]` 的容量是4096bit＝512B。冻结网表实际存在12288个 sums 前缀FF，分属 fu 状态、load 暂存、其他寄存器三族；这不是4096B，也不能仅按名字认定所有副本均可直接合并。

适配原每拍8个输出lane×4个像素lane的访问：输出维完全分区，像素维cyclic4，形成32个bank，每bank4个int32。映射 `bank=4*o+(pixel%4)`、`row=pixel/4`。初始化按4个pg循环，每拍32bank各写一个值；MAC同样每bank各读改写一个值，同row反馈间隔4次迭代。

```cpp
int32_t sums[8][16];
#pragma HLS ARRAY_PARTITION variable=sums complete dim=1
#pragma HLS ARRAY_PARTITION variable=sums cyclic factor=4 dim=2
#pragma HLS BIND_STORAGE variable=sums type=ram_s2p impl=lutram
init_sums_groups: for (int pg=0; pg<4; ++pg) {
#pragma HLS PIPELINE II=1
    for (int o=0; o<8; ++o) {
#pragma HLS UNROLL
        for (int p=0; p<4; ++p) {
#pragma HLS UNROLL
            sums[o][pg*4+p]=0;
        }
    }
}
```

适用前提：消费循环也满足上述端口与反馈访问规律。单独复制这段 pragma/初始化不能保证另一算法满足 II。

实际结果：32个4×32bit分布式RAM，MAC II1/depth11保留，32个整数MAC DSP保留。顶层完整字寄存器声明384→32，该声明数与最终物理FF数不同。cb81→sb41同默认综合命令、同阶段：

|资源|cb81|sb41|减少|
|---|---:|---:|---:|
|LUT|46935|38875|8060（17.17%）|
|FF|57928|42555|15373（26.54%）|
|DSP|159|159|0|
|BRAM Tile|60.5|60.5|0|

证据：`report/runs/xc_control_20261030_01/resource_breakdown.json`、`sim/runs/sums_banks_20261031_01/synthesis_comparison.json`、`hls_verified.json`及该实验下源码/测试记录。

## 3. 控制集下降不等于 Slice 下降

冻结cb81网表的xc有4096个FF、512种控制组合。已证明为同步复位且 `R=CE&&invalid`，可将 `R?0:CE?D:Q` 改写为 `CE?(invalid?0:D):Q`，保留CE/时钟/INIT与逐拍状态。共享掩码减少组合逻辑和控制集。

实际默认布局单独做该ECO仍占13299Slice；增加对应网表的紧凑布局后才得到13000Slice。因此299Slice收益包含ECO与布局。旧ECO配方绑定旧DCP，源码重新综合不会自动带上，也不能用到异步复位或另一网表。

## 4. 默认布局没有兑现全部面积收益

新sums源码默认place：13244Slice，虽然LUT/FF已明显减少，但未超过此前最佳13000Slice，被门禁挡在route前。对同新综合DCP建立本轮hard pblock，实际区域11800Slice，随后完整route得到：

|完整布线结果|cb81|此前最佳xcr1|新sums＋新紧凑布局sb41|
|---|---:|---:|---:|
|Slice / 13300|13299|13000|11766|
|LUT|45164|44834|36654|
|FF|57160|57154|41718|
|控制集|1336|856|1315|
|DSP|159|159|159|
|BRAM Tile|60.5|60.5|60.5|

相对此前最佳减少1234Slice（9.49%），空余300→1534。新版本未套用旧xc ECO，控制集高于xcr1；上表是整体方案对比，源码独立贡献看第2节综合表。

最终100MHz WNS +0.173ns、WHS +0.025ns，12项约束检查全0，76199/76199网络布通，DRC无Error/Critical Warning，保留217 Warning/8 Advisory。

证据：`build/sb41/i02/assessment.json`、`build/sb41/e02/artifacts.json`、`report/runs/sums_banks_20261031_01/report.md`及`review.md`。bit SHA256：`92755b16d8a6c40402c641e24f85ccd4ebf3421796e0182190de467bfa6b95e5`；HWH SHA256：`da5f6102978318b642450e9bfaba9ccfac0b5bfa3c2e83e9c3452efa6b1c5eaf`。

## 5. 验证平台自身也会误通过

发现：继承的统一顶层测试仅声明384000-word参考数组，却访问709896 words，高地址可能出现X对X仍“相等”。旧top01证明已撤销；修复容量并拒绝实际/期望未知值后，top02的6次交错调用通过；在最高保护字同时向actual/expected注入X，必须命中UNKNOWN_ARENA。XSim遇SV fatal仍可能返回0，因此检查实际拒绝标记与PASS缺失。

有效功能证据：166组有效native（含全部126条当前卷积命令）、14类非法输入、整模型native；20次独立conv RTL与修正后的6次顶层调用。不是整网RTL长程验证。与父版相同20组fixture的总周期770875→763327（-0.98%），不能写成板端FPS提升。

这些观察及修复轨迹来自实验的progress、review与失败日志；本文件是提炼摘要，不是原始大模型对话的逐字导出。参赛还应保存对应真实提示词、模型回答及自我纠错记录。

## 迁移边界

本次sb41未上板。未验证另一板卡/工具版本、另一模型的bank参数和区域坐标，也未证明跨板性能不变。迁移的是定位、证明、分阶段验证与诚实归因的方法；512B、32bank、100MHz、13300Slice及区域预留量均须按新工程重算。
