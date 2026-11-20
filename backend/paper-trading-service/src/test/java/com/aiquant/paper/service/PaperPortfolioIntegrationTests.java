package com.aiquant.paper.service;

import com.aiquant.paper.api.PaperRequests.*;
import com.aiquant.paper.client.SimulationDataClient.*;
import com.aiquant.tenancy.TenantTransactions;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.Supplier;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

@EnabledIfEnvironmentVariable(named="PAPER_TEST_JDBC_URL",matches="jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/paper_test.*")
class PaperPortfolioIntegrationTests {
    PaperLedgerIntegrationTests f;TransactionTemplate tx;
    UUID tenant=UUID.randomUUID(),owner=UUID.randomUUID();
    final Map<String,LiveContext> observations=new ConcurrentHashMap<>();
    final Queue<String> rejections=new ConcurrentLinkedQueue<>();
    @BeforeEach void setup()throws Exception {
        f=new PaperLedgerIntegrationTests();f.setup();
        Flyway.configure().dataSource(f.jdbc.getDataSource()).schemas("paper_trading").defaultSchema("paper_trading")
            .baselineOnMigrate(true).baselineVersion("6").load().migrate();
        tx=new TransactionTemplate(new DataSourceTransactionManager(f.jdbc.getDataSource()));
        observations.put("JM2701",quote("JM2701",100,60,"0.5",1000,3));
        observations.put("FG701",quote("FG701",900,20,"1",2000,6));
        when(f.data.live(anyString())).thenAnswer(inv->observations.get(inv.getArgument(0)));
        when(f.data.portfolioQuotes(anyList())).thenAnswer(inv->new PortfolioQuotes(Map.copyOf(observations),Map.of()));
    }
    LiveContext quote(String contract,int price,int multiplier,String tick,int margin,int fee) {
        return new LiveContext(contract,contract,"LIVE",Instant.now(),"TEST_OBSERVED",
            new QuoteSnapshot(contract,contract,BigDecimal.valueOf(price),"TEST_OBSERVED","FRESH",Instant.now()),
            new ContractSpec(contract,multiplier,new BigDecimal(tick),BigDecimal.valueOf(margin),BigDecimal.valueOf(fee)),List.of(),List.of());
    }
    <T>T run(Supplier<T> work){return TenantTransactions.run(f.jdbc,tx,tenant,()->{
        f.jdbc.queryForObject("select set_config('app.user_id',?,true)",String.class,owner.toString());return work.get();});}
    UUID create(int cash) {
        UUID id=(UUID)run(()->f.service.createSession(new CreateSessionRequest("portfolio","LIVE","JM2701",null,null,
            BigDecimal.valueOf(cash),new BigDecimal("0.12"),BigDecimal.ZERO,BigDecimal.ONE,new BigDecimal("0.1"),false,
            "MANUAL",1,new BigDecimal("2"),new BigDecimal("3")))).get("id");
        run(()->f.service.selectInstrument(id,"FG701"));return id;
    }
    Map<String,Object> order(UUID id,String key,String contract,String side,String offset,String type,BigDecimal limit) {
        return run(()->f.service.placeOrder(id,new PlaceOrderRequest(key,side,offset,type,1,limit,null,contract)));
    }
    Map<String,Object> detail(UUID id){return run(()->f.service.detail(id));}
    void money(String expected,Object actual){assertEquals(0,new BigDecimal(expected).compareTo((BigDecimal)actual));}
    @SuppressWarnings("unchecked") List<Map<String,Object>> positions(UUID id){return (List<Map<String,Object>>)detail(id).get("positions");}

