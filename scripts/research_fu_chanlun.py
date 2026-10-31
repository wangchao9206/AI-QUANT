#!/usr/bin/env python3
"""Frozen, causal structure experiments on the previously audited FU snapshot."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
import statistics
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtesting.chanlun_research import ENGINE, FAMILIES, SCALES, detect, execute
from backtesting.fuel_research import adjusted_sharpe_p, segments
from backtesting.independent_research import ResearchRisk, causal_prices
from data.tqsdk_backtest import TqSdkBacktestDataProvider

CORE = 1_000_000
DEFAULT_FOLDER = 'fu-chanlun-2026-10-30'


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def config_id(family, scale):
    return f'{family}__{scale}'


def chart(out, data, signals, audits, cache, windows):
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt, font_manager
    font = Path('C:/Windows/Fonts/msyh.ttc')
    if font.exists():
        font_manager.fontManager.addfont(str(font))
        plt.rcParams['font.family'] = font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams['axes.unicode_minus'] = False
    fig, axes = plt.subplots(3, 1, figsize=(13, 10), constrained_layout=True)
    for ax, stage in zip(axes, windows):
        for family, label in FAMILIES.items():
            curve = cache[(stage, family, 'CAUSAL', 1., CORE, 1)]['result']['curve']
            ax.plot([date.fromisoformat(p['date']) for p in curve],
                    [(p['equity'] / CORE - 1) * 100 for p in curve], label=label, linewidth=1.2)
        ax.axhline(0, color='#999999', linewidth=.6)
        ax.set_title(stage + ' · 历史探索 · 100万元独立账户 / 基准成本')
        ax.set_ylabel('累计净收益 %')
        ax.grid(alpha=.18)
    axes[0].legend(loc='best', fontsize=9, ncol=2)
    fig.savefig(out / 'research.png', dpi=150)
    plt.close(fig)

    events = audits[config_id('CHAN_PEN_T3', 1.)]['events']
    # First signal after common scoring start: deterministic, not chosen for its PnL.
    example = next((e for e in events if e['confirmedIndex'] >= 80), events[0] if events else None)
    if example is None:
        return
    lo = max(0, example['pivotIndex'] - 40)
    hi = min(len(signals), example['confirmedIndex'] + 25)
    fig, ax = plt.subplots(figsize=(14, 6), constrained_layout=True)
    for i in range(lo, hi):
        b = signals[i]
        color = '#bc4b3f' if b.close >= b.open else '#2b8069'
        ax.vlines(i, b.low, b.high, color=color, linewidth=.7)
        ax.vlines(i, min(b.open, b.close), max(b.open, b.close), color=color, linewidth=3)
    ax.axhspan(example['zoneLower'], example['zoneUpper'], color='#bda66b', alpha=.18, label='冻结的重叠区域')
    ax.axvline(example['pivotIndex'], color='#777777', linestyle=':', label='回抽极值位置（当时尚未确认）')
    ax.axvline(example['confirmedIndex'], color='#bf7b2c', linestyle='--', label='结构确认 / 收盘生成信号')
    fills = []
    for stage in windows:
        fills.extend(cache[(stage, 'CHAN_PEN_T3', 'CAUSAL', 1., CORE, 1)]['result']['trades'])
    by_date = {b.timestamp.date().isoformat(): i for i, b in enumerate(data.bars)}
    first_entry = first_exit = True
    for t in fills:
        for field, price, marker, color in [('entryDate', 'entryPrice', '^' if t['direction'] > 0 else 'v', '#2560a0'),
                                           ('exitDate', 'exitPrice', 'x', '#853d77')]:
            i = by_date[t[field]]
            if lo <= i < hi:
                y = t[price] * signals[i].open / data.bars[i].open
                label = None
                if field == 'entryDate' and first_entry:
                    label = '实际模拟开仓（次日开盘）'; first_entry = False
                if field == 'exitDate' and first_exit:
                    label = '实际模拟平仓'; first_exit = False
                ax.scatter(i, y, marker=marker, color=color, s=75, zorder=5, label=label)
    ticks = list(range(lo, hi, max(1, (hi - lo) // 8)))
    ax.set_xticks(ticks, [signals[i].timestamp.date().isoformat() for i in ticks], rotation=25)
    ax.set_title('三笔近似 · 评分起点后首个信号 · 极值、确认与成交分开标记')
    ax.set_ylabel('因果换月归一化信号价格（成交价仅作同尺度换算）')
    ax.legend(fontsize=8, loc='best')
    ax.grid(alpha=.15)
    fig.savefig(out / 'signal-example.png', dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=f'docs/research/data/{DEFAULT_FOLDER}')
    parser.add_argument('--report', default='docs/research/fu-chanlun-2026-10-30.md')
    args = parser.parse_args()
    out, report_path = ROOT / args.output, ROOT / args.report
    if (out / 'manifest.json').exists() or report_path.exists():
        raise SystemExit('Preserve the frozen attempt; choose a new output and report path.')
    source = ROOT / 'docs/research/data/fu-focused-2026-10-27-r2/source-snapshot.json.gz'
    raw = gzip.decompress(source.read_bytes())
    temp = ROOT / '.test-tmp/fu-chanlun-input.json'
    temp.parent.mkdir(exist_ok=True)
    temp.write_bytes(raw)
    data = TqSdkBacktestDataProvider(cache_dir=ROOT / '.test-tmp')._read_cache(temp, 0, allow_stale=True)
    if not data or data.symbol != 'FU0' or not data.complete or len(data.bars) < 1000:
        raise ValueError('Complete audited FU evidence required')
    if any(s.volume_multiple != 10 or s.price_tick != 1 for s in data.contract_specs.values()):
        raise ValueError('Unexpected FU contract specification')
    signals = causal_prices(data)
    windows = {'DEVELOPMENT': (data.bars[80].timestamp.date(), date(2023, 12, 31)),
               'VALIDATION': (date(2024, 1, 1), date(2025, 12, 31)),
               'FINAL': (date(2026, 1, 1), data.bars[-1].timestamp.date())}
    risk = ResearchRisk()
    paths = ['backtesting/chanlun_research.py', 'scripts/research_fu_chanlun.py',
             'backtesting/independent_research.py', 'backtesting/fuel_research.py', 'backtesting/backtester.py',
             'data/tqsdk_backtest.py', 'docs/plans/2026-10-30-fu-chanlun-research.md']
    out.mkdir(parents=True, exist_ok=True)
    (out / 'source-snapshot.json.gz').write_bytes(gzip.compress(raw, mtime=0))
    manifest = {'engineVersion': ENGINE, 'status': 'POST_PRIOR_RESEARCH_HISTORICAL_EXPLORATION',
                'createdAt': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
                'source': {'symbol': data.symbol, 'provider': data.provider_symbol, 'bars': len(data.bars),
                           'first': str(data.bars[0].timestamp.date()), 'last': str(data.bars[-1].timestamp.date()),
                           'contracts': len(data.contract_specs), 'rolls': len(data.roll_events),
                           'sha256': hashlib.sha256(raw).hexdigest()},
                'windows': {k: list(map(str, v)) for k, v in windows.items()}, 'risk': asdict(risk),
                'families': FAMILIES, 'scales': SCALES, 'runCount': 180,
                'codeAndProtocolHashes': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths},
                'selection': 'All four centers fixed before return calculation; no validation-based selection.',
                'scope': 'Fixed-bottom structural overlap experiments; not the full recursive Chan theory.',
                'forwardEvidence': False, 'ordersSubmittedToBroker': 0}
    dump(out / 'manifest.json', manifest)
    print(json.dumps({'phase': 'FROZEN', 'runs': 180, 'bars': len(data.bars)}), flush=True)
    audits = {config_id(f, s): detect(signals, f, s) for f in FAMILIES for s in SCALES}
    cuts = (80, 180, 400, 800, 1200, 1500, 1800)
    checked = 0
    for f in FAMILIES:
        for s in SCALES:
            full = audits[config_id(f, s)]
            for n in cuts:
                prefix = detect(signals[:n], f, s)
                for kind in full:
                    if prefix[kind] != [e for e in full[kind] if e['confirmedIndex'] < n]:
                        raise AssertionError(f'Future observations rewrote {f}/{s}/{kind}/{n}')
                checked += 1
    dump(out / 'structure-audit.json', audits)
    cache, records, ledgers = {}, [], []

    def run(stage, family, scale=1., capital=CORE, cost=1, delay=0):
        mode = 'DELAY_1' if delay else 'CAUSAL'
        key = (stage, family, mode, scale, capital, cost)
        if key in cache:
            return cache[key]
        result = execute(data, audits[config_id(family, scale)]['events'], capital, *windows[stage],
                         cost_multiplier=cost, risk=risk, delay=delay, signal_bars=signals)
        row = {'stage': stage, 'family': family, 'mode': mode, 'scale': scale,
               'capital': capital, 'cost': cost, 'metrics': result['metrics'],
               'segments': segments(result['curve'], capital)}
        records.append(row)
        ledgers.append({'key': list(key), 'result': result})
        cache[key] = {'record': row, 'result': result}
        return cache[key]

    for stage in windows:
        for family in FAMILIES:
            for scale in SCALES:
                for cost in (1, 2):
                    run(stage, family, scale, cost=cost)
            for capital in (10_000, 100_000, CORE):
                for cost in (1, 2, 4):
                    run(stage, family, capital=capital, cost=cost)
            for cost in (1, 2):
                run(stage, family, cost=cost, delay=1)
        print(json.dumps({'phase': stage, 'completedRuns': len(records)}), flush=True)
    if len(records) != 180:
        raise AssertionError('Frozen scenario matrix not completed')
    curves = {config_id(f, s): cache[('DEVELOPMENT', f, 'CAUSAL', s, CORE, 1)]['result']['curve']
              for f in FAMILIES for s in SCALES}
    multiple = adjusted_sharpe_p(curves, CORE, [config_id(f, 1.) for f in FAMILIES])
    dump(out / 'multiple-testing.json', multiple)
    diagnostics, journal, outcomes = {}, [], []
    for family, label in FAMILIES.items():
        audit = audits[config_id(family, 1.)]
        lag = [e['confirmedIndex'] - e['pivotIndex'] for e in audit['events']]
        diagnostics[family] = {'counts': {k: len(v) for k, v in audit.items()},
                               'medianConfirmationLagBars': statistics.median(lag) if lag else None,
                               'maximumConfirmationLagBars': max(lag) if lag else None,
                               'eventsByYear': {str(y): sum(data.bars[e['confirmedIndex']].timestamp.year == y for e in audit['events'])
                                                for y in range(2019, 2027)}}
        metrics = {stage: {str(c): cache[(stage, family, 'CAUSAL', 1., CORE, c)]['record']['metrics']
                           for c in (1, 2, 4)} for stage in windows}
        excluding = {stage: sum(t['netPnl'] for t in cache[(stage, family, 'CAUSAL', 1., CORE, 1)]['result']['trades']) -
                     max((t['netPnl'] for t in cache[(stage, family, 'CAUSAL', 1., CORE, 1)]['result']['trades']), default=0)
                     for stage in windows}
        neighbor = {stage: sum(cache[(stage, family, 'CAUSAL', s, CORE, 2)]['record']['metrics']['netPnl'] > 0 for s in SCALES)
                    for stage in windows}
        p = multiple['selected'][config_id(family, 1.)]['adjustedP']
        gates = {'developmentSample': metrics['DEVELOPMENT']['1']['closedTrades'] >= 30,
                 'validationSample': metrics['VALIDATION']['1']['closedTrades'] >= 15,
                 'finalSample': metrics['FINAL']['1']['closedTrades'] >= 8,
                 'positiveBaseAndDoubleCosts': all(m[str(c)]['netPnl'] > 0 for m in metrics.values() for c in (1, 2)),
                 'drawdown': all(m['1']['maxDrawdownPct'] <= 8 for m in metrics.values()),
                 'excludeBest': all(v > 0 for v in excluding.values()),
                 'neighbors': all(v >= 2 for v in neighbor.values()), 'multipleTesting': p <= .1}
        outcomes.append({'family': family, 'metrics': metrics, 'gates': gates,
                         'observationQualified': all(gates.values()), 'excludeBest': excluding,
                         'positiveStressNeighbors': neighbor, 'adjustedP': p})
        reasons = []
        names = {'developmentSample': '开发成交不足30笔', 'validationSample': '2024—2025成交不足15笔',
                 'finalSample': '2026成交不足8笔', 'positiveBaseAndDoubleCosts': '至少一个窗口基准或双倍成本不盈利',
                 'drawdown': '最大收盘回撤超过8%', 'excludeBest': '至少一窗口去掉最好一笔不再盈利',
                 'neighbors': '邻近尺度双倍成本盈利未覆盖多数', 'multipleTesting': '多重尝试校正未达门槛'}
        reasons = [names[k] for k, v in gates.items() if not v]
        lesson = ('严格确认显著减少可用样本；需要真实更细级别数据，不能放宽规则后冒称原理论获证。'
                  if family == 'CHAN_SEGMENT_T3' else
                  '三笔重叠是近似；延迟与成本检验必须保留，不能替代完整递归中枢。'
                  if family == 'CHAN_PEN_T3' else '对照也需检验成本、失效退出和窗口稳定性，不能用某一段盈利代替持续优势。')
        journal.append({'family': family, 'name': label, 'hypothesis': label + '是否提供扣费后可持续的方向性优势',
                        'base': metrics['DEVELOPMENT']['1'], 'failureReasons': reasons, 'lesson': lesson,
                        'repairs': {'predeclaredScales': SCALES, 'delayedExecution': True, 'noPostHocRepair': True}})
    verification = {'prefixInvarianceChecks': checked, 'futureRewrites': 0, 'runs': len(records),
                    'cashReconciledRuns': len(records), 'ordersSubmittedToBroker': 0,
                    'allFillsAfterConfirmation': all(t['confirmedDate'] < t['entryDate'] for l in ledgers for t in l['result']['trades']),
                    'codeAndProtocolHashesStillMatch': all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h
                                                           for p, h in manifest['codeAndProtocolHashes'].items())}
    if not verification['allFillsAfterConfirmation'] or not verification['codeAndProtocolHashesStillMatch']:
        raise AssertionError('Frozen implementation verification failed')
    results = {'status': 'HISTORICAL_EXPLORATION_NOT_FULL_CHAN_THEORY_VALIDATION', 'runCount': len(records),
               'qualifiedCount': sum(o['observationQualified'] for o in outcomes), 'outcomes': outcomes,
               'diagnostics': diagnostics, 'noIndependentValidationClaim': True,
               'source': manifest['source'], 'ordersSubmittedToBroker': 0}
    dump(out / 'results.json', results)
    dump(out / 'verification.json', verification)
    dump(out / 'failure-journal.json', journal)
    dump(out / 'all-runs.json', records)
    (out / 'full-ledgers.json.gz').write_bytes(gzip.compress(json.dumps(ledgers, ensure_ascii=False, allow_nan=False).encode(), mtime=0))
    flattened = [{**{k: v for k, v in r.items() if k not in ('metrics', 'segments')},
                  **{k: v for k, v in r['metrics'].items() if k != 'denials'},
                  'denials': json.dumps(r['metrics']['denials'])} for r in records]
    with (out / 'all-runs.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(flattened[0]))
        writer.writeheader(); writer.writerows(flattened)
    chart(out, data, signals, audits, cache, windows)
    report(out, report_path, results, cache, windows, verification)
    print(json.dumps({'runs': len(records), 'qualified': results['qualifiedCount'],
                      'centerSignalCounts': {f: diagnostics[f]['counts']['events'] for f in FAMILIES}}), flush=True)


def report(out, path, results, cache, windows, verification):
    relative = 'data/' + out.name + '/'
    lines = ['# 燃油：缠论结构与突破回踩研究', '',
             f"冻结日期：2026-10-30。真实FU交割合约日线 {results['source']['bars']} 根，{results['source']['first']} 至 {results['source']['last']}。",
             '', f"完成180个场景；通过预定全部门槛：{results['qualifiedCount']}组。所有窗口已在其他研究中使用，本轮属于历史探索。",
             '', '## 本轮回答什么', '',
             '检验固定底层上的特征序列线段重叠、三笔重叠近似，是否比普通突破回踩或直接突破增加可交易价值。只检验本文冻结的研究版本，不把它等同于原著全部递归走势类型，也不据此断言整个缠论有效或无效。',
             '', '线段研究版采用第67课有/无特征序列缺口的两种确认路径；特征元素包含按当前段方向合并。数据开头可能位于未完成线段中，先跳过不满足三笔交集的未知前缀；一旦建立起点就不再跳过或回写已发布结构。保守确认笔需要再一个合法反向端点，确认延迟是规则的一部分。',
             '', '## 固定中心规则结果', '',
             '下表均为100万元独立账户、基准模型成本、整个窗口累计净收益；不是年化收益，不是四组资金合并为一个账户。', '',
             '| 研究版本 | 窗口 | 累计净收益 | 收盘回撤 | 平仓笔数 | 双倍成本收益 |',
             '|---|---|---|---|---|---|']
    labels = {'DEVELOPMENT': '2019—2023', 'VALIDATION': '2024—2025', 'FINAL': '2026至快照末日'}
    for f, label in FAMILIES.items():
        for stage in windows:
            m = cache[(stage, f, 'CAUSAL', 1., CORE, 1)]['record']['metrics']
            stress = cache[(stage, f, 'CAUSAL', 1., CORE, 2)]['record']['metrics']
            lines.append(f"| {label} | {labels[stage]} | {m['returnPct']:+.3f}% | {m['maxDrawdownPct']:.3f}% | {m['closedTrades']} | {stress['returnPct']:+.3f}% |")
    lines += ['', f'![四组固定规则资金曲线]({relative}research.png)', '', '## 结构确认究竟有多晚', '',
              '| 版本 | 全历史确认事件 | 笔 | 线段 | 重叠区域 | 极值至确认中位交易日数 | 最大交易日数 |',
              '|---|---|---|---|---|---|---|']
    for f, label in FAMILIES.items():
        d = results['diagnostics'][f]; c = d['counts']
        lines.append(f"| {label} | {c['events']} | {c['pens']} | {c['segments']} | {c['zones']} | {d['medianConfirmationLagBars']} | {d['maximumConfirmationLagBars']} |")
    lines += ['', '计数是同一历史内的确认事件；并非全部都成交，也不是独立策略数量。笔/段可能使用了日线之前的完整预热，分窗口账户仍从规定评分起点开始。', '',
              '结构极值可以画在过去，但订单只在确认之后的开盘产生。末尾未完成结构保持未完成，绝不拿完整历史重算后回填低点成交。确认后若已触及区域、开盘跳回无效边界、换月或风险不足，则取消。', '']
    if (out / 'signal-example.png').exists():
        lines += [f'![首个信号的极值确认与真实模拟成交点]({relative}signal-example.png)', '',
                  '图例固定选择评分起点后首个三笔近似信号，未按盈利挑图。K线使用因果换月信号尺度；实际模拟成交标记按该日比例换算到同一尺度，账本保留真实合约原价。', '']
    lines += ['## 不同资金规模', '', '| 版本 | 窗口 | 初始资金 | 累计净收益 | 平仓笔数 | 不足一手拒单 |', '|---|---|---|---|---|---|']
    for f, label in FAMILIES.items():
        for stage in ('VALIDATION', 'FINAL'):
            for capital in (10_000, 100_000, CORE):
                m = cache[(stage, f, 'CAUSAL', 1., capital, 1)]['record']['metrics']
                lines.append(f"| {label} | {labels[stage]} | {capital:,} | {m['returnPct']:+.3f}% | {m['closedTrades']} | {m['denials'].get('RISK_OR_MARGIN_BELOW_ONE_LOT', 0)} |")
    lines += ['', '## 失败与能学到什么', '']
    for o in results['outcomes']:
        d = results['diagnostics'][o['family']]
        failed = [k for k, v in o['gates'].items() if not v]
        lines += [f"### {FAMILIES[o['family']]}", '',
                  f"全历史{d['counts']['events']}个事件；未通过项：{', '.join(failed) or '无'}。开发联合多重尝试校正p={o['adjustedP']:.4f}，为固定10日分块近似，不是获利概率。", '',
                  f"各窗口去掉最好一笔后的净额：{json.dumps(o['excludeBest'], ensure_ascii=False)}。", '']
    lines += ['## 执行、证据和局限', '',
              '- 四组使用相同2ATR保护、4ATR目标、20根持仓上限和结构失效退出；更高成本会改变整数手数，不能只从旧收益机械减费用。',
              '- 每笔预算为初始资金与当前现金较小者的0.5%；保证金≤20%、名义敞口≤2倍，资金不足一手不交易。1万资金的零成交不表示策略安全。',
              '- 次日开盘仅用此前完整日线、当日开盘和已知换月证据决定订单，不用当日量/高低/收盘挑选入场。历史日费率、涨跌停排队、盘中路径和实际强平仍不完整，结果是条件性模拟。',
              '- 同根止损/目标双触先止损；目标限价不扣不利滑点；跳空可超过预算；换月旧仓平仓，不自动开新；窗口末假设清算单列。收盘回撤不等于盘中最大风险。',
              '- 预定的180个场景包含邻域、资金、费用及额外一日确认延迟对照，不等于180个独立想法；本轮不按成绩挑选规则，也不临时放宽阈值。',
              '- 日线上的次级结构不能替代分钟数据的递归走势类型。若线段研究版样本过少，下一步先取得真实分钟及交割合约数据，并先冻结新实验，不能凭本轮低回撤宣称有效。',
              '', f"完成{verification['prefixInvarianceChecks']}项真实数据截断/追加核验，历史事件重写数为0；180个账本现金对账通过，所有成交均晚于确认日期。没有实盘或模拟账户写入。", '',
              f'[研究协议](../plans/2026-10-30-fu-chanlun-research.md) · [数据与代码指纹]({relative}manifest.json) · [完整结构与信号审计]({relative}structure-audit.json) · [全部场景CSV]({relative}all-runs.csv) · [全部逐笔及决策账本]({relative}full-ledgers.json.gz) · [核验结果]({relative}verification.json)', '',
              '原文依据：[第62课](https://blog.sina.com.cn/s/blog_486e105c01000bf2.html)、[第67课](https://blog.sina.com.cn/s/blog_486e105c01000c16.html)、[第21课原文存档](https://eczsc.com/originals/21)。本报告的算法口径、执行假设和统计结论均为项目研究定义。']
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
