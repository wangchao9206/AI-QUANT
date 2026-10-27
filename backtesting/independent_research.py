"""Pre-registered, isolated research. Reuses graph evaluation and the cash ledger.

This module never submits production orders or alters the existing paper engine.
"""
from collections import Counter
from dataclasses import asdict,dataclass,replace
from datetime import date
import math
import statistics

from backtesting.backtester import FuturesExecutionLedger
from backtesting.workflow import compile_workflow
from data.data_feed import KLineBar
from data.tqsdk_backtest import TqSdkBacktestDataset

ENGINE='independent-daily-research-v1'


def hypothesis(family:str,period:int=20,stop:float=2.0):
    """Fully specified causal rules, represented by the production graph DSL."""
    if family not in ('BREAKOUT','PULLBACK','REVERSION'):raise ValueError('Unknown hypothesis')
    nodes=[];edges=[]
    def node(id,type,params=None):
        nodes.append({'id':id,'type':type,'label':id,'params':params or {}});return id
    def edge(source,target,target_port,source_port='value'):
        edges.append({'id':'e'+str(len(edges)),'source':source,'sourcePort':source_port,'target':target,'targetPort':target_port})
    def indicator(id,kind,period,field='close',shift=0):
        node(id,'INDICATOR',{'kind':kind,'period':period,'field':field,'shift':shift});edge('market',id,'market','bars');return id
    def compare(id,op,left,right):
        node(id,'COMPARE',{'op':op});edge(left,id,'left');edge(right,id,'right');return id
    def combine(id,a,b):
        node(id,'LOGIC',{'op':'AND'});edge(a,id,'a','result');edge(b,id,'b','result');return id
    def action(id,kind,condition):
        node(id,'ACTION',{'action':kind});edge(condition,id,'condition','result');edge('risk',id,'risk','risk')
    node('market','MARKET');node('risk','RISK',{'lots':1,'stopLossAtr':stop,'takeProfitAtr':4})
    node('price','PRICE',{'field':'close','shift':0});edge('market','price','market','bars')
    if family!='REVERSION':
        indicator('trend','SMA',60)
        compare('trend_up','GT','price','trend');compare('trend_down','LT','price','trend')
    if family=='BREAKOUT':
        indicator('upper','HIGHEST',period,'high',1);indicator('lower','LOWEST',period,'low',1)
        indicator('exit_upper','HIGHEST',10,'high',1);indicator('exit_lower','LOWEST',10,'low',1)
        buy=compare('break_up','GT','price','upper');sell=compare('break_down','LT','price','lower')
        close_long=compare('close_long','LT','price','exit_lower');close_short=compare('close_short','GT','price','exit_upper')
    else:
        indicator('mean','SMA',period);indicator('std','STDDEV',period)
        node('z','CONSTANT',{'value':1.5});node('width','MATH',{'op':'MUL'});edge('z','width','left');edge('std','width','right')
        for id,op in [('upper','ADD'),('lower','SUB')]:
            node(id,'MATH',{'op':op});edge('mean',id,'left');edge('width',id,'right')
        buy=compare('below_band','LT','price','lower');sell=compare('above_band','GT','price','upper')
        close_long=compare('close_long','GTE','price','mean');close_short=compare('close_short','LTE','price','mean')
    if family!='REVERSION':
        buy=combine('buy_filter',buy,'trend_up');sell=combine('sell_filter',sell,'trend_down')
    action('open_long','BUY',buy);action('open_short','SELL',sell)
    action('exit_long','CLOSE_LONG',close_long);action('exit_short','CLOSE_SHORT',close_short)
    return compile_workflow({'schemaVersion':1,'nodes':nodes,'edges':edges}).definition.model_dump()


