package com.aiquant.market.api;

import java.time.Instant;
import java.util.List;

public record HistoryResponse(
    String symbol,
    String seriesSymbol,
    String seriesType,
    String source,
    DataStatus dataStatus,
    Instant dataTimestamp,
    List<HistoryPoint> points
) {
}
