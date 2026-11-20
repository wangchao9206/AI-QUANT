package com.aiquant.paper.api;
import com.aiquant.paper.service.PaperAutomationService;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.*;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/paper/sessions/{sessionId}/automation")
public class PaperAutomationController {
    private final PaperAutomationService service;private final JdbcTemplate db;private final ObjectMapper json;private final String secret;
    public PaperAutomationController(PaperAutomationService service,JdbcTemplate db,ObjectMapper json,@Value("${IDENTITY_INTERNAL_SECRET:}") String secret){this.service=service;this.db=db;this.json=json;this.secret=secret;}
    @ModelAttribute void actor(HttpServletRequest req,HttpServletResponse res){res.setHeader("Cache-Control","no-store");req.setAttribute("automationOwner",DecisionAccess.owner(req,db,json,secret,null));}
    @GetMapping public Object state(@PathVariable UUID sessionId){return service.state(sessionId);}
    @PostMapping public Object start(@PathVariable UUID sessionId,@RequestAttribute("automationOwner") UUID owner,@Valid @RequestBody PaperAutomationService.Start request){return service.start(sessionId,owner,request);}
    @PostMapping("/{runId}/stop") public Object stop(@PathVariable UUID sessionId,@PathVariable UUID runId){return service.stop(sessionId,runId);}
}