    @Test void sharedWalletIndependentContractsAndPrivateNotesSurviveSwitching() {
        UUID id=create(100000);
        order(id,"first-contract-open","JM2701","BUY","OPEN","MARKET",null);
        order(id,"second-contract-open","FG701","SELL","OPEN","MARKET",null);
        var both=detail(id);assertEquals(2,positions(id).size());
        money("99991",both.get("cashBalance"));money("50",both.get("slippagePaid"));money("9",both.get("commissionPaid"));
        money("99941",both.get("equity"));money("3160",both.get("totalMargin"));money("96781",both.get("availableCash"));
        var switched=run(()->f.service.selectInstrument(id,"JM2701"));
        assertEquals(id,switched.get("id"));assertEquals(2,positions(id).size());money("99991",switched.get("cashBalance"));
        observations.put("JM2701",quote("JM2701",102,60,"0.5",1000,3));
        order(id,"first-contract-close","JM2701","SELL","CLOSE","MARKET",null);
        assertEquals("FG701",positions(id).get(0).get("contract"));money("60",detail(id).get("realizedPnl"));
        UUID fill=run(()->f.jdbc.queryForObject("select id from paper_trading.paper_fill where session_id=? and contract='JM2701' and offset_type='CLOSE'",UUID.class,id));
        var notes=new PaperFillNoteService(f.jdbc);
        run(()->notes.save(id,fill,owner,new PaperFillNoteService.SaveNote("分品种复盘，控制共同资金占用",0)));
        run(()->f.service.selectInstrument(id,"FG701"));
        assertEquals("分品种复盘，控制共同资金占用",run(()->notes.get(id,fill,owner)).get("content"));
        assertEquals(0,run(()->f.jdbc.queryForObject("select count(*) from paper_trading.paper_position where session_id=?",Integer.class,id)));
        assertEquals(0,TenantTransactions.run(f.jdbc,tx,UUID.randomUUID(),()->f.jdbc.queryForObject("select count(*) from paper_trading.paper_portfolio_position",Integer.class)));
        assertThrows(IllegalStateException.class,()->order(id,"wrong-contract-close","JM2701","SELL","CLOSE","MARKET",null));
    }
    @Test void pendingReservationsAndConcurrentOrdersCannotReuseTheSameFunds()throws Exception {
        UUID id=create(2500);
        var pending=order(id,"reserved-first-open","JM2701","BUY","OPEN","LIMIT",BigDecimal.valueOf(90));
        money("1003",pending.get("reservedCash"));money("1497",pending.get("availableCash"));
        assertThrows(IllegalStateException.class,()->order(id,"reserved-second-open","FG701","BUY","OPEN","LIMIT",BigDecimal.valueOf(800)));
        UUID orderId=run(()->f.jdbc.queryForObject("select id from paper_trading.paper_order where session_id=?",UUID.class,id));
        run(()->f.service.cancelOrder(id,orderId));money("0",detail(id).get("reservedCash"));
        var pool=Executors.newFixedThreadPool(2);
        try {
            var a=pool.submit(()->tryOpen(id,"concurrent-first-open","JM2701"));
            var b=pool.submit(()->tryOpen(id,"concurrent-second-open","FG701"));
            int filled=(a.get(20,TimeUnit.SECONDS)?1:0)+(b.get(20,TimeUnit.SECONDS)?1:0);
            assertEquals(1,filled,()->"accepted orders: "+rejections);
            assertEquals(1,positions(id).size(),()->"positions after accepted orders: "+detail(id));
            assertTrue(((BigDecimal)detail(id).get("availableCash")).signum()>=0);
        } finally {pool.shutdownNow();}
    }
    boolean tryOpen(UUID id,String key,String contract) {
        try {order(id,key,contract,"BUY","OPEN","MARKET",null);return true;}
        catch(IllegalStateException rejected){rejections.add(rejected.getMessage());return false;}
    }
    @Test void idempotencyAndUnavailableQuotesPreserveExistingPositions() {
        UUID id=create(100000);
        order(id,"idempotent-contract","JM2701","BUY","OPEN","MARKET",null);
        var before=detail(id);
        order(id,"idempotent-contract","JM2701","BUY","OPEN","MARKET",null);
        assertEquals(before.get("fillCount"),detail(id).get("fillCount"));
        assertThrows(IllegalArgumentException.class,()->order(id,"idempotent-contract","FG701","BUY","OPEN","MARKET",null));
        observations.remove("JM2701");
        assertThrows(IllegalStateException.class,()->order(id,"missing-held-quote","FG701","BUY","OPEN","MARKET",null));
        assertEquals(1,positions(id).size());money("99997",detail(id).get("cashBalance"));
        run(()->f.service.advance(id,new AdvanceRequest(1)));
        assertEquals("UNAVAILABLE",positions(id).get(0).get("marketState"));
        assertEquals(before.get("fillCount"),detail(id).get("fillCount"));
    }
    @Test void upgradingAnExistingAccountKeepsItsCashPositionAndPendingOrders() {
        when(f.data.quote("JM2701")).thenAnswer(inv->observations.get("JM2701").quote());
        UUID id=(UUID)run(()->f.service.createSession(new CreateSessionRequest("legacy","LIVE","JM2701",null,null,
            BigDecimal.valueOf(100000),new BigDecimal("0.12"),BigDecimal.ZERO,BigDecimal.ONE,new BigDecimal("0.1"),false,
            "MANUAL",1,new BigDecimal("2"),new BigDecimal("3")))).get("id");
        run(()->f.service.placeOrder(id,new PlaceOrderRequest("legacy-existing-fill","BUY","OPEN","MARKET",1,null,null)));
        run(()->f.service.placeOrder(id,new PlaceOrderRequest("legacy-existing-pending","BUY","OPEN","LIMIT",1,BigDecimal.valueOf(80),null)));
        var before=detail(id);run(()->f.service.selectInstrument(id,"FG701"));var after=detail(id);
        assertEquals(before.get("cashBalance"),after.get("cashBalance"));assertEquals(before.get("fillCount"),after.get("fillCount"));
        assertEquals(1,positions(id).size());assertEquals("JM2701",positions(id).get(0).get("contract"));
        money("1003",after.get("reservedCash"));
        assertEquals("JM2701",run(()->f.jdbc.queryForObject("select contract from paper_trading.paper_order where session_id=? and client_order_id='legacy-existing-pending'",String.class,id)));
    }
}
