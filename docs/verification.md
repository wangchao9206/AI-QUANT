# AI-QUANT 验证记录

本文件记录可复现的验收命令。最终结果以 2026-10-13 当前工作区的实际执行输出为准；未执行或受环境限制的项目必须明确标注，不把静态配置当成运行验证。

## 验收目标

| 类别 | 门槛 |
| --- | --- |
| Python | 全量 pytest 通过 |
| Java | Maven Reactor 全模块测试通过 |
| 前端 | Vitest 全量通过，TypeScript/Vite 生产构建成功 |
| 依赖 | `npm audit` 无已知漏洞 |
| 编排 | `docker compose config --quiet` 成功 |
| API 压测 | 错误率 < 0.1%，p95 < 300 ms，p99 < 800 ms |
| 视觉 | 桌面 1440px 与移动 390px 无溢出，降级/演示状态清晰可见 |

## 命令

```bash
python -m pytest tests -q
backend/mvnw -f backend/pom.xml test
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend audit --audit-level=high
docker compose --env-file infrastructure/.env.example -f infrastructure/docker-compose.yml config --quiet
docker run --rm --network ai-quant_application -e BASE_URL=http://gateway-service:8080 \
  -v "$PWD/tests/load:/scripts:ro" grafana/k6:0.57.0 run /scripts/k6-smoke.js
```

## 前次验证结果（2026-10-13，Docker 部署前）

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| Python | 通过 | `17 passed`，71.49 秒；有 1 条上游 `httpx` 弃用警告 |
| Java | 代码阶段已通过，最终容器复验受限 | 前一批 Maven Reactor 8/8 模块成功；本机无 Java，本轮应通过 Docker 复验 |
| 前端单测 | 通过 | 5 个测试文件、11 项测试全部通过 |
| 前端构建 | 通过 | Vue TypeScript 检查和 Vite 构建成功；入口 JS 108.68 kB，gzip 42.29 kB |
| npm 安全审计 | 通过 | 官方 registry 返回 `found 0 vulnerabilities` |
| Compose 静态校验 | 通过 | Docker Compose v2.35.1，`config --quiet` 退出码 0 |
| 桌面视觉 | 通过 | 1440×1000；卡片内边距问题在检查中发现并修复 |
| 移动视觉 | 通过 | Edge 无头模式最小可靠布局宽度 500×900，命中移动断点；底部导航、双列指标和降级提示无横向裁切 |
| 生产失败态 | 通过 | 后端不可达时显示错误与重试，不加载演示数据 |
| 完整容器启动 | 未执行 | Codex 外部执行审批返回“工作区审批额度不足”；不是 Docker/Compose 错误 |
| k6 压测 | 未执行 | 本机未安装 k6；已提供固定版本容器命令，依赖完整容器栈启动 |
| Redis/算法故障演练 | 代码测试通过，运行演练未执行 | 单元测试覆盖缓存回源、算法失败降级、并发合并；真实容器停机演练依赖完整栈 |

视觉证据：

- `reports/ui-overview-desktop.png`
- `reports/ui-strategy-mobile.png`

## 待环境恢复后执行

以下命令不会在宿主机安装任何运行时；所有服务和 k6 都由 Docker 提供：

```bash
cd infrastructure
docker compose --env-file .env up -d --build
docker compose --env-file .env ps
cd ..
docker run --rm --network ai-quant_application \
  -e BASE_URL=http://gateway-service:8080 \
  -v "$PWD/tests/load:/scripts:ro" \
  grafana/k6:0.57.0 run /scripts/k6-smoke.js
```

压测完成后应补录 `http_req_duration` p50/p95/p99、`http_reqs` 吞吐、错误率，以及 Prometheus 中 Gateway、Market、Strategy、Algorithm、PostgreSQL 和 Redis 的 CPU/内存。未获得这些数字前，不声明具体生产容量。

## Docker 部署验收补录（2026-10-13）

本次在 Windows Docker Desktop 的 Linux 引擎上实际完成构建和启动。Docker Engine 29.6.2、Compose v5.3.1；本节覆盖上方前次验证中未执行的容器部署状态。

| 检查 | 实际结果 |
| --- | --- |
| Python 容器测试 | 17 项通过，4.25 秒；1 条 FastAPI/Starlette 上游弃用警告 |
| Java 容器构建及测试 | Reactor 全部成功；Gateway 1 项、Market 3 项、Strategy 4 项测试通过 |
| 前端 Linux 容器 | 11 项测试通过，1.66 秒；TypeScript/Vite 生产构建成功，npm ci 审计为 0 漏洞 |
| 编排与启动 | `docker compose config --quiet` 和 `up -d --no-build --pull never --wait` 均退出 0；12 个常驻服务正常，初始化容器退出 0 |
| 网页入口 | `http://localhost:8088/` 返回 200 |
| 网关与前端健康转发 | Gateway readiness 和前端 `/actuator/health` 均返回 200 / UP |
| 预测完整链路 | 前端 `/api/v1/predictions/CJ2701` 返回 200、FRESH、11 个维度；连续请求返回 CACHED |
| PostgreSQL 持久化 | `market` 与 `strategy` schema 独立迁移成功；实际预测写入 strategy_decision_snapshot |
| PgBouncer | 经连接池执行 SQL，数据库与用户均为 aiquant |
| RocketMQ | Broker 注册正常；strategy-prediction-updated Topic 队列最大偏移为 1，确认发布了实际消息 |
| Prometheus | 就绪接口 200；Gateway、Market、Strategy 三个抓取目标均为 up，无 lastError |
| 凭据 | 随机凭据保存于被 Git 忽略的 infrastructure/.env；Nacos 管理员初始化后使用随机密码验证登录成功 |

