package com.aiquant.paper.api;
import com.aiquant.paper.service.DecisionJournalService;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.*;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.junit.jupiter.api.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
class DecisionControllerTests {
    final String secret="isolated-decision-controller-unit-secret-32chars";final ObjectMapper json=new ObjectMapper();
    final UUID owner=UUID.randomUUID();DecisionJournalService service;JdbcTemplate db;MockMvc mvc;
    @BeforeEach void setup(){service=mock(DecisionJournalService.class);db=mock(JdbcTemplate.class);mvc=MockMvcBuilders.standaloneSetup(new DecisionController(service,db,json,secret)).setControllerAdvice(new PaperTradingExceptionHandler()).build();}
    String token(String...permissions)throws Exception{
        String payload=Base64.getUrlEncoder().withoutPadding().encodeToString(json.writeValueAsBytes(Map.of("tenantId",UUID.randomUUID(),"userId",owner,"expiresAt",Instant.now().plusSeconds(30).getEpochSecond(),"permissions",List.of(permissions))));
        Mac mac=Mac.getInstance("HmacSHA256");mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8),"HmacSHA256"));return payload+"."+Base64.getUrlEncoder().withoutPadding().encodeToString(mac.doFinal(payload.getBytes(StandardCharsets.UTF_8)));
    }
    @Test void verified_permissions_are_required_even_behind_gateway()throws Exception{
        mvc.perform(get("/api/v1/paper/decisions")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/v1/paper/decisions").header("X-Aiquant-Identity",token("paper.read"))).andExpect(status().isForbidden());
        mvc.perform(post("/api/v1/paper/decisions/from-event").header("X-Aiquant-Identity",token("market.read","paper.read")).contentType("application/json").content("{\"eventId\":42}")).andExpect(status().isForbidden());
        verifyNoInteractions(service);
        when(service.list(owner,1,20)).thenReturn(Map.of("items",List.of(),"total",0));
        mvc.perform(get("/api/v1/paper/decisions").header("X-Aiquant-Identity",token("paper.read","market.read"))).andExpect(status().isOk()).andExpect(header().string("Cache-Control","no-store"));
        verify(service).list(owner,1,20);
    }
    @Test void invalid_plan_fields_do_not_reach_service()throws Exception{
        mvc.perform(post("/api/v1/paper/decisions/"+UUID.randomUUID()+"/plans").header("X-Aiquant-Identity",token("market.read","paper.write")).contentType("application/json").content("{\"commandId\":\""+UUID.randomUUID()+"\",\"expectedVersion\":0,\"fields\":{\"side\":\"LONG\",\"lots\":-1}}")).andExpect(status().isBadRequest());verifyNoInteractions(service);
    }
    @Test void list_accepts_trailing_slash_without_redirecting_or_weakening_auth()throws Exception{
        mvc.perform(get("/api/v1/paper/decisions/")).andExpect(status().isUnauthorized());
        when(service.list(owner,2,20)).thenReturn(Map.of("items",List.of(),"total",0));
        mvc.perform(get("/api/v1/paper/decisions/").param("page","2").header("X-Aiquant-Identity",token("paper.read","market.read"))).andExpect(status().isOk()).andExpect(header().string("Cache-Control","no-store"));
        verify(service).list(owner,2,20);
    }
    @Test void inbox_uses_verified_owner_and_existing_read_permissions()throws Exception{
        mvc.perform(get("/api/v1/paper/decisions/inbox")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/v1/paper/decisions/inbox").header("X-Aiquant-Identity",token("paper.read"))).andExpect(status().isForbidden());
        verifyNoInteractions(service);
        when(service.inbox(owner,"EXPIRING",2,20)).thenReturn(Map.of("items",List.of(),"total",0));
        mvc.perform(get("/api/v1/paper/decisions/inbox").param("filter","EXPIRING").param("page","2").header("X-Aiquant-Identity",token("paper.read","market.read"))).andExpect(status().isOk()).andExpect(header().string("Cache-Control","no-store"));
        verify(service).inbox(owner,"EXPIRING",2,20);
    }
}
