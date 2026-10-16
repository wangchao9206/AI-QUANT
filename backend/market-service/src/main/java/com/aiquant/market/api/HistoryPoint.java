package com.aiquant.market.api;

import java.math.BigDecimal;
import java.time.Instant;

public record HistoryPoint(
    Instant timestamp,
    BigDecimal price,
    BigDecimal changePct,
    BigDecimal open,
    BigDecimal high,
    BigDecimal low,
    Long volume,
    Long openInterest
) {
}
