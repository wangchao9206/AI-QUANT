# 缠论中心：第一期运行说明

2026-10-31 实施。入口：`/chanlun`，默认工作台 `/chanlun/workbench`。用户已决定采用自研路线，目标与验收见 [自主缠论引擎](plans/chanlun-native-goal.md)。

## 已交付

- 主导航独立入口；工作台、信号雷达、多周期观察、引擎对照、逐根训练、策略实验、原典课堂、判断档案、监控复盘、规则与引擎十个页面。
- 默认 AI-QUANT 自研引擎 `aiquant-chan-v1`，保留 chan.py、CZSC、`fu-chanlun-causal-v1` 研究基线，共四个隔离 Worker；取消 pro 待授权入口。
- 已冻结 FU 日线的任意 50—1,894 根前缀计算；只返回该前缀内行情与结构，不用最终图回填过去。
- 笔/线段/中枢图层与选择；CZSC 当前适配器不提供线段层，明确禁用。
- 首次观察、当前修订确认、修订与撤回事件留档；结构身份在单引擎内按类型、起点、方向关联，改变起点视为新对象。
- 判断绑定不可变分析、结构、数据哈希、规则哈希和可选原文课号，支持幂等保存、档案回到当时图表与原文。
- 独立逐根训练 `/chanlun/replay`：服务端按步推进，先提交判断才能展开下一根；并发重试不跳步，会话可恢复，训练判断进入中央档案并保留结构快照。
- 策略实验 `/chanlun/lab`：首次候选接入已有交割合约现金账本，同时列出基础、双倍成本、延迟一根和两个普通规则对照；冻结配置、逐笔交易、未成交记录和摘要持久化保存。
- 主源持久雷达 `/chanlun/radar` 与复盘 `/chanlun/reviews`：真实交割合约 DAY/MIN5/MIN30，服务器检查、数据库租约与水位、初始化/补算抑制、冻结事件与复盘。已创建 FU2701 五分钟默认观察任务。
- 多周期观察 `/chanlun/multiframe`：主源独立日/30/5 分钟序列，按共同后继证据界限截取输入后重算、冻结与恢复；光标按封存证据联动，支持时间视窗和按光标重新构建。
- 复用本系统本地 108 课全文与图片；原文与引擎解释分开，无外站阅读跳转。
- 复用并扩展 `TongdaxinChart` 的视口和覆盖层，保留市场、策略、模拟交易中的原图表功能。

工作台、训练和成本实验使用冻结历史数据。日线日期是交易日标签，尚不能映射为精确的行情可得时刻；所有结果 `executable=false`、`eligibleAt=null`。工作台回放可自由选区间；逐根训练使用独立页面与服务端状态机，只返回已展开前缀。已看过走势的历史区间属于复习，训练并不阻止用户主动访问独立研究接口查看该历史。雷达和多周期观察另接天勤主源真实交割合约与原始价格，不与冻结连续信号价格混用；主连自动换月、精确日线可得时间映射、自动交易与可取消队列仍待后续交付。

## 数据与版本

输入：`docs/research/data/fu-chanlun-2026-10-30/source-snapshot.json.gz`，SHA-256：
`f069d8c21ec41d106f4b21c90f9e04d4d285d00847c8f551ff11991e38768577`。

2019-01-02—2026-10-27，1,894 根日线、33 次换月。连续信号价格使用已观察换月开盘比价向前串联，不回写旧价格；与真实合约可成交价格分开。图中涨跌幅由相邻信号收盘价计算，首根缺少前收盘时显示未知。

chan.py 固定提交 `f8ca3b5e44d7166e2abd756a8e7fa816c79faebe`，45 个公开计算/许可文件原样保留，MIT 声明见 `third_party/chanpy/LICENSE`，文件校验见 `manifest.json`。未引入完整版或 pro 专有代码。CZSC 固定 `1.0.2`、wbt 固定 `0.9.2`；Linux Python 依赖锁在 `chanlun_worker/requirements-*.lock`。

