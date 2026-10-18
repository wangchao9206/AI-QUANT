"""Evidence catalogue and descriptive checks of organizer-published aggregates."""
from __future__ import annotations

import json
import hashlib
import math
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path


def aggregate_analysis(account):
    rows = account.get('futuresByBreed', [])
    result = []
    for row in rows:
        profit = float(row['tradeClosingProfitAmount'])
        loss = float(row['tradeClosingLossAmount'])
        if not all(math.isfinite(x) for x in [profit,loss]) or profit<0 or loss>0:
            raise ValueError('赛方平仓汇总字段或符号异常，停止归因')
        result.append({'code':row['breedCode'],'name':row['breedName'],
                       'grossClosedPnl':round(profit+loss,2),
                       'winningCloseCount':int(row['tradeClosingProfitCount']),
                       'losingCloseCount':int(row['tradeClosingLossCount'])})
    trades = {r['breedCode']:r for r in account.get('tradeStatistics',[])}
    for row in result:
        trade = trades.get(row['code'])
        row['reportedDealCount'] = trade['dealCount'] if trade else None
        row['reportedDealAmount'] = trade['dealAmount'] if trade else None
    result.sort(key=lambda r:r['grossClosedPnl'],reverse=True)
    positive = sum(max(0,row['grossClosedPnl']) for row in result)
    gross = sum(row['grossClosedPnl'] for row in result)
    options_gross = sum(float(row['closingProfitAmount'])+float(row['closingLossAmount']) for row in account.get('optionsByBreed',[]))
    peak = 1.; max_dd = 0.; curve = []
    previous = None
    for point in sorted(account.get('netWorth',[]),key=lambda p:p['date']):
        value = float(point['value'])
        if not math.isfinite(value) or value<=0 or point['date']==previous:
            raise ValueError('赛方净值包含异常或重复点')
        previous = point['date'];peak=max(peak,value);max_dd=max(max_dd,(peak-value)/peak)
        curve.append(point)
    best = max(0,result[0]['grossClosedPnl']) if result else 0
    top3 = sum(max(0,r['grossClosedPnl']) for r in result[:3])
    count = sum(r['winningCloseCount']+r['losingCloseCount'] for r in result)
    wins = sum(r['winningCloseCount'] for r in result)
    reported = account['reported']
    daily = {r['date']:{'date':r['date'],'netWorth':r['value'],'netProfit':None,'reportedRiskDegree':None} for r in curve}
    for field,key,out in [('dailyProfit','netProfit','netProfit'),('dailyRisk','matchRiskDegree','reportedRiskDegree')]:
        seen = set()
        for row in account.get(field,[]):
            day = row['tradeDate'][:10]
            value = float(row[key])
            if day in seen or not math.isfinite(value) or day>account['asOf']:
                raise ValueError('赛方日度记录重复、越界或数值异常')
            seen.add(day)
            daily.setdefault(day,{'date':day,'netWorth':None,'netProfit':None,'reportedRiskDegree':None})[out]=value
    daily = sorted(daily.values(),key=lambda r:r['date'])
    profits = [Decimal(str(r['netProfit'])) for r in daily if r['netProfit'] is not None]
    daily_sum = sum(profits,Decimal(0))
    positive_days = sum((max(Decimal(0),p) for p in profits),Decimal(0))
    best_days = sum(sorted((p for p in profits if p>0),reverse=True)[:5],Decimal(0))
    cash_fields = ['openAmount','endAmount','inMoney','outMoney']
    cash_gap = (round(float(reported['endAmount'])-float(reported['openAmount'])-float(reported['inMoney'])+float(reported['outMoney'])-float(reported['netProfit']),2)
                if all(k in reported for k in cash_fields) else None)
    return {'byBreed':result,'netWorth':curve,
            'daily':daily,
            'metrics':{'futuresGrossClosedPnl':round(gross,2),'optionsGrossClosedPnl':round(options_gross,2),
                       'reportedNetProfit':reported['netProfit'],
                       'unreconciledDifference':round(float(reported['netProfit'])-gross-options_gross,2),
                       'top1PositiveBreedSharePct':round(best/positive*100,2) if positive>0 else None,
                       'top3PositiveBreedSharePct':round(top3/positive*100,2) if positive>0 else None,
                       'grossWithoutBestBreed':round(gross-best,2),
                       'dailySampleDrawdownPct':round(max_dd*100,3) if curve else None,
                       'reportedDrawdownPct':round(float(reported['maxWithrawalRate'])*100,3),
                       'reportedCumulativeNetWorth':reported['netWorth'],
                       'closeCountWinRatePct':round(wins/count*100,2) if count else None,
                       'dailyPointCount':len(curve),
                       'dailyProfitPointCount':len(profits),
                       'sumDailyNetProfit':round(float(daily_sum),2) if profits else None,
                       'dailyProfitReconciliationDifference':round(float(daily_sum)-float(reported['netProfit']),2) if profits else None,
                       'top5PositiveDaySharePct':round(float(best_days/positive_days)*100,2) if positive_days else None,
                       'netWithoutBestDay':round(float(daily_sum-max(profits)),2) if profits else None,
                       'cashReconciliationDifference':cash_gap},
            'findings':[
                f"该样本{len(result)}个期货品种有平仓统计；按净盈利品种的正贡献计算集中度，不将其解释为净利润百分比。",
                '移除最好品种后的数值仍是期货平仓毛损益；不是扣费收益，也不是可执行的交易组合。',
                '赛方净利润与期货/期权平仓毛损益分别展示；差额未完成费用、浮盈亏及资金流对账，不直接归因。',
                '日终净值点回撤不涵盖盘中极值；赛方回撤字段口径可能不同，二者分别列出。',
            ]}


