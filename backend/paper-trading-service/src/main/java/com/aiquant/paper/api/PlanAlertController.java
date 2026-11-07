package com.aiquant.paper.api;
import com.aiquant.paper.service.PlanAlertStore;
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
public class PlanAlertController {
 private final PlanAlertStore store;private final JdbcTemplate db;private final ObjectMapper json;private final String secret;
 public PlanAlertController(PlanAlertStore store,JdbcTemplate db,ObjectMapper json,@Value("${IDENTITY_INTERNAL_SECRET:}") String secret){this.store=store;this.db=db;this.json=json;this.secret=secret;}
 @ModelAttribute void noCache(HttpServletResponse res){res.setHeader("Cache-Control","no-store");}
 private UUID owner(HttpServletRequest req){UUID owner=DecisionAccess.owner(req,db,json,secret,null);try{var payload=json.readTree(Base64.getUrlDecoder().decode(req.getHeader("X-Aiquant-Identity").split("\\.")[0]));boolean read=false;for(var p:payload.path("permissions"))if("paper.read".equals(p.asText()))read=true;if(!read)throw new org.springframework.web.server.ResponseStatusException(org.springframework.http.HttpStatus.FORBIDDEN,"需要档案读取权限。");return owner;}catch(java.io.IOException e){throw new IllegalStateException(e);}}
 public record Edit(boolean enabled,@NotNull @Pattern(regexp="BREAKOUT|PULLBACK") String entryMode,@Min(0) long revision){}
 @GetMapping("/{id}/plans/{planId}/alerts") Object read(HttpServletRequest req,@PathVariable UUID id,@PathVariable UUID planId){return store.read(owner(req),id,planId);}
 @PostMapping("/{id}/plans/{planId}/alerts") Object edit(HttpServletRequest req,@PathVariable UUID id,@PathVariable UUID planId,@Valid @RequestBody Edit body){return store.edit(owner(req),id,planId,body.enabled(),body.entryMode(),body.revision());}
 @GetMapping("/alerts/events") Object events(HttpServletRequest req,@RequestParam(defaultValue="false") boolean unread,@RequestParam(defaultValue="1") int page){return store.events(owner(req),null,unread,page);}
 @PostMapping("/alerts/events/{id}/ack") Object ack(HttpServletRequest req,@PathVariable UUID id){store.acknowledge(owner(req),id);return Map.of("message","已标记已读。");}
}
