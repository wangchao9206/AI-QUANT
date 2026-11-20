package com.aiquant.paper.service;

import com.aiquant.paper.api.PaperRequests.AdvanceRequest;
import com.aiquant.paper.api.PaperRequests.PlaceOrderRequest;
import com.aiquant.paper.api.StrategyWorkflowController.CreateRequest;
import com.aiquant.paper.api.StrategyWorkflowController.MaTrendReplayRequest;
import com.aiquant.paper.api.StrategyWorkflowController.PublishRequest;
import com.aiquant.paper.service.ReplayReviewService.SaveReview;
import com.aiquant.paper.service.ReplayReviewService.Stage;
import com.aiquant.paper.service.ReplayReviewService.SuggestedAction;
import com.aiquant.paper.service.WorkflowTrialService.CreateTrial;
import com.aiquant.tenancy.TenantTransactions;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.UUID;
import java.util.function.Supplier;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.core.io.ClassPathResource;
import org.springframework.web.server.ResponseStatusException;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@EnabledIfEnvironmentVariable(named="PAPER_TEST_JDBC_URL",matches="jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/paper_test.*")
class ReplayReviewIntegrationTests {
    PaperPortfolioIntegrationTests fixture;
    ReplayReviewService reviews;
    StrategyWorkflowService workflows;
    UUID otherOwner = UUID.randomUUID();

    @BeforeEach void prepare() throws Exception {
        fixture = new PaperPortfolioIntegrationTests();
        fixture.setup();
        reviews = new ReplayReviewService(fixture.f.jdbc);
        workflows = new StrategyWorkflowService(fixture.f.jdbc,fixture.tx,fixture.f.data);
    }

    @Test void validatesHistoricalCursorAndFillRetainsEvidenceAndKeepsNotesPrivate() {
        var sim = fixture.f.service;
        var account = fixture.run(()->sim.createSession(fixture.f.request("HISTORICAL","MANUAL")));
        UUID session = fixture.f.id(account);
        UUID owner = fixture.owner;
        Instant first = (Instant)account.get("currentMarketTime");
        var future = new SaveReview(UUID.randomUUID(), first.plusSeconds(86400), Stage.BAR, null, SuggestedAction.WAIT, "未来尚未显示", null);
        assertEquals(400,assertThrows(ResponseStatusException.class,()->fixture.run(()->reviews.saveSessionNote(session,owner,future))).getStatusCode().value());

        var noTrade = new SaveReview(UUID.randomUUID(),first,Stage.BAR,null,SuggestedAction.OPEN_LONG,"回踩确认，可以试多",null);
        var saved = fixture.run(()->reviews.saveSessionNote(session,owner,noTrade));
        assertEquals("NO_ACTION",saved.observedAction());
        assertEquals(100,saved.evidence().path("close").asInt());
        fixture.run(()->sim.placeOrder(session,new PlaceOrderRequest("review-paper-order","BUY","OPEN","MARKET",1,null,null)));
        fixture.run(()->sim.advance(session,new AdvanceRequest(1)));
        assertEquals(saved,fixture.run(()->reviews.saveSessionNote(session,owner,noTrade)));

        var trade = fixture.run(()->fixture.f.jdbc.queryForMap("select id,market_time from paper_trading.paper_fill where session_id=?",session));
        var fill = new SaveReview(UUID.randomUUID(),((Timestamp)trade.get("market_time")).toInstant(),Stage.FILL,
            trade.get("id").toString(),SuggestedAction.WAIT,"确认不够，等下一根收盘",null);
        var fillNote = fixture.run(()->reviews.saveSessionNote(session,owner,fill));
        assertEquals("OPEN_LONG",fillNote.observedAction());
        assertEquals(1,fillNote.evidence().path("quantity").asInt());
        assertEquals(2,fixture.run(()->reviews.sessionNotes(session,owner)).size());
        assertEquals(404,assertThrows(ResponseStatusException.class,()->asPeer(()->reviews.sessionNotes(session,owner))).getStatusCode().value());
        assertEquals(0,asPeer(()->fixture.f.jdbc.queryForObject("select count(*) from paper_trading.paper_replay_review",Integer.class)));
        var changed = new SaveReview(fill.clientRequestId(),fill.at(),fill.stage(),fill.targetId(),SuggestedAction.ADD,"重复请求改内容",null);
        assertEquals(409,assertThrows(ResponseStatusException.class,()->fixture.run(()->reviews.saveSessionNote(session,owner,changed))).getStatusCode().value());
        assertEquals(1L,fixture.run(()->sim.detail(session)).get("fillCount"));
    }

