package com.aiquant.market.service;

import com.aiquant.market.api.QuoteResponse;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;

public record MarketFeedSnapshot(QuoteResponse quote, List<Bar> history, List<Contract> contracts) {
    public record Bar(Instant timestamp, BigDecimal price, BigDecimal change, BigDecimal changePct) {}
    public record Contract(String contract, LocalDate maturityDate, BigDecimal price, Instant dataTimestamp) {}
}
