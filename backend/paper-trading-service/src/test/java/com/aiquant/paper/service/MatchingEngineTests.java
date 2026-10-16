package com.aiquant.paper.service;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class MatchingEngineTests {
    private final MatchingEngine engine = new MatchingEngine();
    private final MatchingEngine.BarView bar = new MatchingEngine.BarView(
        new BigDecimal("100"), new BigDecimal("108"), new BigDecimal("96"),
        new BigDecimal("104"), 1000
    );

    @Test
    void marketBuyUsesAdverseTickSlippageAndIntegerVolumeCap() {
        var result = engine.match(
            new MatchingEngine.OrderView("BUY", "MARKET", 20, null, null),
            bar, new BigDecimal("2"), BigDecimal.ONE, new BigDecimal("0.01")
        );

        assertThat(result.fillable()).isTrue();
        assertThat(result.fillPrice()).isEqualByComparingTo("102");
        assertThat(result.quantity()).isEqualTo(10);
    }

    @Test
    void limitOrderNeverFillsWorseThanItsLimit() {
        var result = engine.match(
            new MatchingEngine.OrderView("BUY", "LIMIT", 5, new BigDecimal("99"), null),
            bar, BigDecimal.ONE, new BigDecimal("3"), new BigDecimal("0.1")
        );

        assertThat(result.fillable()).isTrue();
        assertThat(result.fillPrice()).isEqualByComparingTo("99");
    }

    @Test
    void untouchedStopRemainsPending() {
        var result = engine.match(
            new MatchingEngine.OrderView("BUY", "STOP", 5, null, new BigDecimal("110")),
            bar, BigDecimal.ONE, BigDecimal.ONE, new BigDecimal("0.1")
        );

        assertThat(result.fillable()).isFalse();
    }
}
