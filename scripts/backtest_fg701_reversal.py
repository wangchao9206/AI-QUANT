"""FG701 revision: close and immediately reverse; explicit intraminute OHLC paths."""
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


def simulate_reversal(bars, tick=1, multiple=20, fee=6, slippage=1, stop_ticks=10,
                      exit_ticks=3, path='HIGH_FIRST'):
    if path not in ('HIGH_FIRST', 'LOW_FIRST'):
        raise ValueError('Unknown OHLC path')
    if tick <= 0 or multiple <= 0 or fee < 0 or not 0 <= slippage < stop_ticks or exit_ticks <= 0:
        raise ValueError('Invalid execution parameters')
    trades, curve, events = [], [], []
    position, pending, day, balance = None, None, None, 0.0

    def fill_event(b, reference, buy, kind, phase, reason, trade_id):
        actual = reference + (1 if buy else -1)*slippage*tick
        event = {'sequence': len(events)+1, 'tradeId': trade_id, 'tradingDay': day,
                 'timestamp': b['timestamp'].isoformat(), 'timestampPrecision': 'MINUTE',
                 'phase': phase, 'kind': kind, 'buy': buy, 'referencePrice': reference,
                 'price': actual, 'lots': 1, 'fee': fee, 'reason': reason}
        events.append(event)
        return event

    def enter(b, reference, side, reason, phase, signal_time):
        nonlocal position
        event = fill_event(b, reference, side == 1, 'OPEN', phase, reason, len(trades)+1)
        price = event['price']
        position = {'tradeId': len(trades)+1, 'tradingDay': day, 'side': side, 'lots': 1,
                    'entryTime': b['timestamp'].isoformat(), 'signalTime': signal_time,
                    'entryReason': reason, 'entryPhase': phase, 'entrySequence': event['sequence'],
                    'entryReference': reference, 'entryPrice': price, 'stopPrice': price-side*stop_ticks*tick}

    def close(b, reference, reason, phase):
        nonlocal position, balance
        old = position
        event = fill_event(b, reference, old['side'] == -1, 'CLOSE', phase, reason, old['tradeId'])
        gross = old['side']*(reference-old['entryReference'])*multiple
        slip = 2*slippage*tick*multiple
        net = old['side']*(event['price']-old['entryPrice'])*multiple-2*fee
        balance += net
        trades.append({**old, 'exitTime': b['timestamp'].isoformat(), 'exitPhase': phase,
                       'exitSequence': event['sequence'], 'exitReference': reference,
                       'exitPrice': event['price'], 'exitReason': reason,
                       'grossPnl': gross, 'fees': 2*fee, 'slippageCost': slip, 'netPnl': net,
                       'holdingMinutes': (b['timestamp']-datetime.fromisoformat(old['entryTime'])).total_seconds()/60,
                       'cumulativeNetPnl': balance})
        position = None
        return old

    def close_reverse(b, reference, reason, phase, allow_entry, signal_time):
        old = close(b, reference, reason, phase)
        if allow_entry:
            enter(b, reference, -old['side'], 'REVERSE_'+reason, phase, signal_time)

    for b in bars:
        stamp, m, traded = b['timestamp'], b['mean'], b['volume'] > 0
        if day != b['tradingDay']:
            if position:
                raise ValueError('Missing daily liquidation')
            day, pending = b['tradingDay'], None
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
            if gap_stop:
                close_reverse(b, b['open'], 'STOP_GAP', 'OPEN', not cutoff, stamp.isoformat())
                pending = None
            elif pending:
                action, pending = pending, None
                if action['kind'] == 'EXIT' and position:
                    close_reverse(b, b['open'], 'MEAN_REVERSAL', 'OPEN', not cutoff, action['signalTime'])
                elif action['kind'] == 'ENTRY' and not position and not cutoff:
                    enter(b, b['open'], action['side'], 'INITIAL_SIDE', 'OPEN', action['signalTime'])
            # Explicit scenario paths preserve causal segment order, including repeated reversals.
            route = [b['open'], b['high'], b['low'], b['close']] if path == 'HIGH_FIRST' else [b['open'], b['low'], b['high'], b['close']]
            for segment, (start, finish) in enumerate(zip(route, route[1:]), 1):
                if not position:
                    break
                side, level = position['side'], position['stopPrice']
                hit = (side == 1 and finish <= level <= start) or (side == -1 and start <= level <= finish)
                if hit:
                    close_reverse(b, level, 'STOP', f'SEGMENT_{segment}', not cutoff, stamp.isoformat())
        if not cutoff and traded and m is not None:
            delta = b['close']-m
            if position:
                if position['side']*delta <= -exit_ticks*tick+1e-9:
                    pending = {'kind': 'EXIT', 'signalTime': stamp.isoformat()}
            elif abs(delta) > 1e-9:
                pending = {'kind': 'ENTRY', 'side': 1 if delta > 0 else -1, 'signalTime': stamp.isoformat()}
        unrealized = position['side']*(b['close']-position['entryPrice'])*multiple-fee if position else 0
        curve.append({'timestamp': stamp.isoformat(), 'tradingDay': day, 'realizedPnl': balance,
                      'markedPnl': balance+unrealized, 'position': position['side'] if position else 0,
                      'mean': m, 'close': b['close']})
    if position:
        raise ValueError('Missing terminal daily liquidation')
    return trades, curve, events


