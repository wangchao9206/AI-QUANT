package com.aiquant.paper.client;
import com.fasterxml.jackson.databind.JsonNode;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.UriComponentsBuilder;

@Component
public class SimulationDataClient {
    private final RestClient algorithmClient;
    private final RestClient marketClient;

    public SimulationDataClient(
        @Value("${aiquant.algorithm-base-url}") String algorithmBaseUrl,
        @Value("${aiquant.market-base-url}") String marketBaseUrl,
        @Value("${aiquant.client.connect-timeout:2s}") Duration connectTimeout,
        @Value("${aiquant.client.read-timeout:180s}") Duration readTimeout
    ) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(connectTimeout);
        factory.setReadTimeout(readTimeout);
        this.algorithmClient = RestClient.builder().baseUrl(algorithmBaseUrl).requestFactory(factory).build();
        this.marketClient = RestClient.builder().baseUrl(marketBaseUrl).requestFactory(factory).build();
    }

    public SimulationDataset history(String symbol, LocalDate startDate, LocalDate endDate) {
        UriComponentsBuilder builder = UriComponentsBuilder
            .fromPath("/internal/v1/simulation/history/{symbol}");
        if (startDate != null) builder.queryParam("start_date", startDate);
        if (endDate != null) builder.queryParam("end_date", endDate);
        String uri = builder.buildAndExpand(symbol).encode().toUriString();
        SimulationDataset result = algorithmClient.get().uri(uri).retrieve().body(SimulationDataset.class);
        if (result == null || result.bars() == null || result.bars().size() < 2) {
            throw new IllegalStateException("真实历史数据不足，无法创建模拟会话");
        }
        return result;
    }

    public ChartContext chart(String symbol, Instant asOf, int limit) {
        String uri = UriComponentsBuilder.fromPath("/internal/v1/simulation/chart/{symbol}")
            .queryParam("as_of", asOf).queryParam("limit", limit)
            .buildAndExpand(symbol).encode().toUriString();
        return algorithmClient.get().uri(uri).retrieve().body(ChartContext.class);
    }

    public record ChartContext(String source, Instant asOf, List<HistoricalBar> bars) {}
    public JsonNode validateWorkflow(JsonNode definition){return algorithmClient.post().uri("/internal/v1/workflows/validate").body(Map.of("definition",definition)).retrieve().body(JsonNode.class);}
    public JsonNode debugWorkflow(JsonNode definition,String symbol,Instant asOf,int direction){return algorithmClient.post().uri("/internal/v1/workflows/debug").body(Map.of("definition",definition,"symbol",symbol,"asOf",asOf,"direction",direction)).retrieve().body(JsonNode.class);}
    public JsonNode backtestWorkflow(JsonNode request){return algorithmClient.post().uri("/api/v1/backtest/run").body(request).retrieve().body(JsonNode.class);}

    public LiveContext live(String symbol) {
        LiveContext result = algorithmClient.get().uri("/internal/v1/simulation/live/{symbol}", symbol)
            .retrieve().body(LiveContext.class);
        if (result == null || result.contract() == null || result.quote() == null || result.spec() == null
            || !result.contract().equals(result.quote().symbol()) || !result.contract().equals(result.spec().contract())
            || result.quote().dataTimestamp()==null || result.checkedAt()==null
            || result.quote().price() == null || result.quote().price().signum() <= 0
            || result.spec().volumeMultiple() <= 0 || result.spec().priceTick() == null
            || result.spec().priceTick().signum() <= 0 || result.spec().marginPerLot() == null
            || result.spec().marginPerLot().signum() <= 0 || result.spec().commissionPerLot() == null
            || result.spec().commissionPerLot().signum() < 0) {
            throw new IllegalStateException("真实交割合约行情或规格尚未就绪，请稍后刷新");
        }
        return result;
    }

    public StrategyDecision evaluate(StrategyInput request) {
        StrategyDecision result = algorithmClient.post().uri("/internal/v1/simulation/strategy/evaluate")
            .body(request).retrieve().body(StrategyDecision.class);
        if (result == null || !request.strategy().equals(result.strategy())
            || "WORKFLOW".equals(request.strategy()) && !"workflow-daily-v1".equals(result.modelVersion())
            || !List.of("BUY","SELL","FLATTEN","HOLD","WARMING").contains(result.signal())
            || result.signalTime() != null && result.signalTime().isAfter(request.asOf())) {
            throw new IllegalStateException("策略响应无效，未提交模拟委托");
        }
        return result;
    }

    public record LiveContext(String symbol, String contract, String marketState, Instant checkedAt,
        String source, QuoteSnapshot quote, ContractSpec spec,
        List<HistoricalBar> signalBars, List<HistoricalBar> executionBars) {}
    public record StrategyInput(String strategy, String symbol, Instant asOf, List<HistoricalBar> bars,
        List<HistoricalBar> executionBars, int direction, boolean firstEntry,JsonNode workflow) {
        public StrategyInput(String strategy,String symbol,Instant asOf,List<HistoricalBar> bars,List<HistoricalBar> executionBars,int direction,boolean firstEntry){this(strategy,symbol,asOf,bars,executionBars,direction,firstEntry,null);}
    }
    public record StrategyDecision(String strategy, String strategyName, String modelVersion, String signal,
        String reason, Instant signalTime, int historyCount, int requiredBars, BigDecimal atr,List<Map<String,Object>> nodeTrace) {
        public StrategyDecision(String strategy,String strategyName,String modelVersion,String signal,String reason,Instant signalTime,int historyCount,int requiredBars,BigDecimal atr){this(strategy,strategyName,modelVersion,signal,reason,signalTime,historyCount,requiredBars,atr,List.of());}
    }

    public QuoteSnapshot quote(String symbol) {
        QuoteSnapshot result = marketClient.get()
            .uri("/api/v1/market/{symbol}/quote", symbol)
            .retrieve()
            .body(QuoteSnapshot.class);
        if (result == null || result.price() == null || result.price().signum() <= 0) {
            throw new IllegalStateException("真实行情不可用，模拟委托未执行");
        }
        Instant now = Instant.now();
        if (!"FRESH".equals(result.dataStatus()) || result.dataTimestamp() == null
            || result.dataTimestamp().isBefore(now.minusSeconds(60))
            || result.dataTimestamp().isAfter(now.plusSeconds(10))) {
            throw new IllegalStateException("实时行情未就绪或已过期，不能使用缓存价格进行实时仿真；可切换历史时点回放使用已保存的真实数据");
        }
        return result;
    }

    public QuoteSnapshot latestQuoteOrNull(String symbol) {
        try {
            QuoteSnapshot result = marketClient.get()
                .uri("/api/v1/market/{symbol}/quote", symbol)
                .retrieve()
                .body(QuoteSnapshot.class);
            if (result != null && result.price() != null && result.price().signum() > 0) {
                return result;
            }
        } catch (RuntimeException ignored) {
        }
        return null;
    }

    public record SimulationDataset(
        String symbol,
        String providerSymbol,
        String source,
        Instant generatedAt,
        List<HistoricalBar> bars,
        List<RollEvent> rollEvents,
        Map<String, ContractSpec> contractSpecs,
        List<HistoricalBar> signalBars,
        List<HistoricalBar> contextBars
    ) {
        public SimulationDataset(String symbol, String providerSymbol, String source, Instant generatedAt,
            List<HistoricalBar> bars, List<RollEvent> rollEvents, Map<String, ContractSpec> contractSpecs) {
            this(symbol, providerSymbol, source, generatedAt, bars, rollEvents, contractSpecs, bars, bars);
        }
    }

    public record HistoricalBar(
        Instant timestamp,
        String contract,
        BigDecimal open,
        BigDecimal high,
        BigDecimal low,
        BigDecimal close,
        long volume,
        long openInterest
    ) {}

    public record RollEvent(
        LocalDate executionDate,
        String fromContract,
        String toContract,
        BigDecimal oldOpen,
        BigDecimal newOpen
    ) {}

    public record ContractSpec(
        String contract,
        int volumeMultiple,
        BigDecimal priceTick,
        BigDecimal marginPerLot,
        BigDecimal commissionPerLot
    ) {}

    public record QuoteSnapshot(
        String symbol,
        String displayName,
        BigDecimal price,
        String source,
        String dataStatus,
        Instant dataTimestamp
    ) {}
}
