package com.aiquant.market.service;

import com.aiquant.market.api.DataStatus;
import com.aiquant.market.api.QuoteResponse;
import com.aiquant.market.api.TermStructureResponse;
import com.aiquant.market.cache.MarketQuoteCache;
import com.aiquant.market.messaging.MarketEventPublisher;
import com.aiquant.market.persistence.MarketQuoteSnapshot;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;

import java.sql.Timestamp;

@Service
public class MarketSnapshotWriter {
    private final JdbcClient jdbcClient;
    private final MarketQuoteCache cache;
    private final MarketEventPublisher eventPublisher;

    public MarketSnapshotWriter(
        JdbcClient jdbcClient,
        MarketQuoteCache cache,
        MarketEventPublisher eventPublisher
    ) {
        this.jdbcClient = jdbcClient;
        this.cache = cache;
        this.eventPublisher = eventPublisher;
    }

    public QuoteResponse save(MarketQuoteSnapshot snapshot) {
        jdbcClient.sql("""
                insert into market_quote_snapshot (
                    symbol, display_name, price, price_change, change_pct, source, observed_at
                ) values (
                    :symbol, :displayName, :price, :change, :changePct, :source, :observedAt
                )
                on conflict (symbol, source, observed_at) do update set
                    display_name = excluded.display_name,
                    price = excluded.price,
                    price_change = excluded.price_change,
                    change_pct = excluded.change_pct
                """)
            .param("symbol", snapshot.getSymbol())
            .param("displayName", snapshot.getDisplayName())
            .param("price", snapshot.getPrice())
            .param("change", snapshot.getChange())
            .param("changePct", snapshot.getChangePct())
            .param("source", snapshot.getSource())
            .param("observedAt", Timestamp.from(snapshot.getObservedAt()))
            .update();
        QuoteResponse quote = new QuoteResponse(
            snapshot.getSymbol(),
            snapshot.getDisplayName(),
            snapshot.getPrice(),
            snapshot.getChange(),
            snapshot.getChangePct(),
            snapshot.getSource(),
            DataStatus.FRESH,
            snapshot.getObservedAt()
        );
        cache.put(quote);
        eventPublisher.quoteUpdated(quote);
        return quote;
    }

    public TermStructureResponse save(TermStructureResponse curve) {
        curve.contracts().forEach(contract -> jdbcClient.sql("""
                insert into market_term_snapshot (
                    root_symbol, contract_symbol, maturity_date, price, observed_at
                ) values (
                    :rootSymbol, :contractSymbol, :maturityDate, :price, :observedAt
                )
                on conflict (contract_symbol, observed_at) do update set
                    root_symbol = excluded.root_symbol,
                    maturity_date = excluded.maturity_date,
                    price = excluded.price
                """)
            .param("rootSymbol", curve.rootSymbol())
            .param("contractSymbol", contract.contract())
            .param("maturityDate", contract.maturityDate())
            .param("price", contract.price())
            .param("observedAt", Timestamp.from(curve.dataTimestamp()))
            .update());
        return curve;
    }
}
