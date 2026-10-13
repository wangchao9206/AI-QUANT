package com.aiquant.strategy.api;

import com.aiquant.strategy.service.StrategyService;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/predictions")
public class StrategyController {
    private final StrategyService strategyService;

    public StrategyController(StrategyService strategyService) {
        this.strategyService = strategyService;
    }

    @GetMapping("/{symbol}")
    public PredictionResponse prediction(
        @PathVariable String symbol,
        @RequestHeader(name = "X-Trace-Id", required = false) String traceId
    ) {
        return strategyService.prediction(symbol, traceId);
    }
}
