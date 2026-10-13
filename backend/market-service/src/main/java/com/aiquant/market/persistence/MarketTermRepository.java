package com.aiquant.market.persistence;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface MarketTermRepository extends JpaRepository<MarketTermSnapshot, Long> {
    @Query("""
        select snapshot from MarketTermSnapshot snapshot
        where snapshot.rootSymbol = :rootSymbol
          and snapshot.observedAt = (
              select max(latest.observedAt) from MarketTermSnapshot latest
              where latest.rootSymbol = :rootSymbol
          )
        order by snapshot.maturityDate asc
        """)
    List<MarketTermSnapshot> findLatestCurve(@Param("rootSymbol") String rootSymbol);
}
