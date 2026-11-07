package com.aiquant.paper.service;

import com.aiquant.paper.client.SimulationDataClient.LiveContext;
import com.aiquant.paper.service.DecisionJournalService.Fields;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;

/** Minute observations, not continuous tick coverage or a fill/position model. */
public final class PlanAlertEvaluator {
 private PlanAlertEvaluator(){}
 public record Result(String status,String message,Map<String,Object> state,List<String> kinds){}
 public static Result evaluate(String symbol,Fields fields,String mode,Map<String,Object> previous,LiveContext live,Instant now){
  var q=live==null?null:live.quote();
  if(live==null||q==null||!symbol.equals(live.contract())||!symbol.equals(q.symbol())||live.spec()==null||!symbol.equals(live.spec().contract()))return empty("STALE","实际合约不可核对，等待新基线。");
  if(!"LIVE".equals(live.marketState())||!"FRESH".equals(q.dataStatus())||!fresh(q.dataTimestamp(),now)||!fresh(live.checkedAt(),now)||q.price()==null||q.price().signum()<=0)return empty("STALE","非交易时段或报价过时，等待新基线。");
  Instant at=q.dataTimestamp();Map<String,Object> state=Map.of("price",q.price(),"at",at.toString());
  if(!previous.containsKey("price")||!previous.containsKey("at"))return new Result("READY","已建立近时行情基线，未补发旧触发。",state,List.of());
  Instant beforeAt=Instant.parse(previous.get("at").toString());
  if(!at.isAfter(beforeAt))return new Result("READY","行情时点未前进，等待新观测。",previous,List.of());
  if(at.isAfter(beforeAt.plusSeconds(90)))return new Result("READY","采样间隔超过90秒，重建基线，不推断中间路径。",state,List.of());
  BigDecimal before=new BigDecimal(previous.get("price").toString()),price=q.price();boolean buy="LONG".equals(fields.side());
  var kinds=new ArrayList<String>();
  if(cross(before,price,fields.entry(),"BREAKOUT".equals(mode)?buy:!buy))kinds.add("ENTRY");
  if(cross(before,price,fields.stop(),!buy))kinds.add("STOP");
  if(cross(before,price,fields.target(),buy))kinds.add("TARGET");
  return new Result("READY","分钟采样价位观察；不代表连续触达、收盘确认或成交。",state,kinds);
 }
 private static boolean fresh(Instant t,Instant now){return t!=null&&!t.isBefore(now.minusSeconds(30))&&!t.isAfter(now.plusSeconds(2));}
 private static boolean cross(BigDecimal before,BigDecimal now,BigDecimal level,boolean up){return up?before.compareTo(level)<0&&now.compareTo(level)>=0:before.compareTo(level)>0&&now.compareTo(level)<=0;}
 public static Result empty(String status,String message){return new Result(status,message,Map.of(),List.of());}
}