def mentor_catalog():
    result = json.loads(Path(__file__).with_name('mentors_catalog.json').read_text(encoding='utf-8'))
    expansion = json.loads(Path(__file__).with_name('mentors_expansion.json').read_text(encoding='utf-8'))
    result['sources'].extend(expansion['sources'])
    result['profiles'].extend(expansion['profiles'])
    operations_data = json.loads(Path(__file__).with_name('mentor_operations.json').read_text(encoding='utf-8'))
    result['sources'].extend(operations_data['sources'])
    result['profiles'].extend(operations_data['profiles'])
    result['operations'] = operations_data['operations']
    result['operationPolicy'] = operations_data['policy']
    result['version'] = operations_data['version']
    try:
        snapshot = json.loads(Path(__file__).with_name('mentor_contest_snapshot.json').read_text(encoding='utf-8'))
        history_path = Path(__file__).with_name('mentor_historical_snapshot.json')
        if history_path.exists():
            history = json.loads(history_path.read_text(encoding='utf-8'))
            snapshot['accounts'] = history['accounts'] + snapshot['accounts']
            snapshot['fetchedAt'] = max(snapshot['fetchedAt'],history['fetchedAt'])
            snapshot['sampling'] = '包含第十八届4个已对应昵称的历史账户，以及第二十届3个公开轻量组样本；均是选定优胜者样本。各账户赛期和截止日期单独展示。'
            result['sources'].append({'id':'contest-public-2024','publisher':'期货日报实盘大赛公开平台','title':'第十八届公开账户日终、成交与平仓统计',
                                      'url':'https://ds.qhrb.com.cn/','kind':'ORGANIZER_AGGREGATE','publishedAt':None,
                                      'checkedAt':history['fetchedAt'][:10],'limitation':'482个日终净值点及对应日盈亏、风险字段；分品种汇总不含逐笔成交、时刻和价格。'})
        archive_path = Path(__file__).with_name('mentor_archive_snapshot.json')
        if archive_path.exists():
            archive = json.loads(archive_path.read_text(encoding='utf-8'))
            snapshot['accounts'].extend(archive['accounts'])
            snapshot['fetchedAt'] = max(snapshot['fetchedAt'],archive['fetchedAt'])
            result['sources'].append({'id':'contest-archive','publisher':'期货日报实盘大赛公开平台','title':'第十八、十九届新增8个公开账户',
                                      'url':'https://spdspc.qhrb.com.cn/','kind':'ORGANIZER_AGGREGATE','publishedAt':None,
                                      'checkedAt':archive['fetchedAt'][:10],'limitation':'按届次、组别与公开账户ID分别建档。采集时点名次不自动认证最终颁奖结果。'})
        counts = {}
        for a in snapshot['accounts']:counts[a.get('year',2026)] = counts.get(a.get('year',2026),0)+1
        snapshot['sampling'] = '公开账户分布：'+ '、'.join(f'{year}年{count}个' for year,count in sorted(counts.items()))+'。选定优胜者样本不代表全体交易者；各账户日期分别展示。'
        for account in snapshot['accounts']:
            account['analysis'] = aggregate_analysis(account)
            # An official alias is an adequate research identity. A public account
            # reference within a specific edition/group links only that record.
            account['identityStatus'] = 'PUBLIC_CONTEST_ALIAS'
            account['contestKey'] = f"qhrb:{account.get('edition',20)}:{account.get('year',2026)}:{account['groupLabel']}:{account['id']}"
            profile = next((p for p in result['profiles'] if p['id']==account.get('profileId')),None)
            if profile:
                profile['linkedAccountId'] = account['id']
                profile['sourceIds'] = list(dict.fromkeys(profile['sourceIds']+['contest-public-2024']))
                profile['ledger']['message'] = f"已取得该昵称第十八届官方公开账户数据：{len(account['netWorth'])}个日终净值点、日盈亏、风险字段及分品种成交和平仓统计；仍缺逐笔成交明细。"
                profile['ledger']['missing'] = ['完整逐笔成交时刻、方向、价格与费用','完整逐日资金结算及盘中持仓','跨赛期独立样本']
                profile['liveEvidence'] = '官方公开榜单与账户详情按本届、本组账户ID对应，已保存原始接口数据。'
                profile['contestRecords'].append({'event':'全国期货（期权）实盘交易大赛','edition':18,'year':2024,
                    'group':'轻量组' if account['reported']['groupType']==1 else '重量组','scope':'OBSERVED_PUBLIC',
                    'asOf':account['asOf'],'rank':account['rank'],'accountRef':account['id'],
                    'netProfit':account['reported']['netProfit'],'cumulativeNetWorth':account['reported']['netWorth'],
                    'reportedDrawdownPct':account['analysis']['metrics']['reportedDrawdownPct'],
                    'sourceIds':['contest-public-2024'],'note':'采集时点公开账户详情；未以期末数据自动认定颁奖结果。'})
            else:
                result['profiles'].append(public_account_profile(account))
        snapshot['identityWarning'] = '官方昵称可独立研究，无需公开实名。同名跨赛事、届次或组别不自动关联；汇总统计仍不等于完整交割单。'
        result['contestSnapshot'] = snapshot
    except FileNotFoundError:
        result['contestSnapshot'] = {'status':'UNAVAILABLE','accounts':[],'message':'尚未取得赛方公开统计'}
    settlements_path = Path(__file__).with_name('mentor_settlement_snapshot.json')
    result['settlementSnapshot'] = json.loads(settlements_path.read_text(encoding='utf-8')) if settlements_path.exists() else {'accounts':[]}
    if result['settlementSnapshot']['accounts']:
        settlement = result['settlementSnapshot']
        for account in settlement['accounts']:
            fees = Decimal(0); incoming = Decimal(0); outgoing = Decimal(0); residuals=[]
            for row in account['rows']:
                values = {k:Decimal(str(row[k])) for k in ['cbalance','balance','today_in','today_out','profit','fee','royalty']}
                if not all(v.is_finite() for v in values.values()):raise ValueError('公开资金表含无效金额')
                residual = values['cbalance']-values['balance']-values['today_in']+values['today_out']-values['profit']+values['fee']-values['royalty']
                row['cashResidual'] = float(residual)
                residuals.append(abs(residual)); fees+=values['fee']; incoming+=values['today_in']; outgoing+=values['today_out']
            account['checks']={'feeSum':float(fees),'inSum':float(incoming),'outSum':float(outgoing),
                               'cashResidualRows':sum(v>Decimal('.01') for v in residuals),
                               'maxAbsCashResidual':float(max(residuals,default=Decimal(0)))}
        result['sources'].append({'id':'settlement-public','publisher':settlement['publisher'],'title':'公开实盘账户逐日资金表',
                                  'url':settlement['rankSourceUrl'],'kind':'ORGANIZER_AGGREGATE','publishedAt':None,
                                  'checkedAt':settlement['fetchedAt'][:10],'limitation':'仅采集无需登录公开展示的资金表；成交明细未开放，未请求私有明细。'})
    for profile in result['profiles']:
        profile.setdefault('identityKind', 'PUBLIC_NAME')
        profile.setdefault('researchStatus', 'DOCUMENTED')
        profile.setdefault('contestRecords', [])
        profile.setdefault('identityNotes', '原始资料已定位不等于完整业绩认证。')
        profile['operationIds'] = [o['id'] for o in result['operations'] if o['profileId']==profile['id']]
        for index, record in enumerate(profile['contestRecords']):
            # Preserve separate observations, even for identical display aliases.
            payload = [profile['id'], record['event'], record['edition'], record['group'],
                       record['asOf'], record['accountRef'], record['sourceIds'], index]
            record['recordKey'] = hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()[:24]
    validate_operations(result['operations'],result['profiles'],result['sources'])
    known = {1:(2006,'xie-lei'),2:(2008,'li-yongqiang'),3:(2009,'cheng-jiajun'),4:(2010,'ding-hongbo'),
             5:(2011,'lin-bo'),6:(2012,'feng-chengyi'),7:(2013,'wang-xingmin'),8:(2014,'han-jian'),17:(2023,'alias-zhuifeng'),
             18:(2024,'alias-beihaidadao'),19:(2025,'wu-weimiao'),20:(2026,None)}
    result['editions'] = [{'edition':i,'year':known.get(i,(None,None))[0],
                          'profileId':known.get(i,(None,None))[1],
                          'status':'PARTIAL_PERSON_EVIDENCE' if known.get(i,(None,None))[1] else 'PUBLIC_SNAPSHOT' if i==20 else 'ARCHIVE_PENDING',
                          'url':'https://ds.qhrb.com.cn/',
                          'note':'主办方入口；不是该届完整获奖或交割单档案'} for i in range(1,21)]
    for edition in result['editions']:
        matched = [p['id'] for p in result['profiles'] if any(
            r['event']=='全国期货（期权）实盘交易大赛' and r['edition']==edition['edition'] for r in p['contestRecords'])]
        edition['profileIds'] = list(dict.fromkeys(([edition['profileId']] if edition['profileId'] else []) + matched))
        years = {r['year'] for p in result['profiles'] for r in p['contestRecords'] if r['event']=='全国期货（期权）实盘交易大赛' and r['edition']==edition['edition'] and r['year'] is not None}
        if len(years)==1:edition['year']=years.pop()
        if matched and edition['status']=='ARCHIVE_PENDING': edition['status']='PARTIAL_PERSON_EVIDENCE'
    result['generatedAt'] = datetime.now(timezone.utc).isoformat()
    result['summary'] = {'profiles':len(result['profiles']),
                         'completePersonLedgers':sum(p['ledger']['status']=='COMPLETE' for p in result['profiles']),
                         'aggregateAccounts':len(result['contestSnapshot'].get('accounts',[])),
                         'quoteCount':sum(len(p['quotes']) for p in result['profiles']),
                         'contestAliases':sum(p['identityKind']=='CONTEST_ALIAS' for p in result['profiles']),
                         'documentedProfiles':sum(p['researchStatus']=='DOCUMENTED' for p in result['profiles']),
                         'pendingProfiles':sum(p['researchStatus'] in ('PENDING_MATCH','PARTIAL_RECORD') for p in result['profiles']),
                         'backgroundProfiles':sum(p['researchStatus']=='BACKGROUND_ONLY' for p in result['profiles'])}
    accounts = result['contestSnapshot'].get('accounts',[])
    result['dataCoverage'] = {'executionRows':0,'netWorthRows':sum(len(a['netWorth']) for a in accounts),
                            'dailyProfitRows':sum(len(a.get('dailyProfit',[])) for a in accounts),
                            'dailyRiskRows':sum(len(a.get('dailyRisk',[])) for a in accounts),
                            'breedRows':sum(len(a['futuresByBreed'])+len(a.get('optionsByBreed',[])) for a in accounts),
                            'settlementRows':sum(len(a['rows']) for a in result['settlementSnapshot']['accounts']),
                            'linkedRequestedAliases':sum(bool(a.get('profileId')) for a in accounts)}
    result['operationSummary'] = {'records':len(result['operations']),
                                  'profiles':len({o['profileId'] for o in result['operations']}),
                                  'regulatoryRecords':sum(o['sourceType']=='REGULATORY_DISCLOSURE' for o in result['operations']),
                                  'recalledRecords':sum(o['sourceType']=='FIRST_PERSON_RECALL' for o in result['operations']),
                                  'exactDayRecords':sum(o['datePrecision']=='DAY' for o in result['operations'])}
    return result