    @Test void pinsPrivateMaReplayAndOnlyAcceptsFillsInSelectedBar() throws Exception {
        var mapper = new ObjectMapper();
        var definition = mapper.readTree(new ClassPathResource("ma-trend-workflow-graph.json").getInputStream());
        UUID workflow = (UUID)fixture.run(()->workflows.create(new CreateRequest("ma-review-publish-test", "MA review", "", definition))).get("id");
        UUID version = fixture.run(()->workflows.publish(workflow,new PublishRequest(1,"ma-review-version-test"))).id();
        when(fixture.f.data.replayMaTrendWorkflow(anyMap())).thenReturn(mapper.readTree("""
            {"reviewDatasetId":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
             "metrics":{"entryCount":1},"reviewTimeline":[
                {"at":"2026-11-02T21:15:00+08:00","signal":"HOLD","executionIndexes":[]},
                {"at":"2026-11-02T21:30:00+08:00","signal":"HOLD","executionIndexes":[0]}],
             "executions":[{"at":"2026-11-02T21:15:00+08:00","action":"OPEN","lots":10}]}
            """));
        var request = new MaTrendReplayRequest("FG701",new BigDecimal("100000"),1,true);
        UUID run = UUID.fromString(fixture.run(()->workflows.maTrendReplay(version,request,fixture.owner)).path("reviewRunId").asText());
        assertEquals(run.toString(),fixture.run(()->workflows.maTrendReplay(version,request,fixture.owner)).path("reviewRunId").asText());
        assertEquals(404,assertThrows(ResponseStatusException.class,()->asPeer(()->reviews.runNotes(version,run,fixture.owner))).getStatusCode().value());

        Instant first = Instant.parse("2026-11-02T13:15:00Z");
        var unavailable = new SaveReview(UUID.randomUUID(),first,Stage.FILL,"0",SuggestedAction.WAIT,"另一根的成交",run);
        assertEquals(400,assertThrows(ResponseStatusException.class,()->fixture.run(()->reviews.saveRunNote(version,fixture.owner,unavailable))).getStatusCode().value());
        var valid = new SaveReview(UUID.randomUUID(),first.plusSeconds(900),Stage.FILL,"0",SuggestedAction.REDUCE,"先试较小仓位",run);
        var note = fixture.run(()->reviews.saveRunNote(version,fixture.owner,valid));
        assertEquals("OPEN",note.observedAction());
        assertEquals(workflow,note.workflowId());
        assertEquals(10,note.evidence().path("fill").path("lots").asInt());
        assertEquals(note,fixture.run(()->reviews.runNotes(version,run,fixture.owner)).get(0));
        assertEquals(0,asPeer(()->fixture.f.jdbc.queryForObject("select count(*) from paper_trading.paper_replay_review",Integer.class)));
    }

    @Test void createsNamedTrialsIdempotentlyAndReopensTheirPrivateFrozenResults() throws Exception {
        var mapper = new ObjectMapper();
        var definition = mapper.readTree(new ClassPathResource("ma-trend-workflow-graph.json").getInputStream());
        UUID workflow = (UUID)fixture.run(()->workflows.create(
            new CreateRequest("ma-trial-publish-test","MA trial","",definition))).get("id");
        UUID version = fixture.run(()->workflows.publish(workflow,new PublishRequest(1,"ma-trial-version-test"))).id();
        when(fixture.f.data.replayMaTrendWorkflow(anyMap())).thenReturn(mapper.readTree("""
            {"reviewDatasetId":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
             "scope":{"first":"2026-11-01","last":"2026-11-03","scoreDays":2},
             "metrics":{"entryCount":0},"assumptions":["基准成本"],
             "reviewTimeline":[{"at":"2026-11-02T21:15:00+08:00","signal":"HOLD","executionIndexes":[]}],"executions":[]}
            """));
        var trials = new WorkflowTrialService(fixture.f.jdbc,workflows);
        UUID owner = fixture.owner;
        var request = new CreateTrial(version,"玻璃历史试验","FG701",new BigDecimal("100000"),1,UUID.randomUUID());
        var saved = fixture.run(()->trials.create(owner,request));
        assertEquals(saved,fixture.run(()->trials.create(owner,request)));
        assertEquals(saved,fixture.run(()->trials.detail(owner,saved.trial().id())));
        verify(fixture.f.data,times(1)).replayMaTrendWorkflow(anyMap());
        assertEquals("玻璃历史试验",saved.trial().name());
        assertEquals(version,saved.version().id());
        assertEquals(saved.trial().id().toString(),saved.replay().path("reviewRunId").asText());
        assertEquals(1,saved.replay().path("reviewTimeline").size());
        assertEquals(2,saved.replay().path("scope").path("scoreDays").asInt());
        assertEquals("基准成本",saved.replay().path("assumptions").path(0).asText());
        assertEquals(1,fixture.run(()->trials.list(owner)).size());

        assertEquals(0,asPeer(()->trials.list(otherOwner)).size());
        assertEquals(404,assertThrows(ResponseStatusException.class,
            ()->asPeer(()->trials.detail(otherOwner,saved.trial().id()))).getStatusCode().value());
        var changed = new CreateTrial(version,"不同名称","FG701",request.initialCash(),1,request.clientRequestId());
        assertEquals(409,assertThrows(ResponseStatusException.class,
            ()->fixture.run(()->trials.create(owner,changed))).getStatusCode().value());

        var another = new CreateTrial(version,request.name(),"FG701",request.initialCash(),1,UUID.randomUUID());
        var second = fixture.run(()->trials.create(owner,another));
        assertNotEquals(saved.trial().id(),second.trial().id());
        var ordinaryReplay = new MaTrendReplayRequest("FG701",request.initialCash(),1,true);
        var ordinary = fixture.run(()->workflows.maTrendReplay(version,ordinaryReplay,owner));
        assertNotEquals(saved.trial().id().toString(),ordinary.path("reviewRunId").asText());
        assertEquals(2,fixture.run(()->trials.list(owner)).size());

        var note = new SaveReview(UUID.randomUUID(),Instant.parse("2026-11-02T13:15:00Z"),
            Stage.BAR,null,SuggestedAction.WAIT,"等待下一根确认",saved.trial().id());
        fixture.run(()->reviews.saveRunNote(version,owner,note));
        assertEquals(1,fixture.run(()->reviews.runNotes(version,saved.trial().id(),owner)).size());
        assertTrue(fixture.run(()->reviews.runNotes(version,second.trial().id(),owner)).isEmpty());
    }

    private <T> T asPeer(Supplier<T> operation) {
        return TenantTransactions.run(fixture.f.jdbc,fixture.tx,fixture.tenant,()->{
            fixture.f.jdbc.queryForObject("select set_config('app.user_id',?,true)",String.class,otherOwner.toString());
            return operation.get();
        });
    }
}
