package com.aiquant.chanlun;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class LabControllerTests {
    @Test void rejectsWrongDatasetAndUnreconciledResults() throws Exception {
        var mapper=new ObjectMapper();var report=mapper.createObjectNode();
        var request=new LabController.Request(UUID.randomUUID(),"THIRD",1000000);
        assertThrows(IllegalStateException.class,()->LabController.validate(report,request));
        report.put("executable",false).put("engineVersion","native-chan-cost-lab-v1").put("configHash","a".repeat(64));
        report.putObject("config").put("group","THIRD").put("initialCash",1000000)
            .put("datasetHash","f069d8c21ec41d106f4b21c90f9e04d4d285d00847c8f551ff11991e38768577");
        var variants=report.putArray("variants");
        for(String id:java.util.List.of("NATIVE_BASE","NATIVE_DOUBLE_COST","NATIVE_DELAY_ONE","RANGE_RETEST","CHANNEL_BREAKOUT")) {
            var variant=variants.addObject().put("id",id);variant.putObject("metrics").put("netPnl",-20).put("finalEquity",999980);
            variant.putArray("trades").addObject().put("netPnl",-20);
        }
        assertDoesNotThrow(()->LabController.validate(report,request));
        ((com.fasterxml.jackson.databind.node.ObjectNode)report.at("/variants/0/metrics")).put("netPnl",100);
        assertThrows(IllegalStateException.class,()->LabController.validate(report,request));
        ((com.fasterxml.jackson.databind.node.ObjectNode)report.at("/variants/0/metrics")).remove("finalEquity");
        assertThrows(IllegalStateException.class,()->LabController.validate(report,request));
    }
}
