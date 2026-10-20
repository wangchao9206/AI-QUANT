package com.aiquant.paper.service;
import com.aiquant.paper.service.PersonalTrainingStatistics.Fill;
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class PersonalTrainingStatisticsTests {
    @Test void partialClosesAreOneTradeAndFeesAreCountedOnce() {
        var m=PersonalTrainingStatistics.calculate(100000,List.of(100000.0,105000.0,102000.0),List.of(
            new Fill("OPEN",2,0,4,1000.0),new Fill("CLOSE",1,100,2,null),new Fill("CLOSE",1,-200,2,null),new Fill("OPEN",1,0,2,1000.0)));
        assertEquals(1,m.get("closedTradeCount"));assertEquals(-108.0,m.get("closedNetPnl"));
        assertEquals(0,m.get("winningTradeCount"));assertEquals(2.8571,m.get("maxDrawdownPct"));
        assertEquals("INSUFFICIENT_SAMPLE",m.get("validationStatus"));
    }
    @Test void reportsGapLossBeyondPlanRatherThanClampingItToBudget() {
        var m=PersonalTrainingStatistics.calculate(10000,List.of(10000.0,8800.0),List.of(new Fill("OPEN",1,0,2,100.0),new Fill("CLOSE",1,-1196,2,null)));
        assertEquals(1,m.get("lossBeyondBudgetCount"));assertEquals(-1200.0,m.get("closedNetPnl"));assertEquals(12.0,m.get("maxDrawdownPct"));
    }
}
