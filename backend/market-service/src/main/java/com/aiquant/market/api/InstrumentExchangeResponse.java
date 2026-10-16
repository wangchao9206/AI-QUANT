package com.aiquant.market.api;

import java.util.List;

public record InstrumentExchangeResponse(
    String code,
    String name,
    List<InstrumentSummaryResponse> instruments
) {}
