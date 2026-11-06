package com.aiquant.paper.service;

import com.aiquant.paper.client.SimulationDataClient;
import com.aiquant.paper.client.SimulationDataClient.SimulationDataset;
import com.aiquant.tenancy.TenantContext;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.Instant;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

/** Append-only historical observations. Reading a saved observation never reruns it. */
@Service
public class WorkflowShadowService {
    private final JdbcTemplate db;
    private final SimulationDataClient data;
    public WorkflowShadowService(JdbcTemplate db,SimulationDataClient data){this.db=db;this.data=data;}
    static ResponseStatusException conflict(String message){return new ResponseStatusException(HttpStatus.CONFLICT,message);}
    static String canonicalSymbol(String value){return value.toUpperCase(Locale.ROOT).replaceFirst("0$","M");}
    static ObjectNode result(Map<String,Object> row){
        ObjectNode value=StrategyWorkflowStore.json(row.get("result")).deepCopy();
        value.put("id",row.get("id").toString());value.put("workflowVersionId",row.get("workflow_version_id").toString());
        value.put("symbol",row.get("symbol").toString());value.put("recordedAt",((java.sql.Timestamp)row.get("created_at")).toInstant().toString());
        return value;
    }
    public ObjectNode get(UUID id){
        var rows=db.queryForList("select * from paper_trading.workflow_shadow where id=? and tenant_id=?",id,TenantContext.currentOrLegacy());
        if(rows.isEmpty())throw new ResponseStatusException(HttpStatus.NOT_FOUND,"观察记录不属于当前工作空间。");
        return result(rows.get(0));
    }
    public List<JsonNode> list(UUID version){
        new StrategyWorkflowStore(db).version(version);
        return db.queryForList("select * from paper_trading.workflow_shadow where workflow_version_id=? and tenant_id=? order by created_at desc limit 30",version,TenantContext.currentOrLegacy())
            .stream().map(r->{var item=result(r);item.remove("inputSnapshot");return (JsonNode)item;}).toList();
    }
    public ObjectNode create(UUID versionId,UUID command,String symbol,Instant asOf,int direction){
        if(asOf.isAfter(Instant.now())||direction < -1||direction>1)throw new IllegalArgumentException("观察时点或假设持仓无效");
        asOf=asOf.truncatedTo(java.time.temporal.ChronoUnit.MICROS);
        String normalized=canonicalSymbol(symbol);
        var previous=db.queryForList("select * from paper_trading.workflow_shadow where tenant_id=? and client_request_id=?",TenantContext.currentOrLegacy(),command);
        if(!previous.isEmpty())return repeated(previous.get(0),versionId,normalized,asOf,direction);
        var version=new StrategyWorkflowStore(db).executable(versionId);
        if(!StrategyWorkflowStore.CHAN_ENGINE.equals(version.engineVersion()))throw new IllegalArgumentException("此观察归档用于版本2缠论工作流");
        var observed=data.debugWorkflow(version.definition(),normalized,asOf,direction);
        if(observed==null||!version.engineVersion().equals(observed.path("modelVersion").asText())
            ||!observed.path("inputSnapshot").path("signalBars").isArray()||!observed.path("inputHash").asText().matches("[a-f0-9]{64}"))
            throw new IllegalStateException("观察结果缺少冻结输入和版本依据");
        ObjectNode frozen=observed.deepCopy();frozen.put("direction",direction);frozen.set("workflowDefinition",version.definition());
        if(frozen.toString().length()>4000000)throw new IllegalArgumentException("观察输入超出归档上限");
        db.update("insert into paper_trading.workflow_shadow(id,tenant_id,client_request_id,workflow_version_id,symbol,as_of,direction,result) values(?,?,?,?,?,?,?,?::jsonb) on conflict(tenant_id,client_request_id) do nothing",
            UUID.randomUUID(),TenantContext.currentOrLegacy(),command,versionId,normalized,java.sql.Timestamp.from(asOf),direction,frozen.toString());
        var saved=db.queryForMap("select * from paper_trading.workflow_shadow where tenant_id=? and client_request_id=?",TenantContext.currentOrLegacy(),command);
        return repeated(saved,versionId,normalized,asOf,direction);
    }
    static ObjectNode repeated(Map<String,Object> row,UUID version,String symbol,Instant asOf,int direction){
        if(!version.equals(row.get("workflow_version_id"))||!symbol.equals(row.get("symbol"))
            ||!asOf.equals(((java.sql.Timestamp)row.get("as_of")).toInstant())||direction!=((Number)row.get("direction")).intValue())
            throw conflict("此请求编号已用于另一份观察，原记录未覆盖。");
        return result(row);
    }
    public ObjectNode forSession(UUID id,StrategyWorkflowStore.Version version,String symbol,String mode){
        if(!StrategyWorkflowStore.CHAN_ENGINE.equals(version.engineVersion())){
            if(id!=null)throw new IllegalArgumentException("普通工作流不使用缠论观察记录");return null;
        }
        if(!"HISTORICAL".equals(mode))throw new IllegalArgumentException("缠论工作流目前仅支持历史模拟，请勿用于实时账户");
        if(id==null)throw new IllegalArgumentException("请先归档该发布版本的空仓观察，再创建模拟账户");
        var shadow=get(id);
        if(!version.id().toString().equals(shadow.path("workflowVersionId").asText())||!canonicalSymbol(symbol).equals(shadow.path("symbol").asText())
            ||shadow.path("direction").asInt()!=0||shadow.path("historyCount").asInt()<50||shadow.path("signalTime").isNull()
            ||!version.definition().equals(shadow.path("workflowDefinition")))throw conflict("观察版本、品种、空仓状态或已知日线不足，请重新观察。");
        return shadow;
    }
    public static void verifyInput(JsonNode shadow,SimulationDataset dataset){
        if(shadow==null)return;
        Instant observed=Instant.parse(shadow.path("signalTime").asText());
        if(dataset.bars().get(0).timestamp().isBefore(observed))throw conflict("模拟起点不能早于观察记录已展开的日线。");
        verifySeries(shadow.path("inputSnapshot").path("signalBars"),dataset.signalBars());
        verifySeries(shadow.path("inputSnapshot").path("executionBars"),dataset.contextBars());
    }
    static void verifySeries(JsonNode rows,List<SimulationDataClient.HistoricalBar> series){
        var available=new HashMap<Instant,SimulationDataClient.HistoricalBar>();
        if(series!=null)for(var bar:series)available.put(bar.timestamp(),bar);
        for(var frozen:rows){
            var bar=available.get(Instant.parse(frozen.path("timestamp").asText()));
            if(bar==null||bar.volume()!=frozen.path("volume").asLong())throw conflict("观察输入与回放数据不一致，请重新观察。");
            if(!Objects.equals(bar.contract(),frozen.path("contract").isNull()?null:frozen.path("contract").asText()))throw conflict("观察合约与回放数据不一致，请重新观察。");
            for(String key:List.of("open","high","low","close")){
                var value=switch(key){case "open"->bar.open();case "high"->bar.high();case "low"->bar.low();default->bar.close();};
                if(value.setScale(6,java.math.RoundingMode.HALF_UP).compareTo(frozen.path(key).decimalValue().setScale(6,java.math.RoundingMode.HALF_UP))!=0)throw conflict("观察价格已修订，请重新观察，旧档案保持可读。");
            }
        }
    }
}