本次修复了 PgBouncer 镜像标签、YAML tmpfs 字符串解析、RocketMQ 卷权限和内存、Java 日志写入只读目录、Windows 锁文件缺失 Linux 原生组件、Flyway schema 与凭据配置、Resilience4j 版本混用、非法 RocketMQ Topic 名称，以及网关更新后前端需要刷新服务地址的问题。Java 构建改用共享 BuildKit Maven 缓存并运行完整测试，网络失败后可以复用下载结果。

行情服务尚未接入持续行情入库任务：新数据库的行情报价没有可信快照，历史和期限结构接口返回 200、空数组和 DEGRADED。这是当前应用的数据接入边界，不能将其标记为实时行情验收通过。预测接口的独立行情接入已实际验证。

本次未执行 k6 容量压测、故障停机演练或新的浏览器视觉验收，不声明生产容量。

## 行情接入与页面修复验收（2026-10-14）

本节更新上一节中“行情采集尚未接入”的边界。已接入新浪期货真实报价和日 K，默认 CJ2701；Python 后台采集并持久化，Java 定时同步 PostgreSQL。生产请求不再调用生成历史行情的旧函数，前端按模块独立加载。

| 验证 | 结果 |
| --- | --- |
| Python | 全量 20 项通过；行情缓存与 API 的 6 项测试在最后修改后再次通过 |
| Java | 全量 13 项通过；覆盖总超时、保留降级状态、重复行情幂等和拒绝旧生成价格回源 |
| 前端 | 14 项通过；生产构建通过；覆盖缺失报价不阻塞预测、慢预测不阻塞报价、切换合约不串数据 |
| 真实报价 | 前端报价接口 200；来源为新浪期货，保留行情源 2026-10-13 15:00（北京时间）的数据时间 |
| 历史与曲线 | 前端接口 200；CJ2701 近 30 天为 16 个观测点，CJ 曲线含 4 个交割月份 |
| 实际入库 | CJ2612/CJ2701/CJ2703/CJ2705 的真实日 K 分别为 198/175/141/98 条；各合约另有 1 条源报价，重复采集没有重复写入 |
| 预测 | 返回 200、11 个维度；正常休市状态为 CACHED，模型使用 observed 标记 |
| 超时演练 | 暂停算法容器并移除该合约缓存后，预测在 4047 ms 返回 200 / DEGRADED，数据时间保持不变；已恢复容器，恢复请求返回 CACHED |
| 断网缓存 | network=none 的隔离容器可从行情卷读取真实报价和 60 根真实日 K，明确标记 DEGRADED，不生成替代价格 |
| 消息 | market-quote-updated 已有实际队列偏移；Topic 通过初始化容器自动创建 |
| 浏览器 | 实际总览、市场、策略页面已显示报价、历史轨迹、合约梯度与 11 维策略；原全页 404 错误不再阻塞正常数据模块 |
| 重启后复验 | 容器恢复后曾出现宿主端口 ERR_EMPTY_RESPONSE，容器内部请求正常；重启 frontend 与 prometheus 后，宿主网页和监控均恢复 200，浏览器重新验证通过 |

仍不声明生产容量；新浪公网连接可能超时，失败时保留真实缓存并显式标记降级。初次采集尚未成功且没有持久化数据的合约，会显示模块级采集中或不可用提示。

## 全市场目录与全局导航验收（2026-10-15）

| 验证 | 结果 |
| --- | --- |
| 动态目录 | 新浪期货公开目录返回 5 个交易所分组、86 个品种、714 个可观察合约；目录状态 FRESH |
| 代表品种 | IFM、RBM、TM、SIM、CJM 的报价、历史和预测均返回 200 |
| 分析维度 | 上述代表品种均返回 11 个实证维度和 3 个文化维度；不可用的外部证据明确标为 UNAVAILABLE |
| 期限结构 | 一字母根代码 `T` 可查询，返回真实已观测合约，不再受红枣专用逻辑限制 |
| 并发基线 | 100 个报价/历史混合请求、30 并发全部返回 200；p50 277.2 ms、p95 401.5 ms、最大 508.6 ms |
| 全局导航 | 顶部可按中文名、代码和交易所搜索；侧栏保留当前及最近成功品种；URL `symbol` 参数跨页面保持 |
| 前端 | 6 个测试文件、14 项测试全部通过；Vue TypeScript 检查和 Vite 生产构建成功 |

该数字是当前本机 Docker 验收结果，不代表生产容量承诺。目录数量随交易所挂牌与公开数据源更新动态变化；公开目录中已停止报价的历史合约不会被伪造补值。
