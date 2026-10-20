package com.aiquant.paper.service;

import com.aiquant.paper.client.SimulationDataClient.HistoricalBar;
import com.aiquant.paper.service.PersonalStrategyEngine.*;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class PersonalStrategyEngineTests {
    final PersonalStrategyEngine engine=new PersonalStrategyEngine();
    BigDecimal d(double v){return BigDecimal.valueOf(v);}
    List<HistoricalBar> bars(boolean shortSide,boolean roll) {
        var result=new ArrayList<HistoricalBar>();LocalDate date=LocalDate.of(2025,1,2);
        for(int i=0;i<132;i++) {
            while(date.getDayOfWeek()==DayOfWeek.SATURDAY||date.getDayOfWeek()==DayOfWeek.SUNDAY)date=date.plusDays(1);
            double close=i<100?80+i*.3:110,open=close-.1,high=close+.5,low=close-.5;
            if(i==130){open=110;close=113;high=114;low=110;}
            if(i==131){open=110.8;close=111.5;high=112.5;low=110.3;}
            if(shortSide){double oldHigh=high;open=200-open;close=200-close;high=200-low;low=200-oldHigh;}
            double gap=roll&&i>=115?40:0;
            result.add(new HistoricalBar(date.atStartOfDay(ZoneOffset.UTC).toInstant(),roll&&i>=115?"CJ509":"CJ505",
                d(open+gap),d(high+gap),d(low+gap),d(close+gap),i==130?2000:1000,10000));
            date=date.plusDays(1);
        }
        return result;
    }
    Account account(int lots,int direction,Double stop,Integer exit,boolean halted) {
        return new Account(100000,100000,lots,direction,110,.1,10,2000,1,.15,.0001,1,stop,lots>0?130:null,exit,0,halted);
    }
    @Test void waitsForConfirmationAndProducesRiskLimitedSymmetricEntries() {
        var series=bars(false,false);
        assertNotEquals("ENTER",engine.evaluate(series.subList(0,131),List.of(),account(0,0,null,null,false),Rules.defaults()).action());
        var p=engine.evaluate(series,List.of(),account(0,0,null,null,false),Rules.defaults());
        assertEquals("ENTER",p.action());assertEquals(1,p.direction());assertTrue(p.maxLots()>0);
        assertTrue(p.stopPrice()<p.entryPrice());assertTrue(p.plannedRisk()<=500);
        var shortPlan=engine.evaluate(bars(true,false),List.of(),account(0,0,null,null,false),Rules.defaults());
        assertEquals("ENTER",shortPlan.action());assertEquals(-1,shortPlan.direction());assertTrue(shortPlan.stopPrice()>shortPlan.entryPrice());
    }
    @Test void blocksWideStopsCooldownReusedSetupsAndDrawdownReentry() {
        var series=bars(false,false);var empty=account(0,0,null,null,false);
        assertEquals("STOP_TOO_FAR",engine.evaluate(series,List.of(),empty,new Rules(.5,20,1.5,1,3)).state());
        assertEquals("COOLDOWN",engine.evaluate(series,List.of(),account(0,0,null,130,false),Rules.defaults()).state());
        assertEquals("HALTED",engine.evaluate(series,List.of(),account(0,0,null,null,true),Rules.defaults()).state());
        assertNotEquals("ENTER",engine.evaluate(series,List.of(),account(0,0,null,130,false),new Rules(.5,20,1.5,2,2)).action());
    }
    @Test void tightensProtectionAndExitsHaltedPositionsWithoutAdding() {
        var p=engine.evaluate(bars(false,false),List.of(),account(2,1,110.0,null,false),Rules.defaults());
        assertEquals("HOLD",p.action());assertEquals(0,p.maxLots());assertTrue(p.stopPrice()>=110);
        assertEquals("EXIT",engine.evaluate(bars(false,false),List.of(),account(2,1,110.0,null,true),Rules.defaults()).action());
    }
    @Test void requiresObservedRollEvidenceAndIgnoresFutureRolls() {
        var base=engine.evaluate(bars(false,false),List.of(),account(0,0,null,null,false),Rules.defaults());
        var future=new Roll(LocalDate.of(2099,1,1),100,9999);
        assertEquals(base,engine.evaluate(bars(false,false),List.of(future),account(0,0,null,null,false),Rules.defaults()));
        var rolled=bars(false,true);
        assertEquals("WARMUP",engine.evaluate(rolled,List.of(),account(0,0,null,null,false),Rules.defaults()).state());
        var known=new Roll(LocalDate.ofInstant(rolled.get(115).timestamp(),ZoneOffset.UTC),110,150);
        var p=engine.evaluate(rolled,List.of(known),account(0,0,null,null,false),Rules.defaults());
        assertEquals("ENTER",p.action());assertEquals(base.entryPrice()+40,p.entryPrice(),.11);
    }
    @Test void rejectsUnsafeParametersAndReturnsZeroLotsRatherThanRoundingUp() {
        assertThrows(IllegalArgumentException.class,()->new Rules(Double.NaN,20,1.5,2,3).validate());
        assertThrows(IllegalArgumentException.class,()->new Rules(10,100,1,2,0).validate());
        var small=new Account(10000,10000,0,0,0,.1,10000,100000,100,.15,.0001,1,null,null,null,0,false);
        var p=engine.evaluate(bars(false,false),List.of(),small,Rules.defaults());
        assertEquals("NO_SIZE",p.state());assertEquals(0,p.maxLots());
    }
}
