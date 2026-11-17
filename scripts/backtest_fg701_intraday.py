"""Causal, one-lot FG701 intraday research. No trading-service dependencies."""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, time, timedelta
import hashlib
import html
import json
import math
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SH = ZoneInfo('Asia/Shanghai')


def prepare(raw, start=date(2026, 10, 17), end=date(2026, 11, 16)):
    """Require complete exchange sessions; never substitute a shorter window."""
    days = sorted(date.fromisoformat(r['date']) for r in raw['calendar'] if r['trading'])
    expected_days = [d for d in days if start <= d <= end]
    rows, seen, errors = [], set(), []
    ids = []
    for r in raw['minute']:
        stamp = datetime.fromtimestamp(r['datetime'] / 1e9, SH)
        if stamp.hour >= 18:
            j = bisect_right(days, stamp.date())
            if j == len(days):
                continue
            day = days[j]
        else:
            day = stamp.date()
        if not start <= day <= end:
            continue
        if stamp in seen:
            errors.append('duplicate timestamp ' + stamp.isoformat())
        seen.add(stamp)
        values = [r.get(k) for k in ('open', 'high', 'low', 'close', 'volume')]
        if any(v is None or not math.isfinite(v) for v in values):
            errors.append('nonfinite OHLCV ' + stamp.isoformat())
            continue
        o, h, l, c, v = values
        if min(o, h, l, c) <= 0 or v < 0 or l > min(o, c) or h < max(o, c):
            errors.append('invalid OHLCV ' + stamp.isoformat())
        rows.append(dict(timestamp=stamp, tradingDay=day.isoformat(), open=o, high=h, low=l,
                         close=c, volume=v, sourceId=r.get('id')))
        ids.append(r.get('id'))
    if raw.get('symbol') != 'CZCE.FG701':
        errors.append('wrong actual delivery contract')
    if rows != sorted(rows, key=lambda b: b['timestamp']):
        errors.append('input is not chronological')
    if any(b != a + 1 for a, b in zip(ids, ids[1:]) if a is not None and b is not None):
        errors.append('provider serial ID gap')
    if raw.get('lastMinuteProvisional') and raw['minute']:
        final = raw['minute'][-1]['datetime']
        if any(int(b['timestamp'].timestamp()*1e9) == final for b in rows):
            errors.append('provisional terminal minute overlaps requested complete window')
    byday = defaultdict(list)
    for bar in rows:
        byday[bar['tradingDay']].append(bar)
    daily = {datetime.fromtimestamp(b['datetime']/1e9, SH).date().isoformat(): b for b in raw.get('daily', [])}
    daily_checks = 0
    coverage = []
    for d in expected_days:
        actual = byday[d.isoformat()]
        # FG sessions from the exchange rules, independently checked against SDK metadata.
        minutes = set(range(21*60, 23*60)) | set(range(9*60, 10*60+15)) | set(range(10*60+30, 11*60+30)) | set(range(13*60+30, 15*60))
        observed = [b['timestamp'].hour*60+b['timestamp'].minute for b in actual]
        missing = sorted(minutes - set(observed))
        extra = sorted(set(observed) - minutes)
        if missing or extra or len(actual) != len(minutes):
            errors.append(f'{d}: incomplete/extra session minutes')
        daily_match = None
        if actual and raw.get('daily') is not None:
            observed = dict(open=actual[0]['open'], high=max(b['high'] for b in actual),
                            low=min(b['low'] for b in actual), close=actual[-1]['close'],
                            volume=sum(b['volume'] for b in actual))
            reference = daily.get(d.isoformat())
            daily_match = reference is not None and all(v == reference.get(k) for k, v in observed.items())
            daily_checks += 1
            if not daily_match:
                errors.append(f'{d}: minute OHLCV aggregation disagrees with daily reference')
        coverage.append({'tradingDay': d.isoformat(), 'bars': len(actual), 'expectedBars': len(minutes),
                         'missingMinutes': missing, 'extraMinutes': extra, 'matchesDailyOHLCV': daily_match})
    if not expected_days or not rows:
        errors.append('empty requested calendar/data window')
    audit = {'status': 'PASS' if not errors else 'FAIL', 'errors': errors,
             'requestedStart': start.isoformat(), 'requestedEnd': end.isoformat(),
             'days': len(expected_days), 'bars': len(rows), 'coverage': coverage,
             'dailyReferenceChecks': daily_checks,
             'firstTimestamp': rows[0]['timestamp'].isoformat() if rows else None,
             'lastTimestamp': rows[-1]['timestamp'].isoformat() if rows else None}
    return rows, audit


