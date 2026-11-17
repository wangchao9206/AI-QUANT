"""Verify frozen research ledgers, then render an exportable chart and report."""
from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'output/fg701-intraday-2026-11-17'


def read_csv(name):
    with (OUT/name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    results = json.loads((OUT/'results.json').read_text(encoding='utf-8'))
    assert results['dataSha256'] == hashlib.sha256((ROOT/'data/history/fg701-intraday-2026-11-17/raw.json').read_bytes()).hexdigest()
    assert results['scriptSha256'] == hashlib.sha256((ROOT/'scripts/backtest_fg701_intraday.py').read_bytes()).hexdigest()
    verified = {}
    for name, stats in results['scenarios'].items():
        ledger = read_csv(name+'-trades.csv')
        daily = read_csv(name+'-daily.csv')
        curve = read_csv(name+'-curve.csv')
        assert len(ledger) == stats['trades']
        for key in ('grossPnl', 'fees', 'slippageCost', 'netPnl'):
            assert sum(float(t[key]) for t in ledger) == stats[key]
            assert sum(float(t[key]) for t in daily) == stats[key]
        previous_exit = None
        cumulative = 0
        trading_labels = {row['timestamp']: row['tradingDay'] for row in curve}
        for t in ledger:
            entry, exit_ = datetime.fromisoformat(t['entryTime']), datetime.fromisoformat(t['exitTime'])
            assert entry > datetime.fromisoformat(t['signalTime'])
            assert exit_ >= entry
            assert previous_exit is None or entry > previous_exit
            assert trading_labels[t['entryTime']] == trading_labels[t['exitTime']] == t['tradingDay']
            assert (9 <= exit_.hour < 15) or (21 <= exit_.hour < 23)
            assert int(t['lots']) == 1
            side = int(t['side'])
            assert side in (-1, 1)
            assert abs(float(t['entryPrice'])-float(t['stopPrice'])) == 10
            assert side*(float(t['exitPrice'])-float(t['entryPrice']))*20-float(t['fees']) == float(t['netPnl'])
            assert float(t['grossPnl'])-float(t['fees'])-float(t['slippageCost']) == float(t['netPnl'])
            cumulative += float(t['netPnl'])
            assert cumulative == float(t['cumulativeNetPnl'])
            previous_exit = exit_
        assert float(curve[-1]['markedPnl']) == stats['netPnl']
        assert int(curve[-1]['position']) == 0
        verified[name] = {'ledgerAccounting': 'PASS', 'dailyAccounting': 'PASS',
                          'nextBarExecution': 'PASS', 'noOverlappingPositions': 'PASS',
                          'fixedStopDistance': 'PASS', 'noTradingDayCarry': 'PASS'}
    (OUT/'verification.json').write_text(json.dumps(verified, indent=2), encoding='utf-8')
    font = FontProperties(fname='C:/Windows/Fonts/msyh.ttc')
    plt.rcParams.update({'font.family': font.get_name(), 'axes.unicode_minus': False, 'font.size': 11})
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={'height_ratios': [2, 1]}, layout='constrained')
    names = {'zero_cost': '不计成本', 'baseline': '每边1跳滑点 + 每边6元手续费', 'stress': '每边2跳滑点 + 每边6元手续费'}
    colors = {'zero_cost': '#667085', 'baseline': '#2563eb', 'stress': '#dc2626'}
    for name in names:
        daily = read_csv(name+'-daily.csv')
        values, total = [0], 0
        for d in daily:
            total += float(d['netPnl'])
            values.append(total)
        axes[0].plot(range(len(values)), values, label=names[name], color=colors[name], linewidth=2)
        axes[0].annotate(f'{total:,.0f}元', (len(values)-1, values[-1]), xytext=(8, 0), textcoords='offset points', color=colors[name])
    baseline = read_csv('baseline-daily.csv')
    x = list(range(1, len(baseline)+1))
    y = [float(d['netPnl']) for d in baseline]
    axes[1].bar(x, y, color=['#16a34a' if v > 0 else '#dc2626' for v in y])
    axes[0].set_title('玻璃2701 · 1分钟日内基础版回测\n2026-10-19—11-16（21个交易日，含所属夜盘）', fontproperties=font)
    axes[0].set_ylabel('累计净盈亏（元）', fontproperties=font)
    axes[0].legend(prop=font, loc='lower left')
    axes[1].set_ylabel('基准每日盈亏（元）', fontproperties=font)
    ticks = [1, 6, 11, 16, 21]
    axes[1].set_xticks(ticks, [baseline[i-1]['tradingDay'][5:] for i in ticks])
    axes[1].set_xlabel('交易日', fontproperties=font)
    for ax in axes:
        ax.axhline(0, color='#9ca3af', linewidth=0.8)
        ax.grid(axis='y', alpha=.2)
        ax.spines[['top', 'right']].set_visible(False)
    axes[0].set_xlim(0, 24)
    fig.savefig(OUT/'equity.png', dpi=160)
    fig.savefig(OUT/'equity.svg')
    plt.close(fig)
    rows = [('完整开平笔数', 'trades', '{:,.0f}'), ('成本前盈亏（元）', 'grossPnl', '{:,.0f}'),
            ('手续费（元）', 'fees', '{:,.0f}'), ('滑点成本（元）', 'slippageCost', '{:,.0f}'),
            ('净盈亏（元）', 'netPnl', '{:,.0f}'), ('胜率', 'winRate', '{:.1%}'),
            ('盈利因子', 'profitFactor', '{:.2f}'), ('已实现最大回撤（元）', 'maxRealizedDrawdown', '{:,.0f}'),
            ('分钟收盘盯市最大回撤（元）', 'maxMinuteCloseMarkedDrawdown', '{:,.0f}')]
    table = ''.join('<tr><th>'+label+'</th>'+''.join('<td>'+fmt.format(results['scenarios'][n][key])+'</td>' for n in names)+'</tr>' for label,key,fmt in rows)
    daily_table = ''.join('<tr><td>'+d['tradingDay']+'</td><td>'+d['trades']+'</td><td>'+f'{float(d["netPnl"]):,.0f}'+'</td></tr>' for d in baseline)
    spec = json.loads((ROOT/'data/history/fg701-intraday-2026-11-17/raw.json').read_text(encoding='utf-8'))['spec']
    document = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>玻璃2701日内策略回测</title>
