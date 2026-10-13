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

## 本轮结果（2026-10-13）

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
