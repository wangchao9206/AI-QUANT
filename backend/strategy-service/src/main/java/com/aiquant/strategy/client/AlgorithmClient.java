package com.aiquant.strategy.client;

import com.aiquant.strategy.api.PredictionResponse;

public interface AlgorithmClient {
    PredictionResponse predict(String symbol, String traceId);
}
