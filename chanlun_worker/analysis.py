"""Prefix-only calculation and append-only observation revisions."""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .adapters import ADAPTERS, ADAPTER_VERSION
from .data import DATASET_HASH, DATASET_ID, PRICE_BASIS, catalog, load_dataset


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def analyze(engine_id: str, observed_bars: int):
    if engine_id not in ADAPTERS:
        raise ValueError('Unsupported engine')
    all_bars = load_dataset()
    if not 50 <= observed_bars <= len(all_bars):
        raise ValueError('Observation prefix is outside the frozen dataset')
    adapter = ADAPTERS[engine_id]()
    root=Path(__file__).resolve().parents[1]
    sources=[root/'chanlun_worker'/name for name in ('analysis.py','adapters.py','data.py')]
    sources += [root/'third_party/chanpy/manifest.json'] if engine_id=='chanpy' else [root/'backtesting/chanlun_research.py'] if engine_id=='baseline' else []
    if engine_id=='native':sources.append(root/'chanlun_worker/native.py')
    digest=hashlib.sha256(b''.join(p.read_bytes().replace(b'\r\n',b'\n') for p in sources)).hexdigest()
    profile = {'engine': engine_id, 'version': adapter.version, 'implementationHash':digest,
               'adapterVersion': ADAPTER_VERSION, 'parameters': adapter.parameters, 'priceBasis': PRICE_BASIS}
    profile_hash = hashlib.sha256(canonical(profile).encode()).hexdigest()
    bars = all_bars[:observed_bars]
    current, latest, events, identities = {}, {}, [], {}
    recorded_at = datetime.now(timezone.utc).isoformat()

    def event(kind, record, date):
        item = {**record, 'eventType': kind, 'eventSeq': len(events) + 1,
                'observedDate': date, 'recordedAt': recorded_at}
        events.append(item)

    for bar in bars:
        adapter.push(bar)
        next_state = {}
        for raw in adapter.structures():
            if not 0 <= raw['startIndex'] <= raw['endIndex'] <= bar['index']:
                raise ValueError('Adapter returned a future or invalid structure')
            # Engine-scoped anchor lineage: same origin/type/direction is revised;
            # a changed origin is a new identity, never an invented match.
            anchor = f"{engine_id}:{raw['type']}:{raw['startIndex']}:{raw['direction']}"
            if raw.get('identityScope'):anchor += ':' + raw['identityScope']
            identity = identities.get(anchor)
            if identity is None:
                identity = hashlib.sha256(anchor.encode()).hexdigest()[:24]
                identities[anchor] = identity
            if identity in next_state:
                raise ValueError('Ambiguous structure anchor')
            previous = latest.get(identity)
            changed = previous is None or previous['raw'] != raw or previous['state'] == 'RETRACTED'
            if changed:
                revision = previous['revision'] + 1 if previous else 1
                record = {**raw, 'id': identity, 'revision': revision,
                          'priorRevision': previous['revision'] if previous else None,
                          'firstObservedDate': previous['firstObservedDate'] if previous else bar['date'],
                          'engineConfirmedDate': bar['date'] if raw['engineConfirmed'] else None,
                          'eligibleAt': None, 'state': 'CURRENT', 'raw': raw,
                          'pivotStartDate': bars[raw['startIndex']]['date'],
                          'pivotEndDate': bars[raw['endIndex']]['date']}
                event('OBSERVED' if previous is None or previous['state'] == 'RETRACTED' else 'REVISED', record, bar['date'])
                latest[identity] = record
            else:
                record = previous
            next_state[identity] = record
        for identity, previous in current.items():
            if identity not in next_state:
                record = {**previous, 'revision': previous['revision'] + 1,
                          'priorRevision': previous['revision'], 'state': 'RETRACTED'}
                latest[identity] = record
                event('RETRACTED', record, bar['date'])
        current = next_state
    structures = [{**record, 'observedAsOfDate': bars[-1]['date']} for record in current.values()]
    return {'schemaVersion': 1, 'engineId': engine_id, 'engineVersion': adapter.version,
            'adapterVersion': ADAPTER_VERSION, 'profile': profile, 'profileHash': profile_hash,
            'dataset': catalog(), 'datasetId': DATASET_ID, 'datasetHash': DATASET_HASH,
            'priceBasis': PRICE_BASIS, 'observedBars': observed_bars, 'observedAsOfDate': bars[-1]['date'],
            'recordedAt': recorded_at, 'timeSemantics': 'TRADING_DATE_LABEL_ONLY', 'executable': False,
            'bars': bars, 'structures': structures, 'events': events,
            'counts': dict(Counter(s['type'] for s in structures)),
            'layers': adapter.layers}