每个结果同时记录引擎版本、适配器版本、固定参数、实现源码摘要与规则哈希。升级 Worker 后旧分析仍可读取，不自动覆盖为新结果。结构“确定”是各引擎的当前口径，可能后续修订，不等于可交易信号。

## 架构与运行

前端 → 既有 Gateway → `chanlun-service:8084` → 独立 Python Workers `:8010`。策略实验经内部接口调用已有 `algorithm-service:8000` 的期货账本，不获取外部数据，不生成订单；雷达/多周期复用该算法服务的现有主源行情连接。新服务使用 PostgreSQL 独立 `chanlun` schema，V1 结构/判断、V2 训练、V3 策略实验、V4 持久监控与复盘、V5 多周期冻结观察；未改写已执行迁移。Worker 和 Java 服务不新增宿主机监听端口。

第一期使用有时限的同步计算：每个 Worker 最多一个计算，Java 最多三个并发。任务与结果持久化，超时/中断任务会变为失败，需显式重新分析；尚未启用 RocketMQ 调度或任务取消。Nginx 对缠论接口单独使用 120 秒读取超时，Worker 调用为 90 秒；普通行情接口保持原超时。

沿用现有本机共享工作区的访问方式，没有引入多用户账号隔离。部署成多人服务前，需把资源所有者与身份校验作为单独交付。

网关的 Netty DNS 正缓存最多保留 5 秒，避免容器地址变化后持续连接旧地址。隔离 Docker 网络中已验证：同一 DNS 别名的后端换到不同 IP 后，网关无需重启即可访问替换后端；本次约 4.78 秒观测到恢复，结果见 `docs/research/data/chanlun-native-2026-10-31/dns-refresh.json`。

```powershell
docker compose -f infrastructure/docker-compose.yml build chanlun-native-worker chanpy-worker czsc-worker chanlun-baseline-worker algorithm-service chanlun-service gateway-service frontend
docker compose -f infrastructure/docker-compose.yml up -d --wait algorithm-service chanlun-service gateway-service frontend
```

`GET /api/chanlun/v1/engines` 查看四个已接入引擎的服务状态。`GET /datasets` 提供冻结数据目录。`POST /runs` 的 `clientRequestId` 为 UUID，相同内容重试返回同一任务，变更内容返回 409。失败后使用新请求编号重新计算。分析目前支持 `native|chanpy|czsc|baseline` 和固定数据集，其他名称拒绝计算。

`GET /runs/{id}/structures` 读取冻结结果；`GET /runs/{id}/events?structureId=…` 返回该对象最近 100 条事件（界面默认展示最近 8 条）。完整事件保存在数据库。`POST /judgments` 保存判断；`GET /judgments` 返回最近 50 条。没有删除/覆盖已发布分析或判断的网页接口。

## 逐根训练协议

新增 Flyway V2 `causal_replay`，只扩展 `chanlun` schema。`POST /replays` 冻结初始数据与规则哈希，起点为 50—1,893 根；`GET /replays/{id}` 恢复当前步骤和当前前缀。所有训练响应均为 `Cache-Control: no-store`。

`POST /replays/{id}/decisions` 使用当前 `expectedStep` 保存一次判断；同一请求重复返回同一记录，修改内容或试图覆盖已提交步骤返回 409。判断关联当时 run、结构快照、原文课号及训练步骤，写入中央判断档案。

`POST /replays/{id}/advance` 在会话行锁下检查步骤、已存判断和推进状态，只计算 `observedBars+1`。计算期间不占用数据库事务；完成后通过比较步骤与命令 ID 原子发布。并发相同命令不重复推进，不同命令竞争不会跳步。失败保持旧观察界限，超时推进会解除占用；规则/数据哈希变化会阻止旧会话混用新实现。到第 1,894 根标为完成。

训练页面不调用工作台的完整研究计算接口，不预载最终图表；自动恢复只读取当前会话。反馈显示实际已展开信号价变化及上一观察对象的修订/撤回，不将单根涨跌当作缠论划分正确率或账户收益。

