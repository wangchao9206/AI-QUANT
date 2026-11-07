package com.aiquant.market.monitor;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import com.aiquant.tenancy.TenantTransactions;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.*;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.*;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;

@EnabledIfEnvironmentVariable(named="MONITOR_TEST_DATABASE_URL",matches=".*identity_test.*")
class MonitorStoreIntegrationTests {
 MonitorStore store;JdbcTemplate db;TransactionTemplate tx;ObjectMapper mapper=new ObjectMapper();
 final UUID tenant=UUID.randomUUID(),other=UUID.randomUUID(),actor=UUID.randomUUID();MonitorStore.Scope scope,foreign,option;
 @BeforeEach void setup(){var ds=new DriverManagerDataSource(System.getenv("MONITOR_TEST_DATABASE_URL"),"identity_test","isolated-test-only");db=new JdbcTemplate(ds);db.execute("drop schema if exists market cascade");Flyway.configure().dataSource(ds).schemas("market").defaultSchema("market").load().migrate();tx=new TransactionTemplate(new DataSourceTransactionManager(ds));store=new MonitorStore(db,tx,mapper);scope=new MonitorStore.Scope(tenant,actor,"FUTURE");foreign=new MonitorStore.Scope(other,actor,"FUTURE");option=new MonitorStore.Scope(tenant,actor,"OPTION");}
 Map<String,Object> validation(String kind){return Map.of("spec",Map.of("assetType",kind,"symbol",kind.equals("OPTION")?"DCE.m2701-C-3000":"RB2701","seconds",60,"parameters",Map.of("rules",List.of("DAILY_MA_BREAKOUT_UP"))),"metadata",Map.of("symbol","RB2701"));}
 UUID create(MonitorStore.Scope selected,boolean enabled){return (UUID)store.save(selected,null,"integration",enabled,0,validation(selected.kind())).get("id");}
 void status(HttpStatus expected,Runnable work){assertEquals(expected,assertThrows(ResponseStatusException.class,work::run).getStatusCode());}
 Map<String,Object> result(String key){return Map.of("status","READY","message","ok","state",Map.of("seen",key),"events",List.of(Map.of("key",key,"rule","BIG_BUY","label","大额买向成交增量","observedAt",Instant.now().toString(),"evidence",Map.of("lots",120),"algorithmVersion","depth-monitor-v1")));}
 @Test void individual_event_lookup_keeps_tenant_and_asset_boundaries(){create(scope,true);UUID worker=UUID.randomUUID();assertTrue(store.complete(store.claim(worker,1).get(0),worker,result("decision-source")));long id=((Number)store.events(scope,"",null,false,1,20).items().get(0).get("id")).longValue();assertEquals(id,((Number)((Map<?,?>)store.event(scope,id)).get("id")).longValue());status(HttpStatus.NOT_FOUND,()->store.event(foreign,id));status(HttpStatus.NOT_FOUND,()->store.event(option,id));status(HttpStatus.NOT_FOUND,()->store.event(scope,id+1));}
 @Test void rows_events_and_audit_are_tenant_and_asset_scoped(){UUID id=create(scope,true);assertEquals(1,store.list(scope,"",1,20).total());assertEquals(0,store.list(foreign,"",1,20).total());assertEquals(0,store.list(option,"",1,20).total());status(HttpStatus.NOT_FOUND,()->store.get(foreign,id));status(HttpStatus.NOT_FOUND,()->store.enable(option,id,false,0));UUID worker=UUID.randomUUID();assertTrue(store.complete(store.claim(worker,1).get(0),worker,result("one")));assertEquals(1,store.events(scope,"",null,false,1,20).total());assertEquals(0,store.events(foreign,"",null,false,1,20).total());assertEquals(0,store.events(option,"",null,false,1,20).total());TenantTransactions.run(db,tx,other,()->{assertEquals(0,db.queryForObject("select count(*) from market.live_monitor",Integer.class));assertEquals(0,db.update("update market.live_monitor set name='forged' where id=?",id));return null;});assertEquals(1,db.queryForObject("select count(*) from market.live_monitor_audit",Integer.class));}
 @Test void pause_and_versions_discard_in_flight_trigger_results(){UUID id=create(scope,true),worker=UUID.randomUUID();var job=store.claim(worker,1).get(0);store.enable(scope,id,false,0);assertFalse(store.complete(job,worker,result("late")));assertEquals(0,store.events(scope,"",null,false,1,20).total());status(HttpStatus.CONFLICT,()->store.enable(scope,id,true,0));assertEquals("PAUSED",store.get(scope,id).get("status"));store.enable(scope,id,true,1);assertEquals("STARTING",store.get(scope,id).get("status"));assertEquals(2L,store.get(scope,id).get("version"));}
 @Test void leases_state_and_dedup_survive_a_new_store(){UUID id=create(scope,true),worker=UUID.randomUUID();var job=store.claim(worker,1).get(0);assertTrue(store.claim(UUID.randomUUID(),1).isEmpty());assertTrue(store.complete(job,worker,result("persisted")));var restored=new MonitorStore(db,tx,new ObjectMapper());db.update("update market.live_monitor set next_check_at=now() where id=?",id);var resumed=restored.claim(worker,1).get(0);assertEquals("persisted",restored.object(resumed.get("state")).get("seen"));assertTrue(restored.complete(resumed,worker,result("persisted")));assertEquals(1,restored.events(scope,"",null,false,1,20).total());}
 @Test void global_and_tenant_capacity_limits_are_enforced(){UUID first=create(scope,true);for(int i=1;i<20;i++)create(scope,true);status(HttpStatus.CONFLICT,()->create(scope,true));for(int i=0;i<12;i++)create(foreign,true);status(HttpStatus.CONFLICT,()->create(new MonitorStore.Scope(UUID.randomUUID(),actor,"OPTION"),true));UUID paused=create(scope,false);status(HttpStatus.CONFLICT,()->store.enable(scope,paused,true,0));store.archive(scope,first,0);status(HttpStatus.NOT_FOUND,()->store.get(scope,first));assertEquals(20,store.list(scope,"",1,50).total());}
 @Test void forged_tenant_headers_are_rejected(){var controller=new MonitorController(store,mock(MonitorClients.class),mapper,"integration-secret-longer-than-32-characters");var req=new MockHttpServletRequest();req.setRequestURI("/api/v1/options/monitors");req.addHeader("X-Tenant-Id",tenant.toString());status(HttpStatus.UNAUTHORIZED,()->controller.scope(req));req.addHeader("X-Aiquant-Identity","forged.payload");status(HttpStatus.UNAUTHORIZED,()->controller.scope(req));}
 @Test void expired_options_stop_automatically_without_emitting_a_signal(){UUID id=create(option,true),worker=UUID.randomUUID();var job=store.claim(worker,1).get(0);assertTrue(store.complete(job,worker,Map.of("status","EXPIRED","message","期权已到期。","state",Map.of(),"events",List.of())));assertEquals(false,store.get(option,id).get("enabled"));assertEquals("EXPIRED",store.get(option,id).get("status"));assertTrue(store.claim(worker,1).isEmpty());}
 @Test void event_failure_rolls_back_the_watermark_and_entire_batch(){UUID id=create(scope,true),worker=UUID.randomUUID();var job=store.claim(worker,1).get(0);var bad=new HashMap<>(result("one"));bad.put("events",List.of(Map.of("key","bad","rule","BIG_BUY","observedAt",Instant.now().toString(),"evidence",Map.of(),"algorithmVersion","test")));assertThrows(RuntimeException.class,()->store.complete(job,worker,bad));assertEquals(0,store.events(scope,"",null,false,1,20).total());assertEquals("{}",db.queryForObject("select state::text from market.live_monitor where id=?",String.class,id));assertTrue(store.complete(job,worker,result("recovered")));assertEquals(1,store.events(scope,"",null,false,1,20).total());}
 @Test void revoked_execution_rights_prevent_engine_calls() throws Exception {UUID id=create(scope,true);var clients=mock(MonitorClients.class);when(clients.authorized(any(),any(),any())).thenReturn(false);var scheduler=new MonitorScheduler(store,clients,true);try{scheduler.tick();for(int i=0;i<60&&!"FORBIDDEN".equals(store.get(scope,id).get("status"));i++)Thread.sleep(50);assertEquals("FORBIDDEN",store.get(scope,id).get("status"));verify(clients,never()).evaluate(any(),any());assertEquals(0,store.events(scope,"",null,false,1,20).total());}finally{scheduler.close();}}

