package com.aiquant.market.monitor;

import com.aiquant.tenancy.TenantBoundaryConfiguration;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestClientResponseException;

@RestController
@RequestMapping({"/api/v1/market/monitors","/api/v1/options/monitors"})
public class MonitorController {
    private final MonitorStore store;private final MonitorClients clients;private final ObjectMapper mapper;private final String secret;
    public MonitorController(MonitorStore store,MonitorClients clients,ObjectMapper mapper,@Value("${IDENTITY_INTERNAL_SECRET:}") String secret){this.store=store;this.clients=clients;this.mapper=mapper;this.secret=secret;}
    public record Edit(@NotBlank @Size(max=80) String name,boolean enabled,@NotBlank @Size(max=100) String symbol,int seconds,@NotNull @Size(max=20) Map<String,Object> parameters,@Min(0) long version){}
    public record Enabled(boolean enabled,@Min(0) long version){}
    public record Version(@Min(0) long version){}
    @ModelAttribute void privateResponse(HttpServletResponse response){response.setHeader("Cache-Control","no-store");}
    MonitorStore.Scope scope(HttpServletRequest request){
        try{String token=request.getHeader("X-Aiquant-Identity");UUID tenant=TenantBoundaryConfiguration.verify(token,secret,mapper);
            var payload=mapper.readTree(Base64.getUrlDecoder().decode(token.split("\\.")[0]));
            return new MonitorStore.Scope(tenant,UUID.fromString(payload.path("userId").asText()),request.getRequestURI().startsWith("/api/v1/options/")?"OPTION":"FUTURE");
        }catch(Exception e){throw MonitorStore.fail(HttpStatus.UNAUTHORIZED,"需要经过网关验证的租户身份。");}
    }
    @GetMapping("/catalog") Object catalog(HttpServletRequest req){scope(req);try{return clients.catalog();}catch(RuntimeException e){throw MonitorStore.fail(HttpStatus.SERVICE_UNAVAILABLE,"监控规则服务暂不可用。");}}
    @GetMapping Object list(HttpServletRequest req,@RequestParam(defaultValue="") @Size(max=100) String q,@RequestParam(defaultValue="1") int page,@RequestParam(defaultValue="20") int size){return store.list(scope(req),q,page,size);}
    @GetMapping("/{id}") Object get(HttpServletRequest req,@PathVariable UUID id){return store.get(scope(req),id);}
    Map<String,Object> validate(MonitorStore.Scope scope,Edit body){
        try{return clients.validate(Map.of("assetType",scope.kind(),"symbol",body.symbol(),"seconds",body.seconds(),"parameters",body.parameters()));}
        catch(RestClientResponseException e){if(e.getStatusCode().is4xxClientError())throw MonitorStore.fail(HttpStatus.BAD_REQUEST,"合约或规则参数校验失败："+e.getResponseBodyAsString().substring(0,Math.min(350,e.getResponseBodyAsString().length())));throw MonitorStore.fail(HttpStatus.SERVICE_UNAVAILABLE,"主行情监控服务暂不可用。");}
        catch(RuntimeException e){throw MonitorStore.fail(HttpStatus.SERVICE_UNAVAILABLE,"主行情监控服务暂不可用。");}
    }
    @PostMapping Object create(HttpServletRequest req,@Valid @RequestBody Edit body){var scope=scope(req);return store.save(scope,null,body.name(),body.enabled(),0,validate(scope,body));}
    @PostMapping("/{id}") Object edit(HttpServletRequest req,@PathVariable UUID id,@Valid @RequestBody Edit body){var scope=scope(req);store.get(scope,id);return store.save(scope,id,body.name(),body.enabled(),body.version(),validate(scope,body));}
    @PostMapping("/{id}/enabled") Object enabled(HttpServletRequest req,@PathVariable UUID id,@Valid @RequestBody Enabled body){return store.enable(scope(req),id,body.enabled(),body.version());}
    @PostMapping("/{id}/archive") Object archive(HttpServletRequest req,@PathVariable UUID id,@Valid @RequestBody Version body){store.archive(scope(req),id,body.version());return Map.of("message","监控已归档，触发记录保留。");}
    @GetMapping("/events") Object events(HttpServletRequest req,@RequestParam(defaultValue="") String q,@RequestParam(required=false) UUID monitorId,@RequestParam(defaultValue="false") boolean unacknowledged,@RequestParam(defaultValue="1") int page,@RequestParam(defaultValue="20") int size){return store.events(scope(req),q,monitorId,unacknowledged,page,size);}
    @PostMapping("/events/{id}/ack") Object acknowledge(HttpServletRequest req,@PathVariable long id){store.acknowledge(scope(req),id);return Map.of("message","已标记已读。");}
}
