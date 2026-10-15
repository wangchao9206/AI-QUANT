# AI-QUANT 运行手册

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

停止服务使用 `docker compose --env-file .env down`。不要附加 `-v`，除非已经确认要永久删除数据库、缓存、消息和指标卷。

RocketMQ 的 `rocketmq-volume-init` 和 `rocketmq-topic-init` 容器会以退出码 0 完成卷权限及业务 Topic 初始化，这是正常状态。NameServer 与 Broker 配有健康探针，并使用与容器限额匹配的 JVM 内存。

行情与策略服务分别使用 PostgreSQL 的 `market` 和 `strategy` schema，各自维护 Flyway 迁移历史。Flyway 直连 PostgreSQL，业务查询仍经 PgBouncer，Hibernate 使用显式的默认 schema，避免事务连接池丢失会话级 search_path。

三个 Java 镜像共用相同的 Maven Reactor 构建步骤和 BuildKit 下载缓存，构建时运行全部 Java 测试。`backend/maven-settings.xml` 将依赖仓库统一到官方 Maven Central；下载中断后直接重跑构建即可复用缓存。Java 库的运行日志写入容器 `/tmp`，保持根文件系统只读。

若 Docker Desktop 的镜像加速源返回 403，可直接拉取官方仓库地址并恢复本地镜像标签，例如：

```bash
docker pull registry-1.docker.io/edoburu/pgbouncer:v1.24.1-p0
docker tag registry-1.docker.io/edoburu/pgbouncer:v1.24.1-p0 edoburu/pgbouncer:v1.24.1-p0
```

应用基础镜像和其他基础设施镜像可用同样方式处理；Docker Hub 的无命名空间镜像（如 `postgres`）需要在官方仓库地址中加上 `library/`。无需修改 Docker Desktop 的全局设置。

Python 服务默认由一个后台线程独占 TqSdk 数据会话，通过 `wait_update` 持续接收国内期货合约与主连行情；浏览器和 Java 服务只读取内存快照，不会按请求新建上游连接。访问品种时惰性订阅真实日 K，Java 随后将快照同步至 Redis/PostgreSQL。源数据时间保留在响应中，休市或断线后的 TqSdk 快照显示 `CACHED`。凭证缺失、认证失败或通道中断时，新浪公开目录与轮询行情仅作为兜底，并强制标记 `DEGRADED`，不会用生成价格填补缺口或冒充实盘。可通过 `/api/v1/market/provider` 检查 `configured`、`connected`、`lastEventAt` 和 `fallbackActive`；响应不包含凭证。

Java 行情服务每 15 秒从 Python 的内部快照接口同步报价、日 K 和各月份合约至 `market` schema。相同观测时间幂等入库，日 K 修订会更新已有记录。浏览器查询其它合约时会将该合约加入采集列表；首次采集完成前可能显示模块级的“采集中”提示。

前端默认主力连续合约为 `CJM`，顶部全市场搜索与左侧最近访问列表共享同一选中状态。当前代码写入 URL 的 `symbol` 参数，刷新、跨页面导航和分享链接都保持同一品种。报价、历史、期限结构和预测独立加载，缺失期限结构不阻塞其它真实数据。Python 预测只使用已采集的真实报价与历史数据；首次暖机尚未采集到数据时返回 503。策略调用的重试共用 4 秒总预算，在浏览器和网关超时前回退至最近成功预测。缓存和上游的 `DEGRADED` 不会被提升为实时。

真实行情输入的预测带有 `+observed.2` 模型标记。升级前没有 observed 标记的历史预测仍保存在数据库中，但不会作为可信缓存或故障回源结果展示。没有可信结果时返回模块级不可用提示。相同合约、模型与行情时间会复用已有预测快照，避免休市缓存刷新时触发唯一约束。

## 3. 容量与高并发基线

- Nginx 对单 IP API 请求限制为 300 req/s，允许 600 请求突发，超限返回 429；生产应在边缘网关再配置租户级和身份级限流。
- 每个 Java 业务实例的 Hikari 连接池上限为 30，PgBouncer 接受 1000 客户端连接并以 transaction 模式复用 60 个数据库连接。
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

1. 先运行 Python、Maven、前端测试与 `docker compose config`。
2. 先发布向后兼容的数据库迁移，再滚动业务服务，最后发布前端。
3. 每批观察错误率、p95、熔断与数据库等待至少一个完整业务高峰窗口。
4. 应用回滚使用上一已签名镜像；数据库只允许前向修复迁移，不自动执行破坏性降级脚本。

所有故障处理必须保留 trace ID、数据时间、版本号和操作者记录。交易相关页面的 `DEGRADED` 状态不能通过 CSS 或配置隐藏。
