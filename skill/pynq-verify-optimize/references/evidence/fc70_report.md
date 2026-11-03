# jn69 PS v2 基线五项开销联合验收


候选完整 Pipeline 直接实测均值 **899.991 ms**，中位数 **897.597 ms**。同 boot、100 MHz、CPU 650 MHz 的 A/B/A 均值为 1238.342/899.991/1230.935 ms；相对两次A均值省 334.647 ms（27.10%），相对更快A省 330.944 ms（26.89%）。中位数相对两A中位数均值省 334.460 ms，相对更快A中位数省 333.366 ms。

候选均值距1000 ms为 -100.009 ms，距665 ms为 +234.991 ms；10次有效样本中 10 次低于1000 ms。历史正式基线直接Pipeline均值为 1239.740 ms。目标按完整run_frame直接调用判断，不拼接独立最快阶段，也不通过抬高A来判断665 ms。

本候选同次调用硬件均值805.406 ms，核外94.585 ms。仅把核外降为零，现硬件调度仍比665 ms高140.406 ms，因此PS单项不足以达到665；还需要减少或重叠硬件开销。这只限定当前实现，未验证双缓冲重叠等剩余方向，不能据此宣称整个方向没有空间。

以下每项的状态1只对应已采用的具体实现。状态2为实际验证收益不足或代价不可接受；状态3为定量排除的具体方案；状态4为尚未充分验证的剩余方向。一个被拒绝分支不代表整个方向没有空间。

| 开销 | 历史正式基线ms与主因 | 实际尝试及局部结果 | 采用和拒绝依据 | 本轮两A均值 → B | 状态及未解决部分 |
| --- | --- | --- | --- | --- | --- |
| 两网 input/load/unpack | 230.861；短请求和反复 unpack；首层及超过容量的层仍走安全回退。 | 沿用128KiB缓存整图packed input；cb32→64、k3 tap复用、DW九tap预装；unpack II1/d12、MAC II1/d9。input helper339936→210691，HP0 max16请求379398→279314；raw word只少31200。 | 采用去重复工作及XC以32个TDP BRAM换LUTRAM；拒绝direct路径MAC d17及对齐共享unpack II2（后者预算净慢54.319ms）。 | 229.815 → 156.125；保守省 73.458ms | 1 已实现并通过最终验收；仍保留输入读2660448 word和不适用层；共享对齐/更大重叠方向未充分验证。 |
| 两网 requant 加 store | 234.812；原4路完整Q30量化；短行写回、读改写与helper开销。 | 8路原标量量化，显式偶奇bank单写：40→22拍/block，预算省24.134ms；共享32KiB row缓存、单store实例。写请求338320→187849，RMW55194→10574，输出15687336字节不变。 | 采用精确8路和末stripe后排空；quant01 II2已修复；缺末stripe守卫的旧分支因288次非法内部读被排除。7376块/130199写、53978 Q30及26实际RTL通过。 | 234.605 → 137.094；保守省 97.447ms | 1 已实现并通过最终验收；仍需精确算术、有效输出搬运和10574次RMW；继续隐藏等待或扩大缓存未充分验证。 |
| 两网 control other | 127.269；helper启动、外层循环、初始化及各engine命令调度。 | MAC helper683544→316284、unpack491604→137844、store35331→21979。22可比层含init的控制214782→116265拍（14改善/8退化）；没有将定向mix外推全网。 | 采用cb64、tap/DW复用、共享排空减少调度；拒绝mac_child II2，额外214.335ms大于最多13.018ms drain收益。局部归因与input/store重叠，仅整帧计一次。 | 127.253 → 91.815；保守省 35.435ms | 1 已实现并通过最终验收；ROM126初始化134076次、outputblock设置35331次、stripe6807次及其他engine控制仍在；完整FSM或更多重叠方向未充分验证。 |
| YOLOX EW | 97.957；Add/requantConcat每字节串行映射与小块调用。 | 双字节双端口表、64-word块；4104B Add14308→6847拍、requant12324→5200、identity3791→2879；173 native、86实际RTL通过。 | 采用同级HLS LUT−537/FF−243、BRAM/DSP不增的实现；原回退、别名、-128及独立舍入语义保留。局部加权47.52ms仅作预算。 | 97.786 → 43.178；保守省 54.565ms | 1 已实现并通过最终验收；查表初始化、内存搬运、Sigmoid和回退仍在；改变算术或融合跨命令未充分验证。 |
| 两核硬件外完整 Pipeline | 141.811；含PS预处理、copy/sync、协议检查、解码和完整输出。 | 私有resize canvas原位cv2.LUT加mixChannels直接NCHW；ARM PS专项1+10 A/B/A均值70.728/24.424/67.452ms，较快A省43.028ms；21测试及全字节/stride/ownership检查通过。 | 采用逐字节相等映射；完整Pipeline保留检查、sync、诊断和输出；没有把独立函数节省直接当整帧收益。 | 138.579 → 94.585；保守省 40.679ms | 1 已实现并通过最终验收；其余CPU解码、裁剪、输出读取和协议开销仍在；未归因主机延迟保留，其他CPU重构未充分验证。 |

