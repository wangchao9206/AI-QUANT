# AI-QUANT 运行手册

## 书籍感悟（2026-10-27）

入口为桌面/手机导航的「书籍感悟」，地址 `/books`。首本收录豆豆《遥远的救世主》，包括思想解读、交易应用、误用边界与自问问题，明确标注为本站解读；交易应用附 CME/NFA 原始投教链接。新添书籍不会自动生成或套用其他书的解读。

点击「在线预览原著」或「在线预览」页签，系统按书名和作者查找微信读书的文字阅读资源，展示版本、作者、出版社与核对时间；「打开在线预览」在原平台新窗口打开。已核对《遥远的救世主（〈天道〉影视原著）》豆豆/作家出版社的官方阅读入口。其他书籍自动检索，无匹配结果或连接失败时明确提示，可重新查找。平台控制可试读范围、登录、会员或购买；本站不抓取/代理正文。内嵌验收出现平台限制，因此采用新窗口，保留既有 CSP。

预览接口为只读 `GET /api/v1/paper/books/{id}/preview?refresh=false`，独立 2 秒连接/5 秒读取超时，有界缓存最多 256 个书名/作者组合，匹配成功缓存 30 分钟；刷新会复用 10 秒内的最近结果。只接受微信读书 HTTPS 的 `/web/reader/` 链接。该功能无需新增数据库迁移。

点击「添加书籍」填写书名与可选作者；在「我的感悟」中选择思想理解、交易应用或疑问与反思，保存后按书籍分页查看。书籍与感悟保存在 PostgreSQL，同一入口可跨设备读取。保存失败保留草稿，未修改的请求重试不重复创建；改写后保存使用新的请求编号。每次成功保存追加一条记录，当前版本不提供覆盖编辑或删除历史记录。尚未保存的分书草稿保留于当前页面，刷新前请完成保存。

接口为 `/api/v1/paper/books` 及 `/{id}/reflections`，沿用既有网关。`V5__book_reflections.sql` 新增独立书籍和感悟表，并初始化首本书元数据，不修改交易账户/订单。部署更新 `paper-trading-service` 和 `frontend`，按需重启网关刷新地址。书架连接失败时仍可阅读内置解读，但不会假装已保存笔记。

## K 线买卖点与远端同步（2026-10-21）

模拟交易和个人总结的训练 K 线默认显示实际模拟成交。红色上箭头为买入（买开多、买平空），绿色下箭头为卖出（卖开空、卖平多）；小圆点使用含滑点的实际成交价。同根同方向的多笔成交合并标记，点击、悬停或键盘聚焦可逐笔查看合约、时间、手数、成本和成交原因。图例中可关闭买卖点，拖动或缩放可查看较早的成交。

标记来自同一次图表响应的独立成交流水，不受列表分页和账户最近 200 条记录限制，严格截止该响应的 asOf。只匹配实际合约及已观察的交易日；实时夜盘使用已观察的交易日标签，未完成日线、换月旧腿缺少对应合约 K 线时单独提示，不借用前一根或另一合约的价格轴。

同步远端 `a24e822` 后，个人训练的普通委托/推进限制、策略模拟与买卖点共同保留。个人训练迁移顺延为 V4，本机已执行的 V2/V3 不更名、不改校验和。若另一个环境已经执行远端原始的个人训练 V2，需要先核对其 Flyway 历史，不能直接套用本机迁移顺序。

## 策略模拟交易（2026-10-20）

在 `/paper` 点击“新建试验”，选择历史或实时模式，再选择模拟策略。保留手动交易，新增布林均值回归、放量动量突破、Dual Thrust、自适应 CTA、日线可用维度融合、买入持有六种策略。每个账户固定策略、开仓手数和 ATR 保护参数；换策略应新建对照试验，避免混合业绩。

历史单步/播放时，服务读取冻结且不晚于回放时点的信号日线，下一根真实交割合约日线撮合。保护使用实际交割合约 ATR，跨合约价差不计入风险波动；同根同时触及止盈止损时优先止损。买入持有不使用 ATR 保护。信号入场/退出规则与回测共享；模拟账户使用固定手数及其自身保护规则，不承诺与回测页资金比例、杠杆和移动保护设置的收益完全一致。

实时账户不再依赖完整回放档案，仅需真实交割合约报价及规格。休市或过期时允许刷新估值，不用缓存报价成交。实时刷新评估最近已完成日线，同根信号在数据库去重。“启动策略监测”在页面前台且保持打开时每10秒刷新，切换账户或卸载页面停止；这不是无人值守后台任务。实时自动移仓需要有效的新旧合约双腿报价并计入成本，缺任一腿即暂停提示。

策略面板展示决策依据、计提成本后的净收益和记录以来最大回撤。不同品种、区间、资金和手数不能直接排名。已有账户保持手动模式，冻结行情、订单和成交不重写；旧账户回撤从功能启用后的记录开始。

