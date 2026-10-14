package com.aiquant.strategy.api;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;

public record DimensionResponse(
    String key,
    String name,
    Double score,
    String direction,
    Double confidence,
    String summary,
    String recommendation,
    String category,
    String dataStatus,
    boolean includedInScore,
    double weight,
    String sourceName,
    String sourceUrl,
    Instant observedAt,
    int sampleSize,
    JsonNode keyMetrics
) {
}
