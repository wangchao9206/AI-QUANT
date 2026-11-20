package com.aiquant.paper.api;

import com.aiquant.paper.service.WorkflowTrialService;
import com.aiquant.paper.service.WorkflowTrialService.CreateTrial;
import com.aiquant.paper.service.WorkflowTrialService.Detail;
import com.aiquant.paper.service.WorkflowTrialService.Trial;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/paper/workflow-trials")
public class WorkflowTrialController {
    private final WorkflowTrialService service;
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private final String secret;

    public WorkflowTrialController(WorkflowTrialService service, JdbcTemplate jdbc, ObjectMapper mapper,
        @Value("${IDENTITY_INTERNAL_SECRET:}") String secret) {
        this.service = service;
        this.jdbc = jdbc;
        this.mapper = mapper;
        this.secret = secret;
    }

    @ModelAttribute void privateResponse(HttpServletResponse response) {
        response.setHeader("Cache-Control","no-store");
    }

    @GetMapping public List<Trial> list(HttpServletRequest request) {
        return service.list(DecisionAccess.paperActor(request,jdbc,mapper,secret));
    }

    @GetMapping("/{id}") public Detail detail(@PathVariable UUID id, HttpServletRequest request) {
        return service.detail(DecisionAccess.paperActor(request,jdbc,mapper,secret),id);
    }

    @PostMapping public Detail create(@Valid @RequestBody CreateTrial trial, HttpServletRequest request) {
        return service.create(DecisionAccess.paperActor(request,jdbc,mapper,secret),trial);
    }
}