新增内部接口 `/internal/v1/simulation/strategy/evaluate`（无状态计算）和 `/internal/v1/simulation/live/{symbol}`（共享行情快照），不由公共网关暴露。`V2__paper_strategies.sql` 与保存风险日线合约标识的 `V3__signal_bar_contract_identity.sql` 均为向前兼容迁移；更新算法、模拟交易和前端三个服务。算法计算在账本事务外，写入前校验会话版本。

隔离集成测试使用无业务卷的临时 PostgreSQL，设置 `PAPER_TEST_JDBC_URL=jdbc:postgresql://127.0.0.1:<临时端口>/paper_test?currentSchema=paper_trading` 后运行 Maven 测试。`PaperLedgerIntegrationTests` 仅针对专用的 `paper_test` 数据库启用，会重置其 schema，禁止指向业务数据库。

## 1. 运行边界

生产请求路径为 `浏览器 → Nginx → Spring Cloud Gateway → Java 业务服务 → Python 算法服务`。PostgreSQL、PgBouncer、Redis 与 RocketMQ 位于内部数据网络，不应直接暴露到公网。Nacos、Gateway 和 Prometheus 在默认 Compose 中仅绑定 `127.0.0.1`；前端默认监听 `8088`。

前端和生产请求均不启用演示行情回退。实时接口不可达时保留最后一次可信观测并明确显示 `CACHED/DEGRADED`；首次采集尚未成功则显示不可用。

## 2. 本地启动

1. 复制 `infrastructure/.env.example` 为 `infrastructure/.env`。
2. 填写数据专用的 `TQSDK_USERNAME`、`TQSDK_PASSWORD`，并替换 PostgreSQL 密码、Nacos token 和身份值。不要在聊天、日志或 Git 中记录真实凭证。Nacos token 使用至少 32 字节随机值的 Base64 编码；`NACOS_ENABLED` 默认是 `false`，服务先使用 Compose 内的静态地址。Nacos 2.4.3 首次启动需要初始化管理员：在控制台按提示设置密码，或向 `/nacos/v1/auth/users/admin` 发送包含 `password` 的 POST 表单；同步更新 `.env` 中的 `NACOS_USERNAME=nacos` 和 `NACOS_PASSWORD`。管理员和配置通过 `nacos-data` 卷持久化，验证后再按需启用注册发现。
3. 在 `infrastructure` 目录执行：

   ```bash
   docker compose --env-file .env config
   docker compose --env-file .env up -d --build
   docker compose --env-file .env ps
   ```

4. 打开 `http://localhost:8088`。健康探针为 `http://127.0.0.1:18080/actuator/health/readiness`，行情通道状态为 `http://127.0.0.1:18080/api/v1/market/provider`，指标入口为 `http://127.0.0.1:9090`。

首次部署或需要刷新全品种日线仓库时，只使用 Docker 执行下列一次性任务。缓存写入 `data/history` 挂载目录，采用临时文件加原子替换；任务运行期间在线接口不会读到半写入文件。该目录是可重建运行数据，不提交到 Git。

```bash
docker compose --env-file .env run --rm --no-deps algorithm-service python scripts/download_history.py --all
docker compose --env-file .env run --rm --no-deps algorithm-service python scripts/download_history.py --status
```

停止服务使用 `docker compose --env-file .env down`。不要附加 `-v`，除非已经确认要永久删除数据库、缓存、消息和指标卷。

RocketMQ 的 `rocketmq-volume-init` 和 `rocketmq-topic-init` 容器会以退出码 0 完成卷权限及业务 Topic 初始化，这是正常状态。NameServer 与 Broker 配有健康探针，并使用与容器限额匹配的 JVM 内存。

行情、策略和模拟交易服务分别使用 PostgreSQL 的 `market`、`strategy` 和 `paper_trading` schema，各自维护 Flyway 迁移历史。Flyway 直连 PostgreSQL，业务查询仍经 PgBouncer，Hibernate 使用显式的默认 schema，避免事务连接池丢失会话级 search_path。

四个 Java 镜像共用相同的 Maven Reactor 构建步骤和 BuildKit 下载缓存，构建时运行全部 Java 测试。`backend/maven-settings.xml` 将依赖仓库统一到官方 Maven Central；下载中断后直接重跑构建即可复用缓存。Java 库的运行日志写入容器 `/tmp`，保持根文件系统只读。

若 Docker Desktop 的镜像加速源返回 403，可直接拉取官方仓库地址并恢复本地镜像标签，例如：

```bash
docker pull registry-1.docker.io/edoburu/pgbouncer:v1.24.1-p0
docker tag registry-1.docker.io/edoburu/pgbouncer:v1.24.1-p0 edoburu/pgbouncer:v1.24.1-p0
```

应用基础镜像和其他基础设施镜像可用同样方式处理；Docker Hub 的无命名空间镜像（如 `postgres`）需要在官方仓库地址中加上 `library/`。无需修改 Docker Desktop 的全局设置。

