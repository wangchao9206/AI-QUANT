package com.aiquant.strategy.messaging;

import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class StrategyMessagingConfiguration {
    @Bean
    @ConditionalOnMissingBean(StrategyEventPublisher.class)
    StrategyEventPublisher noOpStrategyEventPublisher() {
        return new NoOpStrategyEventPublisher();
    }
}
