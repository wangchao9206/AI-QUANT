package com.aiquant.paper.service;

import com.aiquant.paper.api.PaperRequests.*;
import com.aiquant.paper.client.SimulationDataClient;
import com.aiquant.paper.client.SimulationDataClient.*;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/** Runs ONLY against the disposable, volume-free paper_test database. */
@EnabledIfEnvironmentVariable(named="PAPER_TEST_JDBC_URL",matches="jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/paper_test.*")
class PaperLedgerIntegrationTests {
    JdbcTemplate jdbc;
    SimulationDataClient data;
    PaperTradingService service;
    List<HistoricalBar> bars;
    ContractSpec spec=new ContractSpec("JM2701",60,new BigDecimal("0.5"),new BigDecimal("1000"),new BigDecimal("3"));

    @BeforeEach
    void setup() throws Exception {
        String url=System.getenv("PAPER_TEST_JDBC_URL");
        var ds=new DriverManagerDataSource(url+(url.contains("?")?"&":"?")+"currentSchema=paper_trading","paper_test","isolated-test-only");
        jdbc=new JdbcTemplate(ds);
        assertEquals("paper_test",jdbc.queryForObject("select current_database()",String.class));
        jdbc.execute("drop schema if exists paper_trading cascade");
        jdbc.execute("create schema paper_trading");
        for(String file:List.of("V1__paper_trading_schema.sql","V2__paper_strategies.sql","V3__signal_bar_contract_identity.sql","V4__personal_strategy_training.sql","V5__book_reflections.sql","V6__strategy_workflows.sql")) {
            String sql=new String(getClass().getResourceAsStream("/db/migration/"+file).readAllBytes(),StandardCharsets.UTF_8);
            for(String statement:sql.split(";"))if(!statement.isBlank())jdbc.execute(statement);
        }
        data=mock(SimulationDataClient.class);
        service=new PaperTradingService(jdbc,new TransactionTemplate(new DataSourceTransactionManager(ds)),data,new MatchingEngine());
        bars=new ArrayList<>();
        for(int n=0;n<70;n++)bars.add(bar(Instant.parse("2025-01-01T00:00:00Z").plusSeconds(n*86400L),100+n));
        when(data.history(anyString(),any(),any())).thenReturn(new SimulationDataset("JM0","KQ.m@DCE.jm","OBSERVED",
            Instant.now(),bars,List.of(),Map.of("JM2701",spec),bars,bars));
        when(data.evaluate(any())).thenAnswer(inv->{StrategyInput input=inv.getArgument(0);
            return new StrategyDecision(input.strategy(),input.strategy(),"paper-daily-v1","BUY","fixture signal",
                input.bars().isEmpty()?null:input.bars().get(input.bars().size()-1).timestamp(),input.bars().size(),2,new BigDecimal("1"));});
    }

    HistoricalBar bar(Instant stamp,int close) {
        var p=BigDecimal.valueOf(close);
        return new HistoricalBar(stamp,"JM2701",p,p.add(BigDecimal.ONE),p.subtract(BigDecimal.ONE),p,10000,10000);
    }
    CreateSessionRequest request(String mode,String strategy) {
        return new CreateSessionRequest("isolated test",mode,"JM0",null,null,new BigDecimal("1000000"),
            new BigDecimal("0.12"),new BigDecimal("0.0001"),BigDecimal.ONE,new BigDecimal("0.1"),true,
            strategy,1,new BigDecimal("2"),new BigDecimal("3"));
    }
    UUID id(Map<String,Object> session){return (UUID)session.get("id");}
    LiveContext live(String state) {
        Instant stamp="LIVE".equals(state)?Instant.now():Instant.now().minusSeconds(86400);
        return new LiveContext("JMM","JM2701",state,Instant.now(),"OBSERVED",
            new QuoteSnapshot("JM2701","焦煤",new BigDecimal("200"),"OBSERVED","LIVE".equals(state)?"FRESH":"CACHED",stamp),
            spec,List.of(bar(Instant.now().minusSeconds(172800),198),bar(Instant.now().minusSeconds(86400),199)),bars);
    }

    @Test void historicalManualOrderActuallyPersistsAndFillsOnTheNextBar() {
        var account=service.createSession(request("HISTORICAL","MANUAL")); UUID id=id(account);
        var pending=service.placeOrder(id,new PlaceOrderRequest("manual-order-test","BUY","OPEN","MARKET",1,null,null));
        assertEquals(0L,pending.get("fillCount"));
        var advanced=service.advance(id,new AdvanceRequest(1));
        assertEquals(1,advanced.get("currentBarIndex"));assertEquals(1L,advanced.get("fillCount"));
        assertEquals(1,((Map<?,?>)advanced.get("position")).get("lots"));
        assertEquals(new BigDecimal("101.500000"),jdbc.queryForObject("select fill_price from paper_trading.paper_fill where session_id=?",BigDecimal.class,id));
    }

