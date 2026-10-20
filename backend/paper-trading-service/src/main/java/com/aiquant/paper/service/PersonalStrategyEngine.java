package com.aiquant.paper.service;

import com.aiquant.paper.client.SimulationDataClient.HistoricalBar;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.temporal.TemporalAdjusters;
import java.util.*;

/** Versioned, causal daily strategy. Indicators use past observed roll legs;
 * execution and protection always use the unadjusted delivery-contract prices. */
public final class PersonalStrategyEngine {
    public static final String ENGINE = "SURVIVAL_RETEST_1.0";
    private static final ZoneId SHANGHAI = ZoneId.of("Asia/Shanghai");

    public record Rules(double riskPct, double maxMarginPct, double volumeRatio,
                        double maxStopAtr, int cooldownBars) {
        public static Rules defaults() { return new Rules(.5,20,1.5,2,3); }
        public void validate() {
            if (!Double.isFinite(riskPct) || riskPct<.1 || riskPct>1
                || !Double.isFinite(maxMarginPct) || maxMarginPct<5 || maxMarginPct>25
                || !Double.isFinite(volumeRatio) || volumeRatio<1.2 || volumeRatio>3
                || !Double.isFinite(maxStopAtr) || maxStopAtr<1 || maxStopAtr>3
                || cooldownBars<2 || cooldownBars>10)
                throw new IllegalArgumentException("风险0.1–1%、保证金5–25%、放量1.2–3倍、止损1–3ATR、冷静期2–10根日线");
        }
    }
    public record Roll(LocalDate date, double oldOpen, double newOpen) {}
    public record Account(double equity,double initialCash,int lots,int direction,double averagePrice,
                          double tick,int multiplier,double marginPerLot,double commissionPerLot,
                          double marginRate,double feeRate,double slippageTicks,
                          Double stopPrice,Integer entryBar,Integer lastExitBar,int entriesThisWeek,
                          boolean halted) {}
    public record Plan(String state,String action,int direction,double entryPrice,Double stopPrice,
                       int maxLots,double riskBudget,double plannedRisk,Double atr,Double ma20,Double ma60,
                       Double weeklyMa10,Double boxLevel,Double volumeRatio,List<String> reasons) {}
    private record Bar(LocalDate date,String contract,double open,double high,double low,double close,long volume) {}

