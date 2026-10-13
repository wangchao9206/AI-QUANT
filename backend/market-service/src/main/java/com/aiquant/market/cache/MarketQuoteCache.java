package com.aiquant.market.cache;

import com.aiquant.market.api.QuoteResponse;

import java.util.Optional;

public interface MarketQuoteCache {
    Optional<QuoteResponse> get(String symbol);

    void put(QuoteResponse quote);
}
