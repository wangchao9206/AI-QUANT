package com.aiquant.paper.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

/** Immutable published configurations shared by the editor and paper ledger. */
public final class StrategyWorkflowStore {
    public static final String ENGINE="workflow-daily-v1";
    private static final ObjectMapper JSON=new ObjectMapper();
    private final JdbcTemplate jdbc;
    public StrategyWorkflowStore(JdbcTemplate jdbc){this.jdbc=jdbc;}
    public record Version(UUID id,UUID workflowId,int version,int sourceRevision,String name,JsonNode definition,
        String engineVersion,int requiredBars,int lots,BigDecimal stopLossAtr,BigDecimal takeProfitAtr,Instant createdAt) {}
    private static final RowMapper<Version> VERSION=(rs,n)->new Version(rs.getObject("id",UUID.class),
        rs.getObject("workflow_id",UUID.class),rs.getInt("version"),rs.getInt("source_revision"),rs.getString("name"),json(rs.getObject("definition")),
        rs.getString("engine_version"),rs.getInt("required_bars"),rs.getInt("lots"),rs.getBigDecimal("stop_loss_atr"),rs.getBigDecimal("take_profit_atr"),rs.getTimestamp("created_at").toInstant());
    public static JsonNode json(Object value){
        if(value==null)return JSON.nullNode();if(value instanceof JsonNode node)return node;
        if(value instanceof java.util.Collection<?>||value instanceof java.util.Map<?,?>)return JSON.valueToTree(value);
        try{return JSON.readTree(value.toString());}catch(Exception error){throw new IllegalStateException("工作流配置读取失败，请刷新重试");}
    }
    public Version version(UUID id){
        var rows=jdbc.query("select * from paper_trading.strategy_workflow_version where id=?",VERSION,id);
        if(rows.isEmpty())throw new IllegalArgumentException("已发布的工作流版本不存在");return rows.get(0);
    }
    public Version executable(UUID id){
        Version version=version(id);
        if(!ENGINE.equals(version.engineVersion()))throw new IllegalStateException("此工作流引擎版本当前只读，请另行发布新版本");
        return version;
    }
    public List<Version> versions(UUID workflowId){
        return jdbc.query("select * from paper_trading.strategy_workflow_version where workflow_id=? order by version desc",VERSION,workflowId);
    }
    public Version prior(UUID workflowId,String command){
        var rows=jdbc.query("select * from paper_trading.strategy_workflow_version where workflow_id=? and command_id=?",VERSION,workflowId,command);
        return rows.isEmpty()?null:rows.get(0);
    }
    public static JsonNode snapshot(Version version){
        var node=JSON.createObjectNode();node.put("versionId",version.id().toString());node.put("name",version.name());
        node.put("version",version.version());node.put("engineVersion",version.engineVersion());node.set("definition",version.definition());return node;
    }
}