def add_mean(bars):
    total = volume = 0.0
    day = None
    output = []
    for b in bars:
        if b['tradingDay'] != day:
            total = volume = 0.0
            day = b['tradingDay']
        total += (b['high'] + b['low'] + b['close']) / 3 * b['volume']
        volume += b['volume']
        output.append({**b, 'mean': total / volume if volume > 0 else None})
    return output


def simulate(bars, tick=1.0, multiple=20, fee=6.0, slippage=1, stop_ticks=10, exit_ticks=3):
    """Signals use completed bars, orders fill next observed open; stops act intrabar.

    Pullback means low in [mean, mean+tick] for long, symmetric high for short.
    Daily liquidation is scheduled at 14:59 open, never a hindsight last-row close.
    """
    if tick <= 0 or multiple <= 0 or fee < 0 or slippage < 0 or stop_ticks <= 0 or exit_ticks <= 0:
        raise ValueError('Invalid execution parameters')
    trades, curve = [], []
    position = pending = None
    mode, waiting, armed_at = 'INITIAL', 0, -1
    day, balance = None, 0.0

    def close(b, price, reason):
        nonlocal position, balance
        side = position['side']
        actual = price - side * slippage * tick
        gross = side * (price-position['entryReference']) * multiple
        slip_cost = 2 * slippage * tick * multiple
        net = side * (actual-position['entryPrice']) * multiple - 2 * fee
        trade = {**position, 'exitTime': b['timestamp'].isoformat(), 'exitReference': price,
                 'exitPrice': actual, 'exitReason': reason, 'grossPnl': gross,
                 'fees': 2*fee, 'slippageCost': slip_cost, 'netPnl': net,
                 'holdingMinutes': (b['timestamp']-datetime.fromisoformat(position['entryTime'])).total_seconds()/60}
        balance += net
        trade['cumulativeNetPnl'] = balance
        trades.append(trade)
        position = None

    for i, b in enumerate(bars):
        stamp, m, traded = b['timestamp'], b['mean'], b['volume'] > 0
        if b['tradingDay'] != day:
            if position:
                raise ValueError('Missing scheduled session liquidation; refuse overnight position')
            day, mode, waiting, pending = b['tradingDay'], 'INITIAL', 0, None
        clock = stamp.time().replace(tzinfo=None)
        cutoff = time(14, 58) <= clock < time(18)
        liquidate = time(14, 59) <= clock < time(18)
        stopped = False
        # A gap stop has priority over any scheduled signal exit.
        if position and traded:
            s, level = position['side'], position['stopPrice']
            if s*(b['open']-level) <= 0:
                close(b, b['open'], 'STOP_GAP')
                pending, mode, waiting, stopped = None, 'INITIAL', 0, True
        if position and liquidate:
            if not traded:
                raise ValueError('No observed volume at scheduled liquidation')
            close(b, b['open'], 'DAY_END')
            pending = None
        if pending and not stopped and traded:
            action = pending
            pending = None
            if action['kind'] == 'EXIT' and position:
                close(b, b['open'], 'MEAN_REVERSAL')
                mode, waiting, armed_at = 'WAIT', action['reverse'], action['signalIndex']
            elif action['kind'] == 'ENTRY' and not position and not cutoff:
                s = action['side']
                price = b['open'] + s*slippage*tick
                position = {'tradingDay': day, 'side': s, 'lots': 1, 'entryTime': stamp.isoformat(),
                            'signalTime': action['signalTime'], 'entryReason': action['reason'],
                            'entryReference': b['open'], 'entryPrice': price,
                            'stopPrice': price-s*stop_ticks*tick}
                mode = 'HELD'
        if position and traded:
            s, level = position['side'], position['stopPrice']
            if (s == 1 and b['low'] <= level) or (s == -1 and b['high'] >= level):
                close(b, level, 'STOP')
                pending, mode, waiting, stopped = None, 'INITIAL', 0, True
        if not cutoff and not stopped and traded and m is not None:
            delta = b['close']-m
            if position:
                if position['side']*delta <= -exit_ticks*tick + 1e-9:
                    pending = {'kind': 'EXIT', 'reverse': -position['side'], 'signalIndex': i}
            elif mode == 'INITIAL':
                if abs(delta) > 1e-9:
                    pending = {'kind': 'ENTRY', 'side': 1 if delta > 0 else -1,
                               'signalTime': stamp.isoformat(), 'reason': 'INITIAL_SIDE'}
            elif mode in ('WAIT', 'INVALID'):
                opposite = -waiting
                if opposite*delta >= exit_ticks*tick - 1e-9:
                    waiting, mode, armed_at = opposite, 'WAIT', i
                elif mode == 'WAIT' and i > armed_at:
                    extreme = b['low'] if waiting == 1 else b['high']
                    distance = waiting*(extreme-m)
                    if distance < -1e-9:
                        mode = 'INVALID'
                    elif distance <= tick+1e-9 and waiting*delta > 1e-9:
                        pending = {'kind': 'ENTRY', 'side': waiting, 'signalTime': stamp.isoformat(),
                                   'reason': 'FIRST_PULLBACK'}
                        mode = 'PENDING'
        unrealized = 0.0
        if position:
            unrealized = position['side']*(b['close']-position['entryPrice'])*multiple-fee
        curve.append({'timestamp': stamp.isoformat(), 'tradingDay': day, 'realizedPnl': balance,
                      'markedPnl': balance+unrealized, 'position': position['side'] if position else 0,
                      'mean': m, 'close': b['close']})
    if position:
        raise ValueError('Unliquidated terminal position; incomplete session input')
    return trades, curve


