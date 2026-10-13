package com.aiquant.market.messaging;

import com.aiquant.market.api.QuoteResponse;

public class NoOpMarketEventPublisher implements MarketEventPublisher {
    @Override
    public void quoteUpdated(QuoteResponse quote) {
        // Messaging is opt-in for local development and unit tests.
    }
}
