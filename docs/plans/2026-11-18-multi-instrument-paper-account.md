# Multi-instrument paper account Implementation Plan

按实现、验证、Docker 部署的顺序执行。

**Goal:** 在同一实时手动模拟账户中切换并同时持有多个期货品种，真正共用现金、权益和保证金，保留现有成交及个人心得。

**Architecture:** 保留现有 `paper_session` 作为唯一资金账本；新增按账户及实际合约唯一的多品种持仓表，复用原委托、成交、私人心得表。旧单品种账户在用户首次添加/切换品种时事务性升级，迁移原持仓并给原挂单绑定原合约；历史回放、自动策略及受控计划/训练账户继续原流程。所有多品种写操作先锁同一资金账户，跨品种开仓共享可用资金，委托显式绑定实际合约。

**Tech Stack:** Java17/Spring/JDBC/Flyway/PostgreSQL，Python/FastAPI/TqSdk，Vue3/TypeScript/Vitest，现有Docker Compose。

---

## Scope and behavior

- 用户已确认先做好实时仿真；本次范围为实时手动账户。
- 单一账户资金只注入一次。现金=初始资金+累计已实现盈亏−手续费；权益=现金+全部合约浮动盈亏；可用资金=权益−全部持仓保证金−开仓挂单预留。
- 每个实际合约独立净持仓，禁止跨合约平仓或用另一品种的乘数、最小跳价和费用计算成交。保持现有净持仓方向规则。
- 切换图表/品种不创建第二份资金，不平掉其他持仓，不提交委托；下单发送明确的实际合约，切换竞态不得导致错单。
- 委托重试以同一账户clientOrderId幂等，变更交易内容复用同一ID需拒绝。挂单预留资金及平仓可用手数，撤单/拒绝/成交释放对应预留。
- 更新估值时读取全部持仓及挂单合约的真实批量行情，行情不可用/过期不补造价格。只撮合交易时段且报价有效的对应合约；已有陈旧观测明确标示。
- 原账户持仓、现金、成交流水、私人心得保留，升级不触发成交。所有新表启用租户RLS与租户/账户外键。

## Task 1: Schema and compatibility

Modify/Create: `backend/paper-trading-service/src/main/resources/db/migration/V16__multi_instrument_accounts.sql`, `api/PaperRequests.java`.
Add portfolio flag, order contract/reservation columns, tenant-scoped positions with per-contract specs and valuation timestamps. Keep old order request constructor compatible. Test migration from full existing schema and tenant/FK boundaries in disposable PostgreSQL.

## Task 2: Shared ledger and execution

Create `service/PaperPortfolioService.java`, `service/PortfolioLedger.java`; route eligible portfolio detail/order/refresh/cancel from `PaperTradingService`. Add select-instrument endpoint to `PaperTradingController`. Implement upgrade, shared funds locking, spec-specific net positions and execution, pending reservations, aggregate valuation. Test two-symbol concurrent funds exhaustion, independent close, multiplier/fee math, idempotency and upgrade preservation.

## Task 3: Batch market observations

Extend `algorithm_service/paper_strategy.py`, `algorithm_service/app.py` and `SimulationDataClient` with bounded actual-contract execution snapshots without daily history payloads or per-request SDK calls. Test exact-contract isolation, partial availability and stale/closed states.

## Task 4: Web interaction

Extend `frontend/src/services/api.ts` and `views/PaperTradingView.vue`; add account instrument picker and all-position table. Keep active position/quote for the order ticket, account-wide funds for wallet cards, explicit contract per order and independent close controls. Preserve all-position fills and notes. Tests cover switching without opening a new wallet, aggregate cash/margin, explicit contract and rejected stale responses.

## Task 5: Verify and deploy

Run Python, Java, frontend tests and production build. Back up the existing production database before migration; use isolated PostgreSQL for tests. Build and start existing Docker services, then use a disposable QA tenant to open/close two real-contract simulated positions, verify shared funds and persistence, notes and isolation. Clean only QA data. Do not reset administrator credentials or delete production volumes.
