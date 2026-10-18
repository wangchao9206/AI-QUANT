"""Capture additional public contest accounts from observed ranking rows.

No account guessing or authentication. These are historical ranking observations,
not automatic claims about final awards or a person's lifetime performance.
"""
import argparse
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE='https://spdspc.qhrb.com.cn'
KINDS=['getBasicVo','getBreedTotalVO','getBreedVOList','getDayProfit','getRiskDegree']
EXISTING={'北海大盗','一切都好','南方以南','期海浮萍'}


def collect(cache=None):
    captures=[];files=[];accounts=[]

    def read(year,path,name):
        url=f'{BASE}/api/spsread{year}/'+path
        if cache:
            file=cache/name;files.append(file)
            payload=json.loads(file.read_text(encoding='utf-8'))
            if year==2024 and ('-rank' in name or name.endswith('-date.json')):url=url.replace(BASE,'https://ds.qhrb.com.cn')
        else:
            with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':BASE+'/'}),timeout=25) as response:payload=json.load(response)
        if payload.get('statusCode')!=1 or payload.get('dataPoints') is None:raise ValueError('公开资料未返回成功；保留旧快照')
        captures.append({'url':url,'payload':payload})
        return payload['dataPoints'],url

    for year in [2024,2025]:
        day,_=read(year,'adm/getLastDayFront',f'mentor-{year}-date.json');day=day[:10]
        for group in [1,2]:
            params={'tradeDate':day,'groupType':group,'rankType':0,'index':1,'size':10 if year==2024 else 3,'selType':0}
            rank,rank_url=read(year,'groupBaseFront/getBaseScoreTotalListAdm?'+urlencode(params),f'mentor-{year}-rank{group}.json')
            for row in rank['list'][:3]:
                if year==2024 and row['playerNickName'] in EXISTING:continue
                values={};urls=[rank_url]
                query=urlencode({'playerId':row['playerId'],'tradeDate':day})
                for kind in KINDS:
                    values[kind],url=read(year,'curveFront/'+kind+'?'+query,f'mentor-{year}-{row["playerId"]}-{kind}.json');urls.append(url)
                basic=values['getBasicVo']['basicDataFrontVO'];stats=values['getBreedTotalVO']
                if basic['nickName']!=row['playerNickName'] or basic['groupType']!=group:raise ValueError('榜单与账户身份上下文不一致')
                accounts.append({'id':hashlib.sha256(f'qhrb:{year}:{row["playerId"]}'.encode()).hexdigest()[:16],
                    'alias':row['playerNickName'],'rank':row['sortNo'],'year':year,'edition':year-2006,
                    'groupLabel':f'第{year-2006}届 · '+('轻量组' if group==1 else '重量组'),'sourceId':'contest-archive',
                    'identityStatus':'PUBLIC_CONTEST_ALIAS','evidenceType':'ORGANIZER_AGGREGATE','statementStatus':'NO_EXECUTION_LEDGER',
                    'periodStart':basic['beginMatchTime'],'asOf':day,'reported':basic,
                    'futuresByBreed':stats.get('totalBreedVOList') or [],'optionsByBreed':stats.get('optTotalBreedVOList') or [],
                    'tradeStatistics':values['getBreedVOList'],
                    'netWorth':[{'date':p['tradeDate'][:10],'value':p['netWorth']} for p in values['getBasicVo']['netWorthVOList']],
                    'dailyProfit':values['getDayProfit'],'dailyRisk':values['getRiskDegree'],'sourceUrls':urls,
                    'sourceSha256':hashlib.sha256(json.dumps(values,ensure_ascii=False,sort_keys=True).encode()).hexdigest()})
    if len(accounts)!=8:raise ValueError('未取得预期8个公开账户；保留旧快照')
    captured=datetime.fromtimestamp(max(p.stat().st_mtime for p in files),timezone.utc) if cache else datetime.now(timezone.utc)
    result={'status':'OBSERVED_PUBLIC_AGGREGATES','fetchedAt':captured.isoformat(),'accounts':accounts,
            'sampling':'2024及2025年公开轻量、重量榜单前三名中的新增8个账户；采集时点观察，不自动认定最终颁奖结果。'}
    Path('algorithm_service/mentor_archive_snapshot.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    archive=Path('docs/research/data/mentor-archive-source-responses.json.gz');archive.parent.mkdir(parents=True,exist_ok=True)
    archive.write_bytes(gzip.compress(json.dumps({'fetchedAt':result['fetchedAt'],'responses':captures},ensure_ascii=False,sort_keys=True).encode(),mtime=0))
    print(json.dumps({'accounts':len(accounts),'nav':sum(len(a['netWorth']) for a in accounts)},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--from-cache',type=Path)
    collect(parser.parse_args().from_cache)