 @Test void opportunity_checks_keep_alerts_but_stop_minute_snapshots(){
  UUID id=create(scope,true),worker=UUID.randomUUID();
  assertTrue(store.complete(store.claim(worker,1).get(0),worker,result("one")));
  db.update("update market.live_monitor set next_check_at=now(),next_history_at=now()-interval '1 minute' where id=?",id);
  assertTrue(store.complete(store.claim(worker,1).get(0),worker,result("two")));
  assertEquals(0,store.history(scope,"",null,1,20).total());
  assertEquals(2,store.events(scope,"",null,false,1,20).total());
 }
 @Test void migration_retires_legacy_jobs_preserves_evidence_and_keeps_new_alerts(){
  var ds=new DriverManagerDataSource(System.getenv("MONITOR_TEST_DATABASE_URL"),"identity_test","isolated-test-only");
  db.execute("drop schema market cascade");
  Flyway.configure().dataSource(ds).schemas("market").defaultSchema("market").target("3").load().migrate();
  UUID legacy=UUID.randomUUID(),mixed=UUID.randomUUID(),outcome=UUID.randomUUID();
  for(UUID id:List.of(legacy,mixed,outcome)){
   String rules=id.equals(legacy)?"[\"BIG_BUY\"]":id.equals(mixed)?"[\"BIG_BUY\",\"DAILY_MA_PULLBACK\"]":"[\"OUTCOME_PATTERN\"]";
   db.update("insert into market.live_monitor(id,tenant_id,created_by,asset_type,symbol,name,seconds,parameters,lease_owner,lease_until) values(?,?,?,'FUTURE','RB2701','migration',900,jsonb_build_object('rules',?::jsonb),?,now()+interval '45 seconds')",id,tenant,actor,rules,UUID.randomUUID());
  }
  db.update("insert into market.live_monitor_history(tenant_id,monitor_id,monitor_version,asset_type,symbol,name,seconds,parameters,status,message,metrics,signals,algorithm_version) select tenant_id,id,version,asset_type,symbol,name,seconds,parameters,status,message,metrics,'[]'::jsonb,'legacy' from market.live_monitor where id=?",legacy);
  db.update("insert into market.live_monitor_event(tenant_id,monitor_id,event_key,rule,label,symbol,asset_type,observed_at,evidence,algorithm_version) values(?,?, 'old','BIG_BUY','old','RB2701','FUTURE',now(),'{}','legacy')",tenant,legacy);
  Flyway.configure().dataSource(ds).schemas("market").defaultSchema("market").load().migrate();
  var old=db.queryForMap("select * from market.live_monitor where id=?",legacy);
  assertEquals(true,old.get("archived"));assertEquals(false,old.get("enabled"));assertEquals(1L,old.get("version"));assertNull(old.get("lease_owner"));
  assertEquals("[\"DAILY_MA_PULLBACK\"]",db.queryForObject("select (parameters->'rules')::text from market.live_monitor where id=?",String.class,mixed));
  assertEquals(0L,store.get(scope,outcome).get("version"));
  assertEquals(1,store.history(scope,"",legacy,1,20).total());assertEquals(0,store.history(foreign,"",legacy,1,20).total());
  assertEquals(1,store.events(scope,"",legacy,false,1,20).total());
  status(HttpStatus.NOT_FOUND,()->store.enable(scope,legacy,true,1));
  db.update("update market.live_monitor set lease_until=null");
  assertEquals(2,store.claim(UUID.randomUUID(),4).size());
  assertThrows(RuntimeException.class,()->db.update("update market.live_monitor set archived=false,enabled=true where id=?",legacy));
 }
 @Test void paused_inflight_results_never_create_history(){
  UUID id=create(scope,true),worker=UUID.randomUUID();var job=store.claim(worker,1).get(0);
  store.enable(scope,id,false,0);assertFalse(store.complete(job,worker,result("late")));
  assertEquals(0,store.history(scope,"",id,1,20).total());
 }
}
