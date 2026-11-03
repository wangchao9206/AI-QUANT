package com.aiquant.chanlun;

import com.aiquant.chanlun.ChanlunController.JudgmentRequest;
import com.aiquant.chanlun.ChanlunController.RunRequest;
import com.aiquant.chanlun.ReplayController.*;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ReplayService {
    private final JdbcTemplate jdbc;
    private final ChanlunService analysis;
    private final ObjectMapper mapper;
    private final TransactionTemplate tx;
    public ReplayService(JdbcTemplate jdbc,ChanlunService analysis,ObjectMapper mapper,PlatformTransactionManager manager) {
        this.jdbc=jdbc;this.analysis=analysis;this.mapper=mapper;this.tx=new TransactionTemplate(manager);
    }
    private JsonNode json(String value) {
        try {return mapper.readTree(value);}catch(Exception e){throw new IllegalStateException("练习记录读取失败",e);}
    }
    private String encode(Object value) {
        try{return mapper.writeValueAsString(value);}catch(Exception e){throw new IllegalStateException("练习记录保存失败",e);}
    }
    private static ResponseStatusException conflict(String message) { return new ResponseStatusException(HttpStatus.CONFLICT,message); }
    private Map<String,Object> session(UUID id,boolean lock) {
        var rows=jdbc.queryForList("select * from chanlun.replay_session where id=?"+(lock?" for update":""),id);
        if(rows.isEmpty())throw new ResponseStatusException(HttpStatus.NOT_FOUND,"练习会话不存在");
        return rows.get(0);
    }
    private Map<String,Object> byRequest(String table,UUID requestId) {
        // table names are fixed call-site constants, never request parameters.
        var rows=jdbc.queryForList("select * from chanlun."+table+" where client_request_id=?",requestId);
        return rows.isEmpty()?null:rows.get(0);
    }
    private void sameRequest(Map<String,Object> row,Object request) {
        if(!json(row.get("request_payload").toString()).equals(mapper.valueToTree(request)))throw conflict("该请求编号已用于其他内容");
    }
    public Object create(CreateRequest request) {
        var existing=byRequest("replay_session",request.clientRequestId());
        if(existing!=null){sameRequest(existing,request);return view((UUID)existing.get("id"));}
        UUID runRequest=UUID.nameUUIDFromBytes(("replay-start:"+request.clientRequestId()).getBytes(StandardCharsets.UTF_8));
        @SuppressWarnings("unchecked")
        var run=(Map<String,Object>)analysis.create(new RunRequest(runRequest,request.engineId(),request.datasetId(),request.startBars()));
        if("FAILED".equals(run.get("status")))throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY,"初始结构计算失败，请重新创建练习");
        if(!"SUCCEEDED".equals(run.get("status")))throw conflict("初始结构仍在计算，请稍后重试同一请求");
        UUID runId=(UUID)run.get("id");
        var result=analysis.result(runId);
        UUID id=UUID.randomUUID();
        String title=request.title()==null||request.title().isBlank()?"我的逐根练习":request.title().strip();
        jdbc.update("""
            insert into chanlun.replay_session(id,client_request_id,request_payload,title,engine_id,dataset_id,dataset_hash,profile_hash,start_bars,observed_bars,current_run_id)
            values(?,?,?::jsonb,?,?,?,?,?,?,?,?) on conflict(client_request_id) do nothing
            """,id,request.clientRequestId(),encode(request),title,request.engineId(),request.datasetId(),result.path("datasetHash").asText(),
            result.path("profileHash").asText(),request.startBars(),request.startBars(),runId);
        var saved=byRequest("replay_session",request.clientRequestId());sameRequest(saved,request);
        return view((UUID)saved.get("id"));
    }
    public Object recent() {
        return jdbc.queryForList("""
            select id,title,engine_id as "engineId",observed_bars as "observedBars",step,state,created_at as "createdAt"
            from chanlun.replay_session order by created_at desc,id desc limit 30
            """);
    }
    public Map<String,Object> view(UUID id) {
        var row=session(id,false);
        int count=((Number)row.get("observed_bars")).intValue();
        int step=((Number)row.get("step")).intValue();
        JsonNode result=analysis.result((UUID)row.get("current_run_id"));
        checkPrefix(result,row,count);
        var decisions=jdbc.query("""
            select d.id,d.step,d.observed_bars,d.run_id,j.id as judgment_id,j.structure_id,j.outlook,j.content,j.evidence::text,j.created_at
            from chanlun.replay_decision d join chanlun.judgment j on j.id=d.judgment_id
            where d.session_id=? and d.step<=? order by d.step desc limit 100
            """,(rs,n)->{
                var item=new LinkedHashMap<String,Object>();item.put("id",rs.getObject("id"));item.put("step",rs.getInt("step"));
                item.put("observedBars",rs.getInt("observed_bars"));item.put("runId",rs.getObject("run_id"));
                item.put("judgmentId",rs.getObject("judgment_id"));item.put("structureId",rs.getString("structure_id"));
                item.put("outlook",rs.getString("outlook"));item.put("content",rs.getString("content"));item.put("evidence",json(rs.getString("evidence")));
                item.put("createdAt",rs.getTimestamp("created_at").toInstant());return item;
            },id,step);
        var output=new LinkedHashMap<String,Object>();output.put("id",id);output.put("title",row.get("title"));output.put("engineId",row.get("engine_id"));
        output.put("startBars",row.get("start_bars"));output.put("observedBars",count);output.put("step",step);
        output.put("status",row.get("pending_command")!=null?"ADVANCING":row.get("state"));output.put("error",row.get("last_error"));
        output.put("analysis",result);output.put("decisions",decisions);
        output.put("decisionSubmitted",decisions.stream().anyMatch(item->Integer.valueOf(step).equals(item.get("step"))));
        return output;
    }
    static void checkPrefix(JsonNode result,Map<String,Object> session,int count) {
        if(result.path("observedBars").asInt()!=count||result.path("bars").size()!=count
            ||!result.path("engineId").asText().equals(session.get("engine_id"))
            ||!result.path("profileHash").asText().equals(session.get("profile_hash"))
            ||!result.path("datasetHash").asText().equals(session.get("dataset_hash")))throw conflict("数据或引擎规则版本不一致，请新建练习；旧记录仍保留");
        if(!result.path("observedAsOfDate").asText().equals(result.path("bars").get(count-1).path("date").asText()))throw conflict("观察日期与行情界限不一致");
        for(int i=0;i<count;i++)if(result.path("bars").get(i).path("index").asInt(-1)!=i)throw conflict("行情前缀校验失败");
        for(var item:result.path("structures"))if(item.path("endIndex").asInt()>=count)throw conflict("检测到超出观察界限的结构");
    }
    public Object decide(UUID id,DecisionRequest request) {
        tx.executeWithoutResult(status->{
            var prior=byRequest("replay_decision",request.clientRequestId());
            if(prior!=null){
                if(!id.equals(prior.get("session_id")))throw conflict("该保存编号属于其他练习");
                sameRequest(prior,request);return;
            }
            var row=session(id,true);
            prior=byRequest("replay_decision",request.clientRequestId());
            if(prior!=null){if(!id.equals(prior.get("session_id")))throw conflict("该保存编号属于其他练习");sameRequest(prior,request);return;}
            if(!"ACTIVE".equals(row.get("state"))||row.get("pending_command")!=null)throw conflict("当前练习不能提交判断，请刷新进度");
            int step=((Number)row.get("step")).intValue();
            if(step!=request.expectedStep())throw conflict("观察步骤已变化，请刷新后再判断");
            if(jdbc.queryForObject("select count(*) from chanlun.replay_decision where session_id=? and step=?",Integer.class,id,step)>0)
                throw conflict("此步骤已提交判断，原判断不能覆盖");
            UUID noteRequest=UUID.nameUUIDFromBytes(("replay-note:"+id+":"+request.clientRequestId()).getBytes(StandardCharsets.UTF_8));
            var noteEvidence=new LinkedHashMap<String,Object>(Map.of("replaySessionId",id,"replayStep",step));
            if(request.structureId()!=null)for(var structure:analysis.result((UUID)row.get("current_run_id")).path("structures"))
                if(request.structureId().equals(structure.path("id").asText()))noteEvidence.put("structureSnapshot",structure);
            @SuppressWarnings("unchecked")
            var note=(Map<String,Object>)analysis.persistJudgment(new JudgmentRequest(noteRequest,(UUID)row.get("current_run_id"),request.structureId(),
                request.outlook(),request.content(),request.lessonNumber()),noteEvidence);
            jdbc.update("""
                insert into chanlun.replay_decision(id,client_request_id,session_id,step,observed_bars,run_id,judgment_id,request_payload)
                values(?,?,?,?,?,?,?,?::jsonb)
                """,UUID.randomUUID(),request.clientRequestId(),id,step,row.get("observed_bars"),row.get("current_run_id"),note.get("id"),encode(request));
        });
        return view(id);
    }
    private record Start(UUID commandId,int nextCount,Map<String,Object> session) {}
    public Object advance(UUID id,AdvanceRequest request) {
        Start started=tx.execute(status->{
            var prior=byRequest("replay_advance",request.clientRequestId());
            if(prior!=null){
                if(!id.equals(prior.get("session_id"))||((Number)prior.get("expected_step")).intValue()!=request.expectedStep())throw conflict("该推进编号已用于其他步骤");
                if("FAILED".equals(prior.get("status")))throw conflict("上次推进未成功，请使用新的请求编号重试");
                return null;
            }
            var row=session(id,true);
            prior=byRequest("replay_advance",request.clientRequestId());
            if(prior!=null){
                if(!id.equals(prior.get("session_id"))||((Number)prior.get("expected_step")).intValue()!=request.expectedStep())throw conflict("该推进编号已用于其他步骤");
                if("FAILED".equals(prior.get("status")))throw conflict("上次推进未成功，请使用新的请求编号重试");
                return null;
            }
            int step=((Number)row.get("step")).intValue();
            if(step!=request.expectedStep())throw conflict("观察步骤已变化，请刷新进度");
            if(!"ACTIVE".equals(row.get("state")))throw conflict("练习已经完成");
            if(row.get("pending_command")!=null)throw conflict("本步骤正在推进，请稍后刷新");
            if(jdbc.queryForObject("select count(*) from chanlun.replay_decision where session_id=? and step=?",Integer.class,id,step)==0)
                throw conflict("请先提交本步骤的判断，再展开下一根");
            UUID command=UUID.randomUUID();
            jdbc.update("insert into chanlun.replay_advance(id,client_request_id,session_id,expected_step,status) values(?,?,?,?,'RUNNING')",command,request.clientRequestId(),id,step);
            jdbc.update("update chanlun.replay_session set pending_command=?,last_error=null,updated_at=now() where id=?",command,id);
            return new Start(command,((Number)row.get("observed_bars")).intValue()+1,row);
        });
        if(started==null)return view(id);
        try {
            UUID runRequest=UUID.nameUUIDFromBytes(("replay-advance:"+started.commandId()).getBytes(StandardCharsets.UTF_8));
            @SuppressWarnings("unchecked")
            var run=(Map<String,Object>)analysis.create(new RunRequest(runRequest,started.session().get("engine_id").toString(),
                started.session().get("dataset_id").toString(),started.nextCount()));
            if(!"SUCCEEDED".equals(run.get("status")))throw conflict("下一步计算未成功，请刷新状态后重试");
            UUID runId=(UUID)run.get("id");
            checkPrefix(analysis.result(runId),started.session(),started.nextCount());
            tx.executeWithoutResult(status->{
                if(jdbc.update("update chanlun.replay_advance set status='SUCCEEDED',run_id=?,updated_at=now() where id=? and status='RUNNING'",runId,started.commandId())!=1)
                    throw conflict("推进已过期，请刷新状态");
                int updated=jdbc.update("""
                    update chanlun.replay_session set current_run_id=?,observed_bars=?,step=step+1,
                    state=case when ?=1894 then 'COMPLETE' else 'ACTIVE' end,pending_command=null,last_error=null,updated_at=now()
                    where id=? and step=? and pending_command=?
                    """,runId,started.nextCount(),started.nextCount(),id,request.expectedStep(),started.commandId());
                if(updated!=1)throw conflict("观察步骤已变化，请刷新进度");
            });
        } catch(Exception failure) {
            String message=failure instanceof ResponseStatusException exception?exception.getReason():"推进计算未完成，请刷新状态后重试";
            fail(started.commandId(),id,message);
            if(failure instanceof ResponseStatusException exception)throw exception;
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,message);
        }
        return view(id);
    }
    private void fail(UUID command,UUID session,String message) {
        tx.executeWithoutResult(status->{
            jdbc.update("update chanlun.replay_advance set status='FAILED',error=?,updated_at=now() where id=? and status='RUNNING'",message,command);
            jdbc.update("update chanlun.replay_session set pending_command=null,last_error=?,updated_at=now() where id=? and pending_command=?",message,session,command);
        });
    }
    @Scheduled(fixedDelay=60000)
    public void expireInterruptedAdvances() {
        jdbc.update("""
            with expired as (
                update chanlun.replay_advance set status='FAILED',error='推进中断或超时，请重试',updated_at=now()
                where status='RUNNING' and updated_at<now()-interval '3 minutes' returning id,session_id
            ) update chanlun.replay_session s set pending_command=null,last_error='推进中断或超时，请重试',updated_at=now()
              from expired e where s.id=e.session_id and s.pending_command=e.id
            """);
    }
}
