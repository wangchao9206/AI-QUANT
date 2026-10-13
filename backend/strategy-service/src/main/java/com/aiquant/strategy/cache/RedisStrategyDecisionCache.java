package com.aiquant.strategy.cache;

import com.aiquant.strategy.api.PredictionResponse;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.time.Duration;
import java.util.Optional;
import java.util.concurrent.ThreadLocalRandom;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class RedisStrategyDecisionCache implements StrategyDecisionCache {
    private static final Logger log = LoggerFactory.getLogger(RedisStrategyDecisionCache.class);
    private static final String KEY_PREFIX = "strategy:prediction:";

    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;
    private final Duration baseTtl;
    private final long jitterSeconds;

    public RedisStrategyDecisionCache(
        StringRedisTemplate redisTemplate,
        ObjectMapper objectMapper,
        @Value("${aiquant.cache.prediction-ttl:30s}") Duration baseTtl,
        @Value("${aiquant.cache.ttl-jitter-seconds:15}") long jitterSeconds
    ) {
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
        this.baseTtl = baseTtl;
        this.jitterSeconds = Math.max(jitterSeconds, 0);
    }

    @Override
    public Optional<PredictionResponse> get(String symbol) {
        try {
            String value = redisTemplate.opsForValue().get(KEY_PREFIX + symbol);
            return value == null ? Optional.empty() : Optional.of(objectMapper.readValue(value, PredictionResponse.class));
        } catch (Exception exception) {
            log.warn("strategy_cache_read_failed symbol={}", symbol, exception);
            return Optional.empty();
        }
    }

    @Override
    public void put(PredictionResponse prediction) {
        try {
            long jitter = jitterSeconds == 0 ? 0 : ThreadLocalRandom.current().nextLong(jitterSeconds + 1);
            redisTemplate.opsForValue().set(
                KEY_PREFIX + prediction.symbol(),
                objectMapper.writeValueAsString(prediction),
                baseTtl.plusSeconds(jitter)
            );
        } catch (Exception exception) {
            log.warn("strategy_cache_write_failed symbol={}", prediction.symbol(), exception);
        }
    }
}
