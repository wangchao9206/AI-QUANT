package com.aiquant.paper.service;

import com.aiquant.paper.api.StrategyWorkflowController.MaTrendReplayRequest;
import com.aiquant.paper.service.ReplayReviewService.TrialIdentity;
import com.aiquant.paper.service.StrategyWorkflowStore.Version;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class WorkflowTrialService {
    public record CreateTrial(@NotNull UUID workflowVersionId, @NotBlank @Size(max=80) String name,
        @NotBlank @Pattern(regexp="FG701|SA701|AP701|CJ701") String symbol,
        @NotNull @DecimalMin("1000") @DecimalMax("100000000") @Digits(integer=9,fraction=2) BigDecimal initialCash,
        @Min(1) @Max(2) Integer costMultiplier, @NotNull UUID clientRequestId) {}

    public record Trial(UUID id, String name, UUID workflowVersionId, String symbol, BigDecimal initialCash,
        int costMultiplier, Instant createdAt) {}

    public record Detail(Trial trial, Version version, JsonNode replay) {}

    private record FrozenTrial(Trial trial, ObjectNode replay) {}

    private static final String TRIAL_COLUMNS = "id,trial_name,workflow_version_id,symbol,initial_cash,cost_multiplier,created_at";
    private static final RowMapper<Trial> TRIAL_ROW = (rs, row) -> new Trial(
        rs.getObject("id",UUID.class),rs.getString("trial_name"),rs.getObject("workflow_version_id",UUID.class),
        rs.getString("symbol"),rs.getBigDecimal("initial_cash"),rs.getInt("cost_multiplier"),rs.getTimestamp("created_at").toInstant());

    private final JdbcTemplate jdbc;
    private final StrategyWorkflowService workflows;

    public WorkflowTrialService(JdbcTemplate jdbc, StrategyWorkflowService workflows) {
        this.jdbc = jdbc;
        this.workflows = workflows;
    }

    public List<Trial> list(UUID owner) {
        return jdbc.query("select "+TRIAL_COLUMNS+" "+"""
             from paper_trading.paper_replay_review_run
             where owner_id=? and trial_name is not null order by created_at desc,id desc
             """,TRIAL_ROW,owner);
    }

    public Detail detail(UUID owner, UUID id) {
        var rows = jdbc.query("select "+TRIAL_COLUMNS+"""
            ,dataset_id,trial_summary,timeline,executions from paper_trading.paper_replay_review_run
            where owner_id=? and id=? and trial_name is not null
            """,(rs,index)->{
                var trial = TRIAL_ROW.mapRow(rs,index);
                var replay = (ObjectNode)StrategyWorkflowStore.json(rs.getObject("trial_summary"));
                replay.put("reviewRunId",trial.id().toString());
                replay.put("reviewDatasetId",rs.getString("dataset_id"));
                replay.set("reviewTimeline",StrategyWorkflowStore.json(rs.getObject("timeline")));
                replay.set("executions",StrategyWorkflowStore.json(rs.getObject("executions")));
                return new FrozenTrial(trial,replay);
            },owner,id);
        if (rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"找不到该历史试验。");
        var row = rows.get(0);
        var version = workflows.version(row.trial().workflowVersionId());
        row.replay().put("workflowVersionId",version.id().toString());
        row.replay().put("workflowName",version.name());
        row.replay().put("workflowVersion",version.version());
        return new Detail(row.trial(),version,row.replay());
    }

    public Detail create(UUID owner, CreateTrial request) {
        var prior = jdbc.query("""
            select id from paper_trading.paper_replay_review_run where owner_id=? and trial_request_id=?
            """,(rs,index)->rs.getObject("id",UUID.class),owner,request.clientRequestId());
        var name = request.name().strip();
        int cost = request.costMultiplier()==null ? 1 : request.costMultiplier();
        UUID id;
        if (prior.isEmpty()) {
            var replay = workflows.maTrendReplay(request.workflowVersionId(),
                new MaTrendReplayRequest(request.symbol(),request.initialCash(),cost,true),owner,
                new TrialIdentity(request.clientRequestId(),name));
            id = UUID.fromString(replay.path("reviewRunId").asText());
        } else {
            id = prior.get(0);
        }
        var saved = detail(owner,id);
        var trial = saved.trial();
        if (!trial.name().equals(name) || !trial.workflowVersionId().equals(request.workflowVersionId())
            || !trial.symbol().equals(request.symbol()) || trial.initialCash().compareTo(request.initialCash())!=0
            || trial.costMultiplier()!=cost) {
            throw new ResponseStatusException(HttpStatus.CONFLICT,"该历史试验请求已用于不同设置，请重新发起创建。");
        }
        return saved;
    }
}