## 策略实验协议与执行假设

`POST /api/chanlun/v1/lab` 接受 UUID `clientRequestId`、固定组 `THIRD|ALL` 和初始资金 `100000|500000|1000000`。同内容重试恢复同一实验，变更内容返回 409。`GET /lab` 返回最近 30 条，`GET /lab/{id}` 读取冻结报告，即使计算服务离线仍能恢复。同步计算最多一个，超过三分钟的中断实验标记失败；失败后显式发起新实验。

私有 `POST /internal/v1/chanlun/lab` 不对网关开放。`backtesting/native_chanlun_lab.py` 读取校验过的原始交割合约快照，核对连续信号 OHLC 与结构 Worker 完全一致。从 append-only `OBSERVED` 事件取得**首次候选**，不从最终仍有效的结构筛选；后来失效或撤回也保留，并在该次失效观察之后的下一根开盘退出。相同观察根有多个候选时全部跳过，避免事后挑选。窗口外/末根无法执行的候选单独留档。

复用 `FuturesExecutionLedger`、`ResearchRisk` 和既有成本执行器。收盘后观察，下一根真实交割合约开盘执行；2 ATR 止损、4 ATR 止盈、最长 20 根，换月开盘平旧仓且取消当日新单。固定风险预算、手续费、滑点、保证金、成交量参与率；基础/双倍费用与滑点/再延迟一根三种自研情景，以及普通突破回踩/直接突破两种基础成本对照，均采用同一账本。逐笔净损益之和必须与最终权益变化对账，Java 再核验后才发布。

日线仅有交易日标签，因此这是下一日开盘的研究假设；规格采用快照常数，不能称为逐日真实费率与保证金。开发已使用该历史，不称为未见样本或前向业绩。同日止损/止盈先计止损；止损跳空按更差开盘，止盈按目标或越过目标的开盘且滑点为零。成本变动会改变可开手数，回撤和净损益不保证随费用单调变化。失效边界用于候选与退出，初始风控止损固定为 2 ATR，不宣称完整缠论策略或收益优势。

100 万初始资金、全部候选首轮结果：18 个首次候选；基础 15 笔、净损益约 -11,277.08 元，双倍成本约 -15,707.10 元，延迟一根约 +3,081.58 元；普通回踩约 +18,223.47 元、直接突破约 -10,791.65 元。基础情景有 3 笔实际损失超过计划风险预算，页面予以展示。该敏感性与样本量不足以支持盈利或优于对照的结论。实际接口报告见 `docs/research/data/chanlun-native-2026-10-31/cost-lab-protocol.json`。

## 最新验证

监控最新检查：47 个前端文件、247 个检查，TypeScript/生产构建通过；Java 8 个检查。主源/封存与已有天勤模块 190 个检查通过。独立 Docker 内网与临时 PostgreSQL 已验证初始化抑制、请求幂等/冲突、断流保留水位、恢复去重、暂停/恢复、重启与过期租约恢复、封存行情修订暂停、规则漂移暂停、冻结事件前缀和复盘幂等。该故障演练使用合成时钟，**不是实时市场观测**；报告 `monitor-protocol.json` 已标明范围并记录容器/网络清理。

真实主源另行核验：FU2701 MIN5，1,999 根已封存 K 线，序号 11,518—13,516，2026-09-11 11:05 至 2026-10-30 22:50；实际接收 2026-10-31 12:27 上海时间，34 条近期候选/修订，初始化均未标为新提醒。报告 `docs/research/data/chanlun-native-2026-10-31/monitor-primary.json`；验收任务已清理。默认观察任务 `0744473b-c46c-4f42-a95a-5ef97961c231` 为正式后台任务，另行保留。当前周六休市，实际开市增量与长时间前向稳定性尚待观察，不能用隔离故障演练替代。

