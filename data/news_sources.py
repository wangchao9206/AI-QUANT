"""Attributed source collection. A failed publisher never hides other feeds."""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

from data.evidence_feed import SHANGHAI_TZ

SOURCES = [
    {'id': 'ndrc', 'name': '国家发展改革委', 'tier': 'PRIMARY', 'kind': 'html',
     'url': 'https://www.ndrc.gov.cn/xwdt/xwfb/', 'scope': '产业政策、能源保供、价格干预'},
    {'id': 'nbs', 'name': '国家统计局', 'tier': 'PRIMARY', 'kind': 'html',
     'url': 'https://www.stats.gov.cn/sj/zxfb/', 'scope': '工业产量、价格与宏观统计'},
    {'id': 'fed', 'name': '美联储', 'tier': 'PRIMARY', 'kind': 'rss',
     'url': 'https://www.federalreserve.gov/feeds/press_all.xml', 'scope': '美国货币政策与金融条件'},
    {'id': 'eia', 'name': '美国能源信息署 EIA', 'tier': 'PRIMARY', 'kind': 'rss',
     'url': 'https://www.eia.gov/rss/todayinenergy.xml', 'scope': '能源供需分析；Today in Energy 并非库存报告快讯'},
    {'id': 'usda', 'name': '美国农业部 NASS', 'tier': 'PRIMARY', 'kind': 'rss',
     'url': 'https://www.nass.usda.gov/rss/news.xml', 'scope': '种植面积、产量与农产品统计原始发布'},
    {'id': 'shfe', 'name': '上海期货交易所', 'tier': 'PRIMARY', 'kind': 'shfe',
     'url': 'https://www.shfe.com.cn/publicnotice/notice/', 'scope': '交易、交割及风险管理公告'},
    {'id': 'eastmoney', 'name': '东方财富期货频道收录', 'tier': 'SECONDARY', 'kind': 'eastmoney',
     'url': 'https://futures.eastmoney.com/', 'scope': '媒体汇编；需回溯原始发布者'},
]


def text_only(text):
    from html import unescape
    return re.sub(r'\s+', ' ', unescape(re.sub('<[^>]*>', '', text or ''))).strip()


def canonical_url(url):
    parts = urlsplit(url)
    if parts.scheme not in ('https', 'http') or not parts.hostname or parts.username:
        return ''
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ''))


def parse_rss(payload, source):
    root = ET.fromstring(payload.lstrip('\ufeff'))
    result = []
    for entry in root.findall('.//item'):
        title = text_only(entry.findtext('title'))
        url = canonical_url(entry.findtext('link') or '')
        try:
            stamp = parsedate_to_datetime(entry.findtext('pubDate') or '')
            if stamp.tzinfo is None:
                continue  # Never guess the publisher's timezone.
        except (ValueError, TypeError):
            continue
        if title and url:
            result.append({'title': title, 'url': url, 'publishedAt': stamp.isoformat(),
                           'summary': '', 'timePrecision': 'MINUTE'})
    return result


def parse_official_html(payload, source):
    result = []
    for block in re.findall(r'<li\b[^>]*>(.*?)</li>', payload, re.S | re.I):
        link = re.search(r'<a\b[^>]*href=[\'\"]([^\'\"]+)[\'\"][^>]*>(.*?)</a>', block, re.S | re.I)
        date = re.search(r'(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})', text_only(block))
        if not link or not date:
            continue
        try:
            stamp = datetime(*map(int, date.groups()), tzinfo=SHANGHAI_TZ)
        except ValueError:
            continue
        title = text_only(link[2]); url = canonical_url(urljoin(source['url'], link[1]))
        # Reject menu anchors and unrelated hosts, and require an actual article.
        if title and url and urlsplit(url).hostname == urlsplit(source['url']).hostname and url != source['url']:
            result.append({'title': title, 'url': url, 'publishedAt': stamp.isoformat(),
                           'summary': '', 'timePrecision': 'DAY'})
    return result


class NewsCollector:
    def __init__(self, read_text, cache_path=None):
        self.read_text = read_text
        self.path = Path(cache_path) if cache_path else Path(os.environ.get('HISTORY_CACHE_DIR', 'data/history')) / 'news/radar.json'
        self.lock = threading.Lock()

    def collect(self):
        with self.lock:
            return self._collect()

    def _collect(self):
        try:
            previous = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            previous = {}
        now = datetime.now(timezone.utc)

        def fetch(source):
            try:
                payload = self.read_text(source['url'])
                if source['kind'] == 'rss':
                    rows = parse_rss(payload, source)
                elif source['kind'] == 'shfe':
                    blocks = re.findall(r'<div\s+class="table_item_info">(.*?)<div\s+class="info_item_date">([^<]*)</div>', payload, re.S)
                    rows = parse_official_html(''.join('<li>' + b + '<span>' + d + '</span></li>' for b, d in blocks), source)
                elif source['kind'] == 'html':
                    rows = parse_official_html(payload, source)
                else:
                    from data.radar_feed import parse_market_news
                    rows = parse_market_news(payload)
                rows = [r for r in rows if datetime.fromisoformat(r['publishedAt']) <= now + timedelta(minutes=5)]
                if not rows:
                    raise ValueError('no dated entries')
                rows = rows[:100]
                return source, {'items': rows, 'fetchedAt': now.isoformat()}, 'READY'
            except Exception:
                saved = previous.get(source['id'], {})
                return source, saved, 'CACHED' if saved.get('items') else 'UNAVAILABLE'

        items = []; statuses = []; updated = {}; seen = set()
        with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
            for source, snapshot, status in pool.map(fetch, SOURCES):
                updated[source['id']] = snapshot
                statuses.append({**{k: v for k, v in source.items() if k != 'kind'},
                                 'status': status, 'fetchedAt': snapshot.get('fetchedAt'),
                                 'itemCount': len(snapshot.get('items', [])),
                                 'message': '本次已读取' if status == 'READY' else '读取失败，保留原采集时间' if status == 'CACHED' else '本次未取得带日期的有效条目'})
                if snapshot.get('items'):
                    newest = max(datetime.fromisoformat(r['publishedAt']) for r in snapshot['items'])
                    statuses[-1]['latestPublishedAt'] = newest.isoformat()
                    if now - newest > timedelta(days=90):
                        statuses[-1]['message'] += '；源列表最新条目已超过90天，非近期快讯'
                for row in snapshot.get('items', []):
                    url = canonical_url(row['url'])
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    items.append({**row, 'id': hashlib.sha256(url.encode()).hexdigest()[:20],
                                  'publisher': source['name'], 'sourceId': source['id'],
                                  'sourceTier': source['tier'], 'sourceStatus': status,
                                  'fetchedAt': snapshot.get('fetchedAt')})
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps(updated, ensure_ascii=False), encoding='utf-8')
            tmp.replace(self.path)
        except OSError:
            pass  # Collection remains usable on a read-only deployment.
        items.sort(key=lambda i: datetime.fromisoformat(i['publishedAt']), reverse=True)
        return {'status': 'READY' if all(s['status'] == 'READY' for s in statuses) else 'PARTIAL' if items else 'UNAVAILABLE',
                'items': items, 'sources': statuses, 'source': '官方原始发布与媒体汇编 · 独立采集',
                'dataTimestamp': items[0]['publishedAt'] if items else None, 'fetchedAt': now.isoformat(),
                'message': '仅展示各源当前列表及上次成功快照，不是完整新闻档案；原文时间与采集时间分别记录。相同事件的转发不作为独立验证。'}
