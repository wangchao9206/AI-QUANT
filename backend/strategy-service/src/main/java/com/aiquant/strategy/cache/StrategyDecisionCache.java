package com.aiquant.strategy.cache;

import com.aiquant.strategy.api.PredictionResponse;

import java.util.Optional;

public interface StrategyDecisionCache {
    Optional<PredictionResponse> get(String symbol);

    void put(PredictionResponse prediction);
}
