# AI-QUANT 平台重构设计

## 目标

将现有 Python 单进程看板升级为 Vue 3 前端、Spring Cloud Alibaba 业务服务与 Python 算法服务协作的平台，在保持十一维模型输出一致的前提下，提高可维护性、并发能力和故障隔离能力。

## 非功能基线

- 单集群支持约 1,000 名并发用户，核心读接口 p95 小于 300 ms。
- 核心接口错误率低于 0.1%，服务可用性目标 99.9%。
- 行情源或算法服务故障时展示最后一次可信结果，并明确标注缓存时间与降级状态。
- 所有请求带 Trace ID；提供健康检查、指标、结构化日志及慢请求观测。
- 键盘可操作、清晰焦点态、非颜色单一表达，主要界面满足 WCAG AA。

## 总体架构

```text
Vue 3 SPA
   |
Spring Cloud Gateway -- Nacos / Sentinel
   |-- Market Service ---- Redis ---- RocketMQ
   |       |                  |
   |       +------------ PostgreSQL
   |
   +-- Strategy Service -- Python Algorithm Service
                              |
                        Existing 11 engines
```

网关负责统一路由、跨域、追踪、限流和安全边界。Market Service 负责行情标准化和快照查询；Strategy Service 负责计算编排、结果缓存与历史持久化；Python Algorithm Service 复用现有十一维引擎，并保持无状态以支持横向扩容。

## 数据流与降级

1. 前端读取网关的聚合接口。
2. 服务优先返回 Redis 中的最新可信快照，并异步刷新数据。
3. 同一合约的并发计算进行请求合并，防止缓存击穿。
4. 外部行情与算法调用均设置超时、有限重试、熔断和舱壁隔离。
5. 成功结果写入 PostgreSQL；事件经 RocketMQ 异步分发，消费者以业务键保证幂等。
6. 依赖失败时返回带 `FRESH`、`CACHED` 或 `DEGRADED` 标识的数据，禁止伪装成实时结果。

## UI/UX 方向

设计语言借鉴 Apple 的克制、精确和内容优先，但不复制其品牌资产。使用暖白、石墨黑、低饱和蓝和语义红绿；以留白、排版、细分隔线和轻量层次替代紫色渐变、霓虹光晕和过度玻璃拟态。动效限制在 160–240 ms，并尊重 `prefers-reduced-motion`。

首期页面包括总览、市场、策略和系统状态。桌面端使用可收起侧栏，移动端使用底部导航。所有数据区具备加载、空、错误、重试和过期状态；行情价格、来源、更新时间及降级状态始终可见。

## 测试与验收

- Vue：组件、路由、状态和关键交互测试，生产构建与视觉截图检查。
- Java：单元测试、控制器切片、数据库集成及网关路由测试。
- Python：保留原回归测试，并新增 HTTP 契约与异常路径测试。
- 系统：端到端契约测试，以及缓存击穿、算法超时、数据库短故障和并发压测。

## 版本策略

采用 Java 17。Spring Cloud Alibaba 2025.0.x 对应 Spring Cloud 2025.0.x 与 Spring Boot 3.5.x；依赖通过 BOM 统一管理。生产部署必须使用已验证的补丁版本并执行依赖漏洞扫描。

## 参考

- https://sca.aliyun.com/en/docs/2025.x/overview/version-explain/
- https://github.com/alibaba/spring-cloud-alibaba

