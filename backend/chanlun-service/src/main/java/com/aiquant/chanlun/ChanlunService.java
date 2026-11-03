package com.aiquant.chanlun;

import com.aiquant.chanlun.ChanlunController.*;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.*;
import java.util.concurrent.Semaphore;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.scheduling.annotation.Scheduled;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Service
public class ChanlunService {
    private static final Logger log=LoggerFactory.getLogger(ChanlunService.class);
    private static final String DATASET_HASH="f069d8c21ec41d106f4b21c90f9e04d4d285d00847c8f551ff11991e38768577";
    private final JdbcTemplate jdbc;
    private final WorkerClient workers;
    private final ObjectMapper mapper;
    private final TransactionTemplate transactions;
    private final Semaphore capacity=new Semaphore(3);
    public ChanlunService(JdbcTemplate jdbc,WorkerClient workers,ObjectMapper mapper,PlatformTransactionManager manager) {
        this.jdbc=jdbc;this.workers=workers;this.mapper=mapper;this.transactions=new TransactionTemplate(manager);
    }
    private JsonNode json(String value) {
        try { return mapper.readTree(value); } catch(Exception e) { throw new IllegalStateException("结果读取失败",e); }
    }
    private String encode(Object value) {
        try { return mapper.writeValueAsString(value); } catch(Exception e) { throw new IllegalStateException("结果保存失败",e); }
    }
    public List<Map<String,Object>> engines() {
        var list=new ArrayList<Map<String,Object>>();
        for(String id:List.of("native","chanpy","czsc","baseline")) {
            boolean available=false;
            try { var health=workers.health(id);available=id.equals(health.path("engine").asText())&&"UP".equals(health.path("status").asText()); }
            catch(Exception ignored) { /* No fallback to another engine. */ }
            list.add(Map.of("id",id,"name",switch(id){case "native"->"AI-QUANT 自研引擎";case "chanpy"->"chan.py";case "czsc"->"CZSC";default->"AI-QUANT 研究基线";},
                "status",available?"AVAILABLE":"UNAVAILABLE","layers",id.equals("native")?List.of("FRACTAL","BI","SEGMENT","ZONE","BSP"):id.equals("czsc")?List.of("BI","ZONE"):List.of("BI","SEGMENT","ZONE")));
        }
        return list;
    }
    public Object datasets() {
        for(String id:List.of("native","chanpy","czsc","baseline"))try{return List.of(workers.health(id).path("dataset"));}catch(Exception ignored){}
        throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"缠论计算服务暂时不可用");
    }
    public Object create(RunRequest request) {
        jdbc.update("insert into chanlun.analysis_run(id,client_request_id,engine_id,dataset_id,observed_bars,status) values(?,?,?,?,?,'QUEUED') on conflict(client_request_id) do nothing",
            UUID.randomUUID(),request.clientRequestId(),request.engineId(),request.datasetId(),request.observedBars());
        var row=jdbc.queryForMap("select * from chanlun.analysis_run where client_request_id=?",request.clientRequestId());
        if(!row.get("engine_id").equals(request.engineId())||!row.get("dataset_id").equals(request.datasetId())||((Number)row.get("observed_bars")).intValue()!=request.observedBars())
            throw new ResponseStatusException(HttpStatus.CONFLICT,"该请求编号已用于其他分析");
        UUID id=(UUID)row.get("id");
        if(!"QUEUED".equals(row.get("status")))return run(id);
        if(!capacity.tryAcquire())throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS,"计算任务较多，请稍后重试");
        try {
            if(jdbc.update("update chanlun.analysis_run set status='RUNNING',updated_at=now() where id=? and status='QUEUED'",id)==0)return run(id);
            JsonNode result=workers.analyze(request.engineId(),request.datasetId(),request.observedBars());
            validateResult(result,request);
            List<JsonNode> events=new ArrayList<>();result.path("events").forEach(events::add);
            ObjectNode stored=((ObjectNode)result).deepCopy();stored.remove("events");stored.put("runId",id.toString());
            transactions.executeWithoutResult(status->{
                jdbc.batchUpdate("insert into chanlun.structure_event(run_id,event_seq,structure_id,payload) values(?,?,?,?::jsonb)",events,200,(ps,event)->{
                    ps.setObject(1,id);ps.setInt(2,event.path("eventSeq").asInt());ps.setString(3,event.path("id").asText());ps.setString(4,encode(event));
                });
                jdbc.update("update chanlun.analysis_run set status='SUCCEEDED',result=?::jsonb,updated_at=now() where id=?",encode(stored),id);
            });
        } catch(Exception failure) {
            log.error("Chan analysis {} failed",id,failure);
            jdbc.update("update chanlun.analysis_run set status='FAILED',error=?,updated_at=now() where id=?","结构计算或保存失败，请检查引擎状态后重新分析",id);
        } finally { capacity.release(); }
        return run(id);
    }
    static void validateResult(JsonNode result,RunRequest request) {
        if(result==null||!result.isObject()||!request.engineId().equals(result.path("engineId").asText())
            ||!DATASET_HASH.equals(result.path("datasetHash").asText())||result.path("observedBars").asInt()!=request.observedBars()
            ||result.path("bars").size()!=request.observedBars()||result.path("executable").asBoolean(true)
            ||!result.path("events").isArray()||!result.path("structures").isArray())throw new IllegalStateException("Invalid worker result");
        for(var structure:result.path("structures"))if(structure.path("endIndex").asInt()>=request.observedBars())throw new IllegalStateException("Future structure");
    }
    public List<Map<String,Object>> runs() {
        return jdbc.queryForList("select id,engine_id as \"engineId\",observed_bars as \"observedBars\",status,created_at as \"createdAt\" from chanlun.analysis_run order by created_at desc,id desc limit 30");
    }
    public Map<String,Object> run(UUID id) {
        var rows=jdbc.queryForList("select id,engine_id as \"engineId\",observed_bars as \"observedBars\",status,error,created_at as \"createdAt\" from chanlun.analysis_run where id=?",id);
        if(rows.isEmpty())throw new ResponseStatusException(HttpStatus.NOT_FOUND,"分析记录不存在");
        return rows.get(0);
    }
    public JsonNode result(UUID id) {
        var summary=run(id);
        if(!"SUCCEEDED".equals(summary.get("status")))throw new ResponseStatusException(HttpStatus.CONFLICT,"分析尚未成功完成，请刷新任务状态");
        return json(jdbc.queryForObject("select result::text from chanlun.analysis_run where id=?",String.class,id));
    }
    public Object events(UUID id,String structureId) {
        run(id);
        if(!structureId.matches("[a-f0-9]{24}"))throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"结构编号无效");
        return jdbc.query("select payload::text from chanlun.structure_event where run_id=? and structure_id=? order by event_seq desc limit 100",
            (rs,n)->json(rs.getString(1)),id,structureId);
    }
    public Object judge(JudgmentRequest request) {
        return persistJudgment(request,Map.of());
    }
    Object persistJudgment(JudgmentRequest request,Map<String,Object> extraEvidence) {
        JsonNode evidence=result(request.runId());
        if(request.structureId()!=null) {
            boolean found=false;for(var structure:evidence.path("structures"))if(request.structureId().equals(structure.path("id").asText()))found=true;
            if(!found)throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"该结构不属于此分析时点");
        }
        var context=new LinkedHashMap<String,Object>(Map.of("runId",request.runId(),"profileHash",evidence.path("profileHash").asText(),
            "datasetHash",evidence.path("datasetHash").asText(),"observedAsOfDate",evidence.path("observedAsOfDate").asText(),
            "engineId",evidence.path("engineId").asText()));
        if(request.lessonNumber()!=null)context.put("lessonNumber",request.lessonNumber());
        context.putAll(extraEvidence);
        String content=request.content().strip();
        jdbc.update("insert into chanlun.judgment(id,client_request_id,run_id,structure_id,outlook,content,evidence) values(?,?,?,?,?,?,?::jsonb) on conflict(client_request_id) do nothing",
            UUID.randomUUID(),request.clientRequestId(),request.runId(),request.structureId(),request.outlook(),content,encode(context));
        var saved=jdbc.queryForMap("select * from chanlun.judgment where client_request_id=?",request.clientRequestId());
        var savedEvidence=json(saved.get("evidence").toString());
        if(!saved.get("run_id").equals(request.runId())||!Objects.equals(saved.get("structure_id"),request.structureId())
            ||!saved.get("outlook").equals(request.outlook())||!saved.get("content").equals(content)
            ||!savedEvidence.equals(mapper.valueToTree(context)))throw new ResponseStatusException(HttpStatus.CONFLICT,"该保存请求已用于其他判断");
        return Map.of("id",saved.get("id"),"createdAt",saved.get("created_at").toString());
    }
    public Object judgments() {
        return jdbc.query("select id,run_id,structure_id,outlook,content,evidence::text,created_at from chanlun.judgment order by created_at desc,id desc limit 50",
            (rs,n)->{var row=new LinkedHashMap<String,Object>();row.put("id",rs.getObject("id"));row.put("runId",rs.getObject("run_id"));
                row.put("structureId",rs.getString("structure_id"));row.put("outlook",rs.getString("outlook"));row.put("content",rs.getString("content"));
                row.put("evidence",json(rs.getString("evidence")));row.put("createdAt",rs.getTimestamp("created_at").toInstant());return row;});
    }
    @Scheduled(fixedDelay=60000)
    public void expireInterruptedRuns() {
        jdbc.update("update chanlun.analysis_run set status='FAILED',error='计算中断或超时，请重新分析',updated_at=now() where status='RUNNING' and updated_at<now()-interval '3 minutes'");
    }
}
