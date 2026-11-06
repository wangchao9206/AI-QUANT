package com.aiquant.identity;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Path;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.*;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;

@EnabledIfEnvironmentVariable(named="IDENTITY_TEST_DATABASE_URL",matches=".*identity_test.*")
class AccountsIntegrationTests {
    JdbcTemplate db;TransactionTemplate tx;Accounts a;JavaMailSender sender;List<SimpleMailMessage> sent;
    final String secret="identity-integration-only-32-character-secret";
    @BeforeEach void setup(){
        var ds=new DriverManagerDataSource(System.getenv("IDENTITY_TEST_DATABASE_URL"),"identity_test","isolated-test-only");db=new JdbcTemplate(ds);db.execute("drop schema if exists identity cascade");
        Flyway.configure().dataSource(ds).schemas("identity").defaultSchema("identity").load().migrate();tx=new TransactionTemplate(new DataSourceTransactionManager(ds));
        sender=mock(JavaMailSender.class);sent=new ArrayList<>();doAnswer(i->{sent.add(new SimpleMailMessage(i.getArgument(0,SimpleMailMessage.class)));return null;}).when(sender).send(any(SimpleMailMessage.class));
        a=new Accounts(db,tx,new AccountMail(sender,"smtp.test","accounts@example.test","https://example.test"),new ObjectMapper(),secret);a.run(null);
    }
    String token(){String text=sent.get(sent.size()-1).getText();return text.substring(text.indexOf("#token=")+7).split("\\s")[0];}
    UUID verified(String name){a.register(name,name+"@example.test");a.verify(token());return db.queryForObject("select id from identity.account where username=?",UUID.class,name);}
    Accounts.Principal principal(Accounts.Login login,boolean write){return a.authenticate(login.token(),null,null,login.csrf(),write);}
    void status(HttpStatus expected,Runnable action){assertEquals(expected,assertThrows(ResponseStatusException.class,action::run).getStatusCode());}
    @Test void bootstrap_is_hashed_idempotent_and_requires_change(){
        var u=db.queryForMap("select * from identity.account where username='admin'");assertTrue(a.passwords.matches("admin123456",(String)u.get("password_hash")));assertNotEquals("admin123456",u.get("password_hash"));
        var login=a.login("admin","admin123456");var p=principal(login,false);assertTrue(p.mustChange());assertEquals(Accounts.LEGACY,p.tenant());
        status(HttpStatus.FORBIDDEN,()->new IdentityController(a,true).introspect(secret,new IdentityController.Introspection(login.token(),null,null,null,false,"/api/v1/market/instruments")));
        a.changePassword(p,"admin123456","a-long-new-password");a.run(null);assertFalse(principal(a.login("admin","a-long-new-password"),false).mustChange());
    }
    @Test void mailbox_must_be_verified_and_token_is_hashed_single_use(){
        a.register("alice","Alice@example.test");assertEquals("alice@example.test",sent.get(0).getTo()[0]);status(HttpStatus.FORBIDDEN,()->a.login("alice","alice123456"));String token=token();
        assertEquals(0,db.queryForObject("select count(*) from identity.challenge where token_hash=?",Integer.class,token));a.verify(token);status(HttpStatus.BAD_REQUEST,()->a.verify(token));
        var p=principal(a.login("alice@example.test","alice123456"),false);assertTrue(p.mustChange());assertNotEquals(Accounts.LEGACY,p.tenant());
    }
    @Test void missing_or_failed_smtp_rolls_back_registration(){
        var missing=new Accounts(db,tx,new AccountMail(sender,"","","https://example.test"),new ObjectMapper(),secret);status(HttpStatus.SERVICE_UNAVAILABLE,()->missing.register("alice","alice@example.test"));
        doThrow(new org.springframework.mail.MailSendException("private credential details")).when(sender).send(any(SimpleMailMessage.class));
        var error=assertThrows(ResponseStatusException.class,()->a.register("bobby","bobby@example.test"));assertFalse(error.getReason().contains("credential"));assertEquals(1,db.queryForObject("select count(*) from identity.account",Integer.class));
    }
    @Test void csrf_and_password_change_revoke_all_sessions_and_keys(){
        UUID id=verified("alice");var first=a.login("alice","alice123456");var second=a.login("alice","alice123456");status(HttpStatus.FORBIDDEN,()->a.authenticate(first.token(),null,null,"wrong",true));var p=principal(first,true);
        db.update("insert into identity.api_key(id,tenant_id,user_id,name,token_hash,scope,expires_at) values(?,?,?,'test',?,'READ',?)",UUID.randomUUID(),p.tenant(),id,Secrets.hash("test"),Timestamp.from(Instant.now().plusSeconds(100)));
        a.changePassword(p,"alice123456","alice-long-password");status(HttpStatus.UNAUTHORIZED,()->principal(first,false));status(HttpStatus.UNAUTHORIZED,()->principal(second,false));assertEquals(0,db.queryForObject("select count(*) from identity.api_key",Integer.class));
    }
    @Test void expired_reset_and_replayed_reset_are_rejected(){
        verified("alice");a.sendChallenge("alice@example.test","RESET");String expired=token();db.update("update identity.challenge set expires_at=now()-interval '1 second'");status(HttpStatus.BAD_REQUEST,()->a.reset(expired,"alice-long-password"));
        a.sendChallenge("alice@example.test","RESET");String reset=token();a.reset(reset,"alice-long-password");status(HttpStatus.BAD_REQUEST,()->a.reset(reset,"different-long-password"));assertFalse(principal(a.login("alice","alice-long-password"),false).mustChange());
    }
    @Test void tenant_membership_is_checked_online_and_last_owner_is_preserved(){
        UUID alice=verified("alice"),bob=verified("bobby");var la=a.login("alice","alice123456");var lb=a.login("bobby","bobby123456");var pa=principal(la,false);var pb=principal(lb,false);
        status(HttpStatus.FORBIDDEN,()->a.authenticate(la.token(),null,pb.tenant().toString(),null,false));a.member(pb,alice,"VIEWER",false);assertEquals("VIEWER",a.authenticate(la.token(),null,pb.tenant().toString(),null,false).role());
        status(HttpStatus.CONFLICT,()->a.member(pb,bob,"MEMBER",false));a.member(pb,alice,"MEMBER",true);status(HttpStatus.FORBIDDEN,()->a.authenticate(la.token(),null,pb.tenant().toString(),null,false));assertNotEquals(pa.tenant(),pb.tenant());
    }
    @Test void api_keys_are_scoped_revocable_and_cannot_manage_accounts(){
        verified("alice");var first=a.login("alice","alice123456");a.changePassword(principal(first,false),"alice123456","alice-long-password");var login=a.login("alice","alice-long-password");
        var req=new MockHttpServletRequest();req.setCookies(new jakarta.servlet.http.Cookie("aq_session",login.token()));req.addHeader("X-CSRF-Token",login.csrf());var c=new IdentityController(a,true);
        var issued=(Map<?,?>)c.key(new IdentityController.Key("integration","READ",30),req);String key=(String)issued.get("token");assertTrue(a.authenticate(null,key,null,null,false).apiKey());
        status(HttpStatus.FORBIDDEN,()->c.introspect(secret,new IdentityController.Introspection(null,key,null,null,true,"/api/v1/paper/sessions")));
        var apiReq=new MockHttpServletRequest();apiReq.addHeader("Authorization","Bearer "+key);status(HttpStatus.FORBIDDEN,()->a.require(apiReq,false,false));c.revokeKey((UUID)issued.get("id"),req);status(HttpStatus.UNAUTHORIZED,()->a.authenticate(null,key,null,null,false));
    }
    @Test void failed_logins_do_not_roll_back_rate_limits(){for(int i=0;i<10;i++)status(HttpStatus.UNAUTHORIZED,()->a.login("unknown","bad-password"));status(HttpStatus.TOO_MANY_REQUESTS,()->a.login("unknown","bad-password"));}
    @Test void admin_can_bind_real_email_only_after_confirming_new_mailbox(){
        var first=a.login("admin","admin123456");a.changePassword(principal(first,false),"admin123456","admin-long-password");var login=a.login("admin","admin-long-password");var p=principal(login,false);
        a.requestEmail(p,"owner@example.test","admin-long-password");assertNull(a.account(p.user()).get("email"));String token=token();assertTrue(sent.get(sent.size()-1).getText().contains("/auth/verify-email#token="));
        a.verifyEmail(token);assertEquals("owner@example.test",a.account(p.user()).get("email"));status(HttpStatus.UNAUTHORIZED,()->principal(login,false));status(HttpStatus.BAD_REQUEST,()->a.verifyEmail(token));
    }
    @Test void migrations_protect_private_rows_and_cross_tenant_foreign_keys(){
        var ds=db.getDataSource();db.execute("drop schema if exists paper_trading cascade");db.execute("drop schema if exists chanlun cascade");
        for(String service:List.of("paper-trading-service","chanlun-service")){String schema=service.startsWith("paper")?"paper_trading":"chanlun";
            var config=Flyway.configure().dataSource(ds).schemas(schema).defaultSchema(schema).locations("filesystem:"+Path.of("..",service,"src/main/resources/db/migration").toAbsolutePath());
            config.target("7").load().migrate();
            if(schema.equals("chanlun"))db.update("insert into chanlun.analysis_run(id,client_request_id,engine_id,dataset_id,observed_bars,status) values(?,?,'native','legacy',50,'QUEUED')",UUID.randomUUID(),UUID.randomUUID());
            config.target("latest").load().migrate();}
        UUID one=UUID.randomUUID(),two=UUID.randomUUID(),run=UUID.randomUUID();tenant(one,()->db.update("insert into chanlun.analysis_run(id,client_request_id,engine_id,dataset_id,observed_bars,status) values(?,?,'native','test',50,'QUEUED')",run,UUID.randomUUID()));
        tenant(two,()->{assertEquals(0,db.queryForObject("select count(*) from chanlun.analysis_run",Integer.class));assertEquals(0,db.update("delete from chanlun.analysis_run where id=?",run));return 0;});
        assertThrows(org.springframework.dao.DataAccessException.class,()->tenant(two,()->db.update("insert into chanlun.judgment(id,client_request_id,run_id,outlook,content,evidence) values(?,?,?,'WAIT','cross tenant','{}')",UUID.randomUUID(),UUID.randomUUID(),run)));
        tenant(one,()->{assertEquals(1,db.queryForObject("select count(*) from chanlun.analysis_run",Integer.class));return 0;});assertEquals("identity_test",db.queryForObject("select current_user",String.class));
        tenant(Accounts.LEGACY,()->{assertEquals(1,db.queryForObject("select count(*) from chanlun.analysis_run where dataset_id='legacy'",Integer.class));return 0;});
        tenant(two,()->{assertEquals(2,db.queryForObject("select count(*) from paper_trading.reading_book",Integer.class));assertEquals(0,db.update("delete from paper_trading.reading_book where slug is not null"));return 0;});
        UUID book=UUID.randomUUID();tenant(one,()->db.update("insert into paper_trading.reading_book(id,client_request_id,title) values(?,?,'private')",book,UUID.randomUUID().toString()));
        assertThrows(org.springframework.dao.DataAccessException.class,()->tenant(two,()->db.update("insert into paper_trading.reading_reflection(id,book_id,client_request_id,category,content) values(?,?,?,'IDEA','cross tenant')",UUID.randomUUID(),book,UUID.randomUUID().toString())));
        int all=db.queryForObject("select count(*) from pg_tables where schemaname in ('paper_trading','chanlun') and tablename<>'flyway_schema_history'",Integer.class);
        assertEquals(all,db.queryForObject("select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname in ('paper_trading','chanlun') and c.relkind='r' and c.relrowsecurity and c.relforcerowsecurity",Integer.class));
    }
    @Test void real_http_login_cookie_csrf_logout_and_health_work_without_smtp()throws Exception{
        try(var app=new org.springframework.boot.builder.SpringApplicationBuilder(IdentityApplication.class).run(
            "--server.port=0","--spring.datasource.url="+System.getenv("IDENTITY_TEST_DATABASE_URL"),"--spring.datasource.username=identity_test","--spring.datasource.password=isolated-test-only",
            "--identity.secret="+secret,"--identity.cookie-secure=false","--spring.mail.host=","--identity.smtp-from=","--spring.main.banner-mode=off")){
            int port=((org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext)app).getWebServer().getPort();String base="http://127.0.0.1:"+port;
            var cookies=new java.net.CookieManager(null,java.net.CookiePolicy.ACCEPT_ALL);var client=java.net.http.HttpClient.newBuilder().cookieHandler(cookies).build();
            var health=client.send(java.net.http.HttpRequest.newBuilder(java.net.URI.create(base+"/actuator/health")).build(),java.net.http.HttpResponse.BodyHandlers.ofString());assertEquals(200,health.statusCode());
            var login=client.send(java.net.http.HttpRequest.newBuilder(java.net.URI.create(base+"/api/v1/auth/login")).header("Content-Type","application/json").POST(java.net.http.HttpRequest.BodyPublishers.ofString("{\"identifier\":\"admin\",\"password\":\"admin123456\"}")).build(),java.net.http.HttpResponse.BodyHandlers.ofString());assertEquals(200,login.statusCode());
            assertTrue(login.headers().allValues("set-cookie").stream().anyMatch(v->v.startsWith("aq_session=")&&v.toLowerCase().contains("httponly")));
            String csrf=cookies.getCookieStore().getCookies().stream().filter(c->c.getName().equals("aq_csrf")).findFirst().orElseThrow().getValue();
            var invalid=client.send(java.net.http.HttpRequest.newBuilder(java.net.URI.create(base+"/api/v1/auth/logout")).header("Content-Type","application/json").POST(java.net.http.HttpRequest.BodyPublishers.ofString("{}")).build(),java.net.http.HttpResponse.BodyHandlers.ofString());assertEquals(403,invalid.statusCode());
            var logout=client.send(java.net.http.HttpRequest.newBuilder(java.net.URI.create(base+"/api/v1/auth/logout")).header("Content-Type","application/json").header("X-CSRF-Token",csrf).POST(java.net.http.HttpRequest.BodyPublishers.ofString("{}")).build(),java.net.http.HttpResponse.BodyHandlers.ofString());assertEquals(200,logout.statusCode());
            var operations=db.queryForList("select user_id,method,path,status,trace_id from identity.operation_log order by id");
            assertTrue(operations.stream().anyMatch(row->row.get("path").equals("/api/v1/auth/login")&&row.get("status").equals(200)&&row.get("user_id")!=null));
            assertTrue(operations.stream().anyMatch(row->row.get("path").equals("/api/v1/auth/logout")&&row.get("status").equals(403)));
            assertFalse(operations.toString().contains("admin123456"));assertFalse(operations.toString().contains(csrf));
        }
    }
    <T>T tenant(UUID tenant,java.util.function.Supplier<T> work){try{return com.aiquant.tenancy.TenantTransactions.run(db,tx,tenant,work);}finally{assertNull(com.aiquant.tenancy.TenantContext.current());}}
}
