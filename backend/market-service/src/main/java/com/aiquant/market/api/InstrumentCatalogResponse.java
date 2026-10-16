package com.aiquant.market.api;

import java.time.Instant;
import java.util.List;

public record InstrumentCatalogResponse(
    String source,
    DataStatus dataStatus,
    Instant dataTimestamp,
    List<InstrumentExchangeResponse> exchanges
) {
    public InstrumentCatalogResponse withStatus(DataStatus status) {
        return new InstrumentCatalogResponse(source, status, dataTimestamp, exchanges);
    }
}
