package com.aiquant.paper.api;

import com.aiquant.paper.service.DecisionJournalService;
import com.aiquant.paper.service.DecisionJournalService.*;
import com.aiquant.tenancy.TenantBoundaryConfiguration;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/paper/decisions")
public class DecisionController {
    private final DecisionJournalService service; private final JdbcTemplate jdbc;private final ObjectMapper json;private final String secret;
    public DecisionController(DecisionJournalService service,JdbcTemplate jdbc,ObjectMapper json,@Value("${IDENTITY_INTERNAL_SECRET:}") String secret){this.service=service;this.jdbc=jdbc;this.json=json;this.secret=secret;}
    @ModelAttribute void noCache(HttpServletResponse res){res.setHeader("Cache-Control","no-store");}
    private UUID owner(HttpServletRequest req){
        try{
            String token=req.getHeader("X-Aiquant-Identity");TenantBoundaryConfiguration.verify(token,secret,json);
            var payload=json.readTree(Base64.getUrlDecoder().decode(token.split("\\.")[0]));
            var permissions=new HashSet<String>();for(var permission:payload.path("permissions"))permissions.add(permission.asText());
            if(!permissions.contains("market.read")||!permissions.contains("GET".equals(req.getMethod())?"paper.read":"paper.write"))throw new org.springframework.web.server.ResponseStatusException(org.springframework.http.HttpStatus.FORBIDDEN,"当前身份缺少行情或决策档案操作权限。");
            UUID owner=UUID.fromString(payload.path("userId").asText());
            jdbc.queryForObject("select set_config('app.user_id',?,true)",String.class,owner.toString());return owner;
        }catch(org.springframework.web.server.ResponseStatusException e){throw e;}
        catch(Exception e){throw new org.springframework.web.server.ResponseStatusException(org.springframework.http.HttpStatus.UNAUTHORIZED,"需要经过网关验证的身份。");}
    }
    public record EventRequest(@Min(1) long eventId){}
    public record Command(@NotNull UUID commandId){}
    @GetMapping public Object list(HttpServletRequest req,@RequestParam(defaultValue="1") int page,@RequestParam(defaultValue="20") int size){return service.list(owner(req),page,size);}
    @GetMapping("/for-session/{sessionId}") public Object forSession(HttpServletRequest req,@PathVariable UUID sessionId){return service.forSession(owner(req),sessionId);}
    @PostMapping("/from-event") public Object fromEvent(HttpServletRequest req,@Valid @RequestBody EventRequest body){return service.fromEvent(owner(req),body.eventId(),req.getHeader("X-Aiquant-Identity"));}
    @GetMapping("/{id}") public Object detail(HttpServletRequest req,@PathVariable UUID id){return service.detail(owner(req),id);}
    @PostMapping("/{id}/plans") public Object save(HttpServletRequest req,@PathVariable UUID id,@Valid @RequestBody SavePlan body){return service.save(owner(req),id,body);}
    @PostMapping("/{id}/plans/{planId}/check") public Object check(HttpServletRequest req,@PathVariable UUID id,@PathVariable UUID planId){return service.check(owner(req),id,planId);}
    @PostMapping("/{id}/plans/{planId}/paper") public Object paper(HttpServletRequest req,@PathVariable UUID id,@PathVariable UUID planId,@Valid @RequestBody Command body){return service.paper(owner(req),id,planId,body.commandId());}
    @PostMapping("/{id}/plans/{planId}/reviews") public Object review(HttpServletRequest req,@PathVariable UUID id,@PathVariable UUID planId,@Valid @RequestBody Review body){return service.review(owner(req),id,planId,body);}
}
