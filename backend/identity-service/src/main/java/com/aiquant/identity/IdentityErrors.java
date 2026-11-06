package com.aiquant.identity;
import java.util.Map;
import org.springframework.dao.*;
import org.springframework.http.*;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.*;
@RestControllerAdvice
class IdentityErrors {
    @ExceptionHandler(DataIntegrityViolationException.class) ResponseEntity<?> conflict(){return ResponseEntity.status(409).body(Map.of("message","账号、邮箱或记录已存在，或当前操作与其他更新冲突。"));}
    @ExceptionHandler(DataAccessException.class) ResponseEntity<?> database(){return ResponseEntity.status(503).body(Map.of("message","账号数据服务暂不可用，请稍后重试。"));}
    @ExceptionHandler(MethodArgumentNotValidException.class) ResponseEntity<?> invalid(){return ResponseEntity.badRequest().body(Map.of("message","输入参数不完整或格式无效，请检查后重试。"));}
}