Python 服务默认由一个后台线程独占 TqSdk 数据会话，通过 `wait_update` 持续接收国内期货合约与主连行情；浏览器和 Java 服务只读取内存快照，不会按请求新建上游连接。访问品种时惰性订阅真实日 K，Java 随后将快照同步至 Redis/PostgreSQL。源数据时间保留在响应中，休市或断线后的 TqSdk 快照显示 `CACHED`。凭证缺失、认证失败或通道中断时，新浪公开目录与轮询行情仅作为兜底，并强制标记 `DEGRADED`，不会用生成价格填补缺口或冒充实盘。可通过 `/api/v1/market/provider` 检查 `configured`、`connected`、`lastEventAt` 和 `fallbackActive`；响应不包含凭证。

回测接口只接受可审计的 TqSdk 主力映射数据，不会退回演示日线。首次回测某品种时会下载最多 `TQSDK_BACKTEST_BARS` 根主连日线、逐日真实交割月映射、各交割合约独立 OHLC，以及合约乘数、最小变动价位、保证金和手续费规格。主连价格仅用于生成信号，成交、止损、估值与模拟交易历史均使用对应交割合约的真实价格；换月双腿由各自日线按交易日期对齐。未完成的交易日日 K 不进入回测，当日日 K 保守地在北京时间 16:00 后视为完成。结果缓存在 `data/history/tqsdk-roll`，默认 12 小时更新；`schema_version=2`、`price_basis=OBSERVED_DELIVERY_CONTRACT`，旧格式缓存会自动失效。指定起止日期时只要求该区间的交割月与换月证据，区间缓存单独保存，不会覆盖完整区间缓存。已缓存品种可独立读取，不等待其他品种冷下载。首次冷下载可能耗时数分钟，浏览器、Nginx 与网关回测链路均配置为 180 秒超时。

回测先按昨日信号在今日开盘成交、平旧合约并换月，再检查所持合约当天区间的止损，多空开仓当天也执行保护。价差只重置成本基准，不直接计入盈亏；手续费扣减后若保证金不足，系统会减少新合约整数手数。所选区间的任一交割合约或换月腿缺价时返回 503，不补造价格。夜盘预测按天勤交易日历或上游日 K 的交易日期合并，跨周末、节假日不按报价自然日期重复追加。升级不会改写旧回测报告或已固化的模拟会话，查看修复后的结果需要重新运行回测或新建历史试验。

模拟交易入口为 `http://localhost:8088/paper`。历史模式将真实 TqSdk 主力日线、逐日交割月映射、换月双腿价格和合约规格固化到独立会话账本；委托最早从下一根 K 线撮合，防止未来数据泄漏。实时模式只读取当前真实行情并在内部模拟成交，不连接或调用实盘交易账户。实时试验按当前交割月惰性订阅一份共享的 TqSdk 逐笔序列，页面每秒读取内存快照并显示买卖五档与最近成交；上游未提供的档位保持空值，绝不推算或补造。历史模式不展示伪造盘口。两种模式共用市价、限价、止损、撤单、整数手、保证金、手续费和不利滑点规则。开启自动换月时分别平旧合约、开新合约；缺少任一真实换月腿时会话进入错误状态，禁止补价。所有会话、委托、持仓和成交由 `paper_trading` schema 持久化；删除试验会经过二次确认，并由 PostgreSQL 外键级联永久删除该会话的场景、合约参数、换月、委托、持仓和成交记录。

Java 行情服务每 15 秒从 Python 的内部快照接口同步报价、日 K 和各月份合约至 `market` schema。相同观测时间幂等入库，日 K 修订会更新已有记录。浏览器查询其它合约时会将该合约加入采集列表；首次采集完成前可能显示模块级的“采集中”提示。

前端默认主力连续合约为 `CJM`，顶部全市场搜索与左侧最近访问列表共享同一选中状态。当前代码写入 URL 的 `symbol` 参数，刷新、跨页面导航和分享链接都保持同一品种。报价、历史、期限结构和预测独立加载，缺失期限结构不阻塞其它真实数据。Python 预测只使用已采集的真实报价与历史数据；首次暖机尚未采集到数据时返回 503。策略调用的重试共用 4 秒总预算，在浏览器和网关超时前回退至最近成功预测。缓存和上游的 `DEGRADED` 不会被提升为实时。

真实行情输入的预测带有 `+observed.2` 模型标记。升级前没有 observed 标记的历史预测仍保存在数据库中，但不会作为可信缓存或故障回源结果展示。没有可信结果时返回模块级不可用提示。相同合约、模型与行情时间会复用已有预测快照，避免休市缓存刷新时触发唯一约束。

### 本机临时 HTTPS 远程访问

保留本机完整系统，用独立的 `ai-quant-remote` Compose 项目运行带认证的 Caddy 入口和 Cloudflare Quick Tunnel；不需要服务器、域名或路由器端口转发。只有通过登录的业务页面和 API 可用，入口不发布本机端口，监控、Nacos 与 Actuator 路径均被阻止。远程密码不会转发到业务服务。浏览器到隧道使用 HTTPS；HTTP 请求先跳转 HTTPS，再要求认证。

首次运行（本机业务系统须已启动）：

```powershell
python scripts/setup_remote_access.py
./scripts/remote_access.ps1 -Action Start
```

