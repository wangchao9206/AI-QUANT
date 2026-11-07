package com.aiquant.paper.service;

import com.aiquant.paper.api.PaperRequests.*;
import com.aiquant.paper.client.SimulationDataClient.*;
import com.aiquant.paper.service.DecisionJournalService.Fields;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Supplier;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/** Real PostgreSQL locks/RLS and real ledger; all prices/identities are synthetic, never production writes. */
@EnabledIfEnvironmentVariable(named="PAPER_TEST_JDBC_URL",matches="jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/paper_test.*")
class PlanOrderGuardIntegrationTests {
    DecisionJournalIntegrationTests f;UUID caseId,planId,sessionId;
    AtomicReference<LiveContext> quote=new AtomicReference<>();
    @BeforeEach void setup()throws Exception{
        f=new DecisionJournalIntegrationTests();f.setup();quote.set(f.f.live("LIVE"));
        when(f.f.data.live(anyString())).thenAnswer(i->quote.get());
        when(f.f.data.quote(anyString())).thenAnswer(i->quote.get().quote());
    }
    @AfterEach void stop(){f.stop();}
    <T>T run(Supplier<T> work){return run(f.owner,true,work);}
    <T>T run(UUID owner,boolean market,Supplier<T> work){return f.run(f.tenant,owner,()->{f.f.jdbc.queryForObject("select set_config('app.market_read',?,true)",String.class,Boolean.toString(market));return work.get();});}
    Fields fields(String side,int lots,int budget,Instant expiry){
        return new Fields(side,new BigDecimal("200"),new BigDecimal("LONG".equals(side)?"198":"202"),new BigDecimal("LONG".equals(side)?"210":"190"),lots,new BigDecimal("100000"),BigDecimal.valueOf(budget),"synthetic hypothesis","synthetic invalidation",expiry);
    }
    void account(String side,int lots,int budget){account(fields(side,lots,budget,Instant.now().plusSeconds(3600)));}
    void account(Fields fields){caseId=f.create();planId=f.save(caseId,0,fields,UUID.randomUUID());sessionId=UUID.fromString(((Map<?,?>)run(()->f.service.paper(f.owner,caseId,planId,UUID.randomUUID()))).get("sessionId").toString());}
    PlaceOrderRequest order(String side,String offset,String type,int quantity,String price){return new PlaceOrderRequest(UUID.randomUUID().toString(),side,offset,type,quantity,"LIMIT".equals(type)?new BigDecimal(price):null,"STOP".equals(type)?new BigDecimal(price):null);}
    Map<String,Object> place(PlaceOrderRequest request){return run(()->f.f.service.placeOrder(sessionId,request));}
    void price(String price){var old=quote.get();quote.set(new LiveContext(old.symbol(),old.contract(),"LIVE",Instant.now(),old.source(),new QuoteSnapshot(old.contract(),"synthetic",new BigDecimal(price),"SYNTHETIC","FRESH",Instant.now()),old.spec(),old.signalBars(),old.executionBars()));}
    void refresh(){run(()->f.f.service.advance(sessionId,new AdvanceRequest(1)));}
    int orders(){return f.f.jdbc.queryForObject("select count(*) from paper_trading.paper_order",Integer.class);}
    int fills(){return f.f.jdbc.queryForObject("select count(*) from paper_trading.paper_fill",Integer.class);}
    int position(){return f.f.jdbc.queryForObject("select lots from paper_trading.paper_position where session_id=?",Integer.class,sessionId);}
    String lastStatus(){return f.f.jdbc.queryForObject("select status from paper_trading.paper_order order by created_at desc,id desc limit 1",String.class);}
    ResponseStatusException rejected(PlaceOrderRequest r,String reason){var error=assertThrows(ResponseStatusException.class,()->place(r));assertTrue(error.getReason().contains(reason),error.getReason());return error;}

