"""Auditable analysis of supplied fills; never authenticates a person's account."""
from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import defaultdict, deque
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

SHANGHAI = ZoneInfo('Asia/Shanghai')
ZERO = Decimal(0)


class LedgerRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', populate_by_name=True)
    csv_text: str = Field(alias='csvText', min_length=1, max_length=1_000_000)
    source_label: str = Field(alias='sourceLabel', min_length=1, max_length=150)
    source_url: str = Field(default='', alias='sourceUrl', max_length=1000)
    rights_confirmed: bool = Field(default=False, alias='rightsConfirmed')


ALIASES = {
    'trade_id': ['trade_id', '成交编号'], 'time': ['time', '成交时间'],
    'contract': ['contract', '合约'], 'side': ['side', '买卖'],
    'offset': ['offset', '开平'], 'price': ['price', '成交价'],
    'quantity': ['quantity', '手数'], 'multiplier': ['multiplier', '合约乘数'],
    'fee': ['fee', '手续费'],
}
SIDE = {'BUY':'BUY', 'SELL':'SELL', '买':'BUY', '卖':'SELL', '买入':'BUY', '卖出':'SELL'}
OFFSET = {'OPEN':'OPEN','开':'OPEN','开仓':'OPEN','CLOSE':'CLOSE','平':'CLOSE','平仓':'CLOSE',
          'CLOSETODAY':'CLOSETODAY','平今':'CLOSETODAY','CLOSEYESTERDAY':'CLOSEYESTERDAY','平昨':'CLOSEYESTERDAY'}


def number(value, field, row):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or abs(result) > Decimal('1e15'): raise InvalidOperation()
        return result
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f'第{row}行{field}不是有效有限数值') from None


def read_fills(text):
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    headers = [str(h).strip() for h in (reader.fieldnames or [])]
    if len(headers) != len(set(headers)): raise ValueError('CSV存在重复列名')
    columns = {}
    for key, aliases in ALIASES.items():
        found = [h for h in headers if h in aliases]
        if len(found) != 1: raise ValueError(f'需要且只能有一列：{key}（{aliases[-1]}）')
        columns[key] = reader.fieldnames[headers.index(found[0])]
    fills = []; seen = set(); multipliers = {}
    for row_number, raw in enumerate(reader, 2):
        if len(fills) >= 5000: raise ValueError('单次最多分析5000条成交，请分段并保留期初持仓衔接')
        if None in raw or any(raw.get(c) is None for c in columns.values()): raise ValueError(f'第{row_number}行列数不一致')
        row = {key: raw[col].strip() for key,col in columns.items()}
        trading_day_col = next((h for h in (reader.fieldnames or []) if h.strip() in ('trading_day','交易日')), None)
        day_text = (raw.get(trading_day_col) or '').strip() if trading_day_col else ''
        try: row['trading_day'] = date.fromisoformat(day_text) if day_text else None
        except ValueError: raise ValueError(f'第{row_number}行交易日无效') from None
        if not row['trade_id'] or len(row['trade_id']) > 100: raise ValueError(f'第{row_number}行缺少有效成交编号')
        contract = row['contract'].upper()
        if not re.fullmatch(r'(?:[A-Z]{2,6}\.)?[A-Z]{1,6}\d{3,4}', contract):
            raise ValueError(f'第{row_number}行需要实际交割合约，不能使用主连或连续代码')
        try:
            if not re.match(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}', row['time']): raise ValueError()
            stamp = datetime.fromisoformat(row['time'])
            if stamp.tzinfo is None: stamp = stamp.replace(tzinfo=SHANGHAI)
            stamp = stamp.astimezone(SHANGHAI)
        except ValueError:
            raise ValueError(f'第{row_number}行成交时间无效，请使用ISO日期时间') from None
        execution_key = (row['trading_day'] or stamp.date(), contract, row['trade_id'])
        if execution_key in seen: raise ValueError(f'第{row_number}行同交易日同合约成交编号重复，未静默去重')
        seen.add(execution_key)
        side = SIDE.get(row['side'].upper()); offset = OFFSET.get(row['offset'].upper())
        if side is None or offset is None: raise ValueError(f'第{row_number}行买卖或开平标记无效')
        for key in ['price','quantity','multiplier','fee']: row[key] = number(row[key],key,row_number)
        if row['quantity'] <= 0 or row['quantity'] != row['quantity'].to_integral_value(): raise ValueError(f'第{row_number}行手数必须为正整数')
        if row['multiplier'] <= 0 or row['fee'] < 0: raise ValueError(f'第{row_number}行乘数必须为正，手续费不能为负；返还请单独核对')
        if contract in multipliers and multipliers[contract] != row['multiplier']: raise ValueError(f'第{row_number}行同一合约乘数不一致')
        multipliers[contract] = row['multiplier']
        fills.append({**row,'contract':contract,'time':stamp,'side':side,'offset':offset,'line':row_number})
    if not fills: raise ValueError('CSV没有成交记录')
    return sorted(fills,key=lambda f:(f['time'],f['line']))


