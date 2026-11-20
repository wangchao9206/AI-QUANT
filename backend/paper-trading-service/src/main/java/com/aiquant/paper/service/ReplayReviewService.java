package com.aiquant.paper.service;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ReplayReviewService {
    public enum Stage { BAR, FILL }
    public enum SuggestedAction { WAIT, OPEN_LONG, OPEN_SHORT, ADD, CLOSE, REDUCE }

    public record SaveReview(@NotNull UUID clientRequestId, @NotNull Instant at, @NotNull Stage stage,
        @Size(max=36) String targetId, @NotNull SuggestedAction suggestedAction, @NotBlank @Size(max=2000) String reason,
        UUID reviewRunId) {}

    public record Review(UUID id, Instant at, Stage stage, String targetId, String observedAction,
        SuggestedAction suggestedAction, String reason, Instant createdAt, JsonNode evidence, UUID workflowId) {}

    private record Anchor(String observedAction, JsonNode evidence) {}
    private record Saved(UUID sessionId, UUID runId, Review review) {}
    record TrialIdentity(UUID requestId, String name) {}
    private static final String NOTE_COLUMNS = "id,market_time,stage,target_id,observed_action,suggested_action,reason,created_at,evidence";
    private static final int REVIEW_LIMIT = 500;
    private final JdbcTemplate jdbc;

    public ReplayReviewService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public UUID registerRun(UUID owner, UUID versionId, String symbol, BigDecimal initialCash, int costMultiplier,
        JsonNode replay) {
        return registerRun(owner,versionId,symbol,initialCash,costMultiplier,replay,null);
    }

    UUID registerRun(UUID owner, UUID versionId, String symbol, BigDecimal initialCash, int costMultiplier,
        JsonNode replay, TrialIdentity trial) {
        String dataset = replay.path("reviewDatasetId").asText();
        JsonNode timeline = replay.path("reviewTimeline");
        JsonNode executions = replay.path("executions");
        if (!dataset.matches("[a-f0-9]{64}") || !timeline.isArray() || timeline.isEmpty() || timeline.size()>2000
            || !executions.isArray() || executions.size()>4000) {
            throw new IllegalStateException("历史模拟未返回可冻结的复盘记录");
        }
        String timelineJson = timeline.toString();
        String executionJson = executions.toString();
        if (timelineJson.length()+executionJson.length()>2_000_000) {
            throw new IllegalStateException("历史模拟复盘记录超过保存上限");
        }
        String runFingerprint = dataset+"\n"+timelineJson+"\n"+executionJson;
        if (trial!=null) {
            var summary = trialSummary(replay);
            String fingerprint = digest(trial.requestId()+"\n"+runFingerprint);
            jdbc.update("""
                insert into paper_trading.paper_replay_review_run
                    (id,owner_id,workflow_version_id,snapshot_hash,dataset_id,symbol,initial_cash,cost_multiplier,
                     timeline,executions,trial_name,trial_request_id,trial_summary)
                values(?,?,?,?,?,?,?,?,?::jsonb,?::jsonb,?,?,?::jsonb)
                on conflict (tenant_id,owner_id,trial_request_id) do nothing
                """,UUID.randomUUID(),owner,versionId,fingerprint,dataset,symbol,initialCash,costMultiplier,timelineJson,executionJson,
                trial.name(),trial.requestId(),summary);
            return jdbc.queryForObject("""
                select id from paper_trading.paper_replay_review_run where owner_id=? and trial_request_id=?
                """,UUID.class,owner,trial.requestId());
        }
        String fingerprint = digest(runFingerprint);
        jdbc.update("""
            insert into paper_trading.paper_replay_review_run
                (id,owner_id,workflow_version_id,snapshot_hash,dataset_id,symbol,initial_cash,cost_multiplier,timeline,executions)
            values(?,?,?,?,?,?,?,?,?::jsonb,?::jsonb)
            on conflict (tenant_id,owner_id,workflow_version_id,symbol,initial_cash,cost_multiplier,snapshot_hash) do nothing
            """,UUID.randomUUID(),owner,versionId,fingerprint,dataset,symbol,initialCash,costMultiplier,timelineJson,executionJson);
        return jdbc.queryForObject("""
            select id from paper_trading.paper_replay_review_run
            where owner_id=? and workflow_version_id=? and symbol=? and initial_cash=? and cost_multiplier=? and snapshot_hash=?
            """,UUID.class,owner,versionId,symbol,initialCash,costMultiplier,fingerprint);
    }

    private static String trialSummary(JsonNode replay) {
        var scope = replay.path("scope");
        var metrics = replay.path("metrics");
        var assumptions = replay.path("assumptions");
        if (!scope.isObject() || !metrics.isObject() || !assumptions.isArray()) {
            throw new IllegalStateException("历史试验缺少可保存的区间、结果或成交说明");
        }
        String summary = StrategyWorkflowStore.json(Map.of("scope",scope,"metrics",metrics,"assumptions",assumptions)).toString();
        if (summary.length()>65_536) throw new IllegalStateException("历史试验摘要超过保存上限");
        return summary;
    }

    public List<Review> sessionNotes(UUID session, UUID owner) {
        var row = paperSession(session,owner);
        return list("session_id",session,owner,workflowId((UUID)row.get("workflow_version_id")));
    }

    public Review saveSessionNote(UUID session, UUID owner, SaveReview request) {
        if (request.reviewRunId()!=null) throw badRequest("账户复盘不接受工作流回放编号");
        validateNote(request);
        var row = paperSession(session,owner);
        UUID workflow = workflowId((UUID)row.get("workflow_version_id"));
        var prior = prior(owner,request.clientRequestId(),workflow);
        if (prior!=null) return assertRepeat(prior,session,null,request);
        Instant visibleThrough = ((Timestamp)row.get("current_market_time")).toInstant();
        if (request.at().isAfter(visibleThrough)) throw badRequest("该时点的行情尚未在当前回放显示");
        var anchor = request.stage()==Stage.FILL ? paperFill(session,request) : paperBar(session,row,request,visibleThrough);
        return insert(session,null,owner,workflow,request,anchor);
    }

    public List<Review> runNotes(UUID version, UUID run, UUID owner) {
        requireRun(version,run,owner);
        return list("run_id",run,owner,workflowId(version));
    }

    public Review saveRunNote(UUID version, UUID owner, SaveReview request) {
        validateNote(request);
        UUID run = request.reviewRunId();
        requireRun(version,run,owner);
        UUID workflow = workflowId(version);
        var prior = prior(owner,request.clientRequestId(),workflow);
        if (prior!=null) return assertRepeat(prior,null,run,request);
        var snapshot = jdbc.queryForMap("""
            select timeline,executions,symbol,dataset_id,initial_cash,cost_multiplier from paper_trading.paper_replay_review_run
            where id=? and workflow_version_id=? and owner_id=?
            """,run,version,owner);
        JsonNode bar = findBar(StrategyWorkflowStore.json(snapshot.get("timeline")),request.at());
        var evidence = new LinkedHashMap<String,Object>();
        evidence.put("bar",bar);
        evidence.put("symbol",snapshot.get("symbol"));
        evidence.put("datasetId",snapshot.get("dataset_id"));
        evidence.put("initialCash",snapshot.get("initial_cash"));
        evidence.put("costMultiplier",snapshot.get("cost_multiplier"));
        evidence.put("workflowVersionId",version);
        String action = action(bar.path("signal").asText());
        if (request.stage()==Stage.FILL) {
            int index = fillIndex(request.targetId());
            boolean observedOnBar = false;
            for (JsonNode item : bar.path("executionIndexes")) {
                if (item.isIntegralNumber() && item.asInt()==index) {
                    observedOnBar = true;
                    break;
                }
            }
            JsonNode fill = StrategyWorkflowStore.json(snapshot.get("executions")).path(index);
            if (!observedOnBar || !fill.isObject()) throw badRequest("该成交不属于所选回放时点");
            evidence.put("fill",fill);
            action = action(fill.path("action").asText());
        }
        return insert(null,run,owner,workflow,request,new Anchor(action,StrategyWorkflowStore.json(evidence)));
    }

    private Map<String,Object> paperSession(UUID session, UUID owner) {
        var records = jdbc.queryForList("""
            select mode,symbol,strategy_id,workflow_version_id,current_market_time,current_bar_index,current_contract,
                current_price,equity from paper_trading.paper_session where id=? and owner_id=?
            """,session,owner);
        if (records.isEmpty()) throw notFound("模拟账户不存在");
        var row = records.get(0);
        if (!"HISTORICAL".equals(row.get("mode"))) throw badRequest("实时模拟账户没有历史复盘标注");
        return row;
    }

    private Anchor paperBar(UUID session, Map<String,Object> sessionRow, SaveReview request, Instant visibleThrough) {
        if (!request.at().equals(visibleThrough)) throw badRequest("回放时点已变化，请在当前 K 线重新添加标注");
        var records = jdbc.queryForList("""
            select b.open_price as open,b.high_price as high,b.low_price as low,b.close_price as close,b.volume,b.contract
            from paper_trading.paper_scenario_bar b where b.session_id=? and b.bar_index=?
            """,session,sessionRow.get("current_bar_index"));
        if (records.isEmpty()) throw badRequest("当前回放 K 线不可用");
        var evidence = new LinkedHashMap<String,Object>(records.get(0));
        evidence.put("at",request.at().toString());
        evidence.put("symbol",sessionRow.get("symbol"));
        evidence.put("strategyId",sessionRow.get("strategy_id"));
        evidence.put("equity",sessionRow.get("equity"));
        evidence.put("workflowVersionId",sessionRow.get("workflow_version_id"));
        var decision = jdbc.queryForList("""
            select signal,reason,model_version as "modelVersion" from paper_trading.paper_strategy_decision
            where session_id=? and signal_time=?
            """,session,Timestamp.from(request.at()));
        String action = "NO_ACTION";
        if (!decision.isEmpty()) {
            evidence.put("decision",decision.get(0));
            action = action(decision.get(0).get("signal").toString());
        }
        return new Anchor(action,StrategyWorkflowStore.json(evidence));
    }

    private Anchor paperFill(UUID session, SaveReview request) {
        UUID fill;
        try { fill = UUID.fromString(request.targetId()); }
        catch (IllegalArgumentException invalid) { throw badRequest("成交编号无效"); }
        if (!fill.toString().equals(request.targetId())) throw badRequest("成交编号无效");
        var records = jdbc.queryForList("""
            select contract,side,offset_type as "offsetType",quantity,fill_price as price,fee,reason,event_type as "eventType"
            from paper_trading.paper_fill where session_id=? and id=? and market_time=?
            """,session,fill,Timestamp.from(request.at()));
        if (records.isEmpty()) throw notFound("成交记录不存在或不属于所选回放时点");
        var evidence = new LinkedHashMap<String,Object>(records.get(0));
        evidence.put("at",request.at().toString());
        String action = "OPEN".equals(evidence.get("offsetType"))
            ? ("BUY".equals(evidence.get("side")) ? "OPEN_LONG" : "OPEN_SHORT") : "CLOSE";
        return new Anchor(action,StrategyWorkflowStore.json(evidence));
    }

    private void requireRun(UUID version, UUID run, UUID owner) {
        if (run==null) throw badRequest("缺少历史回放编号");
        if (jdbc.queryForObject("""
            select exists (select 1 from paper_trading.paper_replay_review_run
                where id=? and workflow_version_id=? and owner_id=?)
            """,Boolean.class,run,version,owner)!=Boolean.TRUE) throw notFound("历史回放不存在");
    }

    private static JsonNode findBar(JsonNode timeline, Instant requestedAt) {
        for (JsonNode bar : timeline) {
            if (Instant.parse(bar.path("at").asText()).equals(requestedAt)) return bar;
        }
        throw badRequest("所选时点不在此次已核验的历史回放中");
    }

    private static int fillIndex(String target) {
        if (!target.matches("0|[1-9][0-9]{0,3}")) throw badRequest("成交索引无效");
        return Integer.parseInt(target);
    }

    private static String action(String value) {
        return value.matches("[A-Z_]{1,32}") ? value : "NO_ACTION";
    }

    private static void validateNote(SaveReview request) {
        if (request.clientRequestId()==null || request.at()==null || request.stage()==null || request.suggestedAction()==null
            || request.reason()==null || request.reason().isBlank() || request.reason().length()>2000
            || (request.stage()==Stage.FILL) != (request.targetId()!=null && !request.targetId().isBlank())
            || (request.stage()==Stage.BAR && request.targetId()!=null)) {
            throw badRequest("请填写复盘时点、建议动作和原因");
        }
    }

    private UUID workflowId(UUID version) {
        if (version==null) return null;
        return jdbc.query("select workflow_id from paper_trading.strategy_workflow_version where id=?",
            (row,index)->row.getObject("workflow_id",UUID.class),version).stream().findFirst().orElse(null);
    }

    private List<Review> list(String scopeColumn, UUID scope, UUID owner, UUID workflow) {
        return jdbc.query("select "+NOTE_COLUMNS+" from paper_trading.paper_replay_review where "+ scopeColumn
            +"=? and owner_id=? order by market_time desc,created_at desc,id desc limit ?",(row,index)->map(row,workflow),
            scope,owner,REVIEW_LIMIT);
    }

    private Review insert(UUID session, UUID run, UUID owner, UUID workflow, SaveReview request, Anchor anchor) {
        jdbc.update("""
            insert into paper_trading.paper_replay_review
                (id,owner_id,client_request_id,session_id,run_id,market_time,stage,target_id,observed_action,suggested_action,reason,evidence)
            values (?,?,?,?,?,?,?,?,?,?,?,?::jsonb) on conflict (tenant_id,owner_id,client_request_id) do nothing
            """,UUID.randomUUID(),owner,request.clientRequestId(),session,run,Timestamp.from(request.at()),request.stage().name(),
            request.targetId(),anchor.observedAction(),request.suggestedAction().name(),request.reason().strip(),anchor.evidence().toString());
        return assertRepeat(prior(owner,request.clientRequestId(),workflow),session,run,request);
    }

    private Saved prior(UUID owner, UUID command, UUID workflow) {
        return jdbc.query("select session_id,run_id,"+NOTE_COLUMNS+" from paper_trading.paper_replay_review where owner_id=? and client_request_id=?",
            (row,index)->new Saved(row.getObject("session_id",UUID.class),row.getObject("run_id",UUID.class),map(row,workflow)),
            owner,command).stream().findFirst().orElse(null);
    }

    private static Review assertRepeat(Saved saved, UUID session, UUID run, SaveReview request) {
        if (saved==null) throw new IllegalStateException("复盘标注未能保存");
        var note = saved.review();
        if (!Objects.equals(saved.sessionId(),session) || !Objects.equals(saved.runId(),run)
            || !note.at().equals(request.at()) || note.stage()!=request.stage() || !Objects.equals(note.targetId(),request.targetId())
            || note.suggestedAction()!=request.suggestedAction() || !note.reason().equals(request.reason().strip())) {
            throw new ResponseStatusException(HttpStatus.CONFLICT,"此标注请求已经用于另一条复盘记录");
        }
        return note;
    }

    private static Review map(java.sql.ResultSet row, UUID workflow) throws java.sql.SQLException {
        return new Review(row.getObject("id",UUID.class),row.getTimestamp("market_time").toInstant(),
            Stage.valueOf(row.getString("stage")),row.getString("target_id"),row.getString("observed_action"),
            SuggestedAction.valueOf(row.getString("suggested_action")),row.getString("reason"),row.getTimestamp("created_at").toInstant(),
            StrategyWorkflowStore.json(row.getObject("evidence")),workflow);
    }

    private static String digest(String source) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(source.getBytes(StandardCharsets.UTF_8))); }
        catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }

    private static ResponseStatusException badRequest(String message) { return new ResponseStatusException(HttpStatus.BAD_REQUEST,message); }
    private static ResponseStatusException notFound(String message) { return new ResponseStatusException(HttpStatus.NOT_FOUND,message); }
}
