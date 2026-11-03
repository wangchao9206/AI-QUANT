# CZSC 与 chan.py 初步研究（2026-10-31）

研究结论：如果下一步要把原文中的分型、笔、特征序列线段、中枢和买卖点画清楚，优先评估 chan.py 的公开结构计算代码；如果下一步要做多周期信号组合、批量研究和统计报告，优先评估 CZSC。现有燃油研究规则与两个库的默认定义不同，应作为三个具名版本并排比较。执行与期货账本继续使用 AI-QUANT 已有的真实交割合约、费用和移仓模型。

这是一轮源码审阅与结构状态实验，未运行收益策略、参数寻优、实盘或网络行情采集。它不能证明任一框架有交易优势，也不是对两个项目全部功能的审计。

## 固定版本与研究方式

| 对象 | 审阅/运行版本 | 说明 |
|---|---|---|
| CZSC 源码 | `5d350a943d6b1935561765fed5467c234973d121` | Apache-2.0；当前 1.0 系列已采用 Rust 核心与 Python 接口 |
| CZSC 运行包 | PyPI `czsc==1.0.2`、`wbt==0.9.2` | Windows x64、Python 3.11.9 独立虚拟环境；源码提交与发布 wheel 分开记录，不声称逐字相同 |
| chan.py 源码与运行 | `f8ca3b5e44d7166e2abd756a8e7fa816c79faebe` | MIT；直接加载固定 checkout 中的公开计算模块 |
| 输入 | 现有 FU 冻结快照，2019-01-02—2026-10-27，1,894 根日线、33 次换月 | SHA-256 与路径在 `data/czsc-chanpy-2026-10-31/structure-probe.json` |

两者使用相同 OHLCV 输入：用快照中已观察到的新旧合约开盘比价，沿时间向前串联价格，保留过去价格，不用未来换月价格重新调整历史。核对原始时区为 UTC+8 后，适配为库接受的无时区时间。日线时间在本实验中是交易日标签，确认滞后按观测序号计，不解释为盘中可交易的具体时刻。

输入没有真实成交额，CZSC 的 `amount=0` 仅作为缺失占位；本实验只研究价格结构，不运行依赖成交额的信号。未生成或填补行情。

## 实际能力与边界

| 方面 | CZSC | chan.py |
|---|---|---|
| 结构实现 | `CZSC`、`FX`、`BI`、`ZS`；当前核心的 `zs_list` 由 `finished_bis` 构造 | 分型、笔、特征序列线段、线段的线段、中枢及分类买卖点分别实现 |
| 规则配置 | 典型核心参数如 `min_bi_len`、`max_bi_num`，另有信号体系 | 笔严格性、分型检查、缺口成笔、线段算法、中枢合并、买卖点条件等有独立配置 |
| 多周期 | `BarGenerator`、`CzscSignals`、`CzscTrader` | `CChan` 及级别间 K 线关联，`trigger_load` 可增量喂数据 |
| 研究框架 | 信号—事件—持仓体系；`run_research`、`run_replay`；权重回测依赖独立项目 `wbt` | 公开代码含计算模块和简化策略演示；README 的完整模型、AutoML、交易引擎等不能视为全部可用 |
| 工程接入 | 当前源码构建需要 Rust/maturin；PyPI 有 Windows 与 Linux amd64 wheel | 公开核心可直接以 Python 运行，但采用 `Bi`、`Common` 等顶层包名，接入需控制命名空间与版本 |
| 对本项目的价值 | 多品种研究组织、信号组合、统计和报告 | 原文规则对照、逐层结构可视化、不同划分口径核验 |

**需要纠正只看 README 容易形成的印象：**chan.py 在 README 开头明确区分公开版与完整版。公开仓库没有完整交易引擎、模型与 AutoML，不能按完整文档直接规划全部功能。其演示策略在观察到信号后按当前收盘价记账，也不等于本项目所需的下一根真实合约撮合、滑点、保证金与移仓账本。

