package com.aiquant.market.api;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.aiquant.market.service.MarketService;
import com.aiquant.market.service.MarketIngestionService;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;

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
        mockMvc = MockMvcBuilders.standaloneSetup(new MarketController(marketService, Mockito.mock(MarketIngestionService.class))).build();
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

    @Test
    void returnsObservedIntradayBarsAndForwardsPeriod() throws Exception {
        when(marketService.intraday("RB2701",15,400)).thenReturn(new IntradayResponse("RB2701",15,"15","TqSdk",DataStatus.CACHED,
            Instant.parse("2026-11-06T02:00:00Z"),Instant.now(),Instant.now(),true,"",true,List.of(),
            Map.of("version","line-geometry-v1","lines",List.of(Map.of("kind","REGRESSION_UPPER","startIndex",12,"endIndex",80,"knownAt","2026-11-06T01:59:00Z")))));
        mockMvc.perform(get("/api/v1/market/RB2701/intraday?seconds=15&limit=400"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.seconds").value(15))
            .andExpect(jsonPath("$.dataStatus").value("CACHED")).andExpect(jsonPath("$.lastBarProvisional").value(true))
            .andExpect(jsonPath("$.geometry.lines[0].kind").value("REGRESSION_UPPER"))
            .andExpect(jsonPath("$.geometry.lines[0].endIndex").value(80))
            .andExpect(jsonPath("$.geometry.lines[0].knownAt").value("2026-11-06T01:59:00Z"));
    }

    @Test
    void calendarMonthIsForwardedAsNamedPeriodRatherThanFixedSeconds() throws Exception {
        when(marketService.calendar("RBM","MONTH",600)).thenReturn(new IntradayResponse("RBM",0,"MONTH","TqSdk daily aggregate",DataStatus.CACHED,
            Instant.now(),Instant.now(),Instant.now(),true,"",true,List.of()));
        mockMvc.perform(get("/api/v1/market/RBM/intraday?period=MONTH&limit=600"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.period").value("MONTH"))
            .andExpect(jsonPath("$.seconds").value(0));
    }

    @Test
    void returnsLeadsContract() throws Exception {
        when(marketService.leads()).thenReturn("{\"scannedCount\":6,\"leadsCount\":1,\"leads\":[]}");

        mockMvc.perform(get("/api/v1/market/leads"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.scannedCount").value(6))
            .andExpect(jsonPath("$.leadsCount").value(1));
    }

    @Test
    void returnsFiveLevelDepthAndTrades() throws Exception {
        when(marketService.microstructure("CJ701")).thenReturn(new MarketMicrostructureResponse(
            "CJ701", "TqSdk", DataStatus.FRESH, Instant.parse("2026-10-16T01:31:00Z"),
            new BigDecimal("6430"),
            List.of(new MarketMicrostructureResponse.DepthLevel(1, new BigDecimal("6425"), 10)),
            List.of(new MarketMicrostructureResponse.DepthLevel(1, new BigDecimal("6430"), 12)),
            List.of(new MarketMicrostructureResponse.MarketTrade(
                "1", Instant.parse("2026-10-16T01:30:59Z"), new BigDecimal("6430"),
                2, new BigDecimal("64300"), 100, 1, "BUY"
            ))
        ));

        mockMvc.perform(get("/api/v1/market/CJ701/microstructure"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.bids[0].price").value(6425))
            .andExpect(jsonPath("$.trades[0].side").value("BUY"));
    }
}
