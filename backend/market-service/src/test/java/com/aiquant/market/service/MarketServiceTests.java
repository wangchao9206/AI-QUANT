package com.aiquant.market.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import com.aiquant.market.api.DataStatus;
import com.aiquant.market.api.QuoteResponse;
import com.aiquant.market.cache.MarketQuoteCache;
import com.aiquant.market.persistence.MarketQuoteRepository;
import com.aiquant.market.persistence.MarketQuoteSnapshot;
import com.aiquant.market.persistence.MarketTermRepository;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class MarketServiceTests {
    @Mock
    private MarketQuoteCache cache;

    @Mock
    private MarketQuoteRepository quoteRepository;

    @Mock
    private MarketTermRepository termRepository;

    @Test
    void returnsCachedQuoteWithoutReadingDatabase() {
        QuoteResponse quote = quote(DataStatus.FRESH);
        when(cache.get("CJ2701")).thenReturn(Optional.of(quote));

        MarketService service = new MarketService(cache, quoteRepository, termRepository);

        assertThat(service.currentQuote(" cj2701 ").dataStatus()).isEqualTo(DataStatus.CACHED);
    }

    @Test
    void fallsBackToTrustedDatabaseSnapshotAsDegraded() {
        Instant observedAt = Instant.parse("2026-10-13T08:00:00Z");
        MarketQuoteSnapshot snapshot = new MarketQuoteSnapshot(
            "CJ2701",
            "Red jujube 2701",
            new BigDecimal("12345.00"),
            new BigDecimal("12.00"),
            new BigDecimal("0.10"),
            "trusted-feed",
            observedAt
        );
        when(cache.get("CJ2701")).thenReturn(Optional.empty());
        when(quoteRepository.findFirstBySymbolOrderByObservedAtDesc("CJ2701")).thenReturn(Optional.of(snapshot));

        QuoteResponse response = new MarketService(cache, quoteRepository, termRepository).currentQuote("CJ2701");

        assertThat(response.dataStatus()).isEqualTo(DataStatus.DEGRADED);
        assertThat(response.dataTimestamp()).isEqualTo(observedAt);
    }

    private QuoteResponse quote(DataStatus status) {
        return new QuoteResponse(
            "CJ2701",
            "Red jujube 2701",
            new BigDecimal("12345.00"),
            new BigDecimal("12.00"),
            new BigDecimal("0.10"),
            "trusted-feed",
            status,
            Instant.parse("2026-10-13T08:00:00Z")
        );
    }
}
