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
    void liveChartUsesActualContractAndLiveClockWithoutHistoricalDailyFallback() throws Exception {
        when(jdbc.queryForMap(anyString(), eq(id))).thenReturn(Map.of("mode", "LIVE", "symbol", "JM0",
            "current_contract","JM2701","current_market_time", Timestamp.from(clock), "current_bar_index", 0, "data_source", "observed"));
        Instant now=Instant.now(),start=now.minusSeconds(20);
        var raw=new com.fasterxml.jackson.databind.ObjectMapper().readTree("{\"symbol\":\"JM2701\",\"seconds\":60,\"dataStatus\":\"FRESH\",\"connected\":true,\"marketState\":\"LIVE\",\"dataTimestamp\":\""+now+"\",\"lastBarProvisional\":true,\"points\":[{\"timestamp\":\""+start+"\",\"open\":100,\"high\":102,\"low\":99,\"price\":101,\"volume\":10}]}");
        when(data.liveChart("JM2701",60,1)).thenReturn(raw);
        var result = service.chart(id,1);
        assertEquals(1, ((List<?>)result.get("bars")).size());
        assertEquals("LIVE",result.get("snapshotKind"));assertEquals("FRESH",result.get("dataStatus"));
        assertTrue(((Instant)result.get("asOf")).isAfter(clock));
        verify(data,never()).chart(anyString(),any(),anyInt());
        verify(jdbc).query(contains("and contract=?"),any(RowMapper.class),eq(id),eq(Timestamp.from(start)),any(Timestamp.class),eq("JM2701"));
    }

    @Test void liveSubscriptionFailureReturnsExplicitUnavailableRatherThanDailyHistory(){
        when(jdbc.queryForMap(anyString(),eq(id))).thenReturn(Map.of("mode","LIVE","symbol","JM0","current_contract","JM2701","current_market_time",Timestamp.from(clock),"current_bar_index",0));
        when(data.liveChart("JM2701",300,240)).thenThrow(new IllegalStateException("warming"));
        var result=service.chart(id,240,300);
        assertEquals("UNAVAILABLE",result.get("contextStatus"));assertEquals(List.of(),result.get("bars"));
        verify(data,never()).chart(anyString(),any(),anyInt());
        verify(data,never()).evaluate(any());
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
