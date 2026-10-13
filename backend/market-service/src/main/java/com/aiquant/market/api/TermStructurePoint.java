package com.aiquant.market.api;

import java.math.BigDecimal;
import java.time.LocalDate;

public record TermStructurePoint(String contract, LocalDate maturityDate, BigDecimal price) {
}