默认任务最后一次手动检查为上海时间 12:31:28，随后只读 GET 查询看到后台心跳已推进到 12:33:07，仍保留 1,999 根及 34 条初始化事件。最终主源/监控/已有成本研究/原文组合回归共 208 个测试与 151 个子用例通过。此证据证明后台检查独立于页面请求，不能证明休市期间产生了新市场行情。

## 持久雷达与复盘协议

`POST /api/chanlun/v1/monitors` 接受 UUID 请求编号、名称、真实交割合约和 `DAY|MIN5|MIN30`；同请求幂等，变更内容 409。`GET /monitors`、`GET /monitors/{id}` 查看服务器状态。`POST /{id}/control` 暂停/恢复，`POST /{id}/check` 触发检查；浏览器普通刷新只读取状态，不承担调度。服务器每 15 秒领取到期任务，单进程最多一轮计算，正常检查间隔 30 秒；两分钟数据库租约让中断任务在过期后被下一实例接管。发布结果在事务内比较租约，暂停/更换租约后迟到结果不会覆盖状态。

主源读取在既有天勤 SDK 所属线程进行，HTTP 线程不直接调用 SDK。只订阅真实交割合约、不使用主连拼接或公开降级源。各周期最多取 2,000 根源窗口；必须具有连续 providerIndex、合法 OHLCV、已观察到后一根且后者时间戳不晚于检查时刻。最后一根即使休市也保持未封存，可能延迟到下一交易时段。日线保存 SDK 原始时间戳，不猜测其交易日/精确可得时间；日线目前只留档，不取得新提醒资格。

源连接断开、线程心跳超 15 秒、未知交易日历/时段、开市合约报价或分钟水位陈旧时，不计算新信号。休市可维护已封存状态，事件留档但不发新提醒。首次历史初始化抑制提醒；分钟事件在已保存水位之后、主源就绪且距假设周期结束不超过两分钟才可标记站内新事件。它仍是研究候选，`eligibleAt=null`，没有订单或外部通知通道。

输入按 providerIndex 追加；重叠封存行情任一字段修订、源窗口越过保存水位、规则摘要改变或累计超过一万根时暂停任务，保留原行情、旧分析与事件。不得静默重置原点或采用最新实现覆盖旧证据。独立监控规则哈希包含原始交割合约价格口径、合约、周期、内核和监控/来源代码，不能与冻结 FU0 工作台哈希等同。

`GET /{id}/events/{seq}` 返回该事件观察索引以内的原始行情与**单个候选**冻结快照，明确不是该时点全部图层；不返回后续行情。`POST /{id}/events/{seq}/ack` 标记站内已读；`POST /{id}/events/{seq}/reviews` 保存不可覆盖复盘，重复同内容幂等，变更内容 409。复盘保留当时行情、候选、规则摘要、实际发现时间和可选课号；`GET /monitors/reviews` 与 `/chanlun/reviews` 恢复档案并跳回原事件和本系统原文。

当前每次算法服务进程最多八个交割合约×周期订阅组合，暂停任务不会立即释放 SDK 订阅槽；需要新组合而容量已满时，应在维护窗口重启算法服务，由仍启用的任务重新订阅。Java 同时启用任务也限八个；保留窗口、源权限、过期合约与真实开市延迟仍需要容量/前向观测验收。多周期冻结同屏已另行交付，未通过主连自动换月、真实开市新增数据的长期联动与容量验收。

```powershell
python scripts/test_chanlun_monitor_protocol.py --output docs/research/data/chanlun-native-2026-10-31/monitor-protocol.json
python scripts/smoke_chanlun_monitor.py --cleanup --output docs/research/data/chanlun-native-2026-10-31/monitor-primary.json
```

## 多周期冻结观察

`POST /api/chanlun/v1/multiframe` 接受 UUID `clientRequestId`、交割合约、组合 `PAIR|TRIPLE`（30/5 或日/30/5）及可选带时区 `asOf`。前端日期输入明确按上海时间解释。`GET /multiframe` 列出最近 30 个观察，`GET /multiframe/{id}` 不重算地恢复已冻结报告。相同请求重复返回同一记录，变更请求返回 409；未来界限返回 400。主源未就绪时保留 `WAITING_INPUT`，同请求可继续，打开归档不会自动重订阅。

