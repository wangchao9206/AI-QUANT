package com.aiquant.paper.service;

import com.aiquant.paper.api.PaperRequests.PlaceOrderRequest;
import com.aiquant.paper.client.SimulationDataClient;
import com.aiquant.paper.client.SimulationDataClient.LiveContext;
import com.aiquant.paper.client.SimulationDataClient.PortfolioQuotes;
import com.aiquant.paper.service.PortfolioLedger.Position;
import com.aiquant.paper.service.PortfolioLedger.Spec;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;

/** One parent row lock serializes all contracts sharing the wallet. */
final class PaperPortfolioService {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate tx;
    private final SimulationDataClient data;
    private final MatchingEngine matching;

    PaperPortfolioService(JdbcTemplate jdbc,TransactionTemplate tx,SimulationDataClient data,MatchingEngine matching) {
        this.jdbc=jdbc;this.tx=tx;this.data=data;this.matching=matching;
    }
    static boolean enabled(Map<String,Object> session) {return Boolean.TRUE.equals(session.get("multi_instrument"));}
    private Map<String,Object> account(UUID id,boolean lock) {
        var rows=jdbc.queryForList("select * from paper_trading.paper_session where id=?"+(lock?" for update":""),id);
        if(rows.isEmpty())throw new IllegalArgumentException("模拟账户不存在");
        return rows.get(0);
    }
    private void eligible(Map<String,Object> s) {
        if(!"LIVE".equals(s.get("mode")) || !"MANUAL".equals(s.get("strategy_id")) || PlanOrderGuard.guarded(s)
            || jdbc.queryForObject("select count(*) from paper_trading.personal_training where session_id=?",Integer.class,s.get("id"))>0)
            throw new IllegalStateException("多品种共用资金仅支持实时手动模拟账户");
    }
    void select(UUID id,String symbol) {
        eligible(account(id,false));
        LiveContext observed=data.live(symbol.toUpperCase(Locale.ROOT));
        tx.executeWithoutResult(status->{
            var s=account(id,true);eligible(s);
            if(!enabled(s))upgrade(id,s);
            if(jdbc.queryForObject("select count(*) from paper_trading.paper_portfolio_position where session_id=? and contract=?",Integer.class,id,observed.contract())==0
                && instruments(id).size()>=100)throw new IllegalStateException("每个账户最多添加100个实际合约");
            observe(id,observed);
            activate(id,observed);
            value(id);
        });
    }
    private void upgrade(UUID id,Map<String,Object> s) {
        var p=jdbc.queryForMap("select * from paper_trading.paper_position where session_id=? for update",id);
        String contract=(String)p.get("contract");
        var specs=jdbc.queryForList("select * from paper_trading.paper_contract_spec where session_id=? and contract=?",id,contract);
        Map<String,Object> spec=specs.isEmpty()?s:specs.get(0);
        jdbc.update("""
            insert into paper_trading.paper_portfolio_position
            (session_id,contract,symbol,direction,lots,average_price,current_price,market_time,market_state,data_source,
             volume_multiple,price_tick,margin_per_lot,commission_per_lot,margin_occupied,unrealized_pnl)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,id,contract,s.get("symbol"),p.get("direction"),p.get("lots"),p.get("average_price"),s.get("current_price"),
            s.get("current_market_time"),s.get("market_state"),s.get("data_source"),spec.get("volume_multiple"),spec.get("price_tick"),
            spec.get("margin_per_lot"),spec.get("commission_per_lot"),p.get("margin_occupied"),p.get("unrealized_pnl"));
        jdbc.update("""
            update paper_trading.paper_order o set contract=coalesce(
                (select f.contract from paper_trading.paper_fill f where f.order_id=o.id order by f.created_at limit 1),?)
            where o.session_id=? and o.contract is null
            """,contract,id);
        for(var order:pending(id)) {
            var pos=instrument(id,(String)order.get("contract"));
            if("OPEN".equals(order.get("offset_type")))jdbc.update("update paper_trading.paper_order set reserved_cash=? where id=?",
                reserve(s,pos,order),order.get("id"));
        }
        jdbc.update("delete from paper_trading.paper_position where session_id=?",id);
        jdbc.update("update paper_trading.paper_session set multi_instrument=true,auto_roll=false,version=version+1,updated_at=now() where id=?",id);
    }
    private List<Map<String,Object>> instruments(UUID id) {
        return jdbc.queryForList("select * from paper_trading.paper_portfolio_position where session_id=? order by contract",id);
    }
    private Map<String,Object> instrument(UUID id,String contract) {
        var rows=jdbc.queryForList("select * from paper_trading.paper_portfolio_position where session_id=? and contract=?",id,contract);
        if(rows.isEmpty())throw new IllegalArgumentException("请先在此账户添加该实际合约");
        return rows.get(0);
    }
    private List<Map<String,Object>> pending(UUID id) {
        return jdbc.queryForList("select * from paper_trading.paper_order where session_id=? and status in ('PENDING','PARTIAL') order by created_at,id",id);
    }
    private void observe(UUID id,LiveContext c) {
        // Quote timestamps never move backwards, including snapshots fetched before another transaction.
        jdbc.update("""
            insert into paper_trading.paper_portfolio_position
            (session_id,contract,symbol,current_price,market_time,market_state,data_source,volume_multiple,price_tick,margin_per_lot,commission_per_lot)
            values (?,?,?,?,?,?,?,?,?,?,?)
            on conflict (tenant_id,session_id,contract) do update set
            current_price=excluded.current_price,market_time=excluded.market_time,market_state=excluded.market_state,
            data_source=excluded.data_source,volume_multiple=excluded.volume_multiple,price_tick=excluded.price_tick,
            margin_per_lot=excluded.margin_per_lot,commission_per_lot=excluded.commission_per_lot,updated_at=now()
            where excluded.market_time>=paper_portfolio_position.market_time
            """,id,c.contract(),c.symbol(),c.quote().price(),Timestamp.from(c.quote().dataTimestamp()),c.marketState(),c.source(),
            c.spec().volumeMultiple(),c.spec().priceTick(),c.spec().marginPerLot(),c.spec().commissionPerLot());
    }
    private void activate(UUID id,LiveContext context) {
        var p=instrument(id,context.contract());
        jdbc.update("""
            update paper_trading.paper_session set symbol=?,current_contract=?,current_price=?,current_market_time=?,
            data_timestamp=?,data_source=?,market_state=?,volume_multiple=?,price_tick=?,margin_per_lot=?,commission_per_lot=?,
            updated_at=now(),version=version+1 where id=?
            """,p.get("symbol"),p.get("contract"),p.get("current_price"),p.get("market_time"),p.get("market_time"),p.get("data_source"),
            p.get("market_state"),p.get("volume_multiple"),p.get("price_tick"),p.get("margin_per_lot"),p.get("commission_per_lot"),id);
    }
    void detail(UUID id,Map<String,Object> session,Map<String,Object> result) {
        var all=instruments(id).stream().map(this::view).toList();
        result.put("instruments",all);
        result.put("positions",all.stream().filter(p->((Number)p.get("lots")).intValue()>0).toList());
        result.put("position",all.stream().filter(p->p.get("contract").equals(session.get("current_contract"))).findFirst().orElseThrow());
        var totals=totals(id);
        result.put("totalMargin",totals.margin());result.put("totalUnrealized",totals.unrealized());
        result.put("reservedCash",totals.reserved());
        result.put("availableCash",d(session,"cash_balance").add(totals.unrealized()).subtract(totals.margin()).subtract(totals.reserved()));
    }
    private Map<String,Object> view(Map<String,Object> row) {
        var result=new LinkedHashMap<String,Object>();
        String[][] keys={{"contract","contract"},{"symbol","symbol"},{"direction","direction"},{"lots","lots"},
            {"averagePrice","average_price"},{"currentPrice","current_price"},{"marginOccupied","margin_occupied"},
            {"unrealizedPnl","unrealized_pnl"},{"marketState","market_state"},{"dataSource","data_source"},
            {"volumeMultiple","volume_multiple"},{"priceTick","price_tick"}};
        for(String[] key:keys)result.put(key[0],row.get(key[1]));
        result.put("marketTime",instant(row.get("market_time")));
        return result;
    }
    private PortfolioQuotes quotes(UUID id) {
        var contracts=instruments(id).stream().map(p->(String)p.get("contract")).toList();
        try {return data.portfolioQuotes(contracts);}
        catch(RuntimeException error) {
            var errors=new LinkedHashMap<String,String>();contracts.forEach(c->errors.put(c,"行情服务暂不可用"));
            return new PortfolioQuotes(Map.of(),errors);
        }
    }
    private static boolean fresh(LiveContext c) {
        if(c==null || !"LIVE".equals(c.marketState()) || !"FRESH".equals(c.quote().dataStatus()))return false;
        Instant now=Instant.now(),time=c.quote().dataTimestamp();
        return time!=null && !time.isBefore(now.minusSeconds(60)) && !time.isAfter(now.plusSeconds(10));
    }
    private void refresh(UUID id,PortfolioQuotes batch) {
        for(var p:instruments(id)) {
            var c=batch.quotes().get(p.get("contract"));
            if(c!=null)observe(id,c);
            else jdbc.update("update paper_trading.paper_portfolio_position set market_state='UNAVAILABLE' where session_id=? and contract=?",id,p.get("contract"));
        }
        var s=account(id,false);
        var active=batch.quotes().get(s.get("current_contract"));
        if(active!=null)activate(id,active);
        else jdbc.update("update paper_trading.paper_session set market_state='UNAVAILABLE' where id=?",id);
        value(id);
    }
    void place(UUID id,PlaceOrderRequest r) {
        if(r.contract()==null || !r.contract().matches("[A-Z]{1,4}[0-9]{3,4}"))throw new IllegalArgumentException("下单必须指定账户中的实际合约");
        // Idempotent retries must also work after the trading session closes.
        var existing=jdbc.queryForList("select * from paper_trading.paper_order where session_id=? and client_order_id=?",id,r.clientOrderId());
        if(!existing.isEmpty()) {sameOrder(existing.get(0),r);return;}
        instrument(id,r.contract());
        var batch=quotes(id);
        tx.executeWithoutResult(status->{
            var s=account(id,true);eligible(s);
            existingOrderOrPlace(id,s,r,batch);
        });
    }
    private void existingOrderOrPlace(UUID id,Map<String,Object> s,PlaceOrderRequest r,PortfolioQuotes batch) {
        existingOrderOrPlace(id,s,r,batch,null,null,null);
    }
    void automatedOrder(UUID id,PlaceOrderRequest r,PortfolioQuotes batch,UUID run,String reason,BigDecimal atr) {
        existingOrderOrPlace(id,account(id,false),r,batch,run,reason,atr);
    }
    void refreshAutomation(UUID id,PortfolioQuotes batch,UUID run) {
        refresh(id,batch);match(id,batch,run);value(id);
    }
    private void existingOrderOrPlace(UUID id,Map<String,Object> s,PlaceOrderRequest r,PortfolioQuotes batch,UUID run,String reason,BigDecimal atr) {
        var existing=jdbc.queryForList("select * from paper_trading.paper_order where session_id=? and client_order_id=?",id,r.clientOrderId());
        if(!existing.isEmpty()) {sameOrder(existing.get(0),r);return;}
        if(!"ACTIVE".equals(s.get("status")))throw new IllegalStateException("账户当前不可交易，请先恢复账户");
        if(run==null && jdbc.queryForObject("select count(*) from paper_trading.paper_automation_run where session_id=? and contract=? and enabled",Integer.class,id,r.contract())>0)
            throw new IllegalStateException("该合约正在量化运行，请先停止策略再手动下单");
        if(!fresh(batch.quotes().get(r.contract())))throw new IllegalStateException("该合约未开市或真实行情已过期，委托未提交");
        refresh(id,batch);
        s=account(id,false);
        var p=instrument(id,r.contract());
        var order=new LinkedHashMap<String,Object>();
        order.put("side",r.side());order.put("offset_type",r.offset());order.put("order_type",r.orderType());
        order.put("remaining_quantity",r.quantity());order.put("limit_price",r.limitPrice());order.put("stop_price",r.stopPrice());
        validatePosition(id,p,order,null);
        if("OPEN".equals(r.offset())) {
            for(var held:instruments(id))if(n(held,"lots")>0 && !usable(batch.quotes().get(held.get("contract"))))
                throw new IllegalStateException("已有持仓行情暂不可用，请刷新全部持仓估值后再开仓");
        }
        BigDecimal reservation="OPEN".equals(r.offset())?reserve(s,p,order):BigDecimal.ZERO;
        var totals=totals(id);
        if("OPEN".equals(r.offset()) && d(s,"cash_balance").add(totals.unrealized()).subtract(totals.margin()).subtract(totals.reserved()).compareTo(reservation)<0)
            throw new IllegalStateException("账户共用可用资金不足，无法预留该委托保证金及手续费");
        jdbc.update("""
            insert into paper_trading.paper_order
            (id,session_id,client_order_id,contract,side,offset_type,order_type,quantity,remaining_quantity,limit_price,stop_price,
             status,eligible_bar_index,reserved_cash) values (?,?,?,?,?,?,?,?,?,?,?,'PENDING',0,?)
            """,UUID.randomUUID(),id,r.clientOrderId(),r.contract(),r.side(),r.offset(),r.orderType(),r.quantity(),r.quantity(),r.limitPrice(),r.stopPrice(),reservation);
        if(run!=null)jdbc.update("update paper_trading.paper_order set automation_run_id=?,origin='STRATEGY',reason=?,risk_atr=? where session_id=? and client_order_id=?",
            run,reason,atr,id,r.clientOrderId());
        match(id,batch,run);
        value(id);
    }
    private static boolean usable(LiveContext c) {
        return c!=null && (fresh(c) || "CLOSED_CACHE".equals(c.marketState()));
    }
    private void sameOrder(Map<String,Object> o,PlaceOrderRequest r) {
        if(!Objects.equals(o.get("contract"),r.contract()) || !Objects.equals(o.get("side"),r.side())
            || !Objects.equals(o.get("offset_type"),r.offset()) || !Objects.equals(o.get("order_type"),r.orderType())
            || n(o,"quantity")!=r.quantity() || !sameDecimal((BigDecimal)o.get("limit_price"),r.limitPrice())
            || !sameDecimal((BigDecimal)o.get("stop_price"),r.stopPrice()))
            throw new IllegalArgumentException("此委托编号已使用，不能变更合约或交易内容");
    }
    private static boolean sameDecimal(BigDecimal a,BigDecimal b) {return a==null?b==null:b!=null&&a.compareTo(b)==0;}
    private BigDecimal reserve(Map<String,Object> s,Map<String,Object> p,Map<String,Object> o) {
        BigDecimal price=d(p,"current_price");
        if(o.get("limit_price")!=null)price=price.max(d(o,"limit_price"));
        if(o.get("stop_price")!=null)price=price.max(d(o,"stop_price"));
        price=price.add(d(p,"price_tick").multiply(d(s,"slippage_ticks")));
        var spec=spec(p);int lots=n(o,"remaining_quantity");
        return PortfolioLedger.margin(spec,price,lots,d(s,"margin_rate")).add(PortfolioLedger.fee(spec,price,lots,d(s,"fee_rate")));
    }
    private void validatePosition(UUID id,Map<String,Object> p,Map<String,Object> o,UUID exclude) {
        int dir="BUY".equals(o.get("side"))?1:-1;
        if("OPEN".equals(o.get("offset_type"))) {
            if(n(p,"lots")>0 && n(p,"direction")!=dir)throw new IllegalStateException("反向开仓前必须先平掉该合约持仓");
        } else {
            int reserved=0;
            for(var other:pending(id))if(Objects.equals(other.get("contract"),p.get("contract"))
                && "CLOSE".equals(other.get("offset_type")) && !Objects.equals(other.get("id"),exclude))reserved+=n(other,"remaining_quantity");
            if(n(p,"direction")==dir || n(p,"lots")-reserved<n(o,"remaining_quantity"))
                throw new IllegalStateException("该合约可平持仓不足（其他平仓挂单已占用的手数不可重复使用）");
        }
    }
    void advance(UUID id) {
        var batch=quotes(id);
        tx.executeWithoutResult(status->{
            var s=account(id,true);eligible(s);
            refresh(id,batch);
            if("ACTIVE".equals(s.get("status")))match(id,batch);
            value(id);
        });
    }
    void cancel(UUID id,UUID orderId) {
        tx.executeWithoutResult(status->{
            account(id,true);
            if(jdbc.update("update paper_trading.paper_order set status='CANCELLED',reserved_cash=0,updated_at=now() where session_id=? and id=? and status in ('PENDING','PARTIAL')",id,orderId)==0)
                throw new IllegalStateException("委托不存在或已无法撤销");
            value(id);
        });
    }
    private void match(UUID id,PortfolioQuotes batch) {
        match(id,batch,null);
    }
    private void match(UUID id,PortfolioQuotes batch,UUID allowedRun) {
        for(var o:pending(id)) {
            if(!Objects.equals(o.get("automation_run_id"),allowedRun))continue;
            LiveContext c=batch.quotes().get(o.get("contract"));
            if(!fresh(c))continue;
            var s=account(id,false);var p=instrument(id,c.contract());
            // A request prepared earlier may not execute at a price older than the stored observation.
            if(databaseTime(c.quote().dataTimestamp()).isBefore(instant(p.get("market_time"))))continue;
            var price=c.quote().price();
            var fill=matching.match(new MatchingEngine.OrderView((String)o.get("side"),(String)o.get("order_type"),n(o,"remaining_quantity"),
                (BigDecimal)o.get("limit_price"),(BigDecimal)o.get("stop_price")),
                new MatchingEngine.BarView(price,price,price,price,Long.MAX_VALUE/4),d(p,"price_tick"),d(s,"slippage_ticks"),d(s,"max_participation_rate"));
            if(!fill.fillable())continue;
            try {
                validatePosition(id,p,o,(UUID)o.get("id"));
                var trade=PortfolioLedger.trade(spec(p),position(p),(String)o.get("side"),(String)o.get("offset_type"),fill.quantity(),fill.marketPrice(),fill.fillPrice(),d(s,"fee_rate"));
                var totals=totals(id);
                BigDecimal margin=PortfolioLedger.margin(spec(p),price,trade.position().lots(),d(s,"margin_rate"));
                BigDecimal pnl=PortfolioLedger.pnl(spec(p),trade.position(),price);
                BigDecimal cash=d(s,"cash_balance").add(trade.cashChange());
                BigDecimal equity=cash.add(totals.unrealized()).subtract(d(p,"unrealized_pnl")).add(pnl);
                BigDecimal totalMargin=totals.margin().subtract(d(p,"margin_occupied")).add(margin);
                BigDecimal otherReserved=totals.reserved().subtract(d(o,"reserved_cash"));
                if("OPEN".equals(o.get("offset_type"))) {
                    for(var held:instruments(id))if(n(held,"lots")>0 && !usable(batch.quotes().get(held.get("contract"))))
                        throw new IllegalStateException("已有持仓行情暂不可用，未执行开仓");
                    if(equity.subtract(totalMargin).subtract(otherReserved).signum()<0)
                        throw new IllegalStateException("账户共用可用资金不足，无法缴纳实际保证金及手续费");
                }
                jdbc.update("""
                    update paper_trading.paper_portfolio_position set direction=?,lots=?,average_price=?,margin_occupied=?,unrealized_pnl=?,updated_at=now()
                    where session_id=? and contract=?
                    """,trade.position().direction(),trade.position().lots(),trade.position().average(),margin,pnl,id,c.contract());
                int remaining=n(o,"remaining_quantity")-fill.quantity();
                jdbc.update("update paper_trading.paper_order set remaining_quantity=?,status=?,reserved_cash=?,updated_at=now() where id=?",
                    remaining,remaining==0?"FILLED":"PARTIAL",remaining==0?BigDecimal.ZERO:d(o,"reserved_cash").multiply(BigDecimal.valueOf(remaining))
                        .divide(BigDecimal.valueOf(n(o,"remaining_quantity")),2,RoundingMode.CEILING),o.get("id"));
                jdbc.update("""
                    insert into paper_trading.paper_fill
                    (id,session_id,order_id,event_type,contract,side,offset_type,quantity,market_price,fill_price,fee,slippage_cost,realized_pnl,reason,market_time)
                    values (?,?,?,'ORDER',?,?,?,?,?,?,?,?,?,'多品种共用资金账户：真实合约行情模拟撮合',?)
                    """,UUID.randomUUID(),id,o.get("id"),c.contract(),o.get("side"),o.get("offset_type"),fill.quantity(),fill.marketPrice(),fill.fillPrice(),
                    trade.fee(),trade.slippage(),trade.realized(),Timestamp.from(c.quote().dataTimestamp()));
                jdbc.update("""
                    update paper_trading.paper_session set cash_balance=?,realized_pnl=realized_pnl+?,commission_paid=commission_paid+?,
                    slippage_paid=slippage_paid+?,version=version+1,updated_at=now() where id=?
                    """,cash,trade.realized(),trade.fee(),trade.slippage(),id);
            } catch(IllegalStateException error) {
                jdbc.update("update paper_trading.paper_order set status='REJECTED',reserved_cash=0,rejection_reason=?,updated_at=now() where id=?",error.getMessage(),o.get("id"));
            }
        }
    }
    private void value(UUID id) {
        var s=account(id,false);
        for(var p:instruments(id))jdbc.update("update paper_trading.paper_portfolio_position set margin_occupied=?,unrealized_pnl=? where session_id=? and contract=?",
            PortfolioLedger.margin(spec(p),d(p,"current_price"),n(p,"lots"),d(s,"margin_rate")),
            PortfolioLedger.pnl(spec(p),position(p),d(p,"current_price")),id,p.get("contract"));
        var totals=totals(id);BigDecimal equity=d(s,"cash_balance").add(totals.unrealized());
        BigDecimal peak=d(s,"peak_equity").max(equity).max(d(s,"initial_cash"));
        BigDecimal drawdown=peak.subtract(equity).max(BigDecimal.ZERO).multiply(BigDecimal.valueOf(100)).divide(peak,6,RoundingMode.HALF_UP);
        jdbc.update("""
            update paper_trading.paper_session set equity=?,peak_equity=?,max_drawdown_pct=greatest(max_drawdown_pct,?),
            portfolio_valued_at=now(),updated_at=now(),version=version+1,
            status=case when ?<? then 'PAUSED' else status end,
            execution_message=? where id=?
            """,equity,peak,drawdown,equity,totals.margin(),"全部合约共用资金；可用资金已扣除持仓保证金及开仓挂单预留",id);
    }
    private record Totals(BigDecimal margin,BigDecimal unrealized,BigDecimal reserved) {}
    private Totals totals(UUID id) {
        var t=jdbc.queryForMap("select coalesce(sum(margin_occupied),0) margin,coalesce(sum(unrealized_pnl),0) pnl from paper_trading.paper_portfolio_position where session_id=?",id);
        BigDecimal reserved=jdbc.queryForObject("select coalesce(sum(reserved_cash),0) from paper_trading.paper_order where session_id=? and status in ('PENDING','PARTIAL')",BigDecimal.class,id);
        return new Totals(d(t,"margin"),d(t,"pnl"),reserved);
    }
    private static Spec spec(Map<String,Object> p) {return new Spec(n(p,"volume_multiple"),d(p,"price_tick"),d(p,"margin_per_lot"),d(p,"commission_per_lot"));}
    private static Position position(Map<String,Object> p) {return new Position(n(p,"direction"),n(p,"lots"),d(p,"average_price"));}
    private static BigDecimal d(Map<String,Object> p,String key) {return (BigDecimal)p.get(key);}
    private static int n(Map<String,Object> p,String key) {return ((Number)p.get(key)).intValue();}
    private static Instant instant(Object v) {return v instanceof Timestamp t?t.toInstant():v instanceof java.time.OffsetDateTime t?t.toInstant():(Instant)v;}
    private static Instant databaseTime(Instant time) {
        return Instant.ofEpochSecond(time.getEpochSecond(),((time.getNano()+500L)/1000)*1000);
    }
}
