package com.aiquant.strategy.config;

import java.util.concurrent.Executor;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class StrategyExecutorConfiguration {
    @Bean(name = "strategyExecutor")
    Executor strategyExecutor(
        @Value("${aiquant.executor.core-size:16}") int coreSize,
        @Value("${aiquant.executor.max-size:32}") int maxSize,
        @Value("${aiquant.executor.queue-capacity:200}") int queueCapacity
    ) {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(coreSize);
        executor.setMaxPoolSize(maxSize);
        executor.setQueueCapacity(queueCapacity);
        executor.setThreadNamePrefix("strategy-calc-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);
        executor.initialize();
        return executor;
    }
}
