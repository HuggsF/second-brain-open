"""Serve only the local dashboard on loopback; never expose the project or vault."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, unquote
import argparse

ROOT = Path(__file__).resolve().parent
class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)
    def send_head(self):
        path = unquote(urlparse(self.path).path)
        if path.startswith('/dashboard/'):
            path = path[len('/dashboard'):]
        if path == '/':
            path = '/index.html'
        target = (ROOT / path.lstrip('/')).resolve()
        if not target.is_relative_to(ROOT) or not target.is_file() or target.suffix.lower() not in {'.html','.css','.js','.json','.svg','.jpg','.png','.webp','.md'}:
            self.send_error(404)
            return None
        self.path = path
        return super().send_head()
    def guess_type(self, path):
        if str(path).endswith('.md'):
            return 'text/plain; charset=utf-8'
        return super().guess_type(path)
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
        super().end_headers()
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8847)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), DashboardHandler)
    print(f'Dashboard local: http://127.0.0.1:{args.port}/dashboard/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
