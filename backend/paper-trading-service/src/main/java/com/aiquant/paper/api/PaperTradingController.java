package com.aiquant.paper.api;

import com.aiquant.paper.api.PaperRequests.AdvanceRequest;
import com.aiquant.paper.api.PaperRequests.CreateSessionRequest;
import com.aiquant.paper.api.PaperRequests.PlaceOrderRequest;
import com.aiquant.paper.service.PaperTradingService;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import jakarta.validation.Valid;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.http.ResponseEntity;

@RestController
@RequestMapping("/api/v1/paper")
public class PaperTradingController {
    private final PaperTradingService service;
    private final org.springframework.jdbc.core.JdbcTemplate jdbc;
    private final com.fasterxml.jackson.databind.ObjectMapper json;
    private final String secret;

    public PaperTradingController(PaperTradingService service,org.springframework.jdbc.core.JdbcTemplate jdbc,
        com.fasterxml.jackson.databind.ObjectMapper json,@org.springframework.beans.factory.annotation.Value("${IDENTITY_INTERNAL_SECRET:}") String secret) {
        this.service = service;this.jdbc=jdbc;this.json=json;this.secret=secret;
    }

    @org.springframework.web.bind.annotation.ModelAttribute
    void actor(jakarta.servlet.http.HttpServletRequest request,jakarta.servlet.http.HttpServletResponse response){
        response.setHeader("Cache-Control","no-store");
        request.setAttribute("paperOwner",DecisionAccess.paperActor(request,jdbc,json,secret));
    }

    @GetMapping("/intraday/catalog")
    public Object intradayCatalog(){return service.intradayCatalog();}

    @GetMapping("/sessions/{sessionId}/fills/{fillId}/note")
    public Object note(@PathVariable UUID sessionId,@PathVariable UUID fillId,
        @org.springframework.web.bind.annotation.RequestAttribute("paperOwner") UUID owner){
        return new com.aiquant.paper.service.PaperFillNoteService(jdbc).get(sessionId,fillId,owner);
    }
    @PostMapping("/sessions/{sessionId}/fills/{fillId}/note")
    public Object saveNote(@PathVariable UUID sessionId,@PathVariable UUID fillId,
        @org.springframework.web.bind.annotation.RequestAttribute("paperOwner") UUID owner,
        @Valid @RequestBody com.aiquant.paper.service.PaperFillNoteService.SaveNote body){
        return new com.aiquant.paper.service.PaperFillNoteService(jdbc).save(sessionId,fillId,owner,body);
    }

    @GetMapping("/sessions")
    public List<Map<String, Object>> sessions() {
        return service.listSessions();
    }

    @PostMapping("/sessions")
    public Map<String, Object> create(@Valid @RequestBody CreateSessionRequest request) {
        return service.createSession(request);
    }

    @GetMapping("/sessions/{sessionId}")
    public Map<String, Object> detail(@PathVariable UUID sessionId) {
        return service.detail(sessionId);
    }

    @DeleteMapping("/sessions/{sessionId}")
    public ResponseEntity<Void> delete(@PathVariable UUID sessionId) {
        service.deleteSession(sessionId);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/sessions/{sessionId}/chart")
    public Map<String, Object> chart(@PathVariable UUID sessionId,
                                     @RequestParam(defaultValue = "240") int limit,
                                     @RequestParam(required=false) Integer barSeconds) {
        return barSeconds==null?service.chart(sessionId, limit):service.chart(sessionId,limit,barSeconds);
    }

    @GetMapping("/sessions/{sessionId}/strategy-evidence")
    public Object strategyEvidence(@PathVariable UUID sessionId,@RequestParam java.time.Instant asOf){
        return service.strategyEvidence(sessionId,asOf);
    }

    @GetMapping("/sessions/{sessionId}/records/{kind}")
    public Map<String, Object> records(@PathVariable UUID sessionId, @PathVariable String kind,
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(defaultValue = "20") int pageSize) {
        return service.records(sessionId, kind, page, pageSize);
    }

    @PostMapping("/sessions/{sessionId}/orders")
    public Map<String, Object> placeOrder(
        @PathVariable UUID sessionId,
        @Valid @RequestBody PlaceOrderRequest request
    ) {
        return service.placeOrder(sessionId, request);
    }

    @PostMapping("/sessions/{sessionId}/orders/{orderId}/cancel")
    public Map<String, Object> cancel(@PathVariable UUID sessionId, @PathVariable UUID orderId) {
        return service.cancelOrder(sessionId, orderId);
    }

    @PostMapping("/sessions/{sessionId}/advance")
    public Map<String, Object> advance(
        @PathVariable UUID sessionId,
        @Valid @RequestBody AdvanceRequest request
    ) {
        return service.advance(sessionId, request);
    }

    @PostMapping("/sessions/{sessionId}/pause")
    public Map<String, Object> pause(@PathVariable UUID sessionId) {
        return service.setPaused(sessionId, true);
    }

    @PostMapping("/sessions/{sessionId}/resume")
    public Map<String, Object> resume(@PathVariable UUID sessionId) {
        return service.setPaused(sessionId, false);
    }
}
