package com.aiquant.chanlun;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class MultiframeControllerTests {
    @Test void verifiesEveryFrameAndRejectsLaterConfirmation() {
        var mapper=new ObjectMapper();var request=new MultiframeController.Request(UUID.randomUUID(),"FU2701","PAIR",null);
        var r=mapper.createObjectNode().put("executable",false).put("configHash","a".repeat(64)).put("asOf","2026-10-30T10:00:00+08:00").put("capturedAt","2026-10-31T12:00:00+08:00");
        r.putObject("config").put("symbol","FU2701");var frames=r.putArray("frames");
        for(String f:java.util.List.of("MIN5","MIN30")){
            var a=frames.addObject().put("frequency",f).putObject("analysis").put("symbol","FU2701").put("frequency",f).put("observedBars",50).put("priceBasis","UNADJUSTED_DELIVERY").put("executable",false).put("profileHash","b".repeat(64)).put("inputHash","c".repeat(64));
            var bars=a.putArray("bars");for(int i=0;i<50;i++)bars.addObject().put("index",i).put("sealedByTimestamp","2026-10-30T10:00:00+08:00");a.putArray("structures");
        }
        assertDoesNotThrow(()->MultiframeController.validate(r,request));
        ((ObjectNode)r.at("/frames/1/analysis/bars/49")).put("sealedByTimestamp","2026-10-30T10:30:00+08:00");
        assertThrows(IllegalStateException.class,()->MultiframeController.validate(r,request));
        r.withArray("frames").remove(1);assertThrows(IllegalStateException.class,()->MultiframeController.validate(r,request));
    }
}
