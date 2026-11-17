"""Read-only actual FG701 history collection. Never submits orders."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
import time
from datetime import date, datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RUNTIME = ROOT / '.test-tmp/tqsdk-runtime'
if RUNTIME.exists():
    sys.path.insert(0, str(RUNTIME))


def write_json(path, value):
    temp = path.with_suffix('.pending')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temp.replace(path)


def credentials():
    from dotenv import dotenv_values
    values = dotenv_values(ROOT / 'infrastructure/.env')
    user = os.getenv('TQSDK_USERNAME') or values.get('TQSDK_USERNAME')
    password = os.getenv('TQSDK_PASSWORD') or values.get('TQSDK_PASSWORD')
    if not user or not password:
        raise RuntimeError('CREDENTIALS_MISSING')
    return user, password


def records(frame):
    result = []
    for row in frame.to_dict('records'):
        if not math.isfinite(float(row.get('datetime', 0))) or row.get('datetime', 0) <= 0:
            continue
        if row.get('id', 0) < 0:
            continue
        record = {}
        for key, value in row.items():
            if hasattr(value, 'item'):
                value = value.item()
            record[key] = None if isinstance(value, float) and not math.isfinite(value) else value
        result.append(record)
    return result


def collect(out, timeout):
    from tqsdk import TqApi, TqAuth, TqSim
    import tqsdk
    user, password = credentials()
    api = None
    try:
        api = TqApi(TqSim(), auth=TqAuth(user, password), web_gui=False, debug=False, disable_print=True)
        quote = api.get_quote('CZCE.FG701')
        minute = api.get_kline_serial('CZCE.FG701', 60, data_length=10000)
        daily = api.get_kline_serial('CZCE.FG701', 86400, data_length=100)
        deadline = time.time() + timeout
        while not (api.is_serial_ready(minute) and api.is_serial_ready(daily)):
            if time.time() >= deadline:
                raise TimeoutError('SERIAL_TIMEOUT')
            api.wait_update(deadline=min(deadline, time.time() + 2))
        cld = api.get_trading_calendar(date(2026, 10, 1), date(2026, 11, 20))
        calendar = [{'date': row['date'].date().isoformat(), 'trading': bool(row['trading'])}
                    for row in cld.to_dict('records')]
        keys = ['instrument_id', 'exchange_id', 'instrument_name', 'price_tick', 'volume_multiple',
                'commission', 'margin', 'trading_time', 'expire_datetime']
        spec = {}
        for key in keys:
            v = getattr(quote, key, None)
            if key == 'trading_time':
                v = {s: [list(pair) for pair in getattr(v, s, [])] for s in ('day', 'night')}
            if isinstance(v, float) and not math.isfinite(v):
                v = None
            spec[key] = v
        payload = {'symbol': 'CZCE.FG701', 'source': 'Authenticated TqSdk actual delivery-contract serial',
                   'sdkVersion': tqsdk.__version__, 'capturedAt': datetime.now(timezone.utc).isoformat(),
                   'requestedWindowTradingDates': ['2026-10-17', '2026-11-16'],
                   'spec': spec, 'calendar': calendar, 'minute': records(minute.copy()),
                   'daily': records(daily.copy()), 'lastMinuteProvisional': True}
        path = out / 'raw.json'
        write_json(path, payload)
        return {'status': 'COLLECTED', 'symbol': 'CZCE.FG701', 'minuteBars': len(payload['minute']),
                'dailyBars': len(payload['daily']), 'minuteFirstNs': payload['minute'][0]['datetime'],
                'minuteLastNs': payload['minute'][-1]['datetime'],
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'sdkVersion': tqsdk.__version__}
    finally:
        if api is not None:
            api.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'data/history/fg701-intraday-2026-11-17')
    parser.add_argument('--timeout', type=int, default=90)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if (args.out / 'raw.json').exists():
        print(json.dumps({'status': 'EXISTING_PRESERVED', 'path': str(args.out)}))
        return
    # SDK output may contain account identifiers: only emit an allowlisted summary.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        try:
            result = collect(args.out, args.timeout)
        except Exception as exc:
            msg = str(exc).lower()
            category = 'PROVIDER_ERROR'
            if 'password' in msg or '密码' in msg or 'auth' in msg or '登录' in msg:
                category = 'AUTHENTICATION_FAILED'
            elif 'permission' in msg or '权限' in msg or '专业版' in msg:
                category = 'ACCESS_OR_ENTITLEMENT'
            elif isinstance(exc, (TimeoutError, ConnectionError)):
                category = 'CONNECTION_OR_TIMEOUT'
            result = {'status': 'UNAVAILABLE', 'errorType': type(exc).__name__, 'category': category}
    write_json(args.out / 'collection.json', result)
    print(json.dumps(result, ensure_ascii=True), flush=True)
    if result['status'] != 'COLLECTED':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
