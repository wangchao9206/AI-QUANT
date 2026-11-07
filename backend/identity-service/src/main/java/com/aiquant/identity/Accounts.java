package com.aiquant.identity;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import java.nio.charset.StandardCharsets;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.scheduling.annotation.Scheduled;

@Service
class Accounts implements ApplicationRunner {
    static final UUID LEGACY=UUID.fromString("00000000-0000-0000-0000-000000000001");
    static final Set<String> ROLES=Set.of("OWNER","ADMIN","MEMBER","VIEWER");
    final JdbcTemplate db; final TransactionTemplate tx; final AccountMail mail; final ObjectMapper mapper;
    final BCryptPasswordEncoder passwords=new BCryptPasswordEncoder(12);
    final String secret; final String dummyHash;
    final AccessControl access;
    Accounts(JdbcTemplate db,TransactionTemplate tx,AccountMail mail,ObjectMapper mapper,@Value("${identity.secret}") String secret){
        this.db=db;this.tx=tx;this.mail=mail;this.mapper=mapper;this.secret=secret;
        this.access=new AccessControl(db,mapper);
        if(secret.length()<32)throw new IllegalArgumentException("IDENTITY_INTERNAL_SECRET must contain at least 32 characters");
        dummyHash=passwords.encode(Secrets.token());
    }
    static ResponseStatusException fail(HttpStatus status,String message){return new ResponseStatusException(status,message);}
    static String username(String value){String s=value==null?"":value.strip().toLowerCase(Locale.ROOT);if(!s.matches("[a-z][a-z0-9_]{2,31}"))throw fail(HttpStatus.BAD_REQUEST,"账号需为 3～32 位小写字母、数字或下划线，且以字母开头。");return s;}
    static String email(String value){String s=value==null?"":value.strip().toLowerCase(Locale.ROOT);if(s.length()>254||!s.matches("[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+"))throw fail(HttpStatus.BAD_REQUEST,"请输入有效邮箱地址。");return s;}
    void newPassword(String name,String password){if(password==null||password.length()<12||password.length()>72||password.getBytes(StandardCharsets.UTF_8).length>72||password.equals(name+"123456"))throw fail(HttpStatus.BAD_REQUEST,"新密码需为 12～72 字节，且不能继续使用初始密码。");}
    @Override public void run(ApplicationArguments args){tx.executeWithoutResult(status->{
        db.execute("select pg_advisory_xact_lock(71203001)");
        db.update("insert into identity.tenant(id,name) values(?,'默认工作空间') on conflict(id) do nothing",LEGACY);
        if(db.queryForObject("select count(*) from identity.account where username='admin'",Integer.class)==0){
            UUID id=UUID.randomUUID();db.update("insert into identity.account(id,username,password_hash,verified,platform_admin,must_change) values(?,'admin',?,true,true,true)",id,passwords.encode("admin123456"));
            db.update("insert into identity.membership(tenant_id,user_id,role) values(?,?,'OWNER')",LEGACY,id);audit(id,LEGACY,"BOOTSTRAP_ADMIN",id.toString());
        }
    });}
    void limit(String key,int max){long bucket=Instant.now().getEpochSecond()/600;
        int attempts=db.queryForObject("insert into identity.rate_limit(key_hash,bucket,attempts) values(?,?,1) on conflict(key_hash,bucket) do update set attempts=identity.rate_limit.attempts+1 returning attempts",Integer.class,Secrets.hash(key),bucket);
        if(attempts>max)throw fail(HttpStatus.TOO_MANY_REQUESTS,"操作过于频繁，请 10 分钟后重试。");
    }
    void audit(UUID uid,UUID tenant,String action,String target){db.update("insert into identity.audit(user_id,tenant_id,action,target) values(?,?,?,?)",uid,tenant,action,target);}
    Map<String,Object> account(UUID id){var rows=db.queryForList("select * from identity.account where id=?",id);if(rows.isEmpty())throw fail(HttpStatus.UNAUTHORIZED,"登录已失效。");return rows.get(0);}
    void challenge(Map<String,Object> user,String purpose){
        limit("smtp-global",100);
        UUID id=(UUID)user.get("id");String token=Secrets.token();
        db.update("delete from identity.challenge where user_id=? and purpose=?",id,purpose);
        db.update("insert into identity.challenge(token_hash,user_id,purpose,expires_at) values(?,?,?,?)",Secrets.hash(token),id,purpose,Timestamp.from(Instant.now().plus(30,ChronoUnit.MINUTES)));
        mail.send((String)user.get("email"),purpose,token);
    }
    void register(String name,String address){String user=username(name),em=email(address);limit("register:"+em,3);limit("register-name:"+user,5);mail.available();
        tx.executeWithoutResult(status->{
            if(!db.queryForList("select id from identity.account where username=? or email=?",user,em).isEmpty())throw fail(HttpStatus.CONFLICT,"该账号或邮箱已被使用，可尝试登录、重新发送验证邮件或找回密码。");
            UUID id=UUID.randomUUID();db.update("insert into identity.account(id,username,email,password_hash) values(?,?,?,?)",id,user,em,passwords.encode(user+"123456"));
            challenge(account(id),"VERIFY");audit(id,null,"REGISTER",id.toString());
        });
    }
    void sendChallenge(String address,String purpose){String em=email(address);limit("mail:"+em,3);mail.available();
        tx.executeWithoutResult(status->{var users=db.queryForList("select * from identity.account where email=? and enabled",em);
            if(!users.isEmpty()&&(purpose.equals("VERIFY")?!Boolean.TRUE.equals(users.get(0).get("verified")):Boolean.TRUE.equals(users.get(0).get("verified"))))challenge(users.get(0),purpose);
        });
    }
    Map<String,Object> consume(String token,String purpose){if(token==null||!token.matches("[A-Za-z0-9_-]{43}"))throw fail(HttpStatus.BAD_REQUEST,"链接无效或已过期。");
        var rows=db.queryForList("delete from identity.challenge where token_hash=? and purpose=? and expires_at>now() returning user_id",Secrets.hash(token),purpose);
        if(rows.isEmpty())throw fail(HttpStatus.BAD_REQUEST,"链接无效、已过期或已使用。");return account((UUID)rows.get(0).get("user_id"));
    }
    UUID createTenant(UUID user,String name){String title=name==null?"":name.strip();if(title.isEmpty()||title.length()>80)throw fail(HttpStatus.BAD_REQUEST,"工作空间名称需为 1～80 个字符。");
        UUID id=UUID.randomUUID();db.update("insert into identity.tenant(id,name) values(?,?)",id,title);db.update("insert into identity.membership(tenant_id,user_id,role) values(?,?,'OWNER')",id,user);audit(user,id,"TENANT_CREATE",id.toString());return id;
    }
    void verify(String token){tx.executeWithoutResult(status->{var user=consume(token,"VERIFY");UUID id=(UUID)user.get("id");
        if(!Boolean.TRUE.equals(user.get("enabled")))throw fail(HttpStatus.FORBIDDEN,"账号已停用。");
        if(!Boolean.TRUE.equals(user.get("verified"))){db.update("update identity.account set verified=true where id=?",id);createTenant(id,user.get("username")+" 的工作空间");}
        audit(id,null,"EMAIL_VERIFIED",id.toString());
    });}
    record Login(String token,String csrf,UUID user){}
    Login login(String identifier,String password){String name=identifier==null?"":identifier.strip().toLowerCase(Locale.ROOT);limit("login:"+name,10);
        var users=db.queryForList("select * from identity.account where username=? or email=?",name,name);var u=users.isEmpty()?null:users.get(0);
        boolean correct=password!=null&&password.length()<=128&&passwords.matches(password,u==null?dummyHash:(String)u.get("password_hash"));
        if(u==null||!correct||!Boolean.TRUE.equals(u.get("enabled"))){audit(null,null,"LOGIN_FAILED",Secrets.hash(name));throw fail(HttpStatus.UNAUTHORIZED,"账号或密码错误，或账号已停用。");}
        if(!Boolean.TRUE.equals(u.get("verified")))throw fail(HttpStatus.FORBIDDEN,"请先验证邮箱。");
        UUID id=(UUID)u.get("id");return tx.execute(status->{
            var memberships=tenants(id);if(memberships.isEmpty())throw fail(HttpStatus.FORBIDDEN,"没有可用的工作空间，请联系管理员。");
            String token=Secrets.token(),csrf=Secrets.token();UUID tenant=(UUID)memberships.get(0).get("id");
            db.update("insert into identity.session(id,token_hash,csrf_hash,user_id,tenant_id,expires_at) values(?,?,?,?,?,?)",UUID.randomUUID(),Secrets.hash(token),Secrets.hash(csrf),id,tenant,Timestamp.from(Instant.now().plus(7,ChronoUnit.DAYS)));
            audit(id,tenant,"LOGIN",id.toString());return new Login(token,csrf,id);
        });
    }
    static String cookie(HttpServletRequest request,String name){if(request.getCookies()!=null)for(Cookie c:request.getCookies())if(name.equals(c.getName()))return c.getValue();return null;}
    record Principal(UUID user,UUID tenant,UUID credential,String username,String role,boolean platformAdmin,boolean mustChange,boolean apiKey,String scope){}
    Principal authenticate(String session,String bearer,String tenant,String csrf,boolean mutation){
        boolean key=bearer!=null&&!bearer.isBlank();String token=key?bearer:session;
        if(token==null||token.length()>120)throw fail(HttpStatus.UNAUTHORIZED,"请先登录。");
        var rows=db.queryForList(key?"select k.*,a.username,a.verified,a.must_change,a.enabled as user_enabled,a.platform_admin from identity.api_key k join identity.account a on a.id=k.user_id where k.token_hash=? and k.expires_at>now()":"select s.*,a.username,a.verified,a.must_change,a.enabled as user_enabled,a.platform_admin from identity.session s join identity.account a on a.id=s.user_id where s.token_hash=? and s.expires_at>now()",Secrets.hash(token));
        if(rows.isEmpty())throw fail(HttpStatus.UNAUTHORIZED,"登录或接口密钥已失效。");var row=rows.get(0);
        if(!Boolean.TRUE.equals(row.get("user_enabled"))||!Boolean.TRUE.equals(row.get("verified")))throw fail(HttpStatus.UNAUTHORIZED,"账号不可用。");
        if(mutation&&!key&&!Secrets.equal(Secrets.hash(csrf==null?"":csrf),(String)row.get("csrf_hash")))throw fail(HttpStatus.FORBIDDEN,"请求校验失败，请刷新页面后重试。");
        UUID tid=(UUID)row.get("tenant_id");
        if(tenant!=null&&!tenant.isBlank()){try{UUID requested=UUID.fromString(tenant);if(key&&!tid.equals(requested))throw fail(HttpStatus.FORBIDDEN,"接口密钥不属于所选工作空间。");tid=requested;}catch(IllegalArgumentException e){throw fail(HttpStatus.BAD_REQUEST,"工作空间标识无效。");}}
        var memberships=db.queryForList("select m.role from identity.membership m join identity.tenant t on t.id=m.tenant_id where m.tenant_id=? and m.user_id=? and t.enabled",tid,row.get("user_id"));
        if(memberships.isEmpty())throw fail(HttpStatus.FORBIDDEN,"无权访问该工作空间。");String role=(String)memberships.get(0).get("role");
        return new Principal((UUID)row.get("user_id"),tid,(UUID)row.get("id"),(String)row.get("username"),role,Boolean.TRUE.equals(row.get("platform_admin")),Boolean.TRUE.equals(row.get("must_change")),key,key?(String)row.get("scope"):"READ_WRITE");
    }
    Principal require(HttpServletRequest req,boolean mutation,boolean allowChange){
        String auth=req.getHeader("Authorization");String bearer=auth!=null&&auth.startsWith("Bearer ")?auth.substring(7):null;
        Principal p=authenticate(cookie(req,"aq_session"),bearer,req.getHeader("X-Tenant-Id"),req.getHeader("X-CSRF-Token"),mutation);
        if(p.apiKey())throw fail(HttpStatus.FORBIDDEN,"账号管理需要浏览器登录。");
        req.setAttribute("identity.user",p.user());req.setAttribute("identity.tenant",p.tenant());
        if(p.mustChange()&&!allowChange)throw fail(HttpStatus.FORBIDDEN,"请先修改初始密码。");return p;
    }
    List<Map<String,Object>> tenants(UUID user){return db.queryForList("select t.id,t.name,m.role from identity.tenant t join identity.membership m on m.tenant_id=t.id where m.user_id=? and t.enabled order by t.created_at,t.id",user);}
    Map<String,Object> me(Principal p){var u=account(p.user());var out=new LinkedHashMap<String,Object>();out.put("id",p.user());out.put("username",p.username());out.put("displayName",u.get("display_name"));out.put("email",u.get("email"));out.put("platformAdmin",p.platformAdmin());out.put("mustChangePassword",p.mustChange());out.put("tenantId",p.tenant());out.put("role",p.role());out.put("tenants",tenants(p.user()));out.put("permissions",access.effective(p));out.put("menus",access.navigation(p));return out;}
    void changePassword(Principal p,String old,String next){var u=account(p.user());limit("password:"+p.user(),10);
        if(old==null||old.length()>128||!passwords.matches(old,(String)u.get("password_hash")))throw fail(HttpStatus.BAD_REQUEST,"原密码不正确。");newPassword(p.username(),next);
        tx.executeWithoutResult(status->{db.update("update identity.account set password_hash=?,must_change=false where id=?",passwords.encode(next),p.user());revokeAll(p.user());audit(p.user(),p.tenant(),"PASSWORD_CHANGE",p.user().toString());});
    }
    void reset(String token,String password){tx.executeWithoutResult(status->{var u=consume(token,"RESET");UUID id=(UUID)u.get("id");if(!Boolean.TRUE.equals(u.get("enabled")))throw fail(HttpStatus.FORBIDDEN,"账号已停用。");newPassword((String)u.get("username"),password);
        db.update("update identity.account set password_hash=?,must_change=false where id=?",passwords.encode(password),id);revokeAll(id);audit(id,null,"PASSWORD_RESET",id.toString());
    });}
    void requestEmail(Principal p,String address,String password){
        String em=email(address);limit("email-change:"+p.user(),3);mail.available();var u=account(p.user());
        if(password==null||password.length()>128||!passwords.matches(password,(String)u.get("password_hash")))throw fail(HttpStatus.BAD_REQUEST,"密码不正确。");
        tx.executeWithoutResult(status->{if(!db.queryForList("select id from identity.account where email=?",em).isEmpty())throw fail(HttpStatus.CONFLICT,"邮箱已被使用。");
            String token=Secrets.token();db.update("delete from identity.challenge where user_id=? and purpose='EMAIL'",p.user());
            db.update("insert into identity.challenge(token_hash,user_id,purpose,target_email,expires_at) values(?,?,'EMAIL',?,?)",Secrets.hash(token),p.user(),em,Timestamp.from(Instant.now().plusSeconds(1800)));
            mail.send(em,"EMAIL",token);audit(p.user(),p.tenant(),"EMAIL_CHANGE_REQUEST",p.user().toString());
        });
    }
    void verifyEmail(String token){tx.executeWithoutResult(status->{
        if(token==null||!token.matches("[A-Za-z0-9_-]{43}"))throw fail(HttpStatus.BAD_REQUEST,"验证链接无效。");
        var rows=db.queryForList("delete from identity.challenge where token_hash=? and purpose='EMAIL' and expires_at>now() returning user_id,target_email",Secrets.hash(token));
        if(rows.isEmpty())throw fail(HttpStatus.BAD_REQUEST,"链接无效、已过期或已使用。");var row=rows.get(0);UUID id=(UUID)row.get("user_id");
        if(!Boolean.TRUE.equals(account(id).get("enabled")))throw fail(HttpStatus.FORBIDDEN,"账号已停用。");
        db.update("update identity.account set email=?,verified=true where id=?",row.get("target_email"),id);revokeAll(id);audit(id,null,"EMAIL_CHANGED",id.toString());
    });}
    void revokeAll(UUID user){db.update("delete from identity.session where user_id=?",user);db.update("delete from identity.api_key where user_id=?",user);db.update("delete from identity.challenge where user_id=?",user);}
    void tenantAdmin(Principal p){if(!Set.of("OWNER","ADMIN").contains(p.role()))throw fail(HttpStatus.FORBIDDEN,"需要工作空间管理员权限。");}
    void admin(Principal p){if(!p.platformAdmin())throw fail(HttpStatus.FORBIDDEN,"需要平台管理员权限。");}
    void member(Principal p,UUID user,String role,boolean remove){tenantAdmin(p);if(!ROLES.contains(role))throw fail(HttpStatus.BAD_REQUEST,"角色无效。");
        tx.executeWithoutResult(status->{db.queryForObject("select id from identity.tenant where id=? for update",UUID.class,p.tenant());
            var before=db.queryForList("select role from identity.membership where tenant_id=? and user_id=?",p.tenant(),user);String previous=before.isEmpty()?null:(String)before.get(0).get("role");
            if(!p.role().equals("OWNER")&&(role.equals("OWNER")||"OWNER".equals(previous)||"ADMIN".equals(previous)||(!remove&&role.equals("ADMIN"))))throw fail(HttpStatus.FORBIDDEN,"仅所有者可以管理管理员或所有者。");
            if("OWNER".equals(previous)&&(remove||!role.equals("OWNER"))&&db.queryForObject("select count(*) from identity.membership where tenant_id=? and role='OWNER'",Integer.class,p.tenant())<=1)throw fail(HttpStatus.CONFLICT,"工作空间必须保留至少一名所有者。");
            if(remove){db.update("delete from identity.membership where tenant_id=? and user_id=?",p.tenant(),user);db.update("delete from identity.session where tenant_id=? and user_id=?",p.tenant(),user);db.update("delete from identity.api_key where tenant_id=? and user_id=?",p.tenant(),user);}
            else {var u=account(user);if(!Boolean.TRUE.equals(u.get("verified"))||!Boolean.TRUE.equals(u.get("enabled")))throw fail(HttpStatus.BAD_REQUEST,"仅可添加已验证且启用的账号。");db.update("insert into identity.membership(tenant_id,user_id,role) values(?,?,?) on conflict(tenant_id,user_id) do update set role=excluded.role",p.tenant(),user,role);}
            audit(p.user(),p.tenant(),remove?"MEMBER_REMOVE":"MEMBER_ROLE",user.toString());
        });
    }
    String signed(Principal p){try{var data=Map.of("userId",p.user().toString(),"tenantId",p.tenant().toString(),"role",p.role(),"permissions",access.effective(p),"expiresAt",Instant.now().plusSeconds(30).getEpochSecond());String payload=Base64.getUrlEncoder().withoutPadding().encodeToString(mapper.writeValueAsBytes(data));return payload+"."+Secrets.sign(payload,secret);}catch(Exception e){throw new IllegalStateException(e);}}
    @Scheduled(fixedDelay=3600000) void cleanup(){db.update("delete from identity.rate_limit where bucket<?",Instant.now().getEpochSecond()/600-2);db.update("delete from identity.challenge where expires_at<now()");db.update("delete from identity.session where expires_at<now()");db.update("delete from identity.api_key where expires_at<now()");}
}
