package com.aiquant.strategy.api;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record PredictionResponse(
    String symbol,
    String displayName,
    BigDecimal price,
    BigDecimal change,
    BigDecimal changePct,
    double compositeScore,
    double resonance,
    double confidence,
    String signal,
    String actionDirective,
    double recommendedPositionPct,
    BigDecimal targetPrice,
    BigDecimal stopLossPrice,
    DataStatus dataStatus,
    Instant dataTimestamp,
    String modelVersion,
    String traceId,
    List<DimensionResponse> dimensions,
    List<DimensionResponse> culturalReferences,
    List<String> eventWindows
) {
    public PredictionResponse withStatus(DataStatus status) {
        return new PredictionResponse(
            symbol,
            displayName,
            price,
            change,
            changePct,
            compositeScore,
            resonance,
            confidence,
            signal,
            actionDirective,
            recommendedPositionPct,
            targetPrice,
            stopLossPrice,
            status,
            dataTimestamp,
            modelVersion,
            traceId,
            dimensions,
            culturalReferences,
            eventWindows
        );
    }
}
