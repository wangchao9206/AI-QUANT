package com.aiquant.gateway;
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.prometheusmetrics.PrometheusConfig;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.http.*;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.reactive.function.client.*;
import reactor.core.publisher.Mono;
class IdentityFilterTests {
    String secret="test-internal-secret-at-least-32-characters";
    @Test void identity_metrics_coexist_with_gateway_metrics_and_keep_active_timers(){
        var meters=new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);
        try{
            meters.config().onMeterRegistrationFailed((id,reason)->{throw new AssertionError(reason);});
            LongTaskTimer.builder("http.client.requests.active").tags("http.method","GET","spring.cloud.gateway.route.id","market").register(meters);
            var observations=ObservationRegistry.create();
            observations.observationConfig().observationHandler(new DefaultMeterObservationHandler(meters));
            var builder=WebClient.builder().observationRegistry(observations).exchangeFunction(req->Mono.just(ClientResponse.create(HttpStatus.OK)
                .header("Content-Type","application/json").body("{\"identity\":\"verified\"}").build()));
            var filter=new IdentityFilter(builder,"http://identity.test",secret);
            filter.filter(MockServerWebExchange.from(MockServerHttpRequest.get("/api/v1/market/provider")),next->Mono.empty()).block();
            assertEquals(1,meters.get("aiquant.identity.client.requests").timer().count());
            assertEquals(0,meters.get("aiquant.identity.client.requests.active").longTaskTimer().activeTasks());
            assertNotNull(meters.get("http.client.requests.active").longTaskTimer());
        }finally{meters.close();}
    }
    @Test void replaces_spoofed_context_with_online_authenticated_identity(){
        var builder=WebClient.builder().exchangeFunction(req->Mono.just(ClientResponse.create(HttpStatus.OK).header("Content-Type","application/json").body("{\"identity\":\"verified-context\"}").build()));
        var filter=new IdentityFilter(builder,"http://identity.test",secret);
        var exchange=MockServerWebExchange.from(MockServerHttpRequest.get("/api/v1/paper/sessions").header("X-Aiquant-Identity","forged").header("X-Identity-Service-Secret","client-controlled"));
        filter.filter(exchange,next->{assertEquals("verified-context",next.getRequest().getHeaders().getFirst("X-Aiquant-Identity"));assertNull(next.getRequest().getHeaders().getFirst("X-Identity-Service-Secret"));return Mono.empty();}).block();
    }
    @Test void fails_closed_on_invalid_login_or_identity_outage(){
        for(boolean outage:new boolean[]{false,true}){
            var filter=new IdentityFilter(WebClient.builder().exchangeFunction(req->outage?Mono.error(new IllegalStateException()):Mono.just(ClientResponse.create(HttpStatus.UNAUTHORIZED).header("Content-Type","application/json").body("{\"message\":\"expired\"}").build())),"http://identity.test",secret);
            var called=new AtomicBoolean();var exchange=MockServerWebExchange.from(MockServerHttpRequest.get("/api/v1/options/catalog"));
            filter.filter(exchange,next->{called.set(true);return Mono.empty();}).block();assertFalse(called.get());assertEquals(outage?HttpStatus.SERVICE_UNAVAILABLE:HttpStatus.UNAUTHORIZED,exchange.getResponse().getStatusCode());
        }
    }
    @Test void account_routes_still_strip_untrusted_context(){
        var filter=new IdentityFilter(WebClient.builder().exchangeFunction(req->Mono.error(new AssertionError("Auth route must not introspect"))),"http://identity.test",secret);
        var exchange=MockServerWebExchange.from(MockServerHttpRequest.post("/api/v1/auth/login").header("X-Aiquant-Identity","forged"));
        filter.filter(exchange,next->{assertNull(next.getRequest().getHeaders().getFirst("X-Aiquant-Identity"));return Mono.empty();}).block();
    }
    @Test void introspection_timeout_does_not_shorten_business_request_timeout(){
        var filter=new IdentityFilter(WebClient.builder().exchangeFunction(req->Mono.just(ClientResponse.create(HttpStatus.OK).header("Content-Type","application/json").body("{\"identity\":\"verified\"}").build())),"http://identity.test",secret);
        var exchange=MockServerWebExchange.from(MockServerHttpRequest.post("/api/v1/backtest/run"));
        filter.filter(exchange,next->Mono.delay(Duration.ofMillis(5100)).then()).block(Duration.ofSeconds(8));assertNull(exchange.getResponse().getStatusCode());
    }
}
