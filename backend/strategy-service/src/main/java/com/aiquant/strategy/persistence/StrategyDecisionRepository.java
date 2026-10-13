package com.aiquant.strategy.persistence;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface StrategyDecisionRepository extends JpaRepository<StrategyDecisionSnapshot, Long> {
    Optional<StrategyDecisionSnapshot> findFirstBySymbolOrderByCalculatedAtDesc(String symbol);
}
