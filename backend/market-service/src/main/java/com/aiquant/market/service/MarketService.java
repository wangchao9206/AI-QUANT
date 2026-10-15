package com.aiquant.market.service;

import com.aiquant.market.api.DataStatus;
import com.aiquant.market.api.HistoryPoint;
import com.aiquant.market.api.HistoryResponse;
import com.aiquant.market.api.InstrumentCatalogResponse;
import com.aiquant.market.api.QuoteResponse;
import com.aiquant.market.api.TermStructurePoint;
import com.aiquant.market.api.TermStructureResponse;
import com.aiquant.market.cache.MarketQuoteCache;
import com.aiquant.market.client.AlgorithmMarketDataClient;
import com.aiquant.market.persistence.MarketQuoteRepository;
import com.aiquant.market.persistence.MarketQuoteSnapshot;
import com.aiquant.market.persistence.MarketTermRepository;
import com.aiquant.market.persistence.MarketTermSnapshot;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Service
public class MarketService {
    private static final Logger log = LoggerFactory.getLogger(MarketService.class);

    private final MarketQuoteCache cache;
    private final MarketQuoteRepository quoteRepository;
    private final MarketTermRepository termRepository;
    private final AlgorithmMarketDataClient marketDataClient;
    private final MarketSnapshotWriter snapshotWriter;
    private volatile InstrumentCatalogResponse catalogCache;

    public MarketService(
        MarketQuoteCache cache,
        MarketQuoteRepository quoteRepository,
        MarketTermRepository termRepository,
        AlgorithmMarketDataClient marketDataClient,
        MarketSnapshotWriter snapshotWriter
    ) {
        this.cache = cache;
        this.quoteRepository = quoteRepository;
        this.termRepository = termRepository;
        this.marketDataClient = marketDataClient;
        this.snapshotWriter = snapshotWriter;
    }

    public QuoteResponse currentQuote(String rawSymbol) {
        String symbol = SymbolNormalizer.normalize(rawSymbol);
        return cache.get(symbol)
            .map(quote -> quote.withStatus(DataStatus.CACHED))
            .orElseGet(() -> loadLiveQuoteOrFallback(symbol));
    }

    public InstrumentCatalogResponse instruments() {
        try {
            InstrumentCatalogResponse live = marketDataClient.instruments();
            catalogCache = live;
            return live;
        } catch (RuntimeException exception) {
            log.warn("instrument_catalog_fetch_failed", exception);
            if (catalogCache != null) return catalogCache.withStatus(DataStatus.DEGRADED);
            throw new ResponseStatusException(
                HttpStatus.SERVICE_UNAVAILABLE,
                "No observed instrument catalog available",
                exception
            );
        }
    }

    public HistoryResponse history(String rawSymbol, Instant from, int limit) {
        String symbol = SymbolNormalizer.normalize(rawSymbol);
        int safeLimit = Math.min(Math.max(limit, 1), 1000);
        try {
            return marketDataClient.history(symbol, safeLimit);
        } catch (RuntimeException exception) {
            log.warn("live_history_fetch_failed symbol={}", symbol, exception);
        }
        Instant safeFrom = from == null ? Instant.now().minus(Duration.ofDays(30)) : from;
        List<MarketQuoteSnapshot> snapshots = new ArrayList<>(quoteRepository
            .findBySymbolAndObservedAtGreaterThanEqualOrderByObservedAtDesc(
                symbol,
                safeFrom,
                PageRequest.of(0, safeLimit)
            ));
        Collections.reverse(snapshots);
        List<HistoryPoint> points = snapshots.stream()
            .map(snapshot -> new HistoryPoint(snapshot.getObservedAt(), snapshot.getPrice(), snapshot.getChangePct()))
            .toList();
        Instant timestamp = points.isEmpty() ? safeFrom : points.get(points.size() - 1).timestamp();
        return new HistoryResponse(symbol, points.isEmpty() ? DataStatus.DEGRADED : DataStatus.CACHED, timestamp, points);
    }

    public TermStructureResponse termStructure(String rawRootSymbol) {
        String rootSymbol = SymbolNormalizer.normalize(rawRootSymbol);
        try {
            return snapshotWriter.save(marketDataClient.termStructure(rootSymbol));
        } catch (RuntimeException exception) {
            log.warn("live_term_structure_fetch_failed rootSymbol={}", rootSymbol, exception);
        }
        List<MarketTermSnapshot> snapshots = termRepository
            .findLatestCurve(rootSymbol);
        List<TermStructurePoint> contracts = snapshots.stream()
            .map(item -> new TermStructurePoint(item.getContractSymbol(), item.getMaturityDate(), item.getPrice()))
            .toList();
        Instant timestamp = snapshots.stream()
            .map(MarketTermSnapshot::getObservedAt)
            .max(Instant::compareTo)
            .orElse(Instant.EPOCH);
        return new TermStructureResponse(rootSymbol, contracts.isEmpty() ? DataStatus.DEGRADED : DataStatus.CACHED, timestamp, contracts);
    }

    private QuoteResponse loadLiveQuoteOrFallback(String symbol) {
        try {
            QuoteResponse live = marketDataClient.quote(symbol);
            return snapshotWriter.save(new MarketQuoteSnapshot(
                live.symbol(),
                live.displayName(),
                live.price(),
                live.change(),
                live.changePct(),
                live.source(),
                live.dataTimestamp()
            ));
        } catch (RuntimeException exception) {
            log.warn("live_quote_fetch_failed symbol={}", symbol, exception);
            return quoteRepository.findFirstBySymbolOrderByObservedAtDesc(symbol)
                .map(this::toDegradedQuote)
                .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "No trusted quote available",
                    exception
                ));
        }
    }

    private QuoteResponse toDegradedQuote(MarketQuoteSnapshot snapshot) {
        return new QuoteResponse(
            snapshot.getSymbol(),
            snapshot.getDisplayName(),
            snapshot.getPrice(),
            snapshot.getChange(),
            snapshot.getChangePct(),
            snapshot.getSource(),
            DataStatus.DEGRADED,
            snapshot.getObservedAt()
        );
    }
}
