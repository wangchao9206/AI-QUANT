"""Representative event evidence, not an ex-post predictive ranking."""
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path

WATCH_SOURCES = [
    {'name':'发改委 / 国家统计局', 'url':'https://www.ndrc.gov.cn/xwdt/xwfb/', 'scope':'煤焦钢、能源与宏观政策；对照产量和库存', 'collection':'发改委和统计局列表已接入，逐源状态见来源页'},
    {'name':'上海期货交易所', 'url':'https://www.shfe.com.cn/publicnotice/notice/', 'scope':'实际合约、交割、暂停、限仓与保证金', 'collection':'公告列表已接入'},
    {'name':'USDA NASS', 'url':'https://www.nass.usda.gov/rss/news.xml', 'scope':'粮油种植、产量与统计修订', 'collection':'官方RSS已接入；以原文日期判断更新程度'},
    {'name':'EIA 周度石油报告', 'url':'https://www.eia.gov/petroleum/supply/weekly/', 'scope':'能源库存、产量和炼厂运行', 'collection':'人工核验入口；已接入的Today in Energy订阅不等同本周报快讯'},
    {'name':'农业农村部', 'url':'https://www.moa.gov.cn/', 'scope':'疫情、畜牧存栏、种植与供需', 'collection':'人工核验入口；尚未自动采集'},
    {'name':'美联储', 'url':'https://www.federalreserve.gov/feeds/press_all.xml', 'scope':'黄金、白银、债券与股指的宏观条件', 'collection':'官方RSS已接入'},
    {'name':'Vale / 上市公司原始公告', 'url':'https://www.vale.com/', 'scope':'矿产停产、发运、复产与影响量修订', 'collection':'案例已核验；企业公告实时监听尚未接入'},
    {'name':'LME', 'url':'https://www.lme.com/Market-data/disruption-events', 'scope':'外盘交易中断与执行规则', 'collection':'案例已核验；自动公告订阅尚未接入'},
    {'name':'OPEC', 'url':'https://www.opec.org/', 'scope':'减产会议、承诺与执行安排', 'collection':'案例已核验；自动公告订阅尚未接入'},
]


def price_window(bars, event_date):
    """Day-precision releases use sessions strictly AFTER their local date."""
    valid = sorted((b for b in bars if math.isfinite(b.close) and b.close > 0), key=lambda b:b.timestamp)
    before = [b for b in valid if b.timestamp.date() < event_date]
    after = [b for b in valid if b.timestamp.date() > event_date]
    if not before or not after:
        return {'status':'INSUFFICIENT'}
    baseline = before[-1]
    if (event_date - baseline.timestamp.date()).days > 10 or (after[0].timestamp.date() - event_date).days > 10:
        return {'status':'INSUFFICIENT'}
    result = {'status':'OBSERVED', 'baselineDate':baseline.timestamp.date().isoformat(), 'baselineClose':baseline.close,
              'before20Pct':round((baseline.close / before[-21].close - 1)*100, 3) if len(before)>=21 else None}
    for horizon in (5,20):
        bar = after[horizon-1] if len(after)>=horizon else None
        result[f'after{horizon}Pct'] = round((bar.close / baseline.close - 1)*100,3) if bar else None
        result[f'after{horizon}Date'] = bar.timestamp.date().isoformat() if bar else None
    return result


def event_study(histories):
    cases = json.loads(Path(__file__).with_name('event_cases.json').read_text(encoding='utf-8'))
    loaded = {}
    for case in cases:
        case['windows'] = []
        # Beijing date for the Fed's 17:00 EDT release.
        anchor = date.fromisoformat('2020-03-16' if case['id']=='fed-2020' else case['eventDate'])
        for symbol in case['relatedSymbols']:
            if symbol not in loaded:
                try:
                    loaded[symbol] = histories.get_historical_bars(symbol[:-1]+'0', allow_download=False)
                except Exception:
                    loaded[symbol] = []
            case['windows'].append({'symbol':symbol, **price_window(loaded[symbol], anchor)})
    return {'scope':'2016-10-18至2026-10-18，国内期货主要板块的8个代表事件；另列2016供给侧改革背景。非所有品种穷举。',
            'methodology':'人工核验原始发布，区分事件、公开、执行与网页迁移时间；全部案例均未证明绝对最早来源。价格窗口采用本地公开主连日线：基准为发布日前最后收盘，之后第5/20个交易日收盘；日期精度不足时不取当日收盘作为事件后观测终点；变化仍是从发布前收盘到终点的累计变化，包含期间所有日线，不代表次日能以前日价格成交。前20日变化用于识别已先行的行情。主连可能含换月价差，窗口变化不等于可交易收益；不检验因果或胜率，代表案例存在选择偏差。',
            'items':cases, 'watchSources':WATCH_SOURCES, 'generatedAt':datetime.now(timezone.utc).isoformat()}
