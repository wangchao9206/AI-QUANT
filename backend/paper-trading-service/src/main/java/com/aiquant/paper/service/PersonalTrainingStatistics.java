package com.aiquant.paper.service;
import java.util.*;

/** Descriptive statistics only. Partial closes are not counted as independent trades. */
public final class PersonalTrainingStatistics {
    private PersonalTrainingStatistics() {}
    public record Fill(String offset,int quantity,double realizedPnl,double fee,Double riskBudget) {}
    public static Map<String,Object> calculate(double initialCash,List<Double> equities,List<Fill> fills) {
        double peak=initialCash,maxDrawdown=0,net=0,closedNet=0,budget=0;
        int lots=0,completed=0,wins=0,overBudget=0;
        for(double equity:equities) {
            peak=Math.max(peak,equity);
            if(peak>0)maxDrawdown=Math.max(maxDrawdown,100*(1-equity/peak));
        }
        for(var f:fills) {
            if("OPEN".equals(f.offset())) {
                if(lots==0){net=0;budget=f.riskBudget()==null?Double.NaN:f.riskBudget();}
                lots+=f.quantity();net-=f.fee();
            } else {
                if(f.quantity()>lots)throw new IllegalStateException("成交配对无法核对，保留原始记录，禁止生成失真的交易统计");
                lots-=f.quantity();net+=f.realizedPnl()-f.fee();
                if(lots==0){completed++;closedNet+=net;if(net>0)wins++;if(Double.isFinite(budget)&&-net>budget+.005)overBudget++;}
            }
        }
        var result=new LinkedHashMap<String,Object>();result.put("closedTradeCount",completed);result.put("winningTradeCount",wins);
        result.put("closedNetPnl",Math.round(closedNet*100)/100.0);result.put("maxDrawdownPct",Math.round(maxDrawdown*10000)/10000.0);
        result.put("lossBeyondBudgetCount",overBudget);result.put("winRatePct",completed>0?100.0*wins/completed:null);
        result.put("validationStatus",completed<20?"INSUFFICIENT_SAMPLE":"DESCRIPTIVE_ONLY");return result;
    }
}
