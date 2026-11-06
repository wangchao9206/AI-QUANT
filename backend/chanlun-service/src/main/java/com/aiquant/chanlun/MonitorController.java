package com.aiquant.chanlun;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
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
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;
import org.slf4j.LoggerFactory;

@RestController
@RequestMapping("/api/chanlun/v1/monitors")
public class MonitorController {
    public record Create(@NotNull UUID clientRequestId,@NotBlank @Size(max=120) String title,
        @NotNull @Pattern(regexp="[A-Z]{1,4}[0-9]{3,4}") String symbol,
        @NotNull @Pattern(regexp="DAY|MIN5|MIN30") String frequency) {}
    public record Control(boolean enabled) {}
    public record Review(@NotNull UUID clientRequestId,@NotNull @Pattern(regexp="UP|DOWN|WAIT") String outlook,
        @NotBlank @Size(max=6000) String content,@Min(1) @Max(108) Integer lessonNumber) {}
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private final TransactionTemplate tx;
    private final RestClient client;
    private final String algorithm;
    private final Semaphore gate=new Semaphore(1);
    public MonitorController(JdbcTemplate jdbc,ObjectMapper mapper,PlatformTransactionManager manager,
                             @Value("${chanlun.algorithm-url:http://algorithm-service:8000}") String algorithm) {
        this.jdbc=jdbc;this.mapper=mapper;this.tx=new TransactionTemplate(manager);this.algorithm=algorithm;
        var factory=new JdkClientHttpRequestFactory(HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build());
        factory.setReadTimeout(Duration.ofSeconds(90));client=RestClient.builder().requestFactory(factory).build();
    }
    private JsonNode json(Object value) {try{return mapper.readTree(value.toString());}catch(Exception e){throw new IllegalStateException("监控记录读取失败",e);}}
    private String encode(Object value) {try{return mapper.writeValueAsString(value);}catch(Exception e){throw new IllegalStateException("监控记录保存失败",e);}}
    private static ResponseStatusException conflict(String message){return new ResponseStatusException(HttpStatus.CONFLICT,message);}
    private Map<String,Object> row(UUID id) {
        var rows=jdbc.queryForList("select * from chanlun.monitor where id=?",id);
        if(rows.isEmpty())throw new ResponseStatusException(HttpStatus.NOT_FOUND,"监控任务不存在");return rows.get(0);
    }
    @PostMapping public Object create(@Valid @RequestBody Create request) {
        UUID id=tx.execute(status->{
            jdbc.execute("select pg_advisory_xact_lock(82402214)");
            var previous=jdbc.queryForList("select id,request_payload from chanlun.monitor where client_request_id=?",request.clientRequestId());
            if(!previous.isEmpty()) {
                if(!json(previous.get(0).get("request_payload")).equals(mapper.valueToTree(request)))throw conflict("该编号已用于其他监控任务");
                return (UUID)previous.get(0).get("id");
            }
            if(jdbc.queryForObject("select count(*) from chanlun.monitor where enabled",Integer.class)>=8)throw conflict("同时启用的监控最多八个，请先暂停任务");
            UUID created=UUID.randomUUID();
            jdbc.update("insert into chanlun.monitor(id,client_request_id,request_payload,title,symbol,frequency) values(?,?,?::jsonb,?,?,?)",created,request.clientRequestId(),encode(request),request.title().strip(),request.symbol(),request.frequency());
            return created;
        });
        return view(id);
    }
    @GetMapping public Object list() {
        return jdbc.queryForList("select id,title,symbol,frequency,enabled,status,observed_bars as \"observedBars\",heartbeat_at as \"heartbeatAt\",last_error as error,profile_hash as \"profileHash\",created_at as \"createdAt\" from chanlun.monitor order by created_at desc,id desc limit 100");
    }
    @GetMapping("/{id}") public Object view(@PathVariable UUID id) {
        // Read head and fallback snapshot in one statement: a concurrent publish
        // cannot mix an old pointer with newer metadata or a missing head.
        var rows=jdbc.queryForList("select m.*,coalesce(m.latest_analysis,s.analysis) as current_analysis from chanlun.monitor m left join chanlun.monitor_snapshot s on s.id=m.latest_snapshot_id where m.id=?",id);
        if(rows.isEmpty())throw new ResponseStatusException(HttpStatus.NOT_FOUND,"监控任务不存在");
        var r=rows.get(0);var out=new LinkedHashMap<String,Object>();
        for(String key:List.of("id","title","symbol","frequency","enabled","status"))out.put(key,r.get(key));
        out.put("observedBars",r.get("observed_bars"));out.put("heartbeatAt",r.get("heartbeat_at"));out.put("error",r.get("last_error"));out.put("profileHash",r.get("profile_hash"));
        out.put("source",r.get("source")==null?null:json(r.get("source")));
        out.put("analysis",r.get("current_analysis")==null?null:json(r.get("current_analysis")));
        // A new publish may commit after reading the head. Keep this response's
        // event list within that captured head, rather than exposing newer bars.
        out.put("events",jdbc.query("select event_seq,payload::text,inbox_state,detected_at from chanlun.monitor_event where monitor_id=? and event_seq<=? order by event_seq desc limit 100",(rs,n)->Map.of("eventSeq",rs.getInt(1),"payload",json(rs.getString(2)),"inboxState",rs.getString(3),"detectedAt",rs.getTimestamp(4).toInstant()),id,r.get("last_event_seq")));
        return out;
    }
    @PostMapping("/{id}/control") public Object control(@PathVariable UUID id,@RequestBody Control control) {
        tx.executeWithoutResult(status->{
            jdbc.execute("select pg_advisory_xact_lock(82402214)");var r=row(id);
            if(control.enabled()&&Set.of("VERSION_CHANGED","INPUT_REVISED","GAP","LIMIT_REACHED").contains(r.get("status")))throw conflict("此任务需保留原证据，请核查后新建监控");
            if(control.enabled()&&!Boolean.TRUE.equals(r.get("enabled"))&&jdbc.queryForObject("select count(*) from chanlun.monitor where enabled",Integer.class)>=8)throw conflict("同时启用的监控最多八个");
            jdbc.update("update chanlun.monitor set enabled=?,status=?,next_check_at=now(),lease_id=null,lease_until=null,updated_at=now() where id=?",control.enabled(),control.enabled()?"WAITING_DATA":"PAUSED",id);
        });return view(id);
    }
    @PostMapping("/{id}/check") public Object check(@PathVariable UUID id) {row(id);poll(id);return view(id);}
    @PostMapping("/{id}/events/{seq}/ack") public Object acknowledge(@PathVariable UUID id,@PathVariable @Min(1) int seq) {
        row(id);jdbc.update("update chanlun.monitor_event set inbox_state='ACKNOWLEDGED' where monitor_id=? and event_seq=? and inbox_state='NEW'",id,seq);return view(id);
    }
    @GetMapping("/{id}/events/{seq}") public Object evidence(@PathVariable UUID id,@PathVariable @Min(1) int seq) {
        var rows=jdbc.queryForList("select e.payload,e.detected_at,s.analysis,s.source from chanlun.monitor_event e join chanlun.monitor_snapshot s on s.id=e.snapshot_id where e.monitor_id=? and e.event_seq=?",id,seq);
        if(rows.isEmpty())throw new ResponseStatusException(HttpStatus.NOT_FOUND,"监控事件不存在");
        var r=rows.get(0);JsonNode event=json(r.get("payload")),full=json(r.get("analysis"));int count=event.path("observedIndex").asInt(-1)+1;
        if(count<1||count>full.path("bars").size())throw new IllegalStateException("Invalid frozen event prefix");
        ObjectNode prefix=((ObjectNode)full).deepCopy();var bars=mapper.createArrayNode();for(int i=0;i<count;i++)bars.add(full.path("bars").get(i));
        prefix.set("bars",bars);prefix.put("observedBars",count);prefix.put("observedAsOfDate",bars.get(count-1).path("timestamp").asText());prefix.remove("inputHash");prefix.remove("lastEventSeq");
        prefix.set("structures",mapper.createArrayNode().add(event));
        return Map.of("event",event,"analysis",prefix,"detectedAt",r.get("detected_at").toString(),"source",json(r.get("source")),"viewScope","EVENT_CANDIDATE_ONLY");
    }
    @PostMapping("/{id}/events/{seq}/reviews") public Object review(@PathVariable UUID id,@PathVariable @Min(1) int seq,@Valid @RequestBody Review request) {
        Object context=evidence(id,seq);
        jdbc.update("insert into chanlun.monitor_review(id,client_request_id,monitor_id,event_seq,outlook,content,lesson_number,evidence) values(?,?,?,?,?,?,?,?::jsonb) on conflict(client_request_id) do nothing",UUID.randomUUID(),request.clientRequestId(),id,seq,request.outlook(),request.content().strip(),request.lessonNumber(),encode(context));
        var r=jdbc.queryForMap("select * from chanlun.monitor_review where client_request_id=?",request.clientRequestId());
        if(!r.get("monitor_id").equals(id)||((Number)r.get("event_seq")).intValue()!=seq||!r.get("outlook").equals(request.outlook())||!r.get("content").equals(request.content().strip())||!Objects.equals(r.get("lesson_number"),request.lessonNumber()))throw conflict("该保存编号已用于其他复盘");
        return Map.of("id",r.get("id"),"createdAt",r.get("created_at").toString());
    }
    @GetMapping("/reviews") public Object reviews() {
        return jdbc.query("select id,monitor_id,event_seq,outlook,content,lesson_number,evidence::text,created_at from chanlun.monitor_review order by created_at desc,id desc limit 100",(rs,n)->{
            var r=new LinkedHashMap<String,Object>();r.put("id",rs.getObject(1));r.put("monitorId",rs.getObject(2));r.put("eventSeq",rs.getInt(3));r.put("outlook",rs.getString(4));r.put("content",rs.getString(5));r.put("lessonNumber",rs.getObject(6));r.put("evidence",json(rs.getString(7)));r.put("createdAt",rs.getTimestamp(8).toInstant());return r;});
    }
    @Scheduled(fixedDelay=15000) public void scheduled() {
        for(var r:jdbc.queryForList("select id,tenant_id from chanlun.monitor where enabled and next_check_at<=now() and (lease_until is null or lease_until<now()) order by next_check_at limit 8"))
            com.aiquant.tenancy.TenantTransactions.run(jdbc,tx,(UUID)r.get("tenant_id"),()->{poll((UUID)r.get("id"));return null;});
    }
    private void poll(UUID id) {
        if(!gate.tryAcquire())return;
        UUID lease=UUID.randomUUID();
        try {
            if(jdbc.update("update chanlun.monitor set lease_id=?,lease_until=now()+interval '2 minutes',heartbeat_at=now() where id=? and enabled and (lease_until is null or lease_until<now())",lease,id)==0)return;
            var r=row(id);var request=new LinkedHashMap<String,Object>();request.put("symbol",r.get("symbol"));request.put("frequency",r.get("frequency"));request.put("previousBars",json(r.get("bars")));request.put("previousProfileHash",r.get("profile_hash"));
            JsonNode result=client.post().uri(algorithm+"/internal/v1/chanlun/monitor").body(request).retrieve().body(JsonNode.class);
            tx.executeWithoutResult(status->apply(id,lease,r,result));
        }catch(Exception e) {
            LoggerFactory.getLogger(MonitorController.class).warn("Chan monitor {} check failed: {}",id,e.getClass().getSimpleName());
            jdbc.update("update chanlun.monitor set status='ERROR',last_error='监控调用失败，保留原水位并等待重试',heartbeat_at=now(),next_check_at=now()+interval '30 seconds',lease_id=null,lease_until=null where id=? and lease_id=?",id,lease);
        }finally {gate.release();}
    }
    private void apply(UUID id,UUID lease,Map<String,Object> previous,JsonNode result) {
        var locked=jdbc.queryForMap("select * from chanlun.monitor where id=? for update",id);
        if(!lease.equals(locked.get("lease_id"))||!Boolean.TRUE.equals(locked.get("enabled")))return;
        String state=result.path("status").asText();
        if(!Set.of("READY","CLOSED","WAITING_DATA","DISCONNECTED","STALE","INPUT_REVISED","GAP","LIMIT_REACHED").contains(state))throw new IllegalStateException("Invalid monitor source state");
        boolean fatal=Set.of("INPUT_REVISED","GAP","LIMIT_REACHED").contains(state);
        JsonNode source=result.path("source");
        if(result.path("unchanged").asBoolean()) {
            if(!Objects.equals(previous.get("profile_hash"),result.path("profileHash").asText()))throw new IllegalStateException("Unchanged profile mismatch");
        } else if(result.has("analysis")) {
            JsonNode analysis=result.path("analysis");validate(analysis,previous);
            JsonNode oldBars=json(previous.get("bars"));
            if(oldBars.size()>analysis.path("bars").size())throw new IllegalStateException("Regressing monitor input");
            for(int i=0;i<oldBars.size();i++)if(!oldBars.get(i).equals(analysis.path("bars").get(i)))throw new IllegalStateException("Revised sealed monitor input");
            String profile=analysis.path("profileHash").asText();
            if(previous.get("profile_hash")!=null&&!profile.equals(previous.get("profile_hash"))) {state="VERSION_CHANGED";fatal=true;}
            else {
                ObjectNode stored=((ObjectNode)analysis).deepCopy();stored.remove("events");
                var newEvents=new ArrayList<JsonNode>();
                for(var event:analysis.path("events"))if(event.path("eventSeq").asInt()>((Number)previous.get("last_event_seq")).intValue())newEvents.add(event);
                UUID snapshot=(UUID)previous.get("latest_snapshot_id");
                if(!newEvents.isEmpty()) {
                    UUID proposed=UUID.randomUUID();
                    jdbc.update("insert into chanlun.monitor_snapshot(id,monitor_id,input_hash,profile_hash,analysis,source) values(?,?,?,?,?::jsonb,?::jsonb) on conflict(monitor_id,input_hash,profile_hash) do nothing",proposed,id,analysis.path("inputHash").asText(),profile,encode(stored),encode(source));
                    snapshot=jdbc.queryForObject("select id from chanlun.monitor_snapshot where monitor_id=? and input_hash=? and profile_hash=?",UUID.class,id,analysis.path("inputHash").asText(),profile);
                }
                for(var event:newEvents) {
                    String inbox=inboxState(event,analysis,"READY".equals(state),((Number)previous.get("observed_bars")).intValue(),Instant.now());
                    jdbc.update("insert into chanlun.monitor_event(monitor_id,event_seq,structure_id,snapshot_id,payload,inbox_state) values(?,?,?,?,?::jsonb,?) on conflict(monitor_id,event_seq) do nothing",id,event.path("eventSeq").asInt(),event.path("id").asText(),snapshot,encode(event),inbox);
                }
                jdbc.update("update chanlun.monitor set profile_hash=?,bars=?::jsonb,observed_bars=?,last_event_seq=?,latest_snapshot_id=?,latest_analysis=?::jsonb where id=?",profile,encode(analysis.path("bars")),analysis.path("observedBars").asInt(),analysis.path("lastEventSeq").asInt(),snapshot,encode(stored),id);
            }
        }
        jdbc.update("update chanlun.monitor set status=?,enabled=?,source=?::jsonb,last_error=?,heartbeat_at=now(),next_check_at=now()+interval '30 seconds',lease_id=null,lease_until=null,updated_at=now() where id=?",state.equals("READY")?"ACTIVE":state,!fatal,encode(source),fatal?"输入或版本变化，已暂停并保留原证据":result.path("message").asText(),id);
    }
    static void validate(JsonNode analysis,Map<String,Object> previous) {
        int count=analysis.path("observedBars").asInt();
        if(!"native".equals(analysis.path("engineId").asText())||analysis.path("executable").asBoolean(true)||count<50||count>10000||count!=analysis.path("bars").size()
            ||!previous.get("symbol").equals(analysis.path("symbol").asText())||!previous.get("frequency").equals(analysis.path("frequency").asText())||!analysis.path("profileHash").asText().matches("[a-f0-9]{64}")||!analysis.path("inputHash").asText().matches("[a-f0-9]{64}"))throw new IllegalStateException("Invalid monitor analysis");
        for(int i=0;i<count;i++)if(analysis.path("bars").get(i).path("index").asInt(-1)!=i)throw new IllegalStateException("Invalid monitor index");
        for(var e:analysis.path("events"))if(!"BSP".equals(e.path("type").asText())||e.path("observedIndex").asInt(-1)<e.path("endIndex").asInt()||e.path("observedIndex").asInt()>=count)throw new IllegalStateException("Future monitor event");
    }
    static String inboxState(JsonNode event,JsonNode analysis,boolean ready,int previousCount,Instant now) {
        if(previousCount==0)return "SUPPRESSED_BOOTSTRAP";
        if(!ready)return "SUPPRESSED_CLOSED";
        if("DAY".equals(analysis.path("frequency").asText()))return "SUPPRESSED_BACKFILL"; // daily availability mapping is not qualified for fresh alerts
        int observed=event.path("observedIndex").asInt();
        Instant bar=OffsetDateTime.parse(analysis.path("bars").get(observed).path("timestamp").asText()).toInstant();
        long period=switch(analysis.path("frequency").asText()){case "MIN5"->300;case "MIN30"->1800;default->16*3600;};
        long lag=Duration.between(bar.plusSeconds(period),now).getSeconds();
        if(observed<previousCount||lag>120||lag<0)return "SUPPRESSED_BACKFILL";
        return "NEW";
    }
}
