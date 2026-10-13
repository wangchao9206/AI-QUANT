package com.aiquant.market.api;

import com.aiquant.market.service.MarketService;

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

    public MarketController(MarketService marketService) {
        this.marketService = marketService;
    }

    @GetMapping("/{symbol}/quote")
    public QuoteResponse quote(@PathVariable String symbol) {
        return marketService.currentQuote(symbol);
    }

    @GetMapping("/{symbol}/history")
    public HistoryResponse history(
        @PathVariable String symbol,
        @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) Instant from,
        @RequestParam(defaultValue = "240") int limit
    ) {
        return marketService.history(symbol, from, limit);
    }

    @GetMapping("/{rootSymbol}/term-structure")
    public TermStructureResponse termStructure(@PathVariable String rootSymbol) {
        return marketService.termStructure(rootSymbol);
    }
}