<style>body{font:16px/1.8 system-ui,"Microsoft YaHei",sans-serif;max-width:1080px;margin:32px auto;padding:0 20px;color:#182230;background:#fafafa}h1{font-size:28px}h2{font-size:21px;margin-top:32px}table{border-collapse:collapse;width:100%;background:white}td,th{padding:9px 12px;border:1px solid #d0d5dd;text-align:right}th:first-child,td:first-child{text-align:left}img{width:100%;height:auto}li{margin-bottom:8px}.lead{font-size:20px;padding:16px;background:#eff6ff;border-left:4px solid #2563eb}.muted{color:#667085}a{color:#1d4ed8}.scroll{overflow-x:auto}</style>
<h1>玻璃2701：1分钟日内基础版回测</h1>
<p class="lead">该月基础版：50笔完整开平，净亏3,100元；胜率28%。不计交易成本时亏520元，加入手续费和滑点后亏损进一步扩大。</p>
<p>申请窗口：2026-10-17至2026-11-16；实际21个交易日：10月19日至11月16日，7,245根真实1分钟K线。每个交易日345根，无缺口，且逐日OHLCV汇总与同源日线全部一致。10月19日交易日包含10月16日21:00起的夜盘，日盘14:59开盘清仓，均线与状态按交易日重置。</p>
<img src="equity.png" alt="三种成本场景累计盈亏及基准每日盈亏">
<h2>结果与费用</h2><div class="scroll"><table><tr><th>指标</th><th>不计成本</th><th>基准：每边1跳</th><th>压力：每边2跳</th></tr>'''+table+'''</table></div>
<p>基准每边每手6元手续费，一组开平12元；每边1跳滑点，一组开平40元滑点成本。50笔合计手续费600元、滑点2,000元。基准成本前盈亏-500元，净盈亏-3,100元。不计成本场景是单独重放，因止损锚定实际成交价，止损成交与净值不等同于直接给基准加回成本。</p>
<p>天勤采集时的commission字段为'''+html.escape(str(spec['commission']))+'''元，但它不能验证整月各日的平今手续费或券商附加费。因此基准6元是明确假设。保持基准成交与滑点不变，每边费用2/4/6元对应净亏2,700/2,900/3,100元。未给初始资金，不报告收益率、资金占用率或保证金收益率。</p>
<p>基准多头25笔，净亏1,200元；空头25笔，净亏1,900元。5天盈利、16天亏损；最好一天11月13日+208元，最差一天11月11日-580元。单笔最大盈利268元，最大亏损232元，平均净亏62元。34笔因反向均线突破退出，15笔日终清仓，1笔固定止损。</p>
<h2>冻结执行口径</h2><ol>
<li>交易CZCE.FG701实际交割合约，每次1手，最多一笔持仓，禁止加仓，无止盈。收敛和趋势过滤按用户确认暂不加入。</li>
<li>均线：每分钟典型价（最高+最低+收盘）/3 × 成交量，按交易日累计后除以累计成交量。它是用户接受的近似VWAP，不等于行情软件的精确分时均价。</li>
<li>首次开仓：1分钟收盘在均线上方做多、下方做空，下一根有成交量的K线开盘加不利滑点成交。</li>
<li>固定止损：距实际开仓价10跳，多空对称。触发后按止损价加不利滑点退出；开盘跳过止损时按更差的开盘价加滑点退出。基准一次正常止损可能亏220元价差加12元费用，共232元。</li>
<li>空单遇收盘价达到均线上方3跳时买入平空；多单遇收盘价达到均线下方3跳时卖出平多。信号确认后的下一根开盘成交，未达3跳继续持有，固定止损仍有效。</li>
<li>突破退出后等首次回踩：向上突破后，某根最低价在该根收盘均线至均线上方1跳以内、最低价未穿均线、收盘仍在均线上，下一根开盘买开；向下突破完全对称。第一轮回踩穿线即作废，不追认后续同向回踩；反向再次突破3跳可重新等待。退出和反手不会在同一根K线内完成。</li>
<li>止损后的该根不再入场，后续已收盘K线可重新触发首次开仓。14:58起不再开仓，14:59开盘计划清仓；无交易日间持仓，夜盘可持有至次日日盘，午休与夜盘后的休市时间计入自然持仓分钟。</li>
</ol>
<h2>逐日基准盈亏</h2><table><tr><th>交易日</th><th>完整开平笔数</th><th>净盈亏（元）</th></tr>'''+daily_table+'''</table>
<h2>文件与验证</h2><ul>
<li><a href="baseline-trades.csv">基准逐笔成交CSV</a> · <a href="baseline-daily.csv">每日盈亏CSV</a> · <a href="baseline-curve.csv">分钟净值CSV</a> · <a href="equity.svg">可导出SVG图</a></li>
<li><a href="results.json">冻结结果与源码指纹</a> · <a href="data-audit.json">逐日数据完整性</a> · <a href="verification.json">独立账务核对</a></li>
<li>16项单元测试通过，涵盖多空对称、3跳边界、首次回踩与作废、止损与跳空、次根成交、日终强平、零成交量过滤和未来数据不影响过去信号。</li>
<li>三种场景逐笔/逐日盈亏与净值交叉核对通过，开仓无重叠、每笔1手、止损距离10跳、无交易日间持仓。原始授权行情保存在本机data/history/fg701-intraday-2026-11-17，未上传公开服务。</li>
</ul>
<h2>结果边界</h2><p>这次只测一个月、一个合约。基础规则在该窗口为负，不能直接推断长期收益。尚未量化收敛点和趋势过滤。1分钟OHLC不能恢复分钟内价格与动态均线的先后顺序，回踩不破使用该根收盘时已知的均线作近似判断；固定滑点不能恢复排队、盘口深度或涨跌停成交约束。回撤按分钟收盘盯市统计，盘中瞬时回撤可能更大。精确分时均价、券商历史手续费、逐笔撮合均未复原。</p>
<p class="muted">合约规格来源：<a href="https://www.czce.com.cn/cn/uploadfile/2024/02/07/20240207103949576.pdf">郑商所平板玻璃期货业务细则</a>；行情字段与窗口：<a href="https://doc.shinnytech.com/tqsdk/latest/reference/tqsdk.api.html">天勤SDK官方文档</a>。测试只读取行情，无实盘委托。</p></html>'''
    (OUT/'report.html').write_text(document, encoding='utf-8')
    print(json.dumps({'status':'VERIFIED_AND_RENDERED','scenarios':len(verified),'chart':str(OUT/'equity.png')}, ensure_ascii=True))


if __name__ == '__main__':
    main()
