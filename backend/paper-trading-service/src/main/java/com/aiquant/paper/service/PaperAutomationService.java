package com.aiquant.paper.service;

import com.aiquant.paper.api.PaperRequests.PlaceOrderRequest;
import com.aiquant.paper.client.SimulationDataClient;
import com.aiquant.paper.client.SimulationDataClient.*;
import com.aiquant.tenancy.TenantTransactions;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.*;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class PaperAutomationService {
    private final JdbcTemplate db;private final TransactionTemplate tx;
    private final SimulationDataClient data;private final PaperPortfolioService portfolio;
    private final UUID startupEpoch=UUID.randomUUID();
    String startupKey(UUID run){return run+":"+startupEpoch;}
    private static final String TRINITY = "PERSONAL_TRINITY";
    private static final ObjectMapper CONFIG_JSON = new ObjectMapper();
    private static final Set<String> STRATEGIES=Set.of("MA20_MACD","HOLISTIC_14D","MOMENTUM_BREAKOUT","BOLLINGER_REVERSAL","DUAL_THRUST","ADAPTIVE_CTA","BUY_AND_HOLD","WORKFLOW", TRINITY);
    public record TrinityConfig(@Min(2) @Max(120) int fastPeriod, @Min(2) @Max(120) int mediumPeriod,
        @Min(2) @Max(120) int slowPeriod, @Min(2) @Max(20) int convergenceDays, int entryMinutes,
        @NotBlank @Pattern(regexp="chan|wyckoff|either") String confirmation,
        @NotBlank @Pattern(regexp="MINUTE_ADD|MA10_ADD|NONE") String addMode,
        @Min(1) @Max(40) int waitTradingDays) {
        void validate() {
            if (!(2 <= fastPeriod && fastPeriod < mediumPeriod && mediumPeriod < slowPeriod && slowPeriod <= 120)
                || convergenceDays < 2 || convergenceDays > 20 || !Set.of(15,30,60).contains(entryMinutes)
                || confirmation == null || !Set.of("chan", "wyckoff", "either").contains(confirmation)
                || addMode == null || !Set.of("MINUTE_ADD", "MA10_ADD", "NONE").contains(addMode)
                || waitTradingDays < 1 || waitTradingDays > 40) {
                throw new IllegalArgumentException("三位一体的均线、周期、确认方式、加仓规则或等待天数无效");
            }
        }
    }
    public record Start(@NotBlank @Pattern(regexp="[A-Z]{1,4}[0-9]{3,4}") String contract,
        @NotBlank String strategy,@Min(1) @Max(1000000) int lots,@Min(0) @Max(10000) int stopLossTicks,
        @NotNull @DecimalMin("0") @DecimalMax("20") BigDecimal stopLossAtr,
        @NotNull @DecimalMin("0") @DecimalMax("50") BigDecimal takeProfitAtr,boolean intradayOnly,
        UUID workflowVersionId, @Valid TrinityConfig trinity) {
        public Start(String contract, String strategy, int lots, int stopLossTicks, BigDecimal stopLossAtr,
            BigDecimal takeProfitAtr, boolean intradayOnly, UUID workflowVersionId) {
            this(contract, strategy, lots, stopLossTicks, stopLossAtr, takeProfitAtr, intradayOnly, workflowVersionId, null);
        }
    }
    public record Prepared(LiveContext live,PortfolioQuotes quotes,JsonNode chart,StrategyDecision decision,String error,JsonNode dataRefresh) {
        public Prepared(LiveContext live,PortfolioQuotes quotes,JsonNode chart,StrategyDecision decision,String error){this(live,quotes,chart,decision,error,null);}
    }
    public PaperAutomationService(JdbcTemplate db,TransactionTemplate tx,SimulationDataClient data,MatchingEngine matching) {
        this.db=db;this.tx=tx;this.data=data;portfolio=new PaperPortfolioService(db,tx,data,matching);
    }
    private Map<String,Object> account(UUID id,boolean lock) {
        var rows=db.queryForList("select * from paper_trading.paper_session where id=?"+(lock?" for update":""),id);
        if(rows.isEmpty())throw new IllegalArgumentException("模拟账户不存在");return rows.get(0);
    }
    private void eligible(Map<String,Object> s) {
        if(!PaperPortfolioService.enabled(s)||!"LIVE".equals(s.get("mode"))||!"MANUAL".equals(s.get("strategy_id"))||PlanOrderGuard.guarded(s)
            ||db.queryForObject("select count(*) from paper_trading.personal_training where session_id=?",Integer.class,s.get("id"))>0)
            throw new IllegalStateException("请在实时手动账户中添加品种后启用量化执行");
    }
    public Map<String,Object> state(UUID id) {
        account(id,false);
        var runs=db.queryForList("select id,contract,strategy,lots,stop_loss_ticks as \"stopLossTicks\",stop_loss_atr as \"stopLossAtr\",take_profit_atr as \"takeProfitAtr\",intraday_only as \"intradayOnly\",workflow_snapshot as workflow,trinity_config as trinity,enabled,status,message,checked_at as \"checkedAt\",created_at as \"createdAt\" from paper_trading.paper_automation_run where session_id=? order by enabled desc,created_at desc limit 100",id);
        runs.forEach(r->{
            r.put("workflow",StrategyWorkflowStore.json(r.get("workflow")));
            if (r.get("trinity")!=null) r.put("trinity",StrategyWorkflowStore.json(r.get("trinity")));
        });
        var receipts=new HashMap<Object,JsonNode>();
        for(var row:db.queryForList("select distinct on(e.run_id) e.run_id,e.evidence from paper_trading.paper_automation_event e join paper_trading.paper_automation_run r on r.id=e.run_id where r.session_id=? and jsonb_exists(e.evidence,'dataRefresh') order by e.run_id,e.created_at desc,e.id desc",id))
            receipts.put(row.get("run_id"),StrategyWorkflowStore.json(row.get("evidence")).path("dataRefresh"));
        for(var run:runs) {
            var receipt=receipts.getOrDefault(run.get("id"),StrategyWorkflowStore.json(Map.of()));run.put("dataRefresh",receipt);
            if(Boolean.TRUE.equals(run.get("enabled")) && !"ERROR".equals(run.get("status")) && !startupKey((UUID)run.get("id")).equals(receipt.path("requestKey").asText())) {
                run.put("status","REFRESHING");run.put("message","启动前正在重新拉取最新日线与分钟数据，完成前不允许开新仓");
            }
        }
        var events=db.queryForList("select e.id,r.contract,r.strategy,e.signal_time as \"signalTime\",e.signal,e.status,e.reason,e.evidence from paper_trading.paper_automation_event e join paper_trading.paper_automation_run r on r.id=e.run_id where r.session_id=? order by e.created_at desc,e.id desc limit 50",id);
        events.forEach(e->e.put("evidence",StrategyWorkflowStore.json(e.get("evidence"))));
        return Map.of("runs",runs,"events",events);
    }
    public Map<String,Object> start(UUID session,UUID owner,Start request) {
        if(!STRATEGIES.contains(request.strategy()))throw new IllegalArgumentException("不支持的策略");
        String trinity = null;
        if (TRINITY.equals(request.strategy())) {
            if (request.trinity()==null) throw new IllegalArgumentException("请提供三位一体的策略参数");
            request.trinity().validate();
            if (!request.contract().matches("(?:FG|SA|AP|CJ)[0-9]{3,4}"))
                throw new IllegalArgumentException("三位一体当前支持玻璃、纯碱、苹果和红枣的实际交割合约");
            int totalLots = "NONE".equals(request.trinity().addMode()) ? 1 : 2;
            if (request.lots()!=totalLots || request.intradayOnly())
                throw new IllegalArgumentException("三位一体需允许隔夜，目标仓位为两手，单手模式除外");
            trinity = CONFIG_JSON.valueToTree(request.trinity()).toString();
        } else if (request.trinity()!=null) {
            throw new IllegalArgumentException("仅三位一体支持该策略参数");
        }
        JsonNode frozen=StrategyWorkflowStore.json(Map.of());
        if("WORKFLOW".equals(request.strategy())) {
            if(request.workflowVersionId()==null)throw new IllegalArgumentException("请选择已发布工作流");
            var v=new StrategyWorkflowStore(db).executable(request.workflowVersionId());
            if(StrategyWorkflowStore.CHAN_ENGINE.equals(v.engineVersion()))throw new IllegalStateException("此缠论工作流版本目前仅支持历史模拟及冻结观察");
            frozen=StrategyWorkflowStore.snapshot(v);
        } else if(request.workflowVersionId()!=null)throw new IllegalArgumentException("仅工作流策略可指定发布版本");
        JsonNode workflow=frozen;
        String trinitySnapshot=trinity;
        tx.executeWithoutResult(status->{
            var s=account(session,true);eligible(s);
            if(!"ACTIVE".equals(s.get("status")))throw new IllegalStateException("请先恢复账户");
            var p=position(session,request.contract());
            if(n(p,"lots")>0 || db.queryForObject("select count(*) from paper_trading.paper_order where session_id=? and contract=? and status in ('PENDING','PARTIAL')",Integer.class,session,request.contract())>0)
                throw new IllegalStateException("启动前请先平掉该合约持仓并撤销挂单，其他品种不受影响");
            if(db.queryForObject("select count(*) from paper_trading.paper_automation_run where session_id=? and contract=? and enabled",Integer.class,session,request.contract())>0)
                throw new IllegalStateException("该合约已有策略运行，请先停止");
            int lots=request.lots();BigDecimal stop=request.stopLossAtr(),profit=request.takeProfitAtr();
            if("WORKFLOW".equals(request.strategy())) {
                var v=new StrategyWorkflowStore(db).version(request.workflowVersionId());lots=v.lots();stop=v.stopLossAtr();profit=v.takeProfitAtr();
            }
            db.update("""
                insert into paper_trading.paper_automation_run
                (id,session_id,contract,owner_id,strategy,lots,stop_loss_ticks,stop_loss_atr,take_profit_atr,intraday_only,workflow_snapshot,trinity_config,message)
                values (?,?,?,?,?,?,?,?,?,?,?::jsonb,?::jsonb,'启动前等待重新拉取最新日线与分钟数据；参数已冻结')
                """,UUID.randomUUID(),session,request.contract(),owner,request.strategy(),lots,request.stopLossTicks(),stop,profit,request.intradayOnly(),workflow.toString(),trinitySnapshot);
        });return state(session);
    }
    public Map<String,Object> stop(UUID session,UUID run) {
        tx.executeWithoutResult(status->{
            account(session,true);
            var rows=db.queryForList("select id from paper_trading.paper_automation_run where id=? and session_id=? for update",run,session);
            if(rows.isEmpty())throw new IllegalArgumentException("策略运行记录不存在");
            db.update("update paper_trading.paper_automation_run set enabled=false,revision=revision+1,status='STOPPED',message='已停止；策略挂单已撤销，已有持仓保留供手动处理',lease_owner=null,lease_until=null,updated_at=now() where id=?",run);
            db.update("update paper_trading.paper_order set status='CANCELLED',reserved_cash=0,updated_at=now() where automation_run_id=? and status in ('PENDING','PARTIAL')",run);
        });return state(session);
    }
    public List<Map<String,Object>> claim(UUID worker,int count) {
        return tx.execute(status->{
            var rows=db.queryForList("""
                select r.*,p.direction as observed_direction,p.lots as observed_lots,p.average_price as observed_average,
                    case when r.strategy='PERSONAL_TRINITY' and p.lots>0 then (
                        select max(f.market_time) from paper_trading.paper_order o
                        join paper_trading.paper_fill f on f.order_id=o.id and f.tenant_id=o.tenant_id
                        where o.automation_run_id=r.id and o.tenant_id=r.tenant_id and f.offset_type='OPEN'
                    ) end as position_opened_at,
                    case when r.strategy='PERSONAL_TRINITY' then (
                        select max(e.signal_time) from paper_trading.paper_automation_event e
                        where e.run_id=r.id and e.tenant_id=r.tenant_id and e.signal in ('BUY','SELL')
                    ) end as last_entry_signal_time
                from paper_trading.paper_automation_run r join paper_trading.paper_portfolio_position p
                on p.tenant_id=r.tenant_id and p.session_id=r.session_id and p.contract=r.contract
                where r.enabled and r.next_check_at<=now() and (r.lease_until is null or r.lease_until<now())
                order by r.next_check_at,r.id limit ? for update of r skip locked
                """,Math.max(1,Math.min(4,count)));
            for(var job:rows)db.update("update paper_trading.paper_automation_run set lease_owner=?,lease_until=clock_timestamp()+interval '90 seconds' where id=?",worker,job.get("id"));
            return rows;
        });
    }
    public Prepared prepare(Map<String,Object> job) {
        PortfolioQuotes batch=null;
        JsonNode raw=StrategyWorkflowStore.json(Map.of());
        LiveContext live=null;
        String key=startupKey((UUID)job.get("id"));
        JsonNode refresh=StrategyWorkflowStore.json(Map.of("state","FAILED","requestKey",key,"message","启动数据刷新暂不可用，未使用旧缓存放行"));
        try {
            String contract=(String)job.get("contract");
            try {refresh=data.refreshAutomationData(contract,key);}catch(RuntimeException unavailable){/* Protection can still use valid live quotes. */}
            var contracts=db.queryForList("select contract from paper_trading.paper_portfolio_position where session_id=? and tenant_id=? order by contract",String.class,job.get("session_id"),job.get("tenant_id"));
            batch=data.portfolioQuotes(contracts);
            // The real bar adapter marks forming minutes explicitly; only completed rows go to the strategy.
            if (!TRINITY.equals(job.get("strategy"))) raw=data.liveChart(contract,60,180);
            if(!"READY".equals(refresh.path("state").asText()))return new Prepared(null,batch,raw,null,refresh.path("message").asText(),refresh);
            if (TRINITY.equals(job.get("strategy"))) {
                live=batch.quotes().get(contract);
                if (!fresh(live)) return new Prepared(live,batch,raw,null,"等待实际合约的实时行情",refresh);
                TrinityFeed feed;
                try { feed=data.trinityFeed(contract); }
                catch (IllegalStateException unavailable) {
                    return new Prepared(live,batch,raw,null,unavailable.getMessage(),refresh);
                }
                if (feed.asOf().isBefore(Instant.now().minusSeconds(30)) || feed.asOf().isAfter(Instant.now().plusSeconds(10)))
                    return new Prepared(live,batch,raw,null,"三位一体行情时点无效，等待更新",refresh);
                var decision=data.evaluateTrinity(new TrinityInput(TRINITY,contract,feed.asOf(),List.of(),
                    feed.dailyBars(),feed.minuteBars(),feed.minuteTradingDates(),feed.minuteCadence(),feed.tradingSessions(),
                    feed.tradingDate(),live.spec().priceTick(),StrategyWorkflowStore.json(job.get("trinity_config")),
                    n(job,"observed_direction"),n(job,"observed_lots"),optionalInstant(job.get("created_at")),
                    optionalInstant(job.get("position_opened_at")),optionalInstant(job.get("last_signal_time")),
                    optionalInstant(job.get("last_entry_signal_time"))));
                if ("WARMING".equals(decision.signal()) && feed.minuteBars().isEmpty() && feed.minuteStatus()!=null) {
                    decision=new StrategyDecision(decision.strategy(),decision.strategyName(),decision.modelVersion(),
                        decision.signal(),decision.reason()+"。"+feed.minuteStatus(),decision.signalTime(),
                        decision.historyCount(),decision.requiredBars(),decision.atr(),decision.nodeTrace());
                }
                return new Prepared(live,batch,raw,decision,null,refresh);
            }
            live=data.liveFast(contract);
            List<HistoricalBar> minutes=new ArrayList<>();
            var validated=PaperLiveChart.snapshot(raw,contract,60,180,Instant.now());
            @SuppressWarnings("unchecked") var rows=(List<Map<String,Object>>)validated.get("bars");
            for(var row:rows)if(!Boolean.TRUE.equals(row.get("provisional"))) {
                Instant stamp=(Instant)row.get("timestamp");
                if(stamp.plusSeconds(60).isAfter(live.checkedAt()))continue;
                minutes.add(new HistoricalBar(stamp,contract,(BigDecimal)row.get("open"),(BigDecimal)row.get("high"),
                    (BigDecimal)row.get("low"),(BigDecimal)row.get("close"),((Number)row.get("volume")).longValue(),0));
            }
            var wf=StrategyWorkflowStore.json(job.get("workflow_snapshot"));
            // This is read-only enumeration; the service role has the same background scope as plan alerts.
            StrategyDecision decision=null;String error=null;
            try {
                if("MA20_MACD".equals(job.get("strategy")) && (!raw.path("connected").asBoolean() || !"FRESH".equals(raw.path("dataStatus").asText())
                    || minutes.isEmpty() || minutes.get(minutes.size()-1).timestamp().isBefore(live.checkedAt().minusSeconds(180))))
                    throw new IllegalStateException("分钟行情未就绪");
                decision=data.evaluateFast(new StrategyInput((String)job.get("strategy"),contract,live.checkedAt(),
                    live.signalBars()==null?List.of():live.signalBars(),live.executionBars()==null?List.of():live.executionBars(),n(job,"observed_direction"),
                    job.get("last_signal_time")==null,"WORKFLOW".equals(job.get("strategy"))?wf.path("definition"):null,minutes,live.spec().priceTick()));
            }catch(RuntimeException unavailable){error="信号计算或分钟行情暂不可用；继续检查已有持仓保护";}
            return new Prepared(live,batch,raw,decision,error,refresh);
        } catch(RuntimeException e){return new Prepared(live,batch,raw,null,"真实行情或策略计算暂不可用；已有有效报价时仍检查固定/ATR止损",refresh);}
    }
    public void complete(Map<String,Object> job,UUID worker,String authorization,Prepared prepared) {
        UUID tenant=(UUID)job.get("tenant_id"),session=(UUID)job.get("session_id"),run=(UUID)job.get("id");
        TenantTransactions.run(db,tx,tenant,()->{
            db.queryForObject("select set_config('app.user_id',?,true)",String.class,job.get("owner_id").toString());
            var s=account(session,true);
            var rows=db.queryForList("select * from paper_trading.paper_automation_run where id=? and enabled and revision=? and lease_owner=? and lease_until>clock_timestamp() for update",run,job.get("revision"),worker);
            if(rows.isEmpty())return null;var r=rows.get(0);eligible(s);
            if("DENIED".equals(authorization)) {
                db.update("update paper_trading.paper_automation_run set enabled=false where id=?",run);
                db.update("update paper_trading.paper_order set status='CANCELLED',reserved_cash=0 where automation_run_id=? and status in ('PENDING','PARTIAL')",run);
                finish(run,"FORBIDDEN","创建者权限已失效，已停止；已有持仓保留");return null;
            }
            if(!"ALLOWED".equals(authorization)){finish(run,"ERROR","暂时无法核验权限，本轮不执行");return null;}
            if(!"ACTIVE".equals(s.get("status"))){finish(run,"PAUSED","账户已暂停，恢复后继续");return null;}
            JsonNode receipt=prepared==null?null:prepared.dataRefresh();
            boolean updated=receipt!=null && "READY".equals(receipt.path("state").asText())
                && r.get("contract").equals(receipt.path("contract").asText()) && startupKey(run).equals(receipt.path("requestKey").asText());
            if(updated)recordRefresh(run,receipt);
            else db.update("update paper_trading.paper_order set status='CANCELLED',reserved_cash=0,updated_at=now() where automation_run_id=? and offset_type='OPEN' and status in ('PENDING','PARTIAL')",run);
            if(prepared==null||prepared.quotes()==null){
                finish(run,updated?"ERROR":"REFRESHING",updated?"历史已更新，等待有效实时行情":"启动前正在重新拉取最新数据，尚未开仓");return null;
            }
            var p=position(session,(String)r.get("contract"));var c=prepared.quotes().quotes().get(r.get("contract"));
            if(!fresh(c)){finish(run,updated?"WAITING":"REFRESHING",updated?"最新历史数据已更新；休市或行情未就绪，等待有效报价":"正在重新拉取最新日线和分钟数据；尚未放行开仓");return null;}
            if(n(p,"direction")!=n(job,"observed_direction")||n(p,"lots")!=n(job,"observed_lots")
                ||d(p,"average_price").compareTo(d(job,"observed_average"))!=0){finish(run,"WAITING","持仓已变化，下轮重新评估");return null;}
            String day=prepared.chart().path("expectedTradingDate").asText("");
            boolean trinity=TRINITY.equals(r.get("strategy"));
            if (trinity) {
                // Do not chase an old entry after a feed gap, a reversal, or a failed execution window.
                boolean revoke=prepared.decision()==null || "FLATTEN".equals(prepared.decision().signal());
                db.update("""
                    update paper_trading.paper_order set status='CANCELLED',reserved_cash=0,updated_at=now()
                    where automation_run_id=? and offset_type='OPEN' and status in ('PENDING','PARTIAL')
                      and (? or created_at<clock_timestamp()-interval '2 minutes')
                    """,run,revoke);
            }
            int ownPending=db.queryForObject("select count(*) from paper_trading.paper_order where automation_run_id=? and status in ('PENDING','PARTIAL')",Integer.class,run);
            if(ownPending>0) {
                if(endWindow(r,c,prepared.chart()))db.update("update paper_trading.paper_order set status='CANCELLED',reserved_cash=0 where automation_run_id=? and offset_type='OPEN' and status in ('PENDING','PARTIAL')",run);
                portfolio.refreshAutomation(session,prepared.quotes(),run);
                db.update("update paper_trading.paper_automation_run set entry_atr=(select risk_atr from paper_trading.paper_order where automation_run_id=? and offset_type='OPEN' and status in ('FILLED','PARTIAL') order by created_at desc limit 1) where id=?",run,run);
                finish(run,"RUNNING","已按有效行情检查策略挂单，下一轮重新评估持仓");return null;
            }
            String reason=protection(r,p,c,prepared.chart());
            if(reason==null&&!updated){finish(run,receipt!=null&&"FAILED".equals(receipt.path("state").asText())?"ERROR":"REFRESHING",receipt==null?"等待最新数据":receipt.path("message").asText("等待最新数据"));return null;}
            if(reason==null && prepared.decision()==null){finish(run,"ERROR",prepared.error());return null;}
            StrategyDecision decision=prepared.decision()==null?new StrategyDecision((String)r.get("strategy"),"持仓保护","protection-v1","HOLD","持仓保护",null,0,0,null):prepared.decision();
            String signal=reason==null?decision.signal():"FLATTEN";
            Instant time=reason==null?decision.signalTime():c.quote().dataTimestamp();
            if(time==null){finish(run,"WARMING",decision.reason());return null;}
            if (trinity && c.quote().dataTimestamp().isBefore(time)) {
                finish(run,"WAITING","等待读取信号确认后的报价");
                return null;
            }
            if(reason==null && r.get("last_signal_time")!=null && !time.isAfter(instant(r.get("last_signal_time")))) {
                finish(run,"RUNNING","同一根行情已处理，等待新信号");return null;
            }
            if(reason==null)reason=decision.reason();
            String execution="OBSERVED";
            boolean close="FLATTEN".equals(signal), add=trinity && "ADD_LONG".equals(signal);
            boolean entry=add || Set.of("BUY","SELL").contains(signal);
            if (trinity && "HOLD".equals(signal)) {
                finish(run,"WAITING",reason);
                return null;
            }
            if(entry && (day.equals(r.get("blocked_trading_date")) || endWindow(r,c,prepared.chart()))) {
                execution="BLOCKED";reason="日内收盘窗口不再开仓";
            } else if(entry && Boolean.TRUE.equals(r.get("intraday_only")) && prepared.chart().path("tradingSessions").path("day").isEmpty()) {
                execution="BLOCKED";reason="真实交易时段尚未就绪，日内策略暂不开仓";
            } else if(close && n(p,"lots")==0 || entry && !add && n(p,"lots")>0
                || add && (n(p,"direction")!=1 || n(p,"lots")!=1 || n(r,"lots")!=2)) {
                execution="BLOCKED";reason=trinity ? "当前持仓不符合该信号的执行条件" : "已有持仓不加仓；平仓后等待新的突破，不立即反手";
            } else if(entry || close) {
                int pending=db.queryForObject("select count(*) from paper_trading.paper_order where session_id=? and contract=? and status in ('PENDING','PARTIAL')",Integer.class,session,r.get("contract"));
                if(pending>0){execution="BLOCKED";reason="该合约已有挂单，本轮不重复提交";}
                else if(entry && (!Set.of("MA20_MACD","BUY_AND_HOLD",TRINITY).contains(r.get("strategy"))
                    || trinity && (d(r,"stop_loss_atr").signum()>0 || d(r,"take_profit_atr").signum()>0))
                    && (decision.atr()==null||decision.atr().signum()<=0)){execution="BLOCKED";reason="真实交割合约ATR不足，等待日线";}
                else {
                    String side=close?(n(p,"direction")>0?"SELL":"BUY"):add?"BUY":signal;
                    // Rejected reversal closes can retry on a later quote until the position is flat.
                    String key="auto:"+run+":"+(trinity && close ? c.quote().dataTimestamp() : time);
                    int quantity = close ? n(p,"lots") : trinity ? 1 : n(r,"lots");
                    try {
                        portfolio.automatedOrder(session,new PlaceOrderRequest(key,side,close?"CLOSE":"OPEN","MARKET",quantity,null,null,(String)r.get("contract")),prepared.quotes(),run,reason,decision.atr());
                        var o=db.queryForMap("select status,rejection_reason from paper_trading.paper_order where session_id=? and client_order_id=?",session,key);
                        execution=(String)o.get("status");if(o.get("rejection_reason")!=null)reason=o.get("rejection_reason").toString();
                        if(entry && "FILLED".equals(execution))db.update("update paper_trading.paper_automation_run set entry_atr=? where id=?",decision.atr(),run);
                        if(close && endWindow(r,c,prepared.chart()))db.update("update paper_trading.paper_automation_run set blocked_trading_date=? where id=?",day,run);
                    } catch(IllegalStateException error){execution="BLOCKED";reason=error.getMessage();}
                }
            }
            // Warming is retried on this bar; a real HOLD/blocked/executed signal is consumed exactly once.
            if(!"WARMING".equals(signal)) {
                db.update("""
                    insert into paper_trading.paper_automation_event(id,run_id,signal_time,signal,status,reason,evidence)
                    values (?,?,?,?,?,?,?::jsonb) on conflict(run_id,signal_time) do update
                    set status=excluded.status,reason=excluded.reason,evidence=paper_trading.paper_automation_event.evidence||excluded.evidence
                    where paper_trading.paper_automation_event.signal='FLATTEN'
                      and paper_trading.paper_automation_event.status in ('BLOCKED','REJECTED')
                    """,
                    UUID.randomUUID(),run,Timestamp.from(time),signal,execution,reason,StrategyWorkflowStore.json(Map.of("nodeTrace",decision.nodeTrace()==null?List.of():decision.nodeTrace())).toString());
                if (!(trinity && close && Set.of("BLOCKED","REJECTED").contains(execution)))
                    db.update("update paper_trading.paper_automation_run set last_signal_time=greatest(last_signal_time,?) where id=?",Timestamp.from(time),run);
            }
            finish(run,"WARMING".equals(signal)?"WARMING":"RUNNING",reason);return null;
        });
    }
    private String protection(Map<String,Object> r,Map<String,Object> p,LiveContext c,JsonNode chart) {
        if(n(p,"lots")==0)return null;
        if(endWindow(r,c,chart))return "日内收盘前一分钟清仓，随后等待下一交易日";
        BigDecimal move=c.quote().price().subtract(d(p,"average_price")).multiply(BigDecimal.valueOf(n(p,"direction")));
        if(n(r,"stop_loss_ticks")>0 && move.compareTo(c.spec().priceTick().multiply(BigDecimal.valueOf(-n(r,"stop_loss_ticks"))))<=0)return "固定跳数止损，平仓后等待新的信号";
        var atr=(BigDecimal)r.get("entry_atr");
        if(atr!=null && atr.signum()>0) {
            if(d(r,"stop_loss_atr").signum()>0 && move.compareTo(atr.multiply(d(r,"stop_loss_atr")).negate())<=0)return "策略ATR止损";
            if(d(r,"take_profit_atr").signum()>0 && move.compareTo(atr.multiply(d(r,"take_profit_atr")))>=0)return "策略ATR止盈";
        }return null;
    }
    private boolean endWindow(Map<String,Object> r,LiveContext c,JsonNode chart) {
        if(!Boolean.TRUE.equals(r.get("intraday_only")))return false;
        LocalTime end=null;
        for(var interval:chart.path("tradingSessions").path("day"))if(interval.isArray()&&interval.size()==2) {
            try {var candidate=LocalTime.parse(interval.get(1).asText());if(end==null||candidate.isAfter(end))end=candidate;}catch(RuntimeException ignored){}
        }
        var time=c.quote().dataTimestamp().atZone(ZoneId.of("Asia/Shanghai")).toLocalTime();
        return end!=null && !time.isBefore(end.minusSeconds(60)) && time.isBefore(end);
    }
    private Map<String,Object> position(UUID session,String contract) {
        var rows=db.queryForList("select * from paper_trading.paper_portfolio_position where session_id=? and contract=?",session,contract);
        if(rows.isEmpty())throw new IllegalArgumentException("请先在账户中添加该实际合约");return rows.get(0);
    }
    private void finish(UUID run,String status,String message) {
        db.update("update paper_trading.paper_automation_run set status=?,message=?,checked_at=clock_timestamp(),next_check_at=clock_timestamp()+interval '10 seconds',lease_owner=null,lease_until=null,updated_at=now() where id=?",status,message,run);
    }
    private void recordRefresh(UUID run,JsonNode receipt) {
        if(db.queryForObject("select count(*) from paper_trading.paper_automation_event where run_id=? and evidence->'dataRefresh'->>'requestKey'=? and evidence->'dataRefresh'->>'completedAt'=?",Integer.class,run,receipt.path("requestKey").asText(),receipt.path("completedAt").asText())>0)return;
        String reason="已重新拉取日线"+receipt.path("dailyCount").asInt()+"根、分钟线"+receipt.path("minuteCount").asInt()+"根；最新分钟 "+receipt.path("latestMinuteTime").asText();
        db.update("insert into paper_trading.paper_automation_event(id,run_id,signal_time,signal,status,reason,evidence) values (?,?,?,'DATA_READY','READY',?,?::jsonb) on conflict(run_id,signal_time) do update set evidence=paper_trading.paper_automation_event.evidence||excluded.evidence",
            UUID.randomUUID(),run,Timestamp.from(Instant.parse(receipt.path("completedAt").asText())),reason,StrategyWorkflowStore.json(Map.of("dataRefresh",receipt)).toString());
    }
    private static boolean fresh(LiveContext c) {return c!=null&&"LIVE".equals(c.marketState())&&"FRESH".equals(c.quote().dataStatus())&&c.quote().dataTimestamp()!=null
        &&!c.quote().dataTimestamp().isBefore(Instant.now().minusSeconds(60))&&!c.quote().dataTimestamp().isAfter(Instant.now().plusSeconds(10));}
    private static int n(Map<String,Object> r,String key){return ((Number)r.get(key)).intValue();}
    private static BigDecimal d(Map<String,Object> r,String key){return (BigDecimal)r.get(key);}
    private static Instant instant(Object v){return v instanceof Timestamp t?t.toInstant():(Instant)v;}
    private static Instant optionalInstant(Object v){return v==null?null:instant(v);}
}
