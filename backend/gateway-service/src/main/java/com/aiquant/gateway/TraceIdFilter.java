package com.aiquant.gateway;

import java.util.Optional;
import java.util.UUID;

import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class TraceIdFilter implements GlobalFilter, Ordered {
    public static final String TRACE_HEADER = "X-Trace-Id";

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        String traceId = Optional.ofNullable(exchange.getRequest().getHeaders().getFirst(TRACE_HEADER))
            .filter(value -> !value.isBlank())
            .map(value -> value.substring(0, Math.min(value.length(), 128)))
            .orElseGet(() -> UUID.randomUUID().toString().replace("-", ""));

        ServerHttpRequest request = exchange.getRequest().mutate().header(TRACE_HEADER, traceId).build();
        exchange.getResponse().getHeaders().set(TRACE_HEADER, traceId);
        return chain.filter(exchange.mutate().request(request).build());
    }

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }
}
