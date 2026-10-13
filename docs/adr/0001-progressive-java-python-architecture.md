# ADR-0001: 采用 Java 业务服务与 Python 算法服务渐进架构

## Status

Accepted

## Context

现有十一维量化算法全部由 Python 实现，直接重写为 Java 会引入信号漂移、回归验证成本和上线风险；新平台同时需要 Spring Cloud Alibaba 的服务治理能力。

## Decision

业务入口、行情、策略编排、缓存、持久化和服务治理使用 Java；现有算法封装为无状态 Python HTTP 服务。Java 通过稳定契约调用算法服务，并持久化输入摘要、模型版本和输出结果。

## Consequences

### Positive

- 保留经过测试的算法行为，迁移风险较低。
- Python 算法与 Java 业务服务可独立扩容和发布。
- 可通过双跑与结果对照逐步迁移单个算法。

### Negative

- 多一种运行时和跨服务调用链。
- 需要维护接口契约与超时降级策略。

### Neutral

- 算法迁移不作为首期上线前置条件。

## Alternatives Considered

- 一次性重写全部算法为 Java：回归风险与交付成本过高。
- 继续使用单体 Python Web：无法满足既定服务治理方向。

