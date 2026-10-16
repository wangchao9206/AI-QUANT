package com.aiquant.paper.api;

import java.math.BigDecimal;
import java.time.LocalDate;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public final class PaperRequests {
    private PaperRequests() {}

    public record CreateSessionRequest(
        @NotBlank @Size(max = 80) String name,
        @NotBlank @Pattern(regexp = "LIVE|HISTORICAL") String mode,
        @NotBlank @Pattern(regexp = "[A-Za-z]{1,4}(?:0|M|[0-9]{3,4})") String symbol,
        LocalDate startDate,
        LocalDate endDate,
        @NotNull @DecimalMin("1000") @DecimalMax("1000000000") BigDecimal initialCash,
        @NotNull @DecimalMin("0.01") @DecimalMax("1") BigDecimal marginRate,
        @NotNull @DecimalMin("0") @DecimalMax("0.02") BigDecimal feeRate,
        @NotNull @DecimalMin("0") @DecimalMax("100") BigDecimal slippageTicks,
        @NotNull @DecimalMin("0.000001") @DecimalMax("1") BigDecimal maxParticipationRate,
        boolean autoRoll
    ) {}

    public record PlaceOrderRequest(
        @NotBlank @Size(min = 8, max = 128) String clientOrderId,
        @NotBlank @Pattern(regexp = "BUY|SELL") String side,
        @NotBlank @Pattern(regexp = "OPEN|CLOSE") String offset,
        @NotBlank @Pattern(regexp = "MARKET|LIMIT|STOP") String orderType,
        @Min(1) @Max(1_000_000) int quantity,
        @DecimalMin("0.000001") BigDecimal limitPrice,
        @DecimalMin("0.000001") BigDecimal stopPrice
    ) {}

    public record AdvanceRequest(@Min(1) @Max(100) int steps) {}
}
