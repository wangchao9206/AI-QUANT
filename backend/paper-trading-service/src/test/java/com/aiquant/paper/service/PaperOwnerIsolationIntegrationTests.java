package com.aiquant.paper.service;

import com.aiquant.paper.api.PaperRequests.*;
import com.aiquant.paper.api.PersonalTrainingController.*;
import com.aiquant.tenancy.TenantTransactions;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.util.*;
import java.util.function.Supplier;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.dao.DataAccessException;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;

/** Same tenant, different authenticated users: privacy must hold below every API. */
@EnabledIfEnvironmentVariable(named="PAPER_TEST_JDBC_URL",matches="jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/paper_test.*")
class PaperOwnerIsolationIntegrationTests {
    PaperPortfolioIntegrationTests f;
    UUID peer=UUID.randomUUID();
    @BeforeEach void setup()throws Exception{f=new PaperPortfolioIntegrationTests();f.setup();}
    <T>T peer(Supplier<T> work){return TenantTransactions.run(f.f.jdbc,f.tx,f.tenant,()->{
        f.f.jdbc.queryForObject("select set_config('app.user_id',?,true)",String.class,peer.toString());return work.get();});}

    @Test void anotherUserCannotReadTradeAnnotateDeleteOrControlAnAccount() {
        UUID id=f.create(100000);
        f.order(id,"private-fill","JM2701","BUY","OPEN","MARKET",null);
        f.order(id,"private-pending","JM2701","BUY","OPEN","LIMIT",BigDecimal.valueOf(80));
        UUID fill=f.run(()->f.f.jdbc.queryForObject("select id from paper_trading.paper_fill where session_id=?",UUID.class,id));
        UUID pending=f.run(()->f.f.jdbc.queryForObject("select id from paper_trading.paper_order where session_id=? and status='PENDING'",UUID.class,id));
        var notes=new PaperFillNoteService(f.f.jdbc);
        f.run(()->notes.save(id,fill,f.owner,new PaperFillNoteService.SaveNote("仅属于账户创建人的心得",0)));
        var auto=new PaperAutomationService(f.f.jdbc,f.tx,f.f.data,new MatchingEngine());
        var start=new PaperAutomationService.Start("FG701","MA20_MACD",1,10,BigDecimal.ZERO,BigDecimal.ZERO,true,null);
        f.run(()->auto.start(id,f.owner,start));
        UUID run=f.run(()->f.f.jdbc.queryForObject("select id from paper_trading.paper_automation_run where session_id=?",UUID.class,id));
        var before=f.detail(id);
        assertTrue(peer(()->f.f.service.listSessions()).isEmpty());
        for(String table:List.of("paper_session","paper_fill","paper_order","paper_fill_note","paper_portfolio_position","paper_contract_spec","paper_automation_run","paper_automation_event"))
            assertEquals(0,peer(()->f.f.jdbc.queryForObject("select count(*) from paper_trading."+table,Integer.class)),table);
        assertThrows(IllegalArgumentException.class,()->peer(()->f.f.service.detail(id)));
        assertThrows(IllegalArgumentException.class,()->peer(()->f.f.service.chart(id,240)));
        assertThrows(IllegalArgumentException.class,()->peer(()->f.f.service.records(id,"fills",1,10)));
        assertThrows(IllegalArgumentException.class,()->peer(()->f.f.service.placeOrder(id,new PlaceOrderRequest("peer-order","BUY","OPEN","MARKET",1,null,null,"FG701"))));
        assertThrows(IllegalArgumentException.class,()->peer(()->f.f.service.cancelOrder(id,pending)));
        assertThrows(IllegalStateException.class,()->peer(()->f.f.service.setPaused(id,true)));
        assertThrows(IllegalArgumentException.class,()->peer(()->{f.f.service.deleteSession(id);return null;}));
        assertEquals(404,assertThrows(ResponseStatusException.class,()->peer(()->notes.get(id,fill,peer))).getStatusCode().value());
        assertEquals(404,assertThrows(ResponseStatusException.class,()->peer(()->notes.save(id,fill,peer,new PaperFillNoteService.SaveNote("越权覆盖",0)))).getStatusCode().value());
        assertThrows(IllegalArgumentException.class,()->peer(()->auto.state(id)));
        assertThrows(IllegalArgumentException.class,()->peer(()->auto.start(id,peer,start)));
        assertThrows(IllegalArgumentException.class,()->peer(()->auto.stop(id,run)));
        var after=f.detail(id);
        for(String key:List.of("cashBalance","equity","fillCount","reservedCash"))assertEquals(before.get(key),after.get(key),key);
        assertEquals("仅属于账户创建人的心得",f.run(()->notes.get(id,fill,f.owner)).get("content"));
        assertTrue(f.run(()->f.f.jdbc.queryForObject("select enabled from paper_trading.paper_automation_run where id=?",Boolean.class,run)));
        UUID own=peer(()->(UUID)f.f.service.createSession(new CreateSessionRequest("peer wallet","LIVE","JM2701",null,null,
            BigDecimal.valueOf(100000),new BigDecimal(".12"),BigDecimal.ZERO,BigDecimal.ONE,new BigDecimal(".1"),false,"MANUAL",1,BigDecimal.valueOf(2),BigDecimal.valueOf(3))).get("id"));
        assertEquals(own,peer(()->f.f.service.listSessions()).get(0).get("id"));
        assertEquals(id,f.run(()->f.f.service.listSessions()).get(0).get("id"));
        assertEquals(1,peer(()->f.f.service.listSessions()).size());
        assertThrows(DataAccessException.class,()->peer(()->f.f.jdbc.update("update paper_trading.paper_session set owner_id=? where id=?",f.owner,own)));
    }

    @Test void personalVersionsReflectionsAndMissingIdentityAreAlsoPrivate() {
        var training=new PersonalTrainingService(f.f.jdbc,f.tx,new ObjectMapper(),f.f.service);
        UUID a=(UUID)f.run(training::versions).get(0).get("id");
        UUID b=(UUID)peer(training::versions).get(0).get("id");assertNotEquals(a,b);
        assertEquals(a,f.run(training::versions).get(0).get("id"));
        assertEquals(1,peer(training::versions).size());
        assertThrows(IllegalArgumentException.class,()->peer(()->training.createVersion(new CreateVersionRequest(a,"invalid","h","v",PersonalStrategyEngine.Rules.defaults()))));
        f.run(()->{training.reflect(new ReflectionRequest(null,null,"EMOTION","创建人的私有复盘"));return null;});
        assertEquals(0L,peer(()->training.reflections(null,1,10)).get("total"));
        peer(()->{training.reflect(new ReflectionRequest(null,null,"EXECUTION","另一用户的复盘"));return null;});
        assertEquals(1L,peer(()->training.reflections(null,1,10)).get("total"));
        assertEquals(1L,f.run(()->training.reflections(null,1,10)).get("total"));
        f.create(100000);
        assertEquals(0,TenantTransactions.run(f.f.jdbc,f.tx,f.tenant,()->{
            f.f.jdbc.queryForObject("select set_config('app.user_id','',true)",String.class);
            return f.f.jdbc.queryForObject("select count(*) from paper_trading.paper_session",Integer.class);
        }));
    }
}
