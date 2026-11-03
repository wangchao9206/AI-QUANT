"""Disposable HTTP peer for the isolated gateway DNS integration check."""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


class Peer(BaseHTTPRequestHandler):
    def do_GET(self):
        body=json.dumps({'marker':os.environ['PROBE_MARKER']}).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self,*args):pass


HTTPServer(('0.0.0.0',8084),Peer).serve_forever()
