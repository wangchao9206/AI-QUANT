"""Publish an already-run audit only when its engine version still matches."""
import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from algorithm_service.research import engine_fingerprint
from config.settings import settings
from data.live_feed import SHANGHAI


def publish(source: Path, destination: Path):
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    summary=read(source/'run-summary.json')
    fingerprint=engine_fingerprint()
    if summary.get('engineFingerprint')!=fingerprint or summary.get('modelVersion')!=settings.version:
        raise ValueError('Audit version/fingerprint does not match current code. Rerun the fixed audit first.')
    if summary.get('not_loaded') or summary.get('unavailable') or len(summary['completed'])!=8:
        raise ValueError('Eight observed datasets must complete before publishing this protocol.')
    assets=[read(source/(item['symbol']+'.json')) for item in summary['completed']]
    rows=[r for a in assets for r in a['results']]
    if len(rows)!=104 or any(a['entry_day_stop_misses'] for a in assets):
        raise ValueError('Incomplete cases or unresolved entry-day stops.')
    ledger=[x for a in assets for x in a['ledger_checks']]
    if any(x['off_tick_fills'] or abs(x['cash_difference'])>.010001 for x in ledger):
        raise ValueError('Execution ledger checks failed.')
    strategies=[]
    for row in rows:
        if row['cost']!='base':continue
        stress=next((x for x in rows if x['symbol']==row['symbol'] and x['strategy']==row['strategy'] and x['cost']=='double'),None)
        strategies.append({'symbol':row['symbol'],'strategy':row['strategy'],
            'baseReturn':row['return_pct'],'stressedReturn':stress['return_pct'] if stress else None,
            'maxDrawdown':row['max_drawdown_pct'],'trades':row['trades'],'source':'TQSDK_OBSERVED_DELIVERY'})
    hashes={a['symbol']:hashlib.sha256((ROOT/'data/history/tqsdk-roll'/(a['symbol']+'_real_roll_daily.json')).read_bytes()).hexdigest() for a in assets}
    payload={'schemaVersion':1,'modelVersion':settings.version,'engineFingerprint':fingerprint,
        'generatedAt':datetime.now(SHANGHAI).isoformat(),'period':{'start':summary['protocol']['start'],'end':summary['protocol']['end']},
        'assets':len(assets),'cases':len(rows),'profitabilityValidated':False,'outOfSampleValidated':False,
        'executionChecks':{'missedStops':0,'offTickFills':0,'cashDifference':max(abs(x['cash_difference']) for x in ledger)},
        'strategies':strategies,'datasetHashes':hashes,'protocol':summary['protocol'],
        'limits':['固定参数的回顾性诊断，未完成独立样本外或前瞻验证，不提供盈利概率。',
            '历史融合仅覆盖 0.64 配置权重，未补造历史天气、新闻、规则等外部证据。',
            '股指使用近期 799 根真实日线覆盖评估区间；2018-07-23 的旧换月腿缺价区间仍被拒绝。',
            '双倍成本同时提高按手手续费、费率和滑点；移除文化因素对照只运行基础成本。',
            '当前合约规格与日线成交假设不能重现历史全部保证金变更、盘口排队和涨跌停成交。']}
    destination.parent.mkdir(parents=True,exist_ok=True)
    temp=destination.with_suffix('.tmp')
    temp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(destination)
    return {'modelVersion':settings.version,'cases':len(rows),'assets':len(assets),'profitabilityValidated':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=ROOT/'.test-tmp/real-validation-fixed-20261017')
    parser.add_argument('--output',type=Path,default=ROOT/'data/history/validation/research-validation.json')
    args=parser.parse_args()
    print(json.dumps(publish(args.source,args.output)))
