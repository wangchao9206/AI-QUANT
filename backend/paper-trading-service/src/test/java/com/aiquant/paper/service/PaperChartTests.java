package com.aiquant.paper.service;

import com.aiquant.paper.client.SimulationDataClient;
import com.aiquant.paper.client.SimulationDataClient.HistoricalBar;
import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.transaction.support.TransactionTemplate;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class PaperChartTests {
    final JdbcTemplate jdbc = mock(JdbcTemplate.class);
    final SimulationDataClient data = mock(SimulationDataClient.class);
    final PaperTradingService service = new PaperTradingService(jdbc, mock(TransactionTemplate.class), data, new MatchingEngine());
    final UUID id = UUID.randomUUID();
    final Instant clock = Instant.parse("2025-01-06T07:00:00Z");

    HistoricalBar bar(Instant stamp, String contract, int price) {
        var p = BigDecimal.valueOf(price);
        return new HistoricalBar(stamp, contract, p, p, p, p, 100, 200);
    }

    @Test
    @SuppressWarnings("unchecked")
    void includesChartFillsFromTheSameAccountAndClockIndependentlyOfPagination() {
        when(jdbc.queryForMap(anyString(), eq(id))).thenReturn(Map.of("mode", "LIVE", "symbol", "JM0",
            "current_market_time", Timestamp.from(clock), "current_bar_index", 0, "data_source", "observed"));
        when(data.chart("JM0", clock, 2)).thenReturn(new SimulationDataClient.ChartContext("archive", clock,
            List.of(bar(clock.minusSeconds(3*86400), "JM2701", 99), bar(clock, "JM2701", 100))));
        var result = service.chart(id, 1);
        assertEquals(1, ((List<?>)result.get("bars")).size());
        assertNotNull(result.get("fills"));
        // Friday 18:00 Shanghai is the lower bound for Monday's first visible
        // trading day. Earlier Friday daytime/night fills must not migrate to it.
        Instant start = Instant.parse("2025-01-03T10:00:00Z");
        verify(jdbc).query(contains("and market_time >= ? and market_time <= ? order by market_time, created_at, id"),
            any(RowMapper.class), eq(id), eq(Timestamp.from(start)), eq(Timestamp.from(clock)));
    }

    @Test
    @SuppressWarnings("unchecked")
    void excludesFutureAndArchiveRevisionsOfFrozenBars() {
        when(jdbc.queryForMap(anyString(), eq(id))).thenReturn(Map.of("mode", "HISTORICAL", "symbol", "CJ0",
            "current_market_time", Timestamp.from(clock), "current_bar_index", 2, "data_source", "frozen"));
        when(jdbc.queryForObject(anyString(), eq(Timestamp.class), eq(id))).thenReturn(Timestamp.from(clock.minusSeconds(86400)));
        var frozen = bar(clock, "CJ505", 100);
        when(jdbc.query(anyString(), any(RowMapper.class), eq(id), eq(2), eq(Timestamp.from(clock)), eq(240)))
            .thenReturn(List.of(frozen));
        when(data.chart("CJ0", clock, 240)).thenReturn(new SimulationDataClient.ChartContext("archive", clock,
            List.of(bar(clock.plusSeconds(86400), "CJ505", 999), bar(clock, "CJ505", 888),
                bar(clock.minusSeconds(172800), "CJ501", 95))));
        var result = service.chart(id, 240);
        var bars = (List<HistoricalBar>) result.get("bars");
        assertEquals(2, bars.size());
        assertEquals(frozen, bars.get(1));
        assertTrue(bars.stream().noneMatch(b -> b.timestamp().isAfter(clock)));
        verify(jdbc).query(contains("bar_index <= ? and market_time <= ?"), any(RowMapper.class), eq(id), eq(2), eq(Timestamp.from(clock)), eq(240));
    }

    @Test
    @SuppressWarnings("unchecked")
    void backgroundFailureKeepsSessionBarsAndRejectsInvalidBounds() {
        when(jdbc.queryForMap(anyString(), eq(id))).thenReturn(Map.of("mode", "HISTORICAL", "symbol", "CJ0",
            "current_market_time", Timestamp.from(clock), "current_bar_index", 2, "data_source", "frozen"));
        when(jdbc.queryForObject(anyString(), eq(Timestamp.class), eq(id))).thenReturn(Timestamp.from(clock));
        when(jdbc.query(anyString(), any(RowMapper.class), eq(id), eq(2), eq(Timestamp.from(clock)), eq(120)))
            .thenReturn(List.of(bar(clock, "CJ505", 100)));
        when(data.chart("CJ0", clock, 120)).thenThrow(new IllegalStateException("unavailable"));
        var result = service.chart(id, 120);
        assertEquals("UNAVAILABLE", result.get("contextStatus"));
        assertEquals(1, ((List<?>)result.get("bars")).size());
        assertThrows(IllegalArgumentException.class, () -> service.chart(id, 1001));
        assertThrows(IllegalArgumentException.class, () -> service.records(id, "unknown", 1, 20));
        assertThrows(IllegalArgumentException.class, () -> service.records(id, "fills", 0, 20));
    }
}
