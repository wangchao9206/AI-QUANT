package com.aiquant.chanlun;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class ChanlunControllerTests {
    @Test void rejectsUnsupportedEngineAndOutOfBoundsBeforeComputing() throws Exception {
        var service=mock(ChanlunService.class);
        var mvc=MockMvcBuilders.standaloneSetup(new ChanlunController(service)).setControllerAdvice(new ApiErrors()).build();
        for(String body:new String[]{
            "{\"clientRequestId\":\"11111111-1111-4111-8111-111111111111\",\"engineId\":\"pro\",\"datasetId\":\"fu-daily-2026-10-30\",\"observedBars\":501}",
            "{\"clientRequestId\":\"11111111-1111-4111-8111-111111111111\",\"engineId\":\"chanpy\",\"datasetId\":\"fu-daily-2026-10-30\",\"observedBars\":1895}"
        })mvc.perform(post("/api/chanlun/v1/runs").contentType(MediaType.APPLICATION_JSON).content(body)).andExpect(status().isBadRequest());
        verifyNoInteractions(service);
    }
    @Test void rejectsMismatchedOrFutureWorkerResult() throws Exception {
        var mapper=new ObjectMapper();
        var request=new ChanlunController.RunRequest(java.util.UUID.randomUUID(),"chanpy","fu-daily-2026-10-30",50);
        var invalid=mapper.readTree("{\"engineId\":\"czsc\",\"observedBars\":50}");
        org.junit.jupiter.api.Assertions.assertThrows(IllegalStateException.class,()->ChanlunService.validateResult(invalid,request));
    }
}
