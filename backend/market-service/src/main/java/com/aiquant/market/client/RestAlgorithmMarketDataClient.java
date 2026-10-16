package com.aiquant.market.client;

import com.aiquant.market.api.HistoryResponse;
import com.aiquant.market.api.InstrumentCatalogResponse;
import com.aiquant.market.api.MarketMicrostructureResponse;
import com.aiquant.market.api.QuoteResponse;
import com.aiquant.market.api.ProviderStatusResponse;
import com.aiquant.market.api.TermStructureResponse;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class RestAlgorithmMarketDataClient implements AlgorithmMarketDataClient {
    private final RestClient restClient;

    public RestAlgorithmMarketDataClient(
        @Value("${aiquant.market-data.base-url:http://localhost:8000}") String baseUrl,
        @Value("${aiquant.market-data.connect-timeout:1s}") Duration connectTimeout,
        @Value("${aiquant.market-data.read-timeout:15s}") Duration readTimeout
    ) {
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(connectTimeout);
        requestFactory.setReadTimeout(readTimeout);
        this.restClient = RestClient.builder()
            .baseUrl(baseUrl)
            .requestFactory(requestFactory)
            .build();
    }

    @Override
    public InstrumentCatalogResponse instruments() {
        return required(restClient.get()
            .uri("/api/v1/market/instruments")
            .retrieve()
            .body(InstrumentCatalogResponse.class));
    }

    @Override
    public ProviderStatusResponse providerStatus() {
        return required(restClient.get()
            .uri("/api/v1/market/provider")
            .retrieve()
            .body(ProviderStatusResponse.class));
    }

    @Override
    public QuoteResponse quote(String symbol) {
        return required(restClient.get()
            .uri("/api/v1/market/{symbol}/quote", symbol)
            .retrieve()
            .body(QuoteResponse.class));
    }

    @Override
    public HistoryResponse history(String symbol, int limit) {
        return required(restClient.get()
            .uri(builder -> builder
                .path("/api/v1/market/{symbol}/history")
                .queryParam("limit", limit)
                .build(symbol))
            .retrieve()
            .body(HistoryResponse.class));
    }

    @Override
    public TermStructureResponse termStructure(String rootSymbol) {
        return required(restClient.get()
            .uri("/api/v1/market/{rootSymbol}/term-structure", rootSymbol)
            .retrieve()
            .body(TermStructureResponse.class));
    }

    @Override
    public MarketMicrostructureResponse microstructure(String symbol) {
        return required(restClient.get()
            .uri("/api/v1/market/{symbol}/microstructure", symbol)
            .retrieve()
            .body(MarketMicrostructureResponse.class));
    }

    @Override
    public String leads() {
        return required(restClient.get()
            .uri("/api/v1/market/leads")
            .retrieve()
            .body(String.class));
    }


    private static <T> T required(T response) {
        if (response == null) {
            throw new IllegalStateException("Algorithm market data service returned an empty response");
        }
        return response;
    }
}
