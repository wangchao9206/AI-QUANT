package com.aiquant.market.monitor;

import java.time.Duration;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class MonitorClients {
    private final RestClient algorithm,identity;
    private static final ParameterizedTypeReference<Map<String,Object>> MAP=new ParameterizedTypeReference<>(){};
    public MonitorClients(@Value("${ALGORITHM_SERVICE_URL:http://localhost:8000}") String algorithmUrl,
            @Value("${IDENTITY_SERVICE_URL:http://localhost:8085}") String identityUrl,
            @Value("${IDENTITY_INTERNAL_SECRET:}") String secret){
        if(secret.length()<32)throw new IllegalArgumentException("IDENTITY_INTERNAL_SECRET must contain at least 32 characters");
        var factory=new SimpleClientHttpRequestFactory();factory.setConnectTimeout(Duration.ofSeconds(1));factory.setReadTimeout(Duration.ofSeconds(6));
        algorithm=RestClient.builder().baseUrl(algorithmUrl).requestFactory(factory).defaultHeader("X-Identity-Service-Secret",secret).build();
        identity=RestClient.builder().baseUrl(identityUrl).requestFactory(factory).defaultHeader("X-Identity-Service-Secret",secret).build();
    }
    public Map<String,Object> catalog(){return required(algorithm.get().uri("/internal/v1/monitor/catalog").retrieve().body(MAP));}
    public Map<String,Object> validate(Map<String,Object> spec){return required(algorithm.post().uri("/internal/v1/monitor/validate").body(spec).retrieve().body(MAP));}
    public Map<String,Object> evaluate(Map<String,Object> spec,Map<String,Object> state){return required(algorithm.post().uri("/internal/v1/monitor/evaluate").body(Map.of("spec",spec,"state",state)).retrieve().body(MAP));}
    public boolean authorized(UUID user,UUID tenant,String type){return Boolean.TRUE.equals(required(identity.post().uri("/internal/v1/identity/monitor-authorization")
        .body(Map.of("userId",user,"tenantId",tenant,"assetType",type)).retrieve().body(MAP)).get("allowed"));}
    private static Map<String,Object> required(Map<String,Object> value){if(value==null)throw new IllegalStateException("Empty monitor service response");return value;}
}
