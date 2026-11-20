package com.aiquant.paper.service;
import com.aiquant.paper.client.SimulationDataClient.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import static org.junit.jupiter.api.Assertions.*;

@EnabledIfEnvironmentVariable(named="PAPER_TEST_JDBC_URL",matches="jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/paper_test.*")
class PaperAutomationIntegrationTests {
    PaperPortfolioIntegrationTests f;PaperAutomationService store;UUID worker=UUID.randomUUID();
    Map<UUID,com.fasterxml.jackson.databind.JsonNode> receipts=new HashMap<>();
    @BeforeEach void setup()throws Exception{f=new PaperPortfolioIntegrationTests();f.setup();store=new PaperAutomationService(f.f.jdbc,f.tx,f.f.data,new MatchingEngine());}
    UUID start(UUID account,String contract){f.run(()->store.start(account,f.owner,new PaperAutomationService.Start(contract,"MA20_MACD",1,10,BigDecimal.ZERO,BigDecimal.ZERO,true,null)));
        return f.run(()->f.f.jdbc.queryForObject("select id from paper_trading.paper_automation_run where session_id=? and contract=? and enabled",UUID.class,account,contract));}
    Map<String,Object> claim(UUID run){f.f.jdbc.update("update paper_trading.paper_automation_run set next_check_at=clock_timestamp()-interval '1 second' where id=?",run);
        return store.claim(worker,4).stream().filter(j->j.get("id").equals(run)).findFirst().orElseThrow();}
    PaperAutomationService.Prepared prepared(String contract,String signal,Instant time)throws Exception {
        var context=f.observations.get(contract);
        var chart=new ObjectMapper().readTree("{\"expectedTradingDate\":\"2026-11-18\",\"tradingSessions\":{\"day\":[[\"09:00:00\",\"15:00:00\"]]}}");
        UUID run=f.run(()->f.f.jdbc.queryForObject("select id from paper_trading.paper_automation_run where contract=? and enabled",UUID.class,contract));
        var receipt=receipts.computeIfAbsent(run,id->StrategyWorkflowStore.json(Map.of("state","READY","contract",contract,
            "requestKey",store.startupKey(id),"completedAt",Instant.now().toString(),"source","TQSDK_FRESH_DOWNLOAD","dailyCount",70,
            "minuteCount",180,"latestDailyTime",Instant.now().toString(),"latestMinuteTime",Instant.now().toString(),"sourceStartupId","isolated-test")));
        return new PaperAutomationService.Prepared(context,new PortfolioQuotes(Map.copyOf(f.observations),Map.of()),chart,
            new StrategyDecision("MA20_MACD","MA20","paper-ma20-macd-v1",signal,"fixture completed minute",time,50,21,BigDecimal.ZERO),null,receipt);
    }
    @Test void oneSignalFillsOnceAndStopLeavesThePositionForManualControl()throws Exception {
        UUID account=f.create(100000),run=start(account,"JM2701");
        var job=claim(run);var observation=prepared("JM2701","BUY",Instant.now().minusSeconds(120));
        store.complete(job,worker,"ALLOWED",observation);store.complete(job,worker,"ALLOWED",observation);
        assertEquals(1L,f.detail(account).get("fillCount"));assertEquals(1,f.positions(account).size());
        assertThrows(IllegalStateException.class,()->f.order(account,"manual-while-auto","JM2701","BUY","OPEN","MARKET",null));
        var late=claim(run);f.run(()->store.stop(account,run));store.complete(late,worker,"ALLOWED",observation);
        assertEquals(1L,f.detail(account).get("fillCount"));assertEquals(1,f.positions(account).size());
        f.order(account,"manual-after-stop","JM2701","SELL","CLOSE","MARKET",null);assertEquals(0,f.positions(account).size());
        f.run(()->{f.f.service.deleteSession(account);return null;});
        assertEquals(0,f.f.jdbc.queryForObject("select count(*) from paper_trading.paper_automation_run",Integer.class));
    }
    @Test void fixedStopRunsBeforeDuplicateMinuteFilteringAndDoesNotReverse()throws Exception {
        UUID account=f.create(100000),run=start(account,"JM2701");Instant bar=Instant.now().minusSeconds(120);
        store.complete(claim(run),worker,"ALLOWED",prepared("JM2701","BUY",bar));
        f.observations.put("JM2701",f.quote("JM2701",90,60,"0.5",1000,3));
        var failedSignal=prepared("JM2701","HOLD",bar);
        store.complete(claim(run),worker,"ALLOWED",new PaperAutomationService.Prepared(failedSignal.live(),failedSignal.quotes(),failedSignal.chart(),null,"算法暂不可用",failedSignal.dataRefresh()));
        assertEquals(0,f.positions(account).size());assertEquals(2L,f.detail(account).get("fillCount"));
        store.complete(claim(run),worker,"ALLOWED",prepared("JM2701","BUY",bar));
        assertEquals(2L,f.detail(account).get("fillCount"));
        assertTrue(f.run(()->store.state(account)).toString().contains("固定跳数止损"));
    }
    @Test void automatedContractsShareFundsAndPermissionLossStopsExecution()throws Exception {
        UUID account=f.create(2500),a=start(account,"JM2701");start(account,"FG701");
        var jobs=store.claim(worker,4);assertEquals(2,jobs.size());
        for(var job:jobs)store.complete(job,worker,"ALLOWED",prepared(job.get("contract").toString(),"BUY",Instant.now().minusSeconds(120)));
        assertEquals(1,f.positions(account).size());assertEquals(1L,f.detail(account).get("fillCount"));
        assertTrue(((BigDecimal)f.detail(account).get("availableCash")).signum()>=0);
        assertTrue(f.run(()->store.state(account)).toString().contains("BLOCKED"));
        store.complete(claim(a),worker,"DENIED",null);
        assertEquals(false,f.run(()->f.f.jdbc.queryForObject("select enabled from paper_trading.paper_automation_run where id=?",Boolean.class,a)));
        assertEquals(1L,f.detail(account).get("fillCount"));
    }
    @Test void expiredLeaseCannotExecuteAfterWaitingForTheWalletLock()throws Exception {
        UUID account=f.create(100000),run=start(account,"JM2701");var job=claim(run);var observation=prepared("JM2701","BUY",Instant.now().minusSeconds(120));
        var pool=Executors.newFixedThreadPool(2);var locked=new CountDownLatch(1);var release=new CountDownLatch(1);
        try{
            var holder=pool.submit(()->f.run(()->{f.f.jdbc.queryForList("select id from paper_trading.paper_session where id=? for update",account);locked.countDown();try{release.await(8,TimeUnit.SECONDS);}catch(InterruptedException e){Thread.currentThread().interrupt();}return null;}));
            assertTrue(locked.await(4,TimeUnit.SECONDS));f.f.jdbc.update("update paper_trading.paper_automation_run set lease_until=clock_timestamp()+interval '1 second' where id=?",run);
            var completion=pool.submit(()->store.complete(job,worker,"ALLOWED",observation));
            f.f.jdbc.execute("select pg_sleep(1.2)");release.countDown();holder.get();completion.get();
            assertEquals(0L,f.detail(account).get("fillCount"));assertTrue(f.positions(account).isEmpty());
        } finally {release.countDown();pool.shutdownNow();}
    }
    @Test void cachedSignalsCannotOpenBeforeNewStartupDataIsReady()throws Exception {
        UUID account=f.create(100000),run=start(account,"JM2701");
        var ready=prepared("JM2701","BUY",Instant.now().minusSeconds(120));
        var pending=StrategyWorkflowStore.json(Map.of("state","PENDING","contract","JM2701","requestKey",store.startupKey(run),"message","正在拉取"));
        store.complete(claim(run),worker,"ALLOWED",new PaperAutomationService.Prepared(ready.live(),ready.quotes(),ready.chart(),ready.decision(),null,pending));
        assertEquals(0L,f.detail(account).get("fillCount"));assertTrue(f.positions(account).isEmpty());
        store.complete(claim(run),worker,"ALLOWED",ready);assertEquals(1L,f.detail(account).get("fillCount"));
        assertTrue(f.run(()->store.state(account)).toString().contains("latestMinuteTime"));
    }
    @Test void aServiceRestartRequiresAnotherRefreshEvenWhenAnOldReceiptExists()throws Exception {
        UUID account=f.create(100000),run=start(account,"JM2701");var old=prepared("JM2701","HOLD",Instant.now().minusSeconds(120));
        store.complete(claim(run),worker,"ALLOWED",old);
        var restored=new PaperAutomationService(f.f.jdbc,f.tx,f.f.data,new MatchingEngine());
        assertNotEquals(store.startupKey(run),restored.startupKey(run));
        restored.complete(claim(run),worker,"ALLOWED",old);
        assertEquals(0L,f.detail(account).get("fillCount"));
        assertEquals("REFRESHING",f.run(()->f.f.jdbc.queryForObject("select status from paper_trading.paper_automation_run where id=?",String.class,run)));
    }