def drawdown(values):
    peak = maximum = 0.0
    for value in values:
        peak = max(peak, value)
        maximum = max(maximum, peak-value)
    return maximum


def summarize(trades, curve):
    wins = [t['netPnl'] for t in trades if t['netPnl'] > 0]
    losses = [t['netPnl'] for t in trades if t['netPnl'] < 0]
    return {'trades': len(trades), 'netPnl': sum(t['netPnl'] for t in trades),
            'grossPnl': sum(t['grossPnl'] for t in trades), 'fees': sum(t['fees'] for t in trades),
            'slippageCost': sum(t['slippageCost'] for t in trades),
            'winRate': len(wins)/len(trades) if trades else None,
            'profitFactor': sum(wins)/-sum(losses) if losses else None,
            'maxRealizedDrawdown': drawdown([0]+[t['cumulativeNetPnl'] for t in trades]),
            'maxMinuteCloseMarkedDrawdown': drawdown([r['markedPnl'] for r in curve]),
            'averageHoldingMinutes': mean(t['holdingMinutes'] for t in trades) if trades else None,
            'exitReasons': dict(Counter(t['exitReason'] for t in trades)),
            'direction': {label: {'trades': len([t for t in trades if t['side'] == s]),
                                  'netPnl': sum(t['netPnl'] for t in trades if t['side'] == s)}
                          for s, label in [(1, 'LONG'), (-1, 'SHORT')]}}


