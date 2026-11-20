package com.aiquant.paper.service;

import com.fasterxml.jackson.databind.JsonNode;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;

/** Read-only live observations, independent of the last ledger valuation clock. */
final class PaperLiveChart {
    private static final ZoneId SH=ZoneId.of("Asia/Shanghai");
    static Map<String,Object> snapshot(JsonNode raw,String contract,int seconds,int limit,Instant now){
        if(raw==null||!contract.equals(raw.path("symbol").asText())||raw.path("seconds").asInt()!=seconds)
            throw new IllegalStateException("实时图表的合约或周期不一致，已停止展示");
        List<Map<String,Object>> bars=new ArrayList<>();
        boolean provisional=false;
        for(var point:raw.path("points")){
            Instant stamp=Instant.parse(point.path("timestamp").asText());
            if(seconds!=86400&&stamp.isAfter(now))continue;
            for(String key:List.of("open","high","low","price"))if(!point.path(key).isNumber()||point.path(key).decimalValue().signum()<=0)
                throw new IllegalStateException("实时图表价格无效，已停止展示");
            BigDecimal open=point.path("open").decimalValue(),high=point.path("high").decimalValue(),low=point.path("low").decimalValue(),close=point.path("price").decimalValue();
            if(high.compareTo(open.max(close))<0||low.compareTo(open.min(close))>0)throw new IllegalStateException("实时图表OHLC无效");
            var bar=new LinkedHashMap<String,Object>();bar.put("timestamp",stamp);bar.put("contract",contract);
            bar.put("open",open);bar.put("high",high);bar.put("low",low);bar.put("close",close);
            bar.put("volume",point.path("volume").asLong());bar.put("openInterest",point.path("openInterest").asLong());
            bar.put("tradingDate",point.path("tradingDate").asText(stamp.atZone(SH).toLocalDate().toString()));
            if(seconds!=86400){bar.put("startTime",stamp);bar.put("endTime",stamp.plusSeconds(seconds));}
            boolean forming=seconds==86400?point==raw.path("points").get(raw.path("points").size()-1)&&raw.path("lastBarProvisional").asBoolean()&&"OPEN".equals(raw.path("marketPhase").asText())
                :stamp.plusSeconds(seconds).isAfter(now)&&raw.path("lastBarProvisional").asBoolean();
            bar.put("provisional",forming);provisional=forming;bars.add(bar);
        }
        bars.sort(Comparator.comparing(b->(Instant)b.get("timestamp")));
        bars=new ArrayList<>(bars.subList(Math.max(0,bars.size()-limit),bars.size()));
        provisional=!bars.isEmpty()&&Boolean.TRUE.equals(bars.get(bars.size()-1).get("provisional"));
        String stamp=raw.path("dataTimestamp").asText(null),state=raw.path("marketState").asText("UNKNOWN");
        boolean fresh=false;
        if(stamp!=null){long age=Duration.between(Instant.parse(stamp),now).getSeconds();fresh=age>=-10&&age<=60&&raw.path("connected").asBoolean()&&"FRESH".equals(raw.path("dataStatus").asText())&&"LIVE".equals(state);}
        var result=new LinkedHashMap<String,Object>();
        result.put("snapshotKind","LIVE");result.put("asOf",now);result.put("barSeconds",seconds);result.put("bars",bars);
        result.put("source",raw.path("source").asText("天勤 TqSdk 实时K线"));result.put("contextStatus",bars.isEmpty()?"UNAVAILABLE":"READY");
        result.put("dataTimestamp",stamp);result.put("receivedAt",raw.path("receivedAt").asText(null));result.put("retrievedAt",now);
        result.put("dataStatus",fresh?"FRESH":"CACHED");result.put("marketState",state);result.put("connected",raw.path("connected").asBoolean());
        result.put("lastBarProvisional",provisional);result.put("tradingSessions",raw.path("tradingSessions"));
        result.put("expectedTradingDate",raw.path("expectedTradingDate").asText(null));
        result.put("displayTradingDate","CLOSED_CACHE".equals(state)&&!bars.isEmpty()?bars.get(bars.size()-1).get("tradingDate"):raw.path("expectedTradingDate").asText(null));
        result.put("lastPrice",raw.path("lastPrice").isNumber()?raw.path("lastPrice").decimalValue():bars.isEmpty()?null:bars.get(bars.size()-1).get("close"));
        result.put("message",fresh?"当前实际合约实时行情；末根K线随行情更新。": "CLOSED_CACHE".equals(state)?"当前休市，显示最近收到的真实行情及原始时间。":"实时行情尚未就绪或已过期，请核对行情时间；不以历史日线代替实时行情。");
        return result;
    }
}
