"""Collect only organizer-exposed public aggregates. No login or account guessing.

The endpoints and parameters below come from the public website's own client.
Run from the repository root. --from-cache reuses inspected development snapshots.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE='https://spdspc.qhrb.com.cn'
OUT=Path('algorithm_service/mentor_contest_snapshot.json')


def fetch(path):
    with urlopen(Request(BASE+'/api'+path,headers={'User-Agent':'Mozilla/5.0','Referer':BASE+'/'}),timeout=12) as response:
        result=json.load(response)
    if result.get('statusCode')!=1: raise ValueError('Public source did not grant a successful response')
    return result


def collect(cache=None):
    latest = json.loads((cache/'mentor-public-date.json').read_text(encoding='utf-8')) if cache else fetch('/spsread2026/adm/getLastDayFront')
    day = latest['dataPoints'][:10]
    params={'tradeDate':day,'groupType':1,'rankType':0,'index':1,'size':5,'selType':0}
    rank_path='/spsread2026/groupBaseFront/getBaseScoreTotalListAdm?'+urlencode(params)
    rank = json.loads((cache/'mentor-public-rank.json').read_text(encoding='utf-8')) if cache else fetch(rank_path)
    rows = rank['dataPoints']['list'][:3]
    accounts=[]
    for i,row in enumerate(rows):
        query=urlencode({'playerId':row['playerId'],'tradeDate':day})
        responses={}
        for kind in ['getBasicVo','getBreedTotalVO']:
            responses[kind]=json.loads((cache/f'mentor-public-{i}-{kind}.json').read_text(encoding='utf-8')) if cache else fetch('/spsread2026/curveFront/'+kind+'?'+query)
            if responses[kind].get('statusCode')!=1: raise ValueError('Invalid organizer response')
        basic=responses['getBasicVo']['dataPoints'];stats=responses['getBreedTotalVO']['dataPoints']
        record=basic['basicDataFrontVO']
        account={'id':hashlib.sha256(row['playerId'].encode()).hexdigest()[:16],
                 'alias':row['playerNickName'],'rank':row['sortNo'],'groupLabel':'全国赛轻量组公开综合统计样本',
                 'identityStatus':'PUBLIC_CONTEST_ALIAS','evidenceType':'ORGANIZER_AGGREGATE',
                 'statementStatus':'NO_EXECUTION_LEDGER','periodStart':record['beginMatchTime'],'asOf':day,
                 'reported':{k:record[k] for k in ['netProfit','netWorth','maxWithrawalRate','realDealDays']},
                 'futuresByBreed':stats.get('totalBreedVOList') or [],'optionsByBreed':stats.get('optTotalBreedVOList') or [],
                 'netWorth':[{'date':p['tradeDate'][:10],'value':p['netWorth']} for p in basic['netWorthVOList']],
                 'sourceUrls':[BASE+'/',BASE+'/api'+rank_path,*[BASE+'/api/spsread2026/curveFront/'+kind+'?'+query for kind in responses]],
                 'sourceSha256':hashlib.sha256(json.dumps(responses,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
        accounts.append(account)
    capture_files = [cache/'mentor-public-date.json',cache/'mentor-public-rank.json',
                     *[cache/f'mentor-public-{i}-{kind}.json' for i in range(len(rows)) for kind in ['getBasicVo','getBreedTotalVO']]] if cache else []
    captured = datetime.fromtimestamp(max(p.stat().st_mtime for p in capture_files),timezone.utc) if cache else datetime.now(timezone.utc)
    result={'status':'OBSERVED_PUBLIC_AGGREGATES','publisher':'期货日报实盘大赛主办方公开平台',
            'fetchedAt':captured.isoformat(),'asOf':day,
            'sampling':f'{day}公开轻量组综合统计前3个账户；仅优胜者小样本，不代表全体交易者。不是独立审计或终身业绩。',
            'identityWarning':'官方昵称可独立研究，无需公开实名。同名跨赛事、届次或组别不自动关联；汇总统计仍不等于完整交割单。',
            'accounts':accounts}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'accounts':len(accounts),'asOf':day,'output':str(OUT)},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--from-cache',type=Path)
    collect(parser.parse_args().from_cache)