    @Test void trinityFreezesRulesAndTradesOneHalfThenOneAddBeforeReversing()throws Exception {
        UUID account=f.create(100000);
        var config=new PaperAutomationService.TrinityConfig(5,10,20,3,30,"either","MINUTE_ADD",10);
        var request=new PaperAutomationService.Start("FG701","PERSONAL_TRINITY",2,0,BigDecimal.ZERO,BigDecimal.ZERO,false,null,config);
        assertTrue(f.run(()->store.start(account,f.owner,request)).toString().contains("\"entryMinutes\":30"));
        UUID run=f.run(()->f.f.jdbc.queryForObject("select id from paper_trading.paper_automation_run where session_id=?",UUID.class,account));
        Instant t=Instant.now().minusSeconds(40);
        applyTrinity(run,"BUY",t);
        assertEquals(1,positionLots(account));
        applyTrinity(run,"ADD_LONG",t.plusSeconds(10));
        applyTrinity(run,"ADD_LONG",t.plusSeconds(10));
        applyTrinity(run,"ADD_LONG",t.plusSeconds(11));
        assertEquals(2,positionLots(account));
        applyTrinity(run,"FLATTEN",t.plusSeconds(20));
        assertEquals(0,positionLots(account));
        applyTrinity(run,"SELL",t.plusSeconds(30));
        assertEquals(1,positionLots(account));
        assertEquals(-1,((Number) f.positions(account).get(0).get("direction")).intValue());
        assertEquals(4L,f.detail(account).get("fillCount"));
    }

    private int positionLots(UUID account) {
        var positions=f.positions(account);
        return positions.isEmpty()?0:((Number)positions.get(0).get("lots")).intValue();
    }

    private void applyTrinity(UUID run,String signal,Instant time)throws Exception {
        var base=prepared("FG701",signal,time);
        var decision=new StrategyDecision("PERSONAL_TRINITY","三位一体","paper-personal-trinity-v1",signal,
            "validated test decision",time,50,21,BigDecimal.ZERO);
        store.complete(claim(run),worker,"ALLOWED",new PaperAutomationService.Prepared(base.live(),base.quotes(),
            base.chart(),decision,null,base.dataRefresh()));
    }
}
