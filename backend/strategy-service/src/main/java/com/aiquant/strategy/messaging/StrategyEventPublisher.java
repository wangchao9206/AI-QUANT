package com.aiquant.strategy.messaging;

import com.aiquant.strategy.api.PredictionResponse;

public interface StrategyEventPublisher {
    void predictionUpdated(PredictionResponse prediction);
}
