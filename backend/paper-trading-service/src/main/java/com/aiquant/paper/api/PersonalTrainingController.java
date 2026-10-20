package com.aiquant.paper.api;

import com.aiquant.paper.service.PersonalTrainingService;
import com.aiquant.paper.service.PersonalStrategyEngine.Rules;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.http.HttpStatus;

@RestController
@RequestMapping("/api/v1/paper/personal")
public class PersonalTrainingController {
    private final PersonalTrainingService service;
    public PersonalTrainingController(PersonalTrainingService service) {this.service=service;}
    public record CreateVersionRequest(@NotNull UUID parentId,@NotBlank @Size(max=120) String title,
        @NotBlank @Size(max=4000) String hypothesis,@NotBlank @Size(max=4000) String validationPlan,@NotNull Rules rules) {}
    public record CreateRunRequest(@NotNull UUID versionId,@NotBlank @Size(max=65) String name,
        @NotBlank @Pattern(regexp="[A-Za-z]{1,4}(?:0|M)") String symbol,
        @NotNull LocalDate startDate,@NotNull LocalDate endDate,
        @NotNull @DecimalMin("10000") @DecimalMax("1000000000") BigDecimal initialCash,
        @NotBlank @Pattern(regexp="GUIDED|RULE_REPLAY") String trainingMode) {}
    public record StepRequest(@NotNull UUID commandId,@Min(0) int expectedBarIndex,
        @NotBlank @Pattern(regexp="FOLLOW|WAIT|EXIT") String action,@Min(0) @Max(5) int emotion,
        boolean riskAccepted,boolean stopAccepted,boolean noRevenge,@NotNull @Size(max=4000) String notes) {}
    public record ReflectionRequest(UUID sessionId,UUID eventId,
        @NotBlank @Pattern(regexp="PRINCIPLE|EXECUTION|EMOTION|TECHNICAL|IMPROVEMENT") String category,
        @NotBlank @Size(max=5000) String content) {}

    @GetMapping("/versions") public Object versions(){return service.versions();}
    @PostMapping("/versions") public Object version(@Valid @RequestBody CreateVersionRequest r){return service.createVersion(r);}
    @GetMapping("/runs") public Object runs(@RequestParam(defaultValue="1") int page,@RequestParam(defaultValue="10") int pageSize){return service.runs(page,pageSize);}
    @PostMapping("/runs") public Object create(@Valid @RequestBody CreateRunRequest r){return service.create(r);}
    @GetMapping("/runs/{id}") public Object detail(@PathVariable UUID id){return service.detail(id);}
    @PostMapping("/runs/{id}/step") public Object step(@PathVariable UUID id,@Valid @RequestBody StepRequest r){return service.step(id,r);}
    @GetMapping("/runs/{id}/events") public Object events(@PathVariable UUID id,@RequestParam(defaultValue="1") int page,@RequestParam(defaultValue="10") int pageSize){return service.events(id,page,pageSize);}
    @GetMapping("/reflections") public Object reflections(@RequestParam(required=false) UUID sessionId,@RequestParam(defaultValue="1") int page,@RequestParam(defaultValue="10") int pageSize){return service.reflections(sessionId,page,pageSize);}
    @PostMapping("/reflections") @ResponseStatus(HttpStatus.NO_CONTENT)
    public void reflect(@Valid @RequestBody ReflectionRequest r){service.reflect(r);}
}
