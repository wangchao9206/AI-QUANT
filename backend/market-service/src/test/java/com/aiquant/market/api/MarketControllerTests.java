package com.aiquant.market.api;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.aiquant.market.service.MarketService;

import java.math.BigDecimal;
import java.time.Instant;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class MarketControllerTests {
    private MarketService marketService;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        marketService = Mockito.mock(MarketService.class);
        mockMvc = MockMvcBuilders.standaloneSetup(new MarketController(marketService)).build();
    }

    @Test
    void returnsCurrentQuoteContract() throws Exception {
        when(marketService.currentQuote("CJ2701")).thenReturn(new QuoteResponse(
            "CJ2701",
            "Red jujube 2701",
            new BigDecimal("12345.00"),
            new BigDecimal("12.00"),
            new BigDecimal("0.10"),
            "trusted-feed",
            DataStatus.FRESH,
            Instant.parse("2026-10-13T08:00:00Z")
        ));

        mockMvc.perform(get("/api/v1/market/CJ2701/quote"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.symbol").value("CJ2701"))
            .andExpect(jsonPath("$.dataStatus").value("FRESH"));
    }
}
