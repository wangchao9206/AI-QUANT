package com.aiquant.identity;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;

/** Actual isolated PostgreSQL: real RLS, sessions/CSRF, revisions and first-insert races. */
@EnabledIfEnvironmentVariable(named="IDENTITY_TEST_DATABASE_URL",matches="jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/identity_test.*")
class WorkspaceDocumentsIntegrationTests {
    AccountsIntegrationTests f;WorkspaceDocuments store;WorkspaceController controller;Accounts.Principal owner;Accounts.Login login;
    @BeforeEach void setup(){f=new AccountsIntegrationTests();f.setup();f.db.update("update identity.account set must_change=false where username='admin'");login=f.a.login("admin","admin123456");owner=f.principal(login,false);store=new WorkspaceDocuments(f.a);controller=new WorkspaceController(f.a,store);}
    JsonNode json(String body){try{return f.a.mapper.readTree(body);}catch(Exception e){throw new RuntimeException(e);}}
    JsonNode preferences(String mode){return json("{\"schemaVersion\":1,\"experience\":\""+mode+"\"}");}
    JsonNode chart(){return json("""
        {"schemaVersion":1,"layout":{"theme":"dark","mainType":"candle","subChart":"vol","maPeriods":[5,10,20,60,180],"autoGroups":["REGRESSION","TREND","HORIZONTAL"]},"items":[{"id":"line-1","kind":"LINE","anchors":[{"timestamp":"2026-11-06T09:00:00+08:00","price":3000},{"timestamp":"2026-11-06T09:15:00+08:00","price":3005}]}]}
        """);}
    WorkspaceDocuments.Save save(long revision,JsonNode content){return new WorkspaceDocuments.Save(UUID.randomUUID(),revision,content);}
    long revision(Map<String,Object> doc){return ((Number)doc.get("revision")).longValue();}
    Accounts.Principal other(UUID tenant,String role){UUID user=UUID.randomUUID();f.db.update("insert into identity.account(id,username,password_hash,verified,must_change) values(?,?,?,true,false)",user,"seed"+user.toString().substring(0,8),f.a.account(owner.user()).get("password_hash"));f.db.update("insert into identity.membership(tenant_id,user_id,role) values(?,?,?)",tenant,user,role);return new Accounts.Principal(user,tenant,user,"seed",role,false,false,false,"READ_WRITE");}
    UUID tenant(){UUID id=UUID.randomUUID();f.db.update("insert into identity.tenant(id,name) values(?,'isolated private workspace')",id);return id;}
    void status(int code,Runnable work){assertEquals(code,assertThrows(ResponseStatusException.class,work::run).getStatusCode().value());}
    MockHttpServletRequest request(boolean csrf){var req=new MockHttpServletRequest();req.setCookies(new jakarta.servlet.http.Cookie("aq_session",login.token()));if(csrf)req.addHeader("X-CSRF-Token",login.csrf());return req;}
    @Test void savesPrivateSettingsAndExactTimePriceAnchorsWithoutCreatingBusinessRecords(){
        assertEquals(0,revision(store.get(owner,store.preferences())));var first=store.save(owner,store.preferences(),save(0,preferences("PRO")));assertEquals(1,revision(first));
        var drawn=store.save(owner,store.chart("RB2701","900"),save(0,chart()));assertEquals(chart(),drawn.get("content"));assertEquals("2026-11-06T09:00:00+08:00",((JsonNode)drawn.get("content")).at("/items/0/anchors/0/timestamp").asText());
        assertEquals(0,revision(store.get(owner,store.chart("RB2705","900"))));assertEquals(0,revision(store.get(owner,store.chart("RB2701","DAY"))));
    }
    @Test void ownerAndTenantAreBothRequiredEvenWhenTheOtherUserIsAnAdmin(){
        store.save(owner,store.preferences(),save(0,preferences("PRO")));var admin=other(owner.tenant(),"ADMIN");assertEquals(0,revision(store.get(admin,store.preferences())));
        UUID otherTenant=tenant();f.db.update("insert into identity.membership(tenant_id,user_id,role) values(?,?,'OWNER')",otherTenant,owner.user());var alternate=new Accounts.Principal(owner.user(),otherTenant,owner.credential(),owner.username(),"OWNER",true,false,false,"READ_WRITE");assertEquals(0,revision(store.get(alternate,store.preferences())));
    }
    @Test void csrfBrowserSessionAndActiveMembershipAreCheckedByThePublicController(){
        status(401,()->controller.preferences(new MockHttpServletRequest()));status(403,()->controller.preferences(save(0,preferences("PRO")),request(false)));
        controller.preferences(save(0,preferences("PRO")),request(true));f.db.update("delete from identity.session where id=?",owner.credential());status(401,()->controller.preferences(request(false)));
    }
    @Test void removingMembershipRetainsPrivateRecordsAndPreventsFurtherAccess(){
        var member=other(owner.tenant(),"MEMBER");store.save(member,store.preferences(),save(0,preferences("PRO")));f.db.update("delete from identity.membership where tenant_id=? and user_id=?",member.tenant(),member.user());status(403,()->store.get(member,store.preferences()));assertEquals(1,f.db.queryForObject("select count(*) from identity.workspace_document",Integer.class));
    }
    @Test void personalPreferencesDoNotGrantTradeOrMarketPermissions(){
        var viewer=other(owner.tenant(),"VIEWER");assertEquals(1,revision(store.save(viewer,store.preferences(),save(0,preferences("PRO")))));assertFalse(f.a.access.effective(viewer).contains("market.write"));
    }
    @Test void casIdempotencyAndOldRetriesCannotSilentlyOverwriteNewerDocuments(){
        var first=save(0,preferences("PRO"));var initial=store.save(owner,store.preferences(),first);assertEquals(initial,store.save(owner,store.preferences(),first));
        status(409,()->store.save(owner,store.preferences(),save(0,preferences("SIMPLE"))));store.save(owner,store.preferences(),save(1,preferences("SIMPLE")));
        status(409,()->store.save(owner,store.preferences(),first));assertEquals(preferences("SIMPLE"),store.get(owner,store.preferences()).get("content"));assertEquals(2,f.db.queryForObject("select count(*) from identity.workspace_revision",Integer.class));
        status(409,()->store.save(owner,store.chart("RB2701","900"),new WorkspaceDocuments.Save(first.commandId(),0,chart())));
    }
    @Test void simultaneousFirstSavesCannotBothClaimRevisionOne()throws Exception{
        var pool=Executors.newFixedThreadPool(2);var start=new CountDownLatch(1);
        try{Callable<Integer> work=()->{start.await();try{store.save(owner,store.preferences(),save(0,preferences("PRO")));return 200;}catch(ResponseStatusException e){return e.getStatusCode().value();}};
            var a=pool.submit(work);var b=pool.submit(work);start.countDown();var result=List.of(a.get(10,TimeUnit.SECONDS),b.get(10,TimeUnit.SECONDS));assertEquals(1,Collections.frequency(result,200));assertEquals(1,Collections.frequency(result,409));assertEquals(1,f.db.queryForObject("select count(*) from identity.workspace_revision",Integer.class));
        }finally{pool.shutdownNow();}
    }
    @Test void reusedCommandsAcrossDifferentDocumentsReturnConflictEvenWhenConcurrent()throws Exception{
        var command=UUID.randomUUID();var pool=Executors.newFixedThreadPool(2);var start=new CountDownLatch(1);
        try{Callable<Integer> preferences=()->{start.await();try{store.save(owner,store.preferences(),new WorkspaceDocuments.Save(command,0,preferences("PRO")));return 200;}catch(ResponseStatusException e){return e.getStatusCode().value();}};
            Callable<Integer> chart=()->{start.await();try{store.save(owner,store.chart("RB2701","900"),new WorkspaceDocuments.Save(command,0,chart()));return 200;}catch(ResponseStatusException e){return e.getStatusCode().value();}};
            var a=pool.submit(preferences);var b=pool.submit(chart);start.countDown();var result=List.of(a.get(10,TimeUnit.SECONDS),b.get(10,TimeUnit.SECONDS));assertEquals(1,Collections.frequency(result,200));assertEquals(1,Collections.frequency(result,409));assertEquals(1,f.db.queryForObject("select count(*) from identity.workspace_document",Integer.class));
        }finally{pool.shutdownNow();}
    }
    @Test void chartAccessUsesCurrentPermissionsAndDisabledAccountsCannotReadStoredPreferences(){
        var member=other(owner.tenant(),"MEMBER");store.save(member,store.chart("RB2701","900"),save(0,chart()));var role=UUID.randomUUID();
        f.db.update("insert into identity.access_role(id,tenant_id,name,permissions) values(?,?,'no market','[\"paper.read\"]')",role,member.tenant());f.db.update("insert into identity.role_assignment(tenant_id,user_id,role_id) values(?,?,?)",member.tenant(),member.user(),role);
        status(403,()->store.get(member,store.chart("RB2701","900")));status(403,()->store.save(member,store.chart("RB2701","900"),save(1,chart())));store.save(member,store.preferences(),save(0,preferences("PRO")));
        f.db.update("update identity.account set enabled=false where id=?",member.user());status(403,()->store.get(member,store.preferences()));assertEquals(2,f.db.queryForObject("select count(*) from identity.workspace_document",Integer.class));
    }
    @Test void forceRlsAndGrantsBlockCrossOwnerReadsWritesAndAccountAdministration(){
        store.save(owner,store.preferences(),save(0,preferences("PRO")));var other=other(owner.tenant(),"MEMBER");
        f.tx.executeWithoutResult(s->{f.db.execute("set local role aiquant_workspace");f.db.queryForObject("select set_config('app.workspace_tenant',?,true)",String.class,other.tenant().toString());f.db.queryForObject("select set_config('app.workspace_owner',?,true)",String.class,other.user().toString());assertEquals(0,f.db.queryForObject("select count(*) from identity.workspace_document",Integer.class));});
        assertThrows(RuntimeException.class,()->f.tx.executeWithoutResult(s->{f.db.execute("set local role aiquant_workspace");f.db.queryForObject("select set_config('app.workspace_tenant',?,true)",String.class,other.tenant().toString());f.db.queryForObject("select set_config('app.workspace_owner',?,true)",String.class,other.user().toString());f.db.update("insert into identity.workspace_document(tenant_id,owner_id,kind,document_key,revision,content) values(?,?,'PREFERENCES','WORKSPACE',1,'{}')",owner.tenant(),owner.user());}));
        assertFalse(f.db.queryForObject("select has_table_privilege('aiquant_workspace','identity.account','SELECT')",Boolean.class));assertFalse(f.db.queryForObject("select has_column_privilege('aiquant_workspace','identity.workspace_document','owner_id','UPDATE')",Boolean.class));assertFalse(f.db.queryForObject("select has_table_privilege('aiquant_workspace','identity.workspace_revision','UPDATE')",Boolean.class));
    }
    @Test void validatesOnlySupportedLayoutAndDrawingPayloads(){
        for(String raw:List.of("{}","{\"schemaVersion\":1,\"experience\":\"ADMIN\"}","{\"schemaVersion\":1,\"experience\":\"PRO\",\"password\":\"forbidden\"}"))status(400,()->store.save(owner,store.preferences(),save(0,json(raw))));
        for(String symbol:List.of("RBM","RB0","rb2701","../RB2701"))status(400,()->store.chart(symbol,"900"));status(400,()->store.chart("RB2701","MIN15"));
        for(String changed:List.of(chart().toString().replace("\"LINE\"","\"SCRIPT\""),chart().toString().replace("3000","-1"),chart().toString().replace("+08:00",""),chart().toString().replace("[5,10,20,60,180]","[5,5]")))status(400,()->store.save(owner,store.chart("RB2701","900"),save(0,json(changed))));
        assertEquals(0,f.db.queryForObject("select count(*) from identity.workspace_document",Integer.class));
    }
}
