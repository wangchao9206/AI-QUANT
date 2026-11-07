package com.aiquant.identity;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.*;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;

@EnabledIfEnvironmentVariable(named="IDENTITY_TEST_DATABASE_URL",matches=".*identity_test.*")
class AdministrationIntegrationTests {
    Accounts a;AdministrationController c;IdentityController auth;MockHttpServletRequest root;
    final String secret="administration-test-internal-secret-longer-than-32";
    @Test void private_plan_alert_authorization_requires_current_paper_write_and_market_read(){
        UUID alice=create("alice"),role=role(Accounts.LEGACY,"plan-alerts",Set.of("market.read","paper.read","paper.write"));
        c.grant(root,null,new AdministrationController.Grant(alice,null,"MEMBER",Set.of(role)));login("alice");
        var request=new IdentityController.DecisionAuthorization(alice,Accounts.LEGACY);
        assertEquals(true,((Map<?,?>)auth.decisionAuthorization(secret,request)).get("allowed"));
        c.editRole(root,role,null,new AdministrationController.RoleEdit("plan-alerts","",Set.of("market.read","paper.read"),true,0));
        assertEquals(false,((Map<?,?>)auth.decisionAuthorization(secret,request)).get("allowed"));
        assertEquals(false,((Map<?,?>)auth.decisionAuthorization(secret,new IdentityController.DecisionAuthorization(alice,UUID.randomUUID()))).get("allowed"));
        status(HttpStatus.FORBIDDEN,()->auth.decisionAuthorization("wrong",request));
    }
    @Test void background_monitor_authorization_checks_current_module_grants(){
        UUID alice=create("alice"),role=role(Accounts.LEGACY,"market-only",Set.of("market.read","market.write"));
        c.grant(root,null,new AdministrationController.Grant(alice,null,"MEMBER",Set.of(role)));login("alice");
        var future=new IdentityController.MonitorAuthorization(alice,Accounts.LEGACY,"FUTURE");
        assertEquals(true,((Map<?,?>)auth.monitorAuthorization(secret,future)).get("allowed"));
        assertEquals(false,((Map<?,?>)auth.monitorAuthorization(secret,new IdentityController.MonitorAuthorization(alice,Accounts.LEGACY,"OPTION"))).get("allowed"));
        c.editRole(root,role,null,new AdministrationController.RoleEdit("market-only","",Set.of("market.read"),true,0));
        assertEquals(false,((Map<?,?>)auth.monitorAuthorization(secret,future)).get("allowed"));
        status(HttpStatus.FORBIDDEN,()->auth.monitorAuthorization("wrong",future));
    }
    @Test void live_menu_uses_market_read_permission_without_expanding_existing_grants(){
        assertEquals("market",AccessControl.ROUTES.get("/live"));
        assertTrue(a.access.navigation(p(root)).stream().anyMatch(row->"/live".equals(row.get("path"))&&"market.read".equals(row.get("permission"))));
        UUID alice=create("alice"),id=role(Accounts.LEGACY,"options-only",Set.of("options.read"));
        c.grant(root,null,new AdministrationController.Grant(alice,null,"MEMBER",Set.of(id)));
        assertFalse(a.access.navigation(p(login("alice"))).stream().anyMatch(row->"/live".equals(row.get("path"))));
    }
    @BeforeEach void setup(){var ds=new DriverManagerDataSource(System.getenv("IDENTITY_TEST_DATABASE_URL"),"identity_test","isolated-test-only");var db=new JdbcTemplate(ds);db.execute("drop schema if exists identity cascade");Flyway.configure().dataSource(ds).schemas("identity").defaultSchema("identity").load().migrate();a=new Accounts(db,new TransactionTemplate(new DataSourceTransactionManager(ds)),new AccountMail(mock(JavaMailSender.class),"smtp.test","admin@example.test","https://example.test"),new ObjectMapper(),secret);a.run(null);c=new AdministrationController(a);auth=new IdentityController(a,false);root=login("admin");}
    MockHttpServletRequest login(String name){var first=a.login(name,name+"123456");var p=a.authenticate(first.token(),null,null,null,false);a.changePassword(p,name+"123456",name+"-secure-new-password");return request(a.login(name,name+"-secure-new-password"));}
    MockHttpServletRequest request(Accounts.Login login){var req=new MockHttpServletRequest();req.setCookies(new jakarta.servlet.http.Cookie("aq_session",login.token()));req.addHeader("X-CSRF-Token",login.csrf());return req;}
    UUID create(String name){return (UUID)((Map<?,?>)c.createUser(root,Accounts.LEGACY,new AdministrationController.UserCreate(name,name+" display",null))).get("id");}
    UUID tenant(UUID owner,String name){return (UUID)((Map<?,?>)c.createTenant(root,new AdministrationController.TenantCreate(name,owner))).get("id");}
    UUID role(UUID tenant,String name,Set<String> permissions){return (UUID)((Map<?,?>)c.createRole(root,tenant,new AdministrationController.RoleEdit(name,"description",permissions,true,0))).get("id");}
    Accounts.Principal p(MockHttpServletRequest req){return a.require(req,false,false);}
    void status(HttpStatus expected,Runnable action){assertEquals(expected,assertThrows(ResponseStatusException.class,action::run).getStatusCode());}
    @Test void managed_users_use_initial_rule_and_mutations_are_audited_without_secrets(){UUID id=create("alice");var u=a.account(id);assertTrue(a.passwords.matches("alice123456",(String)u.get("password_hash")));assertTrue((Boolean)u.get("must_change"));var rows=(AdministrationController.Page)c.users(root,null,"alice",1,20);assertEquals(1,rows.total());assertFalse(rows.items().get(0).containsKey("password_hash"));String data=a.db.queryForObject("select after_state::text from identity.audit where action='ACCOUNT_PROVISION'",String.class);assertFalse(data.contains("password"));assertFalse(data.contains("token"));assertTrue(data.contains("alice"));}
    @Test void ordinary_member_cannot_open_administration(){create("alice");var alice=login("alice");status(HttpStatus.FORBIDDEN,()->c.catalog(alice));status(HttpStatus.FORBIDDEN,()->c.users(alice,null,"",1,20));status(HttpStatus.FORBIDDEN,()->c.createRole(alice,null,new AdministrationController.RoleEdit("forged","",Set.of("market.read"),true,0)));}
    @Test void tenant_owner_cannot_cross_scope_or_manage_global_accounts(){UUID alice=create("alice"),bob=create("bobby");UUID own=tenant(alice,"Alice"),other=tenant(bob,"Bob");var req=login("alice");req.addHeader("X-Tenant-Id",own.toString());status(HttpStatus.FORBIDDEN,()->c.roles(req,other));status(HttpStatus.FORBIDDEN,()->c.users(req,other,"",1,20));status(HttpStatus.FORBIDDEN,()->c.menus(req));status(HttpStatus.FORBIDDEN,()->c.editUser(req,bob,new AdministrationController.UserEdit("x",false)));status(HttpStatus.FORBIDDEN,()->c.platformRole(req,bob,new AdministrationController.PlatformGrant(true)));assertEquals(1,((AdministrationController.Page)c.users(req,own,"",1,20)).total());}
    @Test void custom_roles_change_permissions_for_existing_sessions_and_disabled_roles_fail_closed(){UUID alice=create("alice"),id=role(Accounts.LEGACY,"options-reader",Set.of("options.read"));var aliceReq=login("alice");var before=p(aliceReq);assertTrue(a.access.effective(before).contains("paper.write"));c.grant(root,null,new AdministrationController.Grant(alice,null,"MEMBER",Set.of(id)));assertEquals(Set.of("options.read"),a.access.effective(p(aliceReq)));status(HttpStatus.FORBIDDEN,()->a.access.business(p(aliceReq),"/api/v1/paper/sessions",false));c.editRole(root,id,null,new AdministrationController.RoleEdit("options-reader","updated",Set.of("options.read"),false,0));assertTrue(a.access.effective(p(aliceReq)).isEmpty());status(HttpStatus.CONFLICT,()->c.deleteRole(root,id,null));status(HttpStatus.CONFLICT,()->c.editRole(root,id,null,new AdministrationController.RoleEdit("stale","",Set.of(),true,0)));}
    @Test void role_assignment_rejects_cross_tenant_ids_atomically(){UUID alice=create("alice");UUID other=tenant(alice,"Other"),foreign=role(other,"foreign",Set.of("market.read"));status(HttpStatus.NOT_FOUND,()->c.grant(root,null,new AdministrationController.Grant(alice,null,"VIEWER",Set.of(foreign))));assertEquals("MEMBER",a.db.queryForObject("select role from identity.membership where tenant_id=? and user_id=?",String.class,Accounts.LEGACY,alice));assertEquals(0,a.db.queryForObject("select count(*) from identity.role_assignment",Integer.class));}
    @Test void viewer_cap_and_api_key_cap_cannot_be_overridden(){UUID alice=create("alice"),id=role(Accounts.LEGACY,"all-options",Set.of("options.read","options.write"));c.grant(root,null,new AdministrationController.Grant(alice,null,"VIEWER",Set.of(id)));var req=login("alice");assertEquals(Set.of("options.read"),a.access.effective(p(req)));var owner=p(root);var key=new Accounts.Principal(owner.user(),owner.tenant(),owner.credential(),owner.username(),owner.role(),true,false,true,"READ");assertFalse(a.access.effective(key).stream().anyMatch(code->code.endsWith(".write")));status(HttpStatus.BAD_REQUEST,()->role(null,"forged",Set.of("platform.admin")));}
    @Test void protected_owner_and_platform_identity_cannot_be_self_revoked(){var owner=p(root);status(HttpStatus.CONFLICT,()->c.grant(root,null,new AdministrationController.Grant(owner.user(),null,"MEMBER",Set.of())));status(HttpStatus.CONFLICT,()->c.platformRole(root,owner.user(),new AdministrationController.PlatformGrant(false)));status(HttpStatus.CONFLICT,()->c.editTenant(root,Accounts.LEGACY,new AdministrationController.TenantEdit("Default",false)));}
    @Test void menus_have_safe_routes_cycle_checks_and_independent_api_permissions(){
        status(HttpStatus.BAD_REQUEST,()->c.createMenu(root,new AdministrationController.MenuEdit(null,"unsafe","javascript:alert(1)","market.read",0,true,0)));
        UUID group=(UUID)((Map<?,?>)c.createMenu(root,new AdministrationController.MenuEdit(null,"研究工具",null,"",0,true,0))).get("id");UUID market=UUID.fromString("10000000-0000-0000-0000-000000000004");
        c.editMenu(root,market,new AdministrationController.MenuEdit(group,"市场","/market","market.read",40,true,0));
        status(HttpStatus.BAD_REQUEST,()->c.editMenu(root,group,new AdministrationController.MenuEdit(market,"研究工具",null,"",0,true,0)));
        c.editMenu(root,group,new AdministrationController.MenuEdit(null,"研究工具",null,"",0,false,0));
        assertFalse(a.access.navigation(p(root)).stream().anyMatch(row->"/market".equals(row.get("path"))));assertDoesNotThrow(()->a.access.business(p(root),"/api/v1/market/instruments",false));
        status(HttpStatus.CONFLICT,()->c.deleteMenu(root,group));
    }
    @Test void tenant_disable_and_account_disable_revoke_credentials(){UUID alice=create("alice");UUID tid=tenant(alice,"Alice");var req=login("alice");String token=Accounts.cookie(req,"aq_session");c.editUser(root,alice,new AdministrationController.UserEdit("Alice",false));status(HttpStatus.UNAUTHORIZED,()->a.authenticate(token,null,null,null,false));c.editUser(root,alice,new AdministrationController.UserEdit("Alice",true));var session=request(a.login("alice","alice-secure-new-password"));var who=a.authenticate(Accounts.cookie(session,"aq_session"),null,tid.toString(),null,false);a.db.update("update identity.session set tenant_id=? where id=?",tid,who.credential());c.editTenant(root,tid,new AdministrationController.TenantEdit("Alice",false));status(HttpStatus.UNAUTHORIZED,()->a.authenticate(Accounts.cookie(session,"aq_session"),null,null,null,false));}
    @Test void grants_can_lookup_exact_existing_account_and_reject_non_owner_delegation(){UUID alice=create("alice"),bob=create("bobby");c.grant(root,null,new AdministrationController.Grant(null,"alice","ADMIN",Set.of()));var req=login("alice");status(HttpStatus.FORBIDDEN,()->c.grant(req,null,new AdministrationController.Grant(bob,null,"OWNER",Set.of())));assertEquals("MEMBER",a.db.queryForObject("select role from identity.membership where user_id=?",String.class,bob));}
    @Test void history_and_operations_are_scoped_and_searchable(){UUID alice=create("alice"),bob=create("bobby");UUID own=tenant(alice,"Alice"),other=tenant(bob,"Bob");var req=login("alice");req.addHeader("X-Tenant-Id",own.toString());a.db.update("insert into identity.operation_log(user_id,tenant_id,method,path,status,duration_ms,trace_id) values(?,?,'POST','/api/v1/paper/sessions',403,12,'unique-test-trace')",alice,own);a.db.update("insert into identity.operation_log(tenant_id,method,path,status,duration_ms) values(?,'POST','/api/v1/paper/sessions',200,5)",other);var result=(AdministrationController.Page)c.operations(req,null,"unique-test-trace",403,1,20);assertEquals(1,result.total());assertEquals(403,result.items().get(0).get("status"));status(HttpStatus.FORBIDDEN,()->c.operations(req,other,"",null,1,20));var history=(AdministrationController.Page)c.history(req,null,"",1,20);assertTrue(history.items().stream().allMatch(row->own.equals(row.get("tenantId"))));}
}
