package com.aiquant.market.api;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record IntradayResponse(String symbol, int seconds, String period, String source, DataStatus dataStatus,
    Instant dataTimestamp, Instant receivedAt, Instant retrievedAt, boolean connected,
    String message, boolean lastBarProvisional, List<Bar> points) {
    public record Bar(Instant timestamp, BigDecimal open, BigDecimal high, BigDecimal low,
        BigDecimal price, Long volume, Long openInterest, BigDecimal changePct, boolean changePctKnown) {}
}
