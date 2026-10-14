package com.aiquant.strategy.client;

import com.aiquant.strategy.api.PredictionResponse;
import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.bulkhead.BulkheadConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.retry.Retry;
import io.github.resilience4j.retry.RetryConfig;

import java.time.Duration;
import java.util.function.Supplier;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

@Component
public class WebClientAlgorithmClient implements AlgorithmClient {
    private final WebClient webClient;
    private final CircuitBreaker circuitBreaker;
    private final Retry retry;
    private final Bulkhead bulkhead;
    private final Duration totalTimeout;

    public WebClientAlgorithmClient(
        WebClient algorithmWebClient,
        @Value("${aiquant.algorithm.total-timeout:7s}") Duration totalTimeout,
        @Value("${aiquant.algorithm.max-concurrent-calls:32}") int maxConcurrentCalls
    ) {
        this.webClient = algorithmWebClient;
        this.totalTimeout = totalTimeout;
        this.circuitBreaker = CircuitBreaker.of(
            "algorithm-service",
            CircuitBreakerConfig.custom()
                .failureRateThreshold(50)
                .minimumNumberOfCalls(5)
                .slidingWindowSize(20)
                .waitDurationInOpenState(Duration.ofSeconds(15))
                .build()
        );
        this.retry = Retry.of(
            "algorithm-service",
            RetryConfig.custom()
                .maxAttempts(2)
                .waitDuration(Duration.ofMillis(150))
                .retryExceptions(RuntimeException.class)
                .build()
        );
        this.bulkhead = Bulkhead.of(
            "algorithm-service",
            BulkheadConfig.custom()
                .maxConcurrentCalls(maxConcurrentCalls)
                .maxWaitDuration(Duration.ZERO)
                .build()
        );
    }

    @Override
    public PredictionResponse predict(String symbol, String traceId) {
        long deadline = System.nanoTime() + totalTimeout.toNanos();
        Supplier<PredictionResponse> remoteCall = () -> {
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0) throw new IllegalStateException("Algorithm total timeout exceeded");
            return webClient.get()
            .uri("/api/v1/predictions/{symbol}", symbol)
            .header("X-Trace-Id", traceId)
            .retrieve()
            .onStatus(HttpStatusCode::isError, response -> response.createException())
            .bodyToMono(PredictionResponse.class)
            .block(Duration.ofNanos(remaining));
        };
        Supplier<PredictionResponse> guarded = Bulkhead.decorateSupplier(
            bulkhead,
            Retry.decorateSupplier(retry, CircuitBreaker.decorateSupplier(circuitBreaker, remoteCall))
        );
        PredictionResponse response = guarded.get();
        if (response == null) {
            throw new IllegalStateException("Algorithm service returned an empty response");
        }
        return response;
    }
}