def public_account_profile(account):
    alias=account['alias']; record_id=account['id']
    year=account.get('year',2026);edition=account.get('edition',20)
    source_id=account.get('sourceId','contest-public')
    group='重量组' if account.get('reported',{}).get('groupType')==2 else '轻量组'
    profile_id=f'contest-2026-light-{record_id}' if year==2026 else f'contest-{year}-{record_id}'
    return {'id':profile_id,'name':alias,'initials':alias[0],
            'identityKind':'CONTEST_ALIAS','researchStatus':'DOCUMENTED','linkedAccountId':record_id,
            'style':'官方昵称 · 可核对汇总','admission':'官方公开账户可独立建档；无需实名',
            'identityStatus':'官方参赛昵称与公开账户记录','liveEvidence':'主办方公开接口返回赛期日终净值和分品种平仓汇总。',
            'successEvidence':f"{account['asOf']}第{edition}届公开{group}排名第{account['rank']}；只覆盖该赛期，未视为最终获奖或长期业绩。",
            'intro':'以赛事、届次、组别和公开账户记录为研究身份。该档案与本模块采集的汇总有明确对应，无需披露真实姓名。',
            'timeline':[{'period':f"{account['periodStart']} — {account['asOf']}",
                         'fact':'已取得该账户公开赛期日终净值和分品种平仓汇总。','sourceIds':[source_id]}],
            'achievements':[{'text':'原始汇总可复核收益集中度及日终样本回撤；不把该赛期之外的表现补造为长期成功。','sourceIds':[source_id]}],
            'quotes':[],'methods':[],
            'factors':[{'factor':'盈利贡献与风险过程','evidence':'赛方公开汇总可定位到该届该组账户。','status':'汇总可复核；方法因果待证',
                        'learn':'比较品种贡献、日终回撤和其他赛期，保留失败与费用差异。',
                        'cannotCopy':'缺少逐笔成交、盘中风险与完整资金流，不能由曲线复制下单。',
                        'alternative':'市场机会、仓位、资金流和样本筛选都可能影响结果。'}],
            'ledger':{'status':'MISSING','message':'已有可对应的官方公开汇总；尚无完整逐笔交割单。无需公开实名即可研究。',
                      'missing':['完整逐笔成交及费用','完整资金流和结算','盘中风险与跨赛期样本']},
            'learningIds':['concentration','risk-budget','survivorship'],'sourceIds':[source_id],
            'identityNotes':'仅按公开记录对应本届本组账户；不会按昵称拼接其他账户或追查实名。',
            'contestRecords':[{'event':'全国期货（期权）实盘交易大赛','edition':edition,'year':year,'group':group,
                               'scope':'INTERIM','asOf':account['asOf'],'rank':account['rank'],'accountRef':record_id,
                               'netProfit':account['reported']['netProfit'],'cumulativeNetWorth':account['reported']['netWorth'],
                               'reportedDrawdownPct':account['analysis']['metrics']['reportedDrawdownPct'],
                               'sourceIds':[source_id],'note':'采集时点公开统计，不自动认定最终获奖。'}]}


