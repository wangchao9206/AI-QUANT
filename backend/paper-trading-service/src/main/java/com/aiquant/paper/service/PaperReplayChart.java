package com.aiquant.paper.service;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.*;
import java.util.*;

/** Re-bucket only frozen observations already completed at the account clock. */
final class PaperReplayChart {
    static final List<Integer> PERIODS=List.of(60,180,300,900,1800,3600,86400);
    private static final ZoneId SH=ZoneId.of("Asia/Shanghai");
    static List<Map<String,Object>> bars(JsonNode archive,Instant cutoff,int seconds,int limit){
        if(!PERIODS.contains(seconds)||limit<1||limit>1000)throw new IllegalArgumentException("不支持的图表周期或数量");
        Set<String> complete=new HashSet<>();archive.path("completeTradingDates").forEach(d->complete.add(d.asText()));
        Map<String,List<JsonNode>> days=new TreeMap<>();
        for(var bar:archive.path("minuteBars")){
            if(!complete.contains(bar.path("tradingDate").asText()))continue;
            if(Instant.parse(bar.path("timestamp").asText()).plusSeconds(60).isAfter(cutoff))continue;
            days.computeIfAbsent(bar.path("tradingDate").asText(),k->new ArrayList<>()).add(bar);
        }
        List<Map<String,Object>> result=new ArrayList<>();
        for(var entry:days.entrySet()){
            var rows=entry.getValue();
            rows.sort(Comparator.comparing(b->Instant.parse(b.path("timestamp").asText())));
            boolean closed=Instant.parse(rows.get(rows.size()-1).path("timestamp").asText()).plusSeconds(60)
                .atZone(SH).toLocalTime().equals(LocalTime.of(15,0));
            int size=seconds==86400?rows.size():seconds/60;
            if(seconds==86400&&!closed)continue;
            for(int start=0;start<rows.size();start+=size){
                int end=Math.min(rows.size(),start+size);
                if(end-start<size&&!closed)break;
                var chunk=rows.subList(start,end);var first=chunk.get(0);var last=chunk.get(chunk.size()-1);
                var high=first.path("high").decimalValue();var low=first.path("low").decimalValue();long volume=0;
                for(var b:chunk){high=high.max(b.path("high").decimalValue());low=low.min(b.path("low").decimalValue());volume+=b.path("volume").asLong();}
                Map<String,Object> bar=new LinkedHashMap<>();
                bar.put("timestamp",seconds==86400?LocalDate.parse(entry.getKey()).atStartOfDay(SH).toInstant():Instant.parse(first.path("timestamp").asText()));
                bar.put("startTime",Instant.parse(first.path("timestamp").asText()));
                bar.put("endTime",Instant.parse(last.path("timestamp").asText()).plusSeconds(60));
                bar.put("tradingDate",entry.getKey());bar.put("contract",first.path("contract").asText());
                bar.put("open",first.path("open").decimalValue());bar.put("close",last.path("close").decimalValue());
                bar.put("high",high);bar.put("low",low);bar.put("volume",volume);bar.put("openInterest",last.path("openInterest").asLong());
                result.add(bar);
            }
        }
        return result.subList(Math.max(0,result.size()-limit),result.size());
    }
}
