package com.aiquant.paper.service;

import com.aiquant.tenancy.TenantContext;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import static com.aiquant.paper.service.DecisionJournalService.fail;

/** Server calculations and imported user assertions remain different immutable source kinds. */
@Service
public class ResearchDecisionService {
 private final JdbcTemplate db;private final ObjectMapper json;private final DecisionJournalService journal;private final RestClient algorithm;
 public ResearchDecisionService(JdbcTemplate db,ObjectMapper json,DecisionJournalService journal,@Value("${aiquant.algorithm-base-url}") String url){
  this.db=db;this.json=json;this.journal=journal;var factory=new SimpleClientHttpRequestFactory();factory.setConnectTimeout(Duration.ofSeconds(2));factory.setReadTimeout(Duration.ofSeconds(45));
  algorithm=RestClient.builder().baseUrl(url).requestFactory(factory).build();
 }
 private JsonNode node(Object v){try{return json.reader().with(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS).readTree(v.toString());}catch(Exception e){throw fail(HttpStatus.BAD_REQUEST,"记录不是可读取的JSON。");}}
 private String canonical(JsonNode v){
  if(v.isObject()){var keys=new TreeSet<String>();v.fieldNames().forEachRemaining(keys::add);var parts=new ArrayList<String>();for(String k:keys)parts.add(json.valueToTree(k).toString()+":"+canonical(v.get(k)));return "{"+String.join(",",parts)+"}";}
  if(v.isArray()){var parts=new ArrayList<String>();v.forEach(n->parts.add(canonical(n)));return "["+String.join(",",parts)+"]";}
  return v.isNumber()?v.decimalValue().stripTrailingZeros().toString():v.toString();
 }
 private String hash(JsonNode v){try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(canonical(v).getBytes(StandardCharsets.UTF_8)));}catch(Exception e){throw new IllegalStateException(e);}}
 private void lock(UUID owner,UUID command){
  Boolean held=db.queryForObject("select pg_try_advisory_xact_lock(hashtextextended(?,0))",Boolean.class,TenantContext.current()+":"+owner+":"+command);
  if(!Boolean.TRUE.equals(held))throw fail(HttpStatus.CONFLICT,"同一请求仍在处理中，请保留参数稍后重试。");
 }
 private Map<String,Object> row(UUID owner,UUID id){var rows=db.queryForList("select * from paper_trading.decision_research_source where id=? and owner_id=?",id,owner);if(rows.isEmpty())throw fail(HttpStatus.NOT_FOUND,"研究来源不存在或不属于本人。");return rows.get(0);}
 private Map<String,Object> prior(UUID owner,UUID command,String kind,String inputHash){
  var rows=db.queryForList("select * from paper_trading.decision_research_source where owner_id=? and command_id=?",owner,command);
  if(rows.isEmpty())return null;var p=rows.get(0);if(!kind.equals(p.get("kind"))||!inputHash.equals(p.get("input_hash")))throw fail(HttpStatus.CONFLICT,"此请求编号已用于另一份内容。");return p;
 }
 private void instant(JsonNode n,String field){try{Instant.parse(n.path(field).asText());}catch(Exception e){throw fail(HttpStatus.BAD_REQUEST,field+"缺少有效的原始时间。");}}
 private void plan(JsonNode p){
  if(!p.isObject()||p.toString().length()>150000||p.path("planId").asText().isBlank()||p.path("planId").asText().length()>128||!p.path("contract").asText().matches("[A-Za-z]{1,4}[0-9]{3,4}")||!p.path("symbol").asText().matches("[A-Za-z]{1,4}[A-Za-z0-9]{0,8}")||!Set.of("EMPIRICAL","CULTURAL_COMPARE").contains(p.path("mode").asText())||!p.path("inputs").isObject()||!p.path("inputs").path("equity").isNumber()||p.path("inputs").path("equity").decimalValue().signum()<=0||!Set.of("WAIT","HOLD_POSITION","REDUCE","REVIEW_EXIT","PREPARE","CONDITIONAL_ENTRY").contains(p.path("action").asText()))throw fail(HttpStatus.BAD_REQUEST,"研究计划结构或实际合约不完整，请保留原日志导出备份。");
  instant(p,"createdAt");instant(p,"dataTimestamp");
 }
 private String symbol(String v){return v.matches("(?i)[a-z]{1,4}0")?v.substring(0,v.length()-1).toUpperCase()+"M":v.toUpperCase();}
 public Object calculate(UUID owner,UUID command,JsonNode inputs){
  if(!inputs.isObject()||inputs.toString().length()>32000||!inputs.path("symbol").asText().matches("[A-Za-z]{1,4}[A-Za-z0-9]{0,8}"))throw fail(HttpStatus.BAD_REQUEST,"核算输入不合法。");
  String fingerprint=hash(inputs);lock(owner,command);var prior=prior(owner,command,"SERVER_CALC",fingerprint);if(prior!=null)return calculated(prior);
  // Only inputs are accepted. A caller cannot submit a computed score/plan as a server result.
  String response=algorithm.post().uri("/api/v1/research/plan").body(inputs).retrieve().body(String.class);if(response==null||response.length()>180000)throw fail(HttpStatus.SERVICE_UNAVAILABLE,"研究核算响应不可用。");
  JsonNode snapshot=node(response);plan(snapshot);
  if(!symbol(inputs.path("symbol").asText()).equals(symbol(snapshot.path("symbol").asText()))||!inputs.path("mode").asText("EMPIRICAL").equals(snapshot.path("mode").asText())||inputs.hasNonNull("expectedContract")&&!inputs.path("expectedContract").asText().equals(snapshot.path("contract").asText()))throw fail(HttpStatus.CONFLICT,"研究响应与请求的品种、模式或交割月不一致。");
  UUID id=UUID.randomUUID();db.update("insert into paper_trading.decision_research_source(id,owner_id,kind,command_id,input_hash,source_hash,plan_hash,request,snapshot) values(?,?,'SERVER_CALC',?,?,?,?,?::jsonb,?::jsonb)",id,owner,command,fingerprint,hash(snapshot),hash(snapshot),inputs.toString(),snapshot.toString());return calculated(row(owner,id));
 }
 private Object calculated(Map<String,Object> r){return Map.of("sourceId",r.get("id"),"plan",node(r.get("snapshot")),"sourceHash",r.get("source_hash"));}
 public Object preview(UUID owner,UUID command,String scope,String sourceScope,boolean acknowledgeUnscoped,String raw){
  if(TenantContext.current()==null||!scope.equals(owner+":"+TenantContext.current()))throw fail(HttpStatus.FORBIDDEN,"本机日志作用域与当前账号或工作空间不一致，不能导入。");
  if(!scope.equals(sourceScope)&&!("UNSCOPED".equals(sourceScope)&&acknowledgeUnscoped))throw fail(HttpStatus.FORBIDDEN,"不能导入其他账号或工作空间的日志；未归属日志需要明确声明归属。");
  if(raw.length()>180000)throw fail(HttpStatus.BAD_REQUEST,"单条本机记录过大。");JsonNode entry=node(raw);JsonNode p=entry.path("plan");plan(p);instant(entry,"savedAt");
  if(!entry.path("id").asText().equals(p.path("planId").asText())||!Set.of("PLANNED","EXECUTED","ABANDONED").contains(entry.path("status").asText())||!entry.path("notes").isTextual()||entry.path("notes").asText().length()>4000||entry.hasNonNull("actualPnl")&&!entry.path("actualPnl").isNumber())throw fail(HttpStatus.BAD_REQUEST,"本机复盘结构不完整，请先导出原始日志。");
  String content=hash(entry);String inputHash=hash(json.createObjectNode().put("scope",scope).put("sourceScope",sourceScope).set("entry",entry));lock(owner,command);var prior=prior(owner,command,"LOCAL_IMPORT",inputHash);if(prior!=null)return summary(owner,prior);
  UUID id=UUID.randomUUID();db.update("insert into paper_trading.decision_research_source(id,owner_id,kind,command_id,input_hash,source_hash,plan_hash,request,snapshot,raw_payload) values(?,?,'LOCAL_IMPORT',?,?,?,?,?::jsonb,?::jsonb,?) on conflict do nothing",id,owner,command,inputHash,content,hash(p),json.createObjectNode().put("declaredScope",scope).put("sourceScope",sourceScope).put("ownershipIsUserDeclaration",true).toString(),entry.toString(),raw);
  var r=db.queryForMap("select * from paper_trading.decision_research_source where owner_id=? and kind='LOCAL_IMPORT' and source_hash=?",owner,content);return summary(owner,r);
 }
 private Map<String,Object> summary(UUID owner,Map<String,Object> r){
  var out=new LinkedHashMap<String,Object>();out.put("id",r.get("id"));out.put("kind",r.get("kind"));out.put("sourceHash",r.get("source_hash"));out.put("createdAt",r.get("created_at"));out.put("snapshot",node(r.get("snapshot")));out.put("request",node(r.get("request")));
  var linked=db.queryForList("select case_id from paper_trading.decision_source_link where source_id=? and owner_id=?",r.get("id"),owner);out.put("archivedCaseId",linked.isEmpty()?null:linked.get(0).get("case_id"));
  return out;
 }
 public Object source(UUID owner,UUID id){var r=row(owner,id);var out=summary(owner,r);out.put("rawPayload",r.get("raw_payload"));return out;}
 public Object archive(UUID owner,UUID id,boolean acknowledge,UUID target){
  var r=row(owner,id);boolean local="LOCAL_IMPORT".equals(r.get("kind"));if(local&&!acknowledge)throw fail(HttpStatus.BAD_REQUEST,"导入前需确认本机记录归属及未经核验的来源说明。");
  lock(owner,id);var existing=db.queryForList("select case_id from paper_trading.decision_source_link where source_id=? and owner_id=?",id,owner);
  if(!existing.isEmpty()){
   UUID saved=(UUID)existing.get(0).get("case_id");if(target!=null&&!saved.equals(target))throw fail(HttpStatus.CONFLICT,"该来源已经关联另一档案，不会静默重新归属。");return journal.detail(owner,saved);
  }
  JsonNode snapshot=node(r.get("snapshot")),p=local?snapshot.path("plan"):snapshot;String key=local?r.get("plan_hash").toString():id.toString();
  UUID caseId=target;
  if(target!=null){
   if(local)throw fail(HttpStatus.BAD_REQUEST,"本机导入按原计划内容归档，不附加到其他档案。");
   var rows=db.queryForList("select symbol from paper_trading.decision_case where id=? and owner_id=? for update",target,owner);
   if(rows.isEmpty())throw fail(HttpStatus.NOT_FOUND,"目标档案不存在或不属于本人。");if(!p.path("contract").asText().equals(rows.get(0).get("symbol")))throw fail(HttpStatus.CONFLICT,"新核算的实际合约与原档案不同，请明确新建档案，不自动换月。");
  }else{
   ObjectNode origin=json.createObjectNode();origin.put("id",id.toString());origin.put("kind",r.get("kind").toString());origin.put("symbol",p.path("contract").asText());origin.put("assetType","FUTURE");origin.put("label",local?"本机研究日志 · 未经服务端核验":"服务端研究核算 · "+("EMPIRICAL".equals(p.path("mode").asText())?"实证研究":"文化参考对照"));origin.put("observedAt",p.path("dataTimestamp").asText());origin.put("createdAt",((java.sql.Timestamp)r.get("created_at")).toInstant().toString());origin.put("algorithmVersion",p.path("modelVersion").asText("未提供"));origin.put("verification",local?"LOCAL_UNVERIFIED":"SERVER_CALCULATED");
   var evidence=origin.putObject("evidence");evidence.put("triggerSeconds",86400);evidence.put("featureAt",p.path("dataTimestamp").asText());if(!local)evidence.put("availableAt",p.path("createdAt").asText());
   db.update("insert into paper_trading.decision_case(id,owner_id,symbol,source_kind,source_key,origin) values(?,?,?,?,?,?::jsonb) on conflict do nothing",UUID.randomUUID(),owner,p.path("contract").asText(),r.get("kind"),key,origin.toString());
   caseId=db.queryForObject("select id from paper_trading.decision_case where owner_id=? and source_kind=? and source_key=?",UUID.class,owner,r.get("kind"),key);
  }
  db.update("insert into paper_trading.decision_source_link(owner_id,case_id,source_id) values(?,?,?) on conflict(source_id) do nothing",owner,caseId,id);db.update("update paper_trading.decision_case set updated_at=now() where id=? and owner_id=?",caseId,owner);return journal.detail(owner,caseId);
 }
}
