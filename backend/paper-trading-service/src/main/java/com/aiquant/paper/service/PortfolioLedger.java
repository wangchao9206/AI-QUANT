package com.aiquant.paper.service;

import java.math.BigDecimal;
import java.math.RoundingMode;

/** Contract-specific arithmetic; cash changes only on fills, never on symbol selection. */
final class PortfolioLedger {
    record Position(int direction,int lots,BigDecimal average) {}
    record Spec(int multiplier,BigDecimal tick,BigDecimal margin,BigDecimal commission) {}
    record Trade(Position position,BigDecimal cashChange,BigDecimal realized,BigDecimal fee,BigDecimal slippage) {}

    static BigDecimal fee(Spec spec,BigDecimal price,int quantity,BigDecimal rate) {
        return spec.commission().multiply(BigDecimal.valueOf(quantity)).max(
            price.multiply(BigDecimal.valueOf((long)quantity*spec.multiplier())).multiply(rate))
            .setScale(2,RoundingMode.HALF_UP);
    }
    static BigDecimal margin(Spec spec,BigDecimal price,int lots,BigDecimal rate) {
        return spec.margin().max(price.multiply(BigDecimal.valueOf(spec.multiplier())).multiply(rate))
            .multiply(BigDecimal.valueOf(lots)).setScale(2,RoundingMode.CEILING);
    }
    static BigDecimal pnl(Spec spec,Position position,BigDecimal price) {
        return price.subtract(position.average()).multiply(BigDecimal.valueOf(
            (long)position.direction()*position.lots()*spec.multiplier())).setScale(2,RoundingMode.HALF_UP);
    }
    static Trade trade(Spec spec,Position old,String side,String offset,int quantity,BigDecimal market,
                       BigDecimal price,BigDecimal feeRate) {
        if(quantity<=0 || price.signum()<=0 || !java.util.List.of("BUY","SELL").contains(side)
            || !java.util.List.of("OPEN","CLOSE").contains(offset))throw new IllegalArgumentException("委托参数无效");
        int direction="BUY".equals(side)?1:-1;
        Position next;
        BigDecimal realized=BigDecimal.ZERO;
        if("OPEN".equals(offset)) {
            if(old.lots()>0 && old.direction()!=direction)throw new IllegalStateException("反向开仓前必须先平掉该合约持仓");
            int lots=Math.addExact(old.lots(),quantity);
            BigDecimal average=old.average().multiply(BigDecimal.valueOf(old.lots()))
                .add(price.multiply(BigDecimal.valueOf(quantity))).divide(BigDecimal.valueOf(lots),6,RoundingMode.HALF_UP);
            next=new Position(direction,lots,average);
        } else {
            if(old.lots()==0 || old.direction()==direction || quantity>old.lots())
                throw new IllegalStateException("平仓方向或手数与该合约可用持仓不匹配");
            realized=price.subtract(old.average()).multiply(BigDecimal.valueOf((long)old.direction()*quantity*spec.multiplier()))
                .setScale(2,RoundingMode.HALF_UP);
            int lots=old.lots()-quantity;
            next=new Position(lots==0?0:old.direction(),lots,lots==0?BigDecimal.ZERO:old.average());
        }
        BigDecimal fee=fee(spec,price,quantity,feeRate);
        BigDecimal slippage=price.subtract(market).abs().multiply(BigDecimal.valueOf((long)quantity*spec.multiplier()))
            .setScale(2,RoundingMode.HALF_UP);
        return new Trade(next,realized.subtract(fee),realized,fee,slippage);
    }
}
