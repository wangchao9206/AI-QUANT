# ADR-0002: 使用 PostgreSQL、Redis 与 RocketMQ 分层承载数据

## Status

Accepted

## Context

交易决策记录需要强一致审计，实时行情读取需要低延迟，高峰写入和跨服务通知需要削峰与解耦。

## Decision

PostgreSQL 保存合约、行情快照、策略决策与审计信息；Redis 保存热点快照和短期计算结果；RocketMQ 分发行情及策略事件。数据库记录是最终事实来源，缓存可重建，消息消费者必须幂等。

## Consequences

### Positive

- 事务、低延迟读取和异步吞吐各由适合的组件承担。
- 可独立扩缩容，并降低外部行情源压力。

### Negative

- 引入缓存一致性、消息积压和运维复杂度。
- 本地开发需要容器化基础设施。

### Neutral

- 首期采用缓存旁路模式，不引入分布式事务。

## Alternatives Considered

- 仅 PostgreSQL：实现简单，但热点读取和突发写入余量不足。
- Kafka：吞吐优秀，但与确定的 Alibaba 技术栈相比运维一致性较弱。

