"""Public, attributed news and overseas reference quotes for the market desk."""
from __future__ import annotations

import math
import re
import threading
import time
import urllib.request
from copy import deepcopy
from datetime import datetime, timezone
from html import unescape

from data.evidence_feed import EvidenceFeed, SHANGHAI_TZ


def clean_text(value):
    return unescape(re.sub(r'<[^>]*>', '', str(value or ''))).strip()


def safe_url(value):
    value = str(value or '').strip()
    return value if re.match(r'^https?://[^\s]+$', value, re.I) else ''


def parse_market_news(page):
    """Read the dated cross-product headline lists, not the CJ column API."""
    items=[];seen=set()
    for match in re.finditer(r'<li\b[^>]*\bid=[\'\"]newsTr[^\'\"]*[\'\"][^>]*>(.*?)</li>',page,re.S|re.I):
        block=match[1]
        heading=re.search(r'<h2\b[^>]*class=[\'\"]retitle[\'\"][^>]*>(.*?)</h2>',block,re.S|re.I)
        if not heading:continue
        link=re.search(r'<a\b[^>]*href=[\'\"]([^\'\"]+)[\'\"][^>]*>(.*?)</a>',heading[1],re.S|re.I)
        clock=re.search(r'<p\b[^>]*class=[\'\"]time[\'\"][^>]*>(.*?)</p>',block,re.S|re.I)
        if not link or not clock:continue
        url=safe_url(unescape(link[1]));title=clean_text(link[2])
        article=re.search(r'/a/(\d{8})(\d+)\.html',url)
        if not article or not title or title in seen:continue
        try:
            observed=datetime.strptime(article[1][:4]+'年'+clean_text(clock[1]),'%Y年%m月%d日 %H:%M').replace(tzinfo=SHANGHAI_TZ)
            if observed.strftime('%Y%m%d')!=article[1]:continue
        except ValueError:continue
        seen.add(title)
        items.append({'id':article[1]+article[2],'title':title,'summary':'','url':url,
            'publisher':'东方财富期货频道收录','publishedAt':observed.isoformat(),'timePrecision':'MINUTE'})
    return sorted(items,key=lambda i:i['publishedAt'],reverse=True)


class RadarCache:
    def __init__(self):
        self.values = {}
        self.locks = {}
        self.lock = threading.Lock()

    def get(self, key, ttl, loader):
        with self.lock:
            lock = self.locks.setdefault(key, threading.Lock())
        with lock:
            previous = self.values.get(key)
            if previous and time.monotonic() < previous[0]:
                return deepcopy(previous[1])
            try:
                result = loader()
                self.values[key] = (time.monotonic() + ttl, deepcopy(result))
                return result
            except Exception:
                if previous and previous[1].get('dataTimestamp'):
                    result = {**deepcopy(previous[1]), 'status':'DEGRADED', 'message':'上游暂不可用，保留上次成功快照'}
                else:
                    result = {'status':'UNAVAILABLE', 'items':[], 'dataTimestamp':None, 'message':'暂未取得有效数据，请稍后重试'}
                # Failure backoff must not turn an old observation into fresh data.
                self.values[key] = (time.monotonic() + 20, deepcopy(result))
                return result


GLOBAL_INSTRUMENTS = {
    'GC':('纽约黄金 CFD','美元/盎司',['AUM'],'贵金属'),
    'SI':('纽约白银 CFD','美元/盎司',['AGM'],'贵金属'),
    'CL':('纽约原油 CFD','美元/桶',['SCM','FUM','BUM'],'能源'),
    'OIL':('布伦特原油参考','美元/桶',['SCM','LUM'],'能源'),
    'HG':('纽约铜 CFD','美分/磅',['CUM','BCM'],'有色'),
    'S':('美大豆参考','美分/蒲式耳',['MM','YM','AM','BM'],'农产品'),
    'C':('美玉米参考','美分/蒲式耳',['CM','CSM'],'农产品'),
    'W':('美小麦参考','美分/蒲式耳',['WHM','PMM'],'农产品'),
}


def parse_global_quotes(text, now=None):
    now = now or datetime.now(timezone.utc)
    items = []
    for code, body in re.findall(r'var\s+hq_str_hf_(\w+)="([^"]*)"', text):
        if code not in GLOBAL_INSTRUMENTS:
            continue
        fields = body.split(',')
        try:
            price, settlement = float(fields[0]), float(fields[7])
            observed = datetime.fromisoformat(f'{fields[12]}T{fields[6]}').replace(tzinfo=SHANGHAI_TZ)
            if not all(math.isfinite(n) and n > 0 for n in (price, settlement)):
                continue
            age = (now-observed.astimezone(timezone.utc)).total_seconds()
            if age < -300:
                continue
        except (ValueError, IndexError):
            continue
        name, unit, related, sector = GLOBAL_INSTRUMENTS[code]
        items.append({'symbol':code,'name':name,'unit':unit,'sector':sector,'price':price,
            'changePct':round((price/settlement-1)*100,3),'previousSettlement':settlement,
            'dataTimestamp':observed.isoformat(),'dataStatus':'FRESH' if age<=900 else 'CACHED',
            'relatedSymbols':related, 'sourceUrl':f'https://finance.sina.com.cn/futures/quotes/{code}.shtml'})
    return items


class PublicRadarFeed:
    def __init__(self):
        self.cache = RadarCache()
        self.evidence = EvidenceFeed(timeout=6)

    def news(self):
        return self.cache.get('news',180,self._news)

    def _news(self):
        items=parse_market_news(self.evidence._read_text('https://futures.eastmoney.com/'))
        if not items:
            raise ValueError('No dated news')
        return {'status':'READY','items':items[:30], 'source':'东方财富期货频道跨品种要闻',
            'sourceUrl':'https://futures.eastmoney.com/', 'dataTimestamp':items[0]['publishedAt'],
            'fetchedAt':datetime.now(SHANGHAI_TZ).isoformat()}

    def overseas(self):
        return self.cache.get('overseas',60,self._overseas)

    def _overseas(self):
        url='https://hq.sinajs.cn/?list='+','.join('hf_'+code for code in GLOBAL_INSTRUMENTS)
        request=urllib.request.Request(url,headers={'Referer':'https://finance.sina.com.cn/','User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(request,timeout=6) as response:
            payload=response.read()
        try:text=payload.decode('utf-8')
        except UnicodeDecodeError:text=payload.decode('gb18030',errors='replace')
        items=parse_global_quotes(text)
        if not items:
            raise ValueError('No valid overseas observations')
        missing=[code for code in GLOBAL_INSTRUMENTS if code not in {i['symbol'] for i in items}]
        return {'status':'PARTIAL' if missing else 'READY','source':'新浪财经外盘参考行情',
            'dataTimestamp':max(item['dataTimestamp'] for item in items),'items':items,'missing':missing,
            'message':'含 CFD / 参考报价，非交易所授权实时盘口；时间为北京时间，各市场结算时点不同。关联仅为产业链提示，不代表相关系数或套利信号。'}