SDK 所属线程分别获取各周期原始序列，不能由日线生成分钟线。原始源快照在同一行情锁内采集，随后释放锁再计算。每根输入包含 `providerIndex` 和 `sealedByTimestamp`（已观察的后一根起点）；只选择后继证据不晚于共同重建界限的原始 K 线，至少 50 根。**先截输入再计算**，不把当前完整结构按端点裁切成“过去结果”。最新模式取各源已证实的最新后继界限，较慢周期保留自己的实际已封存水位，不假造对齐 K 线。

该模式明确为 `HISTORICAL_SUCCESSOR_BOUND_RECONSTRUCTION`：SDK 后继时间戳是保守重建界限，不能证明历史网络可得时刻。来源实际接收、实际采集、输入摘要（含封存证据）、规则摘要分别保存。源窗口最多两千根，起点/预热长度可能不同；结构身份只在本次冻结观察内关联，不跨滚动起点自动匹配。日线原始时间戳语义仍保留限制，输出没有交易资格。

光标按各周期 `sealedByTimestamp` 的最近已封存 K 线定位，支持键盘左右键、上海分钟时间、可选联动时间视窗。光标不改变结构的冻结观察界限；“按光标界限重新构建”才生成新的历史观察。光标移动不会重建行情数组或重置视窗。雷达心跳复用未变分析与不可变事件快照，追加新行情时保留历史视窗；跟随末尾时才继续向右。

实际天勤核验：FU2701 日线 197 根，30/5 分钟各 1,999 根；最新共同后继界限 2026-10-30 22:55 上海时间，另重建 2026-10-29 10:45 的更早观察。每根 `sealedByTimestamp` 不晚于界限，每个结构观察索引在该前缀内；双/三周期、同请求/冲突、未来界限、冻结恢复通过。报告 `docs/research/data/chanlun-native-2026-10-31/multiframe-protocol.json`，临时记录已清理。当前为休市重建验证，不等于实际开市前向观察或浏览器视觉验收。

```powershell
python scripts/smoke_chanlun_multiframe.py --cleanup --output docs/research/data/chanlun-native-2026-10-31/multiframe-protocol.json
```

本次最终检查：49 个前端文件、258 个检查；Java 9 个检查；多周期/主源/监控/成本/原文组合 211 个测试与 151 个子用例通过。Docker 生产构建完成。已保留三周期示例观察 `0ea44a24-d231-4de5-a081-9dea6f9206aa`，可在系统内恢复；浏览器视觉复核仍未完成。

## 八任务休市测量范围

`scripts/benchmark_chanlun_monitor_capacity.py` 在已启用的正式 FU2701 MIN5 任务旁创建七个带随机验收标签的临时任务，均使用同一个真实主源序列、每任务 1,999 根；验证第九个启用任务被拒绝，记录七次初始化、三轮共 24 次暖检查，再只清理临时任务。正式任务与其事件保持不变。

本机共享宿主机、Java 1 CPU / 768 MiB、算法服务 2 CPU / 1 GiB：初始化中位 2.162 秒、最大 2.350 秒；暖检查中位 0.166 秒、最近秩 P95 0.179 秒；八任务一轮暖检查中位 1.309 秒、最大 1.382 秒。测量覆盖网关、Java、计算服务、数据库、JSON 与本机传输，不含浏览器渲染。输入摘要 `299196198f796dc0578819ee532a0de767edd0bd9873319892848d45353a5569`，规则摘要及镜像 ID、配额、样本量见 `monitor-capacity.json`；输入来源从保留的不可变默认快照补核，测量未重跑，该时间与说明在报告中单列。

这是**休市、单个主源订阅组合、八个逻辑任务**的初始化与无新增输入暖检查，不能据此宣称八个独立品种开市吞吐，也没有测量 chanlun-pro。逐根新增、较长历史、多个独立 SDK 订阅、数据库长期增长和真实开市前向稳定性仍待验收。