def causal_prices(dataset:TqSdkBacktestDataset):
    """Forward ratio chain at an observed roll open; old signals never revised."""
    bars=dataset.bars
    if not dataset.complete or not bars:raise ValueError('Incomplete execution evidence')
    if any(a.timestamp>=b.timestamp for a,b in zip(bars,bars[1:])):raise ValueError('Unordered bars')
    rolls={e.execution_date:e for e in dataset.roll_events}
    if len(rolls)!=len(dataset.roll_events):raise ValueError('Duplicate roll date')
    result=[];factor=1.0
    for i,b in enumerate(bars):
        if not b.contract_symbol or b.contract_symbol not in dataset.contract_specs:raise ValueError('Missing contract spec')
        if not all(math.isfinite(v) and v>0 for v in (b.open,b.high,b.low,b.close)):raise ValueError('Invalid OHLC')
        if not b.low<=min(b.open,b.close)<=max(b.open,b.close)<=b.high:raise ValueError('Invalid OHLC order')
        e=rolls.get(b.timestamp.date())
        if i and bars[i-1].contract_symbol!=b.contract_symbol:
            if not e or (e.from_contract,e.to_contract)!=(bars[i-1].contract_symbol,b.contract_symbol):
                raise ValueError('Missing observed roll legs')
            if not all(math.isfinite(v) and v>0 for v in (e.old_open,e.new_open)):raise ValueError('Invalid roll prices')
            if abs(e.new_open-b.open)>dataset.contract_specs[b.contract_symbol].price_tick+1e-8:
                raise ValueError('Roll new open disagrees with execution bar')
            factor*=e.old_open/e.new_open
        elif i and e:raise ValueError('Roll event without matching contract change')
        result.append(KLineBar(b.timestamp,b.open*factor,b.high*factor,b.low*factor,b.close*factor,
                               b.volume,b.open_interest,b.contract_symbol))
    return result


@dataclass(frozen=True)
class ResearchRisk:
    fraction:float=.005
    margin_fraction:float=.20
    max_notional:float=2.0
    margin_rate:float=.12
    participation:float=.001
    minimum_volume:int=10_000
    fee_rate:float=.0001
    slippage_ticks:float=1.0

    def __post_init__(self):
        if not 0<self.fraction<=.02 or not 0<self.margin_fraction<=1 or self.max_notional<=0:
            raise ValueError('Invalid risk budget')


def planned_lots(cash,initial,price,atr,stop,spec,risk,cost_multiplier=1):
    if cash<=0 or atr<=0:return 0,0.0
    ticks=risk.slippage_ticks*cost_multiplier
    # Both sides use the larger notional estimate, preserving a cost buffer.
    price_bound=price+stop*atr+ticks*spec.price_tick
    fee=max(spec.commission_per_lot*cost_multiplier,price_bound*spec.volume_multiple*risk.fee_rate*cost_multiplier)
    unit_risk=stop*atr*spec.volume_multiple+2*fee+2*ticks*spec.price_tick*spec.volume_multiple
    unit_margin=max(spec.margin_per_lot,price_bound*spec.volume_multiple*risk.margin_rate)
    count=min(math.floor(min(cash,initial)*risk.fraction/unit_risk),
              math.floor(cash*risk.margin_fraction/unit_margin),
              math.floor(cash*risk.max_notional/(price_bound*spec.volume_multiple)))
    return max(0,count),unit_risk


def _metrics(curve,trades,initial,fees,slippage,denials):
    equity=[initial]+[p['equity'] for p in curve]
    returns=[equity[i]/equity[i-1]-1 if equity[i-1]>0 else 0 for i in range(1,len(equity))]
    peak=initial;drawdown=0
    for value in equity:
        peak=max(peak,value);drawdown=max(drawdown,(peak-value)/peak if peak else 0)
    standard=statistics.pstdev(returns) if returns else 0
    gains=sum(max(t['netPnl'],0) for t in trades);losses=sum(max(-t['netPnl'],0) for t in trades)
    return {
        'initialCash':initial,'finalEquity':equity[-1],'netPnl':equity[-1]-initial,
        'returnPct':(equity[-1]/initial-1)*100,'maxDrawdownPct':drawdown*100,
        'sharpe':statistics.mean(returns)/standard*math.sqrt(250) if standard>0 else 0,
        'closedTrades':len(trades),'winningTrades':sum(t['netPnl']>0 for t in trades),
        'winRatePct':sum(t['netPnl']>0 for t in trades)/len(trades)*100 if trades else 0,
        'grossNetWinners':gains,'grossNetLosers':losses,
        'profitFactor':gains/losses if losses else None,
        'fees':fees,'slippageCost':slippage,
        'overBudgetExits':sum(-t['netPnl']>t['riskBudget']+1e-8 for t in trades),
        'maxLossStreak':_losing_streak(trades),'denials':dict(denials),
        'days':len(curve),'firstExecutionDate':curve[0]['date'] if curve else None,
        'lastExecutionDate':curve[-1]['date'] if curve else None,
    }


