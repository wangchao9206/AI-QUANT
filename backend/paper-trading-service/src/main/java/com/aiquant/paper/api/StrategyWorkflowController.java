package com.aiquant.paper.api;

import com.aiquant.paper.service.StrategyWorkflowService;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.time.Instant;
import java.util.UUID;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/paper/workflows")
public class StrategyWorkflowController {
    private final StrategyWorkflowService service;
    public StrategyWorkflowController(StrategyWorkflowService service){this.service=service;}
    public record CreateRequest(@NotBlank @Pattern(regexp="[A-Za-z0-9-]{8,128}") String clientRequestId,
        @NotBlank @Size(max=120) String name,@Size(max=1000) String description,@NotNull JsonNode definition) {}
    public record SaveRequest(@Min(1) int expectedRevision,@NotBlank @Size(max=120) String name,
        @Size(max=1000) String description,@NotNull JsonNode definition) {}
    public record PublishRequest(@Min(1) int expectedRevision,@NotBlank @Pattern(regexp="[A-Za-z0-9-]{8,128}") String clientRequestId) {}
    public record DebugRequest(@NotNull JsonNode definition,@NotBlank @Pattern(regexp="[A-Za-z]{1,4}(?:0|M)") String symbol,
        @NotNull Instant asOf,@Min(-1) @Max(1) int direction) {}
    @GetMapping public Object list(){return service.list();}
    @GetMapping("/versions") public Object published(){return service.published();}
    @GetMapping("/versions/{id}") public Object version(@PathVariable UUID id){return service.version(id);}
    @PostMapping("/versions/{id}/backtest") public Object backtest(@PathVariable UUID id,@RequestBody JsonNode body){return service.backtest(id,body);}
    @PostMapping public Object create(@Valid @RequestBody CreateRequest request){return service.create(request);}
    @GetMapping("/{id}") public Object detail(@PathVariable UUID id){return service.detail(id);}
    @PutMapping("/{id}") public Object save(@PathVariable UUID id,@Valid @RequestBody SaveRequest request){return service.save(id,request);}
    @PostMapping("/{id}/publish") public Object publish(@PathVariable UUID id,@Valid @RequestBody PublishRequest request){return service.publish(id,request);}
    @PostMapping("/validate") public Object validate(@RequestBody JsonNode body){return service.validate(body.path("definition"));}
    @PostMapping("/debug") public Object debug(@Valid @RequestBody DebugRequest request){return service.debug(request);}
}
