package com.aiquant.market.persistence;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MarketQuoteRepository extends JpaRepository<MarketQuoteSnapshot, Long> {
    Optional<MarketQuoteSnapshot> findFirstBySymbolOrderByObservedAtDesc(String symbol);

    List<MarketQuoteSnapshot> findBySymbolAndObservedAtGreaterThanEqualOrderByObservedAtDesc(
        String symbol,
        Instant from,
        Pageable pageable
    );
}
