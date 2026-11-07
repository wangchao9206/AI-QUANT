package com.aiquant.paper.service;

import com.aiquant.paper.service.DecisionJournalService.*;
import com.aiquant.paper.client.SimulationDataClient.*;
import com.aiquant.tenancy.TenantTransactions;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.sun.net.httpserver.HttpServer;
import java.math.BigDecimal;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.*;
import java.util.function.Supplier;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/** Isolated, volume-free test DB only. Exercises actual PostgreSQL owner RLS and real paper ledger. */
@EnabledIfEnvironmentVariable(named="PAPER_TEST_JDBC_URL",matches="jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/paper_test.*")
class DecisionJournalIntegrationTests {
    PaperLedgerIntegrationTests f;DecisionJournalService service;TransactionTemplate tx;HttpServer market;
    UUID tenant=UUID.randomUUID(),owner=UUID.randomUUID();ObjectMapper json=new ObjectMapper().registerModule(new JavaTimeModule());
    @BeforeEach void setup() throws Exception{
        f=new PaperLedgerIntegrationTests();f.setup();
        Flyway.configure().dataSource(f.jdbc.getDataSource()).schemas("paper_trading").defaultSchema("paper_trading").baselineOnMigrate(true).baselineVersion("6").load().migrate();
        tx=new TransactionTemplate(new DataSourceTransactionManager(f.jdbc.getDataSource()));
        market=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        market.createContext("/api/v1/market/monitors/events/42",exchange->{
            byte[] body=("{\"id\":42,\"assetType\":\"FUTURE\",\"symbol\":\"JM2701\",\"observedAt\":\"2026-11-06T07:00:00Z\",\"createdAt\":\"2026-11-06T07:15:00Z\",\"algorithmVersion\":\"test-v1\",\"evidence\":{\"value\":\"{\\\"triggerSeconds\\\":900,\\\"modelVersion\\\":\\\"frozen-v1\\\"}\"}}").getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type","application/json");exchange.sendResponseHeaders(200,body.length);exchange.getResponseBody().write(body);exchange.close();
        });market.start();
        service=new DecisionJournalService(f.jdbc,f.data,f.service,json,"http://127.0.0.1:"+market.getAddress().getPort());
        when(f.data.live(anyString())).thenAnswer(inv->f.live("LIVE"));
    }
    @AfterEach void stop(){if(market!=null)market.stop(0);}
    <T>T run(UUID t,UUID u,Supplier<T> work){return TenantTransactions.run(f.jdbc,tx,t,()->{f.jdbc.queryForObject("select set_config('app.user_id',?,true)",String.class,u.toString());return work.get();});}
    <T>T run(Supplier<T> work){return run(tenant,owner,work);}
    @SuppressWarnings("unchecked") Map<String,Object> detail(UUID id){return (Map<String,Object>)run(()->service.detail(owner,id));}
    @SuppressWarnings("unchecked") UUID create(){return (UUID)((Map<String,Object>)run(()->service.fromEvent(owner,42,"isolated-signed-fixture"))).get("id");}
    Fields fields(int lots,int budget){return new Fields("LONG",new BigDecimal("200"),new BigDecimal("198"),new BigDecimal("210"),lots,new BigDecimal("100000"),BigDecimal.valueOf(budget),"isolated hypothesis","isolated invalidation",Instant.parse("2030-01-01T00:00:00Z"));}
    UUID save(UUID id,int expected,Fields fields,UUID command){run(()->service.save(owner,id,new SavePlan(command,expected,fields)));return (UUID)((Map<?,?>)((List<?>)detail(id).get("plans")).get(0)).get("id");}
    @Test void immutable_versions_and_idempotent_commands_preserve_reviews(){
        UUID id=create();assertEquals(id,create());UUID command=UUID.randomUUID(),p=save(id,0,fields(1,1000),command);
        assertEquals(p,save(id,0,fields(1,1000),command));
        UUID review=UUID.randomUUID();run(()->service.review(owner,id,p,new Review(review,"WAITING","No fill was fabricated.")));
        run(()->service.review(owner,id,p,new Review(review,"WAITING","No fill was fabricated.")));
        assertThrows(ResponseStatusException.class,()->save(id,0,fields(2,1000),command));
        assertThrows(ResponseStatusException.class,()->save(id,0,fields(2,1000),UUID.randomUUID()));
        save(id,1,fields(2,1000),UUID.randomUUID());var d=detail(id);
        assertEquals(2,((List<?>)d.get("plans")).size());assertEquals(1,((List<?>)d.get("reviews")).size());
        assertEquals(900,((com.fasterxml.jackson.databind.JsonNode)d.get("origin")).path("evidence").path("triggerSeconds").asInt());
        assertEquals(false,((Map<?,?>)run(()->service.check(owner,id,p))).get("ready"));
    }
    @Test void both_database_and_api_enforce_private_owner_and_tenant(){
        UUID id=create(),p=save(id,0,fields(1,1000),UUID.randomUUID()),other=UUID.randomUUID();
        assertThrows(ResponseStatusException.class,()->run(tenant,other,()->service.detail(other,id)));
        assertThrows(ResponseStatusException.class,()->run(UUID.randomUUID(),owner,()->service.detail(owner,id)));
        assertEquals(0,run(tenant,other,()->f.jdbc.queryForObject("select count(*) from paper_trading.decision_plan where id=?",Integer.class,p)));
        assertThrows(RuntimeException.class,()->run(tenant,other,()->f.jdbc.update("insert into paper_trading.decision_review(id,owner_id,plan_id,command_id,outcome,notes) values(?,?,?,?,?,?)",UUID.randomUUID(),other,p,UUID.randomUUID(),"WAITING","forged link")));
    }
    @Test void stale_contract_and_budget_guards_are_server_side_and_rechecked(){
        UUID id=create(),p=save(id,0,fields(1,1000),UUID.randomUUID());
        assertEquals(true,((Map<?,?>)run(()->service.check(owner,id,p))).get("ready"));
        when(f.data.live(anyString())).thenReturn(f.live("CLOSED"));
        assertThrows(ResponseStatusException.class,()->run(()->service.paper(owner,id,p,UUID.randomUUID())));
        when(f.data.live(anyString())).thenAnswer(inv->f.live("LIVE"));
        UUID low=save(id,1,fields(1,1),UUID.randomUUID());assertEquals(false,((Map<?,?>)run(()->service.check(owner,id,low))).get("ready"));
        assertThrows(ResponseStatusException.class,()->run(()->service.paper(owner,id,low,UUID.randomUUID())));
        assertEquals(0,f.jdbc.queryForObject("select count(*) from paper_trading.paper_session",Integer.class));
        var changed=f.live("LIVE");when(f.data.live(anyString())).thenReturn(new LiveContext(changed.symbol(),"JM2705",changed.marketState(),changed.checkedAt(),changed.source(),changed.quote(),changed.spec(),changed.signalBars(),changed.executionBars()));
        assertEquals(false,((Map<?,?>)run(()->service.check(owner,id,p))).get("ready"));
    }
    @Test void paper_handoff_is_idempotent_and_creates_no_orders_or_fills(){
        UUID id=create(),p=save(id,0,fields(1,1000),UUID.randomUUID()),command=UUID.randomUUID();
        var first=(Map<?,?>)run(()->service.paper(owner,id,p,command));var retry=(Map<?,?>)run(()->service.paper(owner,id,p,command));
        assertEquals(first.get("sessionId"),retry.get("sessionId"));assertEquals(false,retry.get("created"));
        assertEquals(1,f.jdbc.queryForObject("select count(*) from paper_trading.paper_session",Integer.class));
        assertEquals(0,f.jdbc.queryForObject("select count(*) from paper_trading.paper_order",Integer.class));assertEquals(0,f.jdbc.queryForObject("select count(*) from paper_trading.paper_fill",Integer.class));
        assertEquals("JM2701",f.jdbc.queryForObject("select symbol from paper_trading.paper_session",String.class));
        UUID sessionId=UUID.fromString(first.get("sessionId").toString());
        assertEquals(id,((Map<?,?>)run(()->service.forSession(owner,sessionId))).get("caseId"));
        assertEquals(Map.of(),run(tenant,UUID.randomUUID(),()->service.forSession(owner,sessionId)));
        assertThrows(RuntimeException.class,()->run(()->{f.service.deleteSession(sessionId);return null;}));
        assertEquals(1,f.jdbc.queryForObject("select count(*) from paper_trading.paper_session",Integer.class));
    }
    @Test void concurrent_editors_cannot_overwrite_a_saved_version() throws Exception{
        UUID id=create();var pool=java.util.concurrent.Executors.newFixedThreadPool(2);var start=new java.util.concurrent.CountDownLatch(1);
        try{
            java.util.concurrent.Callable<String> command=()->{start.await();try{run(()->service.save(owner,id,new SavePlan(UUID.randomUUID(),0,fields(1,1000))));return "SAVED";}catch(ResponseStatusException e){assertEquals(409,e.getStatusCode().value());return "CONFLICT";}};
            var a=pool.submit(command);var b=pool.submit(command);start.countDown();var results=List.of(a.get(),b.get());
            assertEquals(1,Collections.frequency(results,"SAVED"));assertEquals(1,Collections.frequency(results,"CONFLICT"));assertEquals(1,((List<?>)detail(id).get("plans")).size());
        }finally{pool.shutdownNow();}
    }
    @Test void decimal_snapshots_do_not_lose_precision_or_break_idempotency(){
        UUID id=create(),command=UUID.randomUUID();Fields f=fields(1,1000);
        var precise=new Fields(f.side(),new BigDecimal("200.123456789012345678"),f.stop(),f.target(),f.lots(),f.equity(),f.budget(),f.hypothesis(),f.invalidation(),f.validUntil());
        UUID p=save(id,0,precise,command);assertEquals(p,save(id,0,precise,command));
        var saved=(com.fasterxml.jackson.databind.JsonNode)((Map<?,?>)((List<?>)detail(id).get("plans")).get(0)).get("fields");
        assertEquals(0,new BigDecimal("200.123456789012345678").compareTo(saved.path("entry").decimalValue()));
    }
    @Test void expired_plans_remain_readable_but_cannot_create_new_paper_accounts(){
        UUID id=create();Fields f=fields(1,1000);var expired=new Fields(f.side(),f.entry(),f.stop(),f.target(),f.lots(),f.equity(),f.budget(),f.hypothesis(),f.invalidation(),Instant.now().minusSeconds(60));
        UUID p=save(id,0,expired,UUID.randomUUID());var result=(Map<?,?>)run(()->service.check(owner,id,p));assertEquals(false,result.get("ready"));assertTrue(result.get("reasons").toString().contains("有效期"));
        assertThrows(ResponseStatusException.class,()->run(()->service.paper(owner,id,p,UUID.randomUUID())));assertEquals(1,((List<?>)detail(id).get("plans")).size());
    }
}
