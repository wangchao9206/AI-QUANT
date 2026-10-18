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

    public PaperTradingController(PaperTradingService service) {
        this.service = service;
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
                                     @RequestParam(defaultValue = "240") int limit) {
        return service.chart(sessionId, limit);
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
