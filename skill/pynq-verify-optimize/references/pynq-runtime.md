# PYNQ 运行与接口约定

## 先确认板上将运行的是什么

保存生成 bit/HWH 的构建 ID、源和约束摘要、工具/器件、文件 SHA256。相同文件名不能证明同源；两个哈希分别匹配也不能单独证明 bit/HWH 语义配对。需要同一构建导出记录，或接口保持不变且有证据支持的 HWH 复用记录。

按项目契约列出逻辑设备名称、HWH 中的层级 IP 名、预期 VLNV、地址范围、寄存器偏移/位宽/访问类型、控制协议与所有时钟。不要从另一块板照搬物理地址；也不要认为 HLS `ap_ctrl_hs`、`ap_ctrl_chain`、自由运行核和自定义控制核拥有相同启动/完成语义。

## 单一 Overlay 所有者

应用入口负责加载一次 Overlay，然后把同一个对象交给核、显示、GPIO 等驱动。PYNQ 中 Overlay 下载属于 FPGA 配置切换；另一个驱动内部重新构造并下载 Overlay，可能替换掉前一个完整设计。

有上板授权时，先确认当前任务的硬件状态及是否有冲突工作；遵循项目已经约定的切换与恢复方式。仅离线检查时，不为了“发现 IP”隐式下载。某些 PYNQ 版本支持 `Overlay(path, download=False)` 进行元数据加载；是否适用以及是否依赖设备环境应查看目标板的安装版本，不把它当通用离线 XML 解析器。

## ip_dict 与 register_map 的使用范式

加载/解析后的 `ip_dict` 用来发现实际 IP 及地址范围；驱动通常可通过 `register_map` 访问 HWH 描述的寄存器。先核对目标板对象实际提供的字段，再做访问。不要靠“对象有这个名称”就判接口正确，也不要假定所有自定义 RTL 都能生成完整 register_map。

```python
# 结构示意：overlay 由应用传入；这里只展示接口检查，不下载或启动设备。
def resolve_ip(overlay, ip_path):
    if ip_path not in overlay.ip_dict:
        raise RuntimeError(f"Required IP missing: {ip_path}")
    # 接下来由项目适配器核对 phys_addr/addr_range、VLNV 和 registers。
    # 层级 IP 的对象解析由目标 PYNQ 版本/适配器负责，不猜通用 getattr 路径。
    return overlay.ip_dict[ip_path]
```

将 `configure()`、`start()`、`wait_complete()`、`read_outputs()` 和 `quiesce()` 留给明确控制协议的适配器。寄存器名、启动值、done/idle 位、clear-on-read、写一清零、64 位地址的高低寄存器顺序，都来自实际 IP 契约。缺失 register_map 时按已验证寄存器表使用 MMIO，而不是试探写入。

## 内存与缓存生命周期

典型的缓存型 PS/PL 共享缓冲区流程为：分配设备可访问内存 → CPU 写入 → 向设备同步 → 配置设备地址/长度 → 启动 → 等待完整完成 → 从设备同步 → CPU 读取 → 确认没有硬件访问后释放。PYNQ 中常见方法是 `flush`/`invalidate` 或 `sync_to_device`/`sync_from_device`；项目适配器根据目标版本与缓冲区一致性属性选择。

- NumPy 普通虚拟地址不能直接当设备物理地址；使用分配对象提供的设备地址，并检查 IP 地址位宽。
- 同一缓冲区原地读写时，先核对别名合法性与所有权。连续/非连续切片、对齐、长度和尾部字节不能靠 dtype 推断。
- 超时表示“主机没有按时观察到完成”，不能推出“硬件已停止”。最终写事务或 DMA 仍在进行时，释放 CMA 或让进程异常退出可能使硬件访问被重新分配的内存。
- 超时路径先保存状态和诊断，按已验证的排空/停止/复位协议解除访问，再释放。无法证明 idle 时保持所有者与缓冲区存活，并报告仍在运行；不是仅仅跳过一次 `free` 就足够。

## DMA 与 m_axi 分开适配

若设计有 AXI DMA，分别核对 MM2S/S2MM、长度限制、DRE/对齐、通道状态、错误位和流式包边界。收发启动顺序取决于数据流与背压关系，不能把固定顺序强加给所有设计。缺少预期 TLAST、长度不符等是流式接收等待的候选原因，需要用状态/波形确认。

若核通过 HLS `m_axi` 主动访问 DDR，主机配置的是核的地址/参数/控制寄存器，不应套用 AXI DMA 的 `sendchannel`/`recvchannel` 调用。核 done 是否包含所有 outstanding 写响应必须由实现和测试证明。

## 版本资料

优先看目标板安装的 PYNQ 包、匹配版本文档和实际 HWH。官方资料入口（本次网络读取失败，未将在线内容列为新验证证据）：

- [PYNQ 内存分配](https://pynq.readthedocs.io/en/latest/pynq_libraries/allocate.html)
- [Overlay 教程](https://pynq.readthedocs.io/en/latest/overlay_design_methodology/overlay_tutorial.html)
- [DMA 文档](https://pynq.readthedocs.io/en/latest/pynq_libraries/dma.html)

本包没有新增实板 API 兼容性验证；上述范式需由目标版本适配器落实。
