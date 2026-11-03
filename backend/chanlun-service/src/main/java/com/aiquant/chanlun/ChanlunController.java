package com.aiquant.chanlun;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.UUID;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/chanlun/v1")
public class ChanlunController {
    private final ChanlunService service;
    public ChanlunController(ChanlunService service) { this.service=service; }
    public record RunRequest(@NotNull UUID clientRequestId,
        @NotBlank @Pattern(regexp="native|chanpy|czsc|baseline") String engineId,
        @NotBlank @Pattern(regexp="fu-daily-2026-10-30") String datasetId,
        @Min(50) @Max(1894) int observedBars) {}
    public record JudgmentRequest(@NotNull UUID clientRequestId,@NotNull UUID runId,
        @Pattern(regexp="[a-f0-9]{24}") String structureId,
        @NotBlank @Pattern(regexp="UP|DOWN|WAIT") String outlook,
        @NotBlank @Size(max=6000) String content,@Min(1) @Max(108) Integer lessonNumber) {}
    @GetMapping("/engines") public Object engines() { return service.engines(); }
    @GetMapping("/datasets") public Object datasets() { return service.datasets(); }
    @PostMapping("/runs") public Object create(@Valid @RequestBody RunRequest r) { return service.create(r); }
    @GetMapping("/runs") public Object runs() { return service.runs(); }
    @GetMapping("/runs/{id}") public Object run(@PathVariable UUID id) { return service.run(id); }
    @GetMapping("/runs/{id}/structures") public Object result(@PathVariable UUID id) { return service.result(id); }
    @GetMapping("/runs/{id}/events") public Object events(@PathVariable UUID id,
        @RequestParam @Pattern(regexp="[a-f0-9]{24}") String structureId) { return service.events(id,structureId); }
    @PostMapping("/judgments") public Object judge(@Valid @RequestBody JudgmentRequest r) { return service.judge(r); }
    @GetMapping("/judgments") public Object judgments() { return service.judgments(); }
}
