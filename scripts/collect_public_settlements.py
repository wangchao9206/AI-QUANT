"""Read organizer-published daily cash tables. Private execution data is not requested."""
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE='https://ifutures.cs.com.cn'
FIELDS=['dateline','balance','equity','cbalance','today_in','today_out','profit','margin',
        'fee','available','additional','royalty','roy_buy','roy_sell','risk','pledge','fprofit']


def collect():
    responses=[]

    def read(path, params):
        url=BASE+'/api/trader/'+path+'?'+urlencode(params)
        with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':BASE+'/'}),timeout=25) as response:
            payload=json.load(response)
        if payload.get('response')!=0: raise ValueError('公开数据未返回成功，保留原快照')
        responses.append({'url':url,'payload':payload})
        return payload,url

    rank,rank_url=read('contest/contestList',{'number':3,'showPage':1,'page':1,'tid':1,'kw':''})
    rows=rank['data']['data']
    rows=list(rows.values()) if isinstance(rows,dict) else rows
    accounts=[]
    for account in rows[:3]:
        data=[];urls=[];access=False
        for page in range(1,51):
            payload,url=read('AnalyseData/overviewData',{'aid':account['id'],'tid':1,'page':page})
            chunk=payload['data']['data'];urls.append(url)
            access=access or payload.get('access',False)
            if not isinstance(chunk,list):raise ValueError('公开资金表结构变化')
            data.extend({k:r.get(k) for k in FIELDS} for r in chunk)
            if len(chunk)<15:break
        else:raise ValueError('超过分页上限，停止保存不完整快照')
        dates=[r['dateline'] for r in data]
        if not data or len(dates)!=len(set(dates)):raise ValueError('资金表为空或日期重复')
        data.sort(key=lambda r:r['dateline'])
        accounts.append({'id':hashlib.sha256(('cs:1:'+account['id']).encode()).hexdigest()[:16],
                         'alias':account.get('nickname') or account['user'],'rank':account['no'],
                         'sourceUrl':BASE+'/trader/contestDetail/'+account['id']+'-1.html',
                         'rawTradesPublic':bool(access),'rows':data,'sourceUrls':urls,
                         'sourceSha256':hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()})
    result={'publisher':'中证网 · 首届金牛至赢期货大赛','fetchedAt':datetime.now(timezone.utc).isoformat(),
            'sampling':'采集时公开总榜前3个账户，比赛仍在进行；仅作资金表对照，未认定长期成功或与既有人物同一身份。',
            'accounts':accounts,'rankSourceUrl':rank_url}
    Path('algorithm_service/mentor_settlement_snapshot.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    archive=Path('docs/research/data/mentor-settlement-source-responses.json.gz')
    archive.parent.mkdir(parents=True,exist_ok=True)
    archive.write_bytes(gzip.compress(json.dumps({'fetchedAt':result['fetchedAt'],'responses':responses},ensure_ascii=False,sort_keys=True).encode(),mtime=0))
    print(json.dumps({'accounts':len(accounts),'dailyRows':sum(len(a['rows']) for a in accounts),'rawTradePermission':[a['rawTradesPublic'] for a in accounts]},ensure_ascii=False))


if __name__=='__main__':collect()
