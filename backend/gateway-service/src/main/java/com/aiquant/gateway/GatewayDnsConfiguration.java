package com.aiquant.gateway;

import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.gateway.config.HttpClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods=false)
public class GatewayDnsConfiguration {
    @Bean
    HttpClientCustomizer boundedDnsCache(@Value("${aiquant.gateway.dns-cache-seconds:5}") int seconds) {
        if(seconds<0)throw new IllegalArgumentException("DNS cache duration cannot be negative");
        return client->client.resolver(resolver->resolver
            .cacheMaxTimeToLive(Duration.ofSeconds(seconds))
            .cacheMinTimeToLive(Duration.ZERO)
            .cacheNegativeTimeToLive(Duration.ZERO));
    }
}
