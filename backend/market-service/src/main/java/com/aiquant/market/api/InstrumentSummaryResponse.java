package com.aiquant.market.api;

import java.util.List;

public record InstrumentSummaryResponse(
    String exchange,
    String exchangeName,
    String name,
    String node,
    String rootSymbol,
    String mainSymbol,
    List<String> contracts
) {}