```powershell
python scripts/benchmark_chanlun_monitor_capacity.py --output docs/research/data/chanlun-native-2026-10-31/monitor-capacity.json
```

策略实验最新检查：45 个前端文件、243 个测试；Java 6 个检查；成本实验/既有缠论研究/原文共 18 个测试与 151 个子用例通过。12 个自研与 Worker 回归也通过。实际接口并发去重、变更内容 409、冻结恢复、五情景对账、下一根执行与固定配置验证通过，临时实验已按随机请求 ID 清理。最终重建时曾在算法服务尚未就绪时发起验收而得到失败记录，已改为等待 Docker 健康后验收；失败也保持原记录状态，不发布残缺报告。浏览器视觉复核仍未完成。

```powershell
python scripts/smoke_chanlun_lab.py --cleanup --output docs/research/data/chanlun-native-2026-10-31/cost-lab-protocol.json
```

```powershell
# 浏览器与 API 之外的回归
cd frontend
npm test
npm run build

# 从仓库根运行；只创建分析记录，不创建判断或订单
python scripts/smoke_chanlun_center.py

# 创建带随机验收标签的练习和判断，结束后只清理本次临时练习/判断
python scripts/smoke_chanlun_replay.py --cleanup

# 独立内部网络，临时容器自动清理，不使用生产数据或凭据
python scripts/test_gateway_dns_refresh.py

# 研究测试环境需安装 requirements-czsc.lock 中依赖
python -m unittest tests.test_chanlun_worker -v

# 有固定上游 checkout 时核对 vendored 源码
python scripts/verify_chanpy_vendor.py --source <chan.py-checkout>
```

2026-10-31 验证记录：

- 三个实际部署引擎均通过 501 根前缀、相同请求重试不重复、变更请求返回 409、结构端点/观察界限、实现摘要与 pro 阻断检查。
- Python Worker 的前缀重建、未来价格不改变过去、修订/撤回谱系、完整历史计数和输入边界五项检查通过。
- 既有缠论研究与原文完整性检查：14 个测试及 151 个子用例通过。
- Java 全模块 Maven 构建与测试通过；新控制器验证未授权引擎、输入越界及错误来源结果。
- 前端全量检查：42 个测试文件、233 个测试通过；TypeScript 与生产构建通过。
- 浏览器已实际打开本地第 62 课并核对正文、图片及无 iframe；保存系统验收判断后，服务器记录包含当时结构与第 62 课引用。
- 判断接口的相同请求重试返回同一记录，修改内容复用编号返回 409；仅本轮生成的系统验收判断已按精确 ID 清理。
- 最后一轮浏览器复核因 Work 设置关闭本地浏览器控制而中止；新版全页面交互与窄屏布局尚未完成最终浏览器复核。部署接口、静态页面 HTTP 200、Nginx 配置检查及各容器健康检查通过。
- 逐根训练：44 个前端测试文件、239 个测试通过；Java 5 个控制器/界限检查通过，生产构建成功。实际 PostgreSQL 与 HTTP 检查覆盖“无判断不能推进、并发相同判断仅存一次、判断不可覆盖、并发相同推进只走一步、不同命令不跳步、恢复保留原证据、末端不越界”，详见 `docs/research/data/chanlun-native-2026-10-31/replay-protocol.json`。本次临时会话与判断已清理，原始分析留档保留。

完整产品设计见 [缠论中心设计](plans/chanlun-center-design-2026-10-31/design.md)。

## 引擎观察分歧取证（V6）

`/chanlun/compare` 为独立页面，打开不自动计算。新对照选2—4个引擎和50—1894根冻结FU日线；支持笔、线段、中枢，按引擎能力拒绝不支持的组合。相同输入包括完整bars、数据摘要、价格口径和观察根数。三引擎默认，第四个分批提交，任何来源失败都不静默生成局部对照。从工作台进入时沿用已观察根数。

