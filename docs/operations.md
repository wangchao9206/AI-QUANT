# AI-QUANT 运行手册

## 1. 运行边界

生产请求路径为 `浏览器 → Nginx → Spring Cloud Gateway → Java 业务服务 → Python 算法服务`。PostgreSQL、PgBouncer、Redis 与 RocketMQ 位于内部数据网络，不应直接暴露到公网。Nacos、Gateway 和 Prometheus 在默认 Compose 中仅绑定 `127.0.0.1`；前端默认监听 `8088`。

开发环境允许在实时接口不可达时显示演示快照，但页面始终显示“演示快照 / DEGRADED”。生产构建默认关闭该能力；不要设置 `VITE_ENABLE_DEMO_FALLBACK=true`。

## 2. 本地启动

1. 复制 `infrastructure/.env.example` 为 `infrastructure/.env`。
2. 替换 PostgreSQL 密码、Nacos token 和身份值。Nacos token 使用至少 32 字节随机值的 Base64 编码，不要提交 `.env`。`NACOS_ENABLED` 默认是 `false`，服务先使用 Compose 内的静态地址。首次启动后立即在 Nacos 中轮换默认管理员密码，同步更新 `NACOS_USERNAME/NACOS_PASSWORD`，验证后再设为 `true`。
3. 在 `infrastructure` 目录执行：

   ```bash
   docker compose --env-file .env config
   docker compose --env-file .env up -d --build
   docker compose --env-file .env ps
   ```

4. 打开 `http://localhost:8088`。健康探针为 `http://127.0.0.1:8080/actuator/health/readiness`，指标入口为 `http://127.0.0.1:9090`。

停止服务使用 `docker compose --env-file .env down`。不要附加 `-v`，除非已经确认要永久删除数据库、缓存、消息和指标卷。

## 3. 容量与高并发基线

- Nginx 对单 IP API 请求限制为 30 req/s，允许 60 请求突发；生产应在边缘网关再配置租户级和身份级限流。
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
- RocketMQ 本地编排允许自动建 Topic 以便启动；生产必须关闭自动创建，预先创建 `market.quote.updated` 与 `strategy.prediction.updated` 并设置 ACL。
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
