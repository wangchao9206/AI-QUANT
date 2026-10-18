"""Accounting and evidence-boundary tests; all fill data below is a test fixture."""
import copy
import json
import gzip
import hashlib
from decimal import Decimal
from pathlib import Path

import pytest

from algorithm_service.mentor_ledger import LedgerRequest, analyze_ledger, read_fills
from algorithm_service.mentor_research import aggregate_analysis, mentor_catalog, validate_operations

HEADER='trade_id,time,trading_day,contract,side,offset,price,quantity,multiplier,fee\n'


def run(*rows, **kwargs):
    return analyze_ledger(LedgerRequest(csvText=HEADER+'\n'.join(rows),sourceLabel='仅供测试的虚构成交',rightsConfirmed=True,**kwargs))


def test_partial_fifo_fees_direction_and_unclosed_lots():
    result=run('a,2025-01-02T09:00:00,2025-01-02,rb2505,BUY,OPEN,100,2,10,4',
               'b,2025-01-02T10:00:00,2025-01-02,rb2505,SELL,CLOSE,110,1,10,3',
               'c,2025-01-02T11:00:00,2025-01-02,rb2505,SELL,CLOSE,90,1,10,3',
               'd,2025-01-02T12:00:00,2025-01-02,rb2505,SELL,OPEN,120,2,10,4',
               'e,2025-01-02T13:00:00,2025-01-02,rb2505,BUY,CLOSE,110,1,10,3')
    m=result['metrics']
    assert m['grossClosedPnl']==100 and m['allocatedClosedFees']==15 and m['netClosedPnl']==85
    assert m['allFillFees']==17 and m['netAtDoubleClosedFees']==70
    assert m['netWithoutBest1']==-10 and m['netWithoutBest5']==-105
    assert m['weightedHoldingHours']==pytest.approx(4/3)
    assert m['accountReturnPct'] is None and m['accountMaxDrawdownPct'] is None
    assert m['profitFactor']==pytest.approx(190/105,abs=1e-6)
    assert result['pairs'][-1]['direction']=='SHORT'
    assert result['openPositions']==[{'contract':'RB2505','direction':'SHORT','lots':1}]
    assert result['authenticity']=='USER_SUPPLIED_UNVERIFIED'
    assert len(result['inputSha256'])==64


def test_fifo_splits_distinct_entries_without_claiming_independent_trades():
    r=run('a,2025-01-02T09:00:00,,rb2505,BUY,OPEN,100,1,10,1',
          'b,2025-01-02T10:00:00,,rb2505,BUY,OPEN,110,2,10,2',
          'c,2025-01-02T11:00:00,,rb2505,SELL,CLOSE,120,3,10,3')
    assert len(r['pairs'])==2
    assert [p['quantity'] for p in r['pairs']]==[1,2]
    assert r['metrics']['netClosedPnl']==394
    assert r['metrics']['profitFactor'] is None
    assert '不是独立交易' in ' '.join(r['warnings'])


def test_night_session_closetoday_uses_explicit_exchange_trading_day():
    r=run('a,2025-01-02T21:01:00,2025-01-03,rb2505,BUY,OPEN,100,1,10,1',
          'b,2025-01-03T09:01:00,2025-01-03,rb2505,SELL,CLOSETODAY,110,1,10,1')
    assert r['metrics']['netClosedPnl']==98
    assert r['metrics']['weightedHoldingHours']==12
    with pytest.raises(ValueError,match='交易日'):
        run('a,2025-01-02T21:01:00,,rb2505,BUY,OPEN,100,1,10,1',
            'b,2025-01-03T09:01:00,,rb2505,SELL,CLOSETODAY,110,1,10,1')


def test_closeyesterday_does_not_match_same_trading_day_and_hedges_stay_separate():
    with pytest.raises(ValueError,match='超过'):
        run('a,2025-01-02T09:00:00,2025-01-02,rb2505,BUY,OPEN,100,1,10,1',
            'b,2025-01-02T10:00:00,2025-01-02,rb2505,SELL,CLOSEYESTERDAY,110,1,10,1')
    r=run('a,2025-01-02T09:00:00,2025-01-02,rb2505,BUY,OPEN,100,1,10,1',
          'b,2025-01-02T10:00:00,2025-01-02,rb2505,SELL,OPEN,110,1,10,1')
    assert r['metrics']['netClosedPnl']==0 and len(r['openPositions'])==2


@pytest.mark.parametrize('replace,expected',[
    (('rb2505','RBM'),'实际交割合约'),(('1,10,1','1.5,10,1'),'正整数'),
    (('100,1','NaN,1'),'有效有限'),(('1,10,1','1,10,-1'),'手续费不能为负'),
    (('BUY,OPEN','SELL,CLOSE'),'超过'),(('2025-01-02T09:00:00','bad'),'成交时间'),
])
def test_rejects_unsupported_or_malformed_fills(replace,expected):
    row='a,2025-01-02T09:00:00,,rb2505,BUY,OPEN,100,1,10,1'
    with pytest.raises(ValueError,match=expected):run(row.replace(*replace))


