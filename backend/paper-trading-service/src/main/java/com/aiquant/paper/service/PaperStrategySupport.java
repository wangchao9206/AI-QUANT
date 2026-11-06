package com.aiquant.paper.service;

import com.aiquant.paper.client.SimulationDataClient;
import com.aiquant.paper.client.SimulationDataClient.HistoricalBar;
import com.aiquant.paper.client.SimulationDataClient.StrategyDecision;
import com.aiquant.paper.client.SimulationDataClient.StrategyInput;
import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;

/** Signal computation is outside transactions; accept() runs under the session lock. */
final class PaperStrategySupport {
    private final JdbcTemplate jdbc;
    private final SimulationDataClient data;

    PaperStrategySupport(JdbcTemplate jdbc, SimulationDataClient data) { this.jdbc=jdbc; this.data=data; }

    static boolean automatic(Map<String,Object> session) {
        return session.get("strategy_id") != null && !"MANUAL".equals(session.get("strategy_id"));
    }

    void freeze(UUID id, String kind, List<HistoricalBar> bars) {
        if (bars==null || bars.isEmpty()) return;
        var rows=new ArrayList<Object[]>();
        for(var bar:bars) rows.add(new Object[]{id,kind,Timestamp.from(bar.timestamp()),bar.open(),bar.high(),
            bar.low(),bar.close(),bar.volume(),bar.openInterest(),bar.contract()});
        jdbc.batchUpdate("""
            insert into paper_trading.paper_signal_bar
            (session_id,kind,market_time,open_price,high_price,low_price,close_price,volume,open_interest,contract)
            values (?,?,?,?,?,?,?,?,?,?) on conflict (session_id,kind,market_time) do nothing
            """,rows);
    }

    List<HistoricalBar> bars(UUID id, String kind, Instant cutoff) {
        var rows=jdbc.query("""
            select * from paper_trading.paper_signal_bar where session_id=? and kind=? and market_time<=?
            order by market_time desc limit 5000
            """,(rs,n)->new HistoricalBar(rs.getTimestamp("market_time").toInstant(),rs.getString("contract"),
                rs.getBigDecimal("open_price"),rs.getBigDecimal("high_price"),rs.getBigDecimal("low_price"),
                rs.getBigDecimal("close_price"),rs.getLong("volume"),rs.getLong("open_interest")),
            id,kind,Timestamp.from(cutoff));
        Collections.reverse(rows); return rows;
    }

    StrategyDecision prepare(UUID id, Map<String,Object> session, List<HistoricalBar> signals,
                             List<HistoricalBar> execution, Instant cutoff) {
        if (!automatic(session)) return null;
        var position=jdbc.queryForMap("select * from paper_trading.paper_position where session_id=?",id);
        Integer filled=jdbc.queryForObject("""
            select count(*) from paper_trading.paper_order where session_id=? and origin='STRATEGY'
            and offset_type='OPEN' and status in ('FILLED','PARTIAL')
            """,Integer.class,id);
        var decision=data.evaluate(new StrategyInput((String)session.get("strategy_id"),(String)session.get("symbol"),
            cutoff,signals,execution,((Number)position.get("direction")).intValue(),filled==null||filled==0,
            "WORKFLOW".equals(session.get("strategy_id"))?StrategyWorkflowStore.json(session.get("workflow_snapshot")).path("definition"):null));
        var frozen=StrategyWorkflowStore.json(session.get("workflow_snapshot"));
        if(frozen.hasNonNull("shadowId")){
            var trace=new java.util.ArrayList<java.util.Map<String,Object>>(decision.nodeTrace()==null?java.util.List.of():decision.nodeTrace());
            trace.add(java.util.Map.of("nodeId","shadow-reference","label","冻结观察依据","type","SHADOW_REFERENCE","status","FROZEN",
                "value",java.util.Map.of("shadowId",frozen.path("shadowId").asText(),"inputHash",frozen.path("shadowInputHash").asText()),"reason","仅历史模拟；保留创建账户时引用的观察记录"));
            return new StrategyDecision(decision.strategy(),decision.strategyName(),decision.modelVersion(),decision.signal(),decision.reason(),decision.signalTime(),decision.historyCount(),decision.requiredBars(),decision.atr(),trace);
        }
        return decision;
    }