CZSC 当前 `CZSC.zs_list` 的实现是由已完成笔形成的中枢序列。它不能未经规则核对就替代 chan.py 的特征序列线段及其递归结构，也不能把不同定义的中枢数量视为准确率比较。

## 逐根实验的结果

每次仅交给框架当前已观察到的一根日线，立即保存结构的数值快照。笔用“起点序号、终点序号、方向、高点、低点”标识；买卖点按“起点、终点、方向、类别”拆成单独条目。每一步比较上一步条目是否仍在当前输出中。

| 观测集合 | 最终条目数 | 历史中出现过的不同条目 | 从相邻时点输出中移出的累计次数 | 首次出现晚于端点的中位数 |
|---|---:|---:|---:|---:|
| CZSC `bi_list` | 153 | 308 | 155 | 1 根日线 |
| CZSC `finished_bis` | 153 | 198 | 45 | 3 根日线 |
| chan.py 全部笔（含虚笔） | 103 | 647 | 544 | 0 根日线 |
| chan.py `is_sure=True` 的笔 | 102 | 257 | 155 | 1 根日线 |
| chan.py 买卖点条目（含动态尾部） | 33 | 270 | 247 | 0 根日线 |

这些是结构状态变化的统计，不是亏损次数、策略胜率或错误率。同一个条目可以移出后再出现；条目变动也可能来自端点延伸或属性更新。两个库使用各自配置，数量不可用来排名。CZSC 使用 `max_bi_num=10000`，避免默认历史截断被误计为撤回；运行时默认 `min_bi_len=6`。chan.py 使用 `trigger_step=True`、其余为 `CChanConfig` 默认值，并显式设置 `CTime.auto=False`。

CZSC 上述 45 次 `finished_bis` 条目移出时，相同数值条目也已不在当时的 `bi_list` 中，而不是仅被 getter 暂时隐藏。**因此，本样本里不能把 `finished_bis` 当成永远不变的发布记录。**chan.py 的 `is_sure` 也应按框架当前状态理解，不能直接解释为面向交易账本的永久封存。

在第 101、501、1001、1894 根处，分别用截至该点的输入从头重放，两个库的笔集合均与连续增量状态相同。chan.py 另用 `trigger_step=False` 喂完整输入、最后计算结构，笔集合及确定笔集合与增量最终结果一致，两种方式均得到 17 条线段。这些检查只覆盖本样本、参数与笔集合；未证明所有输入、多周期结构和所有买卖点都满足同样性质。

结构随观察更新本身不等于使用未来函数。问题在于：如果把最终图上某个端点的历史日期，当成该结构当时已经可知的日期，再回填订单，就会提前使用信息。应在逐根运行时记录信号，随后发生修订也保留当时的判断和修订记录。

## 与 AI-QUANT 的接入判断

1. **结构时间与观察时间分开保存。**建议统一输出 `pivot_time`、`first_observed_at`、`confirmed_at`、修订/撤回状态、引擎版本、配置哈希。不要直接从全历史最终图反推当年的信号；也不能只靠丢掉最后一笔就宣称永不重绘。
2. **行情入口沿用本项目数据边界。**仅喂已完成 K 线，保留交易日、真实合约、换月证据及信号价格口径。CZSC 的天勤连接器含 `datetime.fromtimestamp` 与分钟结束时间转换，并用 `vol>0` 过滤部分新 K 线；成交量大于零不能替代已收盘判定，不能原样套入当前服务。
3. **时区必须适配。**CZSC 1.0.2 实测拒绝带时区的 `RawBar.dt`；应先转换到市场本地时间，再移除时区。chan.py 的 `CTime` 默认会把 00:00 的日期解释到 23:59，并使用系统本地 `datetime.timestamp()`；日线标签及跨服务 epoch 不应靠默认行为猜测。
4. **默认划分不是共同标准。**现有 `fu-chanlun-causal-v1` 对笔额外封存、保存 `confirmedIndex`，且明确只是研究口径。应分别保留它、CZSC、chan.py 的版本与参数，对照原文课号解释差异，再评估是否改变现有研究规则。
5. **执行层复用现有账本。**第三方库先只输出结构和候选信号。真实合约的下一根成交、整数手数、保证金、手续费、滑点和移仓，交给已有 `FuturesExecutionLedger`。CZSC 的权重回测和 chan.py 的收盘价示例均不能直接替代该账本。
6. **配置接口需有明确白名单。**chan.py 的 `CChanConfig.set_bsp_config` 对部分参数使用 `exec`。若未来开放网页配置，适配层应只接受约定字段、类型与枚举，不能把任意输入字符串直接转交给该配置类。