def write_csv(path, rows):
    if not rows:
        path.write_text('', encoding='utf-8-sig')
        return
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'data/history/fg701-intraday-2026-11-17/raw.json')
    parser.add_argument('--out', type=Path, default=ROOT / 'output/fg701-intraday-2026-11-17')
    parser.add_argument('--fee', type=float, default=6.0, help='Assumed RMB per lot per side, not broker-verified')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if (args.out / 'results.json').exists():
        raise SystemExit('Frozen result exists; select a new --out directory')
    raw = json.loads(args.source.read_text(encoding='utf-8'))
    bars, audit = prepare(raw)
    def save(name, value):
        (args.out/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    save('data-audit.json', audit)
    if audit['status'] != 'PASS':
        raise SystemExit(json.dumps({'status': 'DATA_AUDIT_FAILED', 'errors': audit['errors']}, ensure_ascii=False))
    tick, multiple = raw['spec']['price_tick'], raw['spec']['volume_multiple']
    if tick != 1 or multiple != 20:
        raise SystemExit('Unexpected FG contract specification')
    bars = add_mean(bars)
    results = {'status': 'COMPLETE', 'symbol': raw['symbol'], 'window': ['2026-10-17', '2026-11-16'],
               'dataSha256': hashlib.sha256(args.source.read_bytes()).hexdigest(),
               'scriptSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'planSha256': hashlib.sha256((ROOT/'docs/plans/2026-11-17-fg701-intraday-backtest.md').read_bytes()).hexdigest(),
               'dataAudit': audit, 'mean': 'Causal cumulative HLC3*volume / cumulative volume, approximate VWAP',
               'feeAssumptionPerSide': args.fee, 'scenarios': {},
               'limitations': ['One month, one contract, no out-of-sample validation.',
                   'Approximate minute VWAP is not exact exchange intraday average.',
                   'Minute OHLC cannot reveal intrabar sequence, queue depth, or actual fills.',
                   'Fixed slippage and assumed fees, not account-specific historical fees.',
                   'Marked drawdown samples minute closes; intrabar drawdown may be larger.',
                   'Price-limit liquidity is not reconstructed; slippage fills are scenario assumptions.',
                   'No capital or historical margin model: currency P&L only.']}
    for name, fee, slip in [('zero_cost', 0, 0), ('baseline', args.fee, 1), ('stress', args.fee, 2)]:
        trades, curve = simulate(bars, tick=tick, multiple=multiple, fee=fee, slippage=slip)
        results['scenarios'][name] = {'feePerSide': fee, 'slippageTicksPerSide': slip, **summarize(trades, curve)}
        write_csv(args.out/f'{name}-trades.csv', trades)
        write_csv(args.out/f'{name}-curve.csv', curve)
        daily = defaultdict(lambda: {'trades': 0, 'grossPnl': 0.0, 'fees': 0.0, 'slippageCost': 0.0, 'netPnl': 0.0})
        for b in bars:
            _ = daily[b['tradingDay']]
        for t in trades:
            d = daily[t['tradingDay']]
            d['trades'] += 1
            for k in ('grossPnl', 'fees', 'slippageCost', 'netPnl'):
                d[k] += t[k]
        write_csv(args.out/f'{name}-daily.csv', [{'tradingDay': k, **v} for k, v in sorted(daily.items())])
    save('results.json', results)
    table = ''.join('<tr><th>'+html.escape(k)+'</th>'+''.join(f'<td>{html.escape(str(results["scenarios"][s].get(k)))}</td>' for s in ('zero_cost','baseline','stress'))+'</tr>'
                    for k in ('trades','grossPnl','fees','slippageCost','netPnl','winRate','profitFactor','maxRealizedDrawdown','maxMinuteCloseMarkedDrawdown'))
    report = '<!doctype html><html lang="zh"><meta charset="utf-8"><title>玻璃2701日内基础版回测</title><style>body{font:16px/1.7 system-ui;max-width:1000px;margin:40px auto;padding:20px}table{border-collapse:collapse;width:100%}td,th{padding:10px;border:1px solid #ccc;text-align:right}p{color:#333}</style><h1>玻璃2701：1分钟日内基础版</h1><p>2026-10-17至2026-11-16，按交易日；'+str(audit['days'])+'个完整交易日，'+str(audit['bars'])+'根真实K线。每次1手，10跳止损、反向3跳退出、首次回踩反手、14:59开盘清仓。收敛和趋势过滤暂未加入。</p><p>均线为HLC3按成交量累计加权的近似VWAP；每个交易日重置，包含夜盘。信号收盘确认，次根开盘成交。回踩定义：多头最低价在均线至均线上方1跳内且收盘在均线上；空头对称。费用为假设每边'+str(args.fee)+'元。</p><table><tr><th>指标（人民币元）</th><th>不计成本</th><th>每边1跳滑点</th><th>每边2跳滑点</th></tr>'+table+'</table><p>一次交易=完整开平一组。固定止损以含滑点的实际开仓价为基准，因此三种执行条件可能产生不同交易次数。</p><h2>数据和复核文件</h2><p>逐笔成交、按日盈亏、分钟净值和数据完整性审核均在同目录CSV/JSON中。原始授权行情保留于本机data/history，不上传公开仓库。</p><h2>解释限制</h2><ul>'+''.join('<li>'+html.escape(x)+'</li>' for x in results['limitations'])+'</ul><p>本结果仅描述指定月份与指定规则，不能据此确认长期有效。</p></html>'
    (args.out/'report.html').write_text(report, encoding='utf-8')
    print(json.dumps({'status':'COMPLETE','days':audit['days'],'bars':audit['bars'],'scenarios':results['scenarios']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