主要被拒绝或修复的具体分支保留如下，状态不替代上表五项的合并结论。

| 状态 | 具体分支 | 实测或定量依据 | 结论 |
| --- | --- | --- | --- |
| 2 | direct packed→MAC系列 | 显式bank修复II2后MAC仍d17（原d9）；bank_dw01的22实际RTL中17快/5慢，k1约慢3–6%；gather01同级HLS conv资源51687 LUT/32410 FF。 | 不同快照分别保留证明，采用MAC d9的packed/tap/TDP替代；不外推为整个直接供数方向不可能。 |
| 3 | shared alignment | 同级LUT−1249/FF−647，但unpack II2/d13；精确ROM忙时预算净慢54.319ms。 | 定量排除该实现，未浪费实际RTL或完整物理尝试。 |
| 3 | mac child | HLS II2在原21433536事件槽上额外214.335ms，超过最多13.018ms可减drain。 | 排除该具体child调度，不修改64MAC数量。 |
| 3 | packed01 | 动态bank寻址使unpack II3/d15，净忙时预算退84.26ms。 | 只修read-base外提，packed02恢复II1/d12；失败记录保留。 |
| 2 → 1 | quant01 → quant02 | 相邻双word写导致HLS II2/d8且仅4乘法器；仅40→38拍。显式LSB分bank后II1/d7、8完整乘法器，40→22拍。 | 采用已通过最终回归/物理/板测的quant02。 |
| 3 | 缺末stripe守卫的shared01 | ci321/co9/h3/w127/s2局部所有权检查捕获288次未初始化或已释放读取，尽管最终arena相同。 | 排除错误源；最终加入xs+count==ow守卫并实际RTL验证288产消/2drain。 |

五项本轮比较全部来自同一批直接Pipeline调用。保守收益为各项更快一次A的mean减B，不能把各项各自选择的A收益相加。全帧的硬件/核外分解统一使用整帧更快A：{"pipeline_wall_ms": 330.9440466, "pipeline_hardware_ms": 290.26456600000006, "pipeline_outside_hardware_ms": 40.67948060000003}。阶段忙时可能相交，未将AXI等待或重叠再次加到总硬件历时。

MAC事件槽数保持 YOLOX 16620480、CNN 4813056，共21433536。cb64/DW预装还减少计算helper排空，必须将其实际compute阶段变化与五项分开说明：{"parent": 269.01888, "candidate": 239.63808, "parent_retest": 269.01888} ms。这不增加卷积MAC数量。

同一批完整Pipeline的全部命名硬件阶段均值如下，单位ms。各组阶段总和减实际overlap与同组硬件历时一致；输入/写回/控制联合改动只通过最终整帧差计一次。

| 硬件阶段 | A | B | A复测 | 两A均值省ms |
| --- | --- | --- | --- | --- |
| input_load_and_unpack | 230.048 | 156.125 | 229.583 | 73.691 |
| compute | 269.019 | 239.638 | 269.019 | 29.381 |
| requant | 53.630 | 29.497 | 53.630 | 24.134 |
| store | 181.038 | 107.597 | 180.910 | 73.377 |
| weight_load | 19.589 | 19.564 | 19.560 | 0.010 |
| control_other | 127.256 | 91.815 | 127.250 | 35.438 |
| elementwise | 97.828 | 43.178 | 97.743 | 54.608 |
| spatial | 44.783 | 44.745 | 44.731 | 0.012 |
| input_quant | 21.920 | 21.917 | 21.914 | 0.000 |
| groupnorm | 24.789 | 24.789 | 24.788 | -0.000 |
| pool | 5.465 | 5.467 | 5.466 | -0.001 |
| upconcat | 11.594 | 11.591 | 11.591 | 0.001 |
| valid_head | 6.489 | 6.489 | 6.489 | 0.000 |
| heat_dequant | 3.000 | 2.996 | 2.996 | 0.002 |
| 实际overlap 扣除 | 0.000 | 0.000 | 0.000 | 不重复扣减 |

## 原始样本统计


每个场景、每个A/B/A组均1次预热加10次有效。下面std为总体标准差，单位ms；所有有效慢样本均保留。

