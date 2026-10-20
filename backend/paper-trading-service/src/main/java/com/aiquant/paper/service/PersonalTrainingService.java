package com.aiquant.paper.service;

import com.aiquant.paper.api.PersonalTrainingController.*;
import com.aiquant.paper.api.PaperRequests.*;
import com.aiquant.paper.client.SimulationDataClient.HistoricalBar;
import com.aiquant.paper.service.PersonalStrategyEngine.*;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.sql.Timestamp;
import java.time.*;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class PersonalTrainingService {
    private static final ZoneId SHANGHAI=ZoneId.of("Asia/Shanghai");
    private static final UUID DEFAULT_ID=UUID.nameUUIDFromBytes(PersonalStrategyEngine.ENGINE.getBytes(StandardCharsets.UTF_8));
    private final JdbcTemplate jdbc;
    private final TransactionTemplate tx;
    private final ObjectMapper mapper;
    private final PaperTradingService paper;
    private final PersonalStrategyEngine engine=new PersonalStrategyEngine();

    public PersonalTrainingService(JdbcTemplate jdbc,TransactionTemplate tx,ObjectMapper mapper,PaperTradingService paper) {
        this.jdbc=jdbc;this.tx=tx;this.mapper=mapper;this.paper=paper;
    }
    private String json(Object v) {
        try {return mapper.writeValueAsString(v);} catch(Exception e){throw new IllegalStateException("训练快照无法编码");}
    }
    private Map<String,Object> object(Object value) {
        try{return mapper.readValue(value.toString(),new TypeReference<Map<String,Object>>(){});}
        catch(Exception e){throw new IllegalStateException("训练快照无法读取，保留原数据并停止推进");}
    }
    private Rules rules(Object value) {
        try {var r=mapper.readValue(value.toString(),Rules.class);r.validate();return r;}
        catch(Exception e){throw new IllegalStateException("策略版本参数不合法，禁止继续训练");}
    }
    private void ensureDefault() {
        jdbc.update("""
            insert into paper_trading.personal_strategy_version(id,title,hypothesis,validation_plan,rules,engine_version)
            values(?,?,?, ?,?::jsonb,?) on conflict(id) do nothing
            """,DEFAULT_ID,"生存优先 · 趋势突破回踩 v1","趋势确认后只做突破回踩，以少亏和一致执行替代预测与频繁交易；尚未验证收益优势。",
            "预先划分训练/留出区间，覆盖上涨、下跌、震荡与多个品种；至少20次完整平仓后审视费用、回撤与纪律，样本不足只作描述。",json(Rules.defaults()),PersonalStrategyEngine.ENGINE);
    }
    public List<Map<String,Object>> versions() {
        ensureDefault();
        return jdbc.query("select * from paper_trading.personal_strategy_version order by created_at desc,id",(rs,n)->{
            var v=new LinkedHashMap<String,Object>();
            v.put("id",rs.getObject("id"));v.put("parentId",rs.getObject("parent_id"));v.put("title",rs.getString("title"));
            v.put("hypothesis",rs.getString("hypothesis"));v.put("validationPlan",rs.getString("validation_plan"));
            v.put("rules",object(rs.getString("rules")));v.put("engineVersion",rs.getString("engine_version"));v.put("createdAt",rs.getTimestamp("created_at").toInstant());return v;
        });
    }
    public List<Map<String,Object>> createVersion(CreateVersionRequest r) {
        r.rules().validate();ensureDefault();
        Integer count=jdbc.queryForObject("select count(*) from paper_trading.personal_strategy_version where id=?",Integer.class,r.parentId());
        if(count==null||count!=1) throw new IllegalArgumentException("父版本不存在");
        jdbc.update("insert into paper_trading.personal_strategy_version(id,parent_id,title,hypothesis,validation_plan,rules,engine_version) values(?,?,?,?,?,?::jsonb,?)",
            UUID.randomUUID(),r.parentId(),r.title().trim(),r.hypothesis().trim(),r.validationPlan().trim(),json(r.rules()),PersonalStrategyEngine.ENGINE);
        return versions();
    }
    public Map<String,Object> create(CreateRunRequest r) {
        ensureDefault();
        if(r.startDate().isAfter(r.endDate())||r.endDate().isAfter(LocalDate.now(SHANGHAI))) throw new IllegalArgumentException("训练起止日期不合法");
        Integer versionCount=jdbc.queryForObject("select count(*) from paper_trading.personal_strategy_version where id=?",Integer.class,r.versionId());
        if(versionCount==null||versionCount!=1) throw new IllegalArgumentException("策略版本不存在");
        var version=jdbc.queryForMap("select * from paper_trading.personal_strategy_version where id=?",r.versionId());
        if(!PersonalStrategyEngine.ENGINE.equals(version.get("engine_version"))) throw new IllegalArgumentException("该引擎版本当前只读，请创建受支持的新版本；不会改写旧训练");
        Rules rule=rules(version.get("rules"));
        var request=new CreateSessionRequest("个人训练·"+r.name().trim(),"HISTORICAL",r.symbol(),r.startDate().minusDays(365),r.endDate(),
            r.initialCash(),new BigDecimal("0.15"),new BigDecimal("0.0001"),BigDecimal.ONE,new BigDecimal("0.05"),false);
        var session=paper.createSession(request);
        UUID id=UUID.fromString(session.get("id").toString());
        try {
            Integer first=jdbc.queryForObject("select min(bar_index) from paper_trading.paper_scenario_bar where session_id=? and (market_time at time zone 'Asia/Shanghai')::date>=?",Integer.class,id,r.startDate());
            if(first==null||first<66) throw new IllegalArgumentException("所选开始日期前不足预热数据；请将训练起点后移，至少留出66根日线及11个完整周");
            int warm=first-1;
            for(int remaining=warm;remaining>0;remaining-=Math.min(100,remaining)) paper.advance(id,new AdvanceRequest(Math.min(100,remaining)));
            tx.executeWithoutResult(status->{
                jdbc.update("insert into paper_trading.personal_training(session_id,version_id,training_mode,training_start,rules,peak_equity) values(?,?,?,?,?::jsonb,?)",
                    id,r.versionId(),r.trainingMode(),r.startDate(),json(rule),r.initialCash());
                if("WARMUP".equals(plan(id).state())) throw new IllegalArgumentException("预热周线或换月证据不足，请后移起点或选择其它已备齐数据的品种");
            });
            return detail(id);
        } catch(RuntimeException e) {
            // Only the new account created by this call is disposable.
            jdbc.update("delete from paper_trading.paper_session where id=?",id);
            throw e;
        }
    }
    public Map<String,Object> runs(int page,int size) {
        bounds(page,size);
        var rows=jdbc.query("""
            select s.id,s.name,s.symbol,s.status,s.equity,s.initial_cash,s.current_market_time,t.version_id,t.training_mode,v.title,t.risk_halted
            from paper_trading.personal_training t join paper_trading.paper_session s on s.id=t.session_id
            join paper_trading.personal_strategy_version v on v.id=t.version_id
            order by t.created_at desc,s.id desc limit ? offset ?
            """,(rs,n)->Map.ofEntries(Map.entry("id",rs.getObject("id")),Map.entry("name",rs.getString("name")),Map.entry("symbol",rs.getString("symbol")),
                Map.entry("status",rs.getString("status")),Map.entry("equity",rs.getBigDecimal("equity")),Map.entry("initialCash",rs.getBigDecimal("initial_cash")),
                Map.entry("currentMarketTime",rs.getTimestamp("current_market_time").toInstant()),Map.entry("versionId",rs.getObject("version_id")),
                Map.entry("trainingMode",rs.getString("training_mode")),Map.entry("versionTitle",rs.getString("title")),Map.entry("riskHalted",rs.getBoolean("risk_halted"))),size,(long)(page-1)*size);
        return page(page,size,jdbc.queryForObject("select count(*) from paper_trading.personal_training",Long.class),rows);
    }
    private Map<String,Object> run(UUID id) {
        Integer count=jdbc.queryForObject("select count(*) from paper_trading.personal_training where session_id=?",Integer.class,id);
        if(count==null||count==0) throw new IllegalArgumentException("个人训练不存在");
        return jdbc.queryForMap("select * from paper_trading.personal_training where session_id=?",id);
    }
    @SuppressWarnings("unchecked")
    public Plan plan(UUID id) {
        var r=run(id);
        var session=paper.detail(id);
        String engineVersion=jdbc.queryForObject("select engine_version from paper_trading.personal_strategy_version where id=?",String.class,r.get("version_id"));
        if(!PersonalStrategyEngine.ENGINE.equals(engineVersion)) return new Plan("ARCHIVED","WAIT",0,0,null,0,0,0,null,null,null,null,null,null,
            List.of("此训练的旧引擎当前只读，原始计划与记录保持不变，请创建受支持的新版本；不能用新引擎改写旧结果"));
        int cursor=((Number)session.get("currentBarIndex")).intValue();
        Instant clock=Instant.parse(session.get("currentMarketTime").toString());
        var bars=jdbc.query("select * from paper_trading.paper_scenario_bar where session_id=? and bar_index<=? and market_time<=? order by bar_index",(rs,n)->
            new HistoricalBar(rs.getTimestamp("market_time").toInstant(),rs.getString("contract"),rs.getBigDecimal("open_price"),rs.getBigDecimal("high_price"),rs.getBigDecimal("low_price"),rs.getBigDecimal("close_price"),rs.getLong("volume"),rs.getLong("open_interest")),id,cursor,Timestamp.from(clock));
        LocalDate date=LocalDate.ofInstant(clock,SHANGHAI);
        var rolls=jdbc.query("select * from paper_trading.paper_roll_event where session_id=? and execution_date<=? order by execution_date",(rs,n)->
            new Roll(rs.getDate("execution_date").toLocalDate(),rs.getDouble("old_open"),rs.getDouble("new_open")),id,date);
        var position=(Map<String,Object>)session.get("position");
        Integer entries=jdbc.queryForObject("""
            select count(distinct order_id) from paper_trading.paper_fill
            where session_id=? and offset_type='OPEN' and (market_time at time zone 'Asia/Shanghai')::date>=? and market_time<=?
            """,Integer.class,id,PersonalStrategyEngine.week(date),Timestamp.from(clock));
        var a=new Account(number(session,"equity"),number(session,"initialCash"),((Number)position.get("lots")).intValue(),((Number)position.get("direction")).intValue(),
            number(position,"averagePrice"),number(session,"priceTick"),((Number)session.get("volumeMultiple")).intValue(),number(session,"marginPerLot"),number(session,"commissionPerLot"),
            number(session,"marginRate"),number(session,"feeRate"),number(session,"slippageTicks"),r.get("stop_price")==null?null:number(r,"stop_price"),
            (Integer)r.get("entry_bar"),(Integer)r.get("last_exit_bar"),entries==null?0:entries,Boolean.TRUE.equals(r.get("risk_halted")));
        if(cursor>=((Number)session.get("totalBars")).intValue()-1) return new Plan("END","WAIT",a.direction(),0,a.stopPrice(),0,0,0,null,null,null,null,null,null,
            List.of("已到样本末尾；未平持仓按最后已完成收盘估值，不补造未来成交，也不把浮盈称为已实现收益"));
        return engine.evaluate(bars,rolls,a,rules(r.get("rules")));
    }
    public Map<String,Object> detail(UUID id) {
        return tx.execute(status->{
            run(id);
            jdbc.queryForMap("select id from paper_trading.paper_session where id=? for update",id);
            return detailLocked(id);
        });
    }
    private Map<String,Object> detailLocked(UUID id) {
        var r=run(id);var result=new LinkedHashMap<String,Object>();
        result.put("session",paper.detail(id));result.put("plan",plan(id));result.put("versionId",r.get("version_id"));result.put("trainingMode",r.get("training_mode"));
        result.put("rules",object(r.get("rules")));result.put("trainingStart",r.get("training_start").toString());result.put("peakEquity",r.get("peak_equity"));
        result.put("riskHalted",r.get("risk_halted"));result.put("activeStop",r.get("stop_price"));
        var stats=jdbc.queryForMap("select count(*) as decisions,count(*) filter(where compliant) as compliant from paper_trading.personal_training_event where session_id=?",id);
        long total=((Number)stats.get("decisions")).longValue(),compliant=((Number)stats.get("compliant")).longValue();
        var metrics=new LinkedHashMap<String,Object>();metrics.put("decisions",total);metrics.put("compliant",compliant);
        metrics.put("humanAdherencePct","GUIDED".equals(r.get("training_mode"))&&total>0?100.0*compliant/total:null);
        metrics.put("closedFillFragments",jdbc.queryForObject("select count(*) from paper_trading.paper_fill where session_id=? and offset_type='CLOSE'",Long.class,id));
        var equities=jdbc.query("select (outcome->>'afterEquity')::numeric as equity from paper_trading.personal_training_event where session_id=? order by bar_index",(rs,n)->rs.getDouble("equity"),id);
        // A managed round trip never closes then reopens on the same bar.
        // Therefore OPEN-before-CLOSE is the conservative execution sequence
        // for ambiguous same-day entry/protection, even if DB timestamps tie.
        var fills=jdbc.query("""
            select f.offset_type,f.quantity,f.realized_pnl,f.fee,(e.plan->>'riskBudget')::numeric as budget
            from paper_trading.paper_fill f left join paper_trading.paper_order o on o.id=f.order_id
            left join paper_trading.personal_training_event e on e.session_id=f.session_id and o.client_order_id='personal-entry-'||e.command_id::text
            where f.session_id=? order by f.market_time,case when f.offset_type='OPEN' then 0 else 1 end,f.created_at,f.id
            """,(rs,n)->new PersonalTrainingStatistics.Fill(rs.getString("offset_type"),rs.getInt("quantity"),rs.getDouble("realized_pnl"),rs.getDouble("fee"),
                rs.getObject("budget")==null?null:rs.getDouble("budget")),id);
        var account=paper.detail(id);
        metrics.putAll(PersonalTrainingStatistics.calculate(number(account,"initialCash"),equities,fills));
        metrics.put("sampleWarning","不足20个独立完整交易且未经跨品种/留出区间验证时，不判断收益优势；平仓成交片段不等于独立交易次数。");
        result.put("metrics",metrics);return result;
    }
    @SuppressWarnings("unchecked")
    public Map<String,Object> step(UUID id,StepRequest request) {
        tx.executeWithoutResult(status->{
            // All mutators lock the account before training state, in this order.
            run(id);
            jdbc.queryForMap("select id from paper_trading.paper_session where id=? for update",id);
            var r=run(id);jdbc.queryForMap("select session_id from paper_trading.personal_training where session_id=? for update",id);
            Integer prior=jdbc.queryForObject("select count(*) from paper_trading.personal_training_event where session_id=? and command_id=?",Integer.class,id,request.commandId());
            if(prior!=null&&prior>0) return;
            var before=paper.detail(id);int index=((Number)before.get("currentBarIndex")).intValue();
            if(index!=request.expectedBarIndex()) throw new IllegalStateException("模拟时点已变化，请刷新后重新决定；没有重复下单");
            if(!"ACTIVE".equals(before.get("status"))) throw new IllegalStateException("训练已完成或暂停；暂停账户须先恢复，已有保护规则保持冻结");
            var p=plan(id);boolean automated="RULE_REPLAY".equals(r.get("training_mode"));
            if("ARCHIVED".equals(p.state())) throw new IllegalStateException("旧引擎训练当前只读，请另建新版本");
            if(automated&&!"FOLLOW".equals(request.action())) throw new IllegalArgumentException("规则回放只能按冻结策略执行；人的决策练习请选择手动训练");
            var position=(Map<String,Object>)before.get("position");int lots=((Number)position.get("lots")).intValue();
            if(lots==0&&"EXIT".equals(request.action())) throw new IllegalArgumentException("当前空仓，没有可提前平掉的持仓");
            boolean entering="ENTER".equals(p.action())&&"FOLLOW".equals(request.action());
            boolean ready=automated||(request.riskAccepted()&&request.stopAccepted()&&request.noRevenge()&&request.emotion()<3);
            boolean compliant=(!entering||ready)&&!(lots>0&&"EXIT".equals(request.action())&&!"EXIT".equals(p.action()))
                &&!(lots>0&&"EXIT".equals(p.action())&&"WAIT".equals(request.action()));
            var notes=new ArrayList<String>();
            if(entering&&!ready) notes.add("开仓被拦截：检查单未完成或情绪达到3/5；继续观察，不通过增加交易缓解情绪");
            if("WAIT".equals(request.action())&&"ENTER".equals(p.action())) notes.add("主动放弃有效候选；记录机会成本，但不强迫交易");
            if(lots>0&&"EXIT".equals(p.action())&&"WAIT".equals(request.action())) notes.add("拒绝延迟系统退出，按既定计划保护资金");
            if(lots>0&&"EXIT".equals(request.action())&&!"EXIT".equals(p.action())) notes.add("主动提前离场，与冻结系统有偏差；盈亏和执行分别复盘");
            if(p.stopPrice()!=null&&lots>0) jdbc.update("update paper_trading.personal_training set stop_price=? where session_id=?",BigDecimal.valueOf(p.stopPrice()),id);
            long closeBefore=countFills(id,"CLOSE"),openBefore=countFills(id,"OPEN");
            boolean atEnd="END".equals(p.state());
            if(!atEnd&&entering&&ready) {
                jdbc.update("update paper_trading.personal_training set stop_price=?,risk_budget=? where session_id=?",BigDecimal.valueOf(p.stopPrice()),BigDecimal.valueOf(p.riskBudget()),id);
                paper.trainingOrder(id,new PlaceOrderRequest("personal-entry-"+request.commandId(),p.direction()>0?"BUY":"SELL","OPEN","LIMIT",p.maxLots(),BigDecimal.valueOf(p.entryPrice()),null));
            } else if(!atEnd&&lots>0&&("EXIT".equals(p.action())||"EXIT".equals(request.action()))) {
                int direction=((Number)position.get("direction")).intValue();
                paper.trainingOrder(id,new PlaceOrderRequest("personal-exit-"+request.commandId(),direction>0?"SELL":"BUY","CLOSE","MARKET",lots,null,null));
            }
            var after=paper.trainingAdvance(id);
            jdbc.update("update paper_trading.paper_order set status='CANCELLED',updated_at=now() where session_id=? and status in ('PENDING','PARTIAL')",id);
            int afterIndex=((Number)after.get("currentBarIndex")).intValue();
            var nextPosition=(Map<String,Object>)after.get("position");int afterLots=((Number)nextPosition.get("lots")).intValue();
            if(countFills(id,"OPEN")>openBefore&&afterLots>0) jdbc.update("update paper_trading.personal_training set entry_bar=? where session_id=?",afterIndex,id);
            if(afterLots==0) {
                jdbc.update("update paper_trading.personal_training set stop_price=null,entry_bar=null where session_id=?",id);
                if(countFills(id,"CLOSE")>closeBefore) jdbc.update("update paper_trading.personal_training set last_exit_bar=? where session_id=?",afterIndex,id);
            }
            double peak=Math.max(number(r,"peak_equity"),number(after,"equity"));
            boolean halted=Boolean.TRUE.equals(r.get("risk_halted"))||number(after,"equity")<=peak*.92;
            jdbc.update("update paper_trading.personal_training set peak_equity=?,risk_halted=? where session_id=?",BigDecimal.valueOf(peak),halted,id);
            var outcome=new LinkedHashMap<String,Object>();outcome.put("beforeEquity",before.get("equity"));outcome.put("afterEquity",after.get("equity"));
            outcome.put("afterMarketTime",after.get("currentMarketTime"));outcome.put("afterBarIndex",afterIndex);outcome.put("positionLots",afterLots);
            outcome.put("closedFillFragments",countFills(id,"CLOSE")-closeBefore);outcome.put("openedFillFragments",countFills(id,"OPEN")-openBefore);
            outcome.put("notes",notes);outcome.put("riskHalted",halted);outcome.put("automated",automated);
            outcome.put("orders",jdbc.queryForList("select side,offset_type,order_type,status,rejection_reason from paper_trading.paper_order where session_id=? and client_order_id in (?,?)",id,"personal-entry-"+request.commandId(),"personal-exit-"+request.commandId()));
            jdbc.update("insert into paper_trading.personal_training_event(id,session_id,command_id,bar_index,market_time,action,compliant,emotion,notes,plan,outcome) values(?,?,?,?,?,?,?,?,?,?::jsonb,?::jsonb)",
                UUID.randomUUID(),id,request.commandId(),index,Timestamp.from(Instant.parse(before.get("currentMarketTime").toString())),request.action(),compliant,request.emotion(),request.notes(),json(p),json(outcome));
        });
        return detail(id);
    }
    private long countFills(UUID id,String offset) {return jdbc.queryForObject("select count(*) from paper_trading.paper_fill where session_id=? and offset_type=?",Long.class,id,offset);}
    public Map<String,Object> events(UUID id,int page,int size) {
        run(id);bounds(page,size);
        var items=jdbc.query("select * from paper_trading.personal_training_event where session_id=? order by bar_index desc limit ? offset ?",(rs,n)->{
            var row=new LinkedHashMap<String,Object>();row.put("id",rs.getObject("id"));row.put("barIndex",rs.getInt("bar_index"));
            row.put("marketTime",rs.getTimestamp("market_time").toInstant());row.put("action",rs.getString("action"));row.put("compliant",rs.getBoolean("compliant"));
            row.put("emotion",rs.getInt("emotion"));row.put("notes",rs.getString("notes"));row.put("plan",object(rs.getString("plan")));row.put("outcome",object(rs.getString("outcome")));return row;
        },id,size,(long)(page-1)*size);
        return page(page,size,jdbc.queryForObject("select count(*) from paper_trading.personal_training_event where session_id=?",Long.class,id),items);
    }
    public Map<String,Object> reflections(UUID id,int page,int size) {
        bounds(page,size);if(id!=null) run(id);
        String where=id==null?"":" where session_id=?";
        Object[] args=id==null?new Object[]{size,(long)(page-1)*size}:new Object[]{id,size,(long)(page-1)*size};
        var rows=jdbc.query("select * from paper_trading.personal_reflection"+where+" order by created_at desc,id desc limit ? offset ?",(rs,n)->{
            var row=new LinkedHashMap<String,Object>();row.put("id",rs.getObject("id"));row.put("sessionId",rs.getObject("session_id"));row.put("eventId",rs.getObject("event_id"));
            row.put("category",rs.getString("category"));row.put("content",rs.getString("content"));row.put("createdAt",rs.getTimestamp("created_at").toInstant());return row;
        },args);
        Long total=id==null?jdbc.queryForObject("select count(*) from paper_trading.personal_reflection",Long.class)
            :jdbc.queryForObject("select count(*) from paper_trading.personal_reflection where session_id=?",Long.class,id);
        return page(page,size,total,rows);
    }
    public void reflect(ReflectionRequest r) {
        if(r.sessionId()!=null) run(r.sessionId());
        if(r.eventId()!=null) {
            Integer count=jdbc.queryForObject("select count(*) from paper_trading.personal_training_event where id=? and session_id=?",Integer.class,r.eventId(),r.sessionId());
            if(count==null||count!=1) throw new IllegalArgumentException("复盘事件不属于当前训练");
        }
        jdbc.update("insert into paper_trading.personal_reflection(id,session_id,event_id,category,content) values(?,?,?,?,?)",UUID.randomUUID(),r.sessionId(),r.eventId(),r.category(),r.content().trim());
    }
    private double number(Map<String,Object> row,String key) {return ((Number)row.get(key)).doubleValue();}
    private void bounds(int page,int size) {if(page<1||size<1||size>100) throw new IllegalArgumentException("页码至少1，每页1–100条");}
    private Map<String,Object> page(int page,int size,Long total,Object rows) {return Map.of("page",page,"pageSize",size,"total",total,"items",rows);}
}
