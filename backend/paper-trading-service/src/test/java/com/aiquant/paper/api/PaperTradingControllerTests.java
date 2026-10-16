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
        MockMvc mvc = MockMvcBuilders.standaloneSetup(new PaperTradingController(service)).build();
        UUID id = UUID.fromString("00000000-0000-0000-0000-000000000001");

        mvc.perform(delete("/api/v1/paper/sessions/{id}", id))
            .andExpect(status().isNoContent());

        verify(service).deleteSession(id);
    }
}
