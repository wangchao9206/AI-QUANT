"""Native sealed-input monitor analysis. Distinct from frozen FU profiles."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from datetime import datetime

from .native import NativeEngine, VERSION, PARAMETERS

ROOT = Path(__file__).resolve().parents[1]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


class InputConflict(ValueError):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


def merge_closed(previous, incoming, symbol):
    if not incoming:
        raise InputConflict('WAITING_DATA', '没有已封存行情')
    def checked(bars):
        for i, b in enumerate(bars):
            datetime.fromisoformat(b['timestamp'])
            if i and (b['providerIndex'] != bars[i-1]['providerIndex']+1 or b['timestamp'] <= bars[i-1]['timestamp']):
                raise InputConflict('GAP', '主源 K 线序列不连续，暂停并保留原水位')
    checked(incoming); checked(previous)
    fields = ('providerIndex','timestamp','date','volume','open','high','low','close')
    if previous:
        overlap = {b['providerIndex']: b for b in incoming}
        if previous[-1]['providerIndex'] not in overlap:
            raise InputConflict('GAP', '源窗口已越过保存水位，需要人工检查后新建任务')
        for old in previous:
            new = overlap.get(old['providerIndex'])
            if new and any(new[k] != old[k] for k in fields):
                raise InputConflict('INPUT_REVISED', '已封存行情发生修订，保留原输入并暂停')
        merged = previous + [b for b in incoming if b['providerIndex'] > previous[-1]['providerIndex']]
    else:
        merged = incoming
    if len(merged) > 10000:
        raise InputConflict('LIMIT_REACHED', '单任务达到一万根保留上限，请归档后新建')
    return [{**b, 'index': i, 'contract': symbol} for i,b in enumerate(merged)]


def profile_for(symbol, frequency):
    sources = [Path(__file__), ROOT/'chanlun_worker/native.py', ROOT/'data/chanlun_monitor_source.py']
    implementation = hashlib.sha256(b''.join(p.read_bytes().replace(b'\r\n',b'\n') for p in sources)).hexdigest()
    profile = {'engine':'native','version':VERSION,'parameters':PARAMETERS,'symbol':symbol,
        'frequency':frequency,'priceBasis':'UNADJUSTED_DELIVERY','implementationHash':implementation}
    return profile, hashlib.sha256(canonical(profile).encode()).hexdigest()


def observe(bars, symbol, frequency):
    scope = f'native:{symbol}:{frequency}:UNADJUSTED_DELIVERY'
    profile, profile_hash = profile_for(symbol, frequency)
    engine = NativeEngine()
    latest, current, events = {}, {}, []
    for bar in bars:
        engine.push(bar)
        next_state = {}
        for raw in engine.structures():
            anchor = f"{scope}:{raw['type']}:{raw['startIndex']}:{raw['direction']}:{raw.get('identityScope','')}"
            identity = hashlib.sha256(anchor.encode()).hexdigest()[:24]
            old = latest.get(identity)
            if not old or old['raw'] != raw or old['state'] == 'RETRACTED':
                raw = deepcopy(raw)
                record = {**raw, 'raw':raw, 'id':identity, 'revision':old['revision']+1 if old else 1,
                    'state':'CURRENT','firstObservedIndex':old['firstObservedIndex'] if old else bar['index'],
                    'observedIndex':bar['index'], 'firstObservedDate':bars[old['firstObservedIndex'] if old else bar['index']]['timestamp'],
                    'engineConfirmedDate':bar['timestamp'] if raw['engineConfirmed'] else None,
                    'eligibleAt':None,'pivotStartDate':bars[raw['startIndex']]['timestamp'],
                    'pivotEndDate':bars[raw['endIndex']]['timestamp']}
                events.append({**record,'eventType':'OBSERVED' if not old or old['state']=='RETRACTED' else 'REVISED',
                               'eventSeq':len(events)+1})
                latest[identity] = record
            else:
                record = old
            next_state[identity] = record
        for identity, old in current.items():
            if identity not in next_state:
                record = {**old,'revision':old['revision']+1,'state':'RETRACTED','observedIndex':bar['index']}
                latest[identity] = record
                events.append({**record,'eventType':'RETRACTED','eventSeq':len(events)+1})
        current = next_state
    return {'engineId':'native','engineVersion':VERSION,'profile':profile,'profileHash':profile_hash,
            'symbol':symbol,'frequency':frequency,'priceBasis':'UNADJUSTED_DELIVERY','executable':False,
            'bars':bars,'observedBars':len(bars),'observedAsOfDate':bars[-1]['timestamp'],
            'structures':[{**s,'observedAsOfDate':bars[-1]['timestamp']} for s in current.values()],
            'events':[e for e in events if e['type']=='BSP'],'lastEventSeq':len(events),
            'inputHash':hashlib.sha256(canonical(bars).encode()).hexdigest()}
