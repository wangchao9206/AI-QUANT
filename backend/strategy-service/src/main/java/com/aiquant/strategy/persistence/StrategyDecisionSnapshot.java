package com.aiquant.strategy.persistence;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;

@Entity
@Table(name = "strategy_decision_snapshot")
public class StrategyDecisionSnapshot {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String symbol;

    @Column(name = "model_version", nullable = false)
    private String modelVersion;

    @Column(name = "input_timestamp", nullable = false)
    private Instant inputTimestamp;

    @Column(name = "calculated_at", nullable = false)
    private Instant calculatedAt;

    @Column(name = "data_status", nullable = false)
    private String dataStatus;

    @Column(name = "trace_id", nullable = false)
    private String traceId;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "result_payload", nullable = false, columnDefinition = "jsonb")
    private JsonNode resultPayload;

    protected StrategyDecisionSnapshot() {
    }

    public StrategyDecisionSnapshot(
        String symbol,
        String modelVersion,
        Instant inputTimestamp,
        Instant calculatedAt,
        String dataStatus,
        String traceId,
        JsonNode resultPayload
    ) {
        this.symbol = symbol;
        this.modelVersion = modelVersion;
        this.inputTimestamp = inputTimestamp;
        this.calculatedAt = calculatedAt;
        this.dataStatus = dataStatus;
        this.traceId = traceId;
        this.resultPayload = resultPayload;
    }

    public JsonNode getResultPayload() {
        return resultPayload;
    }
}
