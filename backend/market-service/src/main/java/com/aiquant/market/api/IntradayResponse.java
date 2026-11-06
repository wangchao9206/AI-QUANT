package com.aiquant.market.api;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;

public record IntradayResponse(String symbol, int seconds, String period, String source, DataStatus dataStatus,
    Instant dataTimestamp, Instant receivedAt, Instant retrievedAt, boolean connected,
    String message, boolean lastBarProvisional, List<Bar> points, Map<String,Object> geometry) {
    public IntradayResponse {
        geometry=geometry==null?Map.of():geometry;
    }
    public IntradayResponse(String symbol,int seconds,String period,String source,DataStatus dataStatus,
        Instant dataTimestamp,Instant receivedAt,Instant retrievedAt,boolean connected,
        String message,boolean lastBarProvisional,List<Bar> points) {
        this(symbol,seconds,period,source,dataStatus,dataTimestamp,receivedAt,retrievedAt,connected,
            message,lastBarProvisional,points,Map.of());
    }
    public record Bar(Instant timestamp, BigDecimal open, BigDecimal high, BigDecimal low,
        BigDecimal price, Long volume, Long openInterest, BigDecimal changePct, boolean changePctKnown) {}
}