| 场景与组 | mean | median | min | max | std |
| --- | --- | --- | --- | --- | --- |
| 完整Pipeline wall A | 1238.342 | 1233.152 | 1230.024 | 1275.798 | 12.864 |
| 完整Pipeline wall B | 899.991 | 897.597 | 896.295 | 919.251 | 6.610 |
| 完整Pipeline wall A复测 | 1230.935 | 1230.963 | 1229.190 | 1232.776 | 1.304 |
| YOLOX硬件 A | 895.744 | 895.685 | 895.656 | 896.068 | 0.127 |
| YOLOX硬件 B | 629.196 | 629.072 | 629.031 | 629.759 | 0.232 |
| YOLOX硬件 A复测 | 896.121 | 895.524 | 895.438 | 899.194 | 1.133 |
| CNN硬件 A | 200.514 | 200.285 | 200.275 | 201.511 | 0.443 |
| CNN硬件 B | 176.349 | 176.153 | 176.142 | 177.064 | 0.317 |
| CNN硬件 A复测 | 200.316 | 200.233 | 200.216 | 201.003 | 0.231 |

候选Pipeline全部10个有效wall样本（ms）：896.585, 896.903, 900.179, 896.429, 919.251, 901.069, 898.328, 898.292, 896.295, 896.581。各网络host start/done、copy/sync/output、代表层、阶段忙时和全部样本见 [完整统计](D:/FPGA_learning/gesture_amd_yolo_ps_cnn_pl_classified_20261022/sim/runs/five_cost_20261102_01/board_flow/performance_b01.json)；逐调用原始数据见 [samples.jsonl](D:/FPGA_learning/gesture_amd_yolo_ps_cnn_pl_classified_20261022/sim/runs/five_cost_20261102_01/board_flow/fetch_b01_01/retained/results/samples.jsonl)。主机未划分长延迟不推测为OS原因，也不解释成稳定代码收益。

完整Pipeline内的PS函数探针均值如下（ms）。函数可能嵌套，不能把各项相加或再加到核外总量；零表示该调用中未记录此函数。

| PS函数 | A | B | A复测 |
| --- | --- | --- | --- |
| prepare_input | 0.000 | 0.000 | 0.000 |
| prepare_input_int8 | 68.422 | 26.078 | 67.201 |
| decode_heads | 4.463 | 4.285 | 4.288 |
| map_boxes | 1.217 | 1.179 | 1.165 |
| prepare_crop | 11.589 | 10.619 | 10.572 |
| decode_heatmaps | 2.377 | 2.294 | 2.280 |

## 资源 时序和回归


| routed指标 | jn69正式基线 | 联合候选 |
| --- | --- | --- |
| slice | 13197.0 | 13217.0 |
| lut | 42328.0 | 42782.0 |
| ff | 44810.0 | 44170.0 |
| dsp | 186.0 | 212.0 |
| bram | 94.5 | 117.5 |
| wns | 0.312 | 0.151 |
| whs | 0.014 | 0.01 |

完整综合DSP层级实际增量为：量化+16、unpack+4、卷积其他helper+6，其他模块不增，共186→212。MAC叶内总DSP65保持，其中真正的int8乘法产品64保持；新增量化DSP不计作卷积MAC。原始层级网表及核对记录见 [DSP实际增量](D:/FPGA_learning/gesture_amd_yolo_ps_cnn_pl_classified_20261022/sim/runs/five_cost_20261102_01/resource_breakdown.json)。

器件 xc7z020clg400-1，时钟周期10ns。13217/13300个真实Slice站点，reserved=0，原已放开的900站点没有重复计入。TNS/THS=0.0/0.0，route errors/DRC errors=0/0；check_timing全部零。1次本轮完整物理尝试：[{"path": "D:\\FPGA_learning\\gesture_amd_yolo_ps_cnn_pl_classified_20261022\\build\\fc70\\final\\i01\\inputs.json", "reason": "first unified final candidate", "number": 1}]。局部HLS及checker尝试不冒充完整物理尝试。

实际网表和生成RTL均证明单套共享64个int8卷积MAC及原串行CNN math；量化8路为原完整int32乘unsigned32到int64的Q30算术，不能将总DSP数当成MAC数。完整系统unpack/MAC/quant/store为II1，深度12/9/7/4；quant实际32 DSP、8个完整乘法实例。

最终native：233严格记录、224计数检查、90CNN、50EW、27整arena、9Pipeline、37长尾含19valid-flip。原YOLOX三个整数头精确，CNN原参考/容差、变输入、Y→C→Y、保护区/别名/回退/无reset通过。新conv26及EW86实际生成RTL覆盖背压、4KiB、事务排空和所有权；没有跑全网长RTL。最终板测审计：{"rows": 563, "per_command_cases": 90, "full_arena_snapshots": 27}。

