package com.aiquant.paper.service;

import com.aiquant.paper.api.PaperRequests.CreateSessionRequest;
import com.aiquant.paper.client.SimulationDataClient;
import com.aiquant.paper.client.SimulationDataClient.*;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;

/** References the original alert and existing paper ledger; never fabricates a fill. */
@Service
public class DecisionJournalService {
    private final JdbcTemplate db;private final SimulationDataClient data;private final PaperTradingService paper;
    private final ObjectMapper json;private final RestClient market;
    public DecisionJournalService(JdbcTemplate db,SimulationDataClient data,PaperTradingService paper,ObjectMapper json,@Value("${aiquant.market-base-url}") String url){
        this.db=db;this.data=data;this.paper=paper;this.json=json;
        var factory=new SimpleClientHttpRequestFactory();factory.setConnectTimeout(Duration.ofSeconds(2));factory.setReadTimeout(Duration.ofSeconds(10));
        market=RestClient.builder().baseUrl(url).requestFactory(factory).build();
    }
    public record Fields(@NotBlank @Pattern(regexp="LONG|SHORT") String side,
        @NotNull @DecimalMin("0.000001") @DecimalMax("1000000000") BigDecimal entry,
        @NotNull @DecimalMin("0.000001") @DecimalMax("1000000000") BigDecimal stop,
        @NotNull @DecimalMin("0.000001") @DecimalMax("1000000000") BigDecimal target,
        @Min(1) @Max(100000) int lots,
        @NotNull @DecimalMin("1000") @DecimalMax("1000000000") BigDecimal equity,
        @NotNull @DecimalMin("0.01") @DecimalMax("1000000000") BigDecimal budget,
        @NotBlank @Size(max=2000) String hypothesis,@NotBlank @Size(max=2000) String invalidation,@NotNull Instant validUntil){}
    public record SavePlan(@NotNull UUID commandId,@Min(0) int expectedVersion,@NotNull @Valid Fields fields){}
    public record Review(@NotNull UUID commandId,@NotBlank @Pattern(regexp="WAITING|ABANDONED|PAPER_REVIEW") String outcome,@NotBlank @Size(max=4000) String notes){}
    public static ResponseStatusException fail(HttpStatus status,String message){return new ResponseStatusException(status,message);}
    private JsonNode node(Object value){
        if(value==null)return json.nullNode();
        if(value instanceof JsonNode n){if(n.isObject()&&n.path("value").isTextual())value=n.path("value").asText();else return n;}
        try{return json.reader().with(com.fasterxml.jackson.databind.DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS).readTree(value.toString());}
        catch(java.io.IOException e){throw new IllegalStateException("决策证据或计划读取失败，请刷新重试。");}
    }
    private Map<String,Object> row(UUID owner,UUID id,boolean lock){
        var rows=db.queryForList("select * from paper_trading.decision_case where id=? and owner_id=?"+(lock?" for update":""),id,owner);
        if(rows.isEmpty())throw fail(HttpStatus.NOT_FOUND,"决策档案不存在或不属于本人。");return rows.get(0);
    }
    private Map<String,Object> plan(UUID owner,UUID id,UUID planId){
        row(owner,id,false);var rows=db.queryForList("select * from paper_trading.decision_plan where id=? and case_id=? and owner_id=?",planId,id,owner);
        if(rows.isEmpty())throw fail(HttpStatus.NOT_FOUND,"计划版本不存在于此档案。");return rows.get(0);
    }
    private Map<String,Object> publicCase(Map<String,Object> r){
        var out=new LinkedHashMap<String,Object>();for(String k:List.of("id","symbol","version"))out.put(k,r.get(k));
        out.put("sourceKind",r.get("source_kind"));
        out.put("origin",node(r.get("origin")));out.put("createdAt",r.get("created_at"));out.put("updatedAt",r.get("updated_at"));return out;
    }
    public Object list(UUID owner,int page,int size){
        int p=Math.max(1,page),s=Math.max(1,Math.min(50,size));
        var items=db.queryForList("select id,symbol,version,source_kind,(origin-'evidence') as origin,created_at,updated_at from paper_trading.decision_case where owner_id=? order by updated_at desc,id desc limit ? offset ?",owner,s,(long)(p-1)*s).stream().map(this::publicCase).toList();
        return Map.of("items",items,"total",db.queryForObject("select count(*) from paper_trading.decision_case where owner_id=?",Long.class,owner),"page",p,"size",s);
    }
    /** One database snapshot and server clock; no market reads or execution qualification. */
    public Object inbox(UUID owner,String filter,int page,int size){
        if(!Set.of("ALL","UNPLANNED","EXPIRING","EXPIRED","REVIEW").contains(filter))throw fail(HttpStatus.BAD_REQUEST,"未知待办筛选条件。");
        int p=Math.max(1,page),s=Math.max(1,Math.min(50,size));
        String sql="""
            with clock as (select ?::timestamptz as_of), records as (
              select c.id,c.symbol,coalesce(c.origin->>'label','原始观察') label,c.source_kind,c.updated_at,
                     p.id plan_id,p.version,case when jsonb_typeof(p.fields->'validUntil')='number'
                       then to_timestamp((p.fields->>'validUntil')::double precision) else (p.fields->>'validUntil')::timestamptz end valid_until,
                     b.session_id,r.outcome latest_outcome,r.created_at reviewed_at,
                     exists(select 1 from paper_trading.decision_review rr where rr.owner_id=c.owner_id and rr.plan_id=p.id and rr.outcome='PAPER_REVIEW') paper_reviewed
              from paper_trading.decision_case c
              left join paper_trading.decision_plan p on p.case_id=c.id and p.owner_id=c.owner_id and p.version=c.version
              left join paper_trading.decision_paper b on b.plan_id=p.id and b.owner_id=c.owner_id
              left join lateral (select outcome,created_at from paper_trading.decision_review where plan_id=p.id and owner_id=c.owner_id order by created_at desc,id desc limit 1) r on true
              where c.owner_id=?
            ), classified as (
              select records.*,case when plan_id is null then 'UNPLANNED' when valid_until<=as_of then 'EXPIRED'
                     when valid_until<=as_of+interval '24 hours' then 'EXPIRING' else 'PLANNED' end timing,
                     session_id is not null and not paper_reviewed and coalesce(latest_outcome,'')<>'ABANDONED' needs_review
              from records cross join clock
            ), counts as (
              select count(*) "all",count(*) filter(where timing='UNPLANNED') unplanned,
                     count(*) filter(where timing='EXPIRING') expiring,count(*) filter(where timing='EXPIRED') expired,
                     count(*) filter(where needs_review) review from classified
            ), filtered as (
              select * from classified where ?='ALL' or timing=? or (?='REVIEW' and needs_review)
            ), paged as (
              select id,symbol,label,source_kind "sourceKind",updated_at "updatedAt",plan_id "planId",version,
                     valid_until "validUntil",session_id "sessionId",latest_outcome "latestOutcome",reviewed_at "reviewedAt",
                     timing,"needs_review" "needsReview",
                     case when timing='EXPIRED' then 0 when timing='EXPIRING' then 1 when needs_review then 2 when timing='UNPLANNED' then 3 else 4 end "sortOrder"
              from filtered order by "sortOrder",valid_until nulls last,updated_at desc,id limit ? offset ?
            ) select jsonb_build_object('asOf',(select as_of from clock),'counts',(select to_jsonb(counts) from counts),
                     'items',coalesce((select jsonb_agg(to_jsonb(paged)-'sortOrder' order by "sortOrder","validUntil" nulls last,"updatedAt" desc,id) from paged),'[]'::jsonb),
                     'total',(select count(*) from filtered),'page',?,'size',?,'filter',?)::text
            """;
        return node(db.queryForObject(sql,String.class,java.sql.Timestamp.from(Instant.now()),owner,filter,filter,filter,s,(long)(p-1)*s,p,s,filter));
    }
    public Object forSession(UUID owner,UUID sessionId){
        var rows=db.queryForList("select p.case_id as \"caseId\",p.id as \"planId\",p.version from paper_trading.decision_paper b join paper_trading.decision_plan p on p.id=b.plan_id where b.session_id=? and b.owner_id=?",sessionId,owner);
        return rows.isEmpty()?Map.of():rows.get(0);
    }
    public Object fromEvent(UUID owner,long eventId,String identity){
        // The event is fetched from its authoritative service, never accepted from a client snapshot.
        JsonNode event=market.get().uri("/api/v1/market/monitors/events/{id}",eventId).header("X-Aiquant-Identity",identity).retrieve().body(JsonNode.class);
        if(event==null||event.path("id").asLong()!=eventId||!"FUTURE".equals(event.path("assetType").asText())||!event.path("symbol").asText().matches("[A-Za-z]{1,4}[0-9]{3,4}"))throw fail(HttpStatus.BAD_REQUEST,"原事件不是有效的实际期货合约。");
        var frozen=event.deepCopy();((com.fasterxml.jackson.databind.node.ObjectNode)frozen).set("evidence",node(event.get("evidence")));
        UUID id=UUID.randomUUID();db.update("insert into paper_trading.decision_case(id,owner_id,symbol,source_event_id,origin) values(?,?,?,?,?::jsonb) on conflict(tenant_id,owner_id,source_event_id) do nothing",id,owner,event.path("symbol").asText(),eventId,frozen.toString());
        UUID saved=db.queryForObject("select id from paper_trading.decision_case where owner_id=? and source_event_id=?",UUID.class,owner,eventId);return detail(owner,saved);
    }
    public Object detail(UUID owner,UUID id){
        var out=publicCase(row(owner,id,false));
        out.put("sources",db.queryForList("select s.id,s.kind,s.source_hash as \"sourceHash\",s.snapshot,s.request,s.created_at as \"createdAt\" from paper_trading.decision_source_link l join paper_trading.decision_research_source s on s.id=l.source_id where l.case_id=? and l.owner_id=? order by l.created_at desc,s.id",id,owner).stream().map(r->{r.put("snapshot",node(r.get("snapshot")));r.put("request",node(r.get("request")));return r;}).toList());
        out.put("plans",db.queryForList("select id,version,fields,created_at as \"createdAt\" from paper_trading.decision_plan where case_id=? and owner_id=? order by version desc",id,owner).stream().map(r->{r.put("fields",node(r.get("fields")));return r;}).toList());
        out.put("reviews",db.queryForList("select r.id,r.plan_id as \"planId\",p.version,r.outcome,r.notes,r.created_at as \"createdAt\" from paper_trading.decision_review r join paper_trading.decision_plan p on p.id=r.plan_id where p.case_id=? and r.owner_id=? order by r.created_at desc",id,owner));
        out.put("paper",db.queryForList("select b.plan_id as \"planId\",p.version,b.session_id as \"sessionId\",b.created_at as \"createdAt\" from paper_trading.decision_paper b join paper_trading.decision_plan p on p.id=b.plan_id where p.case_id=? and b.owner_id=? order by b.created_at desc",id,owner));return out;
    }
    public Object save(UUID owner,UUID id,SavePlan request){
        var current=row(owner,id,true);var fields=json.valueToTree(request.fields());
        var prior=db.queryForList("select * from paper_trading.decision_plan where owner_id=? and command_id=?",owner,request.commandId());
        if(!prior.isEmpty()){
            var p=prior.get(0);boolean same=fields.equals((a,b)->a.isNumber()&&b.isNumber()?a.decimalValue().compareTo(b.decimalValue()):a.equals(b)?0:1,node(p.get("fields")));
            if(!id.equals(p.get("case_id"))||!same||((Number)p.get("version")).intValue()!=request.expectedVersion()+1)throw fail(HttpStatus.CONFLICT,"此请求编号已用于另一份计划。");return detail(owner,id);
        }
        int version=((Number)current.get("version")).intValue();if(version!=request.expectedVersion())throw fail(HttpStatus.CONFLICT,"计划已被另一页面修改，请刷新比较后保存。");
        Fields f=request.fields();boolean longSide="LONG".equals(f.side());
        if(longSide?(f.stop().compareTo(f.entry())>=0||f.target().compareTo(f.entry())<=0):(f.stop().compareTo(f.entry())<=0||f.target().compareTo(f.entry())>=0))throw fail(HttpStatus.BAD_REQUEST,"保护价和目标价与计划方向不符。");
        db.update("insert into paper_trading.decision_plan(id,owner_id,case_id,version,command_id,fields) values(?,?,?,?,?,?::jsonb)",UUID.randomUUID(),owner,id,version+1,request.commandId(),fields.toString());
        db.update("update paper_trading.decision_case set version=version+1,updated_at=now() where id=? and owner_id=?",id,owner);return detail(owner,id);
    }
    public Object check(UUID owner,UUID id,UUID planId){
        var c=row(owner,id,false);var p=plan(owner,id,planId);return readiness(c,p);
    }
    Map<String,Object> readiness(Map<String,Object> c,Map<String,Object> p){
        return readiness(c,p,null);
    }
    private Map<String,Object> readiness(Map<String,Object> c,Map<String,Object> p,LiveContext checkedLive){
        var reasons=new ArrayList<String>();var result=new LinkedHashMap<String,Object>();
        result.put("planId",p.get("id"));result.put("version",p.get("version"));result.put("checkedAt",Instant.now());result.put("qualifiedForProfit",false);
        if(!c.get("version").equals(p.get("version")))reasons.add("此版本已被新计划替代；仍可阅读和复盘。");
        try{
            Fields f=json.treeToValue(node(p.get("fields")),Fields.class);LiveContext live=checkedLive==null?data.live(c.get("symbol").toString()):checkedLive;
            result.putAll(evaluate(f,c.get("symbol").toString(),live,reasons));
        }catch(Exception e){reasons.add("当前行情或合约规格不可核验，保留草稿，稍后重试。");}
        result.put("ready",reasons.isEmpty());result.put("reasons",reasons);result.put("meaning","仅核验独立手动模拟账户的准备条件，不自动下单；保护价情景试算，跳空和滑点可能使损失超预算。");return result;
    }
    static Map<String,Object> evaluate(Fields f,String symbol,LiveContext live,List<String> reasons){
        QuoteSnapshot q=live.quote();ContractSpec s=live.spec();Instant now=Instant.now();
        if(f.validUntil()==null||!f.validUntil().isAfter(now))reasons.add("计划有效期已过，请修订新版本。");
        if(!symbol.equals(live.contract())||!symbol.equals(q.symbol())||!symbol.equals(s.contract()))reasons.add("实际合约发生变化，不能沿用旧保护参数。");
        if(!"LIVE".equals(live.marketState())||!"FRESH".equals(q.dataStatus())||q.dataTimestamp()==null||q.dataTimestamp().isBefore(now.minusSeconds(30))||q.dataTimestamp().isAfter(now.plusSeconds(2))||live.checkedAt()==null||live.checkedAt().isBefore(now.minusSeconds(30))||live.checkedAt().isAfter(now.plusSeconds(2)))reasons.add("当前非可交易时段或报价过时，不能进入新模拟。");
        boolean buy="LONG".equals(f.side());BigDecimal entry=buy?f.entry().max(q.price()):f.entry().min(q.price());
        if(buy?f.stop().compareTo(entry)>=0:f.stop().compareTo(entry)<=0)reasons.add("当前价格已越过保护条件，请修订计划。");
        if(buy?q.price().compareTo(f.target())>=0:q.price().compareTo(f.target())<=0)reasons.add("当前价格已越过目标参考，请修订计划。");
        if(f.entry().remainder(s.priceTick()).signum()!=0||f.stop().remainder(s.priceTick()).signum()!=0||f.target().remainder(s.priceTick()).signum()!=0)reasons.add("计划价格未对齐该合约最小跳动。");
        BigDecimal lots=BigDecimal.valueOf(f.lots()),multiplier=BigDecimal.valueOf(s.volumeMultiple());
        BigDecimal cost=s.commissionPerLot().multiply(BigDecimal.valueOf(2)).add(s.priceTick().multiply(multiplier).multiply(BigDecimal.valueOf(4)));
        BigDecimal loss=entry.subtract(f.stop()).abs().multiply(multiplier).add(cost).multiply(lots),margin=s.marginPerLot().multiply(lots);
        if(loss.compareTo(f.budget())>0)reasons.add("保护价情景损失与摩擦费用超过本计划预算。");
        if(f.budget().compareTo(f.equity())>0||margin.compareTo(f.equity())>0)reasons.add("预算或保证金占用超过所填模拟资金。");
        var out=new LinkedHashMap<String,Object>();out.put("scenarioLoss",loss);out.put("marginRequired",margin);out.put("quote",q);out.put("contractSpec",s);out.put("assumptions","按计划与现价较不利者、双边佣金、每边2跳预留；不保证保护价可成交，不含外部账户敞口。");return out;
    }
    public Object paper(UUID owner,UUID id,UUID planId,UUID command){
        var c=row(owner,id,true);var p=plan(owner,id,planId);
        var used=db.queryForList("select plan_id,session_id from paper_trading.decision_paper where owner_id=? and command_id=?",owner,command);
        if(!used.isEmpty()&&!planId.equals(used.get(0).get("plan_id")))throw fail(HttpStatus.CONFLICT,"此请求编号已用于另一模拟。");
        var prior=db.queryForList("select session_id from paper_trading.decision_paper where plan_id=? and owner_id=?",planId,owner);
        if(!prior.isEmpty())return Map.of("sessionId",prior.get(0).get("session_id"),"created",false);
        LiveContext live=data.live(c.get("symbol").toString());
        var ready=readiness(c,p,live);if(!Boolean.TRUE.equals(ready.get("ready")))throw fail(HttpStatus.CONFLICT,String.join("；",(List<String>)ready.get("reasons")));
        try{
            Fields f=json.treeToValue(node(p.get("fields")),Fields.class);
            var session=paper.createDecisionSession(new CreateSessionRequest("计划模拟 "+c.get("symbol"),"LIVE",c.get("symbol").toString(),null,null,f.equity(),new BigDecimal("0.15"),BigDecimal.ZERO,new BigDecimal("2"),new BigDecimal("0.05"),false,"MANUAL",1,new BigDecimal("2"),new BigDecimal("3")),live);
            // The existing runner is manual. This link is provenance, not an executable strategy/order.
            db.update("insert into paper_trading.decision_paper(owner_id,plan_id,session_id,command_id,readiness) values(?,?,?,?,?::jsonb)",owner,planId,UUID.fromString(session.get("id").toString()),command,json.valueToTree(ready).toString());
            return Map.of("sessionId",session.get("id"),"created",true);
        }catch(com.fasterxml.jackson.core.JsonProcessingException e){throw new IllegalStateException("计划读取失败");}
    }
    public Object review(UUID owner,UUID id,UUID planId,Review review){
        plan(owner,id,planId);
        db.update("insert into paper_trading.decision_review(id,owner_id,plan_id,command_id,outcome,notes) values(?,?,?,?,?,?) on conflict(tenant_id,owner_id,command_id) do nothing",UUID.randomUUID(),owner,planId,review.commandId(),review.outcome(),review.notes());
        var r=db.queryForMap("select plan_id,outcome,notes from paper_trading.decision_review where owner_id=? and command_id=?",owner,review.commandId());
        if(!planId.equals(r.get("plan_id"))||!review.outcome().equals(r.get("outcome"))||!review.notes().equals(r.get("notes")))throw fail(HttpStatus.CONFLICT,"此请求编号已用于另一条复盘。");return detail(owner,id);
    }
}
