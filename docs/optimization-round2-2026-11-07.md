# 第二轮：运行数据归档、轻量部署与共享构建

2026-11-07。本轮为运维优化，没有新增数据库迁移。原有 19 个模拟会话、缠论证据和持久卷保留，SMTP 配置未变。

## 六个 Java 镜像共用一次构建

Compose 中 identity、gateway、market、strategy、paper-trading、chanlun 六个服务统一使用 `backend/Dockerfile` 的六个命名 target。一个 Maven Reactor 阶段运行全部 Java 测试并产出 JAR，各运行镜像只复制自己的产物。Maven 下载缓存继续使用 BuildKit cache mount；运行镜像使用 UID/GID 10001、JRE 17 和容器内存比例设置。

本次六镜像联合构建只执行了一个 Maven 阶段，Reactor 用时 45.163 秒。Java 测试共发现 116 项，70 项通过，46 项因未提供专用数据库环境而跳过，失败及错误均为 0。这个结果不包含旧数据库集成测试的执行，也不用于声称固定的构建加速倍数。各服务目录的旧 Dockerfile 保留为单独构建的兼容入口。

```powershell
# 在仓库根目录执行；沿用已保存的部署模式
python scripts/compose.py build identity-service gateway-service market-service strategy-service paper-trading-service chanlun-service
```

## 轻量模式

`infrastructure/docker-compose.light.yml` 在已有静态服务地址基础上省去 Nacos 的启动依赖。RocketMQ、Redis、Prometheus、算法服务和四个缠论 worker 全部保留。六个 Java 服务明确关闭 Nacos 注册发现，消息开关保持原值。基础 Compose 文件仍支持完整模式。