脚本生成随机密码和 bcrypt 哈希，登录信息仅保存在 `infrastructure/remote-access/.credentials.json`，哈希放入同目录 `.env`；两者与运行地址 `.connection.json` 均被 Git 忽略，构建上下文也不包含凭据。Windows 自动限制凭据文件为当前用户与 SYSTEM 可读。重复初始化不会覆盖已有凭据。

```powershell
./scripts/remote_access.ps1 -Action Status  # 查看当前访问地址
./scripts/remote_access.ps1 -Action Stop    # 仅停止远程入口，保留本地系统和数据
```

首次访问显示浏览器账号密码提示。远程模拟账户与本机共用后端数据库；关注列表、模式偏好和本机复盘日志仍保存在各自浏览器，暂不跨设备同步。当前只有一个入口拥有者账号，不提供不同使用者之间的账本隔离。

本机必须保持开机、不休眠且 Docker 正常运行；停止或重新创建隧道后，旧地址可能失效，新地址用 `Status` 查询。Quick Tunnel 用于个人临时访问，没有可用性保证，固定域名和长期运行应使用正式 Tunnel 或云服务器。官方说明：https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/

外层代理保留原始 HTTPS 协议和 Host，Gateway 启用 `SERVER_FORWARD_HEADERS_STRATEGY=framework`；避免合法的远程同源请求被 CORS 拒绝。没有放宽为任意 Origin。部署后必须验证：匿名网页和 API 为401、合法登录及回测 POST 正常、其他 Origin 为403、管理路径为404。

### 个人总结与受控训练

`/personal` 使用现有模拟交易服务与数据库。升级时 Flyway 自动执行 `V4__personal_strategy_training.sql`，只增加版本、训练、事件与追加复盘表，不清空原账户。该迁移由远端的 V2 顺延为 V4，保留本机已执行的策略模拟 V2/V3 及其校验和。需重建 `paper-trading-service` 和 `frontend`；模拟交易容器替换并健康后重新启动网关，刷新 Docker 服务解析。

个人模块 API 位于 `/api/v1/paper/personal/`，继续经过原有网关和远程认证入口。没有新增公网端口。训练历史固定在会话中，复盘在服务器保存。现有单入口拥有者模型不隔离多人数据；不要向不可信人员共享该入口账号。

个人训练账户在普通模拟台可查看行情、流水及暂停/恢复，不能通过普通接口推进、下单、撤单或删除；这些动作必须由个人模块的受控决策路径完成。请求超时后保持同一命令 UUID 重试，不能通过换新 UUID 和旧游标重复下单。原有普通模拟账户保持原功能。

完整规则与训练示例见 `docs/research/personal-survival-strategy.md`。`GUIDED` 记录人的决定与检查单，`RULE_REPLAY` 只研究机器规则；自动执行不得统计为人的纪律评分。

## 3. 容量与高并发基线

- Nginx 对单 IP API 请求限制为 300 req/s，允许 600 请求突发，超限返回 429；生产应在边缘网关再配置租户级和身份级限流。
- 行情、策略 Java 实例的 Hikari 连接池上限为 30，模拟交易服务为 40；PgBouncer 接受 1000 客户端连接并以 transaction 模式复用 60 个数据库连接。
- 策略服务限制同时访问 Python 的调用数为 32，并对同合约的并发计算进行合并；队列容量为 200。
- Redis 设置 512 MiB 上限与 LRU 淘汰。缓存只用于提速，PostgreSQL 是持久化事实来源。
- Java 容器使用容器内存的 75% 作为 JVM 上限，并在 OOM 时立即退出，由编排器重启。

这些数值是可运行基线，不是生产容量承诺。上线前必须在目标硬件、真实数据分布和目标 SLO 下运行阶梯压测，并根据 PostgreSQL IOPS、算法耗时和 p95 调整副本数与池大小。

## 4. 生产覆盖项

- 在负载均衡器终止 TLS，启用 HSTS，并将前端端口限制在入口网络。
- 使用 Vault、Kubernetes Secret 或云密钥管理服务注入凭据；不要把真实秘密写入 Compose、镜像或 Git。
- PostgreSQL 使用托管高可用或主备部署，Redis 使用 Sentinel/Cluster，RocketMQ 使用多副本；Compose 的单节点模式只用于开发与验收。
- Nacos 使用外部 PostgreSQL、集群模式、强认证和最小权限命名空间。
- RocketMQ 本地编排允许自动建 Topic 以便启动；生产必须关闭自动创建，预先创建 `market-quote-updated` 与 `strategy-prediction-updated` 并设置 ACL。
- 为 Java、Python 和前端镜像生成 SBOM，经过镜像漏洞扫描后以 digest 固定部署。
- 设置至少两个 Gateway、Market、Strategy 和 Algorithm 副本，并通过就绪探针滚动发布。
- Prometheus 告警至少覆盖：5xx、p95/p99、线程池拒绝、连接池等待、熔断器打开、Redis 命中率、数据库连接与磁盘、RocketMQ 消费积压。

## 5. 备份与恢复