def _float(value):
    return round(float(value), 6)


def analyze_ledger(request: LedgerRequest):
    if not request.rights_confirmed: raise ValueError('请确认资料已公开或你有权用于本次分析')
    if request.source_url and not re.match(r'^https://[^\s]+$',request.source_url): raise ValueError('来源链接仅支持HTTPS；系统不会自动抓取该链接')
    fills = read_fills(request.csv_text)
    queues = defaultdict(deque); pairs = []; total_fee = ZERO
    for fill in fills:
        total_fee += fill['fee']
        if fill['offset'] == 'OPEN':
            queues[(fill['contract'], fill['side'])].append({**fill,'remaining':fill['quantity']})
            continue
        direction = 'BUY' if fill['side']=='SELL' else 'SELL'
        queue = queues[(fill['contract'],direction)]
        if fill['offset'] != 'CLOSE' and (fill['trading_day'] is None or any(lot['trading_day'] is None for lot in queue)):
            raise ValueError(f"第{fill['line']}行平今/平昨匹配需要开仓和平仓的trading_day交易日，不能用夜盘自然日期猜测")
        candidates = [lot for lot in queue if fill['offset']=='CLOSE' or
                      (lot['trading_day']==fill['trading_day']) == (fill['offset']=='CLOSETODAY')]
        if fill['offset'] == 'CLOSEYESTERDAY':
            candidates = [lot for lot in candidates if lot['trading_day'] < fill['trading_day']]
        if sum((lot['remaining'] for lot in candidates),ZERO) < fill['quantity']:
            raise ValueError(f"第{fill['line']}行平仓超过可匹配持仓。可能缺少期初开仓记录、交易日或平今/平昨标签；不会编造持仓补齐")
        remaining = fill['quantity']
        for lot in candidates:
            if remaining <= 0: break
            quantity = min(remaining,lot['remaining'])
            gross = (fill['price'] - lot['price']) * quantity * fill['multiplier'] * (1 if direction=='BUY' else -1)
            fee = (lot['fee']/lot['quantity'] + fill['fee']/fill['quantity']) * quantity
            pairs.append({'contract':fill['contract'],'direction':'LONG' if direction=='BUY' else 'SHORT',
                          'openedAt':lot['time'].isoformat(),'closedAt':fill['time'].isoformat(),
                          'quantity':quantity,'entryPrice':lot['price'],'exitPrice':fill['price'],
                          'grossPnl':gross,'fees':fee,'netPnl':gross-fee,
                          'holdingHours':Decimal(str((fill['time']-lot['time']).total_seconds()/3600))})
            lot['remaining'] -= quantity; remaining -= quantity
        queues[(fill['contract'],direction)] = deque(lot for lot in queue if lot['remaining']>0)
    gross = sum((p['grossPnl'] for p in pairs),ZERO)
    closed_fees = sum((p['fees'] for p in pairs),ZERO)
    net = gross - closed_fees
    winners = [p for p in pairs if p['netPnl']>0]; losers = [p for p in pairs if p['netPnl']<0]
    positive = sum((p['netPnl'] for p in winners),ZERO)
    negative = -sum((p['netPnl'] for p in losers),ZERO)
    by_contract = defaultdict(lambda: {'netPnl':ZERO,'grossPnl':ZERO,'fees':ZERO,'closedLots':ZERO})
    for pair in pairs:
        row = by_contract[pair['contract']]
        for key in ['netPnl','grossPnl','fees']: row[key] += pair[key]
        row['closedLots'] += pair['quantity']
    ordered_wins = sorted((p['netPnl'] for p in winners),reverse=True)
    open_positions = [{'contract':contract,'direction':'LONG' if side=='BUY' else 'SHORT',
                       'lots':_float(sum((p['remaining'] for p in lots),ZERO))} for (contract,side),lots in queues.items() if lots]
    closed_lots = sum((p['quantity'] for p in pairs),ZERO)
    warnings = ['输入仅在本次请求内处理，未保存原始CSV；来源真实性和账户归属未获独立认证。',
                'FIFO配对片段不是独立交易次数；部分平仓会拆成多个片段，胜率不能与他人榜单直接比较。',
                '手续费按配对手数分摊；成交价已含实际成交影响，缺少委托记录无法另行估计滑点。',
                '没有完整逐日权益和出入金，不能计算真实收益率、最大回撤、杠杆、夏普或爆仓概率。',
                'time为自然成交时刻；平今/平昨必须额外提供trading_day交易日，夜盘不按自然日期猜测。持有时长按自然时刻计算。',
                '删去最好片段是事后敏感性检查，不是可执行策略，也不能估计运气占比。']
    if open_positions: warnings.append('仍有未平仓持仓；当前结果不含浮盈亏，也不是完整账户损益。')
    return {'schemaVersion':1,'sourceLabel':request.source_label,'sourceUrl':request.source_url,
            'inputSha256':hashlib.sha256(request.csv_text.encode('utf-8')).hexdigest(),
            'authenticity':'USER_SUPPLIED_UNVERIFIED','validationStatus':'DESCRIPTIVE_ONLY',
            'period':{'start':fills[0]['time'].isoformat(),'end':fills[-1]['time'].isoformat()},
            'metrics':{'fillCount':len(fills),'pairedFragments':len(pairs),'closedLots':_float(closed_lots),
                       'grossClosedPnl':_float(gross),'allocatedClosedFees':_float(closed_fees),
                       'netClosedPnl':_float(net),'allFillFees':_float(total_fee),
                       'fragmentWinRatePct':len(winners)/len(pairs)*100 if pairs else None,
                       'profitFactor':_float(positive/negative) if negative>0 else None,
                       'top1PositiveSharePct':_float(ordered_wins[0]/positive*100) if positive>0 else None,
                       'netWithoutBest1':_float(net-(ordered_wins[0] if ordered_wins else ZERO)),
                       'netWithoutBest5':_float(net-sum(ordered_wins[:5],ZERO)),
                       'netAtDoubleClosedFees':_float(gross-closed_fees*2),
                       'weightedHoldingHours':_float(sum((p['holdingHours']*p['quantity'] for p in pairs),ZERO)/closed_lots) if closed_lots else None,
                       'accountReturnPct':None,'accountMaxDrawdownPct':None},
            'byContract':[{'contract':key,**{k:_float(v) for k,v in row.items()}} for key,row in sorted(by_contract.items())],
            'pairs':[{k:_float(v) if isinstance(v,Decimal) else v for k,v in pair.items()} for pair in pairs],
            'openPositions':open_positions,'warnings':warnings,
            'learningChecks':[
                {'question':'是否依赖少数大盈利？','finding':'查看移除最好1/5个配对片段后的损益；只说明样本集中性，不证明能力或运气。'},
                {'question':'成本增加后还剩多少？','finding':'对已平仓分摊手续费做双倍压力检验；未模拟滑点、冲击和无法成交。'},
                {'question':'方法能借鉴吗？','finding':'先写清规则、失败条件与资金约束，再用预留样本和模拟账户验证，不能由这份CSV认定可复制。'},
            ]}
