package com.aiquant.paper.service;

import com.aiquant.paper.api.PaperRequests.AdvanceRequest;
import com.aiquant.paper.api.PaperRequests.CreateSessionRequest;
import com.aiquant.paper.api.PaperRequests.PlaceOrderRequest;
import com.aiquant.paper.client.SimulationDataClient;
import com.aiquant.paper.client.SimulationDataClient.ContractSpec;
import com.aiquant.paper.client.SimulationDataClient.HistoricalBar;
import com.aiquant.paper.client.SimulationDataClient.QuoteSnapshot;
import com.aiquant.paper.client.SimulationDataClient.SimulationDataset;
import com.aiquant.paper.service.MatchingEngine.BarView;
import com.aiquant.paper.service.MatchingEngine.FillDecision;
import com.aiquant.paper.service.MatchingEngine.OrderView;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class PaperTradingService {
    private static final ZoneId SHANGHAI = ZoneId.of("Asia/Shanghai");

    private final JdbcTemplate jdbc;
    private final TransactionTemplate transactions;
    private final SimulationDataClient dataClient;
    private final MatchingEngine matchingEngine;

    public PaperTradingService(JdbcTemplate jdbc, TransactionTemplate transactions,
                               SimulationDataClient dataClient, MatchingEngine matchingEngine) {
        this.jdbc = jdbc;
        this.transactions = transactions;
        this.dataClient = dataClient;
        this.matchingEngine = matchingEngine;
    }

    public Map<String, Object> createSession(CreateSessionRequest request) {
        if (request.startDate() != null && request.endDate() != null
            && request.startDate().isAfter(request.endDate())) {
            throw new IllegalArgumentException("开始日期不能晚于结束日期");
        }
        String symbol = request.symbol().toUpperCase();
        boolean live = request.mode().equals("LIVE");
        LocalDate start = live ? LocalDate.now(ZoneOffset.UTC).minusDays(45) : request.startDate();
        SimulationDataset dataset = dataClient.history(symbol, start, request.endDate());
        List<HistoricalBar> bars = dataset.bars();
        HistoricalBar anchor = live ? bars.get(bars.size() - 1) : bars.get(0);
        ContractSpec spec = requiredSpec(dataset, anchor.contract());
        QuoteSnapshot liveQuote = null;
        if (live) {
            try {
                liveQuote = dataClient.quote(anchor.contract());
            } catch (RuntimeException ignored) {
                liveQuote = dataClient.latestQuoteOrNull(anchor.contract());
            }
        }
        Instant marketTime = liveQuote != null && liveQuote.dataTimestamp() != null ? liveQuote.dataTimestamp() : anchor.timestamp();
        BigDecimal marketPrice = liveQuote != null && liveQuote.price() != null ? liveQuote.price() : anchor.close();
        String source = liveQuote != null && liveQuote.source() != null ? liveQuote.source() : dataset.source();
        UUID sessionId = UUID.randomUUID();

        transactions.executeWithoutResult(status -> {
            jdbc.update("""
                insert into paper_trading.paper_session (
                    id, name, mode, symbol, status, data_source, data_timestamp,
                    initial_cash, cash_balance, equity, margin_rate, fee_rate,
                    slippage_ticks, max_participation_rate, auto_roll, current_bar_index,
                    total_bars, current_market_time, current_contract, current_price,
                    volume_multiple, price_tick, margin_per_lot, commission_per_lot
                ) values (?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, sessionId, request.name().trim(), request.mode(), symbol, source,
                Timestamp.from(marketTime), request.initialCash(), request.initialCash(),
                request.initialCash(), request.marginRate(), request.feeRate(), request.slippageTicks(),
                request.maxParticipationRate(), request.autoRoll(), live ? 0 : 0,
                live ? 0 : bars.size(), Timestamp.from(marketTime), anchor.contract(), marketPrice,
                spec.volumeMultiple(), spec.priceTick(), spec.marginPerLot(), spec.commissionPerLot());
            jdbc.update("""
                insert into paper_trading.paper_position
                    (session_id, contract, direction, lots, average_price)
                values (?, ?, 0, 0, 0)
                """, sessionId, anchor.contract());
            insertSpecs(sessionId, dataset.contractSpecs());
            if (!live) {
                insertBars(sessionId, bars);
                insertRolls(sessionId, dataset);
            }
        });
        return detail(sessionId);
    }

    public List<Map<String, Object>> listSessions() {
        return jdbc.queryForList("""
            select * from paper_trading.paper_session order by updated_at desc, id desc
            """).stream().map(this::sessionMap).toList();
    }

    public Map<String, Object> detail(UUID sessionId) {
        Map<String, Object> session;
        try {
            session = jdbc.queryForMap("""
                select * from paper_trading.paper_session where id = ?
                """, sessionId);
        } catch (EmptyResultDataAccessException exception) {
            throw new IllegalArgumentException("模拟会话不存在");
        }
        Map<String, Object> result = sessionMap(session);
        result.put("position", positionMap(jdbc.queryForMap(
            "select * from paper_trading.paper_position where session_id = ?", sessionId)));
        result.put("orders", orders(sessionId, 200, 0));
        result.put("activeOrders", orders(sessionId, Integer.MAX_VALUE, 0, true));
        result.put("fills", fills(sessionId, 200, 0));
        result.put("orderCount", jdbc.queryForObject("select count(*) from paper_trading.paper_order where session_id = ?", Long.class, sessionId));
        result.put("fillCount", jdbc.queryForObject("select count(*) from paper_trading.paper_fill where session_id = ?", Long.class, sessionId));
        result.put("managedTraining", isPersonalTraining(sessionId));
        return result;
    }

    public Map<String, Object> records(UUID sessionId, String kind, int page, int pageSize) {
        if (!List.of("orders", "fills").contains(kind) || page < 1 || pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("分页参数无效：页码至少为1，每页1至100条");
        }
        loadSession(sessionId, false);
        String table = kind.equals("orders") ? "paper_order" : "paper_fill";
        long total = jdbc.queryForObject("select count(*) from paper_trading." + table + " where session_id = ?", Long.class, sessionId);
        long offset = (long) (page - 1) * pageSize;
        return Map.of("page", page, "pageSize", pageSize, "total", total,
            "items", kind.equals("orders") ? orders(sessionId, pageSize, offset) : fills(sessionId, pageSize, offset));
    }

    public Map<String, Object> chart(UUID sessionId, int limit) {
        if (limit < 1 || limit > 1000) throw new IllegalArgumentException("K线数量必须在1至1000之间");
        Map<String, Object> session = loadSession(sessionId, false);
        Instant cutoff = instant(session.get("current_market_time"));
        int cursor = ((Number) session.get("current_bar_index")).intValue();
        // Freeze the clock before the remote read. A concurrent advance must not
        // reveal any scenario row beyond this response's recorded cursor.
        java.util.TreeMap<Instant, HistoricalBar> visible = new java.util.TreeMap<>();
        String contextStatus = "READY";
        String source = String.valueOf(session.get("data_source"));
        String contextSource = "";
        List<HistoricalBar> frozen = jdbc.query("""
            select * from paper_trading.paper_scenario_bar
            where session_id = ? and bar_index <= ? and market_time <= ?
            order by bar_index desc limit ?
            """, (rs, n) -> new HistoricalBar(rs.getTimestamp("market_time").toInstant(),
                rs.getString("contract"), rs.getBigDecimal("open_price"), rs.getBigDecimal("high_price"),
                rs.getBigDecimal("low_price"), rs.getBigDecimal("close_price"), rs.getLong("volume"),
                rs.getLong("open_interest")), sessionId, cursor, Timestamp.from(cutoff), limit);
        // Only supplement observations BEFORE the session started. Persisted
        // execution bars always take priority over a later archive revision.
        Instant first = null;
        if ("HISTORICAL".equals(session.get("mode"))) {
            first = jdbc.queryForObject("select min(market_time) from paper_trading.paper_scenario_bar where session_id = ?", Timestamp.class, sessionId).toInstant();
        }
        try {
            var context = dataClient.chart((String) session.get("symbol"), cutoff, limit);
            if (context != null && context.bars() != null) {
                contextSource = context.source();
                if ("LIVE".equals(session.get("mode"))) source = contextSource;
                for (var bar : context.bars()) {
                    if (!bar.timestamp().isAfter(cutoff) && (first == null || bar.timestamp().isBefore(first))) {
                        visible.put(bar.timestamp(), bar);
                    }
                }
            } else contextStatus = "UNAVAILABLE";
        } catch (RuntimeException failure) { contextStatus = "UNAVAILABLE"; }
        for (var bar : frozen) if (!bar.timestamp().isAfter(cutoff)) visible.put(bar.timestamp(), bar);
        var bars = visible.values().stream().skip(Math.max(0, visible.size() - limit)).toList();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("asOf", cutoff); result.put("barIndex", cursor); result.put("bars", bars);
        result.put("source", source); result.put("contextStatus", contextStatus);
        result.put("contextSource", contextSource);
        result.put("message", "已完成日线 · 实际合约原始OHLC；换月价差不代表交易收益。历史回放严格截止当前时点，成交按原撮合规则执行。");
        return result;
    }

    private List<Map<String, Object>> orders(UUID sessionId, int limit, long offset) {
        return orders(sessionId, limit, offset, false);
    }

    private List<Map<String, Object>> orders(UUID sessionId, int limit, long offset, boolean activeOnly) {
        return jdbc.query("select * from paper_trading.paper_order where session_id = ?"
            + (activeOnly ? " and status in ('PENDING', 'PARTIAL')" : "") + " order by created_at desc, id desc limit ? offset ?",
            (rs, rowNum) -> {
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("id", rs.getObject("id", UUID.class));
                item.put("clientOrderId", rs.getString("client_order_id"));
                item.put("side", rs.getString("side"));
                item.put("offset", rs.getString("offset_type"));
                item.put("orderType", rs.getString("order_type"));
                item.put("quantity", rs.getInt("quantity"));
                item.put("remainingQuantity", rs.getInt("remaining_quantity"));
                item.put("limitPrice", rs.getBigDecimal("limit_price"));
                item.put("stopPrice", rs.getBigDecimal("stop_price"));
                item.put("status", rs.getString("status"));
                item.put("rejectionReason", rs.getString("rejection_reason"));
                item.put("createdAt", rs.getTimestamp("created_at").toInstant());
                return item;
            }, sessionId, limit, offset);
    }

    private List<Map<String, Object>> fills(UUID sessionId, int limit, long offset) {
        return jdbc.query("select * from paper_trading.paper_fill where session_id = ? order by market_time desc, created_at desc, id desc limit ? offset ?",
            (rs, rowNum) -> {
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("id", rs.getObject("id", UUID.class));
                item.put("orderId", rs.getObject("order_id", UUID.class));
                item.put("eventType", rs.getString("event_type"));
                item.put("contract", rs.getString("contract"));
                item.put("side", rs.getString("side"));
                item.put("offset", rs.getString("offset_type"));
                item.put("quantity", rs.getInt("quantity"));
                item.put("marketPrice", rs.getBigDecimal("market_price"));
                item.put("fillPrice", rs.getBigDecimal("fill_price"));
                item.put("fee", rs.getBigDecimal("fee"));
                item.put("slippageCost", rs.getBigDecimal("slippage_cost"));
                item.put("realizedPnl", rs.getBigDecimal("realized_pnl"));
                item.put("reason", rs.getString("reason"));
                item.put("marketTime", rs.getTimestamp("market_time").toInstant());
                return item;
            }, sessionId, limit, offset);
    }
    public void deleteSession(UUID sessionId) {
        requireUnmanaged(sessionId);
        int deleted = jdbc.update("delete from paper_trading.paper_session where id = ?", sessionId);
        if (deleted == 0) throw new IllegalArgumentException("模拟试验不存在或已删除");
    }

    public Map<String, Object> placeOrder(UUID sessionId, PlaceOrderRequest request) {
        requireUnmanaged(sessionId);
        return placeOrderCore(sessionId, request);
    }

    Map<String, Object> trainingOrder(UUID sessionId, PlaceOrderRequest request) {
        if (!isPersonalTraining(sessionId)) throw new IllegalStateException("训练不存在");
        return placeOrderCore(sessionId, request);
    }

    private Map<String, Object> placeOrderCore(UUID sessionId, PlaceOrderRequest request) {
        validateOrderRequest(request);
        Map<String, Object> snapshot = loadSession(sessionId, false);
        BarState liveBar = null;
        if ("LIVE".equals(snapshot.get("mode"))) {
            QuoteSnapshot quote = dataClient.quote((String) snapshot.get("current_contract"));
            liveBar = new BarState(
                intValue(snapshot.get("current_bar_index")), quote.dataTimestamp(),
                (String) snapshot.get("current_contract"), quote.price(), quote.price(),
                quote.price(), quote.price(), Long.MAX_VALUE / 4
            );
        }
        BarState finalLiveBar = liveBar;
        transactions.executeWithoutResult(status -> {
            Map<String, Object> session = loadSession(sessionId, true);
            if (!"ACTIVE".equals(session.get("status"))) {
                throw new IllegalStateException("会话当前不是可交易状态");
            }
            Integer existing = jdbc.queryForObject("""
                select count(*) from paper_trading.paper_order
                where session_id = ? and client_order_id = ?
                """, Integer.class, sessionId, request.clientOrderId());
            if (existing != null && existing > 0) return;

            UUID orderId = UUID.randomUUID();
            int eligibleIndex = intValue(session.get("current_bar_index"))
                + ("HISTORICAL".equals(session.get("mode")) ? 1 : 0);
            jdbc.update("""
                insert into paper_trading.paper_order (
                    id, session_id, client_order_id, side, offset_type, order_type,
                    quantity, remaining_quantity, limit_price, stop_price, status, eligible_bar_index
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                """, orderId, sessionId, request.clientOrderId(), request.side(), request.offset(),
                request.orderType(), request.quantity(), request.quantity(), request.limitPrice(),
                request.stopPrice(), eligibleIndex);
            if (finalLiveBar != null) {
                updateMarket(sessionId, finalLiveBar);
                matchPending(sessionId, finalLiveBar);
            }
        });
        return detail(sessionId);
    }

    public Map<String, Object> cancelOrder(UUID sessionId, UUID orderId) {
        requireUnmanaged(sessionId);
        int updated = jdbc.update("""
            update paper_trading.paper_order set status = 'CANCELLED', updated_at = now()
            where id = ? and session_id = ? and status in ('PENDING', 'PARTIAL')
            """, orderId, sessionId);
        if (updated == 0) throw new IllegalStateException("委托不存在或已无法撤销");
        return detail(sessionId);
    }

    public Map<String, Object> advance(UUID sessionId, AdvanceRequest request) {
        requireUnmanaged(sessionId);
        return advanceCore(sessionId, request);
    }

    Map<String, Object> trainingAdvance(UUID sessionId) {
        if (!isPersonalTraining(sessionId)) throw new IllegalStateException("训练不存在");
        return advanceCore(sessionId, new AdvanceRequest(1));
    }

    private Map<String, Object> advanceCore(UUID sessionId, AdvanceRequest request) {
        for (int step = 0; step < request.steps(); step++) {
            Map<String, Object> snapshot = loadSession(sessionId, false);
            if ("LIVE".equals(snapshot.get("mode"))) {
                QuoteSnapshot quote = dataClient.quote((String) snapshot.get("current_contract"));
                BarState bar = new BarState(
                    intValue(snapshot.get("current_bar_index")), quote.dataTimestamp(),
                    (String) snapshot.get("current_contract"), quote.price(), quote.price(),
                    quote.price(), quote.price(), Long.MAX_VALUE / 4
                );
                transactions.executeWithoutResult(status -> {
                    Map<String, Object> locked = loadSession(sessionId, true);
                    if (!"ACTIVE".equals(locked.get("status"))) return;
                    updateMarket(sessionId, bar);
                    matchPending(sessionId, bar);
                });
                break;
            }
            Boolean moved = transactions.execute(status -> advanceHistoricalOnce(sessionId));
            if (!Boolean.TRUE.equals(moved)) break;
        }
        return detail(sessionId);
    }

    public Map<String, Object> setPaused(UUID sessionId, boolean paused) {
        int updated = jdbc.update("""
            update paper_trading.paper_session
            set status = ?, updated_at = now(), version = version + 1
            where id = ? and status not in ('COMPLETED', 'ERROR')
            """, paused ? "PAUSED" : "ACTIVE", sessionId);
        if (updated == 0) throw new IllegalStateException("会话无法切换状态");
        return detail(sessionId);
    }

    private boolean advanceHistoricalOnce(UUID sessionId) {
        Map<String, Object> session = loadSession(sessionId, true);
        if (!"ACTIVE".equals(session.get("status"))) return false;
        int nextIndex = intValue(session.get("current_bar_index")) + 1;
        if (nextIndex >= intValue(session.get("total_bars"))) {
            jdbc.update("update paper_trading.paper_session set status='COMPLETED', updated_at=now() where id=?", sessionId);
            return false;
        }
        BarState bar = loadBar(sessionId, nextIndex);
        if (!handleContractTransition(sessionId, session, bar)) return false;
        updateMarket(sessionId, bar);
        matchPending(sessionId, bar);
        return true;
    }

    private void matchPending(UUID sessionId, BarState bar) {
        Map<String, Object> session = loadSession(sessionId, true);
        List<OrderState> orders = jdbc.query("""
            select * from paper_trading.paper_order
            where session_id = ? and status in ('PENDING', 'PARTIAL') and eligible_bar_index <= ?
            order by created_at, id
            for update
            """, (rs, rowNum) -> new OrderState(
                rs.getObject("id", UUID.class), rs.getString("side"), rs.getString("offset_type"),
                rs.getString("order_type"), rs.getInt("remaining_quantity"),
                rs.getBigDecimal("limit_price"), rs.getBigDecimal("stop_price")
            ), sessionId, bar.index());
        for (OrderState order : orders) {
            FillDecision decision = matchingEngine.match(
                new OrderView(order.side(), order.orderType(), order.remaining(), order.limitPrice(), order.stopPrice()),
                new BarView(bar.open(), bar.high(), bar.low(), bar.close(), bar.volume()),
                decimal(session.get("price_tick")), decimal(session.get("slippage_ticks")),
                decimal(session.get("max_participation_rate"))
            );
            if (decision.fillable()) executeFill(sessionId, session, order, bar, decision);
            session = loadSession(sessionId, true);
        }
        if (isPersonalTraining(sessionId)) protectTrainingPosition(sessionId, bar);
        updateValuation(sessionId, bar.close());
    }

    private void executeFill(UUID sessionId, Map<String, Object> session, OrderState order,
                             BarState bar, FillDecision decision) {
        PositionState position = loadPosition(sessionId, true);
        int direction = order.side().equals("BUY") ? 1 : -1;
        int multiplier = intValue(session.get("volume_multiple"));
        BigDecimal fee = fee(decision.fillPrice(), decision.quantity(), multiplier,
            decimal(session.get("commission_per_lot")), decimal(session.get("fee_rate")));
        BigDecimal slippageCost = decision.fillPrice().subtract(decision.marketPrice()).abs()
            .multiply(BigDecimal.valueOf(multiplier * (long) decision.quantity()));
        BigDecimal cash = decimal(session.get("cash_balance"));
        BigDecimal realized = BigDecimal.ZERO;
        int newDirection;
        int newLots;
        BigDecimal newAverage;

        if (order.offset().equals("OPEN")) {
            if (isPersonalTraining(sessionId) && !trainingEntryAllowed(sessionId, session, position, decision, bar, direction)) {
                rejectOrder(order.id(), "个人策略保护：禁止加仓、失效跳空或超过冻结风险/敞口预算");
                return;
            }
            if (position.direction() != 0 && position.direction() != direction) {
                rejectOrder(order.id(), "反向开仓前必须先平掉现有持仓");
                return;
            }
            if (position.direction() != 0 && !position.contract().equals(bar.contract())) {
                rejectOrder(order.id(), "当前持仓合约与行情合约不一致");
                return;
            }
            newDirection = direction;
            newLots = position.lots() + decision.quantity();
            newAverage = position.lots() == 0
                ? decision.fillPrice()
                : position.averagePrice().multiply(BigDecimal.valueOf(position.lots()))
                    .add(decision.fillPrice().multiply(BigDecimal.valueOf(decision.quantity())))
                    .divide(BigDecimal.valueOf(newLots), 6, RoundingMode.HALF_UP);
            BigDecimal requiredMargin = marginPerLot(decision.fillPrice(), multiplier, session)
                .multiply(BigDecimal.valueOf(newLots));
            BigDecimal unrealized = unrealized(position, bar.close(), multiplier);
            BigDecimal equityBefore = cash.add(unrealized);
            if (equityBefore.subtract(fee).compareTo(requiredMargin) < 0) {
                rejectOrder(order.id(), "可用资金不足，无法缴纳保证金和手续费");
                return;
            }
            cash = cash.subtract(fee);
        } else {
            if (position.direction() == 0 || position.direction() == direction) {
                rejectOrder(order.id(), "平仓方向与当前持仓不匹配");
                return;
            }
            if (decision.quantity() > position.lots()) {
                rejectOrder(order.id(), "平仓手数超过可用持仓");
                return;
            }
            realized = BigDecimal.valueOf(position.direction())
                .multiply(decision.fillPrice().subtract(position.averagePrice()))
                .multiply(BigDecimal.valueOf(multiplier * (long) decision.quantity()));
            cash = cash.add(realized).subtract(fee);
            newLots = position.lots() - decision.quantity();
            newDirection = newLots == 0 ? 0 : position.direction();
            newAverage = newLots == 0 ? BigDecimal.ZERO : position.averagePrice();
        }

        BigDecimal margin = newLots == 0 ? BigDecimal.ZERO
            : marginPerLot(bar.close(), multiplier, session).multiply(BigDecimal.valueOf(newLots));
        BigDecimal unrealized = newLots == 0 ? BigDecimal.ZERO
            : BigDecimal.valueOf(newDirection).multiply(bar.close().subtract(newAverage))
                .multiply(BigDecimal.valueOf(multiplier * (long) newLots));
        jdbc.update("""
            update paper_trading.paper_position
            set contract=?, direction=?, lots=?, average_price=?, margin_occupied=?, unrealized_pnl=?, updated_at=now()
            where session_id=?
            """, bar.contract(), newDirection, newLots, newAverage, margin, unrealized, sessionId);
        int remaining = order.remaining() - decision.quantity();
        jdbc.update("""
            update paper_trading.paper_order
            set remaining_quantity=?, status=?, updated_at=now() where id=?
            """, remaining, remaining == 0 ? "FILLED" : "PARTIAL", order.id());
        jdbc.update("""
            insert into paper_trading.paper_fill (
                id, session_id, order_id, event_type, contract, side, offset_type, quantity,
                market_price, fill_price, fee, slippage_cost, realized_pnl, reason, market_time
            ) values (?, ?, ?, 'ORDER', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, UUID.randomUUID(), sessionId, order.id(), bar.contract(), order.side(), order.offset(),
            decision.quantity(), decision.marketPrice(), decision.fillPrice(), fee, slippageCost,
            realized, "模拟撮合：真实行情路径与保守成交规则", Timestamp.from(bar.marketTime()));
        BigDecimal equity = cash.add(unrealized);
        jdbc.update("""
            update paper_trading.paper_session
            set cash_balance=?, equity=?, realized_pnl=realized_pnl+?,
                commission_paid=commission_paid+?, slippage_paid=slippage_paid+?,
                updated_at=now(), version=version+1 where id=?
            """, cash, equity, realized, fee, slippageCost, sessionId);
    }

    private boolean handleContractTransition(UUID sessionId, Map<String, Object> session, BarState bar) {
        String currentContract = (String) session.get("current_contract");
        if (currentContract.equals(bar.contract())) return true;
        PositionState position = loadPosition(sessionId, true);
        if (isPersonalTraining(sessionId)) {
            // A roll is an execution boundary, not a new discretionary entry.
            // Flatten using the independently observed OLD leg, then wait again.
            if (position.lots() > 0) {
                Map<String,Object> roll;
                try {
                    roll=jdbc.queryForMap("select * from paper_trading.paper_roll_event where session_id=? and execution_date=? and from_contract=? and to_contract=?",
                        sessionId, LocalDate.ofInstant(bar.marketTime(),SHANGHAI),position.contract(),bar.contract());
                } catch (EmptyResultDataAccessException missing) {
                    jdbc.update("update paper_trading.paper_session set status='ERROR' where id=?",sessionId);
                    return false;
                }
                BigDecimal oldOpen=decimal(roll.get("old_open"));
                BarState oldBar=new BarState(bar.index(),bar.marketTime(),position.contract(),oldOpen,oldOpen,oldOpen,oldOpen,Long.MAX_VALUE/4);
                trainingClose(sessionId,session,position,oldBar,"MARKET",null,"换月边界按旧合约真实开盘平仓，不自动重开");
            }
            jdbc.update("update paper_trading.paper_order set status='CANCELLED',updated_at=now() where session_id=? and status in ('PENDING','PARTIAL')",sessionId);
            jdbc.update("update paper_trading.personal_training set stop_price=null where session_id=?",sessionId);
            applySpec(sessionId,bar.contract());
            return true;
        }
        if (position.direction() != 0) {
            if (!booleanValue(session.get("auto_roll"))) {
                jdbc.update("update paper_trading.paper_session set status='PAUSED', updated_at=now() where id=?", sessionId);
                return false;
            }
            if (!autoRoll(sessionId, session, position, bar)) return false;
        }
        applySpec(sessionId, bar.contract());
        return true;
    }

    private boolean isPersonalTraining(UUID id) {
        Integer count=jdbc.queryForObject("select count(*) from paper_trading.personal_training where session_id=?",Integer.class,id);
        return count!=null && count>0;
    }

    private void requireUnmanaged(UUID id) {
        if (isPersonalTraining(id)) throw new IllegalStateException("此账户属于个人策略受控训练，请到个人总结操作；禁止绕过保护或改写训练记录");
    }

    private boolean trainingEntryAllowed(UUID id, Map<String,Object> session, PositionState position,
                                         FillDecision fill,BarState bar,int direction) {
        var run=jdbc.queryForMap("select stop_price,risk_budget,rules,risk_halted from paper_trading.personal_training where session_id=?",id);
        if(position.lots()>0 || booleanValue(run.get("risk_halted")) || run.get("stop_price")==null || fill.fillPrice().signum()<=0) return false;
        BigDecimal stop=decimal(run.get("stop_price"));
        if(bar.open().subtract(stop).multiply(BigDecimal.valueOf(direction)).signum()<=0) return false;
        int multiplier=intValue(session.get("volume_multiple"));
        BigDecimal distance=fill.fillPrice().subtract(stop).multiply(BigDecimal.valueOf(direction));
        if(distance.signum()<=0) return false;
        BigDecimal lots=BigDecimal.valueOf(fill.quantity());
        BigDecimal costs=fee(fill.fillPrice(),fill.quantity(),multiplier,decimal(session.get("commission_per_lot")),decimal(session.get("fee_rate"))).multiply(BigDecimal.valueOf(2))
            .add(decimal(session.get("price_tick")).multiply(decimal(session.get("slippage_ticks"))).multiply(BigDecimal.valueOf(2L*multiplier)).multiply(lots));
        BigDecimal risk=distance.multiply(BigDecimal.valueOf(multiplier)).multiply(lots).add(costs);
        BigDecimal equity=decimal(session.get("equity"));
        BigDecimal maxMargin=jdbc.queryForObject("select (rules->>'maxMarginPct')::numeric from paper_trading.personal_training where session_id=?",BigDecimal.class,id);
        return risk.compareTo(decimal(run.get("risk_budget")))<=0
            && marginPerLot(fill.fillPrice(),multiplier,session).multiply(lots).add(costs).compareTo(equity.multiply(maxMargin).movePointLeft(2))<=0
            && fill.fillPrice().multiply(BigDecimal.valueOf(multiplier)).multiply(lots).compareTo(equity.multiply(BigDecimal.valueOf(2)))<=0;
    }

    private void protectTrainingPosition(UUID id,BarState bar) {
        PositionState position=loadPosition(id,true);
        if(position.lots()==0) return;
        BigDecimal stop=jdbc.queryForObject("select stop_price from paper_trading.personal_training where session_id=?",BigDecimal.class,id);
        if(stop==null || stop.signum()<=0) throw new IllegalStateException("受控训练持仓缺少有效保护，已回滚本次推进");
        trainingClose(id,loadSession(id,true),position,bar,"STOP",stop,"个人策略结构/跟踪保护；日内路径未知时按同根入场后可能触发止损保守处理");
    }

    private void trainingClose(UUID id,Map<String,Object> session,PositionState position,BarState bar,String type,BigDecimal stop,String reason) {
        String side=position.direction()>0?"SELL":"BUY";
        FillDecision fill=matchingEngine.match(new OrderView(side,type,position.lots(),null,stop),
            new BarView(bar.open(),bar.high(),bar.low(),bar.close(),bar.volume()),decimal(session.get("price_tick")),
            decimal(session.get("slippage_ticks")),decimal(session.get("max_participation_rate")));
        if(!fill.fillable()) return;
        if(fill.fillPrice().signum()<=0) throw new IllegalStateException("保护成交价无效，禁止补造价格");
        UUID orderId=UUID.randomUUID();
        jdbc.update("""
            insert into paper_trading.paper_order(id,session_id,client_order_id,side,offset_type,order_type,quantity,remaining_quantity,stop_price,status,eligible_bar_index)
            values(?,?,?,?,'CLOSE',?,?,?,?,'PENDING',?)
            """,orderId,id,"personal-protect-"+UUID.randomUUID(),side,type,position.lots(),position.lots(),stop,bar.index());
        executeFill(id,session,new OrderState(orderId,side,"CLOSE",type,position.lots(),null,stop),bar,fill);
        jdbc.update("update paper_trading.paper_fill set reason=? where order_id=?",reason,orderId);
        // Protection is re-created for the actual remaining position next bar;
        // stale partial orders may never coexist with the managed protection.
        jdbc.update("update paper_trading.paper_order set status='CANCELLED',updated_at=now() where id=? and status='PARTIAL'",orderId);
    }

    private boolean autoRoll(UUID sessionId, Map<String, Object> session, PositionState position, BarState bar) {
        Map<String, Object> roll;
        try {
            roll = jdbc.queryForMap("""
                select * from paper_trading.paper_roll_event
                where session_id=? and execution_date=? and from_contract=? and to_contract=?
                """, sessionId, LocalDate.ofInstant(bar.marketTime(), SHANGHAI),
                position.contract(), bar.contract());
        } catch (EmptyResultDataAccessException exception) {
            jdbc.update("update paper_trading.paper_session set status='ERROR', updated_at=now() where id=?", sessionId);
            return false;
        }
        SpecState oldSpec = loadSpec(sessionId, position.contract());
        SpecState newSpec = loadSpec(sessionId, bar.contract());
        BigDecimal ticks = decimal(session.get("slippage_ticks"));
        BigDecimal oldMarket = decimal(roll.get("old_open"));
        BigDecimal newMarket = decimal(roll.get("new_open"));
        String closeSide = position.direction() > 0 ? "SELL" : "BUY";
        String openSide = position.direction() > 0 ? "BUY" : "SELL";
        BigDecimal oldFill = adverse(oldMarket, oldSpec.tick(), ticks, closeSide);
        BigDecimal newFill = adverse(newMarket, newSpec.tick(), ticks, openSide);
        BigDecimal realized = BigDecimal.valueOf(position.direction())
            .multiply(oldFill.subtract(position.averagePrice()))
            .multiply(BigDecimal.valueOf(oldSpec.multiplier() * (long) position.lots()));
        BigDecimal closeFee = fee(oldFill, position.lots(), oldSpec.multiplier(), oldSpec.commission(), decimal(session.get("fee_rate")));
        BigDecimal cashAfterClose = decimal(session.get("cash_balance")).add(realized).subtract(closeFee);
        BigDecimal newMarginPerLot = newSpec.margin().max(
            newFill.multiply(BigDecimal.valueOf(newSpec.multiplier())).multiply(decimal(session.get("margin_rate")))
        );
        int affordable = cashAfterClose.max(BigDecimal.ZERO).divide(newMarginPerLot, 0, RoundingMode.FLOOR).intValue();
        int newLots = Math.min(position.lots(), affordable);
        if (newLots <= 0) {
            jdbc.update("update paper_trading.paper_session set status='ERROR', updated_at=now() where id=?", sessionId);
            return false;
        }
        BigDecimal openFee = fee(newFill, newLots, newSpec.multiplier(), newSpec.commission(), decimal(session.get("fee_rate")));
        BigDecimal cash = cashAfterClose.subtract(openFee);
        BigDecimal slippage = oldFill.subtract(oldMarket).abs()
            .multiply(BigDecimal.valueOf(oldSpec.multiplier() * (long) position.lots()))
            .add(newFill.subtract(newMarket).abs()
                .multiply(BigDecimal.valueOf(newSpec.multiplier() * (long) newLots)));
        BigDecimal margin = newMarginPerLot.multiply(BigDecimal.valueOf(newLots));
        jdbc.update("""
            update paper_trading.paper_position set contract=?, lots=?, average_price=?,
                margin_occupied=?, unrealized_pnl=0, updated_at=now() where session_id=?
            """, bar.contract(), newLots, newFill, margin, sessionId);
        insertRollFill(sessionId, position.contract(), closeSide, "CLOSE", position.lots(),
            oldMarket, oldFill, closeFee, oldFill.subtract(oldMarket).abs()
                .multiply(BigDecimal.valueOf(oldSpec.multiplier() * (long) position.lots())), realized, bar.marketTime());
        insertRollFill(sessionId, bar.contract(), openSide, "OPEN", newLots,
            newMarket, newFill, openFee, newFill.subtract(newMarket).abs()
                .multiply(BigDecimal.valueOf(newSpec.multiplier() * (long) newLots)), BigDecimal.ZERO, bar.marketTime());
        jdbc.update("""
            update paper_trading.paper_session set cash_balance=?, equity=?, realized_pnl=realized_pnl+?,
                commission_paid=commission_paid+?, slippage_paid=slippage_paid+?, updated_at=now(), version=version+1
            where id=?
            """, cash, cash, realized, closeFee.add(openFee), slippage, sessionId);
        return true;
    }

    private void insertRollFill(UUID sessionId, String contract, String side, String offset, int lots,
                                BigDecimal market, BigDecimal fill, BigDecimal fee, BigDecimal slippage,
                                BigDecimal realized, Instant marketTime) {
        jdbc.update("""
            insert into paper_trading.paper_fill (
                id, session_id, event_type, contract, side, offset_type, quantity, market_price,
                fill_price, fee, slippage_cost, realized_pnl, reason, market_time
            ) values (?, ?, 'ROLL', ?, ?, ?, ?, ?, ?, ?, ?, ?, '真实主力合约自动移仓', ?)
            """, UUID.randomUUID(), sessionId, contract, side, offset, lots, market, fill,
            fee, slippage, realized, Timestamp.from(marketTime));
    }

    private void updateMarket(UUID sessionId, BarState bar) {
        applySpec(sessionId, bar.contract());
        jdbc.update("""
            update paper_trading.paper_session set current_bar_index=?, current_market_time=?,
                current_contract=?, current_price=?, updated_at=now(), version=version+1 where id=?
            """, bar.index(), Timestamp.from(bar.marketTime()), bar.contract(), bar.close(), sessionId);
    }

    private void updateValuation(UUID sessionId, BigDecimal marketPrice) {
        Map<String, Object> session = loadSession(sessionId, true);
        PositionState position = loadPosition(sessionId, true);
        BigDecimal unrealized = unrealized(position, marketPrice, intValue(session.get("volume_multiple")));
        BigDecimal margin = position.lots() == 0 ? BigDecimal.ZERO
            : marginPerLot(marketPrice, intValue(session.get("volume_multiple")), session)
                .multiply(BigDecimal.valueOf(position.lots()));
        BigDecimal equity = decimal(session.get("cash_balance")).add(unrealized);
        jdbc.update("""
            update paper_trading.paper_position set unrealized_pnl=?, margin_occupied=?, updated_at=now()
            where session_id=?
            """, unrealized, margin, sessionId);
        jdbc.update("update paper_trading.paper_session set equity=?, updated_at=now() where id=?", equity, sessionId);
        if (position.lots() > 0 && equity.compareTo(margin) < 0) {
            jdbc.update("update paper_trading.paper_session set status='PAUSED', updated_at=now() where id=?", sessionId);
        }
    }

    private void applySpec(UUID sessionId, String contract) {
        SpecState spec = loadSpec(sessionId, contract);
        jdbc.update("""
            update paper_trading.paper_session set volume_multiple=?, price_tick=?,
                margin_per_lot=?, commission_per_lot=? where id=?
            """, spec.multiplier(), spec.tick(), spec.margin(), spec.commission(), sessionId);
    }

    private SpecState loadSpec(UUID sessionId, String contract) {
        try {
            return jdbc.queryForObject("""
                select * from paper_trading.paper_contract_spec where session_id=? and contract=?
                """, (rs, rowNum) -> new SpecState(
                    rs.getInt("volume_multiple"), rs.getBigDecimal("price_tick"),
                    rs.getBigDecimal("margin_per_lot"), rs.getBigDecimal("commission_per_lot")
                ), sessionId, contract);
        } catch (EmptyResultDataAccessException exception) {
            throw new IllegalStateException("合约规格缺失，禁止模拟成交: " + contract);
        }
    }

    private Map<String, Object> loadSession(UUID sessionId, boolean lock) {
        try {
            return jdbc.queryForMap(
                "select * from paper_trading.paper_session where id=?" + (lock ? " for update" : ""),
                sessionId
            );
        } catch (EmptyResultDataAccessException exception) {
            throw new IllegalArgumentException("模拟会话不存在");
        }
    }

    private PositionState loadPosition(UUID sessionId, boolean lock) {
        return jdbc.queryForObject(
            "select * from paper_trading.paper_position where session_id=?" + (lock ? " for update" : ""),
            (rs, rowNum) -> new PositionState(
                rs.getString("contract"), rs.getInt("direction"), rs.getInt("lots"),
                rs.getBigDecimal("average_price"), rs.getBigDecimal("margin_occupied"),
                rs.getBigDecimal("unrealized_pnl")
            ), sessionId
        );
    }

    private BarState loadBar(UUID sessionId, int index) {
        return jdbc.queryForObject("""
            select * from paper_trading.paper_scenario_bar where session_id=? and bar_index=?
            """, (rs, rowNum) -> new BarState(
                rs.getInt("bar_index"), rs.getTimestamp("market_time").toInstant(),
                rs.getString("contract"), rs.getBigDecimal("open_price"),
                rs.getBigDecimal("high_price"), rs.getBigDecimal("low_price"),
                rs.getBigDecimal("close_price"), rs.getLong("volume")
            ), sessionId, index);
    }

    private void insertBars(UUID sessionId, List<HistoricalBar> bars) {
        List<Object[]> batch = new ArrayList<>(bars.size());
        for (int index = 0; index < bars.size(); index++) {
            HistoricalBar bar = bars.get(index);
            batch.add(new Object[]{sessionId, index, Timestamp.from(bar.timestamp()), bar.contract(),
                bar.open(), bar.high(), bar.low(), bar.close(), bar.volume(), bar.openInterest()});
        }
        jdbc.batchUpdate("""
            insert into paper_trading.paper_scenario_bar (
                session_id, bar_index, market_time, contract, open_price, high_price,
                low_price, close_price, volume, open_interest
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, batch);
    }

    private void insertSpecs(UUID sessionId, Map<String, ContractSpec> specs) {
        List<Object[]> batch = specs.values().stream().map(spec -> new Object[]{
            sessionId, spec.contract(), spec.volumeMultiple(), spec.priceTick(),
            spec.marginPerLot(), spec.commissionPerLot()
        }).toList();
        jdbc.batchUpdate("""
            insert into paper_trading.paper_contract_spec (
                session_id, contract, volume_multiple, price_tick, margin_per_lot, commission_per_lot
            ) values (?, ?, ?, ?, ?, ?)
            """, batch);
    }

    private void insertRolls(UUID sessionId, SimulationDataset dataset) {
        if (dataset.rollEvents() == null || dataset.rollEvents().isEmpty()) return;
        List<Object[]> batch = dataset.rollEvents().stream().map(event -> new Object[]{
            sessionId, event.executionDate(), event.fromContract(), event.toContract(),
            event.oldOpen(), event.newOpen()
        }).toList();
        jdbc.batchUpdate("""
            insert into paper_trading.paper_roll_event (
                session_id, execution_date, from_contract, to_contract, old_open, new_open
            ) values (?, ?, ?, ?, ?, ?)
            """, batch);
    }

    private ContractSpec requiredSpec(SimulationDataset dataset, String contract) {
        ContractSpec spec = dataset.contractSpecs().get(contract);
        if (spec == null) throw new IllegalStateException("缺少真实合约规格: " + contract);
        return spec;
    }

    private void validateOrderRequest(PlaceOrderRequest request) {
        if (request.orderType().equals("LIMIT") && request.limitPrice() == null) {
            throw new IllegalArgumentException("限价单必须填写限价");
        }
        if (request.orderType().equals("STOP") && request.stopPrice() == null) {
            throw new IllegalArgumentException("止损单必须填写触发价");
        }
    }

    private void rejectOrder(UUID orderId, String reason) {
        jdbc.update("""
            update paper_trading.paper_order set status='REJECTED', rejection_reason=?, updated_at=now()
            where id=?
            """, reason, orderId);
    }

    private BigDecimal fee(BigDecimal price, int quantity, int multiplier,
                           BigDecimal perLot, BigDecimal feeRate) {
        BigDecimal provider = perLot.multiply(BigDecimal.valueOf(quantity));
        BigDecimal rate = price.multiply(BigDecimal.valueOf(multiplier * (long) quantity)).multiply(feeRate);
        return provider.max(rate).setScale(2, RoundingMode.HALF_UP);
    }

    private BigDecimal marginPerLot(BigDecimal price, int multiplier, Map<String, Object> session) {
        return decimal(session.get("margin_per_lot")).max(
            price.multiply(BigDecimal.valueOf(multiplier)).multiply(decimal(session.get("margin_rate")))
        );
    }

    private BigDecimal unrealized(PositionState position, BigDecimal price, int multiplier) {
        if (position.direction() == 0) return BigDecimal.ZERO;
        return BigDecimal.valueOf(position.direction()).multiply(price.subtract(position.averagePrice()))
            .multiply(BigDecimal.valueOf(multiplier * (long) position.lots()));
    }

    private BigDecimal adverse(BigDecimal market, BigDecimal tick, BigDecimal ticks, String side) {
        BigDecimal raw = side.equals("BUY") ? market.add(tick.multiply(ticks)) : market.subtract(tick.multiply(ticks));
        return raw.divide(tick, 0, side.equals("BUY") ? RoundingMode.CEILING : RoundingMode.FLOOR).multiply(tick);
    }

    private Map<String, Object> sessionMap(Map<String, Object> row) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("id", row.get("id"));
        item.put("name", row.get("name"));
        item.put("mode", row.get("mode"));
        item.put("symbol", row.get("symbol"));
        item.put("status", row.get("status"));
        item.put("dataSource", row.get("data_source"));
        item.put("dataTimestamp", instant(row.get("data_timestamp")));
        item.put("initialCash", row.get("initial_cash"));
        item.put("cashBalance", row.get("cash_balance"));
        item.put("equity", row.get("equity"));
        item.put("realizedPnl", row.get("realized_pnl"));
        item.put("commissionPaid", row.get("commission_paid"));
        item.put("slippagePaid", row.get("slippage_paid"));
        item.put("marginRate", row.get("margin_rate"));
        item.put("feeRate", row.get("fee_rate"));
        item.put("slippageTicks", row.get("slippage_ticks"));
        item.put("autoRoll", row.get("auto_roll"));
        item.put("currentBarIndex", row.get("current_bar_index"));
        item.put("totalBars", row.get("total_bars"));
        item.put("currentMarketTime", instant(row.get("current_market_time")));
        item.put("currentContract", row.get("current_contract"));
        item.put("currentPrice", row.get("current_price"));
        item.put("volumeMultiple", row.get("volume_multiple"));
        item.put("priceTick", row.get("price_tick"));
        item.put("marginPerLot", row.get("margin_per_lot"));
        item.put("commissionPerLot", row.get("commission_per_lot"));
        item.put("version", row.get("version"));
        item.put("createdAt", instant(row.get("created_at")));
        item.put("updatedAt", instant(row.get("updated_at")));
        return item;
    }

    private Map<String, Object> positionMap(Map<String, Object> row) {
        return Map.of(
            "contract", row.get("contract"),
            "direction", row.get("direction"),
            "lots", row.get("lots"),
            "averagePrice", row.get("average_price"),
            "marginOccupied", row.get("margin_occupied"),
            "unrealizedPnl", row.get("unrealized_pnl")
        );
    }

    private static BigDecimal decimal(Object value) { return (BigDecimal) value; }
    private static int intValue(Object value) { return ((Number) value).intValue(); }
    private static boolean booleanValue(Object value) { return Boolean.TRUE.equals(value); }
    private static Instant instant(Object value) {
        if (value instanceof Timestamp timestamp) return timestamp.toInstant();
        if (value instanceof OffsetDateTime offsetDateTime) return offsetDateTime.toInstant();
        return (Instant) value;
    }

    private record OrderState(UUID id, String side, String offset, String orderType, int remaining,
                              BigDecimal limitPrice, BigDecimal stopPrice) {}
    private record PositionState(String contract, int direction, int lots, BigDecimal averagePrice,
                                 BigDecimal margin, BigDecimal unrealized) {}
    private record BarState(int index, Instant marketTime, String contract, BigDecimal open,
                            BigDecimal high, BigDecimal low, BigDecimal close, long volume) {}
    private record SpecState(int multiplier, BigDecimal tick, BigDecimal margin, BigDecimal commission) {}
}
