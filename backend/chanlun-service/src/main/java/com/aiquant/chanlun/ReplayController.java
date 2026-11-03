package com.aiquant.chanlun;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.UUID;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/chanlun/v1/replays")
public class ReplayController {
    private final ReplayService service;
    public ReplayController(ReplayService service) { this.service=service; }
    public record CreateRequest(@NotNull UUID clientRequestId,@Size(max=120) String title,
        @NotBlank @Pattern(regexp="native|chanpy|czsc|baseline") String engineId,
        @NotBlank @Pattern(regexp="fu-daily-2026-10-30") String datasetId,
        @Min(50) @Max(1893) int startBars) {}
    public record DecisionRequest(@NotNull UUID clientRequestId,@Min(0) @Max(1844) int expectedStep,
        @Pattern(regexp="[a-f0-9]{24}") String structureId,
        @NotBlank @Pattern(regexp="UP|DOWN|WAIT") String outlook,
        @NotBlank @Size(max=6000) String content,@Min(1) @Max(108) Integer lessonNumber) {}
    public record AdvanceRequest(@NotNull UUID clientRequestId,@Min(0) @Max(1844) int expectedStep) {}
    private ResponseEntity<?> response(Object value) { return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(value); }
    @PostMapping public Object create(@Valid @RequestBody CreateRequest r) { return response(service.create(r)); }
    @GetMapping public Object recent() { return response(service.recent()); }
    @GetMapping("/{id}") public Object view(@PathVariable UUID id) { return response(service.view(id)); }
    @PostMapping("/{id}/decisions") public Object decide(@PathVariable UUID id,@Valid @RequestBody DecisionRequest r) { return response(service.decide(id,r)); }
    @PostMapping("/{id}/advance") public Object advance(@PathVariable UUID id,@Valid @RequestBody AdvanceRequest r) { return response(service.advance(id,r)); }
}