    void accept(UUID id, Map<String,Object> session, StrategyDecision decision, int eligibleIndex) {
        if (decision==null) return;
        String reason=decision.reason()==null?"策略等待":decision.reason();
        jdbc.update("update paper_trading.paper_session set execution_message=? where id=?",reason,id);
        if (decision.signalTime()==null) return;
        int inserted=jdbc.update("""
            insert into paper_trading.paper_strategy_decision
            (session_id,signal_time,signal,reason,model_version,history_count,node_trace) values (?,?,?,?,?,?,?::jsonb)
            on conflict (session_id,signal_time) do nothing
            """,id,Timestamp.from(decision.signalTime()),decision.signal(),reason,decision.modelVersion(),decision.historyCount(),
            StrategyWorkflowStore.json(decision.nodeTrace()==null?List.of():decision.nodeTrace()).toString());
        if(inserted==0)return;
        if(eligibleIndex<0){gate(id,decision.signalTime(),"NO_SUCCESSOR_BAR","末根没有下一根真实行情，本次不生成委托");return;}
        if(!List.of("BUY","SELL","FLATTEN").contains(decision.signal())) return;
        var position=jdbc.queryForMap("select * from paper_trading.paper_position where session_id=?",id);
        int direction=((Number)position.get("direction")).intValue();
        boolean close="FLATTEN".equals(decision.signal());
        if(close) jdbc.update("""
            update paper_trading.paper_order set status='CANCELLED',updated_at=now()
            where session_id=? and origin='STRATEGY' and offset_type='OPEN' and status in ('PENDING','PARTIAL')
            """,id);
        Integer pending=jdbc.queryForObject("select count(*) from paper_trading.paper_order where session_id=? and status in ('PENDING','PARTIAL')",Integer.class,id);
        if(pending!=null && pending>0 || close && direction==0 || !close && direction!=0){
            if(StrategyWorkflowStore.CHAN_ENGINE.equals(decision.modelVersion()))gate(id,decision.signalTime(),"POSITION_OR_PENDING_ORDER","已有持仓或未完成委托，本次候选不重复开仓");return;
        }
        if(!close && (decision.atr()==null || decision.atr().signum()<=0) && !"BUY_AND_HOLD".equals(session.get("strategy_id"))) {
            if(StrategyWorkflowStore.CHAN_ENGINE.equals(decision.modelVersion()))gate(id,decision.signalTime(),"MISSING_DELIVERY_ATR","执行合约ATR不足，本次未开仓");
            jdbc.update("update paper_trading.paper_session set execution_message=? where id=?","执行合约ATR不足，等待真实日线；本次未开仓",id);
            return;
        }
        String side=close?(direction>0?"SELL":"BUY"):decision.signal();
        int lots=close?((Number)position.get("lots")).intValue():((Number)session.get("strategy_lots")).intValue();
        jdbc.update("""
            insert into paper_trading.paper_order
            (id,session_id,client_order_id,side,offset_type,order_type,quantity,remaining_quantity,status,
             eligible_bar_index,origin,reason,risk_atr)
            values (?,?,?,?,?,'MARKET',?,?,'PENDING',?,'STRATEGY',?,?)
            """,UUID.randomUUID(),id,"strategy:"+decision.signalTime(),side,close?"CLOSE":"OPEN",lots,lots,
            eligibleIndex,reason,decision.atr());
    }

    void gate(UUID id,Instant time,String code,String reason){
        var item=Map.of("nodeId","execution-gate","label","成交约束","type","EXECUTION_GATE","status","BLOCKED","value",code,"reason",reason);
        jdbc.update("update paper_trading.paper_strategy_decision set node_trace=node_trace||?::jsonb where session_id=? and signal_time=?",StrategyWorkflowStore.json(List.of(item)).toString(),id,Timestamp.from(time));
    }

    void expireChanEntries(UUID id,int index){
        var cancelled=jdbc.queryForList("update paper_trading.paper_order set status='CANCELLED',rejection_reason='首次可执行日线成交量不足，未成交余量不顺延',updated_at=now() where session_id=? and origin='STRATEGY' and offset_type='OPEN' and status in ('PENDING','PARTIAL') and eligible_bar_index<=? returning client_order_id",id,index);
        for(var row:cancelled){String command=(String)row.get("client_order_id");if(command.startsWith("strategy:"))gate(id,Instant.parse(command.substring(9)),"NEXT_BAR_LIQUIDITY","首次可执行日线成交量不足，未成交余量不顺延");}
    }

    List<Map<String,Object>> decisions(UUID id) {
        return jdbc.query("""
            select * from paper_trading.paper_strategy_decision where session_id=? order by signal_time desc limit 30
            """,(rs,n)->Map.<String,Object>of("signalTime",rs.getTimestamp("signal_time").toInstant(),
                "signal",rs.getString("signal"),"reason",rs.getString("reason"),
                "modelVersion",rs.getString("model_version"),"historyCount",rs.getInt("history_count"),
                "nodeTrace",StrategyWorkflowStore.json(rs.getObject("node_trace"))),id);
    }
}
