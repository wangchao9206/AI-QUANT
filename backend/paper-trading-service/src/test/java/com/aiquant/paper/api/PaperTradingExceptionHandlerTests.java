package com.aiquant.paper.api;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class PaperTradingExceptionHandlerTests {
    @RestController
    static class FailingData {
        @GetMapping("/unavailable") String unavailable() {
            throw HttpServerErrorException.create(HttpStatus.SERVICE_UNAVAILABLE, "Unavailable", HttpHeaders.EMPTY,
                "{\"detail\":\"暂无真实合约回放数据\"}".getBytes(StandardCharsets.UTF_8), StandardCharsets.UTF_8);
        }
        @GetMapping("/invalid") String invalid() {
            throw HttpClientErrorException.create(HttpStatus.BAD_REQUEST, "Bad request", HttpHeaders.EMPTY,
                "{\"detail\":\"有效历史数据不足两根\"}".getBytes(StandardCharsets.UTF_8), StandardCharsets.UTF_8);
        }
        @GetMapping("/html") String html() {
            throw HttpServerErrorException.create(HttpStatus.BAD_GATEWAY, "Bad gateway", HttpHeaders.EMPTY,
                "<html>internal stack trace</html>".getBytes(StandardCharsets.UTF_8), StandardCharsets.UTF_8);
        }
        @GetMapping("/timeout") String timeout() { throw new ResourceAccessException("internal connection"); }
    }
    private final MockMvc mvc = MockMvcBuilders.standaloneSetup(new FailingData())
        .setControllerAdvice(new PaperTradingExceptionHandler()).build();

    @Test void preservesUsefulDataErrorsInsteadOfReturningGeneric500() throws Exception {
        mvc.perform(get("/unavailable")).andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.message").value("暂无真实合约回放数据"));
        mvc.perform(get("/invalid")).andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.message").value("有效历史数据不足两根"));
    }
    @Test void doesNotExposeUpstreamHtmlOrConnectionDetails() throws Exception {
        mvc.perform(get("/html")).andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.message").value("模拟所需的数据服务暂不可用，请稍后重试"));
        mvc.perform(get("/timeout")).andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.message").value("模拟所需的数据服务连接超时或暂不可用，请稍后重试"));
    }
}
