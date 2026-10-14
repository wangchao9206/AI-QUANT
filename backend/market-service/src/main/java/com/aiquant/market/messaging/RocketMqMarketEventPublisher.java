package com.aiquant.market.messaging;

import com.aiquant.market.api.QuoteResponse;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Component
@ConditionalOnProperty(name = "aiquant.messaging.enabled", havingValue = "true")
public class RocketMqMarketEventPublisher implements MarketEventPublisher {
    private static final Logger log = LoggerFactory.getLogger(RocketMqMarketEventPublisher.class);
    private final StreamBridge streamBridge;

    public RocketMqMarketEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    @Override
    public void quoteUpdated(QuoteResponse quote) {
        try {
            boolean accepted = streamBridge.send(
                "marketQuote-out-0",
                MessageBuilder.withPayload(quote).setHeader("symbol", quote.symbol()).build()
            );
            if (!accepted) {
                log.warn("Market quote event was not accepted by the binder for symbol {}", quote.symbol());
            }
        } catch (RuntimeException exception) {
            log.warn("Market quote saved but event publication failed for symbol {}", quote.symbol(), exception);
        }
    }
}