局部conv最初4次失败来自检查器把无消费者的RAM伴随CE当成实际消费或未对齐采样时刻，源码/golden/HEX未变，失败日志全部保留。最终消费由生成RTL真实state和mux确定，物理读=消费+未选读；独立审阅确认没有使用期望owner掩码过滤非法消费。case25实际8448产消、max8191，ci321跨stripe为288产消/2drain。EW原证据链补齐666文件绑定、native463、conv656，原Important已复核关闭。

局部方案与定量排除详见 [conv报告](D:/FPGA_learning/gesture_amd_yolo_ps_cnn_pl_classified_20261022/sim/runs/five_cost_20261102_01/packed/postseal_report.md)、[control分类边界](D:/FPGA_learning/gesture_amd_yolo_ps_cnn_pl_classified_20261022/sim/runs/five_cost_20261102_01/packed/postseal_boundary_v2.md)、[EW报告](D:/FPGA_learning/gesture_amd_yolo_ps_cnn_pl_classified_20261022/sim/runs/five_cost_20261102_01/ew/report.md)、[PS报告](D:/FPGA_learning/gesture_amd_yolo_ps_cnn_pl_classified_20261022/sim/runs/five_cost_20261102_01/ps/report.md)；源冻结/RTL/native/物理/板测审阅在 [独立审阅目录](D:/FPGA_learning/gesture_amd_yolo_ps_cnn_pl_classified_20261022/sim/runs/five_cost_20261102_01/final_review)。

## 交付和恢复


原正式jn69可恢复记录 [原accepted.json](D:/FPGA_learning/gesture_amd_yolo_ps_cnn_pl_classified_20261022/sim/runs/joint_perf_20261102_01/accepted.json)，当前SHA b34fb17d6ef58f7dd70f7618da25bec71d2325477e497eeb03f4c5b7e8f09960；原源码、PS、bit/HWH/DCP仍逐SHA匹配。候选源码 [13源身份清单](D:/FPGA_learning/gesture_amd_yolo_ps_cnn_pl_classified_20261022/sim/runs/five_cost_20261102_01/final_source_identity.json)（build/fc70/source_snapshot），PS [PS候选](D:/FPGA_learning/gesture_amd_yolo_ps_cnn_pl_classified_20261022/build/fc70/ps_candidate/yolox_numpy.py)；[bit](D:/FPGA_learning/gesture_amd_yolo_ps_cnn_pl_classified_20261022/build/fc70/final/e01/yolox_int8.bit) 和 [HWH](D:/FPGA_learning/gesture_amd_yolo_ps_cnn_pl_classified_20261022/build/fc70/final/e01/yolox_int8.hwh)。

bit SHA256 `0f2ef507241d5c0f3b83f413b3eaace4aaca670a7e86953007ebf216f8f2c4e5`；HWH SHA256 `2131d89ef0ae543dfce1c887cdcfcd12c78f8e26da89cd5809062b3d89adc261`；routed DCP SHA256 `aad52b1a13f1ab551741aa42c679f90fa9e7fc770f0b1e946f157ecc5b13c6f4`。完整物理证据 [assessment.json](D:/FPGA_learning/gesture_amd_yolo_ps_cnn_pl_classified_20261022/build/fc70/final/i01/assessment.json)，最终门禁 [final_gates.json](D:/FPGA_learning/gesture_amd_yolo_ps_cnn_pl_classified_20261022/sim/runs/five_cost_20261102_01/final_gates.json)，板测审计 [board_audit_b01.json](D:/FPGA_learning/gesture_amd_yolo_ps_cnn_pl_classified_20261022/sim/runs/five_cost_20261102_01/board_flow/board_audit_b01.json)。

测试后同boot恢复 /home/xilinx/joint_perf_20261101_01_b02/restore/gesture_system.bit，bit/HWH SHA与开测前相同，FCLK=62.5 MHz、CPU=650.0 MHz，active_workloads为空。候选保留为独立版本，实时默认版本未替换。恢复记录 [restored.json](D:/FPGA_learning/gesture_amd_yolo_ps_cnn_pl_classified_20261022/sim/runs/five_cost_20261102_01/board_flow/fetch_b01_01/retained/results/restored.json) 与 [开测后实读状态](D:/FPGA_learning/gesture_amd_yolo_ps_cnn_pl_classified_20261022/sim/runs/five_cost_20261102_01/board_flow/postcheck_01.json)。参数、输入、参考、旧板测大数据通过既有路径或symlink复用，没有复制大型历史目录或做无关清理。
