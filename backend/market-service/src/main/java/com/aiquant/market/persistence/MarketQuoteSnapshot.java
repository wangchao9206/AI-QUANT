package com.aiquant.market.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "market_quote_snapshot")
public class MarketQuoteSnapshot {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String symbol;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @Column(nullable = false, precision = 20, scale = 6)
    private BigDecimal price;

    @Column(name = "price_change", nullable = false, precision = 20, scale = 6)
    private BigDecimal change;

    @Column(name = "change_pct", nullable = false, precision = 12, scale = 6)
    private BigDecimal changePct;

    @Column(nullable = false)
    private String source;

    @Column(name = "observed_at", nullable = false)
    private Instant observedAt;

    protected MarketQuoteSnapshot() {
    }

    public MarketQuoteSnapshot(
        String symbol,
        String displayName,
        BigDecimal price,
        BigDecimal change,
        BigDecimal changePct,
        String source,
        Instant observedAt
    ) {
        this.symbol = symbol;
        this.displayName = displayName;
        this.price = price;
        this.change = change;
        this.changePct = changePct;
        this.source = source;
        this.observedAt = observedAt;
    }

    public String getSymbol() {
        return symbol;
    }

    public String getDisplayName() {
        return displayName;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public BigDecimal getChange() {
        return change;
    }

    public BigDecimal getChangePct() {
        return changePct;
    }

    public String getSource() {
        return source;
    }

    public Instant getObservedAt() {
        return observedAt;
    }
}