### PostgreSQL

每天执行加密的逻辑备份，生产环境同时开启 WAL 连续归档以支持时间点恢复。示例（在受控备份主机执行）：

```bash
pg_dump --format=custom --no-owner --dbname="$DATABASE_URL" --file="aiquant-$(date +%F).dump"
pg_restore --clean --if-exists --no-owner --dbname="$RESTORE_DATABASE_URL" aiquant-YYYY-MM-DD.dump
```

恢复必须先进入隔离实例，执行 Flyway 校验与核心查询抽样，再切换流量。每月至少完成一次恢复演练并记录 RPO/RTO。

### 其他状态

- Redis AOF 用于缩短开发环境重启后的预热时间，不替代 PostgreSQL 备份；丢失后允许冷启动重建。
- RocketMQ store 按消息保留期备份；业务必须能从 PostgreSQL 快照重放关键事件。
- Nacos 配置通过受控导出和基础设施代码保存，不依赖单节点卷作为唯一副本。

## 6. 故障与降级

| 故障 | 系统行为 | 操作 |
| --- | --- | --- |
| Python 超时/错误 | 有界重试后熔断；返回最近成功策略并标记 `DEGRADED` | 检查算法耗时、上游行情与熔断指标，禁止扩大超时掩盖拥塞 |
| Redis 不可用 | 回源 PostgreSQL；延迟上升但业务保持可读 | 观察数据库连接与 p95，修复 Redis 后分批预热 |
| PostgreSQL 不可用 | 缓存命中可短时读；无缓存请求失败 | 停止非必要写入，按主备或 PITR 手册恢复 |
| RocketMQ 不可用 | 核心同步 API 继续；事件发布降级 | 恢复 Broker 后检查积压和幂等消费 |
| 行情源中断 | 使用最后可信快照并标记 `CACHED/DEGRADED` | 核对时间戳，超过业务时效阈值时停止交易建议 |
| Nacos 不可用 | 已启动实例按静态环境地址运行；新实例注册失败 | 保持现有副本，恢复 Nacos 后再扩容 |

## 7. 发布与回滚

### 研究计划与风险试算（2.2）

策略页顶部提供实证研究、账户风险试算和本机复盘日志。默认实证模式只聚合可用实证维度，文化对照是显式可选模式；现有全维模型仍保留，并分别说明配置权重与缺数后的实际权重。覆盖率和指标内部评分不能解释为胜率，盈利概率校准始终单独展示。

### 多品种市场与大众使用体验

`/market` 是独立的多品种浏览页，支持名称/代码搜索、行业与交易所筛选、成交活跃/涨跌排序、卡片和列表视图、国内期货与海外参考切换。行情快照与品种目录独立加载，缺少报价的目录项保留“暂无有效报价”，不以零价补齐。个人关注列表保存在本机 `aiquant.market-watch.v1`，不是平台推荐持仓。

`/market/:symbol` 展示品种详情，报价和历史数据不再依赖预测成功；`/strategy` 为多品种研究方法入口，`/strategy/:symbol` 才进入具体研究与计划。旧的 `?symbol=` 链接保留其他参数和锚点后跳转详情；全局导航不附带当前品种，品种选择器只在详情显示。行情请求使用序号校验，快速切换时旧响应不能覆盖新选品种。

默认“简明模式”，可切到“专业模式”，偏好保存在本机 `aiquant.experience.v1`。简明模式显示通俗导览、价格折线、术语解释，并折叠风险试算、模型明细和回测参数；专业模式展开完整工具，切换不修改研究参数、算法或已有复盘记录。存储受限时提示偏好未保存。

`/learn` 提供浏览—理解金额风险—虚拟练习—研究方法的入门路径、术语解释、虚构合约的双向盈亏示例及三道带解释的学习题。示例金额不代表真实合约规格，学习完成不等于适当性或交易资格认证，不自动创建账户或下单。

本次只需构建并更新 `frontend` 容器；无后端接口、模型或数据库变更，保留行情连接、历史文件和模拟账本。

### 模拟账户创建与历史回放数据

历史模拟使用 `/api/v1/data/replay/status` 展示可用范围，目录只包含校验通过的真实交割合约日线、合约规格和换月双腿，不再把公共主连历史目录当作可成交数据目录。创建表单据此筛选品种和日期；公共行情存在但执行数据缺失的品种不能直接创建历史回放。

`/internal/v1/simulation/history/{symbol}` 优先读取已保存的、schema v2 且标明 `OBSERVED_DELIVERY_CONTRACT` 的完整回放数据，不依赖当前天勤连接。固定历史快照可超过行情刷新 TTL 使用，保留原始数据日期和采集时间；这项策略用于历史模拟与回测，不改变实时行情的时效要求。缺少缓存时仍要求天勤可用后拉取真实数据，不以连续价格伪装交割合约。档案还需通过合约规格、日期顺序、已完成日线、OHLC 与换月双腿校验。

