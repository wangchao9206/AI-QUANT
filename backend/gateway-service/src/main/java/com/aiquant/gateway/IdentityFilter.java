package com.aiquant.gateway;

import java.time.Duration;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.gateway.filter.*;
import org.springframework.core.Ordered;
import org.springframework.http.*;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class IdentityFilter implements GlobalFilter,Ordered {
    private final WebClient client;
    IdentityFilter(WebClient.Builder builder,@Value("${IDENTITY_SERVICE_URL:http://localhost:8085}") String url,
            @Value("${IDENTITY_INTERNAL_SECRET:}") String secret){
        if(secret.length()<32)throw new IllegalArgumentException("IDENTITY_INTERNAL_SECRET must contain at least 32 characters");
        this.client=builder.baseUrl(url).defaultHeader("X-Identity-Service-Secret",secret).build();
    }
    @Override public int getOrder(){return Ordered.HIGHEST_PRECEDENCE+10;}
    @Override public Mono<Void> filter(ServerWebExchange exchange,GatewayFilterChain chain){
        var request=exchange.getRequest();String path=request.getURI().getRawPath();
        long start=System.nanoTime();var identityContext=new java.util.concurrent.atomic.AtomicReference<Context>();
        var clean=request.mutate().headers(headers->{headers.remove("X-Aiquant-Identity");headers.remove("X-Identity-Service-Secret");}).build();
        var target=exchange.mutate().request(clean).build();
        if(request.getMethod()==HttpMethod.OPTIONS||path.startsWith("/api/v1/auth/"))return chain.filter(target);
        String auth=request.getHeaders().getFirst(HttpHeaders.AUTHORIZATION);var cookie=request.getCookies().getFirst("aq_session");
        var body=new LinkedHashMap<String,Object>();body.put("session",cookie==null?null:cookie.getValue());body.put("bearer",auth!=null&&auth.startsWith("Bearer ")?auth.substring(7):null);
        body.put("tenant",request.getHeaders().getFirst("X-Tenant-Id"));body.put("csrf",request.getHeaders().getFirst("X-CSRF-Token"));
        body.put("mutation",!Set.of(HttpMethod.GET,HttpMethod.HEAD,HttpMethod.OPTIONS).contains(request.getMethod()));body.put("path",path);
        return client.post().uri("/internal/v1/identity/introspect").bodyValue(body).retrieve().bodyToMono(Context.class)
          .timeout(Duration.ofSeconds(5)).switchIfEmpty(Mono.error(new IllegalStateException("No identity context")))
          .flatMap(context->{identityContext.set(context);return chain.filter(target.mutate().request(clean.mutate().header("X-Aiquant-Identity",context.identity()).build()).build());})
          .onErrorResume(WebClientResponseException.class,error->{
            if(exchange.getResponse().isCommitted())return Mono.error(error);
            exchange.getResponse().setStatusCode(error.getStatusCode());exchange.getResponse().getHeaders().setContentType(MediaType.APPLICATION_JSON);exchange.getResponse().getHeaders().setCacheControl("no-store");
            return exchange.getResponse().writeWith(Mono.just(exchange.getResponse().bufferFactory().wrap(error.getResponseBodyAsByteArray())));
        }).onErrorResume(error->{
            if(exchange.getResponse().isCommitted())return Mono.error(error);
            exchange.getResponse().setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);return exchange.getResponse().setComplete();
        }).then(Mono.defer(()->{
            if(Set.of(HttpMethod.GET,HttpMethod.HEAD,HttpMethod.OPTIONS).contains(request.getMethod())&&!path.endsWith("/export"))return Mono.empty();
            Context context=identityContext.get();var event=new LinkedHashMap<String,Object>();event.put("userId",context==null?null:context.userId());event.put("tenantId",context==null?null:context.tenantId());event.put("method",request.getMethod().name());event.put("path",path.substring(0,Math.min(300,path.length())));event.put("status",exchange.getResponse().getStatusCode()==null?200:exchange.getResponse().getStatusCode().value());event.put("durationMs",(System.nanoTime()-start)/1000000);event.put("traceId",request.getHeaders().getFirst("X-Trace-Id"));
            return client.post().uri("/internal/v1/identity/operation").bodyValue(event).retrieve().toBodilessEntity().timeout(Duration.ofSeconds(2)).then().onErrorResume(error->{org.slf4j.LoggerFactory.getLogger(getClass()).error("business_operation_log_failed");return Mono.empty();});
        }));
    }
    record Context(String identity,UUID userId,UUID tenantId){}
}
