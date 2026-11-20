package com.aiquant.paper.api;

import com.aiquant.paper.service.ReplayReviewService;
import com.aiquant.paper.service.ReplayReviewService.Review;
import com.aiquant.paper.service.ReplayReviewService.SaveReview;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/paper")
public class ReplayReviewController {
    private final ReplayReviewService service;
    private final JdbcTemplate jdbc;
    private final ObjectMapper json;
    private final String secret;

    public ReplayReviewController(ReplayReviewService service, JdbcTemplate jdbc, ObjectMapper json,
        @Value("${IDENTITY_INTERNAL_SECRET:}") String secret) {
        this.service = service;
        this.jdbc = jdbc;
        this.json = json;
        this.secret = secret;
    }

    @ModelAttribute void privateResponse(HttpServletResponse response) {
        response.setHeader("Cache-Control","no-store");
    }

    @GetMapping("/sessions/{id}/replay-reviews")
    public List<Review> sessionNotes(@PathVariable UUID id, HttpServletRequest request) {
        return service.sessionNotes(id,DecisionAccess.paperActor(request,jdbc,json,secret));
    }

    @PostMapping("/sessions/{id}/replay-reviews")
    public Review saveSessionNote(@PathVariable UUID id, @Valid @RequestBody SaveReview review, HttpServletRequest request) {
        return service.saveSessionNote(id,DecisionAccess.paperActor(request,jdbc,json,secret),review);
    }

    @GetMapping("/workflows/versions/{id}/replay-reviews")
    public List<Review> runNotes(@PathVariable UUID id, @RequestParam UUID reviewRunId, HttpServletRequest request) {
        return service.runNotes(id,reviewRunId,DecisionAccess.workflowActor(request,jdbc,json,secret));
    }

    @PostMapping("/workflows/versions/{id}/replay-reviews")
    public Review saveRunNote(@PathVariable UUID id, @Valid @RequestBody SaveReview review, HttpServletRequest request) {
        return service.saveRunNote(id,DecisionAccess.workflowActor(request,jdbc,json,secret),review);
    }
}
