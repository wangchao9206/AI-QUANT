package com.aiquant.market.service;

import com.aiquant.market.api.DataStatus;
import com.aiquant.market.api.HistoryPoint;
import com.aiquant.market.api.HistoryResponse;
import com.aiquant.market.api.QuoteResponse;
import com.aiquant.market.api.TermStructurePoint;
import com.aiquant.market.api.TermStructureResponse;
import com.aiquant.market.cache.MarketQuoteCache;
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

@Service
public class MarketService {
    private final MarketQuoteCache cache;
    private final MarketQuoteRepository quoteRepository;
    private final MarketTermRepository termRepository;

    public MarketService(
        MarketQuoteCache cache,
        MarketQuoteRepository quoteRepository,
        MarketTermRepository termRepository
    ) {
        this.cache = cache;
        this.quoteRepository = quoteRepository;
        this.termRepository = termRepository;
    }

    public QuoteResponse currentQuote(String rawSymbol) {
        String symbol = SymbolNormalizer.normalize(rawSymbol);
        return cache.get(symbol)
            .map(quote -> quote.withStatus(DataStatus.CACHED))
            .orElseGet(() -> quoteRepository.findFirstBySymbolOrderByObservedAtDesc(symbol)
                .map(this::toDegradedQuote)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "No trusted quote available")));
    }

    public HistoryResponse history(String rawSymbol, Instant from, int limit) {
        String symbol = SymbolNormalizer.normalize(rawSymbol);
        Instant safeFrom = from == null ? Instant.now().minus(Duration.ofDays(30)) : from;
        List<MarketQuoteSnapshot> snapshots = new ArrayList<>(quoteRepository
            .findBySymbolAndObservedAtGreaterThanEqualOrderByObservedAtDesc(
                symbol,
                safeFrom,
                PageRequest.of(0, Math.min(Math.max(limit, 1), 1000))
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