建议下一轮先做一个仅用于研究的结构对照页：同一冻结行情、三个引擎分别显示笔/线段/中枢及首次观察点；保留逐根回放和修订轨迹。等定义与时间语义通过验收，再比较基准策略成本后的表现。当前这轮足以支持“值得继续研究”，不足以支持立即替换现有撮合与策略逻辑。

## 复现与证据

源仓库只作固定版本的研究输入。Python 依赖安装在独立虚拟环境，完整版本见 `data/czsc-chanpy-2026-10-31/requirements-locked.txt`。发布 wheel 地址及 SHA-256 见同目录 `sources.json`；存在 Linux amd64 wheel 不等于已完成本项目 Docker 兼容验收。

```powershell
python scripts/research_chanlun_frameworks.py --chanpy <固定提交的chan.py目录> --output docs/research/data/czsc-chanpy-2026-10-31/structure-probe.json
```

核心依据（均为固定提交）：

- [CZSC 包定义、Python/Rust 与依赖](https://github.com/waditu/czsc/blob/5d350a943d6b1935561765fed5467c234973d121/pyproject.toml)。
- [CZSC 结构更新、finished_bis、末笔撤回与中枢 getter](https://github.com/waditu/czsc/blob/5d350a943d6b1935561765fed5467c234973d121/crates/czsc-core/src/analyze/mod.rs#L169)，[按笔构造中枢](https://github.com/waditu/czsc/blob/5d350a943d6b1935561765fed5467c234973d121/crates/czsc-core/src/analyze/utils.rs#L31)。
- [CZSC 天勤连接器](https://github.com/waditu/czsc/blob/5d350a943d6b1935561765fed5467c234973d121/czsc/connectors/tq_connector.py)，[时间往返与带时区拒绝测试](https://github.com/waditu/czsc/blob/5d350a943d6b1935561765fed5467c234973d121/tests/unit/test_naive_datetime_roundtrip.py)。
- [chan.py 公开版范围说明](https://github.com/Vespa314/chan.py/blob/f8ca3b5e44d7166e2abd756a8e7fa816c79faebe/README.md#L20)，[逐根输入与一致性说明](https://github.com/Vespa314/chan.py/blob/f8ca3b5e44d7166e2abd756a8e7fa816c79faebe/quick_guide.md#L556)。
- [chan.py 笔的虚拟端点与更新](https://github.com/Vespa314/chan.py/blob/f8ca3b5e44d7166e2abd756a8e7fa816c79faebe/Bi/BiList.py#L86)，[动态尾部买卖点清理](https://github.com/Vespa314/chan.py/blob/f8ca3b5e44d7166e2abd756a8e7fa816c79faebe/BuySellPoint/BSPointList.py#L44)。
- [chan.py 配置](https://github.com/Vespa314/chan.py/blob/f8ca3b5e44d7166e2abd756a8e7fa816c79faebe/ChanConfig.py)，[日期处理](https://github.com/Vespa314/chan.py/blob/f8ca3b5e44d7166e2abd756a8e7fa816c79faebe/Common/CTime.py)，[策略演示](https://github.com/Vespa314/chan.py/blob/f8ca3b5e44d7166e2abd756a8e7fa816c79faebe/Debug/strategy_demo2.py)。
