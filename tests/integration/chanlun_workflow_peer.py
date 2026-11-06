"""Isolated HTTP adapter using the real pinned FU archive and workflow engine.

No TqSdk session, user accounts, live market calls, or production volumes.
"""
from dataclasses import asdict
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from types import SimpleNamespace
from urllib.parse import urlsplit, parse_qs

from fastapi import HTTPException
from backtesting.chan_signal import ChanTape, profile
from backtesting.native_chanlun_lab import execution_dataset
from backtesting.independent_research import causal_prices
from algorithm_service.paper_strategy import StrategyRequest, evaluate
from algorithm_service.workflows import DebugRequest, check, debug

DATA = execution_dataset()
SIGNALS = causal_prices(DATA)
PROVIDER = SimpleNamespace(cached_replay=lambda symbol: SimpleNamespace(
    bars=DATA.bars, signal_bars=SIGNALS, source=DATA.source))
TAPE = ChanTape(SIGNALS)
INDEX = next(i for i, row in enumerate(TAPE.rows) if i >= 100 and i < len(DATA.bars)-15 and row['candidates'])
FAULT={'noAtr':False,'zeroVolume':False}


def bar(value):
    return {'timestamp': value.timestamp.isoformat(), 'contract': value.contract_symbol,
            'open': value.open, 'high': value.high, 'low': value.low, 'close': value.close,
            'volume': value.volume, 'openInterest': value.open_interest}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def reply(self, code, value):
        content=json.dumps(value, ensure_ascii=False, default=lambda v:v.isoformat() if isinstance(v,(date,datetime)) else str(v)).encode()
        self.send_response(code);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(content)

    def do_GET(self):
        path=urlsplit(self.path)
        if path.path == '/fixture':
            return self.reply(200, {'symbol':'FU0','startDate':DATA.bars[INDEX].timestamp.date().isoformat(),
                'endDate':DATA.bars[INDEX+10].timestamp.date().isoformat(),
                'asOf':(DATA.bars[INDEX].timestamp+timedelta(hours=23)).isoformat(), 'candidateIndex':INDEX})
        if path.path == '/internal/v1/workflows/chan-profile':return self.reply(200,profile())
        if path.path.startswith('/internal/v1/simulation/history/'):
            query=parse_qs(path.query)
            start=query.get('start_date',['0000-00-00'])[0];end=query.get('end_date',['9999-99-99'])[0]
            selected=[b for b in DATA.bars if start<=b.timestamp.date().isoformat()<=end]
            selected_rows=[bar(b) for b in selected]
            if FAULT['zeroVolume'] and len(selected_rows)>1:selected_rows[1]['volume']=0
            return self.reply(200, {'symbol':'FU0','providerSymbol':DATA.provider_symbol,'source':DATA.source,
                'generatedAt':DATA.generated_at.isoformat(),'bars':selected_rows,
                'signalBars':[bar(b) for b in SIGNALS if b.timestamp.date().isoformat()<=end],
                'contextBars':[] if FAULT['noAtr'] else [bar(b) for b in DATA.bars if b.timestamp.date().isoformat()<=end],
                'rollEvents':[{'executionDate':r.execution_date.isoformat(),'fromContract':r.from_contract,
                    'toContract':r.to_contract,'oldOpen':r.old_open,'newOpen':r.new_open} for r in DATA.roll_events if start<=r.execution_date.isoformat()<=end],
                'contractSpecs':{symbol:{'contract':symbol,'volumeMultiple':spec.volume_multiple,'priceTick':spec.price_tick,
                    'marginPerLot':spec.margin_per_lot,'commissionPerLot':spec.commission_per_lot} for symbol,spec in DATA.contract_specs.items()}})
        return self.reply(404, {'message':'Unknown isolated endpoint'})

    def do_POST(self):
        try:
            if self.headers.get('Transfer-Encoding','').lower()=='chunked':
                chunks=[]
                while True:
                    length=int(self.rfile.readline().strip().split(b';',1)[0],16)
                    if not length:
                        self.rfile.readline();break
                    chunks.append(self.rfile.read(length));self.rfile.read(2)
                body=b''.join(chunks)
            else:body=self.rfile.read(int(self.headers.get('Content-Length','0')))
            value=json.loads(body)
            if self.path == '/fixture-control':
                FAULT.update({key:bool(value.get(key,False)) for key in FAULT});return self.reply(200,{'isolatedFaultInjection':dict(FAULT)})
            if self.path == '/internal/v1/workflows/validate':return self.reply(200,check(value['definition']))
            if self.path == '/internal/v1/workflows/debug':
                provider=SimpleNamespace(cached_replay=lambda symbol:SimpleNamespace(bars=[],signal_bars=SIGNALS,source=DATA.source)) if FAULT['noAtr'] else PROVIDER
                return self.reply(200,debug(DebugRequest(**value),provider,'FU0'))
            if self.path == '/internal/v1/simulation/strategy/evaluate':return self.reply(200,evaluate(StrategyRequest(**value)))
            self.reply(404,{'message':'Unknown isolated endpoint'})
        except HTTPException as error:self.reply(error.status_code,{'message':str(error.detail)})
        except Exception as error:self.reply(422,{'message':str(error)})


ThreadingHTTPServer(('0.0.0.0',8011),Handler).serve_forever()
