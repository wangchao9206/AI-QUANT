package com.aiquant.chanlun;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.List;
import java.util.UUID;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/chanlun/v1/comparisons")
public class ComparisonController {
    private final ComparisonService service;
    public ComparisonController(ComparisonService service){this.service=service;}
    public record Create(@NotNull UUID clientRequestId,@NotNull @Size(min=2,max=4) List<@NotNull UUID> runIds,
                         @NotNull @Pattern(regexp="BI|SEGMENT|ZONE") String layer,
                         @NotNull @Pattern(regexp="GEOMETRY|WITH_CONFIRMATION") String projection,boolean confirmedOnly) {}
    public record Judge(@NotNull UUID clientRequestId,@NotNull UUID sourceRunId,
                        @Pattern(regexp="[a-f0-9]{24}") String structureId,
                        @NotNull @Pattern(regexp="UP|DOWN|WAIT") String outlook,
                        @NotBlank @Size(max=6000) String content,@Min(1) @Max(108) Integer lessonNumber) {}
    @PostMapping public Object create(@Valid @RequestBody Create request){return service.create(request);}
    @GetMapping public Object list(){return service.list();}
    @GetMapping("/{id}") public Object get(@PathVariable UUID id){return service.get(id);}
    @GetMapping("/{id}/at/{index}") public Object at(@PathVariable UUID id,@PathVariable @Min(0) int index){return service.at(id,index);}
    @GetMapping("/{id}/events") public Object events(@PathVariable UUID id,@RequestParam UUID sourceRunId,
            @RequestParam @Min(0) int observedIndex,@RequestParam @Pattern(regexp="[a-f0-9]{24}") String structureId){return service.events(id,sourceRunId,observedIndex,structureId);}
    @PostMapping("/{id}/at/{index}/judgments") public Object judge(@PathVariable UUID id,@PathVariable @Min(0) int index,@Valid @RequestBody Judge request){return service.judge(id,index,request);}
}
