#!/usr/bin/env python3
"""Serve docs/ on http://localhost:8000 to test the web page before it is
published (WebUSB works on localhost). Sends "Cache-Control: no-store", so the
browser never runs a stale script.
"""
import functools
import http.server
from pathlib import Path


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()


docs = Path(__file__).resolve().parent / 'docs'
print('http://localhost:8000/  (Ctrl+C to stop)')
http.server.ThreadingHTTPServer(('127.0.0.1', 8000), functools.partial(Handler, directory=str(docs))).serve_forever()
