"""Read the four domestic delivery-contract K-line tapes for the MA research."""

import argparse
import contextlib
from datetime import date, datetime, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
from time import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.collect_fg701_minutes import credentials, records


SYMBOLS = ('FG701', 'SA701', 'AP701', 'CJ701')


def collect(path):
    from tqsdk import TqApi, TqAuth, TqSim

    staged = {}
    with TqApi(TqSim(), auth=TqAuth(*credentials()), web_gui=False, debug=False, disable_print=True) as api:
        frames = {}
        for symbol in SYMBOLS:
            underlying = f'CZCE.{symbol}'
            quote = api.get_quote(underlying)
            frames[symbol] = (quote, api.get_kline_serial(underlying, 900, data_length=1800),
                              api.get_kline_serial(underlying, 86400, data_length=340))
        deadline = time() + 45
        while not all(api.is_serial_ready(frame) for _, *pair in frames.values() for frame in pair):
            if time() > deadline:
                raise TimeoutError('Historical serial timeout')
            api.wait_update(deadline=min(deadline, time() + 2))
        calendar = api.get_trading_calendar(date(2026, 5, 1), date(2026, 11, 19))
        trade_days = [row['date'].date().isoformat() for row in calendar.to_dict('records') if row['trading']]
        for symbol, (quote, minute, daily) in frames.items():
            staged[symbol] = {'contract': symbol, 'providerSymbol': f'CZCE.{symbol}', 'minutes': records(minute.copy()),
                              'daily': records(daily.copy()), 'tick': float(quote.price_tick),
                              'multiple': int(quote.volume_multiple), 'sessions': {
                                  key: [list(pair) for pair in getattr(quote.trading_time, key)]
                                  for key in ('day', 'night')}, 'expiry': float(quote.expire_datetime)}
    data = {'source': 'TqSdk actual delivery-contract serial', 'nativeMinutes': 15,
            'capturedAt': datetime.now(timezone.utc).isoformat(), 'lastBarsMayBeProvisional': True,
            'tradingDates': trade_days, 'contracts': staged}
    payload = json.dumps(data, separators=(',', ':'), allow_nan=False).encode()
    with path.open('xb') as output:
        output.write(payload)
    return {'status': 'COLLECTED', 'sha256': sha256(payload).hexdigest(),
            'counts': {key: [len(v['minutes']), len(v['daily'])] for key, v in staged.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    if options.output.exists():
        parser.error('Choose a fresh output path')
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        try:
            result = collect(options.output)
        except Exception as error:
            result = {'status': 'UNAVAILABLE', 'errorType': type(error).__name__}
    print(json.dumps(result), flush=True)
    if result['status'] != 'COLLECTED':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
