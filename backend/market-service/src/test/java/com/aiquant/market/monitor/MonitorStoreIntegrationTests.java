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
 Map<String,Object> validation(String kind){return Map.of("spec",Map.of("assetType",kind,"symbol",kind.equals("OPTION")?"DCE.m2701-C-3000":"RB2701","seconds",60,"parameters",Map.of("bigLots",100)),"metadata",Map.of("symbol","RB2701"));}
 UUID create(MonitorStore.Scope selected,boolean enabled){return (UUID)store.save(selected,null,"integration",enabled,0,validation(selected.kind())).get("id");}
 void status(HttpStatus expected,Runnable work){assertEquals(expected,assertThrows(ResponseStatusException.class,work::run).getStatusCode());}
 Map<String,Object> result(String key){return Map.of("status","READY","message","ok","state",Map.of("seen",key),"events",List.of(Map.of("key",key,"rule","BIG_BUY","label","大额买向成交增量","observedAt",Instant.now().toString(),"evidence",Map.of("lots",120),"algorithmVersion","depth-monitor-v1")));}
 @Test void rows_events_and_audit_are_tenant_and_asset_scoped(){UUID id=create(scope,true);assertEquals(1,store.list(scope,"",1,20).total());assertEquals(0,store.list(foreign,"",1,20).total());assertEquals(0,store.list(option,"",1,20).total());status(HttpStatus.NOT_FOUND,()->store.get(foreign,id));status(HttpStatus.NOT_FOUND,()->store.enable(option,id,false,0));UUID worker=UUID.randomUUID();assertTrue(store.complete(store.claim(worker,1).get(0),worker,result("one")));assertEquals(1,store.events(scope,"",null,false,1,20).total());assertEquals(0,store.events(foreign,"",null,false,1,20).total());assertEquals(0,store.events(option,"",null,false,1,20).total());TenantTransactions.run(db,tx,other,()->{assertEquals(0,db.queryForObject("select count(*) from market.live_monitor",Integer.class));assertEquals(0,db.update("update market.live_monitor set name='forged' where id=?",id));return null;});assertEquals(1,db.queryForObject("select count(*) from market.live_monitor_audit",Integer.class));}
 @Test void pause_and_versions_discard_in_flight_trigger_results(){UUID id=create(scope,true),worker=UUID.randomUUID();var job=store.claim(worker,1).get(0);store.enable(scope,id,false,0);assertFalse(store.complete(job,worker,result("late")));assertEquals(0,store.events(scope,"",null,false,1,20).total());status(HttpStatus.CONFLICT,()->store.enable(scope,id,true,0));assertEquals("PAUSED",store.get(scope,id).get("status"));store.enable(scope,id,true,1);assertEquals("STARTING",store.get(scope,id).get("status"));assertEquals(2L,store.get(scope,id).get("version"));}
 @Test void leases_state_and_dedup_survive_a_new_store(){UUID id=create(scope,true),worker=UUID.randomUUID();var job=store.claim(worker,1).get(0);assertTrue(store.claim(UUID.randomUUID(),1).isEmpty());assertTrue(store.complete(job,worker,result("persisted")));var restored=new MonitorStore(db,tx,new ObjectMapper());db.update("update market.live_monitor set next_check_at=now() where id=?",id);var resumed=restored.claim(worker,1).get(0);assertEquals("persisted",restored.object(resumed.get("state")).get("seen"));assertTrue(restored.complete(resumed,worker,result("persisted")));assertEquals(1,restored.events(scope,"",null,false,1,20).total());}
 @Test void global_and_tenant_capacity_limits_are_enforced(){UUID first=create(scope,true);for(int i=1;i<20;i++)create(scope,true);status(HttpStatus.CONFLICT,()->create(scope,true));for(int i=0;i<12;i++)create(foreign,true);status(HttpStatus.CONFLICT,()->create(new MonitorStore.Scope(UUID.randomUUID(),actor,"OPTION"),true));UUID paused=create(scope,false);status(HttpStatus.CONFLICT,()->store.enable(scope,paused,true,0));store.archive(scope,first,0);status(HttpStatus.NOT_FOUND,()->store.get(scope,first));assertEquals(20,store.list(scope,"",1,50).total());}
 @Test void forged_tenant_headers_are_rejected(){var controller=new MonitorController(store,mock(MonitorClients.class),mapper,"integration-secret-longer-than-32-characters");var req=new MockHttpServletRequest();req.setRequestURI("/api/v1/options/monitors");req.addHeader("X-Tenant-Id",tenant.toString());status(HttpStatus.UNAUTHORIZED,()->controller.scope(req));req.addHeader("X-Aiquant-Identity","forged.payload");status(HttpStatus.UNAUTHORIZED,()->controller.scope(req));}
 @Test void expired_options_stop_automatically_without_emitting_a_signal(){UUID id=create(option,true),worker=UUID.randomUUID();var job=store.claim(worker,1).get(0);assertTrue(store.complete(job,worker,Map.of("status","EXPIRED","message","期权已到期。","state",Map.of(),"events",List.of())));assertEquals(false,store.get(option,id).get("enabled"));assertEquals("EXPIRED",store.get(option,id).get("status"));assertTrue(store.claim(worker,1).isEmpty());}
 @Test void event_failure_rolls_back_the_watermark_and_entire_batch(){UUID id=create(scope,true),worker=UUID.randomUUID();var job=store.claim(worker,1).get(0);var bad=new HashMap<>(result("one"));bad.put("events",List.of(Map.of("key","bad","rule","BIG_BUY","observedAt",Instant.now().toString(),"evidence",Map.of(),"algorithmVersion","test")));assertThrows(RuntimeException.class,()->store.complete(job,worker,bad));assertEquals(0,store.events(scope,"",null,false,1,20).total());assertEquals("{}",db.queryForObject("select state::text from market.live_monitor where id=?",String.class,id));assertTrue(store.complete(job,worker,result("recovered")));assertEquals(1,store.events(scope,"",null,false,1,20).total());}
 @Test void revoked_execution_rights_prevent_engine_calls() throws Exception {UUID id=create(scope,true);var clients=mock(MonitorClients.class);when(clients.authorized(any(),any(),any())).thenReturn(false);var scheduler=new MonitorScheduler(store,clients,true);try{scheduler.tick();for(int i=0;i<60&&!"FORBIDDEN".equals(store.get(scope,id).get("status"));i++)Thread.sleep(50);assertEquals("FORBIDDEN",store.get(scope,id).get("status"));verify(clients,never()).evaluate(any(),any());assertEquals(0,store.events(scope,"",null,false,1,20).total());}finally{scheduler.close();}}

 @Test void minute_history_is_durable_scoped_and_throttled_without_alerts(){
  UUID id=create(scope,true),worker=UUID.randomUUID();
  var result=Map.<String,Object>of("status","READY","metrics",Map.of("lastPrice",100),"events",List.of(),"algorithmVersion","history-test");
  assertTrue(store.complete(store.claim(worker,1).get(0),worker,result));
  assertEquals(1,store.history(scope,"",null,1,20).total());
  assertEquals(0,store.history(foreign,"",null,1,20).total());
  assertEquals(0,store.history(option,"",null,1,20).total());
  db.update("update market.live_monitor set next_check_at=now() where id=?",id);
  assertTrue(store.complete(store.claim(worker,1).get(0),worker,result));
  assertEquals(1,store.history(scope,"",id,1,20).total());
  db.update("update market.live_monitor set next_check_at=now(),next_history_at=now()-interval '1 second' where id=?",id);
  assertTrue(store.complete(store.claim(worker,1).get(0),worker,Map.of("status","STALE","message","closed","events",List.of())));
  assertEquals(2,store.history(scope,"",id,1,20).total());
  assertEquals("STALE",store.history(scope,"",id,1,1).items().get(0).get("status"));
  store.archive(scope,id,0);
  assertEquals(2,new MonitorStore(db,tx,mapper).history(scope,"integration",id,1,20).total());
 }
 @Test void paused_inflight_results_never_create_history(){
  UUID id=create(scope,true),worker=UUID.randomUUID();var job=store.claim(worker,1).get(0);
  store.enable(scope,id,false,0);assertFalse(store.complete(job,worker,result("late")));
  assertEquals(0,store.history(scope,"",id,1,20).total());
 }
}
