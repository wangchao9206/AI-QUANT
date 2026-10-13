package com.aiquant.strategy.messaging;

import com.aiquant.strategy.api.PredictionResponse;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(name = "aiquant.messaging.enabled", havingValue = "true")
public class RocketMqStrategyEventPublisher implements StrategyEventPublisher {
    private final StreamBridge streamBridge;

    public RocketMqStrategyEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    @Override
    public void predictionUpdated(PredictionResponse prediction) {
        streamBridge.send(
            "strategyPrediction-out-0",
            MessageBuilder.withPayload(prediction).setHeader("symbol", prediction.symbol()).build()
        );
    }
}
