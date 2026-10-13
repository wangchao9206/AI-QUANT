package com.aiquant.strategy.client;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

class WebClientAlgorithmClientTests {
    @Test
    void retriesShareOneTotalDeadline() {
        WebClient webClient = WebClient.builder().exchangeFunction(request -> Mono.never()).build();
        var client = new WebClientAlgorithmClient(webClient, Duration.ofMillis(200), 1);
        long started = System.nanoTime();
        assertThatThrownBy(() -> client.predict("CJ2701", "timeout-test")).isInstanceOf(RuntimeException.class);
        assertThat(Duration.ofNanos(System.nanoTime() - started)).isLessThan(Duration.ofMillis(650));
    }
}
