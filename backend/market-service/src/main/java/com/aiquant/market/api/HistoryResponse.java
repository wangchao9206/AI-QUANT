package com.aiquant.market.api;

import java.time.Instant;
import java.util.List;

public record HistoryResponse(
    String symbol,
    DataStatus dataStatus,
    Instant dataTimestamp,
    List<HistoryPoint> points
) {
}