    public Plan evaluate(List<HistoricalBar> visible,List<Roll> knownRolls,Account a,Rules rules) {
        rules.validate();
        if (visible.isEmpty()) return waitFor("WARMUP","缺少已完成日线");
        var sorted=visible.stream().sorted(Comparator.comparing(HistoricalBar::timestamp)).toList();
        LocalDate clock=LocalDate.ofInstant(sorted.get(sorted.size()-1).timestamp(),SHANGHAI);
        var bars=new ArrayList<Bar>();
        for (var raw:sorted) {
            LocalDate date=LocalDate.ofInstant(raw.timestamp(),SHANGHAI);
            double adjustment=knownRolls.stream().filter(r->r.date().isAfter(date)&&!r.date().isAfter(clock))
                .mapToDouble(r->r.newOpen()-r.oldOpen()).sum();
            bars.add(new Bar(date,raw.contract(),raw.open().doubleValue()+adjustment,
                raw.high().doubleValue()+adjustment,raw.low().doubleValue()+adjustment,
                raw.close().doubleValue()+adjustment,raw.volume()));
        }
        // Unknown roll evidence makes the technical history ineligible.
        for(int i=1;i<bars.size();i++) if(!bars.get(i).contract().equals(bars.get(i-1).contract())) {
            final LocalDate date=bars.get(i).date();
            if(knownRolls.stream().noneMatch(r->r.date().equals(date))) return waitFor("WARMUP","换月双腿证据缺失，禁止把价差当成突破");
        }
        int n=bars.size(), t=n-1;
        if(n<66) return waitFor("WARMUP","至少需要66根已完成日线，预热期不计交易成绩");
        double atr=atr(bars,t),ma20=ma(bars,t,20),ma60=ma(bars,t,60),close=bars.get(t).close();
        if(!(atr>0) || !(a.equity()>0)) return waitFor("BLOCKED","波动率或账户净值不满足训练要求");
        var weekly=new TreeMap<LocalDate,Double>();
        LocalDate thisWeek=week(clock);
        for(var b:bars) if(week(b.date()).isBefore(thisWeek)) weekly.put(week(b.date()),b.close());
        var w=new ArrayList<>(weekly.values());
        if(w.size()<11) return waitFor("WARMUP","至少需要11个已结束自然周；当前周即使周五也保守排除");
        double w10=w.subList(w.size()-10,w.size()).stream().mapToDouble(Double::doubleValue).average().orElseThrow();
        double wPrev=w.subList(w.size()-11,w.size()-1).stream().mapToDouble(Double::doubleValue).average().orElseThrow();
        double wClose=w.get(w.size()-1);
        int direction=close>ma60&&ma20>ma60&&ma60>ma(bars,t-5,60)&&wClose>w10&&w10>wPrev ? 1
            :close<ma60&&ma20<ma60&&ma60<ma(bars,t-5,60)&&wClose<w10&&w10<wPrev ? -1:0;
        double riskBudget=Math.max(0,Math.min(a.equity(),a.initialCash())*rules.riskPct()/100);
        if(a.lots()>0) {
            boolean exit=a.halted() || (a.direction()>0 ? close<ma20&&bars.get(t-1).close()<ma(bars,t-1,20)
                :close>ma20&&bars.get(t-1).close()>ma(bars,t-1,20));
            // Caller supplies bars beginning at index zero, so entryBar is causal.
            int from=Math.min(t,Math.max(0,a.entryBar()==null?t:a.entryBar()));
            double extreme=a.direction()>0?bars.subList(from,n).stream().mapToDouble(Bar::high).max().orElse(close)
                :bars.subList(from,n).stream().mapToDouble(Bar::low).min().orElse(close);
            double candidate=extreme-a.direction()*3*atr;
            double previous=a.stopPrice()==null?candidate:a.stopPrice();
            double stop=a.direction()>0?Math.max(previous,candidate):Math.min(previous,candidate);
            stop=round(stop,a.tick(),a.direction()>0?RoundingMode.FLOOR:RoundingMode.CEILING);
            if(stop<=0) return waitFor("BLOCKED","保护价非法，需暂停核对合约数据");
            return new Plan(exit?"EXIT":"HOLD",exit?"EXIT":"HOLD",a.direction(),close,stop,0,riskBudget,0,
                atr,ma20,ma60,w10,null,null,List.of(exit?"回撤熔断或连续两日收盘越过MA20，下一日开盘退出":"保留趋势持仓；只收紧3ATR保护，不因小波动反复交易"));
        }
        if(a.halted()) return waitFor("HALTED","净值自历史峰值回撤达到8%，本轮禁止再开仓；先复盘，再开独立新版本试验");
        if(a.lastExitBar()!=null && t-a.lastExitBar()<=rules.cooldownBars())
            return waitFor("COOLDOWN","退出后等待"+rules.cooldownBars()+"根完整日线，禁止立即追回亏损");
        if(a.entriesThisWeek()>=2) return waitFor("COOLDOWN","本自然周已开仓两次，停止增加交易频率");
        if(direction==0) return waitFor("WAIT_TREND","周线与MA20/60未同向，空仓本身是合格决策");
        for(int b=t-1;b>=Math.max(65,t-8);b--) {
            if(a.lastExitBar()!=null && b<=a.lastExitBar()) continue;
            var breakout=bars.get(b);
            if(knownRolls.stream().anyMatch(r->!r.date().isBefore(breakout.date())&&!r.date().isAfter(clock))) continue;
            double boundary=direction>0?bars.subList(b-20,b).stream().mapToDouble(Bar::high).max().orElseThrow()
                :bars.subList(b-20,b).stream().mapToDouble(Bar::low).min().orElseThrow();
            double breakoutAtr=atr(bars,b);
            double meanVolume=bars.subList(b-20,b).stream().mapToLong(Bar::volume).average().orElse(0);
            double vr=meanVolume>0?breakout.volume()/meanVolume:0;
            double ma5=ma(bars,b-1,5),ma10=ma(bars,b-1,10),m20=ma(bars,b-1,20);
            if(Math.max(ma5,Math.max(ma10,m20))-Math.min(ma5,Math.min(ma10,m20))>atr(bars,b-1)) continue;
            if(direction*(breakout.close()-boundary)<.1*breakoutAtr || vr<rules.volumeRatio()) continue;
            boolean failed=false;
            for(int j=b+1;j<=t;j++) if(direction*(bars.get(j).close()-boundary)<-.35*breakoutAtr) failed=true;
            if(failed) continue;
            var last=bars.get(t);
            boolean touched=direction>0?last.low()<=boundary+.35*breakoutAtr:last.high()>=boundary-.35*breakoutAtr;
            if(!touched || direction*(last.close()-last.open())<=0 || direction*(close-boundary)<.1*breakoutAtr) continue;
            double entry=round(close+direction*.25*atr,a.tick(),direction>0?RoundingMode.FLOOR:RoundingMode.CEILING);
            double structural=direction>0?bars.subList(b+1,n).stream().mapToDouble(Bar::low).min().orElseThrow()
                :bars.subList(b+1,n).stream().mapToDouble(Bar::high).max().orElseThrow();
            double stop=round(structural-direction*.2*atr,a.tick(),direction>0?RoundingMode.FLOOR:RoundingMode.CEILING);
            double distance=direction*(entry-stop);
            if(stop<=0||distance<a.tick()||distance>rules.maxStopAtr()*atr)
                return waitFor("STOP_TOO_FAR","结构止损超过距离上限，放弃入场；不把止损硬挪近来凑手数");
            double fee=2*Math.max(a.commissionPerLot(),entry*a.multiplier()*a.feeRate());
            double unitRisk=distance*a.multiplier()+fee+2*a.tick()*a.slippageTicks()*a.multiplier();
            double margin=Math.max(a.marginPerLot(),entry*a.multiplier()*a.marginRate());
            int lots=(int)Math.max(0,Math.min(Math.floor(riskBudget/unitRisk),Math.min(
                Math.floor(a.equity()*rules.maxMarginPct()/100/(margin+fee)),Math.floor(a.equity()*2/(entry*a.multiplier())))));
            return new Plan(lots>0?"ENTRY":"NO_SIZE",lots>0?"ENTER":"WAIT",direction,entry,stop,lots,riskBudget,lots*unitRisk,
                atr,ma20,ma60,w10,boundary,vr,List.of("周线与日线趋势同向；突破前MA5/10/20离散度≤1ATR",
                    "前20日箱体突破，成交量≥"+rules.volumeRatio()+"倍前20日均量；1–8日内回踩守住并收复",
                    lots>0?"下一日限价执行，仅当日有效；跳空越过止损或预算超限则拒绝":"风险、保证金或2倍名义敞口上限不足一手，保持空仓"));
        }
        return new Plan("WAIT_RETEST","WAIT",direction,close,null,0,riskBudget,0,atr,ma20,ma60,w10,null,null,
            List.of("方向已有条件，但收齐、放量突破或回踩确认尚不齐全，不预测顶部和底部"));
    }
    private Plan waitFor(String state,String reason) {
        return new Plan(state,"WAIT",0,0,null,0,0,0,null,null,null,null,null,null,List.of(reason));
    }
    private static double ma(List<Bar> b,int t,int len) {
        return b.subList(t-len+1,t+1).stream().mapToDouble(Bar::close).average().orElseThrow();
    }
    private static double atr(List<Bar> b,int t) {
        double total=0;
        for(int j=t-13;j<=t;j++) {var x=b.get(j);double prev=b.get(j-1).close();total+=Math.max(x.high()-x.low(),Math.max(Math.abs(x.high()-prev),Math.abs(x.low()-prev)));}
        return total/14;
    }
    public static LocalDate week(LocalDate date) {return date.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));}
    private static double round(double price,double tick,RoundingMode mode) {
        return BigDecimal.valueOf(price).divide(BigDecimal.valueOf(tick),0,mode).multiply(BigDecimal.valueOf(tick)).doubleValue();
    }
}
