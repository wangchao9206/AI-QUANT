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
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.util.UriComponentsBuilder;

@Component
public class SimulationDataClient {
    private final RestClient algorithmClient;
    private final RestClient marketClient;
    private final RestClient liveChartClient;

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
        var liveFactory=new SimpleClientHttpRequestFactory();liveFactory.setConnectTimeout(connectTimeout);
        liveFactory.setReadTimeout(readTimeout.compareTo(Duration.ofSeconds(8))>0?Duration.ofSeconds(8):readTimeout);
        this.liveChartClient=RestClient.builder().baseUrl(algorithmBaseUrl).requestFactory(liveFactory).build();
    }

    public SimulationDataset history(String symbol, LocalDate startDate, LocalDate endDate) {
        return history(symbol,startDate,endDate,86400);
    }

    public JsonNode intradayCatalog() {
        return algorithmClient.get().uri("/internal/v1/simulation/intraday/catalog").retrieve().body(JsonNode.class);
    }

    public SimulationDataset history(String symbol, LocalDate startDate, LocalDate endDate,int barSeconds) {
        UriComponentsBuilder builder = UriComponentsBuilder
            .fromPath("/internal/v1/simulation/history/{symbol}");
        if (startDate != null) builder.queryParam("start_date", startDate);
        if (endDate != null) builder.queryParam("end_date", endDate);
        if (barSeconds != 86400) builder.queryParam("bar_seconds",barSeconds);
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
    public JsonNode liveChart(String contract,int seconds,int limit){
        if(!contract.matches("[A-Z]{1,4}[0-9]{3,4}"))throw new IllegalArgumentException("实时图表必须使用当前实际合约");
        if(!List.of(60,180,300,900,1800,3600,86400).contains(seconds))throw new IllegalArgumentException("不支持的实时周期");
        var uri=UriComponentsBuilder.fromPath("/api/v1/market/{symbol}/intraday").queryParam("limit",Math.min(600,limit));
        if(seconds==86400)uri.queryParam("period","DAY");else uri.queryParam("seconds",seconds);
        return liveChartClient.get().uri(uri.buildAndExpand(contract).encode().toUriString()).retrieve().body(JsonNode.class);
    }
    public JsonNode chanProfile(){return algorithmClient.get().uri("/internal/v1/workflows/chan-profile").retrieve().body(JsonNode.class);}
    public JsonNode refreshAutomationData(String contract,String requestKey) {
        JsonNode result=liveChartClient.post().uri("/internal/v1/simulation/automation/{contract}/refresh",contract)
            .body(Map.of("requestKey",requestKey)).retrieve().body(JsonNode.class);
        if(result==null || !contract.equals(result.path("contract").asText()) || !requestKey.equals(result.path("requestKey").asText())
            || !List.of("PENDING","FAILED","READY").contains(result.path("state").asText()))
            throw new IllegalStateException("数据刷新回执无效，未使用旧缓存放行");
        if("READY".equals(result.path("state").asText()) && (!"TQSDK_FRESH_DOWNLOAD".equals(result.path("source").asText())
            || result.path("dailyCount").asInt()<=0 || result.path("minuteCount").asInt()<=0
            || !result.hasNonNull("completedAt") || !result.hasNonNull("latestDailyTime") || !result.hasNonNull("latestMinuteTime")
            || !result.hasNonNull("sourceStartupId")))throw new IllegalStateException("未取得实际合约的完整最新数据");
        return result;
    }
    public JsonNode validateWorkflow(JsonNode definition){return algorithmClient.post().uri("/internal/v1/workflows/validate").body(Map.of("definition",definition)).retrieve().body(JsonNode.class);}
    public JsonNode debugWorkflow(JsonNode definition,String symbol,Instant asOf,int direction){return algorithmClient.post().uri("/internal/v1/workflows/debug").body(Map.of("definition",definition,"symbol",symbol,"asOf",asOf,"direction",direction)).retrieve().body(JsonNode.class);}
    public JsonNode backtestWorkflow(JsonNode request){return algorithmClient.post().uri("/api/v1/backtest/run").body(request).retrieve().body(JsonNode.class);}
    public JsonNode replayMaTrendWorkflow(Map<String, Object> request) {
        return algorithmClient.post().uri("/internal/v1/workflows/ma-trend-replay")
            .body(request).retrieve().body(JsonNode.class);
    }

    public LiveContext live(String symbol) {
        LiveContext result = algorithmClient.get().uri("/internal/v1/simulation/live/{symbol}", symbol)
            .retrieve().body(LiveContext.class);
        validateLive(result);
        return result;
    }
    public LiveContext liveFast(String contract) {
        LiveContext result=liveChartClient.get().uri("/internal/v1/simulation/live/{symbol}",contract).retrieve().body(LiveContext.class);
        validateLive(result);
        if(!contract.equals(result.contract()))throw new IllegalStateException("实际合约已变更");
        return result;
    }

    private static void validateLive(LiveContext result) {
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
    }

    public record PortfolioQuotes(Map<String,LiveContext> quotes,Map<String,String> errors) {}
    public PortfolioQuotes portfolioQuotes(List<String> contracts) {
        if(contracts.isEmpty() || contracts.size()>100 || contracts.stream().anyMatch(c->!c.matches("[A-Z]{1,4}[0-9]{3,4}")))
            throw new IllegalArgumentException("批量行情必须使用实际合约（最多100个）");
        PortfolioQuotes result=liveChartClient.post().uri("/internal/v1/simulation/portfolio/quotes")
            .body(Map.of("contracts",contracts)).retrieve().body(PortfolioQuotes.class);
        if(result==null || result.quotes()==null)throw new IllegalStateException("批量行情暂不可用");
        result.quotes().forEach((contract,context)->{
            validateLive(context);
            if(!contracts.contains(contract) || !contract.equals(context.contract()))throw new IllegalStateException("批量行情合约不匹配");
        });
        return result;
    }

    public StrategyDecision evaluate(StrategyInput request) {
        StrategyDecision result = algorithmClient.post().uri("/internal/v1/simulation/strategy/evaluate")
            .body(request).retrieve().body(StrategyDecision.class);
        return checkedDecision(request,result);
    }
    public StrategyDecision evaluateFast(StrategyInput request) {
        return checkedDecision(request,liveChartClient.post().uri("/internal/v1/simulation/strategy/evaluate").body(request).retrieve().body(StrategyDecision.class));
    }
    public TrinityFeed trinityFeed(String contract) {
        TrinityFeed feed;
        try {
            feed=liveChartClient.get().uri("/internal/v1/simulation/automation/{contract}/trinity-feed",contract)
                .retrieve().body(TrinityFeed.class);
        } catch (RestClientResponseException error) {
            if (error.getStatusCode().value()!=503) throw error;
            var body=error.getResponseBodyAs(JsonNode.class);
            String detail=body==null ? "" : body.path("detail").asText();
            throw new IllegalStateException(detail.isBlank() ? "等待三位一体的实际合约行情" : detail.substring(0,Math.min(180,detail.length())));
        }
        if (feed==null || !contract.equals(feed.contract()) || feed.asOf()==null || feed.tradingDate()==null
            || feed.dailyBars()==null || feed.minuteBars()==null || feed.minuteTradingDates()==null
            || feed.minuteBars().size()!=feed.minuteTradingDates().size() || feed.tradingSessions()==null
            || !List.of(1,5,15).contains(feed.minuteCadence())) {
            throw new IllegalStateException("三位一体的实际合约行情暂未就绪");
        }
        return feed;
    }
    public StrategyDecision evaluateTrinity(TrinityInput request) {
        var result=liveChartClient.post().uri("/internal/v1/simulation/strategy/evaluate")
            .body(request).retrieve().body(StrategyDecision.class);
        if (result==null || !"PERSONAL_TRINITY".equals(result.strategy())
            || !"paper-personal-trinity-v1".equals(result.modelVersion())
            || !List.of("BUY","SELL","FLATTEN","ADD_LONG","HOLD","WARMING").contains(result.signal())
            || result.signalTime()!=null && result.signalTime().isAfter(request.asOf())
            || List.of("BUY","SELL","FLATTEN","ADD_LONG").contains(result.signal()) && result.signalTime()==null) {
            throw new IllegalStateException("三位一体信号无效，未提交模拟委托");
        }
        return result;
    }
    public record TrinityFeed(String contract, Instant asOf, List<HistoricalBar> dailyBars,
        List<HistoricalBar> minuteBars, List<LocalDate> minuteTradingDates, int minuteCadence,
        JsonNode tradingSessions, LocalDate tradingDate, String minuteStatus) {}

    public record TrinityInput(String strategy, String symbol, Instant asOf, List<HistoricalBar> bars,
        List<HistoricalBar> executionBars, List<HistoricalBar> minuteBars, List<LocalDate> minuteTradingDates,
        int minuteCadence, JsonNode tradingSessions, LocalDate tradingDate, BigDecimal priceTick,
        JsonNode trinity, int direction, int positionLots, Instant startedAt, Instant positionOpenedAt,
        Instant lastSignalTime, Instant lastEntrySignalTime) {}

    private StrategyDecision checkedDecision(StrategyInput request,StrategyDecision result) {
        if (result == null || !request.strategy().equals(result.strategy())
            || "WORKFLOW".equals(request.strategy()) && !com.aiquant.paper.service.StrategyWorkflowStore.engine(request.workflow()).equals(result.modelVersion())
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
        List<HistoricalBar> executionBars, int direction, boolean firstEntry,JsonNode workflow,
        List<HistoricalBar> minuteBars,BigDecimal priceTick) {
        public StrategyInput(String strategy,String symbol,Instant asOf,List<HistoricalBar> bars,List<HistoricalBar> executionBars,int direction,boolean firstEntry,JsonNode workflow){this(strategy,symbol,asOf,bars,executionBars,direction,firstEntry,workflow,List.of(),BigDecimal.ONE);}
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
        List<HistoricalBar> contextBars,
        JsonNode replayContext
    ) {
        public SimulationDataset(String symbol,String providerSymbol,String source,Instant generatedAt,
            List<HistoricalBar> bars,List<RollEvent> rollEvents,Map<String,ContractSpec> contractSpecs,
            List<HistoricalBar> signalBars,List<HistoricalBar> contextBars) {
            this(symbol,providerSymbol,source,generatedAt,bars,rollEvents,contractSpecs,signalBars,contextBars,null);
        }
        public SimulationDataset(String symbol, String providerSymbol, String source, Instant generatedAt,
            List<HistoricalBar> bars, List<RollEvent> rollEvents, Map<String, ContractSpec> contractSpecs) {
            this(symbol, providerSymbol, source, generatedAt, bars, rollEvents, contractSpecs, bars, bars,null);
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