def verify(trades, curve, events, stats):
    assert len(events) == 2*len(trades)
    assert sum(e['fee'] for e in events) == stats['fees']
    assert sum(t['netPnl'] for t in trades) == stats['netPnl']
    assert curve[-1]['position'] == 0 and curve[-1]['markedPnl'] == stats['netPnl']
    exposure = 0
    for index, event in enumerate(events):
        assert event['sequence'] == index+1
        if event['kind'] == 'OPEN':
            assert exposure == 0
            exposure = 1 if event['buy'] else -1
        else:
            assert exposure == (-1 if event['buy'] else 1)
            exposure = 0
            clock = datetime.fromisoformat(event['timestamp']).time().replace(tzinfo=None)
            if not time(14, 58) <= clock < time(18) and event['reason'] != 'DAY_END':
                nxt = events[index+1]
                assert nxt['kind'] == 'OPEN' and nxt['timestamp'] == event['timestamp']
                assert nxt['referencePrice'] == event['referencePrice'] and nxt['buy'] == event['buy']
                assert nxt['phase'] == event['phase']
    assert exposure == 0
    for t in trades:
        assert abs(t['entryPrice']-t['stopPrice']) == 10
        assert t['entrySequence'] < t['exitSequence']
        assert t['grossPnl']-t['fees']-t['slippageCost'] == t['netPnl']
        assert t['side']*(t['exitPrice']-t['entryPrice'])*20-t['fees'] == t['netPnl']
    return {'status': 'PASS', 'immediateOppositeEntry': True, 'oneLotExposure': True,
            'accounting': True, 'dayEndFlat': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT/'output/fg701-reversal-2026-11-17')
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
    old = json.loads((ROOT/'output/fg701-intraday-2026-11-17/results.json').read_text(encoding='utf-8'))
    result = {'status': 'COMPLETE', 'strategy': 'CLOSE_AND_IMMEDIATELY_REVERSE', 'symbol': raw['symbol'],
              'window': old['window'], 'dataSha256': hashlib.sha256(raw_path.read_bytes()).hexdigest(),
              'sourceHashes': {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                               [Path(__file__), ROOT/'scripts/backtest_fg701_intraday.py', ROOT/'docs/plans/2026-11-17-fg701-immediate-reversal.md']},
              'audit': audit, 'oldBaseline': old['scenarios']['baseline'], 'scenarios': {},
              'assumptions': ['Mean exits confirmed by minute close; close/reverse at following open.',
                              'All stop exits reverse immediately except the daily entry cutoff.',
                              '14:59 open liquidates without reversing; no entries from 14:58.',
                              'OHLC intraminute path scenarios are not bounds on actual fills.',
                              'Stop events have minute timestamps with explicit within-minute phase and sequence.',
                              'Fees assumed 6 RMB per lot per side; adverse slippage separately per fill.',
                              'Approximate HLC3 volume-weighted trading-day mean.']}
    for path in ('HIGH_FIRST', 'LOW_FIRST'):
        for name, fee, slip in [('zero_cost',0,0),('baseline',6,1),('stress',6,2)]:
            key = path.lower()+'-'+name
            trades, curve, events = simulate_reversal(bars, fee=fee, slippage=slip, path=path)
            stats = {'path': path, 'feePerSide': fee, 'slippageTicksPerSide': slip, **summarize(trades, curve)}
            stats['verification'] = verify(trades, curve, events, stats)
            daily = defaultdict(lambda: {'trades':0,'grossPnl':0,'fees':0,'slippageCost':0,'netPnl':0})
            for b in bars:
                _ = daily[b['tradingDay']]
            for t in trades:
                daily[t['tradingDay']]['trades'] += 1
                for k in ('grossPnl','fees','slippageCost','netPnl'):
                    daily[t['tradingDay']][k] += t[k]
            assert sum(d['netPnl'] for d in daily.values()) == stats['netPnl']
            write_csv(args.out/f'{key}-trades.csv',trades)
            write_csv(args.out/f'{key}-curve.csv',curve)
            write_csv(args.out/f'{key}-events.csv',events)
            write_csv(args.out/f'{key}-daily.csv',[{'tradingDay':k,**v} for k,v in sorted(daily.items())])
            result['scenarios'][key] = stats
    (args.out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:{q:s[q] for q in ('trades','netPnl','winRate','maxMinuteCloseMarkedDrawdown','exitReasons')} for k,s in result['scenarios'].items()},ensure_ascii=True))


if __name__ == '__main__':
    main()