`POST /api/chanlun/v1/comparisons` 接收UUID `clientRequestId`、`runIds`、`layer=BI|SEGMENT|ZONE`、`projection=GEOMETRY|WITH_CONFIRMATION` 和 `confirmedOnly`。保存完整报告；`GET /comparisons` 列最近30条，`GET /comparisons/{id}` 恢复档案，不依赖Worker在线。不同参数复用请求号返回409。逐根重放来源的观察/修订/撤回事件，不把最终结构裁成过去结果；仅支持交易日期唯一的冻结日线。

几何匹配比较类型、起止索引、方向及起止/高低价格，绝对价格容差1e-8；一一配对，各引擎ID仅在自身内部使用。确定标记保持TRUE/FALSE/UNKNOWN，仅在几何匹配后比较。不同起点不强行归为同一对象，匹配数量不表示准确率。CZSC中枢缺少确定字段，拒绝“只看确定中枢”组合。

`GET /comparisons/{id}/at/{index}` 返回该观察索引及以前的价格与各引擎事件状态，另附逐对未匹配/确定标记证据。`GET /comparisons/{id}/events` 限制成员来源、结构和观察界限。页面支持首次所选/几何/标记分歧、连续区间及逐根取证；移动选择器不改变已展示证据，载入后才改变。原文始终在本系统读取。

`POST /comparisons/{id}/at/{index}/judgments` 在事务内将当时事件前缀物化为不可变analysis_run，然后保存中央判断及对照/来源/索引。派生ID由来源及索引确定，可跨对照复用；不调用Worker，不引入未来对象。V6数据库允许1根派生记录，公开新分析请求仍至少50根。判断档案同时链接冻结工作台及分歧取证页。

保留示例：`http://localhost:8088/chanlun/compare?comparison=eb655375-eba9-40c6-855f-218267755330&at=15`。真实三引擎501根的首次所选分歧在第16根；这是该配置下的分歧，不是哪个引擎正确的结论。50个前端文件269项检查、Java13项检查、隔离真实档案协议及部署接口检查通过；最终浏览器视觉待复核。

```powershell
python scripts/test_chanlun_comparison_protocol.py --output docs/research/data/chanlun-native-2026-10-31/comparison-protocol.json
# 后一条会保留一个新的正式研究对照，不创建判断或订单
python scripts/smoke_chanlun_comparison.py --output docs/research/data/chanlun-native-2026-10-31/comparison-deployment.json
```

## 监控当前状态与冻结快照（V7）

V7新增 `monitor.latest_analysis`，从已有最新快照原样回填；所有既有快照保留。无新BSP事件的新增行情只更新当前状态、水位与输入；出现新观察/修订/撤回BSP事件时才保存完整冻结快照并绑定事件。当前状态用单条SQL与兼容快照一起读取，避免并发更新时混读指针和内容。事件复盘仍只读取其不可变快照。

真实V5 schema备份已在隔离数据库升级演练：原表行数、两份当前状态内容及所有事件快照引用保留；本系统实际升级后正式燃油任务1999根、34事件保持一致。额外故障演练验证277/278根无事件推进不增加快照，旧复盘保持不变；返回事件受已读取的状态水位限制，即使两次读取之间提交新事件，也不混入较新时点。重启/版本漂移等10项检查通过。这些检查为隔离演练，不冒充真实开市前向运行。报告 `storage-upgrade-protocol.json`、`monitor-storage-protocol.json`。

此优化减少无事件重复快照；BSP事件快照仍包含完整前缀，长期增长、长历史负载和SDK槽释放问题继续保留。升级前私有备份位于本机 `.test-tmp`，不提交或发布。可用 `scripts/test_chanlun_storage_upgrade.py --backup <本机schema备份> --output <报告>` 在独立内部网络复现演练。

模拟桥接的现有链路与版本、资格、影子观察、订单证据约束见 [桥接实施边界](plans/chanlun-workflow-bridge.md)。该部分仍未实现。
