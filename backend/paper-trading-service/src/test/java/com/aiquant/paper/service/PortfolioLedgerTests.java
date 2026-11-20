package com.aiquant.paper.service;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class PortfolioLedgerTests {
    BigDecimal d(String value){return new BigDecimal(value);}
    void money(String expected,BigDecimal actual){assertEquals(0,d(expected).compareTo(actual));}
    @Test void shortProfitUsesTheContractMultiplierAndSlippageIsNotDeductedTwice() {
        var spec=new PortfolioLedger.Spec(20,d("1"),d("2000"),d("6"));
        var open=PortfolioLedger.trade(spec,new PortfolioLedger.Position(0,0,BigDecimal.ZERO),"SELL","OPEN",1,d("900"),d("899"),BigDecimal.ZERO);
        money("-6",open.cashChange());money("20",open.slippage());
        var close=PortfolioLedger.trade(spec,open.position(),"BUY","CLOSE",1,d("888"),d("889"),BigDecimal.ZERO);
        money("200",close.realized());money("194",close.cashChange());
        assertEquals(0,close.position().lots());money("188",open.cashChange().add(close.cashChange()));
    }
    @Test void weightedAveragePartialCloseAndRateFeesAreContractSpecific() {
        var spec=new PortfolioLedger.Spec(60,d("0.5"),d("1000"),d("3"));
        var add=PortfolioLedger.trade(spec,new PortfolioLedger.Position(1,1,d("100")),"BUY","OPEN",2,d("103"),d("103"),d("0.001"));
        money("102",add.position().average());money("12.36",add.fee());
        var close=PortfolioLedger.trade(spec,add.position(),"SELL","CLOSE",1,d("105"),d("104.5"),BigDecimal.ZERO);
        money("150",close.realized());assertEquals(2,close.position().lots());money("102",close.position().average());
        money("150",PortfolioLedger.pnl(spec,close.position(),d("103.25")));
        assertThrows(IllegalStateException.class,()->PortfolioLedger.trade(spec,close.position(),"SELL","OPEN",1,d("105"),d("105"),BigDecimal.ZERO));
    }
}
