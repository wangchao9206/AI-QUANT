"""Isolated protocol fixture. Price shapes are frozen; clocks are SYNTHETIC.

Never exposed on a host port or connected to production databases/providers.
"""
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

from chanlun_worker.data import load_dataset
from chanlun_worker.monitor import observe, merge_closed, InputConflict

lock=threading.Lock()
control={'prefix':221,'status':'READY','revision':False,'version':False,'gap':False}
# Candidate 275 becomes freshly observable after the initial prefix (index 220).
end=datetime.now(timezone.utc)-timedelta(seconds=330)
bars=[{**b,'index':i,'providerIndex':i,'timestamp':(end+timedelta(minutes=5*(i-275))).isoformat(),
       'date':(end+timedelta(minutes=5*(i-275))).date().isoformat()} for i,b in enumerate(load_dataset())]


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):self.reply({'status':'UP','fixture':'SYNTHETIC_CLOCKS_NOT_MARKET'})
    def do_POST(self):
        if self.headers.get('Transfer-Encoding','').lower()=='chunked':
            chunks=[]
            while True:
                size=int(self.rfile.readline().split(b';')[0].strip(),16)
                if size==0:self.rfile.readline();break
                chunks.append(self.rfile.read(size));self.rfile.read(2)
            raw=b''.join(chunks)
        else:
            raw=self.rfile.read(int(self.headers['Content-Length']))
        body=json.loads(raw)
        if self.path=='/fixture':
            with lock:control.update(body)
            return self.reply(control)
        with lock:settings=dict(control)
        source={'source':'ISOLATED_SYNTHETIC_CLOCK_FIXTURE','receiptAt':datetime.now(timezone.utc).isoformat(),'closeProof':'FIXTURE_ONLY'}
        if settings['status']!='READY':return self.reply({'status':settings['status'],'message':'controlled source fault','source':source})
        incoming=[dict(b) for b in bars[:settings['prefix']]]
        if settings['revision']:incoming[200]['close']+=.01
        if settings['gap']:incoming=incoming[body['previousBars'][-1]['providerIndex']+1:]
        try:
            merged=merge_closed(body['previousBars'],incoming,body['symbol'])
            result=observe(merged,body['symbol'],body['frequency'])
            if settings['version']:result['profileHash']='0'*64
            self.reply({'status':'READY','message':'synthetic protocol fixture','source':source,'analysis':result})
        except InputConflict as exc:self.reply({'status':exc.status,'message':str(exc),'source':source})
    def reply(self,value):
        data=json.dumps(value,ensure_ascii=False).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)


ThreadingHTTPServer(('0.0.0.0',8000),Handler).serve_forever()
