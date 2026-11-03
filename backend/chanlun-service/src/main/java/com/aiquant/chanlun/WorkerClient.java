package com.aiquant.chanlun;

import com.fasterxml.jackson.databind.JsonNode;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class WorkerClient {
    private final Map<String,String> urls;
    private final RestClient client;
    private final RestClient healthClient;
    public WorkerClient(@Value("${chanlun.workers.native}") String nativeUrl,
                        @Value("${chanlun.workers.chanpy}") String chanpy,
                        @Value("${chanlun.workers.czsc}") String czsc,
                        @Value("${chanlun.workers.baseline}") String baseline) {
        urls=Map.of("native",nativeUrl,"chanpy",chanpy,"czsc",czsc,"baseline",baseline);
        var http=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
        var factory=new JdkClientHttpRequestFactory(http);factory.setReadTimeout(Duration.ofSeconds(90));
        client=RestClient.builder().requestFactory(factory).build();
        var healthFactory=new JdkClientHttpRequestFactory(http);healthFactory.setReadTimeout(Duration.ofSeconds(2));
        healthClient=RestClient.builder().requestFactory(healthFactory).build();
    }
    public JsonNode health(String engine) {
        return healthClient.get().uri(urls.get(engine)+"/health").retrieve().body(JsonNode.class);
    }
    public JsonNode analyze(String engine,String dataset,int count) {
        if(!urls.containsKey(engine))throw new IllegalArgumentException("该引擎尚未启用");
        return client.post().uri(urls.get(engine)+"/internal/v1/analyze")
            .body(Map.of("datasetId",dataset,"observedBars",count)).retrieve().body(JsonNode.class);
    }
}
