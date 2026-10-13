package com.aiquant.strategy.api;

import com.fasterxml.jackson.databind.JsonNode;

public record DimensionResponse(
    String key,
    String name,
    double score,
    String direction,
    double confidence,
    String summary,
    String recommendation,
    JsonNode keyMetrics
) {
}
