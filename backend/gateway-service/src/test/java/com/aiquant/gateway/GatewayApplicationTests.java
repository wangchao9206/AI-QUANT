package com.aiquant.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "spring.cloud.nacos.discovery.enabled=false",
        "spring.cloud.sentinel.enabled=false",
        "CORS_ALLOWED_ORIGINS=http://localhost:8088,http://127.0.0.1:8088"
    }
)
class GatewayApplicationTests {
    @Autowired
    private TraceIdFilter traceIdFilter;

    @Autowired
    private WebTestClient webTestClient;

    @Test
    void contextLoadsWithTraceFilter() {
        assertThat(traceIdFilter).isInstanceOf(GlobalFilter.class);
    }

    @Test
    void permitsBacktestPreflightFromBothLocalFrontendHosts() {
        assertBacktestPreflightAllowed("http://localhost:8088");
        assertBacktestPreflightAllowed("http://127.0.0.1:8088");
    }

    @Test
    void rejectsBacktestPreflightFromUnknownOrigins() {
        webTestClient.options()
            .uri("/api/v1/backtest/run")
            .header(HttpHeaders.ORIGIN, "https://example.invalid")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "content-type")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void permitsPaperSessionDeletePreflight() {
        webTestClient.options()
            .uri("/api/v1/paper/sessions/00000000-0000-0000-0000-000000000001")
            .header(HttpHeaders.ORIGIN, "http://127.0.0.1:8088")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "DELETE")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "http://127.0.0.1:8088"
            );
    }

    private void assertBacktestPreflightAllowed(String origin) {
        webTestClient.options()
            .uri("/api/v1/backtest/run")
            .header(HttpHeaders.ORIGIN, origin)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "content-type")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, origin);
    }
}
