package com.aiquant.strategy.client;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class AlgorithmClientConfiguration {
    @Bean
    WebClient algorithmWebClient(
        WebClient.Builder builder,
        @Value("${aiquant.algorithm.base-url:http://localhost:8000}") String baseUrl,
        @Value("${aiquant.algorithm.connect-timeout:1s}") Duration connectTimeout,
        @Value("${aiquant.algorithm.read-timeout:6s}") Duration readTimeout
    ) {
        HttpClient httpClient = HttpClient.create()
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, Math.toIntExact(connectTimeout.toMillis()))
            .responseTimeout(readTimeout);
        return builder
            .baseUrl(baseUrl)
            .clientConnector(new ReactorClientHttpConnector(httpClient))
            .build();
    }
}
