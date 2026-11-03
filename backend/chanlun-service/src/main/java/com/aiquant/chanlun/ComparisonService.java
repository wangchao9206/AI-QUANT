package com.aiquant.chanlun;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.Semaphore;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ComparisonService {
    private final JdbcTemplate jdbc;private final ObjectMapper mapper;private final ChanlunService analysis;private final TransactionTemplate tx;private final Semaphore gate=new Semaphore(1);
    public ComparisonService(JdbcTemplate jdbc,ObjectMapper mapper,ChanlunService analysis,PlatformTransactionManager manager){this.jdbc=jdbc;this.mapper=mapper;this.analysis=analysis;this.tx=new TransactionTemplate(manager);}
    private JsonNode json(Object value){try{return mapper.readTree(value.toString());}catch(Exception e){throw new IllegalStateException("对照档案读取失败",e);}}
    private String encode(Object value){try{return mapper.writeValueAsString(value);}catch(Exception e){throw new IllegalStateException("对照档案保存失败",e);}}
    private static ResponseStatusException bad(String message){return new ResponseStatusException(HttpStatus.BAD_REQUEST,message);}
    private static ResponseStatusException conflict(String message){return new ResponseStatusException(HttpStatus.CONFLICT,message);}
    private Map<String,Object> row(UUID id){var rows=jdbc.queryForList("select * from chanlun.comparison where id=?",id);if(rows.isEmpty())throw new ResponseStatusException(HttpStatus.NOT_FOUND,"对照档案不存在");return rows.get(0);}
    private List<ObservationComparison.Source> sources(List<UUID> ids){
        var sources=new ArrayList<ObservationComparison.Source>();
        for(var id:ids)sources.add(new ObservationComparison.Source(id,analysis.result(id),jdbc.query("select payload::text from chanlun.structure_event where run_id=? order by event_seq",(rs,n)->json(rs.getString(1)),id)));
        return sources;
    }
    private List<UUID> members(Map<String,Object> row){var ids=new ArrayList<UUID>();json(row.get("request_payload")).path("runIds").forEach(id->ids.add(UUID.fromString(id.asText())));return ids;}
    public Object create(ComparisonController.Create request){
        var existing=jdbc.queryForList("select * from chanlun.comparison where client_request_id=?",request.clientRequestId());
        if(!existing.isEmpty()){same(existing.get(0),request);return get((UUID)existing.get(0).get("id"));}
        var sources=sources(request.runIds());
        try{ObservationComparison.validateSources(sources,request.layer(),request.confirmedOnly());}catch(IllegalArgumentException e){throw bad(e.getMessage());}
        if(!gate.tryAcquire())throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS,"对照分析忙，请稍后沿用原请求重试");
        UUID proposed=UUID.randomUUID();
        try{
            int inserted=jdbc.update("insert into chanlun.comparison(id,client_request_id,request_payload,status) values(?,?,?::jsonb,'RUNNING') on conflict(client_request_id) do nothing",proposed,request.clientRequestId(),encode(request));
            var r=jdbc.queryForMap("select * from chanlun.comparison where client_request_id=?",request.clientRequestId());same(r,request);UUID id=(UUID)r.get("id");
            if(inserted==0)return get(id);
            try{
                for(var source:sources)jdbc.update("insert into chanlun.comparison_member(comparison_id,run_id) values(?,?)",id,source.runId());
                var report=ObservationComparison.analyze(sources,request.layer(),request.projection(),request.confirmedOnly());
                jdbc.update("update chanlun.comparison set status='SUCCEEDED',result=?::jsonb,updated_at=now() where id=? and status='RUNNING'",encode(report),id);
            }catch(Exception e){org.slf4j.LoggerFactory.getLogger(ComparisonService.class).warn("Comparison {} failed: {}",id,e.getClass().getSimpleName());jdbc.update("update chanlun.comparison set status='FAILED',error='对照观察重建失败，请重新创建',updated_at=now() where id=? and status='RUNNING'",id);}
            return get(id);
        }finally{gate.release();}
    }
    private void same(Map<String,Object> r,Object request){if(!json(r.get("request_payload")).equals(mapper.valueToTree(request)))throw conflict("该请求编号已用于其他对照");}
    public Object list(){return jdbc.queryForList("select id,status,error,request_payload->>'layer' as layer,request_payload->>'projection' as projection,(result->>'observedBars')::int as \"observedBars\",created_at as \"createdAt\" from chanlun.comparison order by created_at desc,id desc limit 30");}
    public Object get(UUID id){var r=row(id);var out=new LinkedHashMap<String,Object>();out.put("id",id);out.put("status",r.get("status"));out.put("error",r.get("error"));out.put("request",json(r.get("request_payload")));out.put("report",r.get("result")==null?null:json(r.get("result")));out.put("createdAt",r.get("created_at").toString());return out;}
    private JsonNode report(Map<String,Object> r,int index){
        if(!"SUCCEEDED".equals(r.get("status")))throw conflict("对照尚未成功完成");
        var report=json(r.get("result"));if(!ObservationComparison.VERSION.equals(report.path("version").asText()))throw conflict("该对照协议版本暂不支持重新取证");
        if(index<0||index>=report.path("observedBars").asInt())throw bad("取证索引超出此对照观察界限");return report;
    }
    private ObjectNode prefix(ObservationComparison.Source source,int index){
        ObjectNode result=((ObjectNode)source.result()).deepCopy();var bars=mapper.createArrayNode();for(int i=0;i<=index;i++)bars.add(source.result().path("bars").get(i));
        String date=bars.get(index).path("date").asText();var structures=mapper.createArrayNode();var counts=new LinkedHashMap<String,Integer>();
        for(var original:ObservationComparison.stateAt(source,index).values()){
            ObjectNode s=((ObjectNode)original).deepCopy();s.remove(List.of("eventType","eventSeq","observedDate","recordedAt"));s.put("observedAsOfDate",date);structures.add(s);counts.merge(s.path("type").asText(),1,Integer::sum);
        }
        result.set("bars",bars);result.set("structures",structures);result.set("counts",mapper.valueToTree(counts));result.put("observedBars",index+1);result.put("observedAsOfDate",date);
        result.set("derivedFrom",mapper.valueToTree(Map.of("protocol","OBSERVATION_EVENTS_V1","sourceRunId",source.runId(),"observedIndex",index,"sourceRecordedAt",source.result().path("recordedAt").asText())));return result;
    }
    public Object at(UUID id,int index){
        var row=row(id);var report=report(row,index);var sources=sources(members(row));var frames=new ArrayList<Map<String,Object>>();var projections=new ArrayList<List<JsonNode>>();
        for(var source:sources){ObjectNode prefix=prefix(source,index);projections.add(ObservationComparison.projected(ObservationComparison.stateAt(source,index),report.path("layer").asText(),report.path("confirmedOnly").asBoolean()));frames.add(Map.of("sourceRunId",source.runId(),"analysis",prefix));}
        return Map.of("comparisonId",id,"observedIndex",index,"date",sources.get(0).result().path("bars").get(index).path("date").asText(),"frames",frames,"pairs",ObservationComparison.pairs(sources,projections).stream().map(ObservationComparison.Pair::witness).toList());
    }
    public Object events(UUID id,UUID sourceId,int index,String structureId){
        var r=row(id);report(r,index);if(!members(r).contains(sourceId))throw bad("来源不属于此对照");
        String date=analysis.result(sourceId).path("bars").get(index).path("date").asText();
        return jdbc.query("select payload::text from chanlun.structure_event where run_id=? and structure_id=? and payload->>'observedDate'<=? order by event_seq desc limit 100",(rs,n)->json(rs.getString(1)),sourceId,structureId,date);
    }
    private UUID materialize(ObservationComparison.Source source,int index){
        UUID id=UUID.nameUUIDFromBytes(("chan-observed-prefix-v1:"+source.runId()+":"+index).getBytes(StandardCharsets.UTF_8));
        ObjectNode prefix=prefix(source,index);prefix.put("runId",id.toString());prefix.put("recordedAt",Instant.now().toString());
        int inserted=jdbc.update("insert into chanlun.analysis_run(id,client_request_id,engine_id,dataset_id,observed_bars,status,result) values(?,?,?,?,?,'SUCCEEDED',?::jsonb) on conflict(id) do nothing",id,id,prefix.path("engineId").asText(),prefix.path("datasetId").asText(),index+1,encode(prefix));
        if(inserted>0){
            String date=prefix.path("observedAsOfDate").asText();var events=source.events().stream().filter(e->e.path("observedDate").asText().compareTo(date)<=0).toList();
            jdbc.batchUpdate("insert into chanlun.structure_event(run_id,event_seq,structure_id,payload) values(?,?,?,?::jsonb)",events,200,(ps,event)->{ps.setObject(1,id);ps.setInt(2,event.path("eventSeq").asInt());ps.setString(3,event.path("id").asText());ps.setString(4,encode(event));});
        }else{
            var saved=analysis.result(id);if(!saved.path("derivedFrom").path("sourceRunId").asText().equals(source.runId().toString())||saved.path("observedBars").asInt()!=index+1||!saved.path("profileHash").equals(source.result().path("profileHash")))throw conflict("派生前缀来源不一致");
        }
        return id;
    }
    public Object judge(UUID id,int index,ComparisonController.Judge request){
        var r=row(id);var report=report(r,index);if(!members(r).contains(request.sourceRunId()))throw bad("来源不属于此对照");
        var source=sources(List.of(request.sourceRunId())).get(0);
        return tx.execute(status->{
            UUID derived=materialize(source,index);
            return analysis.persistJudgment(new ChanlunController.JudgmentRequest(request.clientRequestId(),derived,request.structureId(),request.outlook(),request.content(),request.lessonNumber()),Map.of("comparisonId",id,"comparisonLayer",report.path("layer").asText(),"comparisonProjection",report.path("projection").asText(),"sourceRunId",request.sourceRunId(),"observedIndex",index));
        });
    }
    @Scheduled(fixedDelay=60000) public void expire(){jdbc.update("update chanlun.comparison set status='FAILED',error='对照计算中断或超时，请重新创建',updated_at=now() where status='RUNNING' and updated_at<now()-interval '3 minutes'");}
}
