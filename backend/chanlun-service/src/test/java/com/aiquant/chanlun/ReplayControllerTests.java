package com.aiquant.chanlun;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class ReplayControllerTests {
    @Test void rejectsInvalidStartAndStepBeforeCreatingWork() throws Exception {
        var service=mock(ReplayService.class);
        var mvc=MockMvcBuilders.standaloneSetup(new ReplayController(service)).setControllerAdvice(new ApiErrors()).build();
        mvc.perform(post("/api/chanlun/v1/replays").contentType(MediaType.APPLICATION_JSON).content("""
            {"clientRequestId":"11111111-1111-4111-8111-111111111111","engineId":"native","datasetId":"fu-daily-2026-10-30","startBars":1894}
            """)).andExpect(status().isBadRequest());
        mvc.perform(post("/api/chanlun/v1/replays/11111111-1111-4111-8111-111111111111/advance").contentType(MediaType.APPLICATION_JSON).content("""
            {"clientRequestId":"22222222-2222-4222-8222-222222222222","expectedStep":-1}
            """)).andExpect(status().isBadRequest());
        verifyNoInteractions(service);
    }
    @Test void rejectsFutureStructuresProfileDriftAndWrongObservationDate() {
        var mapper=new ObjectMapper();
        var result=mapper.createObjectNode();
        result.put("engineId","native").put("profileHash","profile").put("datasetHash","dataset").put("observedBars",50).put("observedAsOfDate","2020-01-01");
        var bars=result.putArray("bars");for(int i=0;i<50;i++)bars.addObject().put("index",i).put("date","2020-01-01");
        var structures=result.putArray("structures");structures.addObject().put("endIndex",49);
        Map<String,Object> session=Map.of("engine_id","native","profile_hash","profile","dataset_hash","dataset");
        assertDoesNotThrow(()->ReplayService.checkPrefix(result,session,50));
        structures.get(0).withObject("").put("endIndex",50);
        assertEquals(409,assertThrows(ResponseStatusException.class,()->ReplayService.checkPrefix(result,session,50)).getStatusCode().value());
        structures.removeAll();result.put("profileHash","changed");
        assertEquals(409,assertThrows(ResponseStatusException.class,()->ReplayService.checkPrefix(result,session,50)).getStatusCode().value());
        result.put("profileHash","profile").put("observedAsOfDate","2026-10-27");
        assertEquals(409,assertThrows(ResponseStatusException.class,()->ReplayService.checkPrefix(result,session,50)).getStatusCode().value());
    }
    @Test void sessionResponsesCannotBeCached() throws Exception {
        var service=mock(ReplayService.class);
        when(service.recent()).thenReturn(java.util.List.of());
        MockMvcBuilders.standaloneSetup(new ReplayController(service)).build().perform(get("/api/chanlun/v1/replays"))
            .andExpect(status().isOk()).andExpect(header().string("Cache-Control","no-store"));
    }
}