轻量覆盖文件使用 `!override`，要求 Docker Compose 2.24.4 或更新版本，依据 [Docker Compose 合并规则](https://docs.docker.com/reference/compose-file/merge/)。本机已用 Compose v5.3.1 解析并实际部署验证。

```powershell
python scripts/compose.py --mode light config --quiet
python scripts/compose.py --mode light --save-mode up -d --no-build --wait --wait-timeout 240
# 已运行过完整模式时，up 不会自动停止已有 Nacos，另行停止并保留卷
python scripts/compose.py --mode full stop nacos
python scripts/compose.py ps

# 恢复完整模式
python scripts/compose.py --mode full --save-mode up -d --no-build --wait --wait-timeout 240
```

首次部署先省去 `--no-build` 并添加 `--build`。包装脚本使用固定项目名 `ai-quant` 和绝对路径，成功后才按 `--save-mode` 保存本机模式；未保存时默认 full。保存文件被 Git 忽略。后续通过包装脚本更新可沿用 light；直接调用基础 Compose 文件仍会使用完整模型。若 `.env` 或当前进程启用了 `NACOS_ENABLED=true` 或设置了 `COMPOSE_PROFILES`，脚本拒绝 light，避免混用发现配置。

本机当前已保存 light，Nacos 容器停止、卷保留。实际业务及依赖服务健康，Prometheus 四个采集目标均为 up。本轮未测量同一负载下的宿主机内存差值，不提供节省内存的数值承诺。

## 运行数据保留与归档

新增 `scripts/data_retention.py`，仅使用 Python 标准库和现有 PostgreSQL 容器的 `psql`，不依赖宿主机数据库驱动。固定允许以下四类运行数据；保留期按 **created_at 入库时间**计算，迟到的旧观测不会刚入库就被归档。

| policy | 表 | 默认保留 | 最低可设 | 附加保护 |
| --- | --- | --- | --- | --- |
| quotes | market.market_quote_snapshot | 30 天 | 7 天 | 保留每个 symbol 最新 observed_at 的全部记录 |
| terms | market.market_term_snapshot | 90 天 | 7 天 | 保留每个 contract_symbol 最新 observed_at 的全部记录 |
| operations | identity.operation_log | 90 天 | 30 天 | 仅显式归档/裁剪 |
| audit | identity.audit | 365 天 | 90 天 | 仅显式归档/裁剪 |

不处理账户、模拟会话、订单、成交、冻结行情、工作流观察、监控事件、缠论结构或历史行情缓存。默认命令不删除源记录；本轮没有安装定时裁剪任务。

```powershell
# 只读预览，不创建归档目录
python scripts/data_retention.py plan
python scripts/data_retention.py plan --policy quotes --days 60

# 默认仓库外私有目录 C:\AiProject\ai-quant-archives；默认每批最多 1000 行
python scripts/data_retention.py archive --policy quotes --batch 1000

# 先审阅 plan、保留期和备份，再显式选择归档且裁剪
python scripts/data_retention.py archive --policy quotes --batch 1000 --prune

# 在维护窗口恢复指定归档，保留整个归档目录（含隐藏标记）
python scripts/data_retention.py restore --manifest "C:\AiProject\ai-quant-archives\quotes-<归档编号>.csv.json"
```

可以用 `--directory` 指向仓库外的专用空目录，用 `--container` 指定 PostgreSQL 容器。目录限制为当前 Windows 账户及 SYSTEM，Unix 为 0700；不把归档或凭证写入 Git。CSV 使用 PostgreSQL 的 UTF-8 COPY 格式，保留 NULL、空串、换行和 JSON 的语义，依据 [PostgreSQL 17 COPY 文档](https://www.postgresql.org/docs/17/sql-copy.html)。CSV 会 gzip 压缩，清单包含列结构、行数、保留期和两层 SHA-256 校验。

每批在 REPEATABLE READ 事务中锁定选中的源行，最多 5000 行。归档和清单写入、文件刷盘与校验全部完成后，`--prune` 才删除同批 ID；并发新增记录不在批次内。归档进程间使用事务级互斥锁；被其他表外键引用的表拒绝裁剪。锁等待上限 5 秒，单条语句与事务空闲上限 120 秒，数据库提交前失败则源数据事务回滚。

清单状态为 `ARCHIVED_SOURCE_RETAINED` 或 `PRUNED`。如果停在 `PREPARED`，可能是提交前中断，也可能是数据库已提交但状态更新前中断，必须核对源行与归档，不能仅凭状态自动重试裁剪。`.partial` 文件不代表有效归档。归档文件需另行备份；同盘归档不能代替异机备份。

恢复先校验文件、列结构与行数，再锁表导入；相同 ID、内容一致时重复恢复不会重复插入，内容冲突或列结构变化会拒绝恢复，不覆盖当前数据。序列不会回退。恢复会阻塞该表写入，因此安排在维护窗口。普通 DELETE 不保证立即缩小数据库文件，本轮不执行 VACUUM FULL 或删除持久卷。

## 验证记录

- Python 配置及边界检查 8 项通过，覆盖完整/轻量模型、持久卷、消息依赖、统一构建目标及发现配置冲突保护。
- 隔离 PostgreSQL 的 14 类协议检查通过，覆盖四类数据的归档/裁剪/恢复、最新快照保留、校验失败回滚、并发写入保留、重复恢复、冲突拒绝、序列保护、Unicode/换行/NULL/空串/JSON、损坏归档和结构漂移拒绝、外键保护。测试使用临时容器、内存文件系统且不接业务卷，结束后清理。
- 本机部署后的六个 Java JAR 与构建镜像哈希一致，均使用非 root 用户；前端资源和缠论源码配置也与当前构建/源码一致。
- 页面与公开配置返回 200，匿名业务请求返回 401；身份与网关指标族均存在。启动日志未发现 Nacos 连接错误或指标重复注册错误。
- 数据库备份已创建且可用 `pg_restore --list` 读取；19 个原会话和 schema 版本保持不变（identity V3、market V2、chanlun V8、paper_trading V9），全部持久挂载一致。
- 正式库四类策略的 eligibleRows 均为 0，只执行了 plan，没有裁剪正式数据。没有前端改动，本轮未重复进行浏览器视觉验收。

可复现检查：

```powershell
python -m pytest tests/test_deployment_modes.py tests/test_data_retention.py -q
python scripts/test_data_retention_protocol.py
```

脱敏结果保存于 `docs/research/data/optimization-round2-2026-11-07/`。精确日线可得时间和 SMTP 仍待后续处理。
