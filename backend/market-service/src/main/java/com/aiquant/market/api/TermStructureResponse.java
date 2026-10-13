package com.aiquant.market.api;

import java.time.Instant;
import java.util.List;

public record TermStructureResponse(
    String rootSymbol,
    DataStatus dataStatus,
    Instant dataTimestamp,
    List<TermStructurePoint> contracts
) {
}
