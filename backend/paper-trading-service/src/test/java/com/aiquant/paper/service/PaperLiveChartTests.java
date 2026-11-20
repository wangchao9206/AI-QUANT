package com.aiquant.paper.service;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class PaperLiveChartTests {
    Instant now=Instant.parse("2026-11-18T01:30:30Z");
    ObjectNode raw()throws Exception{return (ObjectNode)new ObjectMapper().readTree("""
        {"symbol":"FG701","seconds":60,"source":"PRIMARY_LIVE","dataStatus":"FRESH","connected":true,
         "dataTimestamp":"2026-11-18T01:30:29Z","marketState":"LIVE","marketPhase":"OPEN","expectedTradingDate":"2026-11-18",
         "lastBarProvisional":true,"points":[{"timestamp":"2026-11-18T01:30:00Z","tradingDate":"2026-11-18","open":905,"high":907,"low":904,"price":906,"volume":10}]}
        """);}
    @Test void includesTheFormingMinuteAndOriginalQuoteTime()throws Exception{
        var result=PaperLiveChart.snapshot(raw(),"FG701",60,240,now);
        assertEquals("FRESH",result.get("dataStatus"));assertEquals(true,result.get("lastBarProvisional"));
        assertEquals("2026-11-18T01:30:29Z",result.get("dataTimestamp"));assertEquals(1,((List<?>)result.get("bars")).size());
    }
    @Test void newRetrievalTimeDoesNotMakeOldOrDisconnectedQuotesFresh()throws Exception{
        var raw=raw();raw.put("retrievedAt",now.toString());raw.put("dataTimestamp",now.minusSeconds(600).toString());
        assertEquals("CACHED",PaperLiveChart.snapshot(raw,"FG701",60,240,now).get("dataStatus"));
        raw.put("dataTimestamp",now.toString());raw.put("connected",false);
        assertEquals("CACHED",PaperLiveChart.snapshot(raw,"FG701",60,240,now).get("dataStatus"));
    }
    @Test void wrongDeliveryOrPeriodIsNeverPlotted()throws Exception{
        var raw=raw();assertThrows(IllegalStateException.class,()->PaperLiveChart.snapshot(raw,"FG705",60,240,now));
        assertThrows(IllegalStateException.class,()->PaperLiveChart.snapshot(raw,"FG701",300,240,now));
    }
    @Test void dayViewKeepsPastDaysClosedAndOnlyTheLatestDayForming()throws Exception{
        var raw=raw();raw.put("seconds",86400);var points=raw.withArray("points");
        ((ObjectNode)points.get(0)).put("timestamp","2026-11-16T16:00:00Z").put("tradingDate","2026-11-17");
        points.add(points.get(0).deepCopy());((ObjectNode)points.get(1)).put("timestamp","2026-11-17T16:00:00Z").put("tradingDate","2026-11-18");
        @SuppressWarnings("unchecked") var bars=(List<Map<String,Object>>)PaperLiveChart.snapshot(raw,"FG701",86400,240,now).get("bars");
        assertEquals(false,bars.get(0).get("provisional"));assertEquals(true,bars.get(1).get("provisional"));
    }
}
