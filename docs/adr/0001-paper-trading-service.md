# ADR-0001: 独立模拟交易服务

## Status
Accepted

## Context
模拟下单包含资金、委托、成交、持仓和回放时钟等强一致业务状态。现有 Python 服务负责算法与真实数据，市场服务负责行情查询，都不适合成为交易账本所有者。

## Decision
新增 Java `paper-trading-service`，使用独立 PostgreSQL `paper_trading` schema，并通过内部 HTTP 读取真实行情和历史数据。浏览器只通过 Gateway 访问该服务。

## Consequences

### Positive
- 订单与资金状态具有 ACID、一致锁顺序和完整审计。
- 实时模拟与历史回放复用撮合内核。
- 与实盘柜台物理隔离，不会误发真实委托。

### Negative
- 增加一个需要部署和监控的微服务。
- 日线回放不能还原 Tick 内成交顺序。

## Alternatives Considered
- 浏览器内模拟：状态不可信且不可恢复。
- Python 内模拟：破坏既定业务/算法职责边界。
