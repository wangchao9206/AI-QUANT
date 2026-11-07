package com.aiquant.paper.service;

import com.aiquant.paper.client.SimulationDataClient.LiveContext;
import com.aiquant.tenancy.TenantTransactions;
import com.fasterxml.jackson.databind.*;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import java.util.function.Supplier;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import static com.aiquant.paper.service.DecisionJournalService.fail;

@Service
public class PlanAlertStore {
 private final JdbcTemplate db;private final TransactionTemplate tx;private final ObjectMapper json;
 public PlanAlertStore(JdbcTemplate db,TransactionTemplate tx,ObjectMapper json){this.db=db;this.tx=tx;this.json=json;}
 private JsonNode node(Object v){try{return json.reader().with(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS).readTree(v.toString());}catch(Exception e){throw new IllegalStateException("提醒记录不可读取。");}}
 private Map<String,Object> plan(UUID owner,UUID caseId,UUID planId,boolean lock){
  var cases=db.queryForList("select id,version,symbol from paper_trading.decision_case where id=? and owner_id=?"+(lock?" for update":""),caseId,owner);
  if(cases.isEmpty())throw fail(HttpStatus.NOT_FOUND,"档案不属于本人或已不存在。");
  var rows=db.queryForList("select id,version,fields from paper_trading.decision_plan where id=? and case_id=? and owner_id=?",planId,caseId,owner);
  if(rows.isEmpty())throw fail(HttpStatus.NOT_FOUND,"计划版本不在此档案中。");
  var p=new LinkedHashMap<>(rows.get(0));p.put("symbol",cases.get(0).get("symbol"));p.put("latest",cases.get(0).get("version").equals(p.get("version")));return p;
 }
 private Map<String,Object> state(Object raw){var n=node(raw);return n.has("price")&&n.has("at")?Map.of("price",n.path("price").decimalValue(),"at",n.path("at").asText()):Map.of();}
 private DecisionJournalService.Fields fields(Map<String,Object> p){try{return json.treeToValue(node(p.get("fields")),DecisionJournalService.Fields.class);}catch(Exception e){throw new IllegalStateException("计划参数不可读取。");}}
 public Object read(UUID owner,UUID caseId,UUID planId){plan(owner,caseId,planId,false);var out=new LinkedHashMap<String,Object>();var rows=db.queryForList("select revision,enabled,entry_mode as \"entryMode\",status,message,checked_at as \"checkedAt\" from paper_trading.decision_alert_subscription where owner_id=? and plan_id=?",owner,planId);out.put("subscription",rows.isEmpty()?null:rows.get(0));out.put("events",events(owner,planId,false,1).get("items"));return out;}
 public Object edit(UUID owner,UUID caseId,UUID planId,boolean enabled,String mode,long revision){
  db.queryForList("select pg_advisory_xact_lock(hashtextextended(?,0))",owner.toString());var p=plan(owner,caseId,planId,true);if(!Set.of("BREAKOUT","PULLBACK").contains(mode))throw fail(HttpStatus.BAD_REQUEST,"未知入场穿越方式。");
  var rows=db.queryForList("select revision,entry_mode from paper_trading.decision_alert_subscription where plan_id=? and owner_id=?",planId,owner);
  long current=rows.isEmpty()?0:((Number)rows.get(0).get("revision")).longValue();
  if(revision!=current)throw fail(HttpStatus.CONFLICT,"提醒状态已变化，请刷新后重试。");
  if(!rows.isEmpty()&&!rows.get(0).get("entry_mode").equals(mode))throw fail(HttpStatus.CONFLICT,"入场方式已冻结；修改方式请保存新的计划版本。");
  if(enabled){if(!Boolean.TRUE.equals(p.get("latest"))||!fields(p).validUntil().isAfter(Instant.now()))throw fail(HttpStatus.CONFLICT,"仅最新且未过期的计划可启用提醒。");
   if(db.queryForObject("select count(*) from paper_trading.decision_alert_subscription where owner_id=? and enabled and plan_id<>?",Integer.class,owner,planId)>=20)throw fail(HttpStatus.CONFLICT,"每人最多启用20个计划提醒。");}
  if(rows.isEmpty())db.update("insert into paper_trading.decision_alert_subscription(owner_id,plan_id,enabled,entry_mode,status) values(?,?,?,?,?)",owner,planId,enabled,mode,enabled?"STARTING":"PAUSED");
  else db.update("update paper_trading.decision_alert_subscription set revision=revision+1,enabled=?,status=?,message='',state='{}',lease_owner=null,lease_until=null,next_check_at=now(),updated_at=now() where owner_id=? and plan_id=?",enabled,enabled?"STARTING":"PAUSED",owner,planId);
  return read(owner,caseId,planId);
 }
 public Map<String,Object> events(UUID owner,UUID planId,boolean unread,int page){
  String where=" from paper_trading.decision_alert_event e join paper_trading.decision_plan p on p.id=e.plan_id join paper_trading.decision_case c on c.id=p.case_id where e.owner_id=?";
  var args=new ArrayList<Object>();args.add(owner);if(planId!=null){where+=" and e.plan_id=?";args.add(planId);}if(unread)where+=" and e.acknowledged_at is null";
  long total=db.queryForObject("select count(*)"+where,Long.class,args.toArray());int current=Math.max(1,page);args.add(20);args.add((long)(current-1)*20);
  var rows=db.queryForList("select e.id,p.case_id as \"caseId\",p.id as \"planId\",p.version,c.symbol,e.kind,e.observed_at as \"observedAt\",e.created_at as \"createdAt\",e.acknowledged_at as \"acknowledgedAt\",e.evidence"+where+" order by e.created_at desc,e.id desc limit ? offset ?",args.toArray());rows.forEach(r->r.put("evidence",node(r.get("evidence"))));
  return Map.of("items",rows,"total",total,"page",current,"size",20);
 }
 public void acknowledge(UUID owner,UUID id){if(db.update("update paper_trading.decision_alert_event set acknowledged_at=coalesce(acknowledged_at,now()) where owner_id=? and id=?",owner,id)!=1)throw fail(HttpStatus.NOT_FOUND,"提醒不存在于本人档案。");}
 // Background enumeration uses the service role; all completion writes re-enter owner RLS.
 public List<Map<String,Object>> claim(UUID worker,int limit){return tx.execute(s->{var rows=db.queryForList("select a.*,p.case_id,c.symbol from paper_trading.decision_alert_subscription a join paper_trading.decision_plan p on p.id=a.plan_id join paper_trading.decision_case c on c.id=p.case_id where a.enabled and a.next_check_at<=now() and (a.lease_until is null or a.lease_until<now()) order by a.next_check_at,a.plan_id limit ? for update of a skip locked",Math.max(1,Math.min(4,limit)));for(var r:rows)db.update("update paper_trading.decision_alert_subscription set lease_owner=?,lease_until=now()+interval '45 seconds' where plan_id=?",worker,r.get("plan_id"));return rows;});}
 public void complete(Map<String,Object> job,UUID worker,String authorization,LiveContext live,Instant now){
  UUID tenant=(UUID)job.get("tenant_id"),owner=(UUID)job.get("owner_id"),planId=(UUID)job.get("plan_id"),caseId=(UUID)job.get("case_id");
  TenantTransactions.run(db,tx,tenant,()->{db.queryForObject("select set_config('app.user_id',?,true)",String.class,owner.toString());var p=plan(owner,caseId,planId,true);
   var rows=db.queryForList("select * from paper_trading.decision_alert_subscription where owner_id=? and plan_id=? and enabled and revision=? and lease_owner=? and lease_until>clock_timestamp() for update",owner,planId,job.get("revision"),worker);
   if(rows.isEmpty())return null;Instant wall=Instant.now(),checkedAt=wall.isAfter(now)?wall:now;var sub=rows.get(0);var f=fields(p);PlanAlertEvaluator.Result result;boolean enabled=true;
   if(!Boolean.TRUE.equals(p.get("latest"))){result=PlanAlertEvaluator.empty("SUPERSEDED","已被新计划替代，旧订阅停止。");enabled=false;}
   else if("DENIED".equals(authorization)){result=PlanAlertEvaluator.empty("FORBIDDEN","创建者权限已失效；重新授权后需手动启用。");enabled=false;}
   else if(!"ALLOWED".equals(authorization))result=PlanAlertEvaluator.empty("ERROR","授权服务暂不可用，未生成提醒。");
   else if(!f.validUntil().isAfter(checkedAt)){result=new PlanAlertEvaluator.Result("EXPIRED","计划已到期，订阅停止。",Map.of(),List.of("EXPIRED"));enabled=false;}
   else result=PlanAlertEvaluator.evaluate(p.get("symbol").toString(),f,sub.get("entry_mode").toString(),state(sub.get("state")),live,checkedAt);
   for(String kind:result.kinds()){
    var evidence=json.createObjectNode();evidence.set("plan",node(p.get("fields")));evidence.put("caseId",caseId.toString());evidence.put("planId",planId.toString());evidence.put("version",((Number)p.get("version")).intValue());evidence.put("symbol",p.get("symbol").toString());evidence.put("entryMode",sub.get("entry_mode").toString());evidence.put("samplingSeconds",60);evidence.put("confirmation",kind.equals("EXPIRED")?"SERVER_DEADLINE":"OBSERVED_PRICE_CROSS");evidence.set("previousObservation",node(sub.get("state")));evidence.set("currentObservation",json.valueToTree(result.state()));if(live!=null)evidence.set("quote",json.valueToTree(live.quote()));
    Instant at=kind.equals("EXPIRED")?f.validUntil():live.quote().dataTimestamp();
    db.update("insert into paper_trading.decision_alert_event(id,owner_id,plan_id,kind,observed_at,evidence) values(?,?,?,?,?,?::jsonb) on conflict(plan_id,kind) do nothing",UUID.randomUUID(),owner,planId,kind,Timestamp.from(at),evidence.toString());
   }
   db.update("update paper_trading.decision_alert_subscription set enabled=?,status=?,message=?,state=?::jsonb,checked_at=?,next_check_at=? ,lease_owner=null,lease_until=null,updated_at=now() where plan_id=? and owner_id=?",enabled,result.status(),result.message(),json.valueToTree(result.state()).toString(),Timestamp.from(checkedAt),Timestamp.from(checkedAt.plusSeconds(60)),planId,owner);return null;
  });
 }
}
