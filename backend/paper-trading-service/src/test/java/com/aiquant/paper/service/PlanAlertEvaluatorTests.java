package com.aiquant.paper.service;
import com.aiquant.paper.client.SimulationDataClient.*;
import com.aiquant.paper.service.DecisionJournalService.Fields;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class PlanAlertEvaluatorTests {
 final Instant now=Instant.parse("2026-11-09T02:00:00Z");
 Fields fields(String side){return new Fields(side,new BigDecimal("100"),new BigDecimal(side.equals("LONG")?"98":"102"),new BigDecimal(side.equals("LONG")?"105":"95"),1,new BigDecimal("100000"),new BigDecimal("1000"),"fixture","fixture",now.plusSeconds(3600));}
 LiveContext live(String price,Instant at,String state){return new LiveContext("RB2701","RB2701",state,now,"fixture",new QuoteSnapshot("RB2701","fixture",new BigDecimal(price),"fixture","FRESH",at),new ContractSpec("RB2701",10,BigDecimal.ONE,BigDecimal.TEN,BigDecimal.ONE),List.of(),List.of());}
 Map<String,Object> before(String p){return Map.of("price",new BigDecimal(p),"at",now.minusSeconds(60).toString());}
 @Test void first_observation_and_equal_baseline_do_not_invent_an_entry(){assertTrue(PlanAlertEvaluator.evaluate("RB2701",fields("LONG"),"BREAKOUT",Map.of(),live("101",now,"LIVE"),now).kinds().isEmpty());assertTrue(PlanAlertEvaluator.evaluate("RB2701",fields("LONG"),"BREAKOUT",before("100"),live("101",now,"LIVE"),now).kinds().isEmpty());}
 @Test void long_and_short_breakouts_and_pullbacks_are_distinct(){assertEquals(List.of("ENTRY"),PlanAlertEvaluator.evaluate("RB2701",fields("LONG"),"BREAKOUT",before("99"),live("100",now,"LIVE"),now).kinds());assertEquals(List.of("ENTRY"),PlanAlertEvaluator.evaluate("RB2701",fields("LONG"),"PULLBACK",before("101"),live("100",now,"LIVE"),now).kinds());assertEquals(List.of("ENTRY"),PlanAlertEvaluator.evaluate("RB2701",fields("SHORT"),"BREAKOUT",before("101"),live("100",now,"LIVE"),now).kinds());assertEquals(List.of("ENTRY"),PlanAlertEvaluator.evaluate("RB2701",fields("SHORT"),"PULLBACK",before("99"),live("100",now,"LIVE"),now).kinds());}
 @Test void stop_and_target_are_price_observations_without_entry_or_position_assumptions(){assertEquals(List.of("STOP"),PlanAlertEvaluator.evaluate("RB2701",fields("LONG"),"BREAKOUT",before("99"),live("97",now,"LIVE"),now).kinds());assertEquals(List.of("ENTRY","TARGET"),PlanAlertEvaluator.evaluate("RB2701",fields("LONG"),"BREAKOUT",before("99"),live("106",now,"LIVE"),now).kinds());assertEquals(List.of("STOP"),PlanAlertEvaluator.evaluate("RB2701",fields("SHORT"),"BREAKOUT",before("101"),live("103",now,"LIVE"),now).kinds());}
 @Test void stale_closed_future_or_wrong_contract_quotes_clear_the_baseline(){for(var q:List.of(live("101",now.minusSeconds(31),"LIVE"),live("101",now,"CLOSED"),live("101",now.plusSeconds(3),"LIVE"))){var r=PlanAlertEvaluator.evaluate("RB2701",fields("LONG"),"BREAKOUT",before("99"),q,now);assertEquals("STALE",r.status());assertTrue(r.state().isEmpty());assertTrue(r.kinds().isEmpty());}assertEquals("STALE",PlanAlertEvaluator.evaluate("RB2705",fields("LONG"),"BREAKOUT",before("99"),live("101",now,"LIVE"),now).status());}
 @Test void gaps_and_out_of_order_quotes_never_reconstruct_a_missing_path(){assertTrue(PlanAlertEvaluator.evaluate("RB2701",fields("LONG"),"BREAKOUT",Map.of("price",99,"at",now.minusSeconds(91).toString()),live("101",now,"LIVE"),now).kinds().isEmpty());var previous=Map.<String,Object>of("price",99,"at",now.toString());var r=PlanAlertEvaluator.evaluate("RB2701",fields("LONG"),"BREAKOUT",previous,live("101",now,"LIVE"),now);assertEquals(previous,r.state());assertTrue(r.kinds().isEmpty());}
}