模拟服务将上游数据不足、通道未就绪和连接超时转换为带说明的 400/503，不再变成无说明的 500。更新涉及 `algorithm-service`、`paper-trading-service` 和 `frontend`，无数据库迁移，不清空已有账本。修改历史数据读取代码后应重新运行固定参数审计并发布匹配源码指纹的验证报告。

实时仿真只接受标为 `FRESH` 且时间在过去60秒以内（未来偏差不超过10秒）的有效报价，缓存、降级或过期价格不能触发实时模拟成交。休市或天勤连接异常时使用历史时点回放。容器重建后如网关仍连接旧地址而返回连接拒绝，应在业务服务健康后执行 `docker compose restart --no-deps gateway-service` 更新连接与地址缓存。

回测和历史模拟共用 `load_execution_history`：先读取校验通过的真实交割合约档案，命中后不再查询当前主力映射或建立行情连接；档案缺失时才调用天勤下载。回测仍要求筛选后至少25根日线，保留实际数据时间、数据来源和成交合约，不将公共主连价格代替成交价。回测页面的数据覆盖提示、日期快捷范围也改为读取真实合约目录，公共行情总条数不再表示回测已就绪。

### 全市场总览与五类雷达

`/overview` 不依赖选中的单品种，也不等待单品种预测成功。首页展示主连市场广度、热门品种与板块、新闻雷达、原始线索雷达、策略条件雷达和外盘参考雷达。点击品种后进入对应行情或研究计划；总览隐藏单品种选择器。热门榜以成交手数排序，涨幅榜、跌幅榜和板块可切换，未覆盖品种不计入涨跌家数。

独立接口 `/api/v1/research/radar/{market|news|signals|overseas}` 分别读取已订阅主连快照、东方财富期货频道跨品种要闻、本地已完成日线和新浪外盘参考；线索雷达复用 `/api/v1/market/leads`。网页每60秒刷新可见页面，模块独立加载与重试；外源失败保留上次成功快照及原始时间，不把重新请求时间标为数据时间。新闻保留原文链接、收录频道与发布时间（源提供至分钟时不补造秒值），品种关联只按关键词提示。外盘含 CFD / 参考报价，标明单位、北京时间、来源与境内产业链关联，不等于交易所授权实时盘口或套利信号。

策略雷达扫描已缓存品种的空仓入场条件：20日通道突破+MA60+1.05倍成交量、15日布林带2.2倍标准差、4日Dual Thrust（k=0.5）+MA60，展示实际触发品种与阈值。只使用已完成且最近7天内的主连日线，不同步下载缺数品种、不模拟账户或假定实际成交。扫描覆盖率与失效条件单独呈现；此模块的触发数不是胜率，也不代表已完成策略盈利验证。

`/api/v1/research/context/{symbol}` 从已订阅快照读取实际交割合约、乘数、最小价位、保证金、手续费、涨跌停和到期日，同时结合交易日历、合约时段与报价时间区分休市缓存、交易中失效、断线和采集中。`POST /api/v1/research/plan` 重新读取研究资料并检查合约变化，以账户净值、单笔/单日/账户保护风险、其他持仓风险、保证金和名义敞口上限计算整数手数；默认值仅为可修改情景。实际保证金取观测每手金额与用户保证金率下限中的较高值，手数约束预留开仓手续费，风险计入双边手续费和滑点。规格缺失时拒绝补造，休市可准备情景但不产生新增动作。HOLD 按实际持仓区分空仓等待、持仓观察和超限减仓；行情失效时先要求核对资料。该功能不读取实盘账户、不提交订单。

计划保存时冻结合约、行情时间、研究模式、模型、风险输入和估算结果。复盘状态、手工实际盈亏和备注另存，不修改原始快照。同一计划重复保存不清除复盘记录。日志仅保存在当前浏览器，不跨设备同步；列表最多显示最近 100 条，导出包含全部记录，保存失败会提示备份而不自动删除旧记录。

若行情商在休市后清空最新价，合约规格仍单独保留；只有已确认休市时，才允许采用实际交割合约已完成日线收盘价准备情景，并显式标注 `COMPLETED_DAILY_CLOSE` 和原始日期。交易时段不以日线收盘价冒充有效最新报价，形成中的日线也不用于此替代。

`/api/v1/research/validation` 只读取已发布的固定参数报告；报告必须由 `scripts/publish_research_validation.py` 在真实数据复核完成后生成，并校验模型版本和源码指纹。缺少报告、版本不符和已完成回顾性复核分别呈现，不将工程检查或历史收益标为样本外通过。原始审计输入应保留 `run-summary.json`、8 个品种结果及固定参数；发布命令为 `python scripts/publish_research_validation.py --source <审计目录>`。输出保存在挂载历史目录下的 `validation/research-validation.json`。自定义回测可以按同一份已执行参数显式运行 `costMultiplier=2`，同时放大按手手续费、费率和不利滑点；编辑表单不会改变已冻结的成本对照。

1. 先运行 Python、Maven、前端测试与 `docker compose config`。
2. 先发布向后兼容的数据库迁移，再滚动业务服务，最后发布前端。
3. 每批观察错误率、p95、熔断与数据库等待至少一个完整业务高峰窗口。
4. 应用回滚使用上一已签名镜像；数据库只允许前向修复迁移，不自动执行破坏性降级脚本。