def validate_operations(operations, profiles, sources):
    """Keep historical disclosures from masquerading as dated execution fills."""
    people={p['id'] for p in profiles};source_ids={s['id'] for s in sources};seen=set()
    for row in operations:
        if row['id'] in seen or row['profileId'] not in people or not row['sourceIds'] or not set(row['sourceIds'])<=source_ids:
            raise ValueError('操作记录身份、来源或唯一编号异常')
        seen.add(row['id'])
        if row['action'] not in {'OPEN','CLOSE','ADD','REDUCE','HOLD','REVERSE','POSITION'} or row['direction'] not in {'LONG','SHORT','UNSPECIFIED'}:
            raise ValueError('操作类型或方向异常')
        if row['sourceType'] not in {'FIRST_PERSON_RECALL','REGULATORY_DISCLOSURE'} or row['executionVerified'] or row['eligibleForLedgerAnalysis']:
            raise ValueError('披露片段不能冒充经核验逐笔成交')
        if row['ownerScope'] not in {'INDIVIDUAL','GUIDED_TEAM','CONTROLLED_COMPANIES'}:
            raise ValueError('操作主体口径异常')
        if row['datePrecision'] not in {'DAY','MONTH','YEAR','INTERVAL','UNSPECIFIED'}:
            raise ValueError('操作日期精度异常')
        start,end=row['dateStart'],row['dateEnd']
        if bool(start)!=bool(end) or (row['datePrecision']=='UNSPECIFIED' and start):raise ValueError('未披露日期不得补具体交易日')
        if row['datePrecision']!='UNSPECIFIED' and not start:raise ValueError('操作日期精度缺少范围')
        if row['datePrecision']=='DAY' and (not start or start!=end):raise ValueError('具体日期记录缺少同一天的边界')
        if start:
            datetime.strptime(start,'%Y-%m-%d');datetime.strptime(end,'%Y-%m-%d')
            if start>end or (row['publishedAt'] and end>row['publishedAt']):raise ValueError('操作时间范围异常')
        for field in ['price','quantity']:
            if row[field] is not None and (not math.isfinite(float(row[field])) or float(row[field])<=0):raise ValueError('操作披露数值异常')
