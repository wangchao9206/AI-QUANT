package com.aiquant.market.cache;

import com.aiquant.market.api.QuoteResponse;
import com.fasterxml.jackson.core.JsonProcessingException;
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
public class RedisMarketQuoteCache implements MarketQuoteCache {
    private static final Logger log = LoggerFactory.getLogger(RedisMarketQuoteCache.class);
    private static final String KEY_PREFIX = "market:quote:";

    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;
    private final Duration baseTtl;
    private final long jitterSeconds;

    public RedisMarketQuoteCache(
        StringRedisTemplate redisTemplate,
        ObjectMapper objectMapper,
        @Value("${aiquant.cache.quote-ttl:20s}") Duration baseTtl,
        @Value("${aiquant.cache.ttl-jitter-seconds:10}") long jitterSeconds
    ) {
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
        this.baseTtl = baseTtl;
        this.jitterSeconds = Math.max(jitterSeconds, 0);
    }

    @Override
    public Optional<QuoteResponse> get(String symbol) {
        try {
            String value = redisTemplate.opsForValue().get(KEY_PREFIX + symbol);
            return value == null ? Optional.empty() : Optional.of(objectMapper.readValue(value, QuoteResponse.class));
        } catch (Exception exception) {
            log.warn("market_cache_read_failed symbol={}", symbol, exception);
            return Optional.empty();
        }
    }

    @Override
    public void put(QuoteResponse quote) {
        try {
            long jitter = jitterSeconds == 0 ? 0 : ThreadLocalRandom.current().nextLong(jitterSeconds + 1);
            redisTemplate.opsForValue().set(
                KEY_PREFIX + quote.symbol(),
                objectMapper.writeValueAsString(quote),
                baseTtl.plusSeconds(jitter)
            );
        } catch (JsonProcessingException exception) {
            log.warn("market_cache_serialization_failed symbol={}", quote.symbol(), exception);
        } catch (RuntimeException exception) {
            log.warn("market_cache_write_failed symbol={}", quote.symbol(), exception);
        }
    }
}
