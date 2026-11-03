package com.aiquant.chanlun;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.net.http.HttpClient;
import java.time.Duration;
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
import org.slf4j.LoggerFactory;

@RestController
@RequestMapping("/api/chanlun/v1/lab")
public class LabController {
    public record Request(@NotNull UUID clientRequestId,@NotNull @Pattern(regexp="THIRD|ALL") String group,
                          @Min(100000) @Max(1000000) int initialCash) {}
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private final RestClient client;
    private final String algorithm;
    private final Semaphore capacity=new Semaphore(1);
    public LabController(JdbcTemplate jdbc,ObjectMapper mapper,@Value("${chanlun.algorithm-url:http://algorithm-service:8000}") String algorithm) {
        this.jdbc=jdbc;this.mapper=mapper;this.algorithm=algorithm;
        var factory=new JdkClientHttpRequestFactory(HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build());
        factory.setReadTimeout(Duration.ofSeconds(90));client=RestClient.builder().requestFactory(factory).build();
    }
    private JsonNode json(String value) {
        try{return mapper.readTree(value);}catch(Exception e){throw new IllegalStateException("实验结果读取失败",e);}
    }
    private String encode(Object value) {
        try{return mapper.writeValueAsString(value);}catch(Exception e){throw new IllegalStateException("实验结果保存失败",e);}
    }
    @GetMapping public Object recent() {
        return jdbc.queryForList("select id,status,error,request_payload->>'group' as \"group\",(request_payload->>'initialCash')::int as \"initialCash\",created_at as \"createdAt\" from chanlun.lab_experiment order by created_at desc,id desc limit 30");
    }
    @GetMapping("/{id}") public Object get(@PathVariable UUID id) {
        var rows=jdbc.queryForList("select * from chanlun.lab_experiment where id=?",id);
        if(rows.isEmpty())throw new ResponseStatusException(HttpStatus.NOT_FOUND,"实验记录不存在");
        var row=rows.get(0);var out=new LinkedHashMap<String,Object>();
        out.put("id",id);out.put("status",row.get("status"));out.put("error",row.get("error"));
        out.put("createdAt",row.get("created_at").toString());
        out.put("request",json(row.get("request_payload").toString()));
        out.put("report",row.get("result")==null?null:json(row.get("result").toString()));return out;
    }
    @PostMapping public Object create(@Valid @RequestBody Request request) {
        if(!Set.of(100000,500000,1000000).contains(request.initialCash()))throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"请选择固定初始资金");
        UUID id=UUID.randomUUID();
        int inserted=jdbc.update("insert into chanlun.lab_experiment(id,client_request_id,request_payload,status) values(?,?,?::jsonb,'RUNNING') on conflict(client_request_id) do nothing",id,request.clientRequestId(),encode(request));
        var row=jdbc.queryForMap("select id,request_payload::text from chanlun.lab_experiment where client_request_id=?",request.clientRequestId());
        if(!json(row.get("request_payload").toString()).equals(mapper.valueToTree(request)))throw new ResponseStatusException(HttpStatus.CONFLICT,"该请求编号已用于其他实验");
        if(inserted==0)return get((UUID)row.get("id"));
        if(!capacity.tryAcquire()) {
            jdbc.update("update chanlun.lab_experiment set status='FAILED',error='研究计算忙，请重新发起实验',updated_at=now() where id=?",id);
            return get(id);
        }
        try {
            var report=client.post().uri(algorithm+"/internal/v1/chanlun/lab")
                .body(Map.of("group",request.group(),"initialCash",request.initialCash())).retrieve().body(JsonNode.class);
            validate(report,request);
            jdbc.update("update chanlun.lab_experiment set status='SUCCEEDED',result=?::jsonb,updated_at=now() where id=? and status='RUNNING'",encode(report),id);
        } catch(Exception e) {
            LoggerFactory.getLogger(LabController.class).error("Chan lab {} failed",id,e);
            jdbc.update("update chanlun.lab_experiment set status='FAILED',error='实验计算或核验失败，请查看服务状态后重试',updated_at=now() where id=? and status='RUNNING'",id);
        } finally {capacity.release();}
        return get(id);
    }
    static void validate(JsonNode report,Request request) {
        if(report==null||report.path("executable").asBoolean(true)||!"native-chan-cost-lab-v1".equals(report.path("engineVersion").asText())
            ||!request.group().equals(report.at("/config/group").asText())||request.initialCash()!=report.at("/config/initialCash").asInt()
            ||!"f069d8c21ec41d106f4b21c90f9e04d4d285d00847c8f551ff11991e38768577".equals(report.at("/config/datasetHash").asText())
            ||!report.path("configHash").asText().matches("[a-f0-9]{64}")||report.path("variants").size()!=5)throw new IllegalStateException("Invalid research report");
        var ids=new HashSet<String>();
        for(var variant:report.path("variants")) {
            ids.add(variant.path("id").asText());double pnl=variant.at("/metrics/netPnl").asDouble(Double.NaN),sum=0;
            for(var trade:variant.path("trades"))sum+=trade.path("netPnl").asDouble(Double.NaN);
            double equity=variant.at("/metrics/finalEquity").asDouble(Double.NaN);
            if(!Double.isFinite(pnl)||!Double.isFinite(sum)||!Double.isFinite(equity)||Math.abs(pnl-sum)>0.00001
                ||Math.abs(equity-request.initialCash()-pnl)>0.00001)throw new IllegalStateException("Unreconciled cash ledger");
        }
        if(!ids.equals(Set.of("NATIVE_BASE","NATIVE_DOUBLE_COST","NATIVE_DELAY_ONE","RANGE_RETEST","CHANNEL_BREAKOUT")))throw new IllegalStateException("Missing comparison");
    }
    @Scheduled(fixedDelay=60000) public void expire() {
        jdbc.update("update chanlun.lab_experiment set status='FAILED',error='实验计算中断或超时，请重新发起',updated_at=now() where status='RUNNING' and updated_at<now()-interval '3 minutes'");
    }
}
