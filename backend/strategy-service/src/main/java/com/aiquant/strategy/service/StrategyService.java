package com.aiquant.strategy.service;

import com.aiquant.strategy.api.DataStatus;
import com.aiquant.strategy.api.PredictionResponse;
import com.aiquant.strategy.cache.StrategyDecisionCache;
import com.aiquant.strategy.client.AlgorithmClient;
import com.aiquant.strategy.messaging.StrategyEventPublisher;
import com.aiquant.strategy.persistence.StrategyDecisionRepository;
import com.aiquant.strategy.persistence.StrategyDecisionSnapshot;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.time.Instant;
import java.util.Locale;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executor;
import java.util.regex.Pattern;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class StrategyService {
    private static final Logger log = LoggerFactory.getLogger(StrategyService.class);
    private static final Pattern SYMBOL = Pattern.compile("^[A-Z]{1,4}[A-Z0-9]{0,8}$");

    private final AlgorithmClient algorithmClient;
    private final StrategyDecisionCache cache;
    private final StrategyDecisionRepository repository;
    private final StrategyEventPublisher eventPublisher;
    private final ObjectMapper objectMapper;
    private final Executor executor;
    private final ConcurrentHashMap<String, CompletableFuture<PredictionResponse>> inFlight = new ConcurrentHashMap<>();

    public StrategyService(
        AlgorithmClient algorithmClient,
        StrategyDecisionCache cache,
        StrategyDecisionRepository repository,
        StrategyEventPublisher eventPublisher,
        ObjectMapper objectMapper,
        @Qualifier("strategyExecutor") Executor executor
    ) {
        this.algorithmClient = algorithmClient;
        this.cache = cache;
        this.repository = repository;
        this.eventPublisher = eventPublisher;
        this.objectMapper = objectMapper;
        this.executor = executor;
    }

    public PredictionResponse prediction(String rawSymbol, String rawTraceId) {
        String symbol = normalize(rawSymbol);
        String traceId = normalizeTraceId(rawTraceId);
        Optional<PredictionResponse> cached = cache.get(symbol);
        if (cached.isPresent()) {
            return cached.get().withStatus(DataStatus.CACHED);
        }

        CompletableFuture<PredictionResponse> computation = inFlight.computeIfAbsent(
            symbol,
            key -> CompletableFuture.supplyAsync(() -> calculateOrFallback(key, traceId), executor)
        );
        computation.whenComplete((ignored, throwable) -> inFlight.remove(symbol, computation));
        try {
            return computation.join();
        } catch (CompletionException exception) {
            if (exception.getCause() instanceof RuntimeException runtimeException) {
                throw runtimeException;
            }
            throw exception;
        }
    }

    private PredictionResponse calculateOrFallback(String symbol, String traceId) {
        try {
            PredictionResponse fresh = algorithmClient.predict(symbol, traceId).withStatus(DataStatus.FRESH);
            StrategyDecisionSnapshot snapshot = new StrategyDecisionSnapshot(
                fresh.symbol(),
                fresh.modelVersion(),
                fresh.dataTimestamp(),
                Instant.now(),
                fresh.dataStatus().name(),
                traceId,
                objectMapper.valueToTree(fresh)
            );
            repository.save(snapshot);
            cache.put(fresh);
            eventPublisher.predictionUpdated(fresh);
            return fresh;
        } catch (RuntimeException exception) {
            log.warn("algorithm_call_failed symbol={} traceId={}", symbol, traceId, exception);
            return repository.findFirstBySymbolOrderByCalculatedAtDesc(symbol)
                .map(StrategyDecisionSnapshot::getResultPayload)
                .map(payload -> objectMapper.convertValue(payload, PredictionResponse.class))
                .map(prediction -> prediction.withStatus(DataStatus.DEGRADED))
                .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Prediction service temporarily unavailable",
                    exception
                ));
        }
    }

    private String normalize(String rawSymbol) {
        String symbol = rawSymbol == null ? "" : rawSymbol.trim().toUpperCase(Locale.ROOT);
        if (!SYMBOL.matcher(symbol).matches()) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY, "Invalid futures symbol");
        }
        return symbol;
    }

    private String normalizeTraceId(String traceId) {
        if (traceId == null || traceId.isBlank()) {
            return UUID.randomUUID().toString().replace("-", "");
        }
        return traceId.substring(0, Math.min(traceId.length(), 128));
    }
}
