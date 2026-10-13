package com.aiquant.market.api;

import java.math.BigDecimal;
import java.time.Instant;

public record HistoryPoint(Instant timestamp, BigDecimal price, BigDecimal changePct) {
}
