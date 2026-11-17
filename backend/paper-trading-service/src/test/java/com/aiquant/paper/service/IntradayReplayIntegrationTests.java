package com.aiquant.paper.service;

import com.aiquant.paper.api.PaperRequests.*;
import com.aiquant.paper.client.SimulationDataClient.*;
import com.aiquant.tenancy.TenantTransactions;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
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
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

@EnabledIfEnvironmentVariable(named="PAPER_TEST_JDBC_URL",matches="jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/paper_test.*")
class IntradayReplayIntegrationTests {
    PaperLedgerIntegrationTests f;TransactionTemplate tx;PaperFillNoteService notes;
    UUID tenant=UUID.randomUUID(),owner=UUID.randomUUID();
    @BeforeEach void setup()throws Exception{
        f=new PaperLedgerIntegrationTests();f.setup();
        Flyway.configure().dataSource(f.jdbc.getDataSource()).schemas("paper_trading").defaultSchema("paper_trading")
            .baselineOnMigrate(true).baselineVersion("6").load().migrate();
        tx=new TransactionTemplate(new DataSourceTransactionManager(f.jdbc.getDataSource()));notes=new PaperFillNoteService(f.jdbc);
    }
    <T>T run(UUID tenantId,UUID author,Supplier<T> work){return TenantTransactions.run(f.jdbc,tx,tenantId,()->{
        f.jdbc.queryForObject("select set_config('app.user_id',?,true)",String.class,author.toString());return work.get();});}
    <T>T run(Supplier<T> work){return run(tenant,owner,work);}
    HistoricalBar bar(String time,int o,int h,int l,int c){return new HistoricalBar(Instant.parse(time),"JM2701",BigDecimal.valueOf(o),BigDecimal.valueOf(h),BigDecimal.valueOf(l),BigDecimal.valueOf(c),10000,10000);}
    UUID create(List<HistoricalBar> bars,int stop,boolean intraday)throws Exception{
        var context=new ObjectMapper().readTree("{\"dailyMacd\":[{\"date\":\"2026-10-16\",\"availableAt\":\"2026-10-16T07:00:00Z\",\"dif\":1,\"dea\":2},{\"date\":\"2026-10-19\",\"availableAt\":\"2026-10-19T07:00:00Z\",\"dif\":2,\"dea\":1}]}");
        when(f.data.history(anyString(),any(),any(),eq(60))).thenReturn(new SimulationDataset("JM2701","DCE.jm2701","OBSERVED",Instant.now(),bars,List.of(),Map.of("JM2701",f.spec),List.of(),List.of(),context));
        return (UUID)run(()->f.service.createSession(new CreateSessionRequest("minute","HISTORICAL","JM2701",null,null,
            new BigDecimal("100000"),new BigDecimal("0.12"),BigDecimal.ZERO,BigDecimal.ONE,new BigDecimal("0.1"),false,
            "MANUAL",1,new BigDecimal("2"),new BigDecimal("3"),null,null,60,stop,intraday))).get("id");
    }
    void buy(UUID id){run(()->f.service.placeOrder(id,new PlaceOrderRequest("minute-open-"+UUID.randomUUID(),"BUY","OPEN","MARKET",1,null,null)));}
    @Test void minute_cursor_and_daily_context_never_reveal_the_future_and_stops_do_not_reverse()throws Exception{
        UUID id=create(List.of(bar("2026-10-19T01:00:00Z",100,101,99,100),bar("2026-10-19T01:01:00Z",100,101,94,99),bar("2026-10-19T01:02:00Z",99,100,98,99)),10,true);
        var before=run(()->f.service.chart(id,240));assertEquals(1,((List<?>)before.get("bars")).size());
        assertEquals("2026-10-16",((com.fasterxml.jackson.databind.JsonNode)before.get("dailyContext")).path("date").asText());
        buy(id);assertEquals(0L,run(()->f.service.detail(id)).get("fillCount"));
        var after=run(()->f.service.advance(id,new AdvanceRequest(1)));
        assertEquals(Instant.parse("2026-10-19T01:02:00Z"),after.get("currentMarketTime"));
        assertEquals(2L,after.get("fillCount"));assertEquals(0,((Map<?,?>)after.get("position")).get("lots"));
        assertEquals(2,((List<?>)run(()->f.service.chart(id,240)).get("bars")).size());
    }
    @Test void close_liquidation_uses_close_not_open_and_private_notes_survive_with_revision_checks()throws Exception{
        UUID id=create(List.of(bar("2026-10-19T06:58:00Z",100,101,99,100),bar("2026-10-19T06:59:00Z",101,111,100,110)),0,true);
        buy(id);var result=run(()->f.service.advance(id,new AdvanceRequest(1)));
        assertEquals(0,((Map<?,?>)result.get("position")).get("lots"));assertEquals(2L,result.get("fillCount"));
        var fills=(List<Map<String,Object>>)result.get("fills");var close=fills.stream().filter(v->"CLOSE".equals(v.get("offset"))).findFirst().orElseThrow();
        assertEquals(0,new BigDecimal("109.5").compareTo((BigDecimal)close.get("fillPrice")));
        UUID fill=(UUID)close.get("id");
        assertEquals(0,run(()->notes.get(id,fill,owner)).get("version"));
        run(()->notes.save(id,fill,owner,new PaperFillNoteService.SaveNote("耐心等待，避免追价",0)));
        assertEquals("耐心等待，避免追价",run(()->new PaperFillNoteService(f.jdbc).get(id,fill,owner)).get("content"));
        assertEquals(409,assertThrows(ResponseStatusException.class,()->run(()->notes.save(id,fill,owner,new PaperFillNoteService.SaveNote("覆盖",0)))).getStatusCode().value());
        UUID other=UUID.randomUUID();assertEquals("",run(tenant,other,()->notes.get(id,fill,other)).get("content"));
        assertEquals(0,run(tenant,other,()->f.jdbc.queryForObject("select count(*) from paper_trading.paper_fill_note",Integer.class)));
        assertEquals(0,run(UUID.randomUUID(),owner,()->f.jdbc.queryForObject("select count(*) from paper_trading.paper_fill_note",Integer.class)));
        run(()->notes.save(id,fill,owner,new PaperFillNoteService.SaveNote("",1)));
        assertEquals(2,run(()->notes.get(id,fill,owner)).get("version"));
    }
}
