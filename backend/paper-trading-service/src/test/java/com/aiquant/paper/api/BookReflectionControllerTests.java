package com.aiquant.paper.api;

import com.aiquant.paper.service.BookReflectionService;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class BookReflectionControllerTests {
    @Test void validatesWhitespaceCategoriesAndContentSizeBeforeWriting() throws Exception {
        var service=mock(BookReflectionService.class);
        var mvc=MockMvcBuilders.standaloneSetup(new BookReflectionController(service)).setControllerAdvice(new PaperTradingExceptionHandler()).build();
        mvc.perform(post("/api/v1/paper/books").contentType("application/json").content("{\"clientRequestId\":\"request-123\",\"title\":\"   \"}")).andExpect(status().isBadRequest());
        mvc.perform(post("/api/v1/paper/books/b00c0001-0000-4000-8000-000000000001/reflections").contentType("application/json")
            .content("{\"clientRequestId\":\"request-123\",\"category\":\"BAD\",\"content\":\"content\"}")).andExpect(status().isBadRequest());
        mvc.perform(post("/api/v1/paper/books/b00c0001-0000-4000-8000-000000000001/reflections").contentType("application/json")
            .content("{\"clientRequestId\":\"request-123\",\"category\":\"IDEA\",\"content\":\""+"x".repeat(6001)+"\"}")).andExpect(status().isBadRequest());
        verifyNoInteractions(service);
    }
    @Test void readsTheShelfThroughTheExistingPaperGatewayPrefix() throws Exception {
        var service=mock(BookReflectionService.class);when(service.books()).thenReturn(java.util.List.of());
        var mvc=MockMvcBuilders.standaloneSetup(new BookReflectionController(service)).build();
        mvc.perform(get("/api/v1/paper/books")).andExpect(status().isOk()).andExpect(content().json("[]"));
    }
}
