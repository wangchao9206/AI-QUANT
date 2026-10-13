package com.aiquant.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.gateway.filter.GlobalFilter;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "spring.cloud.nacos.discovery.enabled=false",
        "spring.cloud.sentinel.enabled=false"
    }
)
class GatewayApplicationTests {
    @Autowired
    private TraceIdFilter traceIdFilter;

    @Test
    void contextLoadsWithTraceFilter() {
        assertThat(traceIdFilter).isInstanceOf(GlobalFilter.class);
    }
}