    @Test void frozenDirectionAndCombinedLotLimitCannotBeBypassedWithDirectOrders(){
        account("LONG",2,2000);assertEquals(true,run(()->f.f.service.detail(sessionId)).get("decisionGuarded"));
        rejected(order("SELL","OPEN","MARKET",1,null),"方向");
        place(order("BUY","OPEN","LIMIT",1,"199"));assertEquals(0,fills());
        rejected(order("BUY","OPEN","LIMIT",2,"199"),"手数");
        place(order("BUY","OPEN","MARKET",1,null));assertEquals(1,position());
        rejected(order("BUY","OPEN","MARKET",1,null),"手数");assertEquals(2,orders());
    }
    @Test void cancellationReleasesTheReservationAndIdempotentRetryCreatesNoDuplicate(){
        account("LONG",1,1000);var request=order("BUY","OPEN","LIMIT",1,"199");place(request);place(request);assertEquals(1,orders());
        UUID id=f.f.jdbc.queryForObject("select id from paper_trading.paper_order",UUID.class);
        run(()->f.f.service.cancelOrder(sessionId,id));place(order("BUY","OPEN","MARKET",1,null));assertEquals(1,fills());assertEquals(1,position());
    }
    @Test void riskIncludesAllPendingOrdersNotOnlyTheOrderBeingSubmitted(){
        account("LONG",2,500);price("201.5");place(order("BUY","OPEN","LIMIT",1,"199"));
        rejected(order("BUY","OPEN","LIMIT",1,"199"),"预算");assertEquals(1,orders());assertEquals(0,fills());
    }
    @Test void adverseActualFillIsRecheckedAndRecordsARejectionRatherThanAnInventedFill(){
        account("LONG",1,330);place(order("BUY","OPEN","STOP",1,"201"));assertEquals(0,fills());
        price("203");refresh();assertEquals("REJECTED",lastStatus());assertEquals(0,fills());assertEquals(0,position());
        assertTrue(f.f.jdbc.queryForObject("select rejection_reason from paper_trading.paper_order",String.class).contains("预算"));
    }
    @Test void cumulativeLossesAndPaidFeesCannotBeResetByClosingAndReopening(){
        account("LONG",1,480);place(order("BUY","OPEN","MARKET",1,null)); // 201, entry fee 3
        price("198");place(order("SELL","CLOSE","MARKET",1,null)); // 197, gross loss 240, fees 6
        assertEquals(0,position());price("200");
        rejected(order("BUY","OPEN","MARKET",1,null),"预算");assertEquals(2,fills());
    }
    @Test void shortPositionsUseTheCorrectAdverseStopAndDirection(){
        account("SHORT",1,300);rejected(order("BUY","OPEN","MARKET",1,null),"方向");
        place(order("SELL","OPEN","MARKET",1,null));assertEquals(-1,f.f.jdbc.queryForObject("select direction from paper_trading.paper_position",Integer.class));
        place(order("BUY","CLOSE","MARKET",1,null));assertEquals(0,position());assertEquals(2,fills());
    }
    @Test void profitableRoundTripDoesNotOffsetEarlierGrossLossesInTheRiskBudget(){
        account("LONG",1,950);place(order("BUY","OPEN","MARKET",1,null));price("198");place(order("SELL","CLOSE","MARKET",1,null));
        price("200");place(order("BUY","OPEN","MARKET",1,null));price("210");place(order("SELL","CLOSE","MARKET",1,null));
        assertTrue(f.f.jdbc.queryForObject("select realized_pnl from paper_trading.paper_session",BigDecimal.class).signum()>0);
        price("208");rejected(order("BUY","OPEN","MARKET",1,null),"预算");assertEquals(4,fills());
    }
    @Test void pendingMarginAndFeesAreReservedTogetherAcrossOrders(){
        account("LONG",100,100000);place(order("BUY","OPEN","LIMIT",50,"199"));
        rejected(order("BUY","OPEN","LIMIT",10,"199"),"可用资金");assertEquals(1,orders());assertEquals(0,fills());
    }
    @Test void privatePlanIsNotExposedAndAnotherMemberRefreshDoesNotRejectOrFillOwnersOrder(){
        account("LONG",1,1000);place(order("BUY","OPEN","LIMIT",1,"199"));price("199");UUID other=UUID.randomUUID();
        var guard=(Map<?,?>)run(other,true,()->f.f.service.detail(sessionId)).get("planGuard");
        assertEquals(false,guard.get("ownerVisible"));assertFalse(guard.containsKey("budget"));assertFalse(guard.containsKey("planId"));
        run(other,true,()->f.f.service.advance(sessionId,new AdvanceRequest(1)));assertEquals("PENDING",lastStatus());assertEquals(0,fills());
        assertEquals(403,assertThrows(ResponseStatusException.class,()->run(other,true,()->f.f.service.placeOrder(sessionId,order("BUY","OPEN","MARKET",1,null)))).getStatusCode().value());
        refresh();assertEquals(1,fills());assertEquals(1,position());
        run(other,false,()->f.f.service.placeOrder(sessionId,order("SELL","CLOSE","MARKET",1,null)));assertEquals(0,position());
    }
    @Test void removingMarketPermissionStopsNewOpensAndMatchingButPreservesClosing(){
        account("LONG",2,2000);place(order("BUY","OPEN","MARKET",1,null));place(order("BUY","OPEN","LIMIT",1,"199"));price("199");
        var hidden=(Map<?,?>)run(f.owner,false,()->f.f.service.detail(sessionId)).get("planGuard");assertEquals(false,hidden.get("ownerVisible"));assertFalse(hidden.containsKey("budget"));
        assertEquals(403,assertThrows(ResponseStatusException.class,()->run(f.owner,false,()->f.f.service.placeOrder(sessionId,order("BUY","OPEN","MARKET",1,null)))).getStatusCode().value());
        run(f.owner,false,()->f.f.service.advance(sessionId,new AdvanceRequest(1)));assertEquals(1,position());
        run(f.owner,false,()->f.f.service.placeOrder(sessionId,order("SELL","CLOSE","MARKET",1,null)));assertEquals(0,position());
        assertEquals(1,f.f.jdbc.queryForObject("select count(*) from paper_trading.paper_order where status='PENDING'",Integer.class));
    }
    @Test void newPlanVersionStopsOldAccountOpensAndPendingOrdersButAllowsClosing(){
        account("LONG",2,2000);place(order("BUY","OPEN","MARKET",1,null));place(order("BUY","OPEN","LIMIT",1,"199"));
        f.save(caseId,1,fields("LONG",2,2000,Instant.now().plusSeconds(3600)),UUID.randomUUID());
        rejected(order("BUY","OPEN","MARKET",1,null),"新计划版本");price("199");refresh();assertEquals(1,position());
        assertEquals(1,f.f.jdbc.queryForObject("select count(*) from paper_trading.paper_order where status='REJECTED'",Integer.class));
        place(order("SELL","CLOSE","MARKET",1,null));assertEquals(0,position());
    }
    @Test void staleClosedFutureAndMismatchedContractContextsCannotOpen(){
        account("LONG",1,1000);var good=quote.get();
        for(LiveContext bad:List.of(
            new LiveContext(good.symbol(),good.contract(),"CLOSED",Instant.now(),good.source(),good.quote(),good.spec(),good.signalBars(),good.executionBars()),
            new LiveContext(good.symbol(),good.contract(),"LIVE",Instant.now().minusSeconds(31),good.source(),good.quote(),good.spec(),good.signalBars(),good.executionBars()),
            new LiveContext(good.symbol(),good.contract(),"LIVE",Instant.now().plusSeconds(4),good.source(),good.quote(),good.spec(),good.signalBars(),good.executionBars()),
            new LiveContext(good.symbol(),"JM2705","LIVE",Instant.now(),good.source(),good.quote(),good.spec(),good.signalBars(),good.executionBars()))){
            quote.set(bad);assertThrows(ResponseStatusException.class,()->place(order("BUY","OPEN","MARKET",1,null)));
        }
        assertEquals(0,orders());
    }
    @Test void touchingStopTargetAndOffTickOrdersAreRejected(){
        account("LONG",1,1000);for(String value:List.of("198","210","197.5","211")){price(value);rejected(order("BUY","OPEN","MARKET",1,null),"保护价/目标价");}
        price("200");rejected(order("BUY","OPEN","LIMIT",1,"199.1"),"最小跳动");rejected(order("BUY","OPEN","STOP",1,"210"),"保护价");assertEquals(0,orders());
    }
    @Test void actualFillCrossingTargetIsRejectedEvenWhenObservedQuoteIsStillInside(){
        account("LONG",1,2000);price("209.5");place(order("BUY","OPEN","MARKET",1,null));assertEquals("REJECTED",lastStatus());assertEquals(0,fills());
    }
    @Test void partialFillsRetainRemainingReservations(){
        account("LONG",2,2000);
        var engine=new MatchingEngine(){@Override public FillDecision match(OrderView o,BarView b,BigDecimal t,BigDecimal slip,BigDecimal rate){var d=super.match(o,b,t,slip,rate);return d.fillable()?new FillDecision(true,d.marketPrice(),d.fillPrice(),1):d;}};
        f.f.service=new PaperTradingService(f.f.jdbc,new TransactionTemplate(new DataSourceTransactionManager(f.f.jdbc.getDataSource())),f.f.data,engine);
        place(order("BUY","OPEN","MARKET",2,null));assertEquals(1,position());assertEquals("PARTIAL",lastStatus());
        rejected(order("BUY","OPEN","LIMIT",1,"199"),"手数");refresh();assertEquals(2,position());assertEquals("FILLED",lastStatus());
    }
    @Test void concurrentOrdersCannotBothSpendTheSameLotReservation()throws Exception{
        account("LONG",1,1000);var pool=Executors.newFixedThreadPool(2);var start=new CountDownLatch(1);
        try{Callable<Integer> work=()->{start.await();try{place(order("BUY","OPEN","LIMIT",1,"199"));return 200;}catch(ResponseStatusException e){return e.getStatusCode().value();}};
            var a=pool.submit(work);var b=pool.submit(work);start.countDown();var results=List.of(a.get(10,TimeUnit.SECONDS),b.get(10,TimeUnit.SECONDS));
            assertEquals(1,Collections.frequency(results,200));assertEquals(1,Collections.frequency(results,409));assertEquals(1,orders());
        }finally{pool.shutdownNow();}
    }
    @Test void revisionCommittedWhileOrderWaitsForCaseLockIsObserved()throws Exception{
        account("LONG",1,1000);var pool=Executors.newSingleThreadExecutor();var requested=new CountDownLatch(1);AtomicReference<Future<?>> pending=new AtomicReference<>();
        when(f.f.data.live(anyString())).thenAnswer(i->{requested.countDown();return quote.get();});
        try{run(()->{f.f.jdbc.queryForObject("select id from paper_trading.decision_case where id=? for update",UUID.class,caseId);
            pending.set(pool.submit(()->assertThrows(ResponseStatusException.class,()->place(order("BUY","OPEN","MARKET",1,null)))));
            try{assertTrue(requested.await(5,TimeUnit.SECONDS));}catch(InterruptedException e){throw new RuntimeException(e);}
            f.service.save(f.owner,caseId,new DecisionJournalService.SavePlan(UUID.randomUUID(),1,fields("LONG",1,1000,Instant.now().plusSeconds(3600))));return null;
        });pending.get().get(10,TimeUnit.SECONDS);assertEquals(0,orders());}finally{pool.shutdownNow();}
    }
    @Test void deadlineIsRecheckedAfterWaitingForSessionLock()throws Exception{
        account(fields("LONG",1,1000,Instant.now().plusSeconds(2)));var pool=Executors.newSingleThreadExecutor();var requested=new CountDownLatch(1);AtomicReference<Future<?>> pending=new AtomicReference<>();
        when(f.f.data.live(anyString())).thenAnswer(i->{requested.countDown();return quote.get();});
        try{run(()->{f.f.jdbc.queryForObject("select id from paper_trading.paper_session where id=? for update",UUID.class,sessionId);
            pending.set(pool.submit(()->rejected(order("BUY","OPEN","MARKET",1,null),"有效期")));
            try{assertTrue(requested.await(5,TimeUnit.SECONDS));}catch(InterruptedException e){throw new RuntimeException(e);}
            f.f.jdbc.execute("select pg_sleep(2.1)");return null;
        });pending.get().get(10,TimeUnit.SECONDS);assertEquals(0,orders());}finally{pool.shutdownNow();}
    }
    @Test void guardedAccountNeverSilentlyRollsToAnotherContract(){
        account("LONG",1,1000);var old=quote.get();quote.set(new LiveContext(old.symbol(),"JM2705","LIVE",Instant.now(),old.source(),old.quote(),old.spec(),old.signalBars(),old.executionBars()));
        refresh();assertEquals("JM2701",f.f.jdbc.queryForObject("select current_contract from paper_trading.paper_session",String.class));assertEquals("CONTRACT_CHANGED",f.f.jdbc.queryForObject("select market_state from paper_trading.paper_session",String.class));
    }
    @Test void guardMarkerBackfillProtectsExistingLinksAndPreservesLedgerRows()throws Exception{
        account("LONG",1,1000);f.f.jdbc.update("update paper_trading.paper_session set decision_guarded=false where id=?",sessionId);
        String migration=new String(getClass().getResourceAsStream("/db/migration/V14__plan_order_guards.sql").readAllBytes(),java.nio.charset.StandardCharsets.UTF_8);
        f.f.jdbc.execute(migration.substring(migration.indexOf("update paper_trading")));
        assertEquals(true,f.f.jdbc.queryForObject("select decision_guarded from paper_trading.paper_session where id=?",Boolean.class,sessionId));assertEquals(0,orders());assertEquals(0,fills());
    }
}