所有故障处理必须保留 trace ID、数据时间、版本号和操作者记录。交易相关页面的 `DEGRADED` 状态不能通过 CSS 或配置隐藏。
## 消息、历史事件与模拟图表验收

消息中心入口 `/news`，对应 `/api/v1/research/radar/news` 和
`/api/v1/research/events/study`。新闻逐源读取，某一路失败不会阻断其他来源。
七路来源为发改委、统计局、美联储、EIA、USDA NASS、上期所及东方财富。
来源页同时展示采集状态和条目更新程度；`READY` 仅说明本次能读到条目。
解读来自公开的标题关键词及产业链规则，需核对原文和反证，未生成交易指令。
新闻快照保存在 `HISTORY_CACHE_DIR/news/radar.json`，失败保留原始发布时间与采集时间。
源页面结构变化会显示失败或旧快照，需要维护适配器，不得用新采集时间冒充新事件。

模拟账户图表 `/api/v1/paper/sessions/{id}/chart?limit=240` 读取已保存的执行日线，
补充开户前的已核验背景档案。SQL 同时限制 `bar_index` 和 `market_time`；
返回的背景数据再过滤时间，冻结的执行条目优先，禁止展示回放时钟后的日线。
图表目前是日线，实时账户仍通过盘口查看当前行情，不能将历史图当作实时价格。
流水分页使用 `/api/v1/paper/sessions/{id}/records/{fills|orders}?page=1&pageSize=20`，
不再由前端截断最近200条来冒充全部流水。活动委托单独完整返回并在界面分页。

历史研究的范围、来源、时间精度、选择偏差和应用限制见
[事件来源研究](research/event-source-study.md)。页面价格窗口是主连描述性变化，
缺数不补造，不作实际合约收益或信息领先能力的证据。

## 前辈实盘研究

`/mentors` 展示具名人物、来源边界和公开赛方汇总；
`GET /api/v1/research/mentors` 返回版本化档案与描述性计算。
`algorithm_service/mentor_contest_snapshot.json` 是注明截止日的历史快照，
用 `python scripts/collect_mentor_contest.py` 显式更新后重新部署算法服务。
采集仅使用公开平台前端实际调用的接口，不填登录凭据，不猜测账户。
原始响应组合摘要用于版本核对，不代表主办方数字签名或身份认证。

`POST /api/v1/research/mentors/analyze-ledger` 只处理用户明确提交的CSV，
最多5000条、100万字符，不落盘保存，不访问用户附带的来源URL。
原始交易数据不得添加到请求日志；当前接口日志不记录请求体。
结果只做FIFO配对及已平仓分析，不认证账户归属；缺资金流与日终权益时，
账户收益率和回撤留空。学习笔记只在浏览器localStorage中保存，不跨设备同步。
研究口径及缺口见 [前辈证据研究](research/mentor-evidence-study.md)。

昵称是受支持的独立研究身份，不要求实名。扩展名单保存在
`algorithm_service/mentors_expansion.json`；原始资料、背景及昵称匹配待核分别标记。
`mentor_research.py` 按第二十届轻量组实际采集的公开账户记录生成三个昵称档案，
仅通过明确的公开账户ID对应汇总，不按昵称自动跨届、跨组拼接。
赛中排名和最终名次报道分开，转载榜单单独标记。
学习笔记使用档案ID分隔同名对象，旧具名笔记兼容保留。


新增 `mentor_historical_snapshot.json`（第十八届四个已对应昵称账户）及
`mentor_settlement_snapshot.json`（中证网三个独立账户资金表）。
分别用 `python scripts/collect_mentor_history.py` 和
`python scripts/collect_public_settlements.py` 显式采集，成功后重新部署算法服务。
采集脚本不请求未开放的成交明细，失败保留旧快照。
原始成功响应的规范JSON压缩归档保存在 `docs/research/data/`，
供离线核对；页面可导出已采集账户数据，资金表、日度记录和品种表均分页。
详细计数及权限边界见 [实盘数据采集与核验](research/mentor-data-acquisition.md)。


实盘操作库维护在 `algorithm_service/mentor_operations.json`，默认页面栏目为“实盘操作”。
收录已发生的操作/持仓披露，保留主体、年月/期间精度及原文位置，不自动转换为成交或补算收益。
早期冠军档案和操作库同文件维护；第十八/十九届新增账户在 `mentor_archive_snapshot.json`，
显式采集命令 `python scripts/collect_mentor_archive.py`，规范原始响应归档到 `docs/research/data/`。
不得按昵称跨届拼接，不得将操作指导或控制公司的账户自动归为个人完整业绩。
最新覆盖及证据边界见 [操作与往届扩展](research/mentor-operations-study.md)。

