package com.aiquant.strategy.persistence;

import java.util.Optional;
import java.time.Instant;

import org.springframework.data.jpa.repository.JpaRepository;

public interface StrategyDecisionRepository extends JpaRepository<StrategyDecisionSnapshot, Long> {
    Optional<StrategyDecisionSnapshot> findFirstBySymbolOrderByCalculatedAtDesc(String symbol);
    Optional<StrategyDecisionSnapshot> findBySymbolAndModelVersionAndInputTimestamp(String symbol, String modelVersion, Instant inputTimestamp);
}
