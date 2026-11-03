package com.aiquant.chanlun;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ObservationComparisonTests {
    private final ObjectMapper mapper=new ObjectMapper();
    private ObjectNode event(String id,int observed,Boolean confirmed){
        var e=mapper.createObjectNode().put("id",id).put("type","BI").put("startIndex",0).put("endIndex",1).put("startPrice",100).put("endPrice",110).put("direction","UP").put("revision",1).put("eventType","OBSERVED").put("observedDate","2026-10-0"+(observed+1));
        if(confirmed==null)e.putNull("engineConfirmed");else e.put("engineConfirmed",confirmed);return e;
    }
    private ObservationComparison.Source source(String engine,JsonNode... events){
        var r=mapper.createObjectNode().put("engineId",engine).put("observedBars",5).put("datasetHash","frozen").put("priceBasis","causal").put("profileHash",engine+"-profile").put("engineVersion","fixed").put("observedAsOfDate","2026-10-05");r.putArray("layers").add("BI");var bars=r.putArray("bars");for(int i=0;i<5;i++)bars.addObject().put("index",i).put("date","2026-10-0"+(i+1));
        return new ObservationComparison.Source(UUID.randomUUID(),r,List.of(events));
    }
    @Test void firstDifferenceUsesObservationTimeAndKeepsAHistoryThatLaterConverges(){
        var a=source("native",event("a",2,true));var b=source("chanpy",event("b",3,true));
        var r=ObservationComparison.analyze(List.of(a,b),"BI","GEOMETRY",false);
        assertEquals(2,((Map<?,?>)r.get("firstDifference")).get("observedIndex"));
        assertEquals(1,r.get("differentObservationCount"));
        assertEquals(List.of(Map.of("startIndex",2,"endIndex",2)),r.get("spans"));
        assertTrue(ObservationComparison.stateAt(b,2).isEmpty());assertEquals(1,ObservationComparison.stateAt(b,3).size());
    }
    @Test void engineScopedIdsDoNotCreateDifferencesAndUnknownFlagsAreNotFalse(){
        var a=source("native",event("independent-a",2,false));var b=source("chanpy",event("independent-b",2,null));
        var geometry=ObservationComparison.analyze(List.of(a,b),"BI","GEOMETRY",false);
        assertNull(geometry.get("firstDifference"));assertNotNull(geometry.get("firstConfirmationDifference"));
        var withFlags=ObservationComparison.analyze(List.of(a,b),"BI","WITH_CONFIRMATION",false);
        assertNotNull(withFlags.get("firstDifference"));assertEquals("UNKNOWN",ObservationComparison.confirmation(b.events().get(0)));
    }
    @Test void retractionAndReobservationDoNotRewriteTheEarlierPrefix(){
        var first=event("a",1,true);var withdrawn=event("a",2,true).put("eventType","RETRACTED").put("revision",2);var restored=event("a",3,true).put("revision",3);
        var a=source("native",first,withdrawn,restored);var b=source("chanpy",event("b",1,true));
        var r=ObservationComparison.analyze(List.of(a,b),"BI","GEOMETRY",false);
        assertEquals(1,r.get("differentObservationCount"));assertEquals(1,ObservationComparison.stateAt(a,1).get("a").path("revision").asInt());assertTrue(ObservationComparison.stateAt(a,2).isEmpty());assertEquals(3,ObservationComparison.stateAt(a,3).get("a").path("revision").asInt());
    }
    @Test void sameGeometryUsesFixedPriceToleranceAndRejectsUnsupportedOrDifferentInputs(){
        var a=event("a",2,true);var b=event("b",2,true).put("endPrice",110.000000005);
        assertTrue(ObservationComparison.sameGeometry(a,b));b.put("endPrice",110.001);assertFalse(ObservationComparison.sameGeometry(a,b));
        var left=source("native",a);var right=source("chanpy",b);
        assertThrows(IllegalArgumentException.class,()->ObservationComparison.validateSources(List.of(left,right),"SEGMENT",false));
        ((ObjectNode)right.result().path("bars").get(0)).put("close",999);assertThrows(IllegalArgumentException.class,()->ObservationComparison.validateSources(List.of(left,right),"BI",false));
    }
}
