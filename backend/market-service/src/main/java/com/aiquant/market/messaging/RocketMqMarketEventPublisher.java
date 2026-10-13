package com.aiquant.market.messaging;

import com.aiquant.market.api.QuoteResponse;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(name = "aiquant.messaging.enabled", havingValue = "true")
public class RocketMqMarketEventPublisher implements MarketEventPublisher {
    private final StreamBridge streamBridge;

    public RocketMqMarketEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    @Override
    public void quoteUpdated(QuoteResponse quote) {
        boolean sent = streamBridge.send(
            "marketQuote-out-0",
            MessageBuilder.withPayload(quote).setHeader("symbol", quote.symbol()).build()
        );
        if (!sent) throw new IllegalStateException("Market event publication rejected");
    }
}
