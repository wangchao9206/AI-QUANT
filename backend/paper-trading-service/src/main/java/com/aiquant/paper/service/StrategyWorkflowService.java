package com.aiquant.paper.service;

import com.aiquant.paper.api.StrategyWorkflowController.*;
import com.aiquant.paper.client.SimulationDataClient;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class StrategyWorkflowService {
    private final JdbcTemplate jdbc;private final TransactionTemplate tx;private final SimulationDataClient data;
    private final StrategyWorkflowStore store;
    public StrategyWorkflowService(JdbcTemplate jdbc,TransactionTemplate tx,SimulationDataClient data){this.jdbc=jdbc;this.tx=tx;this.data=data;store=new StrategyWorkflowStore(jdbc);}
    private void basic(JsonNode definition){
        if(definition==null||!definition.isObject()||definition.path("schemaVersion").asInt()!=1
            ||!definition.path("nodes").isArray()||definition.path("nodes").size()>40
            ||!definition.path("edges").isArray()||definition.path("edges").size()>120||definition.toString().length()>128000)
            throw new IllegalArgumentException("草稿需使用版本1，最多40个节点和120条连线");
    }
    public Object list(){return jdbc.queryForList("""
        select w.id,w.name,w.description,w.revision,w.created_at as "createdAt",w.updated_at as "updatedAt",
            (select max(v.version) from paper_trading.strategy_workflow_version v where v.workflow_id=w.id) as "publishedVersion"
        from paper_trading.strategy_workflow w order by updated_at desc,id desc
        """);}
    public List<Map<String,Object>> published(){return jdbc.queryForList("""
        select id,workflow_id as "workflowId",version,name,engine_version as "engineVersion",required_bars as "requiredBars",
            lots,stop_loss_atr as "stopLossAtr",take_profit_atr as "takeProfitAtr",created_at as "createdAt"
        from paper_trading.strategy_workflow_version order by created_at desc,id desc limit 200
        """);}
    public StrategyWorkflowStore.Version version(UUID id){return store.version(id);}
    private Map<String,Object> row(UUID id,boolean lock){
        var rows=jdbc.queryForList("select * from paper_trading.strategy_workflow where id=?"+(lock?" for update":""),id);
        if(rows.isEmpty())throw new IllegalArgumentException("工作流不存在，请刷新列表");return rows.get(0);
    }
    public Map<String,Object> detail(UUID id){
        var r=row(id,false);var result=new LinkedHashMap<String,Object>();
        result.put("id",id);result.put("name",r.get("name"));result.put("description",r.get("description"));
        result.put("definition",StrategyWorkflowStore.json(r.get("definition")));result.put("revision",r.get("revision"));
        result.put("versions",store.versions(id));return result;
    }
    public Map<String,Object> create(CreateRequest r){
        basic(r.definition());String description=r.description()==null?"":r.description().strip();
        jdbc.update("insert into paper_trading.strategy_workflow(id,client_request_id,name,description,definition) values(?,?,?,?,?::jsonb) on conflict(client_request_id) do nothing",
            UUID.randomUUID(),r.clientRequestId(),r.name().strip(),description,r.definition().toString());
        UUID id=jdbc.queryForObject("select id from paper_trading.strategy_workflow where client_request_id=?",UUID.class,r.clientRequestId());
        var saved=row(id,false);
        if(!saved.get("name").equals(r.name().strip())||!saved.get("description").equals(description)||!StrategyWorkflowStore.json(saved.get("definition")).equals(r.definition()))
            throw new IllegalStateException("此请求编号已用于另一份草稿，请刷新后重试");
        return detail(id);
    }
    public Map<String,Object> save(UUID id,SaveRequest r){
        basic(r.definition());String description=r.description()==null?"":r.description().strip();
        int changed=jdbc.update("update paper_trading.strategy_workflow set name=?,description=?,definition=?::jsonb,revision=revision+1,updated_at=now() where id=? and revision=?",
            r.name().strip(),description,r.definition().toString(),id,r.expectedRevision());
        if(changed==0){
            var current=row(id,false);
            if(((Number)current.get("revision")).intValue()!=r.expectedRevision()+1||!current.get("name").equals(r.name().strip())
                ||!current.get("description").equals(description)||!StrategyWorkflowStore.json(current.get("definition")).equals(r.definition()))
                throw new IllegalStateException("草稿已被其他编辑更新，请刷新比对后保存；未覆盖服务器内容");
        }
        return detail(id);
    }
    public JsonNode validate(JsonNode definition){
        basic(definition);var response=data.validateWorkflow(definition);
        if(response==null||!response.path("definition").isObject()||!response.path("risk").isObject()
            ||!response.hasNonNull("requiredBars")||response.path("risk").path("lots").asInt()<1)
            throw new IllegalStateException("工作流校验服务响应不完整，请稍后重试");
        return response;
    }
    public StrategyWorkflowStore.Version publish(UUID id,PublishRequest r){
        var prior=store.prior(id,r.clientRequestId());
        if(prior!=null){if(prior.sourceRevision()!=r.expectedRevision())throw new IllegalStateException("发布编号已用于其他修订");return prior;}
        var draft=row(id,false);
        if(((Number)draft.get("revision")).intValue()!=r.expectedRevision())throw new IllegalStateException("草稿修订已变化，请先保存并刷新");
        JsonNode checked=validate(StrategyWorkflowStore.json(draft.get("definition"))); // Remote computation outside transaction.
        if(!StrategyWorkflowStore.ENGINE.equals(checked.path("engineVersion").asText()))throw new IllegalStateException("工作流引擎版本不匹配");
        UUID versionId=tx.execute(status->{
            var locked=row(id,true);var duplicate=store.prior(id,r.clientRequestId());
            if(duplicate!=null){if(duplicate.sourceRevision()!=r.expectedRevision())throw new IllegalStateException("发布编号已用于其他修订");return duplicate.id();}
            if(((Number)locked.get("revision")).intValue()!=r.expectedRevision())throw new IllegalStateException("发布期间草稿发生变化，请重新保存发布");
            int number=jdbc.queryForObject("select coalesce(max(version),0)+1 from paper_trading.strategy_workflow_version where workflow_id=?",Integer.class,id);
            UUID newId=UUID.randomUUID();var risk=checked.path("risk");
            jdbc.update("""
                insert into paper_trading.strategy_workflow_version
                (id,workflow_id,version,command_id,source_revision,name,definition,engine_version,required_bars,lots,stop_loss_atr,take_profit_atr)
                values(?,?,?,?,?,?,?::jsonb,?,?,?,?,?)
                """,newId,id,number,r.clientRequestId(),r.expectedRevision(),locked.get("name"),checked.path("definition").toString(),
                checked.path("engineVersion").asText(),checked.path("requiredBars").asInt(),risk.path("lots").asInt(),
                risk.path("stopLossAtr").decimalValue(),risk.path("takeProfitAtr").decimalValue());
            return newId;
        });
        return store.version(versionId);
    }
    public JsonNode debug(DebugRequest r){
        basic(r.definition());
        if(r.asOf().isAfter(Instant.now()))throw new IllegalArgumentException("不能使用未来时点试算");
        return data.debugWorkflow(r.definition(),r.symbol().toUpperCase(java.util.Locale.ROOT),r.asOf(),r.direction());
    }
    public JsonNode backtest(UUID id,JsonNode request){
        var version=store.executable(id);
        if(!request.isObject())throw new IllegalArgumentException("回测参数必须为对象");
        ObjectNode body=request.deepCopy();body.put("strategy","WORKFLOW");body.set("workflowDefinition",version.definition());
        body.put("stopLossAtr",version.stopLossAtr());body.put("takeProfitAtr",version.takeProfitAtr());
        var response=data.backtestWorkflow(body);
        if(response==null||!response.isObject())throw new IllegalStateException("回测服务响应不完整，请稍后重试");
        ObjectNode result=response.deepCopy();
        result.put("workflowVersionId",version.id().toString());result.put("workflowName",version.name());result.put("workflowVersion",version.version());
        result.put("workflowLots",version.lots());result.put("strategyName",version.name()+" · v"+version.version());
        return result;
    }
}