    @Test void chartContainsAllWindowFillsButNoFutureOrOtherAccountFills() {
        var account=service.createSession(request("HISTORICAL","MANUAL")); UUID own=id(account);
        UUID other=id(service.createSession(request("HISTORICAL","MANUAL")));
        String sql="""
            insert into paper_trading.paper_fill (id,session_id,event_type,contract,side,offset_type,
                quantity,market_price,fill_price,fee,slippage_cost,reason,market_time)
            values (?,?,'ORDER','JM2701','BUY','OPEN',1,100,100.5,3,30,'chart fixture',?)
            """;
        for(int n=0;n<205;n++)jdbc.update(sql,UUID.randomUUID(),own,java.sql.Timestamp.from(bars.get(0).timestamp()));
        jdbc.update(sql,UUID.randomUUID(),own,java.sql.Timestamp.from(bars.get(1).timestamp()));
        jdbc.update(sql,UUID.randomUUID(),other,java.sql.Timestamp.from(bars.get(0).timestamp()));
        var chart=service.chart(own,120);
        var fills=(List<?>)chart.get("fills");
        assertEquals(205,fills.size());
        assertEquals("chart fixture",((Map<?,?>)fills.get(0)).get("reason"));
        assertEquals(bars.get(0).timestamp(),((Map<?,?>)fills.get(0)).get("marketTime"));
        assertEquals(new BigDecimal("100.500000"),((Map<?,?>)fills.get(0)).get("fillPrice"));
    }

    @Test void historicalStrategyUsesOnlyTheCursorThenSubmitsAnAuditableNextBarOrder() {
        var account=service.createSession(request("HISTORICAL","BUY_AND_HOLD"));UUID id=id(account);
        var advanced=service.advance(id,new AdvanceRequest(1));
        assertEquals(1L,advanced.get("fillCount"));
        verify(data).evaluate(argThat(input->input.bars().size()==1 && input.asOf().equals(bars.get(0).timestamp())
            && "JM2701".equals(input.executionBars().get(0).contract())));
        assertEquals(1,jdbc.queryForObject("select count(*) from paper_trading.paper_strategy_decision where session_id=?",Integer.class,id));
        assertEquals("STRATEGY",jdbc.queryForObject("select origin from paper_trading.paper_order where session_id=?",String.class,id));
        assertThrows(IllegalStateException.class,()->service.placeOrder(id,new PlaceOrderRequest("manual-test","BUY","OPEN","MARKET",1,null,null)));
    }

    @Test void liveCreationAndClosedRefreshNeedNoReplayArchiveAndNeverFillCachedQuotes() {
        when(data.live("JM0")).thenReturn(live("CLOSED_CACHE"));
        var account=service.createSession(request("LIVE","BUY_AND_HOLD"));UUID id=id(account);
        var refreshed=service.advance(id,new AdvanceRequest(1));
        assertEquals("CLOSED_CACHE",refreshed.get("marketState"));assertEquals(0L,refreshed.get("fillCount"));
        verify(data,never()).history(anyString(),any(),any());verify(data,never()).evaluate(any());
    }

    @Test void repeatedLiveRefreshCannotRepeatOneDailyStrategyOrder() {
        LiveContext observed=live("LIVE");when(data.live("JM0")).thenReturn(observed);
        var account=service.createSession(request("LIVE","BUY_AND_HOLD"));UUID id=id(account);
        service.advance(id,new AdvanceRequest(1));var second=service.advance(id,new AdvanceRequest(1));
        assertEquals(1L,second.get("orderCount"));assertEquals(1L,second.get("fillCount"));
    }

    @Test void liveRollRequiresBothFreshObservedLegsAndDoesNotBookThePriceGapAsProfit() {
        LiveContext old=live("LIVE");when(data.live("JM0")).thenReturn(old);
        UUID id=id(service.createSession(request("LIVE","BUY_AND_HOLD")));
        service.advance(id,new AdvanceRequest(1));
        var nextSpec=new ContractSpec("JM2705",60,new BigDecimal("0.5"),new BigDecimal("1100"),new BigDecimal("3"));
        var next=new LiveContext("JMM","JM2705","LIVE",Instant.now(),"OBSERVED",
            new QuoteSnapshot("JM2705","焦煤",new BigDecimal("220"),"OBSERVED","FRESH",Instant.now()),nextSpec,old.signalBars(),old.executionBars());
        when(data.live("JM0")).thenReturn(next);when(data.quote("JM2701")).thenReturn(old.quote());
        var result=service.advance(id,new AdvanceRequest(1));
        assertEquals("JM2705",result.get("currentContract"));
        assertEquals(3L,result.get("fillCount"));
        assertTrue(((BigDecimal)result.get("equity")).compareTo(new BigDecimal("1000000"))<0);
    }

    @Test void protectionUsesActualContractAtrAndStopWinsWhenDailyBarTouchesBothBounds() {
        bars.set(1,new HistoricalBar(bars.get(1).timestamp(),"JM2701",new BigDecimal("101"),new BigDecimal("105"),
            new BigDecimal("90"),new BigDecimal("100"),10000,10000));
        var account=service.createSession(request("HISTORICAL","BOLLINGER_REVERSAL"));UUID id=id(account);
        var result=service.advance(id,new AdvanceRequest(1));
        assertEquals(2L,result.get("fillCount"));
        assertEquals(0,((Map<?,?>)result.get("position")).get("lots"));
        String reason=jdbc.queryForObject("select reason from paper_trading.paper_fill where session_id=? and offset_type='CLOSE'",String.class,id);
        assertTrue(reason.contains("止损"));
        assertTrue(((BigDecimal)result.get("equity")).compareTo(new BigDecimal("1000000"))<0);
        assertTrue(((BigDecimal)result.get("maxDrawdownPct")).signum()>0);
    }
}