def test_duplicate_execution_identity_scope_and_rights():
    row='a,2025-01-02T09:00:00,2025-01-02,rb2505,BUY,OPEN,100,1,10,1'
    with pytest.raises(ValueError,match='重复'):run(row,row)
    assert len(run(row,row.replace('2025-01-02','2025-01-03'))['openPositions'])==1
    with pytest.raises(ValueError,match='确认'):analyze_ledger(LedgerRequest(csvText=HEADER+row,sourceLabel='test'))
    with pytest.raises(ValueError,match='HTTPS'):run(row,sourceUrl='http://example.com')
    with pytest.raises(ValueError,match='重复列名'):read_fills(HEADER.replace('fee','price'))


def test_optional_trading_day_missing_cell_is_handled_without_server_error():
    text='trade_id,time,contract,side,offset,price,quantity,multiplier,fee,trading_day\na,2025-01-02T09:00:00,rb2505,BUY,OPEN,100,1,10,1'
    assert len(read_fills(text))==1


def test_real_public_snapshot_accounting_is_reproducible_and_not_person_attributed():
    result=mentor_catalog()
    assert result['summary']=={'profiles':41,'completePersonLedgers':0,'aggregateAccounts':15,'quoteCount':2,
                               'contestAliases':19,'documentedProfiles':35,'pendingProfiles':2,'backgroundProfiles':4}
    accounts=[a for a in result['contestSnapshot']['accounts'] if not a.get('profileId')]
    for a,expected in zip(accounts,[(221990,39350,76.78,-3330.74),(3257990,1897810,39.25,-240987.72),(476305,168665,64.59,130094.49)]):
        m=a['analysis']['metrics']
        assert (m['futuresGrossClosedPnl'],m['grossWithoutBestBreed'],m['top1PositiveBreedSharePct'],m['unreconciledDifference'])==expected
        assert m['dailySampleDrawdownPct']==pytest.approx(m['reportedDrawdownPct'],abs=.002)
        assert not a.get('personId') and a['identityStatus']=='PUBLIC_CONTEST_ALIAS'
    assert result['contestSnapshot']['asOf']=='2026-09-30'
    source_ids={s['id'] for s in result['sources']}
    for p in result['profiles']:
        assert set(p['sourceIds'])<=source_ids
        assert p['ledger']['status']=='MISSING'
        for q in p['quotes']:assert q['sourceId'] in source_ids
    assert result['editions'][0]['year']==2006


def test_official_alias_is_sufficient_and_requested_names_are_separate_research_entries():
    result=mentor_catalog();profiles={p['name']:p for p in result['profiles']}
    for name in ['大道至简','追风','期海浮萍','南方以南','北海大盗','满仓扛把子','一切都好','小赌怡情']:
        assert profiles[name]['identityKind']=='CONTEST_ALIAS'
        assert not profiles[name].get('realName')
    assert profiles['小赌怡情']['researchStatus']=='PENDING_MATCH'
    assert profiles['小赌怡情']['contestRecords']==[]
    assert '666' in profiles['小赌怡情']['identityNotes']
    assert profiles['满仓扛把子']['researchStatus']=='PARTIAL_RECORD'
    for name in ['王孝安','黄伟','徐王冠','叶庆均','林军','林广茂','徐长波','于忠']:
        assert profiles[name]['identityKind']=='PUBLIC_NAME'
    for name in ['王孝安','黄伟','徐王冠','叶庆均']:
        assert profiles[name]['researchStatus']=='BACKGROUND_ONLY'
    assert '无需' in result['definition']


def test_contest_records_preserve_period_scope_and_public_account_links_without_real_names():
    result=mentor_catalog();profiles={p['name']:p for p in result['profiles']}
    one=profiles['一切都好']['contestRecords'][0]
    assert one['scope']=='INTERIM' and one['asOf']=='2024-09-25' and one['rank']==2
    assert one['accountRef'] is None and one['netProfit']==230699.10
    assert profiles['追风']['contestRecords'][0]['scope']=='FINAL_REPORTED'
    assert profiles['期海浮萍']['contestRecords'][1]['reportedDrawdownPct']==71.994
    keys=[r['recordKey'] for p in profiles.values() for r in p['contestRecords']]
    assert len(keys)==len(set(keys))
    accounts={a['id']:a for a in result['contestSnapshot']['accounts']}
    for p in profiles.values():
        if not p.get('linkedAccountId'):continue
        a=accounts[p['linkedAccountId']]
        assert p['name']==a['alias'] and p['identityKind']=='CONTEST_ALIAS'
        linked=[r for r in p['contestRecords'] if r['accountRef']==a['id']]
        assert len(linked)==1
        assert linked[0]['edition']==a.get('edition',20)
    ids=result['editions'][17]['profileIds']
    assert 'alias-nanfangyinan' in ids and 'alias-beihaidadao' in ids


