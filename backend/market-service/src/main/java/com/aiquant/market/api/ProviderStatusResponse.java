package com.aiquant.market.api;

import java.time.Instant;

public record ProviderStatusResponse(
    String provider,
    boolean configured,
    boolean connected,
    Instant lastEventAt,
    boolean fallbackActive,
    String message
) {}
