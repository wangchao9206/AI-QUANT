package com.aiquant.chanlun;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.net.http.HttpClient;
import java.time.*;
import java.util.*;
import java.util.concurrent.Semaphore;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/chanlun/v1/multiframe")
public class MultiframeController {
    public record Request(@NotNull UUID clientRequestId,@NotNull @Pattern(regexp="[A-Z]{1,4}[0-9]{3,4}") String symbol,
                          @NotNull @Pattern(regexp="PAIR|TRIPLE") String frames,OffsetDateTime asOf) {}
    private final JdbcTemplate jdbc;private final ObjectMapper mapper;private final RestClient client;private final String algorithm;
    private final Semaphore gate=new Semaphore(1);
    public MultiframeController(JdbcTemplate jdbc,ObjectMapper mapper,@Value("${chanlun.algorithm-url:http://algorithm-service:8000}") String algorithm) {
        this.jdbc=jdbc;this.mapper=mapper;this.algorithm=algorithm;
        var factory=new JdkClientHttpRequestFactory(HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build());factory.setReadTimeout(Duration.ofSeconds(90));client=RestClient.builder().requestFactory(factory).build();
    }
    private JsonNode json(Object value){try{return mapper.readTree(value.toString());}catch(Exception e){throw new IllegalStateException("多周期结果读取失败",e);}}
    private String encode(Object value){try{return mapper.writeValueAsString(value);}catch(Exception e){throw new IllegalStateException("多周期结果保存失败",e);}}
    @GetMapping public Object list(){return jdbc.queryForList("select id,status,error,request_payload->>'symbol' as symbol,request_payload->>'frames' as frames,created_at as \"createdAt\" from chanlun.multiframe_run order by created_at desc,id desc limit 30");}
    @GetMapping("/{id}") public Object get(@PathVariable UUID id){
        var rows=jdbc.queryForList("select * from chanlun.multiframe_run where id=?",id);if(rows.isEmpty())throw new ResponseStatusException(HttpStatus.NOT_FOUND,"多周期观察不存在");
        var r=rows.get(0);var out=new LinkedHashMap<String,Object>();out.put("id",id);out.put("status",r.get("status"));out.put("error",r.get("error"));out.put("request",json(r.get("request_payload")));out.put("report",r.get("result")==null?null:json(r.get("result")));out.put("createdAt",r.get("created_at").toString());return out;
    }
    @PostMapping public Object create(@Valid @RequestBody Request request){
        if(request.asOf()!=null&&request.asOf().toInstant().isAfter(Instant.now()))throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"观察界限不能晚于当前时间");
        UUID id=UUID.randomUUID();jdbc.update("insert into chanlun.multiframe_run(id,client_request_id,request_payload,status) values(?,?,?::jsonb,'QUEUED') on conflict(client_request_id) do nothing",id,request.clientRequestId(),encode(request));
        var r=jdbc.queryForMap("select * from chanlun.multiframe_run where client_request_id=?",request.clientRequestId());id=(UUID)r.get("id");
        if(!json(r.get("request_payload")).equals(mapper.valueToTree(request)))throw new ResponseStatusException(HttpStatus.CONFLICT,"该请求编号已用于其他多周期观察");
        if(!Set.of("QUEUED","WAITING_INPUT").contains(r.get("status")))return get(id);
        if(!gate.tryAcquire())return get(id);
        try{
            if(jdbc.update("update chanlun.multiframe_run set status='RUNNING',updated_at=now() where id=? and status in ('QUEUED','WAITING_INPUT')",id)==0)return get(id);
            var body=new LinkedHashMap<String,Object>();body.put("symbol",request.symbol());body.put("frames",request.frames());body.put("asOf",request.asOf()==null?null:request.asOf().toString());
            JsonNode response=client.post().uri(algorithm+"/internal/v1/chanlun/multiframe").body(body).retrieve().body(JsonNode.class);
            if("WAITING_INPUT".equals(response.path("status").asText()))jdbc.update("update chanlun.multiframe_run set status='WAITING_INPUT',error=?,updated_at=now() where id=? and status='RUNNING'",response.path("message").asText().substring(0,Math.min(390,response.path("message").asText().length())),id);
            else{
                JsonNode report=response.path("report");validate(report,request);
                jdbc.update("update chanlun.multiframe_run set status='SUCCEEDED',result=?::jsonb,error=null,updated_at=now() where id=? and status='RUNNING'",encode(report),id);
            }
        }catch(Exception e){org.slf4j.LoggerFactory.getLogger(MultiframeController.class).warn("Multiframe {} failed: {}",id,e.getClass().getSimpleName());jdbc.update("update chanlun.multiframe_run set status='FAILED',error='多周期输入或重建核验失败，请检查来源与时点后重新创建',updated_at=now() where id=? and status='RUNNING'",id);}
        finally{gate.release();}return get(id);
    }
    static void validate(JsonNode report,Request request){
        int expected=request.frames().equals("PAIR")?2:3;
        if(report.path("executable").asBoolean(true)||!request.symbol().equals(report.at("/config/symbol").asText())||report.path("frames").size()!=expected||!report.path("configHash").asText().matches("[a-f0-9]{64}"))throw new IllegalStateException("Invalid multiframe report");
        Instant cutoff=OffsetDateTime.parse(report.path("asOf").asText()).toInstant(),captured=OffsetDateTime.parse(report.path("capturedAt").asText()).toInstant();
        if(cutoff.isAfter(captured)||(request.asOf()!=null&&!cutoff.equals(request.asOf().toInstant())))throw new IllegalStateException("Changed multiframe cutoff");
        var frequencies=new HashSet<String>();
        for(var frame:report.path("frames")){
            frequencies.add(frame.path("frequency").asText());JsonNode a=frame.path("analysis");int count=a.path("observedBars").asInt();
            if(count<50||count!=a.path("bars").size()||!request.symbol().equals(a.path("symbol").asText())||!frame.path("frequency").asText().equals(a.path("frequency").asText())||!"UNADJUSTED_DELIVERY".equals(a.path("priceBasis").asText())||a.path("executable").asBoolean(true)||!a.path("profileHash").asText().matches("[a-f0-9]{64}")||!a.path("inputHash").asText().matches("[a-f0-9]{64}"))throw new IllegalStateException("Inconsistent multiframe input");
            for(int i=0;i<count;i++){var b=a.path("bars").get(i);if(b.path("index").asInt(-1)!=i||OffsetDateTime.parse(b.path("sealedByTimestamp").asText()).toInstant().isAfter(cutoff))throw new IllegalStateException("Future multiframe candle");}
            for(var s:a.path("structures"))if(s.path("endIndex").asInt()>=count||s.path("observedIndex").asInt(-1)>=count)throw new IllegalStateException("Future multiframe structure");
        }
        if(!frequencies.equals(expected==2?Set.of("MIN5","MIN30"):Set.of("DAY","MIN30","MIN5")))throw new IllegalStateException("Missing independent timeframe");
    }
    @Scheduled(fixedDelay=60000) public void expire(){jdbc.update("update chanlun.multiframe_run set status='FAILED',error='重建中断或等待输入超时，请重新创建',updated_at=now() where status in ('QUEUED','RUNNING','WAITING_INPUT') and updated_at<now()-interval '3 minutes'");}
}
