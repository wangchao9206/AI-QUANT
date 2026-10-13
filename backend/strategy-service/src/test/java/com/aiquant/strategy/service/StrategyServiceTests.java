package com.aiquant.strategy.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.aiquant.strategy.api.DataStatus;
import com.aiquant.strategy.api.PredictionResponse;
import com.aiquant.strategy.cache.StrategyDecisionCache;
import com.aiquant.strategy.client.AlgorithmClient;
import com.aiquant.strategy.messaging.StrategyEventPublisher;
import com.aiquant.strategy.persistence.StrategyDecisionRepository;
import com.aiquant.strategy.persistence.StrategyDecisionSnapshot;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class StrategyServiceTests {
    private final AlgorithmClient algorithmClient = mock(AlgorithmClient.class);
    private final StrategyDecisionCache cache = mock(StrategyDecisionCache.class);
    private final StrategyDecisionRepository repository = mock(StrategyDecisionRepository.class);
    private final StrategyEventPublisher eventPublisher = mock(StrategyEventPublisher.class);
    private final ObjectMapper objectMapper = new ObjectMapper().findAndRegisterModules();
    private ExecutorService calculationExecutor;
    private StrategyService service;

    @BeforeEach
    void setUp() {
        calculationExecutor = Executors.newFixedThreadPool(4);
        service = new StrategyService(
            algorithmClient,
            cache,
            repository,
            eventPublisher,
            objectMapper,
            calculationExecutor
        );
    }

    @AfterEach
    void tearDown() {
        calculationExecutor.shutdownNow();
    }

    @Test
    void returnsCachedPredictionWithoutCallingAlgorithm() {
        when(cache.get("CJ2701")).thenReturn(Optional.of(prediction(DataStatus.FRESH)));

        PredictionResponse response = service.prediction(" cj2701 ", "trace-1");

        assertThat(response.dataStatus()).isEqualTo(DataStatus.CACHED);
        verify(algorithmClient, times(0)).predict(anyString(), anyString());
    }

    @Test
    void fallsBackToPersistedDecisionWhenAlgorithmFails() {
        PredictionResponse persisted = prediction(DataStatus.FRESH);
        StrategyDecisionSnapshot snapshot = new StrategyDecisionSnapshot(
            persisted.symbol(),
            persisted.modelVersion(),
            persisted.dataTimestamp(),
            Instant.now(),
            persisted.dataStatus().name(),
            persisted.traceId(),
            objectMapper.valueToTree(persisted)
        );
        when(cache.get("CJ2701")).thenReturn(Optional.empty());
        when(algorithmClient.predict("CJ2701", "trace-2")).thenThrow(new IllegalStateException("timeout"));
        when(repository.findFirstBySymbolOrderByCalculatedAtDesc("CJ2701")).thenReturn(Optional.of(snapshot));

        PredictionResponse response = service.prediction("CJ2701", "trace-2");

        assertThat(response.dataStatus()).isEqualTo(DataStatus.DEGRADED);
        assertThat(response.modelVersion()).isEqualTo("2.0.0+observed.1");
    }

    @Test
    void preservesSourceDegradationRatherThanPromotingItToFresh() {
        when(cache.get("CJ2701")).thenReturn(Optional.empty());
        when(algorithmClient.predict("CJ2701", "trace-degraded")).thenReturn(prediction(DataStatus.DEGRADED));
        when(repository.save(any(StrategyDecisionSnapshot.class))).thenAnswer(invocation -> invocation.getArgument(0));
        assertThat(service.prediction("CJ2701", "trace-degraded").dataStatus()).isEqualTo(DataStatus.DEGRADED);
    }

    @Test
    void preservesCachedDegradation() {
        when(cache.get("CJ2701")).thenReturn(Optional.of(prediction(DataStatus.DEGRADED)));
        assertThat(service.prediction("CJ2701", "trace-degraded").dataStatus()).isEqualTo(DataStatus.DEGRADED);
    }

    @Test
    void doesNotReturnLegacyGeneratedPricesAsTrustedFallback() {
        com.fasterxml.jackson.databind.node.ObjectNode payload = objectMapper.valueToTree(prediction(DataStatus.FRESH));
        payload.put("modelVersion", "1.0.0");
        PredictionResponse legacy = objectMapper.convertValue(payload, PredictionResponse.class);
        when(cache.get("CJ2701")).thenReturn(Optional.of(legacy));
        when(algorithmClient.predict("CJ2701", "legacy")).thenThrow(new IllegalStateException("no observed feed"));
        var oldSnapshot = new StrategyDecisionSnapshot(legacy.symbol(), legacy.modelVersion(), legacy.dataTimestamp(),
            Instant.now(), legacy.dataStatus().name(), legacy.traceId(), payload);
        when(repository.findFirstBySymbolOrderByCalculatedAtDesc("CJ2701")).thenReturn(Optional.of(oldSnapshot));
        assertThatThrownBy(() -> service.prediction("CJ2701", "legacy"))
            .isInstanceOf(org.springframework.web.server.ResponseStatusException.class);
    }

    @Test
    void reusesPersistedDecisionForUnchangedMarketTime() {
        PredictionResponse result = prediction(DataStatus.CACHED);
        var snapshot = new StrategyDecisionSnapshot(result.symbol(), result.modelVersion(), result.dataTimestamp(),
            Instant.now(), result.dataStatus().name(), result.traceId(), objectMapper.valueToTree(result));
        when(cache.get("CJ2701")).thenReturn(Optional.empty());
        when(algorithmClient.predict("CJ2701", "repeat")).thenReturn(result);
        when(repository.findBySymbolAndModelVersionAndInputTimestamp(result.symbol(), result.modelVersion(), result.dataTimestamp()))
            .thenReturn(Optional.of(snapshot));
        assertThat(service.prediction("CJ2701", "repeat").dataStatus()).isEqualTo(DataStatus.CACHED);
        verify(repository, times(0)).save(any());
    }

    @Test
    void coalescesConcurrentCalculationsForSameSymbol() {
        AtomicInteger calls = new AtomicInteger();
        when(cache.get("CJ2701")).thenReturn(Optional.empty());
        when(algorithmClient.predict(anyString(), anyString())).thenAnswer(invocation -> {
            calls.incrementAndGet();
            Thread.sleep(120);
            return prediction(DataStatus.FRESH);
        });
        when(repository.save(any(StrategyDecisionSnapshot.class))).thenAnswer(invocation -> invocation.getArgument(0));

        ExecutorService callers = Executors.newFixedThreadPool(2);
        try {
            CompletableFuture<PredictionResponse> first = CompletableFuture.supplyAsync(
                () -> service.prediction("CJ2701", "trace-a"),
                callers
            );
            CompletableFuture<PredictionResponse> second = CompletableFuture.supplyAsync(
                () -> service.prediction("CJ2701", "trace-b"),
                callers
            );

            CompletableFuture.allOf(first, second).join();
        } finally {
            callers.shutdownNow();
        }

        assertThat(calls).hasValue(1);
    }

    private PredictionResponse prediction(DataStatus status) {
        return new PredictionResponse(
            "CJ2701",
            "Red jujube 2701",
            new BigDecimal("12345.00"),
            new BigDecimal("12.00"),
            new BigDecimal("0.10"),
            62.5,
            0.78,
            0.81,
            "BUY",
            "Scale in cautiously",
            0.25,
            new BigDecimal("12800.00"),
            new BigDecimal("12000.00"),
            status,
            Instant.parse("2026-10-13T08:00:00Z"),
            "2.0.0+observed.1",
            "trace-1",
            List.of(),
            List.of()
        );
    }
}
