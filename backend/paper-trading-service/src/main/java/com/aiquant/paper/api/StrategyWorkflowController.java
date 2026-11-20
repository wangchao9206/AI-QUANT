package com.aiquant.paper.api;

import com.aiquant.paper.service.StrategyWorkflowService;
import com.aiquant.paper.service.StrategyWorkflowStore.Version;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/paper/workflows")
public class StrategyWorkflowController {
    private final StrategyWorkflowService service;
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private final String secret;
    public StrategyWorkflowController(StrategyWorkflowService service,JdbcTemplate jdbc,ObjectMapper mapper,
        @Value("${IDENTITY_INTERNAL_SECRET:}") String secret){
        this.service=service;
        this.jdbc=jdbc;
        this.mapper=mapper;
        this.secret=secret;
    }
    public record CreateRequest(@NotBlank @Pattern(regexp="[A-Za-z0-9-]{8,128}") String clientRequestId,
        @NotBlank @Size(max=120) String name,@Size(max=1000) String description,@NotNull JsonNode definition) {}
    public record SaveRequest(@Min(1) int expectedRevision,@NotBlank @Size(max=120) String name,
        @Size(max=1000) String description,@NotNull JsonNode definition) {}
    public record PublishRequest(@Min(1) int expectedRevision,@NotBlank @Pattern(regexp="[A-Za-z0-9-]{8,128}") String clientRequestId) {}
    public record MaTrendReplayRequest(
        @NotBlank @Pattern(regexp="FG701|SA701|AP701|CJ701") String symbol,
        @NotNull @DecimalMin("1000") @DecimalMax("100000000") @Digits(integer=9, fraction=2) BigDecimal initialCash,
        @Min(1) @Max(2) Integer costMultiplier,
        boolean includeTimeline
    ) {
        public MaTrendReplayRequest(String symbol, BigDecimal initialCash, Integer costMultiplier) {
            this(symbol,initialCash,costMultiplier,false);
        }
    }
    public record DebugRequest(@NotNull JsonNode definition,@NotBlank @Pattern(regexp="[A-Za-z]{1,4}(?:0|M)") String symbol,
        @NotNull Instant asOf,@Min(-1) @Max(1) int direction) {}
    public record ShadowRequest(@NotNull UUID clientRequestId,@NotBlank @Pattern(regexp="[A-Za-z]{1,4}(?:0|M)") String symbol,@NotNull Instant asOf,@Min(-1) @Max(1) int direction) {}
    @GetMapping("/chan-profile") public Object chanProfile(){return service.chanProfile();}
    @GetMapping public Object list(){return service.list();}
    @GetMapping("/versions") public Object published(){return service.published();}
    @GetMapping("/versions/ma-trend") public List<Version> publishedMaTrends(HttpServletResponse response) {
        response.setHeader("Cache-Control", "no-store");
        return service.publishedMaTrends();
    }
    @GetMapping("/versions/{id}") public Object version(@PathVariable UUID id){return service.version(id);}
    @PostMapping("/versions/{id}/backtest") public Object backtest(@PathVariable UUID id,@RequestBody JsonNode body){return service.backtest(id,body);}
    @PostMapping("/versions/{id}/ma-trend-replay")
    public Object maTrendReplay(@PathVariable UUID id, @Valid @RequestBody MaTrendReplayRequest request,
        HttpServletRequest httpRequest, HttpServletResponse response) {
        if (!request.includeTimeline()) return service.maTrendReplay(id, request);
        response.setHeader("Cache-Control","no-store");
        var owner = DecisionAccess.workflowActor(httpRequest,jdbc,mapper,secret);
        return service.maTrendReplay(id,request,owner);
    }
    @PostMapping public Object create(@Valid @RequestBody CreateRequest request){return service.create(request);}
    @GetMapping("/{id}") public Object detail(@PathVariable UUID id){return service.detail(id);}
    @PutMapping("/{id}") public Object save(@PathVariable UUID id,@Valid @RequestBody SaveRequest request){return service.save(id,request);}
    @PostMapping("/{id}/publish") public Object publish(@PathVariable UUID id,@Valid @RequestBody PublishRequest request){return service.publish(id,request);}
    @PostMapping("/validate") public Object validate(@RequestBody JsonNode body){return service.validate(body.path("definition"));}
    @PostMapping("/debug") public Object debug(@Valid @RequestBody DebugRequest request){return service.debug(request);}
}
