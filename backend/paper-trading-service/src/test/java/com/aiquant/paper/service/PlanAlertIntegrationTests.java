package com.aiquant.paper.service;
import com.aiquant.paper.client.SimulationDataClient.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;

@EnabledIfEnvironmentVariable(named="PAPER_TEST_JDBC_URL",matches="jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/paper_test.*")
class PlanAlertIntegrationTests {
 DecisionJournalIntegrationTests f;PlanAlertStore store;UUID id,p,worker=UUID.randomUUID();
 @BeforeEach void setup()throws Exception{f=new DecisionJournalIntegrationTests();f.setup();store=new PlanAlertStore(f.f.jdbc,f.tx,f.json);id=f.create();p=f.save(id,0,f.fields(1,1000),UUID.randomUUID());}
 @AfterEach void stop(){if(f!=null)f.stop();}
 void edit(boolean on,long revision){f.run(()->store.edit(f.owner,id,p,on,"BREAKOUT",revision));}
 Map<String,Object> claim(){f.f.jdbc.update("update paper_trading.decision_alert_subscription set next_check_at=now() where plan_id=?",p);return store.claim(worker,4).get(0);}
 LiveContext live(String price,Instant at){var l=f.f.live("LIVE");return new LiveContext(l.symbol(),l.contract(),"LIVE",at,"isolated-fixture",new QuoteSnapshot(l.contract(),"fixture",new BigDecimal(price),"fixture","FRESH",at),l.spec(),List.of(),List.of());}
 Map<String,Object> read(){return (Map<String,Object>)f.run(()->store.read(f.owner,id,p));}
 long events(){return ((Number)f.run(()->store.events(f.owner,null,false,1)).get("total")).longValue();}
 @Test void sampled_crosses_persist_once_per_plan_kind_without_any_order_or_fill(){
  edit(true,0);Instant at=Instant.now();store.complete(claim(),worker,"ALLOWED",live("199",at),at);assertEquals(0,events());
  store.complete(claim(),worker,"ALLOWED",live("201",at.plusSeconds(60)),at.plusSeconds(60));assertEquals(1,events());
  edit(false,1);edit(true,2);store.complete(claim(),worker,"ALLOWED",live("199",at.plusSeconds(120)),at.plusSeconds(120));store.complete(claim(),worker,"ALLOWED",live("201",at.plusSeconds(180)),at.plusSeconds(180));assertEquals(1,events());
  assertEquals(0,f.f.jdbc.queryForObject("select count(*) from paper_trading.paper_order",Integer.class));assertEquals(0,f.f.jdbc.queryForObject("select count(*) from paper_trading.paper_fill",Integer.class));
  var row=((List<Map<String,Object>>)f.run(()->store.events(f.owner,null,false,1)).get("items")).get(0);f.run(()->{store.acknowledge(f.owner,(UUID)row.get("id"));return null;});assertEquals(0,((Number)f.run(()->store.events(f.owner,null,true,1)).get("total")).intValue());
 }
 @Test void pause_and_new_plan_invalidate_pending_workers_and_keep_old_evidence(){edit(true,0);var job=claim();edit(false,1);store.complete(job,worker,"ALLOWED",live("201",Instant.now()),Instant.now());assertEquals(0,events());edit(true,2);job=claim();f.save(id,1,f.fields(1,1000),UUID.randomUUID());store.complete(job,worker,"ALLOWED",live("201",Instant.now()),Instant.now());var sub=(Map<?,?>)read().get("subscription");assertEquals(false,sub.get("enabled"));assertEquals("SUPERSEDED",sub.get("status"));assertThrows(ResponseStatusException.class,()->edit(true,4));}
 @Test void expiry_is_a_server_deadline_event_even_when_market_data_is_unavailable(){p=f.save(id,1,f.until(Instant.now().plusSeconds(20)),UUID.randomUUID());edit(true,0);store.complete(claim(),worker,"ALLOWED",null,Instant.now().plusSeconds(30));assertEquals(1,events());assertEquals("EXPIRED",((Map<?,?>)read().get("subscription")).get("status"));assertTrue(store.claim(worker,4).isEmpty());}
 @Test void inaccessible_identity_stops_alerts_and_unknown_authority_never_generates_events(){edit(true,0);store.complete(claim(),worker,"UNKNOWN",null,Instant.now());assertEquals("ERROR",((Map<?,?>)read().get("subscription")).get("status"));store.complete(claim(),worker,"DENIED",null,Instant.now());assertEquals("FORBIDDEN",((Map<?,?>)read().get("subscription")).get("status"));assertEquals(false,((Map<?,?>)read().get("subscription")).get("enabled"));assertEquals(0,events());}
 @Test void owner_and_tenant_rls_and_revision_guards_hold(){edit(true,0);assertThrows(ResponseStatusException.class,()->edit(false,0));assertThrows(ResponseStatusException.class,()->f.run(()->store.edit(f.owner,id,p,true,"PULLBACK",1)));assertEquals(0,f.run(f.tenant,UUID.randomUUID(),()->f.f.jdbc.queryForObject("select count(*) from paper_trading.decision_alert_subscription",Integer.class)));assertEquals(0,f.run(UUID.randomUUID(),f.owner,()->f.f.jdbc.queryForObject("select count(*) from paper_trading.decision_alert_subscription",Integer.class)));assertThrows(ResponseStatusException.class,()->f.run(f.tenant,UUID.randomUUID(),()->store.read(f.owner,id,p)));}
 @Test void leases_are_exclusive_and_stale_workers_cannot_complete_after_reclaim(){edit(true,0);var old=claim();assertTrue(store.claim(UUID.randomUUID(),4).isEmpty());f.f.jdbc.update("update paper_trading.decision_alert_subscription set lease_until=now()-interval '1 second' where plan_id=?",p);UUID next=UUID.randomUUID();var job=store.claim(next,4).get(0);store.complete(old,worker,"DENIED",null,Instant.now());assertEquals(true,((Map<?,?>)read().get("subscription")).get("enabled"));store.complete(job,next,"ALLOWED",live("199",Instant.now()),Instant.now());assertEquals("READY",((Map<?,?>)read().get("subscription")).get("status"));}
 @Test void stale_data_breaks_continuity_and_completed_jobs_wait_a_minute(){edit(true,0);Instant at=Instant.now();store.complete(claim(),worker,"ALLOWED",live("199",at),at);assertTrue(store.claim(UUID.randomUUID(),4).isEmpty());assertEquals(60,f.f.jdbc.queryForObject("select extract(epoch from next_check_at-checked_at)::int from paper_trading.decision_alert_subscription where plan_id=?",Integer.class,p));store.complete(claim(),worker,"ALLOWED",null,at.plusSeconds(60));assertEquals("STALE",((Map<?,?>)read().get("subscription")).get("status"));store.complete(claim(),worker,"ALLOWED",live("201",at.plusSeconds(120)),at.plusSeconds(120));assertEquals(0,events());}
 @Test void a_lease_that_expires_while_waiting_for_the_case_lock_cannot_write()throws Exception{
  edit(true,0);var job=claim();var pool=java.util.concurrent.Executors.newFixedThreadPool(2);var locked=new java.util.concurrent.CountDownLatch(1);var release=new java.util.concurrent.CountDownLatch(1);
  try{var holder=pool.submit(()->f.run(()->{f.f.jdbc.queryForList("select id from paper_trading.decision_case where id=? for update",id);locked.countDown();try{release.await(5,java.util.concurrent.TimeUnit.SECONDS);}catch(InterruptedException e){Thread.currentThread().interrupt();}return null;}));assertTrue(locked.await(3,java.util.concurrent.TimeUnit.SECONDS));f.f.jdbc.update("update paper_trading.decision_alert_subscription set lease_until=clock_timestamp()+interval '1 second' where plan_id=?",p);
   var completion=pool.submit(()->store.complete(job,worker,"DENIED",null,Instant.now()));f.f.jdbc.execute("select pg_sleep(1.2)");release.countDown();holder.get();completion.get();assertEquals(true,((Map<?,?>)read().get("subscription")).get("enabled"));assertEquals("STARTING",((Map<?,?>)read().get("subscription")).get("status"));
  }finally{release.countDown();pool.shutdownNow();}
 }
}
