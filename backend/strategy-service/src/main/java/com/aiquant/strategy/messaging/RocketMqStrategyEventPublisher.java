package com.aiquant.strategy.messaging;

import com.aiquant.strategy.api.PredictionResponse;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Component
@ConditionalOnProperty(name = "aiquant.messaging.enabled", havingValue = "true")
public class RocketMqStrategyEventPublisher implements StrategyEventPublisher {
    private static final Logger log = LoggerFactory.getLogger(RocketMqStrategyEventPublisher.class);
    private final StreamBridge streamBridge;

    public RocketMqStrategyEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    @Override
    public void predictionUpdated(PredictionResponse prediction) {
        try {
            boolean accepted = streamBridge.send(
                "strategyPrediction-out-0",
                MessageBuilder.withPayload(prediction).setHeader("symbol", prediction.symbol()).build()
            );
            if (!accepted) {
                log.warn("Strategy prediction event was not accepted by the binder for symbol {}", prediction.symbol());
            }
        } catch (RuntimeException exception) {
            log.warn("Strategy prediction saved but event publication failed for symbol {}", prediction.symbol(), exception);
        }
    }
}
