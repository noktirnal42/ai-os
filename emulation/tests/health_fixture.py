"""Temporary host connectivity fixture. This does not serve a model or inference.
Run on the host while checking curl from the guest, then terminate with Ctrl-C.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/health':
            self.send_error(404)
            return
        payload = b'{"fixture":"emulation-network-test","inference":false}\n'
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

if __name__ == '__main__':
    print('Network fixture only, listening on 127.0.0.1:8080', flush=True)
    HTTPServer(('127.0.0.1', 8080), Handler).serve_forever()
