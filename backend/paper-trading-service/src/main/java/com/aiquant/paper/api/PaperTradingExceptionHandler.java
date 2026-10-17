package com.aiquant.paper.api;

import java.time.Instant;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.client.ResourceAccessException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

@RestControllerAdvice
public class PaperTradingExceptionHandler {
    @ExceptionHandler(RestClientResponseException.class)
    ResponseEntity<Map<String, Object>> upstream(RestClientResponseException exception) {
        int code = exception.getStatusCode().value();
        HttpStatus status = code >= 400 && code < 500 ? HttpStatus.BAD_REQUEST : HttpStatus.SERVICE_UNAVAILABLE;
        String message = "模拟所需的数据服务暂不可用，请稍后重试";
        try {
            JsonNode body = new ObjectMapper().readTree(exception.getResponseBodyAsString());
            JsonNode detail = body.hasNonNull("detail") ? body.get("detail") : body.get("message");
            if (detail != null && detail.isTextual() && !detail.asText().isBlank()) message = detail.asText();
        } catch (Exception ignored) {
            // Never forward upstream HTML, stack traces or connection details.
        }
        return error(status, message);
    }

    @ExceptionHandler(ResourceAccessException.class)
    ResponseEntity<Map<String, Object>> unavailable(ResourceAccessException exception) {
        return error(HttpStatus.SERVICE_UNAVAILABLE, "模拟所需的数据服务连接超时或暂不可用，请稍后重试");
    }
    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, Object>> badRequest(IllegalArgumentException exception) {
        return error(HttpStatus.BAD_REQUEST, exception.getMessage());
    }

    @ExceptionHandler(IllegalStateException.class)
    ResponseEntity<Map<String, Object>> conflict(IllegalStateException exception) {
        return error(HttpStatus.CONFLICT, exception.getMessage());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<Map<String, Object>> validation(MethodArgumentNotValidException exception) {
        String message = exception.getBindingResult().getFieldErrors().stream()
            .findFirst().map(error -> error.getField() + ": " + error.getDefaultMessage())
            .orElse("请求参数不合法");
        return error(HttpStatus.BAD_REQUEST, message);
    }

    private ResponseEntity<Map<String, Object>> error(HttpStatus status, String message) {
        return ResponseEntity.status(status).body(Map.of(
            "status", status.value(),
            "message", message == null ? status.getReasonPhrase() : message,
            "timestamp", Instant.now().toString()
        ));
    }
}
