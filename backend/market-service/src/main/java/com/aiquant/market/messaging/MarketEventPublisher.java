package com.aiquant.market.messaging;

import com.aiquant.market.api.QuoteResponse;

public interface MarketEventPublisher {
    void quoteUpdated(QuoteResponse quote);
}
