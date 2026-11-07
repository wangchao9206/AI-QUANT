# 国内期权研究

2026-11-07 快照研究见[买方、卖方与组合机会报告](research/options-opportunities-2026-11-07.md)，PDF为 `output/pdf/options-opportunities-2026-11-07.pdf`。实际采集18条链、1,318个合约；180个通过核心流动性筛选，计算168个结构的到期及7天后价格／IV压力情景。报价为周末前真实缓存，需开市重新核对。该研究不是期权历史回测，不声称正期望或历史胜率；未创建订单，也未自动新增预警任务。全部筛选、失败及日线可用口径修正记录保留。

入口：左侧「期权」，路径 `/options`。当前阶段提供商品期权、以真实期货为标的的金融期权，以及中金所股指期权的行情、期权链、模型敏感度和单腿到期损益研究。

## 使用

1. 启用 `MARKET_DATA_PROVIDER=tqsdk`，配置 `TQSDK_USERNAME` 和 `TQSDK_PASSWORD`。实际覆盖范围取决于账户的行情权限；不在页面输入或保存凭据。
2. 打开「期权」。首次访问触发目录加载，之后按交易所、标的代码选择「标的 / 到期日」。期权标识保留供应商原始代码，不经过期货主连或交割月归一化。
3. 认购列在左，认沽列在右。点击合约报价查看乘数、真实报价时点、成交量、持仓量、内在/时间价值、IV 和 Greeks。
4. 在到期情景中调整买入/卖出及手数。金额按真实合约乘数计算；卖出认购的理论亏损无上限。
5. 利率初始值 2%、指数股息率初始值 0% 均为可修改的研究假设，非实时市场数据。点击「应用假设」后重新计算，页面同时保留本次结果实际使用的参数。

前端每 5 秒读取快照，隐藏页面暂停轮询。行情线程按需订阅选中的完整期权链；不在 HTTP 请求线程创建第二个天勤连接。目录每 6 小时重载，报价订阅总量上限为每连接 2048 个期权/标的代码。达到容量后明确提示；重启行情服务可重新选择。供应商异常不会触发期货行情线程重连。部署时需更新 algorithm-service、gateway-service 和 frontend；无需数据库迁移。

## 数据与模型口径

| 项目 | 处理 |
| --- | --- |
| 合约目录 | `query_quotes(ins_class="OPTION", expired=False)` + 分批 `query_symbol_info`；仅国内期货交易所，标的类型仅 FUTURE/INDEX；不含 ETF/股票期权 |
| 到期 | 使用真实 `expire_datetime`，不按月份推算最后交易日 |
| 股指期权 | 保留实际指数标的，使用 BSM；不以对应股指期货代替指数 |
| 期货期权 | Black-76 模型参考 |
| 美式行权 | 明确标注欧式模型近似，未计提前行权价值；不将近似 IV 标为交易所发布指标 |
| 权利金 | 优先有效、非交叉、有挂单量的买卖一中间价；其次为真实最新成交价并提示局限。报价时点缺失则不可用；交叉盘口不计算 |
| IV 求解 | ACT/365、二分反解，波动率上限 800%；越界不强行钳制为可用 IV |
| Greeks | Delta/Gamma 为每单位标的变动的价格敏感度；Theta 为每自然日；Vega 为每 1 个波动率百分点；整笔头寸乘合约乘数、手数与买卖方向 |
| 数据同步 | 期权与标的时点相差超过 5 分钟则不计算模型指标；缓存数据仅按真实报价时点估值，不冒充当前市场数据 |
| 缺失与到期 | 缺失值保持 null/—；缺少行权方式、标的、时间、可用权利金或合约已到期时，相关指标不可用 |
| 到期情景 | 数学内在价值曲线，非行情预测；不含手续费、滑点、卖方保证金、提前行权或交割资金需求 |

本阶段不包含期权模拟撮合、期权历史回测、组合保证金或实盘委托。

## API

- `GET /api/v1/options/catalog`：实际目录、数据状态与错误提示。未配置账户时返回 `UNAVAILABLE` 空目录，不返回演示合约。
- `GET /api/v1/options/chain?chainId=<catalog.id>&rate=0.02&dividend=0`：实际链、标的快照、单合约风险值和使用参数。`chainId` 必须来自目录并正确 URL 编码；利率范围 -0.1～0.5，股息率 0～0.5。
- `POST /api/v1/options/scenario`：`{"chainId":"<catalog.id>","symbol":"<contract.symbol>","side":"BUY","lots":1}`。严格验证真实目录成员、整手数量和乘数，不创建交易订单。

状态：`FRESH` 近时快照、`CACHED` 缓存快照、`WARMING` 正在订阅、`UNAVAILABLE` 不可用。报价使用供应商原始时间；目录时间和接口读取时间分别展示，不作为成交时间。

## 验证

- Python：`python -m pytest tests/test_options.py tests/test_tqsdk_feed.py tests/test_algorithm_api.py -q -p no:cacheprovider`
- 前端：`node node_modules/vitest/vitest.mjs run src/views/OptionsView.spec.ts src/router.spec.ts src/layouts/AppShell.spec.ts --configLoader runner --no-cache --no-fsModuleCache`（在 frontend 目录）
- 类型：`node node_modules/vue-tsc/bin/vue-tsc.js --noEmit`
- 构建：`node node_modules/vite/bin/vite.js build --configLoader runner --outDir ../.test-tmp/options-dist`

`runner` 绕开当前 Windows 环境中只读的 Vite 配置临时缓存目录，不改变生产配置。单元测试行情均为测试夹具，不能作为实际账户连通性或实时数据权限的验证。

2026-11-06 验证结果：19 项期权测试、185 项行情适配回归、39 项算法 API 回归、10 项前端/导航测试与 5 项网关测试通过；前端类型检查和生产构建通过。网关使用项目已有 Maven 3.9.9，系统默认 Maven 3.5.3 不满足现有编译插件要求。浏览器已使用明确标记的本地测试夹具完成桌面渲染检查；未验证真实账户的期权数据权限，未更新正在运行的服务。

参考：[天勤 API 文档](https://doc.shinnytech.com/tqsdk/latest/reference/tqsdk.api.html)、[天勤 Quote 元数据](https://doc.shinnytech.com/tqsdk/latest/reference/tqsdk.objs.html)、[Black 期货期权模型原始说明（CFTC 存档）](https://www.cftc.gov/sites/default/files/idc/groups/public/%40otherif/documents/ifdocs/eice28supplements-1.pdf)。
