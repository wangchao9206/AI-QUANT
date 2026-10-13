# ADR-0003: 使用 Apple 启发的 Vue 3 设计系统

## Status

Accepted

## Context

现有页面由单文件内联 CSS 生成，层级弱、状态不完整、移动端和无障碍支持不足，并呈现常见模板化数据大屏观感。

## Decision

使用 Vue 3、TypeScript、Vite、Pinia 和 Vue Router 构建独立 SPA。设计以内容优先、精确排版、克制层次和轻量动效为核心，建立显式设计令牌和可复用组件；不复制 Apple 商标、图形或产品页面。

## Consequences

### Positive

- 前端职责清晰，组件、状态和页面可独立测试。
- 统一令牌减少视觉漂移，响应式和无障碍能力可持续维护。

### Negative

- 增加 Node 构建链和前端发布产物。
- 高品质图表与状态处理需要更多初期实现工作。

### Neutral

- 首期不引入大型 UI 组件库，避免模板化观感和无用体积。

## Alternatives Considered

- 服务端模板：工程简单，但交互、状态与长期维护能力不足。
- React：生态广，但团队未指定其优先级，Vue 3 在当前项目中更直接。

