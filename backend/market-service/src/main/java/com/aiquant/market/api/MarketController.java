package com.aiquant.market.api;

import com.aiquant.market.service.MarketService;
import com.aiquant.market.service.MarketIngestionService;

import java.time.Instant;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/market")
public class MarketController {
    private final MarketService marketService;
    private final MarketIngestionService ingestion;

    public MarketController(MarketService marketService, MarketIngestionService ingestion) {
        this.marketService = marketService;
        this.ingestion = ingestion;
    }

    @GetMapping("/instruments")
    public InstrumentCatalogResponse instruments() {
        return marketService.instruments();
    }

    @GetMapping("/provider")
    public ProviderStatusResponse providerStatus() {
        return marketService.providerStatus();
    }

    @GetMapping("/{symbol}/quote")
    public QuoteResponse quote(@PathVariable String symbol) {
        ingestion.watch(symbol);
        return marketService.currentQuote(symbol);
    }

    @GetMapping("/{symbol}/history")
    public HistoryResponse history(
        @PathVariable String symbol,
        @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) Instant from,
        @RequestParam(defaultValue = "5000") int limit
    ) {
        ingestion.watch(symbol);
        return marketService.history(symbol, from, limit);
    }

    @GetMapping("/{rootSymbol}/term-structure")
    public TermStructureResponse termStructure(@PathVariable String rootSymbol) {
        return marketService.termStructure(rootSymbol);
    }

    @GetMapping("/{symbol}/microstructure")
    public MarketMicrostructureResponse microstructure(@PathVariable String symbol) {
        return marketService.microstructure(symbol);
    }

    @GetMapping(value = "/leads", produces = "application/json")
    public String leads() {
        return marketService.leads();
    }
}
