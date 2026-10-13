package com.aiquant.market.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;

@Entity
@Table(name = "market_term_snapshot")
public class MarketTermSnapshot {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "root_symbol", nullable = false)
    private String rootSymbol;

    @Column(name = "contract_symbol", nullable = false)
    private String contractSymbol;

    @Column(name = "maturity_date", nullable = false)
    private LocalDate maturityDate;

    @Column(nullable = false, precision = 20, scale = 6)
    private BigDecimal price;

    @Column(name = "observed_at", nullable = false)
    private Instant observedAt;

    protected MarketTermSnapshot() {
    }

    public MarketTermSnapshot(
        String rootSymbol,
        String contractSymbol,
        LocalDate maturityDate,
        BigDecimal price,
        Instant observedAt
    ) {
        this.rootSymbol = rootSymbol;
        this.contractSymbol = contractSymbol;
        this.maturityDate = maturityDate;
        this.price = price;
        this.observedAt = observedAt;
    }

    public String getContractSymbol() {
        return contractSymbol;
    }

    public LocalDate getMaturityDate() {
        return maturityDate;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public Instant getObservedAt() {
        return observedAt;
    }
}
