package com.aiquant.market.service;

import com.aiquant.market.api.DataStatus;
import com.aiquant.market.api.QuoteResponse;
import com.aiquant.market.cache.MarketQuoteCache;
import com.aiquant.market.messaging.MarketEventPublisher;
import com.aiquant.market.persistence.MarketQuoteSnapshot;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Value;
import java.sql.Timestamp;

@Service
public class MarketSnapshotWriter {
    private final JdbcClient jdbcClient;
    private final MarketQuoteCache cache;
    private final MarketEventPublisher eventPublisher;
    private final String schema;
    private final java.util.Map<String, java.time.Instant> published = new java.util.concurrent.ConcurrentHashMap<>();

    public MarketSnapshotWriter(
        JdbcClient jdbcClient,
        MarketQuoteCache cache,
        MarketEventPublisher eventPublisher,
        @Value("${DATABASE_SCHEMA:public}") String schema
    ) {
        this.jdbcClient = jdbcClient;
        this.cache = cache;
        this.eventPublisher = eventPublisher;
        if (!schema.matches("[a-zA-Z_][a-zA-Z0-9_]*")) throw new IllegalArgumentException("Invalid database schema");
        this.schema = schema;
    }

    public QuoteResponse save(MarketQuoteSnapshot snapshot) {
        return save(snapshot, DataStatus.CACHED);
    }

    public QuoteResponse save(MarketQuoteSnapshot snapshot, DataStatus status) {
        persist(snapshot);
        QuoteResponse quote = new QuoteResponse(
            snapshot.getSymbol(), snapshot.getDisplayName(), snapshot.getPrice(), snapshot.getChange(),
            snapshot.getChangePct(), snapshot.getSource(), status, snapshot.getObservedAt()
        );
        cache.put(quote);
        if (!snapshot.getObservedAt().equals(published.get(snapshot.getSymbol()))) {
            try {
                eventPublisher.quoteUpdated(quote);
                published.put(snapshot.getSymbol(), snapshot.getObservedAt());
            }
            catch (RuntimeException error) { org.slf4j.LoggerFactory.getLogger(getClass()).warn("market_event_failed", error); }
        }
        return quote;
    }

    private int persist(MarketQuoteSnapshot snapshot) {
        return jdbcClient.sql("""
                insert into %s.market_quote_snapshot as stored (
                    symbol, display_name, price, price_change, change_pct, source, observed_at
                ) values (
                    :symbol, :displayName, :price, :change, :changePct, :source, :observedAt
                )
                on conflict (symbol, source, observed_at) do update set
                    display_name = excluded.display_name, price = excluded.price,
                    price_change = excluded.price_change, change_pct = excluded.change_pct
                where (stored.price, stored.price_change, stored.change_pct, stored.display_name)
                    is distinct from (excluded.price, excluded.price_change, excluded.change_pct, excluded.display_name)
                """.formatted(schema))
            .param("symbol", snapshot.getSymbol())
            .param("displayName", snapshot.getDisplayName())
            .param("price", snapshot.getPrice())
            .param("change", snapshot.getChange())
            .param("changePct", snapshot.getChangePct())
            .param("source", snapshot.getSource())
            .param("observedAt", Timestamp.from(snapshot.getObservedAt()))
            .update();
    }

    public void saveHistory(String symbol, String displayName, MarketFeedSnapshot.Bar bar) {
        persist(new MarketQuoteSnapshot(symbol, displayName, bar.price(), bar.change(), bar.changePct(),
            "新浪期货日K", bar.timestamp()));
    }

    public void saveContract(String rootSymbol, MarketFeedSnapshot.Contract contract) {
        jdbcClient.sql("""
            insert into %s.market_term_snapshot(root_symbol, contract_symbol, maturity_date, price, observed_at)
            values (:root, :contract, :maturity, :price, :observed)
            on conflict (contract_symbol, observed_at) do nothing
            """.formatted(schema))
            .param("root", rootSymbol).param("contract", contract.contract())
            .param("maturity", contract.maturityDate()).param("price", contract.price())
            .param("observed", Timestamp.from(contract.dataTimestamp())).update();
    }
}
