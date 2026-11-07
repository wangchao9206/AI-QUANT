package com.aiquant.paper.api;
import com.aiquant.paper.service.ResearchDecisionService;
import com.fasterxml.jackson.databind.*;
import jakarta.servlet.http.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/paper/decisions/research")
public class ResearchDecisionController {
 private final ResearchDecisionService service;private final JdbcTemplate db;private final ObjectMapper json;private final String secret;
 public ResearchDecisionController(ResearchDecisionService service,JdbcTemplate db,ObjectMapper json,@Value("${IDENTITY_INTERNAL_SECRET:}") String secret){this.service=service;this.db=db;this.json=json;this.secret=secret;}
 private UUID owner(HttpServletRequest req,String permission){return DecisionAccess.owner(req,db,json,secret,permission);}
 @ModelAttribute void noCache(HttpServletResponse res){res.setHeader("Cache-Control","no-store");}
 public record Calculate(@NotNull UUID commandId,@NotNull JsonNode inputs){}
 public record ImportPreview(@NotNull UUID commandId,@NotBlank @Size(max=80) String scope,@NotBlank @Size(max=80) String sourceScope,boolean acknowledgeUnscoped,@NotBlank @Size(max=180000) String entryJson){}
 public record Archive(boolean acknowledgeLocalOrigin,UUID targetCaseId){}
 @PostMapping("/calculate") Object calculate(HttpServletRequest req,@Valid @RequestBody Calculate body){return service.calculate(owner(req,"research.write"),body.commandId(),body.inputs());}
 @PostMapping("/import-preview") Object preview(HttpServletRequest req,@Valid @RequestBody ImportPreview body){return service.preview(owner(req,"research.read"),body.commandId(),body.scope(),body.sourceScope(),body.acknowledgeUnscoped(),body.entryJson());}
 @GetMapping("/sources/{id}") Object source(HttpServletRequest req,@PathVariable UUID id){return service.source(owner(req,"research.read"),id);}
 @PostMapping("/sources/{id}/archive") Object archive(HttpServletRequest req,@PathVariable UUID id,@Valid @RequestBody Archive body){return service.archive(owner(req,"research.read"),id,body.acknowledgeLocalOrigin(),body.targetCaseId());}
}
