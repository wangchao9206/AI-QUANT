package com.aiquant.chanlun;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.Map;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class MonitorControllerTests {
    @Test void initialClosedDelayedAndDailyRecordsCannotBecomeFreshAlerts() {
        var mapper=new ObjectMapper();var analysis=mapper.createObjectNode().put("frequency","MIN5");
        analysis.putArray("bars").addObject().put("timestamp","2026-10-30T09:00:00+08:00");
        var event=mapper.createObjectNode().put("observedIndex",0);
        Instant now=Instant.parse("2026-10-30T01:05:30Z");
        assertEquals("SUPPRESSED_BOOTSTRAP",MonitorController.inboxState(event,analysis,true,0,now));
        assertEquals("SUPPRESSED_CLOSED",MonitorController.inboxState(event,analysis,false,1,now));
        assertEquals("SUPPRESSED_BACKFILL",MonitorController.inboxState(event,analysis,true,1,now));
        analysis.withArray("bars").addObject().put("timestamp","2026-10-30T09:00:00+08:00");event.put("observedIndex",1);
        assertEquals("NEW",MonitorController.inboxState(event,analysis,true,1,now));
        assertEquals("SUPPRESSED_BACKFILL",MonitorController.inboxState(event,analysis,true,1,now.plusSeconds(180)));
        analysis.put("frequency","DAY");assertEquals("SUPPRESSED_BACKFILL",MonitorController.inboxState(event,analysis,true,1,now));
    }
    @Test void invalidOrFutureMonitorAnalysisIsRejected() {
        var mapper=new ObjectMapper();var analysis=mapper.createObjectNode();
        var previous=Map.<String,Object>of("symbol","FU2701","frequency","MIN5");
        assertThrows(IllegalStateException.class,()->MonitorController.validate(analysis,previous));
        analysis.put("engineId","native").put("executable",false).put("observedBars",50).put("symbol","FU2701").put("frequency","MIN5").put("profileHash","a".repeat(64)).put("inputHash","b".repeat(64));
        var bars=analysis.putArray("bars");for(int i=0;i<50;i++)bars.addObject().put("index",i);
        analysis.putArray("events");assertDoesNotThrow(()->MonitorController.validate(analysis,previous));
        analysis.withArray("events").addObject().put("type","BSP").put("observedIndex",50).put("endIndex",49);
        assertThrows(IllegalStateException.class,()->MonitorController.validate(analysis,previous));
    }
}
