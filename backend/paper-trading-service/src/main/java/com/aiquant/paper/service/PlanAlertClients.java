package com.aiquant.paper.service;
import com.aiquant.paper.client.SimulationDataClient.LiveContext;
import com.fasterxml.jackson.databind.JsonNode;
import java.time.Duration;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class PlanAlertClients {
 private final RestClient identity,algorithm;
 public PlanAlertClients(@Value("${IDENTITY_SERVICE_URL:http://localhost:8085}") String identityUrl,@Value("${aiquant.algorithm-base-url}") String algorithmUrl,@Value("${IDENTITY_INTERNAL_SECRET:}") String secret){
  var factory=new SimpleClientHttpRequestFactory();factory.setConnectTimeout(Duration.ofSeconds(2));factory.setReadTimeout(Duration.ofSeconds(8));
  identity=RestClient.builder().baseUrl(identityUrl).requestFactory(factory).defaultHeader("X-Identity-Service-Secret",secret).build();algorithm=RestClient.builder().baseUrl(algorithmUrl).requestFactory(factory).build();
 }
 public String authorization(UUID user,UUID tenant){try{JsonNode r=identity.post().uri("/internal/v1/identity/decision-authorization").body(Map.of("userId",user,"tenantId",tenant)).retrieve().body(JsonNode.class);return r!=null&&r.path("allowed").isBoolean()?(r.path("allowed").asBoolean()?"ALLOWED":"DENIED"):"UNKNOWN";}catch(RuntimeException e){return "UNKNOWN";}}
 public LiveContext live(String symbol){try{return algorithm.get().uri("/internal/v1/simulation/live/{symbol}",symbol).retrieve().body(LiveContext.class);}catch(RuntimeException e){return null;}}
}
