package com.aiquant.market.service;

import com.aiquant.market.api.QuoteResponse;
import com.aiquant.market.persistence.MarketQuoteSnapshot;
import java.net.http.HttpClient;
import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class MarketIngestionService {
    private static final Logger log = LoggerFactory.getLogger(MarketIngestionService.class);
    private final RestClient client;
    private final MarketSnapshotWriter writer;
    private final Set<String> symbols = ConcurrentHashMap.newKeySet();
    private final Map<String, String> historyMarkers = new ConcurrentHashMap<>();
    private final int maxSymbols;

    public MarketIngestionService(RestClient.Builder builder, MarketSnapshotWriter writer,
        @Value("${aiquant.ingestion.base-url:http://localhost:8000}") String baseUrl,
        @Value("${aiquant.ingestion.symbols:CJ2612,CJ2701,CJ2703,CJ2705}") String configuredSymbols,
        @Value("${aiquant.ingestion.max-symbols:2048}") int maxSymbols,
        @Value("${aiquant.ingestion.read-timeout:6s}") Duration readTimeout) {
        var factory = new JdkClientHttpRequestFactory(HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(1)).build());
        factory.setReadTimeout(readTimeout);
        this.client = builder.baseUrl(baseUrl).requestFactory(factory).build();
        this.writer = writer;
        this.maxSymbols = maxSymbols;
        Arrays.stream(configuredSymbols.split(",")).filter(value -> !value.isBlank()).forEach(this::watch);
    }

    public void watch(String symbol) {
        String normalized = SymbolNormalizer.normalize(symbol);
        if (symbols.size() < maxSymbols || symbols.contains(normalized)) symbols.add(normalized);
    }

    @Scheduled(fixedDelayString = "${aiquant.ingestion.interval-ms:15000}", initialDelay = 2000)
    public void collect() {
        for (String symbol : Set.copyOf(symbols)) {
            try {
                ingest(symbol, client.get().uri("/api/v1/market/{symbol}/snapshot", symbol)
                    .retrieve().body(MarketFeedSnapshot.class));
            } catch (RuntimeException error) {
                log.warn("market_collection_failed symbol={} error={}", symbol, error.toString());
            }
        }
    }

    void ingest(String symbol, MarketFeedSnapshot snapshot) {
        if (snapshot == null) return;
        QuoteResponse quote = snapshot.quote();
        if (snapshot.history() != null && !snapshot.history().isEmpty()) {
            var lastBar = snapshot.history().get(snapshot.history().size() - 1);
            String marker = lastBar.timestamp() + ":" + lastBar.price().toPlainString();
            if (!marker.equals(historyMarkers.get(symbol))) {
                for (var bar : snapshot.history()) writer.saveHistory(symbol, quote == null ? symbol : quote.displayName(), bar);
                historyMarkers.put(symbol, marker);
            }
        }
        if (snapshot.contracts() != null) {
            String root = symbol.replaceAll("\\d+$", "").replaceAll("[M0]$", "");
            for (var contract : snapshot.contracts()) writer.saveContract(root, contract);
        }
        if (quote != null) writer.save(new MarketQuoteSnapshot(quote.symbol(), quote.displayName(), quote.price(),
            quote.change(), quote.changePct(), quote.source(), quote.dataTimestamp()), quote.dataStatus());
    }
}