def test_all_expanded_evidence_references_resolve_and_no_identifier_collision_is_silently_merged():
    result=mentor_catalog();sources={s['id'] for s in result['sources']}
    assert len(sources)==len(result['sources'])
    assert len({p['id'] for p in result['profiles']})==len(result['profiles'])
    for p in result['profiles']:
        for entry in [*p['timeline'],*p['achievements'],*p['methods'],*p['contestRecords']]:
            assert set(entry['sourceIds'])<=sources
        for r in p['contestRecords']:
            if r['scope']=='FINAL_REPORTED':assert r['asOf'] is None


def test_bad_nav_and_bad_sign_fail_closed_instead_of_fabricating_analysis():
    data=json.loads(Path('algorithm_service/mentor_contest_snapshot.json').read_text(encoding='utf-8'))['accounts'][0]
    bad=copy.deepcopy(data);bad['netWorth'].append(bad['netWorth'][0])
    with pytest.raises(ValueError,match='净值'):aggregate_analysis(bad)
    bad=copy.deepcopy(data);bad['futuresByBreed'][0]['tradeClosingLossAmount']=1
    with pytest.raises(ValueError,match='符号异常'):aggregate_analysis(bad)


def test_historical_alias_evidence_reconciles_daily_profit_and_retains_source_payloads():
    result=mentor_catalog()
    accounts=[a for a in result['contestSnapshot']['accounts'] if a.get('profileId')]
    assert {a['alias'] for a in accounts}=={'北海大盗','一切都好','南方以南','期海浮萍'}
    archive=json.loads(gzip.decompress(Path('docs/research/data/mentor-2024-source-responses.json.gz').read_bytes()))
    captured={r['url']:r['payload'] for r in archive['responses']}
    for a in accounts:
        assert a['asOf']=='2024-09-27' and a['statementStatus']=='NO_EXECUTION_LEDGER'
        assert a['analysis']['metrics']['dailyProfitReconciliationDifference']==0
        assert a['analysis']['metrics']['dailySampleDrawdownPct']==pytest.approx(a['analysis']['metrics']['reportedDrawdownPct'],abs=.002)
        values={u.split('?')[0].rsplit('/',1)[1]:captured[u]['dataPoints'] for u in a['sourceUrls'][1:]}
        assert hashlib.sha256(json.dumps(values,ensure_ascii=False,sort_keys=True).encode()).hexdigest()==a['sourceSha256']
        assert len(a['analysis']['daily'])==len(a['dailyProfit'])==len(a['dailyRisk'])
    qi=next(a for a in accounts if a['alias']=='期海浮萍')
    assert qi['analysis']['byBreed'][0]['code']=='EC'
    assert qi['analysis']['metrics']['grossWithoutBestBreed']==-2154645
    assert qi['analysis']['metrics']['reportedDrawdownPct']==71.994
    # Different public accounting fields are not silently forced to reconcile.
    assert qi['analysis']['metrics']['cashReconciliationDifference']==136493.87
    assert result['dataCoverage']=={'executionRows':0,'netWorthRows':1842,'dailyProfitRows':1459,
                                    'dailyRiskRows':1459,'breedRows':460,'settlementRows':306,'linkedRequestedAliases':4}
    bad=copy.deepcopy(qi);bad['dailyProfit'].append(bad['dailyProfit'][0])
    with pytest.raises(ValueError,match='日度记录'):aggregate_analysis(bad)


def test_public_settlement_cash_checks_match_original_rows_without_claiming_execution_access():
    result=mentor_catalog()
    for a in result['settlementSnapshot']['accounts']:
        assert a['rawTradesPublic'] is False
        rows=a['rows']
        assert len({r['dateline'] for r in rows})==len(rows)
        assert a['checks']['feeSum']==float(sum(Decimal(str(r['fee'])) for r in rows))
        for row in rows:
            d={k:Decimal(str(row[k])) for k in ['cbalance','balance','today_in','today_out','profit','fee','royalty']}
            assert row['cashResidual']==float(d['cbalance']-d['balance']-d['today_in']+d['today_out']-d['profit']+d['fee']-d['royalty'])
        raw=[{k:v for k,v in r.items() if k!='cashResidual'} for r in rows]
        assert hashlib.sha256(json.dumps(raw,ensure_ascii=False,sort_keys=True).encode()).hexdigest()==a['sourceSha256']


