package com.aiquant.identity;

import com.fasterxml.jackson.databind.JsonNode;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.*;
import java.util.function.Supplier;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

/** Personal documents use a restricted role with FORCE RLS, never account-administration privileges. */
@Service
final class WorkspaceDocuments {
    private final Accounts a;
    WorkspaceDocuments(Accounts a){this.a=a;}
    record Save(UUID commandId,long expectedRevision,JsonNode content){}
    record Key(String kind,String key){}
    static final Set<String> PERIODS=Set.of("15","30","60","180","300","900","DAY","WEEK","MONTH");
    Key preferences(){return new Key("PREFERENCES","WORKSPACE");}
    Key chart(String symbol,String period){
        if(symbol==null||!symbol.matches("[A-Z]{1,4}[0-9]{3,4}")||!PERIODS.contains(period))throw Accounts.fail(HttpStatus.BAD_REQUEST,"图表同步需要明确的实际交割月和支持的周期。");
        return new Key("CHART","LIVE_FUTURES_UNADJUSTED:"+symbol+":"+period);
    }
    private Map<String,Object> scoped(Accounts.Principal p,Key key,Supplier<Map<String,Object>> work){
        return a.tx.execute(status->{
            // Lock the live membership/account/tenant before assuming the restricted role.
            var active=a.db.queryForList("""
                select m.role,u.platform_admin from identity.membership m join identity.account u on u.id=m.user_id
                join identity.tenant t on t.id=m.tenant_id
                where m.tenant_id=? and m.user_id=? and u.enabled and u.verified and not u.must_change and t.enabled
                for share of m,u,t
                """,p.tenant(),p.user());
            if(active.isEmpty())throw Accounts.fail(HttpStatus.FORBIDDEN,"账号或工作空间成员身份已失效。");
            var member=active.get(0);var current=new Accounts.Principal(p.user(),p.tenant(),p.credential(),p.username(),member.get("role").toString(),Boolean.TRUE.equals(member.get("platform_admin")),false,p.apiKey(),p.scope());
            if(key.kind().equals("CHART")&&!a.access.effective(current).contains("market.read"))throw Accounts.fail(HttpStatus.FORBIDDEN,"需要行情读取权限才能访问私人图表记录。");
            a.db.execute("set local role aiquant_workspace");
            a.db.queryForObject("select set_config('app.workspace_tenant',?,true)",String.class,p.tenant().toString());
            a.db.queryForObject("select set_config('app.workspace_owner',?,true)",String.class,p.user().toString());
            var result=new LinkedHashMap<String,Object>(work.get());result.put("ownerId",p.user());result.put("tenantId",p.tenant());return result;
        });
    }
    Map<String,Object> get(Accounts.Principal p,Key key){return scoped(p,key,()->read(key));}
    private Map<String,Object> read(Key key){
        var rows=a.db.queryForList("select revision,content::text,updated_at from identity.workspace_document where kind=? and document_key=?",key.kind(),key.key());
        if(rows.isEmpty())return Map.of("kind",key.kind(),"key",key.key(),"revision",0,"content",a.mapper.nullNode());
        var row=rows.get(0);return Map.of("kind",key.kind(),"key",key.key(),"revision",row.get("revision"),"content",json(row.get("content")),"updatedAt",row.get("updated_at").toString());
    }
    Map<String,Object> save(Accounts.Principal p,Key key,Save body){
        if(body==null||body.commandId()==null||body.expectedRevision()<0||body.expectedRevision()>1_000_000_000L)throw Accounts.fail(HttpStatus.BAD_REQUEST,"保存请求编号或版本无效。");
        validate(key,body.content());
        return scoped(p,key,()->{
            // Command IDs belong to the owner/workspace across all document keys.
            a.db.queryForObject("select pg_advisory_xact_lock(hashtextextended(?,0))",Object.class,"workspace-command:"+p.tenant()+":"+p.user()+":"+body.commandId());
            // This also serializes the first insert, where no document row exists yet.
            a.db.queryForObject("select pg_advisory_xact_lock(hashtextextended(?,0))",Object.class,p.tenant()+":"+p.user()+":"+key.kind()+":"+key.key());
            var previous=a.db.queryForList("select kind,document_key,base_revision,revision,content::text from identity.workspace_revision where command_id=?",body.commandId());
            var current=read(key);long revision=((Number)current.get("revision")).longValue();
            if(!previous.isEmpty()){
                var prior=previous.get(0);
                if(!key.kind().equals(prior.get("kind"))||!key.key().equals(prior.get("document_key"))||((Number)prior.get("base_revision")).longValue()!=body.expectedRevision()||!json(prior.get("content")).equals(body.content()))throw Accounts.fail(HttpStatus.CONFLICT,"此请求编号已用于另一份内容。");
                if(revision!=((Number)prior.get("revision")).longValue())throw Accounts.fail(HttpStatus.CONFLICT,"原请求已经保存，但云端已有更新；本机草稿保留，请读取并比较最新版本。");
                return current;
            }
            if(revision!=body.expectedRevision())throw Accounts.fail(HttpStatus.CONFLICT,"云端版本已更新；本机草稿保留，请读取并比较后保存。");
            long next=revision+1;
            if(revision==0)a.db.update("insert into identity.workspace_document(tenant_id,owner_id,kind,document_key,revision,content) values(?,?,?,?,?,?::jsonb)",p.tenant(),p.user(),key.kind(),key.key(),next,body.content().toString());
            else a.db.update("update identity.workspace_document set revision=?,content=?::jsonb,updated_at=clock_timestamp() where kind=? and document_key=?",next,body.content().toString(),key.kind(),key.key());
            a.db.update("insert into identity.workspace_revision(tenant_id,owner_id,kind,document_key,command_id,base_revision,revision,content) values(?,?,?,?,?,?,?,?::jsonb)",p.tenant(),p.user(),key.kind(),key.key(),body.commandId(),revision,next,body.content().toString());
            return read(key);
        });
    }
    private JsonNode json(Object value){try{return a.mapper.readTree(value.toString());}catch(Exception e){throw new IllegalStateException("私人记录格式不可读取");}}
    static void validate(Key key,JsonNode body){
        if(body==null||!body.isObject()||!body.path("schemaVersion").isIntegralNumber()||body.path("schemaVersion").asInt(-1)!=1||body.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8).length>65536)bad();
        if(key.kind().equals("PREFERENCES")){
            fields(body,Set.of("schemaVersion","experience"));if(!Set.of("SIMPLE","PRO").contains(body.path("experience").asText()))bad();return;
        }
        fields(body,Set.of("schemaVersion","layout","items"));JsonNode layout=body.path("layout"),items=body.path("items");
        fields(layout,Set.of("theme","mainType","subChart","maPeriods","autoGroups"));
        if(!Set.of("light","dark").contains(layout.path("theme").asText())||!Set.of("candle","line").contains(layout.path("mainType").asText())||!Set.of("vol","macd","change").contains(layout.path("subChart").asText()))bad();
        unique(layout.path("maPeriods"),Set.of("5","10","20","60","180"),true);unique(layout.path("autoGroups"),Set.of("REGRESSION","TREND","HORIZONTAL"),false);
        if(!items.isArray()||items.size()>100)bad();Set<String> ids=new HashSet<>();
        for(JsonNode item:items){
            fields(item,Set.of("id","kind","anchors"));String id=item.path("id").asText(),kind=item.path("kind").asText();
            if(!id.matches("[A-Za-z0-9_-]{1,100}")||!ids.add(id)||!Set.of("LINE","RAY","HORIZONTAL","CHANNEL").contains(kind))bad();
            JsonNode anchors=item.path("anchors");int count=kind.equals("HORIZONTAL")?1:kind.equals("CHANNEL")?3:2;
            if(!anchors.isArray()||anchors.size()!=count)bad();
            for(JsonNode anchor:anchors){fields(anchor,Set.of("timestamp","price"));try{if(anchor.path("timestamp").asText().length()>40)bad();OffsetDateTime.parse(anchor.path("timestamp").asText());}catch(java.time.DateTimeException e){bad();}
                if(!anchor.path("price").isNumber()||anchor.path("price").decimalValue().signum()<=0||anchor.path("price").decimalValue().compareTo(new BigDecimal("1000000000000"))>0)bad();}
            if(count>1&&OffsetDateTime.parse(anchors.get(0).path("timestamp").asText()).toInstant().equals(OffsetDateTime.parse(anchors.get(1).path("timestamp").asText()).toInstant()))bad();
        }
    }
    private static void fields(JsonNode body,Set<String> allowed){if(!body.isObject()||body.size()!=allowed.size())bad();body.fieldNames().forEachRemaining(k->{if(!allowed.contains(k))bad();});}
    private static void unique(JsonNode node,Set<String> allowed,boolean numbers){if(!node.isArray()||node.size()>allowed.size())bad();Set<String> seen=new HashSet<>();for(var v:node)if(numbers&&!v.isIntegralNumber()||!allowed.contains(v.asText())||!seen.add(v.asText()))bad();}
    private static void bad(){throw Accounts.fail(HttpStatus.BAD_REQUEST,"私人图表或偏好格式无效；仅支持规定的图形、锚点和显示参数。");}
}