模拟交易品种扩展使用 `scripts/collect_replay_history.py`，与公共主连下载器分开。
在已配置行情凭证的算法容器内执行：
`docker compose --env-file infrastructure/.env -f infrastructure/docker-compose.yml exec -T algorithm-service python scripts/collect_replay_history.py --all --bars 600`。
也可用 `--symbols AG0,SC0,EC0` 选择品种。每个品种以独立进程采集，默认超时240秒；
原有通过校验的历史档案保留，新增档案经真实交割合约、合约规格及换月双腿校验后，
自动进入 `/api/v1/data/replay/status`，无需重启服务或修改已有账户。
失败品种保持不可回放，逐品种结果保存在历史缓存内的 `collection-status-*.json`。
新上市品种按实际历史长度展示，不承诺所有品种都有600根日线。
创建模拟账户支持名称/代码搜索、板块筛选、交易所分组和手动刷新数据目录；
筛选无结果时禁止提交，切换品种同步切换可用日期范围。已有账户不受筛选影响。

2026-10-18 本轮完成87个目录品种的采集检查：81个具备通过校验的执行档案，
由原8个扩展73个。普麦、早籼稻、油菜籽、粳稻、强麦、动力煤因换月数据不完整未开放。
多数新增档案包含599根已完成日线，覆盖2024-04-25至2026-10-16；较晚上市品种按实际区间提供。
苹果、丙烯、白银、集运欧线分别通过创建账户、240根背景K线、下一根日线模拟成交验收，
验收账户标记“品种扩充验收”并暂停；前端67项测试通过。

### 可执行策略工作流（2026-10-27）

入口为「策略 → 拖拽编排策略工作流」及 /strategy/workflows。支持行情、字段、指标、常量、持仓、算术、比较、逻辑、已有策略、风控和交易动作节点。可拖入节点、连接同类型端口、拖动位置、删除节点/连线、缩放/平移、撤销重做；输入端口重新连接会替换原有线，禁止循环。

先保存草稿，再校验/发布。草稿保存携带 expectedRevision 防止覆盖其他编辑；创建与发布携带稳定 clientRequestId，响应丢失可安全重试。已发布版本不可编辑，回测通过服务端版本接口取得规则，模拟账户冻结该版本的定义、引擎和风控。更改草稿不会更改已有试验；需要新建试验才能使用新版本。

公开 API 都在 /api/v1/paper/workflows：GET/POST 根路径、GET/PUT /{id}、POST /{id}/publish、GET /versions、GET /versions/{id}、POST /validate、POST /debug、POST /versions/{id}/backtest。创建模拟账户用 strategyId=WORKFLOW 和 workflowVersionId，手数与 ATR 参数以服务器保存的发布版本为准。

执行引擎 workflow-daily-v1 支持最多 40 个节点、120 条连线。指标周期 2–250，历史偏移 0–250；拒绝未来偏移、循环、缺输入、无效端口和未连接到动作的节点。没有脚本与网络节点。指标仅使用决策时点及以前的已完成日线；缺数据时预热，除零或数值异常时等待，同时满足多空开仓时等待。节点试算只返回计算值、条件状态和候选，不创建账户或订单。

当前工作流采用固定整数手数、入场交割合约 ATR 保护，ATR 倍数最多 4 位小数。回测下一根日线成交，保留费用、滑点及整数手数/保证金约束；日线同根触及止盈止损时先止损。模拟继续使用原撮合账本、行情新鲜度、参与量、去重和移仓规则，成交模型与回测有差异。实时监测依赖模拟页面打开并启动；不是后台常驻编排服务。内置策略节点可接自定义过滤，单独使用旧策略的行为不变。

V6 只新增工作流草稿、版本、会话快照和决策轨迹，不修改 V1–V5。部署需同时更新算法、模拟交易服务与前端。


### 自主研究档案（2026-10-27）

入口 /research，按 study=fu-regime、fu-mechanisms、daily-screen 分享批次。三个批次共 1390 个场景，API 位于 /api/v1/research/studies，全部只读：目录、详情、runs 分页筛选、runs/{id} 完整曲线/交易/决策、assets/{name} 白名单下载。第二轮明确为事后探索；这些规则的因果换月信号和风险预算手数不等同于现有工作流执行语义，不提供直接发布或实盘委托。

发布已有研究运行 python scripts/publish_research_library.py。程序只读取冻结源，不重跑研究；生成内容版本目录、只读 SQLite 和证据副本，最后原子替换 catalog.json。已存在的同版本不改写。应把完整 published 目录与源码一起部署；算法镜像内附带发布资料，Compose 另以只读目录绑定支持后续更新。不要手工覆盖已发布版本；旧版本链接继续可用。

GET /api/v1/research/studies/fu-regime/observation 从只读绑定目录读取当前 shadow-state.json；配置哈希不一致时拒绝显示。刷新页面只读取保存记录，不查询行情、不推进账本、不下单。download=true 可下载当前观察 JSON。当前没有自动更新任务；按需先运行 python scripts/refresh_fu_research_input.py，再运行 python scripts/advance_fu_observation.py --input .test-tmp/fu-latest-audited.json。不要对已有账本重新初始化。更新脚本会检查完成日线、原始历史前缀和冻结配置。