def test_operation_fragments_preserve_scope_precision_and_do_not_become_execution_fills():
    result=mentor_catalog();rows=result['operations'];by_id={r['id']:r for r in rows}
    assert result['operationSummary']=={'records':30,'profiles':11,'regulatoryRecords':6,'recalledRecords':24,'exactDayRecords':5}
    assert len(by_id)==30 and all(not r['executionVerified'] and not r['eligibleForLedgerAnalysis'] for r in rows)
    assert all(r['ownerScope']=='CONTROLLED_COMPANIES' and r['direction']=='UNSPECIFIED' and r['quantity'] is None for r in rows if r['profileId']=='ge-weidong')
    assert by_id['ge-reduce-jul']['dateStart']=='2011-07-19'
    assert by_id['fu-cotton-close-16600']['datePrecision']=='MONTH'
    assert by_id['fu-cotton-close-16600']['contractCodes']==[]
    assert '回忆' in by_id['fu-cotton-close-16600']['priceLabel']
    assert by_id['qihai-ec-open']['dateStart'] is None
    assert by_id['qihai-ec-open']['contractCodes']==['EC2404','EC2406','EC2408']
    assert by_id['qihai-ec-position']['quantity']==200
    assert by_id['qihai-ec-position']['contractCodes']==[]  # Not assigned to one maturity by inference.
    assert by_id['qihai-ec-close']['quantity'] is None
    assert all(r['ownerScope']=='GUIDED_TEAM' for r in rows if r['profileId']=='lin-bo')
    people={p['id']:p for p in result['profiles']}
    for row in rows:
        assert row['id'] in people[row['profileId']]['operationIds']
        assert row['interpretation'] and row['validationStatus']=='DESCRIPTIVE_ONLY'
    for change in [dict(executionVerified=True),dict(datePrecision='DAY'),dict(sourceIds=['not-a-source']),dict(price=float('nan'))]:
        bad=copy.deepcopy(by_id['fu-cotton-close-16600']);bad.update(change)
        with pytest.raises(ValueError):validate_operations([bad],result['profiles'],result['sources'])


def test_new_historical_accounts_retain_published_payloads_and_do_not_merge_aliases_between_editions():
    result=mentor_catalog();accounts=[a for a in result['contestSnapshot']['accounts'] if a.get('sourceId')=='contest-archive']
    assert {a['alias'] for a in accounts}=={'落叶狂风','马小夕','吾剑','龙哥','纯纯','玉米','定海神针','突然的自我'}
    archive=json.loads(gzip.decompress(Path('docs/research/data/mentor-archive-source-responses.json.gz').read_bytes()))
    captured={r['url']:r['payload'] for r in archive['responses']}
    for a in accounts:
        values={u.split('?')[0].rsplit('/',1)[1]:captured[u]['dataPoints'] for u in a['sourceUrls'][1:]}
        assert hashlib.sha256(json.dumps(values,ensure_ascii=False,sort_keys=True).encode()).hexdigest()==a['sourceSha256']
        assert a['analysis']['metrics']['dailyProfitReconciliationDifference']==0
        p=next(p for p in result['profiles'] if p.get('linkedAccountId')==a['id'])
        assert p['contestRecords'][0]['edition']==a['edition']
        assert p['contestRecords'][0]['year']==a['year']
        assert p['contestRecords'][0]['scope']!='FINAL_REPORTED'
    # Adverse paths remain visible even for highly ranked positive-profit samples.
    assert next(a for a in accounts if a['alias']=='纯纯')['analysis']['metrics']['reportedDrawdownPct']==99.202
    assert result['editions'][18]['year']==2025
    people={p['id']:p for p in result['profiles']}
    assert {'xie-lei','cheng-jiajun','fu-aimin','lin-bo','feng-chengyi','wang-xingmin','han-jian','wang-xiangyang'}<=people.keys()


def test_research_api_handles_catalogue_and_validation_errors():
    from fastapi.testclient import TestClient
    from algorithm_service.app import app
    client=TestClient(app)
    r=client.get('/api/v1/research/mentors')
    assert r.status_code==200 and r.json()['summary']['completePersonLedgers']==0
    r=client.post('/api/v1/research/mentors/analyze-ledger',json={'csvText':'not csv','sourceLabel':'test','rightsConfirmed':True})
    assert r.status_code==422 and '需要' in r.json()['detail']
    r=client.post('/api/v1/research/mentors/analyze-ledger',json={
        'csvText':HEADER+'a,2025-01-02T09:00:00,,rb2505,BUY,OPEN,100,1,10,1\nb,2025-01-02T10:00:00,,rb2505,SELL,CLOSE,110,1,10,1',
        'sourceLabel':'虚构验收资料，非人物交割单','rightsConfirmed':True})
    assert r.status_code==200
    assert r.json()['metrics']['netClosedPnl']==98
    assert r.json()['metrics']['accountMaxDrawdownPct'] is None
