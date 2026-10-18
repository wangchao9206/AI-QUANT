"""Conditional, inspectable event rules; no sentiment-to-trade conversion."""
import re

RULES = [
    ('货币与流动性', ['利率','降息','加息','降准','货币政策','美元','fomc','federal funds','monetary policy','interest rate','discount rate'],
     ['AUM','AGM','TM','IFM'], '政策变化 → 利率与汇率预期 → 贵金属估值、债券与股指风险偏好',
     '宽松可能支持估值；若同时出现衰退、美元走强或抛售换取现金，短期价格可能反向。',
     ['政策相对市场预期的差异','实际利率与美元是否同向确认','境内政策与跨市场时差']),
    ('通胀与价格数据', ['居民消费价格','工业生产者出厂价格','通胀','cpi','ppi','inflation'],
     ['AUM','AGM','TM','IFM'], '价格数据 → 通胀与政策反应预期 → 实际利率、需求及风险资产估值',
     '价格上涨可能来自需求改善或供给冲击，意义不同；同比也受基数影响，不能直接翻译成单边交易方向。',
     ['同比与环比、核心与总项','相对当时市场预期的差异','供给成本还是终端需求驱动']),
    ('能源供需', ['原油','石油','成品油','opec','crude','petroleum','oil','natural gas'],
     ['SCM','FUM','LUM','BUM','PGM'], '产量、库存或运输变化 → 能源可用供应 → 炼化成本与下游利润',
     '供应收缩可能支撑成本，但需求走弱、库存释放或替代供给会抵消影响。',
     ['实物供应损失与持续时间','库存及炼厂开工变化','运费、汇率与内外盘价差']),
    ('煤焦钢链', ['煤炭','焦煤','焦炭','动力煤','钢铁','螺纹','铁矿','保供'],
     ['ZCM','JMM','JM','RBM','IM'], '产能或保供政策 → 煤矿与钢厂供给、利润 → 黑色产业链重新定价',
     '限产与保供的方向可能相反；原料涨价也可能压缩钢厂利润并抑制采购。',
     ['政策适用地区与执行日期','港口和厂库、产量是否验证','需求端与交易所风控通知']),
    ('农业供需', ['大豆','豆粕','玉米','棕榈','油脂','种植','天气','soybean','corn','wheat','acreage','crop'],
     ['MM','YM','CM','PM','AM'], '面积、单产与出口变化 → 供需平衡预期 → 饲料及油脂成本',
     '总产量还取决于单产与天气；进口节奏、汇率、油粕分配会使境内品种反应不同。',
     ['原始报告与此前预测的差异','后续天气及出口装运','境内到港、压榨和库存']),
    ('有色与供应中断', ['铜','铝','镍','锌','锡','矿山','copper','aluminum','nickel','mine'],
     ['CUM','ALM','NIM','ZNM','SNM'], '矿端或冶炼供给变化 → 可交割库存与升贴水 → 有色价格和期限结构',
     '减产不一定等于净缺口；复产、替代供应和终端需求下降可能抵消冲击。',
     ['企业原始公告和影响吨数','可交割库存与升贴水','交易所限仓、保证金与流动性']),
    ('交易与交割规则', ['保证金','涨跌停','限仓','交割','暂停交易','suspension','margin requirement'],
     [], '规则变更 → 交易资格、资金占用与可成交性 → 执行风险变化',
     '规则调整首先影响执行风险，不能仅凭该公告判断价格方向。',
     ['原公告适用合约','生效时点与过渡安排','持仓和资金是否满足新规则']),
]


def contains(text, term):
    return bool(re.search(r'\b' + re.escape(term) + r'\b', text, re.I)) if term.isascii() else term in text


def interpret(item):
    text = item['title'] + ' ' + item.get('summary', '')
    matches = [r for r in RULES if any(contains(text, word) for word in r[1])]
    if item.get('sourceId') == 'shfe' and RULES[-1] not in matches:
        matches.append(RULES[-1])
    related = list(dict.fromkeys(item.get('relatedSymbols', []) + [s for r in matches for s in r[2]]))
    result = dict(item, relatedSymbols=related,
                  interpretationBasis='标题关键词与公开产业链规则；未读取全文、未计算胜率',
                  verificationStatus='待交叉核验', eventTypes=[r[0] for r in matches])
    result['analysis'] = [{'eventType': r[0], 'chain': r[3], 'conditions': r[4],
                           'checks': r[5]} for r in matches]
    if not matches:
        result['analysis'] = [{'eventType': '尚未归类', 'chain': '标题不足以建立明确的品种传导链',
                               'conditions': '需要阅读原文并确认增量事实，暂不推断利多或利空。',
                               'checks': ['核对原始发布者和原文','确认适用地区、品种与时间','查找独立数据验证']}]
    if any(r[0] == '交易与交割规则' for r in matches): result['topic'] = '交易规则'
    elif any(r[0] in ('货币与流动性', '通胀与价格数据') for r in matches): result['topic'] = '宏观政策'
    return result
