package com.aiquant.paper.client;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class SimulationDataClientQuoteTests {
    private SimulationDataClient.QuoteSnapshot quote(String status, Instant timestamp) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/api/v1/market/CJ701/quote", exchange -> {
            byte[] body = ("{\"symbol\":\"CJ701\",\"price\":6400,\"dataStatus\":\"" + status
                + "\",\"dataTimestamp\":\"" + timestamp + "\"}").getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, body.length);
            try (var out = exchange.getResponseBody()) { out.write(body); }
        });
        server.start();
        try {
            String url = "http://127.0.0.1:" + server.getAddress().getPort();
            return new SimulationDataClient(url, url, Duration.ofSeconds(2), Duration.ofSeconds(2)).quote("CJ701");
        } finally { server.stop(0); }
    }
    @Test void acceptsCurrentObservedQuote() throws Exception {
        assertEquals("CJ701", quote("FRESH", Instant.now()).symbol());
    }
    @Test void refusesCachedAndStalePricesForLiveSimulation() {
        assertThrows(IllegalStateException.class, () -> quote("DEGRADED", Instant.now()));
        assertThrows(IllegalStateException.class, () -> quote("FRESH", Instant.now().minusSeconds(600)));
        assertThrows(IllegalStateException.class, () -> quote("FRESH", Instant.now().plusSeconds(600)));
    }
}
