package com.aiquant.paper.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.*;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class PaperReplayChartTests {
    ObjectMapper json=new ObjectMapper();
    ObjectNode archive(){
        var root=json.createObjectNode();root.putArray("completeTradingDates").add("2026-10-19");var rows=root.putArray("minuteBars");
        for(String session:List.of("2026-10-16T13:00:00Z/120","2026-10-19T01:00:00Z/75","2026-10-19T02:30:00Z/60","2026-10-19T05:30:00Z/90")){
            var parts=session.split("/");Instant start=Instant.parse(parts[0]);
            for(int i=0;i<Integer.parseInt(parts[1]);i++)rows.addObject().put("timestamp",start.plusSeconds(i*60).toString()).put("tradingDate","2026-10-19")
                .put("contract","FG701").put("open",840).put("high",842).put("low",839).put("close",841).put("volume",10).put("openInterest",100);
        }return root;
    }
    @Test void all_periods_include_correct_completed_ohlcv_and_close_fragments(){
        var a=archive();
        int[] expected={345,115,69,23,12,6,1};int i=0;
        for(int period:PaperReplayChart.PERIODS){
            var bars=PaperReplayChart.bars(a,Instant.parse("2026-10-19T07:00:00Z"),period,1000);
            assertEquals(expected[i++],bars.size());assertEquals(3450L,bars.stream().mapToLong(b->(long)b.get("volume")).sum());
            assertTrue(bars.stream().allMatch(b->!((Instant)b.get("endTime")).isAfter(Instant.parse("2026-10-19T07:00:00Z"))));
        }
    }
    @Test void friday_night_belongs_to_monday_daily_and_is_hidden_until_monday_close(){
        var a=archive();assertTrue(PaperReplayChart.bars(a,Instant.parse("2026-10-19T06:59:00Z"),86400,240).isEmpty());
        var daily=PaperReplayChart.bars(a,Instant.parse("2026-10-19T07:00:00Z"),86400,240).get(0);
        assertEquals(Instant.parse("2026-10-16T13:00:00Z"),daily.get("startTime"));assertEquals("2026-10-19",daily.get("tradingDate"));
        assertEquals(Instant.parse("2026-10-18T16:00:00Z"),daily.get("timestamp"));
    }
    @Test void an_unfinished_period_and_future_extreme_price_are_never_revealed(){
        var a=archive();var cutoff=Instant.parse("2026-10-16T13:04:00Z");
        assertTrue(PaperReplayChart.bars(a,cutoff,300,240).isEmpty());
        var before=PaperReplayChart.bars(a,cutoff,180,240);
        ((ObjectNode)a.path("minuteBars").get(10)).put("high",1000000).put("volume",9000000);
        assertEquals(before,PaperReplayChart.bars(a,cutoff,180,240));assertEquals(1,before.size());
    }
    @Test void missing_day_or_unsupported_period_is_not_silently_fabricated(){
        var a=archive();a.putArray("completeTradingDates");assertTrue(PaperReplayChart.bars(a,Instant.MAX,60,240).isEmpty());
        assertThrows(IllegalArgumentException.class,()->PaperReplayChart.bars(archive(),Instant.MAX,120,240));
    }
}
