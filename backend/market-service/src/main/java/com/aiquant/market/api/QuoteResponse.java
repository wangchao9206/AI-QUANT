package com.aiquant.market.api;

import java.math.BigDecimal;
import java.time.Instant;

public record QuoteResponse(
    String symbol,
    String displayName,
    BigDecimal price,
    BigDecimal change,
    BigDecimal changePct,
    String source,
    DataStatus dataStatus,
    Instant dataTimestamp
) {
    public QuoteResponse withStatus(DataStatus status) {
        return new QuoteResponse(symbol, displayName, price, change, changePct, source, status, dataTimestamp);
    }
}
