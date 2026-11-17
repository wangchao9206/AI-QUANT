"""Completed-daily MACD direction gate on causal minute MA20, without reversal."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, time
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.backtest_fg701_intraday import summarize,write_csv
from scripts.backtest_fg701_ma20 import prepare_ma20
from scripts.fg701_daily_macd import daily_macd,bind_daily_filter,verify_daily_overlap,current_contract_daily


def simulate_macd_filtered(bars,tick=1,multiple=20,fee=6,slippage=1,stop_ticks=10,exit_ticks=3,path='HIGH_FIRST'):
    if path not in ('HIGH_FIRST','LOW_FIRST'):
        raise ValueError('Unknown OHLC path')
    if tick<=0 or multiple<=0 or fee<0 or not 0<=slippage<stop_ticks or exit_ticks<=0:
        raise ValueError('Invalid execution parameters')
    trades,curve,events,rejected=[],[],[],[]
    position,pending,day,balance=None,None,None,0.0
    waiting,anchor,last_exit=False,None,None

    def reject(b,action,stage):
        nonlocal waiting,anchor,pending
        rejected.append({'tradingDay':day,'timestamp':b['timestamp'].isoformat(),'stage':stage,
                         'intendedSide':action['side'],'allowedSide':b['allowedSide'],
                         'reason':action['reason'],'dailySourceDay':b['dailySourceDay'],
                         'crossFromDelta':action.get('crossFromDelta'),'crossToDelta':action.get('crossToDelta')})
        waiting,anchor,pending=True,b['close']-b['mean'] if b['mean'] is not None else None,None

    def consider_entry(b,action):
        nonlocal pending
        if action['side']==b['allowedSide']:
            pending=action
        else:
            reject(b,action,'SIGNAL')

    def fill_event(b,reference,buy,kind,phase,reason,trade_id):
        event={'sequence':len(events)+1,'tradeId':trade_id,'tradingDay':day,
               'timestamp':b['timestamp'].isoformat(),'timestampPrecision':'MINUTE',
               'phase':phase,'kind':kind,'buy':buy,'referencePrice':reference,
               'price':reference+(1 if buy else -1)*slippage*tick,'lots':1,'fee':fee,'reason':reason,
               'allowedSide':b['allowedSide'],'dailySourceDay':b['dailySourceDay']}
        events.append(event)
        return event

    def enter(b,action):
        nonlocal position,waiting,anchor
        side=action['side']
        event=fill_event(b,b['open'],side==1,'OPEN','OPEN',action['reason'],len(trades)+1)
        position={'tradeId':len(trades)+1,'tradingDay':day,'side':side,'lots':1,
                  'entryTime':b['timestamp'].isoformat(),'signalTime':action['signalTime'],
                  'entryReason':action['reason'],'entryPhase':'OPEN','entrySequence':event['sequence'],
                  'entryReference':b['open'],'entryPrice':event['price'],
                  'stopPrice':event['price']-side*stop_ticks*tick,
                  'crossFromDelta':action.get('crossFromDelta'),'crossToDelta':action.get('crossToDelta'),
                  'previousExitTime':last_exit if action['reason']=='CROSS_AFTER_EXIT' else None,
                  'dailySourceDay':b['dailySourceDay'],'dailyDIF':b['dailyDIF'],'dailyDEA':b['dailyDEA'],
                  'dailyMACD':b['dailyMACD'],'dailyAvailableAt':b['dailyAvailableAt'],'allowedSide':b['allowedSide']}
        waiting,anchor=False,None

    def close(b,reference,reason,phase):
        nonlocal position,balance,waiting,anchor,pending,last_exit
        old=position
        event=fill_event(b,reference,old['side']==-1,'CLOSE',phase,reason,old['tradeId'])
        net=old['side']*(event['price']-old['entryPrice'])*multiple-2*fee
        balance+=net
        trades.append({**old,'exitTime':b['timestamp'].isoformat(),'exitPhase':phase,'exitSequence':event['sequence'],
                       'exitReference':reference,'exitPrice':event['price'],'exitReason':reason,
                       'grossPnl':old['side']*(reference-old['entryReference'])*multiple,
                       'fees':2*fee,'slippageCost':2*slippage*tick*multiple,'netPnl':net,
                       'holdingMinutes':(b['timestamp']-datetime.fromisoformat(old['entryTime'])).total_seconds()/60,
                       'cumulativeNetPnl':balance})
        position,pending,waiting,anchor,last_exit=None,None,True,None,b['timestamp'].isoformat()

    for b in bars:
        if b['allowedSide'] not in (-1,0,1):
            raise ValueError('Invalid daily direction filter')
        stamp,m,traded=b['timestamp'],b['mean'],b['volume']>0
        if day!=b['tradingDay']:
            if position:
                raise ValueError('Missing daily liquidation')
            day,pending,waiting,anchor,last_exit=b['tradingDay'],None,False,None,None
        clock=stamp.time().replace(tzinfo=None)
        cutoff=time(14,58)<=clock<time(18)
        liquidate=time(14,59)<=clock<time(18)
        if liquidate:
            if position:
                if not traded:
                    raise ValueError('No liquidation volume')
                close(b,b['open'],'DAY_END','OPEN')
            pending=None
        elif traded:
            if position and position['side']*(b['open']-position['stopPrice'])<=0:
                close(b,b['open'],'STOP_GAP','OPEN')
            elif pending:
                action,pending=pending,None
                if action['kind']=='EXIT' and position:
                    close(b,b['open'],'MEAN_REVERSAL','OPEN')
                elif action['kind']=='ENTRY' and not position and not cutoff:
                    if action['side']==b['allowedSide']:
                        enter(b,action)
                    else:
                        reject(b,action,'FILL')
            route=[b['open'],b['high'],b['low'],b['close']] if path=='HIGH_FIRST' else [b['open'],b['low'],b['high'],b['close']]
            for segment,(start,finish) in enumerate(zip(route,route[1:]),1):
                if not position:
                    break
                side,level=position['side'],position['stopPrice']
                hit=(side==1 and finish<=level<=start) or (side==-1 and start<=level<=finish)
                if hit:
                    close(b,level,'STOP',f'SEGMENT_{segment}')
        if not cutoff and traded and m is not None:
            delta=b['close']-m
            if position:
                if position['side']*delta<=-exit_ticks*tick+1e-9:
                    pending={'kind':'EXIT','signalTime':stamp.isoformat()}
            elif waiting:
                side=1 if anchor is not None and anchor<=0 and delta>0 else -1 if anchor is not None and anchor>=0 and delta<0 else 0
                if side:
                    consider_entry(b,{'kind':'ENTRY','side':side,'reason':'CROSS_AFTER_EXIT' if last_exit else 'CROSS_AFTER_FILTER',
                                      'signalTime':stamp.isoformat(),'crossFromDelta':anchor,'crossToDelta':delta})
                anchor=delta
            elif abs(delta)>1e-9:
                consider_entry(b,{'kind':'ENTRY','side':1 if delta>0 else -1,'reason':'INITIAL_SIDE','signalTime':stamp.isoformat()})
        unrealized=position['side']*(b['close']-position['entryPrice'])*multiple-fee if position else 0
        curve.append({'timestamp':stamp.isoformat(),'tradingDay':day,'realizedPnl':balance,
                      'markedPnl':balance+unrealized,'position':position['side'] if position else 0,
                      'mean':m,'close':b['close'],'volume':b['volume'],'waitingForCross':waiting,
                      'crossSignalPending':bool(pending and pending.get('reason') in ('CROSS_AFTER_EXIT','CROSS_AFTER_FILTER')),
                      'allowedSide':b['allowedSide'],'dailySourceDay':b['dailySourceDay']})
    if position:
        raise ValueError('Missing terminal daily liquidation')
    return trades,curve,events,rejected


def verify(trades,curve,events,stats):
    assert len(events)==2*len(trades)
    assert sum(e['fee'] for e in events)==stats['fees']
    assert sum(t['netPnl'] for t in trades)==stats['netPnl']
    assert curve[-1]['position']==0 and curve[-1]['markedPnl']==stats['netPnl']
    index={b['timestamp']:i for i,b in enumerate(curve)}
    exposure,previous_exit=0,None
    for i,event in enumerate(events):
        assert event['sequence']==i+1 and event['lots']==1
        assert not event['reason'].startswith('REVERSE_')
        if event['kind']=='OPEN':
            assert exposure==0
            assert (1 if event['buy'] else -1)==event['allowedSide']
            if previous_exit:
                assert event['timestamp']>previous_exit['timestamp']
                if event['tradingDay']==previous_exit['tradingDay']:
                    assert event['reason']=='CROSS_AFTER_EXIT'
            exposure=1 if event['buy'] else -1
        else:
            assert exposure==(-1 if event['buy'] else 1)
            exposure=0
            previous_exit=event
    assert exposure==0
    last_trade=None
    for t in trades:
        assert t['entryTime']>t['signalTime']
        assert t['entrySequence']<t['exitSequence']
        assert abs(t['entryPrice']-t['stopPrice'])==10
        assert t['grossPnl']-t['fees']-t['slippageCost']==t['netPnl']
        assert t['side']*(t['exitPrice']-t['entryPrice'])*20-t['fees']==t['netPnl']
        assert t['exitReason'] in ('STOP','STOP_GAP','MEAN_REVERSAL','DAY_END')
        signal=curve[index[t['signalTime']]]
        if t['entryReason']=='INITIAL_SIDE':
            assert t['side']*(signal['close']-signal['mean'])>0
        elif t['entryReason'] in ('CROSS_AFTER_EXIT','CROSS_AFTER_FILTER'):
            if t['entryReason']=='CROSS_AFTER_EXIT':
                assert last_trade and last_trade['exitTime']==t['previousExitTime']
                assert t['signalTime']>t['previousExitTime']
            else:
                assert t['previousExitTime'] is None
            j=index[t['signalTime']]
            prev=next(c for c in reversed(curve[:j]) if c['tradingDay']==t['tradingDay'] and c['volume']>0 and c['mean'] is not None)
            a,b=prev['close']-prev['mean'],signal['close']-signal['mean']
            assert a==t['crossFromDelta'] and b==t['crossToDelta']
            assert (a<=0<b) if t['side']==1 else (a>=0>b)
        else:
            raise AssertionError('Unexpected entry reason')
        assert t['side']==t['allowedSide']==signal['allowedSide']
        assert t['dailySourceDay']<t['tradingDay']
        assert datetime.fromisoformat(t['dailyAvailableAt'])<datetime.fromisoformat(t['signalTime'])
        assert t['side']==(1 if t['dailyDIF']>t['dailyDEA'] else -1 if t['dailyDIF']<t['dailyDEA'] else 0)
        if t['exitReason']=='MEAN_REVERSAL':
            exit_index=index[t['exitTime']]
            prev=next(c for c in reversed(curve[:exit_index]) if c['tradingDay']==t['tradingDay'] and c['volume']>0)
            assert t['side']*(prev['close']-prev['mean'])<=-3+1e-9
        last_trade=t
    for day in {c['tradingDay'] for c in curve}:
        assert next(c for c in reversed(curve) if c['tradingDay']==day)['position']==0
    return {'status':'PASS','noReversal':True,'strictlyLaterFreshCrossReentry':True,
            'oneLotExposure':True,'accounting':True,'eachTradingDayFlat':True,'noTakeProfit':True,
            'onlyAllowedDailyDirection':True,'noCurrentDailyBarLeakage':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'output/fg701-ma20-daily-macd-2026-11-17-r2')
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    if (args.out/'results.json').exists():
        raise SystemExit('Preserving frozen study; use a new --out')
    raw_path=ROOT/'data/history/fg701-intraday-2026-11-17/raw.json'
    raw=json.loads(raw_path.read_text(encoding='utf-8'))
    assert raw['spec']['price_tick']==1 and raw['spec']['volume_multiple']==20
    bars,audit,indicator=prepare_ma20(raw)
    daily_path=ROOT/'data/history/fg701-macd-daily-2026-11-17/raw.json'
    daily_source=json.loads(daily_path.read_text(encoding='utf-8'))
    daily_audit=verify_daily_overlap(raw,daily_source)
    current_daily,era_audit=current_contract_daily(daily_source['daily'],raw['spec']['expire_datetime'])
    macd=daily_macd(current_daily,require_listing=False)
    bars,contexts=bind_daily_filter(bars,macd,raw['calendar'])
    prior=json.loads((ROOT/'output/fg701-ma20-wait-cross-2026-11-17/results.json').read_text(encoding='utf-8'))
    result={'status':'COMPLETE','strategy':'DAILY_MACD_DIRECTION_MINUTE_MA20_WAIT_CROSS','symbol':raw['symbol'],
            'window':prior['window'],'dataSha256':hashlib.sha256(raw_path.read_bytes()).hexdigest(),
            'dailyDataSha256':hashlib.sha256(daily_path.read_bytes()).hexdigest(),
            'sourceHashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                           [Path(__file__),ROOT/'scripts/backtest_fg701_intraday.py',ROOT/'scripts/backtest_fg701_ma20.py',ROOT/'scripts/backtest_fg701_reversal.py',ROOT/'scripts/fg701_daily_macd.py',ROOT/'docs/plans/2026-11-17-fg701-ma20-daily-macd.md']},
            'audit':audit,'indicator':indicator,'dailyAudit':daily_audit,'dailyEraAudit':era_audit,
            'macd':{'fast':12,'slow':26,'signal':9,'minimumHistory':35,'dailyBarsForCurrentContract':len(macd),
                    'firstDailyDate':macd[0]['date'],'initializedAtCurrentDeliveryEraStart':True,
                    'firstCurrentSourceId':macd[0]['sourceId']},
            'dailyContexts':contexts,'priorUnfilteredBaseline':prior['scenarios']['high_first-baseline'],
            'scenarios':{},'assumptions':['Completed prior trading-date daily MACD(12,26,9) DIF above DEA allows long only; below allows short only; equality/unready blocks entries.',
                                        'Daily filter fixed over associated night/day session, source available at prior close; no current-day daily candle.',
                                        'Initial close-side candidate retains prior rule but must pass direction filter; if blocked wait for a new eligible MA20 cross.',
                                        'After every exit remain flat; anchor on exit-minute close and wait for a later new close cross of MA20.',
                                        'Fresh upward cross opens long; downward cross opens short, next observed open. No same-minute reentry.',
                                        'Initial daily entry retains close-side rule; daily wait state resets, continuous 20-minute MA does not.',
                                        'Fixed stop 10 ticks, held-position opposite close 3 ticks across MA20 exits next open, no take-profit.',
                                        'No entries after 14:58; 14:59 liquidation. One lot maximum.',
                                        'Use same 7245 real sample minutes and 19 real preceding warmup closes.',
                                        'Fees assumed RMB 6 per lot per side, adverse slippage separately per fill; paths replayed independently.']}
    for path in ('HIGH_FIRST','LOW_FIRST'):
        for name,fee,slip in [('zero_cost',0,0),('baseline',6,1),('stress',6,2)]:
            key=path.lower()+'-'+name
            trades,curve,events,rejected=simulate_macd_filtered(bars,fee=fee,slippage=slip,path=path)
            stats={'path':path,'feePerSide':fee,'slippageTicksPerSide':slip,**summarize(trades,curve)}
            stats['verification']=verify(trades,curve,events,stats)
            stats['blockedEntrySignals']=len(rejected)
            daily=defaultdict(lambda:{'trades':0,'grossPnl':0,'fees':0,'slippageCost':0,'netPnl':0})
            for b in bars:
                _=daily[b['tradingDay']]
            for t in trades:
                daily[t['tradingDay']]['trades']+=1
                for k in ('grossPnl','fees','slippageCost','netPnl'):
                    daily[t['tradingDay']][k]+=t[k]
            assert sum(d['netPnl'] for d in daily.values())==stats['netPnl']
            for suffix,rows in [('trades',trades),('curve',curve),('events',events),('rejected',rejected),('daily',[{'tradingDay':k,**v} for k,v in sorted(daily.items())])]:
                write_csv(args.out/f'{key}-{suffix}.csv',rows)
            result['scenarios'][key]=stats
    write_csv(args.out/'daily-macd.csv',macd)
    write_csv(args.out/'daily-filter-contexts.csv',list(contexts.values()))
    (args.out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:{q:s[q] for q in ('trades','netPnl','winRate','maxMinuteCloseMarkedDrawdown','exitReasons')} for k,s in result['scenarios'].items()},ensure_ascii=True))


if __name__=='__main__':
    main()
