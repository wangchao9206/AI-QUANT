package com.aiquant.identity;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.time.Duration;
import java.time.Instant;
import java.sql.Timestamp;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
class IdentityController {
    private final Accounts a; private final boolean secure;
    IdentityController(Accounts a,@Value("${identity.cookie-secure}") boolean secure){this.a=a;this.secure=secure;}
    record Registration(@NotBlank @Size(max=32) String username,@NotBlank @Size(max=254) String email){}
    record Login(@NotBlank @Size(max=254) String identifier,@NotBlank @Size(max=128) String password){}
    record Email(@NotBlank @Size(max=254) String email){}
    record Token(@NotBlank @Size(max=100) String token){}
    record Reset(@NotBlank @Size(max=100) String token,@NotBlank @Size(max=128) String password){}
    record Change(@NotBlank @Size(max=128) String oldPassword,@NotBlank @Size(max=128) String password){}
    record Name(@NotBlank @Size(max=80) String name){}
    record Tenant(@NotNull UUID tenantId){}
    record Member(@NotBlank @Size(max=254) String identifier,@NotBlank String role){}
    record Key(@NotBlank @Size(max=80) String name,@Pattern(regexp="READ|READ_WRITE") @NotNull String scope,@Min(1) @Max(365) int days){}
    record Enabled(boolean enabled){}
    record BindEmail(@NotBlank @Size(max=254) String email,@NotBlank @Size(max=128) String password){}
    void cookie(HttpServletResponse response,String name,String value,boolean httpOnly,Duration age){response.addHeader(HttpHeaders.SET_COOKIE,ResponseCookie.from(name,value).path("/").httpOnly(httpOnly).secure(secure).sameSite("Lax").maxAge(age).build().toString());}
    void clear(HttpServletResponse response){cookie(response,"aq_session","",true,Duration.ZERO);cookie(response,"aq_csrf","",false,Duration.ZERO);}
    @GetMapping("/api/v1/auth/config") Object config(){return Map.of("registrationEnabled",true,"smtpConfigured",!a.mail.hostIsMissing(),"initialPasswordRule","账号 + 123456");}
    @PostMapping("/api/v1/auth/register") Object register(@Valid @RequestBody Registration body){a.register(body.username(),body.email());return Map.of("message","验证邮件已提交发信服务，请检查邮箱并完成验证。");}
    @PostMapping("/api/v1/auth/verify") Object verify(@Valid @RequestBody Token body){a.verify(body.token());return Map.of("message","邮箱验证完成，请使用初始密码登录并设置新密码。");}
    @PostMapping("/api/v1/auth/resend") Object resend(@Valid @RequestBody Email body){a.sendChallenge(body.email(),"VERIFY");return Map.of("message","若邮箱存在且尚未验证，验证邮件已提交发信服务。");}
    @PostMapping("/api/v1/auth/forgot") Object forgot(@Valid @RequestBody Email body){a.sendChallenge(body.email(),"RESET");return Map.of("message","若邮箱对应已验证账号，重置邮件已提交发信服务。");}
    @PostMapping("/api/v1/auth/reset") Object reset(@Valid @RequestBody Reset body){a.reset(body.token(),body.password());return Map.of("message","密码已重置，旧会话和接口密钥已失效，请重新登录。");}
    @PostMapping("/api/v1/auth/login") Object login(@Valid @RequestBody Login body,HttpServletResponse response,HttpServletRequest request){var result=a.login(body.identifier(),body.password());var p=a.authenticate(result.token(),null,null,null,false);request.setAttribute("identity.user",p.user());request.setAttribute("identity.tenant",p.tenant());cookie(response,"aq_session",result.token(),true,Duration.ofDays(7));cookie(response,"aq_csrf",result.csrf(),false,Duration.ofDays(7));return Map.of("authenticated",true);}
    @GetMapping("/api/v1/auth/me") Object me(HttpServletRequest request){return a.me(a.require(request,false,true));}
    @PostMapping("/api/v1/auth/email") Object bindEmail(@Valid @RequestBody BindEmail body,HttpServletRequest req){a.requestEmail(a.require(req,true,false),body.email(),body.password());return Map.of("message","验证邮件已提交发信服务。新邮箱验证成功后，旧会话和接口密钥会失效。");}
    @PostMapping("/api/v1/auth/verify-email") Object verifyEmail(@Valid @RequestBody Token body){a.verifyEmail(body.token());return Map.of("message","邮箱已更新，请重新登录。");}
    @PostMapping("/api/v1/auth/logout") Object logout(HttpServletRequest request,HttpServletResponse response){var p=a.require(request,true,true);a.db.update("delete from identity.session where id=? and user_id=?",p.credential(),p.user());a.audit(p.user(),p.tenant(),"LOGOUT",p.credential().toString());clear(response);return Map.of("message","已退出登录。");}
    @PostMapping("/api/v1/auth/change-password") Object change(@Valid @RequestBody Change body,HttpServletRequest request,HttpServletResponse response){a.changePassword(a.require(request,true,true),body.oldPassword(),body.password());clear(response);return Map.of("message","密码已更新，请重新登录。");}
    @GetMapping("/api/v1/auth/sessions") Object sessions(HttpServletRequest request){var p=a.require(request,false,false);return a.db.queryForList("select id,tenant_id as \"tenantId\",created_at as \"createdAt\",expires_at as \"expiresAt\" from identity.session where user_id=? and expires_at>now() order by created_at desc",p.user());}
    @PostMapping("/api/v1/auth/sessions/{id}/revoke") Object revokeSession(@PathVariable UUID id,HttpServletRequest request){var p=a.require(request,true,false);a.db.update("delete from identity.session where id=? and user_id=?",id,p.user());a.audit(p.user(),p.tenant(),"SESSION_REVOKE",id.toString());return Map.of("message","会话已撤销。");}
    @PostMapping("/api/v1/auth/tenants") Object createTenant(@Valid @RequestBody Name body,HttpServletRequest request){var p=a.require(request,true,false);a.limit("tenant:"+p.user(),5);return a.tx.execute(status->Map.of("id",a.createTenant(p.user(),body.name())));}
    @PostMapping("/api/v1/auth/tenants/switch") Object switchTenant(@Valid @RequestBody Tenant body,HttpServletRequest request){var p=a.require(request,true,false);var target=a.authenticate(Accounts.cookie(request,"aq_session"),null,body.tenantId().toString(),null,false);a.db.update("update identity.session set tenant_id=? where id=? and user_id=?",target.tenant(),p.credential(),p.user());a.audit(p.user(),target.tenant(),"TENANT_SWITCH",target.tenant().toString());return a.me(target);}
    @GetMapping("/api/v1/auth/members") Object members(HttpServletRequest request){var p=a.require(request,false,false);a.tenantAdmin(p);return a.db.queryForList("select a.id,a.username,a.email,m.role from identity.account a join identity.membership m on m.user_id=a.id where m.tenant_id=? order by a.username",p.tenant());}
    @PostMapping("/api/v1/auth/members") Object member(@Valid @RequestBody Member body,HttpServletRequest request){var p=a.require(request,true,false);a.tenantAdmin(p);String identifier=body.identifier().strip().toLowerCase(Locale.ROOT);var rows=a.db.queryForList("select id from identity.account where username=? or email=?",identifier,identifier);if(rows.isEmpty())throw Accounts.fail(HttpStatus.NOT_FOUND,"请先让该用户完成邮箱注册与验证。");a.member(p,(UUID)rows.get(0).get("id"),body.role(),false);return Map.of("message","成员角色已更新。");}
    @PostMapping("/api/v1/auth/members/{id}/remove") Object remove(@PathVariable UUID id,HttpServletRequest request){a.member(a.require(request,true,false),id,"MEMBER",true);return Map.of("message","成员已移除。");}
    @GetMapping("/api/v1/auth/keys") Object keys(HttpServletRequest request){var p=a.require(request,false,false);return a.db.queryForList("select id,name,scope,expires_at as \"expiresAt\",created_at as \"createdAt\" from identity.api_key where user_id=? and tenant_id=? order by created_at desc",p.user(),p.tenant());}
    @PostMapping("/api/v1/auth/keys") Object key(@Valid @RequestBody Key body,HttpServletRequest request){var p=a.require(request,true,false);if(p.role().equals("VIEWER")&&!body.scope().equals("READ"))throw Accounts.fail(HttpStatus.FORBIDDEN,"只读成员只能生成只读密钥。");a.limit("key:"+p.user(),10);String token="aqk_"+Secrets.token();UUID id=UUID.randomUUID();a.db.update("insert into identity.api_key(id,tenant_id,user_id,name,token_hash,scope,expires_at) values(?,?,?,?,?,?,?)",id,p.tenant(),p.user(),body.name().strip(),Secrets.hash(token),body.scope(),Timestamp.from(Instant.now().plus(Duration.ofDays(body.days()))));a.audit(p.user(),p.tenant(),"KEY_CREATE",id.toString());return Map.of("id",id,"token",token,"message","密钥仅显示一次，请妥善保存。");}
    @PostMapping("/api/v1/auth/keys/{id}/revoke") Object revokeKey(@PathVariable UUID id,HttpServletRequest request){var p=a.require(request,true,false);a.db.update("delete from identity.api_key where id=? and tenant_id=? and user_id=?",id,p.tenant(),p.user());a.audit(p.user(),p.tenant(),"KEY_REVOKE",id.toString());return Map.of("message","密钥已撤销。");}
    @GetMapping("/api/v1/auth/audit") Object audit(HttpServletRequest request){var p=a.require(request,false,false);a.tenantAdmin(p);return a.db.queryForList("select id,user_id as \"userId\",action,target,created_at as \"createdAt\" from identity.audit where tenant_id=? order by id desc limit 100",p.tenant());}
    @GetMapping("/api/v1/auth/admin/users") Object users(HttpServletRequest request){a.admin(a.require(request,false,false));return a.db.queryForList("select id,username,email,verified,enabled,must_change as \"mustChangePassword\",platform_admin as \"platformAdmin\",created_at as \"createdAt\" from identity.account order by created_at desc limit 200");}
    @GetMapping("/api/v1/auth/admin/tenants") Object tenants(HttpServletRequest request){a.admin(a.require(request,false,false));return a.db.queryForList("select t.id,t.name,t.enabled,(select count(*) from identity.membership m where m.tenant_id=t.id) as members from identity.tenant t order by t.created_at desc limit 200");}
    @PostMapping("/api/v1/auth/admin/users/{id}/enabled") Object enabled(@PathVariable UUID id,@RequestBody Enabled body,HttpServletRequest request){var p=a.require(request,true,false);a.admin(p);if(p.user().equals(id))throw Accounts.fail(HttpStatus.CONFLICT,"不能停用当前管理员账号。");var u=a.account(id);if(Boolean.TRUE.equals(u.get("platform_admin")))throw Accounts.fail(HttpStatus.CONFLICT,"平台管理员账号不能在此停用。");a.tx.executeWithoutResult(status->{a.db.update("update identity.account set enabled=? where id=?",body.enabled(),id);a.revokeAll(id);a.audit(p.user(),p.tenant(),"ACCOUNT_ENABLED_"+body.enabled(),id.toString());});return Map.of("message","账号状态已更新。");}
    @PostMapping("/api/v1/auth/admin/users/{id}/reset-initial") Object resetInitial(@PathVariable UUID id,HttpServletRequest request){var p=a.require(request,true,false);a.admin(p);var u=a.account(id);a.tx.executeWithoutResult(status->{a.db.update("update identity.account set password_hash=?,must_change=true where id=?",a.passwords.encode(u.get("username")+"123456"),id);a.revokeAll(id);a.audit(p.user(),p.tenant(),"ADMIN_RESET_INITIAL",id.toString());});return Map.of("message","已恢复为账号 + 123456；旧会话和密钥已撤销，下次登录须改密。");}
    record Introspection(String session,String bearer,String tenant,String csrf,boolean mutation,String path){}
    @PostMapping("/internal/v1/identity/introspect") Object introspect(@RequestHeader(value="X-Identity-Service-Secret",defaultValue="") String secret,@RequestBody Introspection body){
        if(!Secrets.equal(secret,a.secret))throw Accounts.fail(HttpStatus.FORBIDDEN,"Forbidden");
        var p=a.authenticate(body.session(),body.bearer(),body.tenant(),body.csrf(),body.mutation());
        if(p.mustChange())throw Accounts.fail(HttpStatus.FORBIDDEN,"请先修改初始密码。");
        try{a.access.business(p,body.path(),body.mutation());}catch(org.springframework.web.server.ResponseStatusException denied){a.audit(p.user(),p.tenant(),"ACCESS_DENIED",AccessControl.resource(body.path()));throw denied;}
        if(body.mutation()&&(p.role().equals("VIEWER")||(p.apiKey()&&p.scope().equals("READ"))))throw Accounts.fail(HttpStatus.FORBIDDEN,"当前身份仅有只读权限。");
        if(body.mutation()&&body.path()!=null&&body.path().startsWith("/api/v1/research/studies/")&&!p.platformAdmin())throw Accounts.fail(HttpStatus.FORBIDDEN,"公共研究资料的维护需要平台管理员权限。");
        return Map.of("identity",a.signed(p),"userId",p.user(),"tenantId",p.tenant());
    }
    record MonitorAuthorization(@NotNull UUID userId,@NotNull UUID tenantId,@Pattern(regexp="FUTURE|OPTION") @NotNull String assetType){}
    @PostMapping("/internal/v1/identity/monitor-authorization") Object monitorAuthorization(
            @RequestHeader(value="X-Identity-Service-Secret",defaultValue="") String secret,@Valid @RequestBody MonitorAuthorization body){
        if(!Secrets.equal(secret,a.secret))throw Accounts.fail(HttpStatus.FORBIDDEN,"Forbidden");
        var rows=a.db.queryForList("select u.username,u.platform_admin,m.role from identity.account u join identity.membership m on m.user_id=u.id join identity.tenant t on t.id=m.tenant_id where u.id=? and t.id=? and u.enabled and u.verified and not u.must_change and t.enabled",body.userId(),body.tenantId());
        if(rows.isEmpty())return Map.of("allowed",false,"message","账号、租户或成员身份已不可用。");
        var row=rows.get(0);var p=new Accounts.Principal(body.userId(),body.tenantId(),body.userId(),(String)row.get("username"),(String)row.get("role"),Boolean.TRUE.equals(row.get("platform_admin")),false,false,"READ_WRITE");
        var permissions=a.access.effective(p);String module=body.assetType().equals("OPTION")?"options":"market";
        boolean allowed=permissions.contains(module+".read")&&permissions.contains(module+".write");
        return Map.of("allowed",allowed,"message",allowed?"":"创建者已失去该类行情监控的读写权限。");
    }
    record Operation(UUID userId,UUID tenantId,@NotBlank @Size(max=10) String method,@NotBlank @Size(max=300) String path,@Min(100) @Max(599) int status,@Min(0) long durationMs,@Size(max=128) String traceId){}
    record DecisionAuthorization(@NotNull UUID userId,@NotNull UUID tenantId){}
    @PostMapping("/internal/v1/identity/decision-authorization") Object decisionAuthorization(@RequestHeader(value="X-Identity-Service-Secret",defaultValue="") String secret,@Valid @RequestBody DecisionAuthorization body){
        if(!Secrets.equal(secret,a.secret))throw Accounts.fail(HttpStatus.FORBIDDEN,"Forbidden");
        var rows=a.db.queryForList("select u.username,u.platform_admin,m.role from identity.account u join identity.membership m on m.user_id=u.id join identity.tenant t on t.id=m.tenant_id where u.id=? and t.id=? and u.enabled and u.verified and not u.must_change and t.enabled",body.userId(),body.tenantId());
        if(rows.isEmpty())return Map.of("allowed",false);
        var row=rows.get(0);var principal=new Accounts.Principal(body.userId(),body.tenantId(),body.userId(),(String)row.get("username"),(String)row.get("role"),Boolean.TRUE.equals(row.get("platform_admin")),false,false,"READ_WRITE");
        return Map.of("allowed",a.access.effective(principal).containsAll(Set.of("market.read","paper.read","paper.write")));
    }
    @PostMapping("/internal/v1/identity/operation") Object operation(@RequestHeader(value="X-Identity-Service-Secret",defaultValue="") String secret,@Valid @RequestBody Operation body){
        if(!Secrets.equal(secret,a.secret))throw Accounts.fail(HttpStatus.FORBIDDEN,"Forbidden");
        if(!body.path().startsWith("/api/")||body.path().contains("?")||!Set.of("GET","POST","PUT","PATCH","DELETE","HEAD").contains(body.method()))throw Accounts.fail(HttpStatus.BAD_REQUEST,"Invalid operation metadata");
        a.db.update("insert into identity.operation_log(user_id,tenant_id,method,path,status,duration_ms,trace_id) values(?,?,?,?,?,?,?)",body.userId(),body.tenantId(),body.method(),body.path(),body.status(),body.durationMs(),body.traceId());return Map.of("recorded",true);
    }
}