def _losing_streak(trades):
    maximum=current=0
    for t in trades:
        current=current+1 if t['netPnl']<0 else 0;maximum=max(maximum,current)
    return maximum


def simulate(dataset,definition,initial_cash,start:date,end:date,*,cost_multiplier=1,
             risk:ResearchRisk|None=None,signals=None):
    risk=risk or ResearchRisk()
    if cost_multiplier<1 or not math.isfinite(cost_multiplier):raise ValueError('Invalid costs')
    if start>end or initial_cash<=0:raise ValueError('Invalid experiment window')
    signals=signals if signals is not None else causal_prices(dataset)
    bars=dataset.bars
    if [b.timestamp for b in signals]!=[b.timestamp for b in bars]:raise ValueError('Misaligned signal clock')
    program=compile_workflow(definition);prepared=program.prepare(signals)
    stop=float(program.risk['stopLossAtr']);target=float(program.risk['takeProfitAtr'])
    specs={k:replace(v,commission_per_lot=v.commission_per_lot*cost_multiplier) for k,v in dataset.contract_specs.items()}
    ledger=FuturesExecutionLedger(initial_cash)
    rolls={e.execution_date:e for e in dataset.roll_events}
    tr=[max(b.high-b.low,abs(b.high-bars[i-1].close),abs(b.low-bars[i-1].close))
        if i and b.contract_symbol==bars[i-1].contract_symbol else b.high-b.low for i,b in enumerate(bars)]
    atrs=[sum(tr[max(0,i-13):i+1])/min(14,i+1) for i in range(len(tr))]
    indices=[i for i,b in enumerate(bars) if start<=b.timestamp.date()<=end and i>=program.required_bars]
    trades=[];curve=[];decisions=[];denials=Counter();fees=slippage=0.0;entry=None
    def close(price,bar,reason,slip=None):
        nonlocal entry,fees,slippage
        fill=ledger.close_position(market_price=price,spec=specs[ledger.contract],
            slippage_ticks=risk.slippage_ticks*cost_multiplier if slip is None else slip,
            fee_rate=risk.fee_rate*cost_multiplier)
        fees+=fill.fee;slippage+=fill.slippage_cost
        trades.append({**entry,'exitDate':bar.timestamp.date().isoformat(),'exitReason':reason,
            'exitPrice':fill.price,'netPnl':fill.trade_net_pnl,'rMultiple':fill.trade_net_pnl/entry['plannedRisk'],
            'closingFee':fill.fee,'contract':fill.contract})
        entry=None
    for i in indices:
        b,previous=bars[i],bars[i-1]
        observed=prepared.evaluate(i-1,ledger.direction,symbol=dataset.symbol)
        if observed.signal not in ('HOLD','WARMING'):
            decisions.append({'signalDate':previous.timestamp.date().isoformat(),'executionDate':b.timestamp.date().isoformat(),
                'signal':observed.signal,'reason':observed.reason})
        roll=rolls.get(b.timestamp.date())
        if ledger.direction and roll:
            if ledger.contract!=roll.from_contract:raise ValueError('Holding contract disagrees with roll')
            close(roll.old_open,b,'ROLL_EXIT')
        elif ledger.direction:
            if ledger.contract!=b.contract_symbol:raise ValueError('Position lost delivery identity')
            if observed.signal=='FLATTEN':close(b.open,b,'SIGNAL_EXIT')
        if not ledger.direction and observed.signal in ('BUY','SELL'):
            if roll:denials['ROLL_DAY_NEW_ORDER_CANCELLED']+=1
            elif previous.volume<risk.minimum_volume or b.volume<=0:denials['LIQUIDITY']+=1
            else:
                spec=dataset.contract_specs[b.contract_symbol]
                planned,unit_risk=planned_lots(ledger.cash,initial_cash,previous.close,atrs[i-1],stop,spec,risk,cost_multiplier)
                actual,actual_unit=planned_lots(ledger.cash,initial_cash,b.open,atrs[i-1],stop,spec,risk,cost_multiplier)
                lots=min(planned,actual,math.floor(previous.volume*risk.participation))
                if lots<1:denials['RISK_OR_MARGIN_BELOW_ONE_LOT']+=1
                else:
                    budget=min(ledger.cash,initial_cash)*risk.fraction
                    fill=ledger.open_position(direction=1 if observed.signal=='BUY' else -1,contract=b.contract_symbol,
                        market_price=b.open,spec=specs[b.contract_symbol],margin_rate=risk.margin_rate,
                        margin_budget_ratio=risk.margin_fraction,target_leverage=risk.max_notional,
                        slippage_ticks=risk.slippage_ticks*cost_multiplier,fee_rate=risk.fee_rate*cost_multiplier,fixed_lots=lots)
                    if fill.lots!=lots:raise AssertionError('Sizing disagrees with ledger affordability')
                    fees+=fill.fee;slippage+=fill.slippage_cost
                    entry={'signalDate':previous.timestamp.date().isoformat(),'entryDate':b.timestamp.date().isoformat(),
                        'entryPrice':fill.price,'lots':lots,'direction':ledger.direction,'atr':atrs[i-1],
                        'plannedRisk':max(unit_risk,actual_unit)*lots,'riskBudget':budget,'openingFee':fill.fee}
                    assert entry['plannedRisk']<=budget+1e-7
        if ledger.direction:
            tick=specs[ledger.contract].price_tick
            raw_stop=ledger.entry_price-ledger.direction*stop*entry['atr']
            raw_target=ledger.entry_price+ledger.direction*target*entry['atr']
            # Protection rounds towards entry; profit limit rounds away from entry.
            stop_price=(math.ceil(raw_stop/tick-1e-12) if ledger.direction>0 else math.floor(raw_stop/tick+1e-12))*tick
            target_price=(math.ceil(raw_target/tick-1e-12) if ledger.direction>0 else math.floor(raw_target/tick+1e-12))*tick
            stopped=b.low<=stop_price if ledger.direction>0 else b.high>=stop_price
            profited=b.high>=target_price if ledger.direction>0 else b.low<=target_price
            if stopped:
                price=min(b.open,stop_price) if ledger.direction>0 else max(b.open,stop_price)
                close(price,b,'STOP')
            elif profited:
                # Resting profit limit: improve to an advantageous gap open; no adverse limit fill.
                price=max(b.open,target_price) if ledger.direction>0 else min(b.open,target_price)
                # Favorable opening gaps precede any stop touch on carried positions. To preserve
                # the pre-registered conservative daily path, stop still has priority above.
                close(price,b,'TARGET',slip=0)
        if ledger.direction:
            marked=ledger.equity(b.close,specs[ledger.contract])
            if marked<=ledger.margin_occupied(b.close,specs[ledger.contract],risk.margin_rate):
                close(b.close,b,'MARGIN_LIQUIDATION')
        if i==indices[-1] and ledger.direction:close(b.close,b,'WINDOW_END_LIQUIDATION')
        equity=ledger.equity(b.close,specs[b.contract_symbol])
        curve.append({'date':b.timestamp.date().isoformat(),'equity':equity,'direction':ledger.direction,'lots':ledger.lots})
        if equity<=0:
            denials['BANKRUPTCY_STOP']+=1;break
    metrics=_metrics(curve,trades,initial_cash,fees,slippage,denials)
    # Ledger accounting invariant: all windows finish flat and include both fees.
    if abs(metrics['netPnl']-sum(t['netPnl'] for t in trades))>1e-5:
        raise AssertionError('Closed trade PnL does not reconcile with cash')
    return {'engineVersion':ENGINE,'metrics':metrics,'trades':trades,'curve':curve,'decisions':decisions}
