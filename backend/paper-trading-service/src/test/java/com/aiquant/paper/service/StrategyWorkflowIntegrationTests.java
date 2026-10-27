package com.aiquant.paper.service;
import com.aiquant.paper.api.StrategyWorkflowController.*;
import com.aiquant.paper.api.PaperRequests.*;
import com.aiquant.paper.client.SimulationDataClient.*;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

@EnabledIfEnvironmentVariable(named="PAPER_TEST_JDBC_URL",matches="jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/paper_test.*")
class StrategyWorkflowIntegrationTests {
    final ObjectMapper json=new ObjectMapper();
    PaperLedgerIntegrationTests f;StrategyWorkflowService workflows;JsonNode graph;
    @BeforeEach void setup() throws Exception {
        f=new PaperLedgerIntegrationTests();f.setup();
        workflows=new StrategyWorkflowService(f.jdbc,new TransactionTemplate(new DataSourceTransactionManager(f.jdbc.getDataSource())),f.data);
        graph=json.readTree("""
            {"schemaVersion":1,"nodes":[{"id":"risk","type":"RISK","params":{"lots":2,"stopLossAtr":2,"takeProfitAtr":3}}],"edges":[]}
            """);
        when(f.data.validateWorkflow(any())).thenAnswer(inv->{
            var result=json.createObjectNode();result.set("definition",inv.getArgument(0));result.put("engineVersion",StrategyWorkflowStore.ENGINE);
            result.put("requiredBars",2);result.set("risk",json.readTree("{\"lots\":2,\"stopLossAtr\":2,\"takeProfitAtr\":3}"));return result;});
        doAnswer(inv->{StrategyInput input=inv.getArgument(0);return new StrategyDecision("WORKFLOW","fixture",StrategyWorkflowStore.ENGINE,"BUY","isolated candidate",
            input.bars().get(input.bars().size()-1).timestamp(),input.bars().size(),2,BigDecimal.ONE,
            List.of(Map.of("nodeId","open","status","CANDIDATE","value","BUY")));}).when(f.data).evaluate(any());
    }
    UUID draft(){return (UUID)workflows.create(new CreateRequest("isolated-workflow-create","first","",graph)).get("id");}
    StrategyWorkflowStore.Version publish(UUID id){return workflows.publish(id,new PublishRequest(1,"isolated-workflow-publish"));}
    CreateSessionRequest request(String mode,UUID version){
        var r=f.request(mode,"WORKFLOW");
        return new CreateSessionRequest(r.name(),r.mode(),r.symbol(),r.startDate(),r.endDate(),r.initialCash(),r.marginRate(),r.feeRate(),
            r.slippageTicks(),r.maxParticipationRate(),r.autoRoll(),"WORKFLOW",999,new BigDecimal("19"),new BigDecimal("49"),version);
    }
    @Test void optimisticSaveAndImmutableIdempotentPublish() {
        UUID id=draft();var version=publish(id);assertEquals(version.id(),publish(id).id());
        assertEquals(id,workflows.create(new CreateRequest("isolated-workflow-create","first","",graph)).get("id"));
        var changed=graph.deepCopy();((com.fasterxml.jackson.databind.node.ObjectNode)changed).put("editorNote","draft only");
        workflows.save(id,new SaveRequest(1,"second","",changed));
        assertThrows(IllegalStateException.class,()->workflows.save(id,new SaveRequest(1,"overwrite","",graph)));
        var frozen=workflows.version(version.id());assertEquals("first",frozen.name());assertFalse(frozen.definition().has("editorNote"));
        assertEquals(1,f.jdbc.queryForObject("select count(*) from paper_trading.strategy_workflow_version",Integer.class));
        assertThrows(IllegalStateException.class,()->workflows.publish(id,new PublishRequest(2,"isolated-workflow-publish")));
    }
    @Test void historicalSessionFreezesServerVersionAndRiskAndPersistsNodeTrace() {
        UUID draft=draft();var version=publish(draft);var account=f.service.createSession(request("HISTORICAL",version.id()));UUID id=f.id(account);
        assertEquals(2,account.get("strategyLots"));assertEquals(version.id(),account.get("workflowVersionId"));assertEquals("first",account.get("workflowName"));
        var edited=json.createObjectNode().put("schemaVersion",1);edited.set("nodes",json.createArrayNode());edited.set("edges",json.createArrayNode());
        workflows.save(draft,new SaveRequest(1,"edited later","",edited));
        var advanced=f.service.advance(id,new AdvanceRequest(1));assertEquals(1L,advanced.get("fillCount"));
        assertEquals(2,((Map<?,?>)advanced.get("position")).get("lots"));
        verify(f.data).evaluate(argThat(r->r.workflow().equals(version.definition())&&r.bars().size()==1));
        var trace=f.jdbc.queryForObject("select node_trace::text from paper_trading.paper_strategy_decision where session_id=?",String.class,id);
        assertTrue(trace.contains("CANDIDATE"));assertEquals("first",advanced.get("workflowName"));
    }
    @Test void liveWorkflowSharesExistingDedupLedgerAndClosedQuoteGuard() {
        var version=publish(draft());when(f.data.live("JM0")).thenReturn(f.live("LIVE"));UUID id=f.id(f.service.createSession(request("LIVE",version.id())));
        f.service.advance(id,new AdvanceRequest(1));var again=f.service.advance(id,new AdvanceRequest(1));assertEquals(1L,again.get("orderCount"));assertEquals(1L,again.get("fillCount"));
        when(f.data.live("JM0")).thenReturn(f.live("CLOSED_CACHE"));assertEquals(1L,f.service.advance(id,new AdvanceRequest(1)).get("fillCount"));
    }
    @Test void backtestOverridesClientGraphAndRiskWithPublishedVersion() {
        var version=publish(draft());when(f.data.backtestWorkflow(any())).thenReturn(json.createObjectNode().put("totalTrades",0));
        var payload=json.createObjectNode().put("strategy","BUY_AND_HOLD").put("stopLossAtr",19);
        payload.set("workflowDefinition",json.createObjectNode().put("malicious","replacement"));
        var result=workflows.backtest(version.id(),payload);assertEquals(version.id().toString(),result.path("workflowVersionId").asText());
        verify(f.data).backtestWorkflow(argThat(r->"WORKFLOW".equals(r.path("strategy").asText())&&r.path("workflowDefinition").equals(graph)&&r.path("stopLossAtr").asInt()==2));
        assertEquals("BUY_AND_HOLD",payload.path("strategy").asText());
        assertThrows(IllegalArgumentException.class,()->f.service.createSession(request("HISTORICAL",null)));
    }
}
