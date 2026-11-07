package com.aiquant.paper.api;
import com.aiquant.paper.service.PlanAlertStore;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
class PlanAlertControllerTests {
 final DecisionControllerTests f=new DecisionControllerTests();PlanAlertStore store;MockMvc mvc;
 @BeforeEach void setup(){store=mock(PlanAlertStore.class);mvc=MockMvcBuilders.standaloneSetup(new PlanAlertController(store,mock(JdbcTemplate.class),f.json,f.secret)).setControllerAdvice(new PaperTradingExceptionHandler()).build();}
 @Test void private_alert_feeds_and_mutations_require_verified_permissions()throws Exception{
  String path="/api/v1/paper/decisions/"+UUID.randomUUID()+"/plans/"+UUID.randomUUID()+"/alerts";
  mvc.perform(get(path)).andExpect(status().isUnauthorized());mvc.perform(get(path).header("X-Aiquant-Identity",f.token("paper.read"))).andExpect(status().isForbidden());
  mvc.perform(post(path).header("X-Aiquant-Identity",f.token("market.read","paper.read")).contentType("application/json").content("{\"enabled\":true,\"entryMode\":\"BREAKOUT\",\"revision\":0}")).andExpect(status().isForbidden());verifyNoInteractions(store);
  mvc.perform(post(path).header("X-Aiquant-Identity",f.token("market.read","paper.write")).contentType("application/json").content("{\"enabled\":true,\"entryMode\":\"BREAKOUT\",\"revision\":0}")).andExpect(status().isForbidden());verifyNoInteractions(store);
  when(store.events(f.owner,null,true,2)).thenReturn(Map.of("items",List.of(),"total",0));mvc.perform(get("/api/v1/paper/decisions/alerts/events").param("unread","true").param("page","2").header("X-Aiquant-Identity",f.token("market.read","paper.read"))).andExpect(status().isOk()).andExpect(header().string("Cache-Control","no-store"));verify(store).events(f.owner,null,true,2);
 }
}
