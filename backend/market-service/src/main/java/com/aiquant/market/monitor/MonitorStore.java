package com.aiquant.market.monitor;

import com.aiquant.tenancy.TenantTransactions;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import java.util.function.Supplier;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;

@Service
public class MonitorStore {
    public record Scope(UUID tenant,UUID actor,String kind){}
    public record Page(List<Map<String,Object>> items,long total,int page,int size){}
    final JdbcTemplate db;final TransactionTemplate tx;final ObjectMapper mapper;
    static final String PUBLIC="id,tenant_id as \"tenantId\",created_by as \"createdBy\",asset_type as \"assetType\",symbol,name,seconds,parameters,metadata,enabled,archived,version,status,message,metrics,checked_at as \"checkedAt\",source_timestamp as \"sourceTimestamp\",created_at as \"createdAt\",updated_at as \"updatedAt\"";
    public MonitorStore(JdbcTemplate db,TransactionTemplate tx,ObjectMapper mapper){this.db=db;this.tx=tx;this.mapper=mapper;}
    static ResponseStatusException fail(HttpStatus status,String reason){return new ResponseStatusException(status,reason);}
    <T>T tenant(Scope scope,Supplier<T> work){return TenantTransactions.run(db,tx,scope.tenant(),work);}
    public String json(Object value){try{return mapper.writeValueAsString(value);}catch(Exception e){throw new IllegalArgumentException("Invalid monitor JSON");}}
    public Map<String,Object> object(Object value){try{return mapper.readValue(String.valueOf(value),new TypeReference<Map<String,Object>>(){});}catch(Exception e){throw new IllegalArgumentException("Invalid stored monitor JSON");}}
    Map<String,Object> row(Scope scope,UUID id){var rows=db.queryForList("select "+PUBLIC+" from market.live_monitor where id=? and asset_type=? and not archived",id,scope.kind());if(rows.isEmpty())throw fail(HttpStatus.NOT_FOUND,"监控不在当前租户或行情类型中。");return rows.get(0);}
    public Map<String,Object> get(Scope scope,UUID id){return tenant(scope,()->row(scope,id));}
    public Page list(Scope scope,String q,int page,int size){return tenant(scope,()->{
        int limit=Math.max(1,Math.min(50,size)),current=Math.max(1,page);String pattern="%"+q+"%";
        String where=" from market.live_monitor where asset_type=? and not archived and (name ilike ? or symbol ilike ?)";
        Long total=db.queryForObject("select count(*)"+where,Long.class,scope.kind(),pattern,pattern);
        return new Page(db.queryForList("select "+PUBLIC+where+" order by created_at desc limit ? offset ?",scope.kind(),pattern,pattern,limit,(long)(current-1)*limit),total,current,limit);
    });}
    void audit(Scope scope,UUID id,String action,Object before,Object after){db.update("insert into market.live_monitor_audit(tenant_id,monitor_id,actor_id,action,before_state,after_state) values(?,?,?,?,?::jsonb,?::jsonb)",scope.tenant(),id,scope.actor(),action,json(before),json(after));}
    void capacity(Scope scope,boolean enabled,boolean wasEnabled){
        if(!enabled||wasEnabled)return;
        if(db.queryForObject("select count(*) from market.live_monitor where enabled and not archived",Integer.class)>=32)throw fail(HttpStatus.CONFLICT,"后台监控全局容量为 32 个，请先暂停其他任务。");
        if(db.queryForObject("select count(*) from market.live_monitor where tenant_id=? and enabled and not archived",Integer.class,scope.tenant())>=20)throw fail(HttpStatus.CONFLICT,"当前租户最多启用 20 个后台监控。");
    }
    public Map<String,Object> save(Scope scope,UUID id,String name,boolean enabled,long version,Map<String,Object> validated){
        return tx.execute(status->{
            db.execute("select pg_advisory_xact_lock(71203021)");
            boolean existed=id!=null;UUID selected=existed?id:UUID.randomUUID();
            var owned=existed?db.queryForList("select enabled from market.live_monitor where id=? and tenant_id=? and asset_type=? and not archived",selected,scope.tenant(),scope.kind()):List.<Map<String,Object>>of();
            if(existed&&owned.isEmpty())throw fail(HttpStatus.NOT_FOUND,"监控不存在于当前范围。");
            capacity(scope,enabled,existed&&Boolean.TRUE.equals(owned.get(0).get("enabled")));
            return tenant(scope,()->{
                Object before=existed?row(scope,selected):null;
                @SuppressWarnings("unchecked") var spec=(Map<String,Object>)validated.get("spec");
                if(!scope.kind().equals(spec.get("assetType")))throw fail(HttpStatus.BAD_REQUEST,"监控类型不匹配。");
                if(existed){
                    int changed=db.update("update market.live_monitor set name=?,enabled=?,symbol=?,seconds=?,parameters=?::jsonb,metadata=?::jsonb,created_by=?,version=version+1,state='{}',metrics='{}',status=?,message='',source_timestamp=null,checked_at=null,lease_owner=null,lease_until=null,next_check_at=now(),updated_at=now() where id=? and asset_type=? and version=? and not archived",
                        name.strip(),enabled,spec.get("symbol"),spec.get("seconds"),json(spec.get("parameters")),json(validated.get("metadata")),scope.actor(),enabled?"STARTING":"PAUSED",selected,scope.kind(),version);
                    if(changed!=1)throw fail(HttpStatus.CONFLICT,"监控已被修改，请刷新后重试。");
                }else db.update("insert into market.live_monitor(id,tenant_id,created_by,asset_type,symbol,name,seconds,parameters,metadata,enabled,status) values(?,?,?,?,?,?,?,?::jsonb,?::jsonb,?,?)",
                    selected,scope.tenant(),scope.actor(),scope.kind(),spec.get("symbol"),name.strip(),spec.get("seconds"),json(spec.get("parameters")),json(validated.get("metadata")),enabled,enabled?"STARTING":"PAUSED");
                var after=row(scope,selected);audit(scope,selected,existed?"UPDATE":"CREATE",before,after);return after;
            });
        });
    }
    public Map<String,Object> enable(Scope scope,UUID id,boolean enabled,long version){return tx.execute(status->{
        db.execute("select pg_advisory_xact_lock(71203021)");
        var rows=db.queryForList("select enabled from market.live_monitor where id=? and tenant_id=? and asset_type=? and not archived",id,scope.tenant(),scope.kind());
        if(rows.isEmpty())throw fail(HttpStatus.NOT_FOUND,"监控不存在于当前范围。");capacity(scope,enabled,Boolean.TRUE.equals(rows.get(0).get("enabled")));
        return tenant(scope,()->{var before=row(scope,id);int count=db.update("update market.live_monitor set enabled=?,created_by=?,version=version+1,state='{}',metrics='{}',status=?,message='',source_timestamp=null,checked_at=null,lease_owner=null,lease_until=null,next_check_at=now(),updated_at=now() where id=? and asset_type=? and version=? and not archived",enabled,scope.actor(),enabled?"STARTING":"PAUSED",id,scope.kind(),version);
            if(count!=1)throw fail(HttpStatus.CONFLICT,"监控已被修改，请刷新后重试。");var after=row(scope,id);audit(scope,id,enabled?"RESUME":"PAUSE",before,after);return after;});
    });}
    public void archive(Scope scope,UUID id,long version){tenant(scope,()->{var before=row(scope,id);if(db.update("update market.live_monitor set archived=true,enabled=false,status='PAUSED',version=version+1,state='{}',lease_owner=null,lease_until=null,updated_at=now() where id=? and asset_type=? and version=?",id,scope.kind(),version)!=1)throw fail(HttpStatus.CONFLICT,"监控已被修改，请刷新后重试。");audit(scope,id,"ARCHIVE",before,Map.of("archived",true));return null;});}
    public Page events(Scope scope,String q,UUID monitorId,boolean unacknowledged,int page,int size){return tenant(scope,()->{
        int limit=Math.max(1,Math.min(100,size)),current=Math.max(1,page);String pattern="%"+q+"%";
        var args=new ArrayList<Object>(List.of(scope.kind(),pattern,pattern,pattern));
        String where=" from market.live_monitor_event where asset_type=? and (symbol ilike ? or label ilike ? or rule ilike ?)";
        if(monitorId!=null){where+=" and monitor_id=?";args.add(monitorId);}if(unacknowledged)where+=" and acknowledged_at is null";
        Long total=db.queryForObject("select count(*)"+where,Long.class,args.toArray());args.add(limit);args.add((long)(current-1)*limit);
        return new Page(db.queryForList("select id,monitor_id as \"monitorId\",rule,label,symbol,asset_type as \"assetType\",observed_at as \"observedAt\",evidence,algorithm_version as \"algorithmVersion\",acknowledged_at as \"acknowledgedAt\",created_at as \"createdAt\""+where+" order by id desc limit ? offset ?",args.toArray()),total,current,limit);
    });}
    public void acknowledge(Scope scope,long id){tenant(scope,()->{if(db.update("update market.live_monitor_event set acknowledged_at=coalesce(acknowledged_at,now()),acknowledged_by=coalesce(acknowledged_by,?) where id=? and asset_type=?",scope.actor(),id,scope.kind())!=1)throw fail(HttpStatus.NOT_FOUND,"触发记录不存在于当前范围。");return null;});}
    public List<Map<String,Object>> claim(UUID worker,int count){return tx.execute(status->{
        var rows=db.queryForList("select * from market.live_monitor where enabled and not archived and next_check_at<=now() and (lease_until is null or lease_until<now()) order by next_check_at limit ? for update skip locked",Math.min(4,count));
        for(var row:rows)db.update("update market.live_monitor set lease_owner=?,lease_until=now()+interval '45 seconds' where id=?",worker,row.get("id"));return rows;
    });}
    public boolean complete(Map<String,Object> job,UUID worker,Map<String,Object> result){return tx.execute(status->{
        Timestamp source=null;if(result.get("sourceTimestamp")!=null)source=Timestamp.from(Instant.parse(result.get("sourceTimestamp").toString()));
        int changed=db.update("update market.live_monitor set state=?::jsonb,status=?,message=?,metrics=?::jsonb,source_timestamp=?,checked_at=now(),next_check_at=now()+interval '3 seconds',lease_owner=null,lease_until=null,enabled=case when ? then false else enabled end where id=? and version=? and lease_owner=? and enabled and not archived",
            json(result.getOrDefault("state",Map.of())),result.getOrDefault("status","ERROR"),result.getOrDefault("message",""),json(result.getOrDefault("metrics",Map.of())),source,"EXPIRED".equals(result.get("status")),job.get("id"),job.get("version"),worker);
        if(changed!=1)return false;
        Object values=result.get("events");if(values instanceof List<?> events)for(Object value:events){
            @SuppressWarnings("unchecked") var event=(Map<String,Object>)value;
            db.update("insert into market.live_monitor_event(tenant_id,monitor_id,event_key,rule,label,symbol,asset_type,observed_at,evidence,algorithm_version) values(?,?,?,?,?,?,?, ?,?::jsonb,?) on conflict(monitor_id,event_key) do nothing",
                job.get("tenant_id"),job.get("id"),job.get("version")+":"+event.get("key"),event.get("rule"),event.get("label"),job.get("symbol"),job.get("asset_type"),Timestamp.from(Instant.parse(event.get("observedAt").toString())),json(event.get("evidence")),event.get("algorithmVersion"));
        }return true;
    });}
}
