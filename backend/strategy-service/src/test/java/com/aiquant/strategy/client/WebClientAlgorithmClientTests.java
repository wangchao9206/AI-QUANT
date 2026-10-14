package com.aiquant.strategy.client;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

class WebClientAlgorithmClientTests {
    @Test
    void retriesShareOneTotalDeadline() {
        AtomicInteger requests = new AtomicInteger();
        WebClient webClient = WebClient.builder().exchangeFunction(request -> {
            requests.incrementAndGet();
            return Mono.delay(Duration.ofMillis(150))
                .flatMap(ignored -> Mono.error(new IllegalStateException("upstream unavailable")));
        }).build();
        var client = new WebClientAlgorithmClient(webClient, Duration.ofMillis(200), 1);
        assertThatThrownBy(() -> client.predict("CJ2701", "timeout-test")).isInstanceOf(RuntimeException.class);
        assertThat(requests).hasValue(1);
    }
}
