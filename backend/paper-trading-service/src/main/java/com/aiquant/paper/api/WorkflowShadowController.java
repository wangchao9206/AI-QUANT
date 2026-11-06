package com.aiquant.paper.api;
import com.aiquant.paper.service.WorkflowShadowService;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/paper/workflows")
public class WorkflowShadowController {
    private final WorkflowShadowService service;
    public WorkflowShadowController(WorkflowShadowService service){this.service=service;}
    @PostMapping("/versions/{id}/shadows") public Object create(@PathVariable UUID id,@Valid @RequestBody StrategyWorkflowController.ShadowRequest request){
        return service.create(id,request.clientRequestId(),request.symbol(),request.asOf(),request.direction());
    }
    @GetMapping("/versions/{id}/shadows") public Object list(@PathVariable UUID id){return service.list(id);}
    @GetMapping("/shadows/{id}") public Object get(@PathVariable UUID id){return service.get(id);}
}
