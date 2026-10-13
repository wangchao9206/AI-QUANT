package com.aiquant.strategy.messaging;

import com.aiquant.strategy.api.PredictionResponse;

public class NoOpStrategyEventPublisher implements StrategyEventPublisher {
    @Override
    public void predictionUpdated(PredictionResponse prediction) {
        // Messaging is opt-in for local development and unit tests.
    }
}
