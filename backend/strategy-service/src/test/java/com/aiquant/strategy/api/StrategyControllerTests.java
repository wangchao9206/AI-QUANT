package com.aiquant.strategy.api;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.aiquant.strategy.service.StrategyService;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class StrategyControllerTests {
    private StrategyService strategyService;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        strategyService = mock(StrategyService.class);
        mockMvc = MockMvcBuilders.standaloneSetup(new StrategyController(strategyService)).build();
    }

    @Test
    void returnsCanonicalPredictionContract() throws Exception {
        when(strategyService.prediction("CJ2701", "trace-1")).thenReturn(new PredictionResponse(
            "CJ2701",
            "Red jujube 2701",
            new BigDecimal("12345.00"),
            new BigDecimal("12.00"),
            new BigDecimal("0.10"),
            62.5,
            0.78,
            0.81,
            "BUY",
            "Scale in cautiously",
            0.25,
            new BigDecimal("12800.00"),
            new BigDecimal("12000.00"),
            DataStatus.FRESH,
            Instant.parse("2026-10-13T08:00:00Z"),
            "2.0.0",
            "trace-1",
            List.of(),
            List.of(),
            List.of()
        ));

        mockMvc.perform(get("/api/v1/predictions/CJ2701").header("X-Trace-Id", "trace-1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.symbol").value("CJ2701"))
            .andExpect(jsonPath("$.signal").value("BUY"))
            .andExpect(jsonPath("$.dataStatus").value("FRESH"));
    }
}
