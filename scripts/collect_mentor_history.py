"""Collect public 2024 contest evidence, retaining source payloads for review.

Only account IDs returned by the public ranking are used. No login, token or
private trade endpoint is used. --from-cache reads previously captured responses.
Run from the repository root; failed/incomplete responses never replace a snapshot.
"""
import argparse
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = 'https://spdspc.qhrb.com.cn'
TARGETS = {'北海大盗':'alias-beihaidadao', '一切都好':'alias-yiqiedouhao',
           '南方以南':'alias-nanfangyinan', '期海浮萍':'alias-qihaifuping'}
KINDS = ['getBasicVo', 'getBreedTotalVO', 'getBreedVOList', 'getDayProfit', 'getRiskDegree']


def collect(cache=None):
    captured = []
    files = []

    def read(path, name):
        url = BASE+'/api/spsread2024/'+path
        if cache:
            file = cache/name
            payload = json.loads(file.read_text(encoding='utf-8'))
            files.append(file)
            # The public mobile and desktop hosts expose the same 2024 service.
            origin = BASE if any(k in name for k in ['getDayProfit','getRiskDegree']) or (
                'getBasicVo' in name and any(pid in name for pid in [
                    '7c6b02df-8a53-415b-8a93-299859dd3d79','fcff0e2f-0a67-4bf2-8e71-66743da9290e'])) else 'https://ds.qhrb.com.cn'
            url = origin+'/api/spsread2024/'+path
        else:
            with urlopen(Request(url, headers={'User-Agent':'Mozilla/5.0', 'Referer':BASE+'/'}), timeout=30) as response:
                payload = json.load(response)
        if payload.get('statusCode') != 1 or payload.get('dataPoints') is None:
            raise ValueError(f'公开接口未返回成功数据：{path.split("?")[0]}')
        captured.append({'url':url, 'payload':payload})
        return payload['dataPoints'], url

    day, _ = read('adm/getLastDayFront', 'mentor-2024-date.json')
    day = day[:10]
    accounts = []
    for group in [1,2]:
        query = urlencode({'tradeDate':day,'groupType':group,'rankType':0,'index':1,'size':10,'selType':0})
        ranks, rank_url = read('groupBaseFront/getBaseScoreTotalListAdm?'+query, f'mentor-2024-rank{group}.json')
        for row in ranks['list']:
            alias = row['playerNickName']
            if alias not in TARGETS:
                continue
            values, urls = {}, [rank_url]
            query = urlencode({'playerId':row['playerId'],'tradeDate':day})
            for kind in KINDS:
                values[kind], url = read('curveFront/'+kind+'?'+query, f'mentor-2024-{row["playerId"]}-{kind}.json')
                urls.append(url)
            basic = values['getBasicVo']['basicDataFrontVO']
            if basic['nickName'] != alias or basic['groupType'] != group:
                raise ValueError('账户昵称或组别与公开榜单不一致')
            statistics = values['getBreedTotalVO']
            accounts.append({
                'id':hashlib.sha256(('qhrb:2024:'+row['playerId']).encode()).hexdigest()[:16],
                'profileId':TARGETS[alias], 'alias':alias, 'rank':row['sortNo'], 'year':2024, 'edition':18,
                'groupLabel':'第十八届 · '+('轻量组' if group==1 else '重量组'),
                'identityStatus':'PUBLIC_CONTEST_ALIAS', 'evidenceType':'ORGANIZER_AGGREGATE',
                'statementStatus':'NO_EXECUTION_LEDGER', 'periodStart':basic['beginMatchTime'], 'asOf':day,
                'reported':basic,
                'futuresByBreed':statistics.get('totalBreedVOList') or [],
                'optionsByBreed':statistics.get('optTotalBreedVOList') or [],
                'tradeStatistics':values['getBreedVOList'],
                'netWorth':[{'date':p['tradeDate'][:10],'value':p['netWorth']} for p in values['getBasicVo']['netWorthVOList']],
                'dailyProfit':values['getDayProfit'], 'dailyRisk':values['getRiskDegree'],
                'sourceUrls':urls,
                'sourceSha256':hashlib.sha256(json.dumps(values,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
            })
    if {a['alias'] for a in accounts} != set(TARGETS):
        raise ValueError('四个目标账户未全部取得，保留原快照')
    fetched = datetime.fromtimestamp(max(p.stat().st_mtime for p in files), timezone.utc) if cache else datetime.now(timezone.utc)
    result = {'status':'OBSERVED_PUBLIC_AGGREGATES', 'fetchedAt':fetched.isoformat(), 'asOf':day,
              'publisher':'期货日报实盘大赛公开平台',
              'sampling':'第十八届公开榜单中与研究档案对应的四个昵称账户；优胜者选择样本，不能外推全体投资者。',
              'accounts':accounts}
    target = Path('algorithm_service/mentor_historical_snapshot.json')
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    archive = Path('docs/research/data/mentor-2024-source-responses.json.gz')
    archive.parent.mkdir(parents=True,exist_ok=True)
    archive.write_bytes(gzip.compress(json.dumps({'fetchedAt':result['fetchedAt'],'responses':captured},ensure_ascii=False,sort_keys=True).encode(),mtime=0))
    print(json.dumps({'accounts':len(accounts),'netWorthPoints':sum(len(a['netWorth']) for a in accounts),'output':str(target)},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--from-cache',type=Path)
    collect(parser.parse_args().from_cache)
