package com.aiquant.paper.api;

import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.aiquant.paper.service.PaperTradingService;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class PaperTradingControllerTests {
    @Test
    void deletesCompleteExperimentLedger() throws Exception {
        PaperTradingService service = Mockito.mock(PaperTradingService.class);
        DecisionControllerTests f=new DecisionControllerTests();
        MockMvc mvc = MockMvcBuilders.standaloneSetup(new PaperTradingController(service,Mockito.mock(org.springframework.jdbc.core.JdbcTemplate.class),f.json,f.secret)).setControllerAdvice(new PaperTradingExceptionHandler()).build();
        UUID id = UUID.fromString("00000000-0000-0000-0000-000000000001");

        mvc.perform(delete("/api/v1/paper/sessions/{id}", id).header("X-Aiquant-Identity",f.token("paper.write")))
            .andExpect(status().isNoContent());

        verify(service).deleteSession(id);
    }

    @Test void signedIdentityAndMethodPermissionsAreRequiredBeforeAnyLedgerAccess() throws Exception {
        var service=Mockito.mock(PaperTradingService.class);var jdbc=Mockito.mock(org.springframework.jdbc.core.JdbcTemplate.class);var f=new DecisionControllerTests();
        var mvc=MockMvcBuilders.standaloneSetup(new PaperTradingController(service,jdbc,f.json,f.secret)).setControllerAdvice(new PaperTradingExceptionHandler()).build();
        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get("/api/v1/paper/sessions")).andExpect(status().isUnauthorized());
        mvc.perform(delete("/api/v1/paper/sessions/{id}",UUID.randomUUID()).header("X-Aiquant-Identity",f.token("paper.read"))).andExpect(status().isForbidden());
        Mockito.verifyNoInteractions(service);
        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get("/api/v1/paper/sessions").header("X-Aiquant-Identity",f.token("paper.read"))).andExpect(status().isOk()).andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers.header().string("Cache-Control","no-store"));
        Mockito.verify(jdbc).queryForObject("select set_config('app.user_id',?,true)",String.class,f.owner.toString());
        Mockito.verify(jdbc).queryForObject("select set_config('app.market_read',?,true)",String.class,"false");
    }
}
