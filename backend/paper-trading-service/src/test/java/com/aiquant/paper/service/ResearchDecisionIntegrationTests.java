package com.aiquant.paper.service;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;

@EnabledIfEnvironmentVariable(named="PAPER_TEST_JDBC_URL",matches="jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/paper_test.*")
class ResearchDecisionIntegrationTests {
 DecisionJournalIntegrationTests f;ResearchDecisionService service;ObjectNode calculated;AtomicInteger calls=new AtomicInteger();
 @BeforeEach void setup()throws Exception{
  f=new DecisionJournalIntegrationTests();f.setup();
  calculated=(ObjectNode)f.json.readTree("""
   {"planId":"00000000-0000-4000-8000-000000000042","symbol":"JMM","contract":"JM2701","mode":"EMPIRICAL","modelVersion":"isolated-research-v1","createdAt":"2026-11-07T08:00:00+08:00","dataTimestamp":"2026-11-06T07:00:00Z","action":"WAIT","actionMessage":"等待方向，未形成开仓条件","scenarioDirection":"NONE","entryPrice":200,"stopPrice":null,"targetPrice":null,"newLots":0,"reduceLots":0,"maxLots":0,"riskBudget":1000,"gates":["isolated evidence gap"],"modeEvidence":{"score":10,"calibratedWinRate":null},"inputs":{"symbol":"JM0","mode":"EMPIRICAL","equity":100000}}
   """);
  f.market.createContext("/api/v1/research/plan",exchange->{calls.incrementAndGet();exchange.getRequestBody().readAllBytes();byte[] body=calculated.toString().getBytes(StandardCharsets.UTF_8);exchange.getResponseHeaders().add("Content-Type","application/json");exchange.sendResponseHeaders(200,body.length);exchange.getResponseBody().write(body);exchange.close();});
  service=new ResearchDecisionService(f.f.jdbc,f.json,f.service,"http://127.0.0.1:"+f.market.getAddress().getPort());
 }
 @AfterEach void close(){f.stop();}
 <T>T run(Supplier<T> task){return f.run(()->{f.f.jdbc.queryForObject("select set_config('app.research_read','true',true)",String.class);return task.get();});}
 JsonNode inputs(){return f.json.createObjectNode().put("symbol","JM0").put("mode","EMPIRICAL").put("equity",100000).put("forgedScore",99);}
 @SuppressWarnings("unchecked") Map<String,Object> compute(UUID command){return (Map<String,Object>)run(()->service.calculate(f.owner,command,inputs()));}
 UUID sourceId(Map<String,Object> row){return UUID.fromString(row.get("sourceId").toString());}
 @SuppressWarnings("unchecked") Map<String,Object> archive(UUID source,boolean ack,UUID target){return (Map<String,Object>)run(()->service.archive(f.owner,source,ack,target));}
 ObjectNode entry() {var e=f.json.createObjectNode();e.put("id",calculated.path("planId").asText());e.put("savedAt","2025-01-02T08:00:00+08:00");e.put("status","EXECUTED");e.put("actualPnl",123.45);e.put("notes","private self-reported result, not a ledger fill");e.set("plan",calculated.deepCopy());return e;}
 @SuppressWarnings("unchecked") Map<String,Object> preview(String raw,UUID command){return (Map<String,Object>)run(()->service.preview(f.owner,command,f.owner+":"+f.tenant,f.owner+":"+f.tenant,false,raw));}
 @Test void server_receipts_are_immutable_idempotent_and_do_not_turn_wait_into_entry(){
  UUID command=UUID.randomUUID();var a=compute(command);var b=compute(command);assertEquals(sourceId(a),sourceId(b));assertEquals(1,calls.get());
  assertEquals(10,((JsonNode)a.get("plan")).path("modeEvidence").path("score").asInt());
  var c=archive(sourceId(a),false,null);assertEquals(0,c.get("version"));assertEquals(0,((List<?>)c.get("plans")).size());assertEquals("SERVER_CALC",c.get("sourceKind"));
  assertEquals(c.get("id"),archive(sourceId(a),false,null).get("id"));assertEquals("WAIT",((JsonNode)((Map<?,?>)((List<?>)c.get("sources")).get(0)).get("snapshot")).path("action").asText());
  assertThrows(ResponseStatusException.class,()->run(()->service.calculate(f.owner,command,((ObjectNode)inputs()).put("equity",200000))));
  assertEquals(0,f.f.jdbc.queryForObject("select count(*) from paper_trading.paper_order",Integer.class));
 }
 @Test void import_requires_current_scope_and_explicit_unscoped_ownership(){
  String raw=entry().toString(),scope=f.owner+":"+f.tenant;
  assertThrows(ResponseStatusException.class,()->run(()->service.preview(f.owner,UUID.randomUUID(),"another-scope",scope,false,raw)));
  assertThrows(ResponseStatusException.class,()->run(()->service.preview(f.owner,UUID.randomUUID(),scope,"another-scope",true,raw)));
  assertThrows(ResponseStatusException.class,()->run(()->service.preview(f.owner,UUID.randomUUID(),scope,"UNSCOPED",false,raw)));
  var preview=(Map<?,?>)run(()->service.preview(f.owner,UUID.randomUUID(),scope,"UNSCOPED",true,raw));
  assertEquals("LOCAL_IMPORT",preview.get("kind"));assertThrows(ResponseStatusException.class,()->archive((UUID)preview.get("id"),false,null));
 }
 @Test void identical_imports_deduplicate_and_changed_notes_append_source_versions_without_fills(){
  ObjectNode e=entry();String raw=" \n"+e.toString()+"\n";var first=preview(raw,UUID.randomUUID());var retry=preview(e.toPrettyString(),UUID.randomUUID());assertEquals(first.get("id"),retry.get("id"));
  UUID id=(UUID)first.get("id");var c=archive(id,true,null);assertEquals("LOCAL_IMPORT",c.get("sourceKind"));
  assertEquals(raw,((Map<?,?>)run(()->service.source(f.owner,id))).get("rawPayload"));
  e.put("notes","changed private review");var next=preview(e.toString(),UUID.randomUUID());assertNotEquals(id,next.get("id"));var updated=archive((UUID)next.get("id"),true,null);assertEquals(c.get("id"),updated.get("id"));assertEquals(2,((List<?>)updated.get("sources")).size());
  for(String table:List.of("decision_review","paper_session","paper_order","paper_fill"))assertEquals(0,f.f.jdbc.queryForObject("select count(*) from paper_trading."+table,Integer.class));
 }
 @Test void imported_plan_changes_with_the_same_client_id_are_not_silently_overwritten(){
  ObjectNode e=entry();var a=archive((UUID)preview(e.toString(),UUID.randomUUID()).get("id"),true,null);((ObjectNode)e.get("plan")).put("entryPrice",201);
  var b=archive((UUID)preview(e.toString(),UUID.randomUUID()).get("id"),true,null);assertNotEquals(a.get("id"),b.get("id"));
 }
 @Test void owner_tenant_and_revoked_research_access_hide_private_sources(){
  UUID id=sourceId(compute(UUID.randomUUID()));UUID caseId=(UUID)archive(id,false,null).get("id");UUID other=UUID.randomUUID();
  assertThrows(ResponseStatusException.class,()->f.run(f.tenant,other,()->service.source(other,id)));
  assertThrows(ResponseStatusException.class,()->f.run(UUID.randomUUID(),f.owner,()->service.source(f.owner,id)));
  run(()->{f.f.jdbc.queryForObject("select set_config('app.research_read','false',true)",String.class);assertThrows(ResponseStatusException.class,()->service.source(f.owner,id));assertEquals(0,((List<?>)((Map<?,?>)f.service.detail(f.owner,caseId)).get("sources")).size());return null;});
 }
 @Test void attach_keeps_original_event_and_versions_and_rejects_silent_contract_roll(){
  UUID caseId=f.create();var before=f.detail(caseId);var c=archive(sourceId(compute(UUID.randomUUID())),false,caseId);assertEquals(before.get("origin"),c.get("origin"));assertEquals(0,c.get("version"));assertEquals(1,((List<?>)c.get("sources")).size());
  calculated.put("contract","JM2705");UUID changed=sourceId(compute(UUID.randomUUID()));assertThrows(ResponseStatusException.class,()->archive(changed,false,caseId));
  var separate=archive(changed,false,null);assertEquals("JM2705",separate.get("symbol"));assertNotEquals(caseId,separate.get("id"));
 }
 @Test void culture_comparison_and_reported_profit_keep_their_original_identity(){
  var e=entry();((ObjectNode)e.get("plan")).put("mode","CULTURAL_COMPARE");var p=preview(e.toString(),UUID.randomUUID());var c=archive((UUID)p.get("id"),true,null);
  var snapshot=(JsonNode)((Map<?,?>)((List<?>)c.get("sources")).get(0)).get("snapshot");assertEquals("CULTURAL_COMPARE",snapshot.path("plan").path("mode").asText());assertEquals("EXECUTED",snapshot.path("status").asText());assertEquals(123.45,snapshot.path("actualPnl").asDouble());assertEquals(0,((List<?>)c.get("plans")).size());
 }
}
