"""10-tick target; wait for a new mean crossing after profit-taking. Read-only research."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, time
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.backtest_fg701_intraday import add_mean, prepare, summarize, write_csv


def simulate_take_profit(bars, tick=1, multiple=20, fee=6, slippage=1, stop_ticks=10,
                         take_profit_ticks=10, exit_ticks=3, path='HIGH_FIRST'):
    if path not in ('HIGH_FIRST', 'LOW_FIRST'):
        raise ValueError('Unknown OHLC path')
    if tick <= 0 or multiple <= 0 or fee < 0 or not 0 <= slippage < min(stop_ticks, take_profit_ticks) or exit_ticks <= 0:
        raise ValueError('Invalid execution parameters')
    trades, curve, events = [], [], []
    position, pending, day, balance = None, None, None, 0.0
    waiting, anchor, last_tp = False, None, None

    def fill_event(b, reference, buy, kind, phase, reason, trade_id):
        event = {'sequence': len(events)+1, 'tradeId': trade_id, 'tradingDay': day,
                 'timestamp': b['timestamp'].isoformat(), 'timestampPrecision': 'MINUTE',
                 'phase': phase, 'kind': kind, 'buy': buy, 'referencePrice': reference,
                 'price': reference+(1 if buy else -1)*slippage*tick,
                 'lots': 1, 'fee': fee, 'reason': reason}
        events.append(event)
        return event

    def enter(b, reference, side, reason, phase, signal_time, cross_from=None, cross_to=None):
        nonlocal position, waiting, anchor
        event = fill_event(b, reference, side == 1, 'OPEN', phase, reason, len(trades)+1)
        price = event['price']
        position = {'tradeId': len(trades)+1, 'tradingDay': day, 'side': side, 'lots': 1,
                    'entryTime': b['timestamp'].isoformat(), 'signalTime': signal_time,
                    'entryReason': reason, 'entryPhase': phase, 'entrySequence': event['sequence'],
                    'entryReference': reference, 'entryPrice': price,
                    'stopPrice': price-side*stop_ticks*tick, 'targetPrice': price+side*take_profit_ticks*tick,
                    'crossFromDelta': cross_from, 'crossToDelta': cross_to,
                    'previousTakeProfitTime': last_tp if reason == 'CROSS_AFTER_TP' else None}
        waiting, anchor = False, None

    def close(b, reference, reason, phase):
        nonlocal position, balance
        old = position
        event = fill_event(b, reference, old['side'] == -1, 'CLOSE', phase, reason, old['tradeId'])
        gross = old['side']*(reference-old['entryReference'])*multiple
        net = old['side']*(event['price']-old['entryPrice'])*multiple-2*fee
        balance += net
        trades.append({**old, 'exitTime': b['timestamp'].isoformat(), 'exitPhase': phase,
                       'exitSequence': event['sequence'], 'exitReference': reference,
                       'exitPrice': event['price'], 'exitReason': reason,
                       'grossPnl': gross, 'fees': 2*fee, 'slippageCost': 2*slippage*tick*multiple,
                       'netPnl': net, 'holdingMinutes': (b['timestamp']-datetime.fromisoformat(old['entryTime'])).total_seconds()/60,
                       'cumulativeNetPnl': balance})
        position = None
        return old

    def take_profit(b, phase):
        nonlocal waiting, anchor, pending, last_tp
        close(b, position['targetPrice'], 'TAKE_PROFIT', phase)
        waiting, anchor, pending, last_tp = True, None, None, b['timestamp'].isoformat()

    def close_reverse(b, reference, reason, phase, allow_entry, signal_time):
        old = close(b, reference, reason, phase)
        if allow_entry:
            enter(b, reference, -old['side'], 'REVERSE_'+reason, phase, signal_time)

    for b in bars:
        stamp, m, traded = b['timestamp'], b['mean'], b['volume'] > 0
        if day != b['tradingDay']:
            if position:
                raise ValueError('Missing daily liquidation')
            day, pending, waiting, anchor, last_tp = b['tradingDay'], None, False, None, None
        clock = stamp.time().replace(tzinfo=None)
        cutoff = time(14, 58) <= clock < time(18)
        liquidate = time(14, 59) <= clock < time(18)
        if liquidate:
            if position:
                if not traded:
                    raise ValueError('No liquidation volume')
                close(b, b['open'], 'DAY_END', 'OPEN')
            pending = None
        elif traded:
            gap_stop = position and position['side']*(b['open']-position['stopPrice']) <= 0
            gap_profit = position and position['side']*(b['open']-position['targetPrice']) >= 0
            if gap_stop:
                close_reverse(b, b['open'], 'STOP_GAP', 'OPEN', not cutoff, stamp.isoformat())
                pending = None
            elif gap_profit:
                take_profit(b, 'OPEN_TARGET_GAP')
            elif pending:
                action, pending = pending, None
                if action['kind'] == 'EXIT' and position:
                    close_reverse(b, b['open'], 'MEAN_REVERSAL', 'OPEN', not cutoff, action['signalTime'])
                elif action['kind'] == 'ENTRY' and not position and not cutoff:
                    enter(b, b['open'], action['side'], action['reason'], 'OPEN', action['signalTime'],
                          action.get('crossFromDelta'), action.get('crossToDelta'))
            route = [b['open'], b['high'], b['low'], b['close']] if path == 'HIGH_FIRST' else [b['open'], b['low'], b['high'], b['close']]
            for segment, (start, finish) in enumerate(zip(route, route[1:]), 1):
                cursor = start
                while position and cursor != finish:
                    side = position['side']
                    favorable = side*(finish-cursor) > 0
                    level = position['targetPrice'] if favorable else position['stopPrice']
                    if not min(cursor, finish) <= level <= max(cursor, finish):
                        break
                    if favorable:
                        take_profit(b, f'SEGMENT_{segment}')
                    else:
                        close_reverse(b, level, 'STOP', f'SEGMENT_{segment}', not cutoff, stamp.isoformat())
                    cursor = level
                if not position:
                    break
        if not cutoff and traded and m is not None:
            delta = b['close']-m
            if position:
                if position['side']*delta <= -exit_ticks*tick+1e-9:
                    pending = {'kind':'EXIT', 'signalTime':stamp.isoformat()}
            elif waiting:
                # The target minute only initializes the anchor, never confirms its own reentry.
                side = 1 if anchor is not None and anchor <= 0 and delta > 0 else -1 if anchor is not None and anchor >= 0 and delta < 0 else 0
                if side:
                    pending = {'kind':'ENTRY', 'side':side, 'reason':'CROSS_AFTER_TP',
                               'signalTime':stamp.isoformat(), 'crossFromDelta':anchor, 'crossToDelta':delta}
                anchor = delta
            elif abs(delta) > 1e-9:
                pending = {'kind':'ENTRY', 'side':1 if delta > 0 else -1, 'reason':'INITIAL_SIDE', 'signalTime':stamp.isoformat()}
        unrealized = position['side']*(b['close']-position['entryPrice'])*multiple-fee if position else 0
        curve.append({'timestamp':stamp.isoformat(), 'tradingDay':day, 'realizedPnl':balance,
                      'markedPnl':balance+unrealized, 'position':position['side'] if position else 0,
                      'mean':m, 'close':b['close'], 'waitingForCross':waiting,
                      'volume':b['volume'],
                      'crossSignalPending':bool(pending and pending.get('reason') == 'CROSS_AFTER_TP')})
    if position:
        raise ValueError('Missing terminal daily liquidation')
    return trades, curve, events


def verify(trades, curve, events, stats):
    assert len(events) == 2*len(trades)
    assert sum(e['fee'] for e in events) == stats['fees']
    assert sum(t['netPnl'] for t in trades) == stats['netPnl']
    assert curve[-1]['position'] == 0 and curve[-1]['markedPnl'] == stats['netPnl']
    curve_index = {c['timestamp']:i for i,c in enumerate(curve)}
    exposure, after_tp = 0, False
    for index, event in enumerate(events):
        assert event['sequence'] == index+1 and event['lots'] == 1
        if event['kind'] == 'OPEN':
            assert exposure == 0
            exposure = 1 if event['buy'] else -1
            if after_tp:
                prev = next(t for t in reversed(trades) if t['exitSequence'] < event['sequence'])
                if prev['tradingDay'] == event['tradingDay']:
                    assert event['reason'] == 'CROSS_AFTER_TP'
                    assert event['timestamp'] > prev['exitTime']
            after_tp = False
        else:
            assert exposure == (-1 if event['buy'] else 1)
            exposure = 0
            after_tp = event['reason'] == 'TAKE_PROFIT'
            clock = datetime.fromisoformat(event['timestamp']).time().replace(tzinfo=None)
            if not time(14,58) <= clock < time(18) and event['reason'] not in ('DAY_END','TAKE_PROFIT'):
                nxt = events[index+1]
                assert nxt['kind'] == 'OPEN' and nxt['timestamp'] == event['timestamp']
                assert nxt['referencePrice'] == event['referencePrice'] and nxt['buy'] == event['buy']
                assert nxt['phase'] == event['phase']
    assert exposure == 0
    for t in trades:
        assert abs(t['entryPrice']-t['stopPrice']) == 10
        assert abs(t['entryPrice']-t['targetPrice']) == 10
        assert t['entrySequence'] < t['exitSequence']
        assert t['grossPnl']-t['fees']-t['slippageCost'] == t['netPnl']
        assert t['side']*(t['exitPrice']-t['entryPrice'])*20-t['fees'] == t['netPnl']
        if t['exitReason'] == 'TAKE_PROFIT':
            assert t['exitReference'] == t['targetPrice']
        if t['entryReason'] == 'CROSS_AFTER_TP':
            assert t['signalTime'] > t['previousTakeProfitTime']
            assert t['entryTime'] > t['signalTime']
            i = curve_index[t['signalTime']]
            current = curve[i]
            prev = next(c for c in reversed(curve[:i]) if c['tradingDay'] == t['tradingDay'] and c['volume'] > 0 and c['mean'] is not None)
            a, b = prev['close']-prev['mean'], current['close']-current['mean']
            assert a == t['crossFromDelta'] and b == t['crossToDelta']
            assert (a <= 0 < b) if t['side'] == 1 else (a >= 0 > b)
    return {'status':'PASS', 'noImmediateProfitReversal':True, 'freshCrossAfterProfit':True,
            'otherExitsStillReverse':True, 'oneLotExposure':True, 'accounting':True, 'dayEndFlat':True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT/'output/fg701-take-profit-2026-11-17')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if (args.out/'results.json').exists():
        raise SystemExit('Preserving frozen study; use a new --out')
    raw_path = ROOT/'data/history/fg701-intraday-2026-11-17/raw.json'
    raw = json.loads(raw_path.read_text(encoding='utf-8'))
    bars, audit = prepare(raw)
    if audit['status'] != 'PASS':
        raise SystemExit('Source completeness check failed')
    assert raw['spec']['price_tick'] == 1 and raw['spec']['volume_multiple'] == 20
    bars = add_mean(bars)
    prior = json.loads((ROOT/'output/fg701-reversal-2026-11-17/results.json').read_text(encoding='utf-8'))
    result = {'status':'COMPLETE', 'strategy':'TAKE_PROFIT_10_THEN_WAIT_FOR_MEAN_CROSS', 'symbol':raw['symbol'],
              'window':prior['window'], 'dataSha256':hashlib.sha256(raw_path.read_bytes()).hexdigest(),
              'sourceHashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                             [Path(__file__), ROOT/'scripts/backtest_fg701_intraday.py', ROOT/'docs/plans/2026-11-17-fg701-take-profit-reentry.md']},
              'audit':audit, 'priorBaseline':prior['scenarios']['high_first-baseline'], 'scenarios':{},
              'assumptions':['Fixed 10-tick target from actual entry; adverse slippage still applies to exits.',
                             'After profit, anchor on that minute close and require a subsequent completed close cross of VWAP.',
                             'Post-profit crossing is zero-offset; held-position reverse exit remains 3 ticks.',
                             'Mean exits and stops still reverse; take-profit and day-end exits do not.',
                             'Initial/cross/mean signals execute at next observed minute open.',
                             '14:58 entry cutoff, 14:59 liquidation. Approximate HLC3-volume-weighted day mean.',
                             'O-H-L-C and O-L-H-C are fixed intrabar scenarios, not exact ticks or guaranteed bounds.',
                             'Fees assumed RMB 6 per lot per side and separate adverse slippage per fill.']}
    for path in ('HIGH_FIRST','LOW_FIRST'):
        for name, fee, slip in [('zero_cost',0,0),('baseline',6,1),('stress',6,2)]:
            key = path.lower()+'-'+name
            trades, curve, events = simulate_take_profit(bars, fee=fee, slippage=slip, path=path)
            stats = {'path':path, 'feePerSide':fee, 'slippageTicksPerSide':slip, **summarize(trades,curve)}
            stats['verification'] = verify(trades,curve,events,stats)
            daily = defaultdict(lambda:{'trades':0,'grossPnl':0,'fees':0,'slippageCost':0,'netPnl':0})
            for b in bars:
                _ = daily[b['tradingDay']]
            for t in trades:
                daily[t['tradingDay']]['trades'] += 1
                for k in ('grossPnl','fees','slippageCost','netPnl'):
                    daily[t['tradingDay']][k] += t[k]
            assert sum(d['netPnl'] for d in daily.values()) == stats['netPnl']
            for suffix, rows in [('trades',trades),('curve',curve),('events',events),('daily',[{'tradingDay':k,**v} for k,v in sorted(daily.items())])]:
                write_csv(args.out/f'{key}-{suffix}.csv', rows)
            result['scenarios'][key] = stats
    (args.out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:{q:s[q] for q in ('trades','netPnl','winRate','maxMinuteCloseMarkedDrawdown','exitReasons')} for k,s in result['scenarios'].items()},ensure_ascii=True))


if __name__ == '__main__':
    main()
