package com.aiquant.paper.api;
import com.aiquant.paper.service.ResearchDecisionService;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.test.web.servlet.*;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
class ResearchDecisionControllerTests {
 DecisionControllerTests f;ResearchDecisionService service;MockMvc mvc;
 @BeforeEach void setup(){f=new DecisionControllerTests();f.setup();service=mock(ResearchDecisionService.class);mvc=MockMvcBuilders.standaloneSetup(new ResearchDecisionController(service,f.db,f.json,f.secret)).setControllerAdvice(new PaperTradingExceptionHandler()).build();}
 @Test void calculate_requires_research_and_paper_write_not_only_market_access()throws Exception{
  String body="{\"commandId\":\""+UUID.randomUUID()+"\",\"inputs\":{\"symbol\":\"JM0\"}}";
  for(String[] permissions:List.of(new String[]{"paper.write","market.read"},new String[]{"paper.read","market.read","research.read","research.write"},new String[]{"paper.write","market.read","research.write"}))mvc.perform(post("/api/v1/paper/decisions/research/calculate").header("X-Aiquant-Identity",f.token(permissions)).contentType("application/json").content(body)).andExpect(status().isForbidden());
  verifyNoInteractions(service);
  mvc.perform(post("/api/v1/paper/decisions/research/calculate").header("X-Aiquant-Identity",f.token("paper.write","market.read","research.read","research.write")).contentType("application/json").content(body)).andExpect(status().isOk());
 }
 @Test void private_source_reads_require_research_read_and_are_not_cached()throws Exception{
  UUID id=UUID.randomUUID();mvc.perform(get("/api/v1/paper/decisions/research/sources/"+id).header("X-Aiquant-Identity",f.token("paper.read","market.read"))).andExpect(status().isForbidden());
  when(service.source(f.owner,id)).thenReturn(Map.of("id",id));mvc.perform(get("/api/v1/paper/decisions/research/sources/"+id).header("X-Aiquant-Identity",f.token("paper.read","market.read","research.read"))).andExpect(status().isOk()).andExpect(header().string("Cache-Control","no-store"));
 }
}
