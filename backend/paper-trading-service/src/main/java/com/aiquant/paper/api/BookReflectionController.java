package com.aiquant.paper.api;

import com.aiquant.paper.service.BookReflectionService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.UUID;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/paper/books")
public class BookReflectionController {
    private final BookReflectionService service;
    public BookReflectionController(BookReflectionService service) { this.service=service; }
    public record CreateBookRequest(
        @NotBlank @Pattern(regexp="[A-Za-z0-9-]{8,128}") String clientRequestId,
        @NotBlank @Size(max=120) String title,@Size(max=80) String author) {}
    public record CreateReflectionRequest(
        @NotBlank @Pattern(regexp="[A-Za-z0-9-]{8,128}") String clientRequestId,
        @NotBlank @Pattern(regexp="IDEA|TRADING|QUESTION") String category,
        @NotBlank @Size(max=6000) String content) {}
    @GetMapping public Object books() { return service.books(); }
    @PostMapping public Object create(@Valid @RequestBody CreateBookRequest r) { return service.create(r); }
    @GetMapping("/{id}/preview") public Object preview(@PathVariable UUID id,
        @RequestParam(defaultValue="false") boolean refresh) { return service.preview(id,refresh); }
    @GetMapping("/{id}/reflections") public Object reflections(@PathVariable UUID id,
        @RequestParam(defaultValue="1") int page,@RequestParam(defaultValue="10") int pageSize) {
        return service.reflections(id,page,pageSize);
    }
    @PostMapping("/{id}/reflections") public Object reflect(@PathVariable UUID id,
        @Valid @RequestBody CreateReflectionRequest r) { return service.reflect(id,r); }
}
