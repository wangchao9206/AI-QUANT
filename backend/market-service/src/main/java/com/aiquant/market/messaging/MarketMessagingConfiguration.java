package com.aiquant.market.messaging;

import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MarketMessagingConfiguration {
    @Bean
    @ConditionalOnMissingBean(MarketEventPublisher.class)
    MarketEventPublisher noOpMarketEventPublisher() {
        return new NoOpMarketEventPublisher();
    }
}
