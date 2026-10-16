package com.aiquant.paper.service;

import java.math.BigDecimal;
import java.math.RoundingMode;

import org.springframework.stereotype.Component;

@Component
public class MatchingEngine {
    public FillDecision match(OrderView order, BarView bar, BigDecimal tick, BigDecimal slippageTicks,
                              BigDecimal maxParticipationRate) {
        BigDecimal marketPrice;
        boolean addSlippage;
        switch (order.orderType()) {
            case "MARKET" -> {
                marketPrice = bar.open();
                addSlippage = true;
            }
            case "LIMIT" -> {
                if (order.side().equals("BUY")) {
                    if (bar.low().compareTo(order.limitPrice()) > 0) return FillDecision.noFill();
                    marketPrice = bar.open().min(order.limitPrice());
                } else {
                    if (bar.high().compareTo(order.limitPrice()) < 0) return FillDecision.noFill();
                    marketPrice = bar.open().max(order.limitPrice());
                }
                addSlippage = false;
            }
            case "STOP" -> {
                if (order.side().equals("BUY")) {
                    if (bar.high().compareTo(order.stopPrice()) < 0) return FillDecision.noFill();
                    marketPrice = bar.open().max(order.stopPrice());
                } else {
                    if (bar.low().compareTo(order.stopPrice()) > 0) return FillDecision.noFill();
                    marketPrice = bar.open().min(order.stopPrice());
                }
                addSlippage = true;
            }
            default -> throw new IllegalArgumentException("不支持的委托类型");
        }

        long volumeCapacity = BigDecimal.valueOf(bar.volume())
            .multiply(maxParticipationRate)
            .setScale(0, RoundingMode.FLOOR)
            .longValue();
        if (bar.volume() > 0 && volumeCapacity == 0) volumeCapacity = 1;
        if (volumeCapacity <= 0) return FillDecision.noFill();
        int quantity = (int) Math.min(order.remainingQuantity(), Math.min(Integer.MAX_VALUE, volumeCapacity));
        if (quantity <= 0) return FillDecision.noFill();

        BigDecimal fillPrice = marketPrice;
        if (addSlippage && slippageTicks.signum() > 0) {
            BigDecimal adverse = tick.multiply(slippageTicks);
            fillPrice = order.side().equals("BUY") ? marketPrice.add(adverse) : marketPrice.subtract(adverse);
        }
        fillPrice = roundAdverse(fillPrice, tick, order.side());
        return new FillDecision(true, marketPrice, fillPrice, quantity);
    }

    private BigDecimal roundAdverse(BigDecimal price, BigDecimal tick, String side) {
        BigDecimal ticks = price.divide(tick, 0, side.equals("BUY") ? RoundingMode.CEILING : RoundingMode.FLOOR);
        return ticks.multiply(tick);
    }

    public record OrderView(
        String side,
        String orderType,
        int remainingQuantity,
        BigDecimal limitPrice,
        BigDecimal stopPrice
    ) {}

    public record BarView(BigDecimal open, BigDecimal high, BigDecimal low, BigDecimal close, long volume) {}

    public record FillDecision(boolean fillable, BigDecimal marketPrice, BigDecimal fillPrice, int quantity) {
        public static FillDecision noFill() {
            return new FillDecision(false, null, null, 0);
        }
    }
}
