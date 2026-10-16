package com.aiquant.market.api;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record MarketMicrostructureResponse(
    String symbol,
    String source,
    DataStatus dataStatus,
    Instant dataTimestamp,
    BigDecimal lastPrice,
    List<DepthLevel> bids,
    List<DepthLevel> asks,
    List<MarketTrade> trades
) {
    public record DepthLevel(int level, BigDecimal price, long volume) {}

    public record MarketTrade(
        String id,
        Instant timestamp,
        BigDecimal price,
        long volume,
        BigDecimal amount,
        long openInterest,
        long openInterestChange,
        String side
    ) {}
}
