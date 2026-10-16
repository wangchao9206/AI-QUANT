package com.aiquant.paper.client;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.UriComponentsBuilder;

@Component
public class SimulationDataClient {
    private final RestClient algorithmClient;
    private final RestClient marketClient;

    public SimulationDataClient(
        @Value("${aiquant.algorithm-base-url}") String algorithmBaseUrl,
        @Value("${aiquant.market-base-url}") String marketBaseUrl,
        @Value("${aiquant.client.connect-timeout:2s}") Duration connectTimeout,
        @Value("${aiquant.client.read-timeout:180s}") Duration readTimeout
    ) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(connectTimeout);
        factory.setReadTimeout(readTimeout);
        this.algorithmClient = RestClient.builder().baseUrl(algorithmBaseUrl).requestFactory(factory).build();
        this.marketClient = RestClient.builder().baseUrl(marketBaseUrl).requestFactory(factory).build();
    }

    public SimulationDataset history(String symbol, LocalDate startDate, LocalDate endDate) {
        UriComponentsBuilder builder = UriComponentsBuilder
            .fromPath("/internal/v1/simulation/history/{symbol}");
        if (startDate != null) builder.queryParam("start_date", startDate);
        if (endDate != null) builder.queryParam("end_date", endDate);
        String uri = builder.buildAndExpand(symbol).encode().toUriString();
        SimulationDataset result = algorithmClient.get().uri(uri).retrieve().body(SimulationDataset.class);
        if (result == null || result.bars() == null || result.bars().size() < 2) {
            throw new IllegalStateException("真实历史数据不足，无法创建模拟会话");
        }
        return result;
    }

    public QuoteSnapshot quote(String symbol) {
        QuoteSnapshot result = marketClient.get()
            .uri("/api/v1/market/{symbol}/quote", symbol)
            .retrieve()
            .body(QuoteSnapshot.class);
        if (result == null || result.price() == null || result.price().signum() <= 0) {
            throw new IllegalStateException("真实行情不可用，模拟委托未执行");
        }
        return result;
    }

    public record SimulationDataset(
        String symbol,
        String providerSymbol,
        String source,
        Instant generatedAt,
        List<HistoricalBar> bars,
        List<RollEvent> rollEvents,
        Map<String, ContractSpec> contractSpecs
    ) {}

    public record HistoricalBar(
        Instant timestamp,
        String contract,
        BigDecimal open,
        BigDecimal high,
        BigDecimal low,
        BigDecimal close,
        long volume,
        long openInterest
    ) {}

    public record RollEvent(
        LocalDate executionDate,
        String fromContract,
        String toContract,
        BigDecimal oldOpen,
        BigDecimal newOpen
    ) {}

    public record ContractSpec(
        String contract,
        int volumeMultiple,
        BigDecimal priceTick,
        BigDecimal marginPerLot,
        BigDecimal commissionPerLot
    ) {}

    public record QuoteSnapshot(
        String symbol,
        String displayName,
        BigDecimal price,
        String source,
        String dataStatus,
        Instant dataTimestamp
    ) {}
}
