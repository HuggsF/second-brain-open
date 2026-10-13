"""Loopback BFF and non-overlapping observation daemon. Local pilot only."""
import argparse
import asyncio
import json
import mimetypes
import threading
import time
import uuid
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from fastmcp import Client
from backend.store import Store
from backend.workflow_api import MAX_BODY_BYTES, WorkflowApi
from mcp_servers.hub_observability_mcp import mcp

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ('production','hml')


async def collect(environment):
    async with Client(mcp) as client:
        result = await client.call_tool('observe_hub', {'environment':environment})
        if result.is_error:
            raise RuntimeError('SOURCE_UNAVAILABLE')
        return result.data


class Collector:
    def __init__(self, store, source=collect):
        self.store, self.source = store, source
        self.lock, self.stop = threading.Lock(), threading.Event()

    def cycle(self):
        if not self.lock.acquire(blocking=False):
            return False
        try:
            for environment in TARGETS:
                try:
                    payload = asyncio.run(self.source(environment))
                    if not isinstance(payload,dict) or payload.get('environment') != environment:
                        raise ValueError('Invalid contract')
                    self.store.record(environment,payload=payload)
                except Exception:
                    self.store.record(environment,error='SOURCE_UNAVAILABLE')
            return True
        finally:
            self.lock.release()

    def run(self):
        while not self.stop.is_set():
            self.cycle()
            self.stop.wait(60)


def handler_for(store, dashboard, port, workflow=None):
    origin = f'http://127.0.0.1:{port}'
    workflow = workflow or WorkflowApi(ROOT, port=port)
    if not workflow.port: workflow.port = port
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass  # Includes bootstrap secrets in URL: deliberately never access-log them.

        def send(self,status,body,kind='application/json',extra=None):
            content = json.dumps(body,ensure_ascii=False).encode() if kind=='application/json' else body
            self.send_response(status)
            self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(content)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
            for key,value in (extra or {}).items(): self.send_header(key,value)
            self.end_headers()
            self.wfile.write(content)

        def error(self,status,code):
            self.send(status,{'schema_version':1,'error':code,'request_id':str(uuid.uuid4())})

        def has_session(self):
            cookie = SimpleCookie()
            try: cookie.load(self.headers.get('Cookie',''))
            except Exception: return False
            token = cookie.get('brain_session')
            return bool(token) and store.authorize(token.value,'session')

        def do_GET(self):
            if self.headers.get('Host') != f'127.0.0.1:{port}' or self.headers.get('Sec-Fetch-Site') == 'cross-site' or self.headers.get('Origin',origin) != origin:
                return self.error(403,'ORIGIN_DENIED')
            url = urlsplit(self.path)
            path = unquote(url.path)
            if path == '/healthz':
                return self.send(200,{'status':'ok','service':'brain-local-bff','schema_version':1})
            if path.startswith('/connect/'):
                if not store.authorize(path.removeprefix('/connect/'),'bootstrap',consume=True):
                    return self.error(401,'LINK_EXPIRED')
                session = store.issue('session',8*3600)
                return self.send(302,b'','text/plain',{'Location':'/dashboard/#page=observability','Set-Cookie':f'brain_session={session}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'})
            if not self.has_session():
                if path.startswith(('/v1/','/api/')):
                    return self.error(401,'AUTH_REQUIRED')
                return self.send(401,b'<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Conectar Second Brain</title><h1>Sessao local necessaria</h1><p>Execute python -m backend.server --issue-link e abra o link de uso unico gerado em .runtime/connect.url.</p></html>','text/html; charset=utf-8')
            query = parse_qs(url.query)
            if path.startswith('/api/workflow/'):
                result = workflow.handle('GET',path,b'')
                return self.send(result[0],result[1],extra=result[2]) if result else self.error(404,'NOT_FOUND')
            if path.startswith('/v1/'):
                if query.get('space',['kiosk']) != ['kiosk']:
                    return self.error(403,'SPACE_DENIED')
                envelope = {'schema_version':1,'space_id':'kiosk','request_id':str(uuid.uuid4())}
                if path == '/v1/capabilities':
                    return self.send(200,{**envelope,'authentication':'local-session','observability':{'enabled':True,'interval_seconds':60,'stale_after_seconds':180,'targets':list(TARGETS)},'semantic_retrieval':False,'agent_execution':False,'workflow_audit':True})
                if path in ('/v1/observability','/v1/observability/history'):
                    env = query.get('environment',['production'])
                    if len(env)!=1 or env[0] not in TARGETS:
                        return self.error(400,'INVALID_ENVIRONMENT')
                    if path.endswith('/history'):
                        try: limit = int(query.get('limit',['30'])[0])
                        except ValueError: return self.error(400,'INVALID_LIMIT')
                        if not 1<=limit<=100: return self.error(400,'INVALID_LIMIT')
                        return self.send(200,{**envelope,'environment':env[0],'items':store.read(env[0],limit)})
                    return self.send(200,{**envelope,**store.latest(env[0])})
                return self.error(404,'NOT_FOUND')
            if not path.startswith('/dashboard/'):
                return self.error(404,'NOT_FOUND')
            relative = path.removeprefix('/dashboard/') or 'index.html'
            file = (dashboard / relative).resolve()
            if not file.is_relative_to(dashboard.resolve()) or file.suffix.lower() not in {'.html','.js','.css','.json','.svg','.png','.jpg','.webp','.md'} or not file.is_file():
                return self.error(404,'NOT_FOUND')
            return self.send(200,file.read_bytes(),mimetypes.guess_type(file)[0] or 'application/octet-stream')

        def do_POST(self):
            # Writes need an explicit same-origin Origin header, unlike reads (CSRF guard).
            if self.headers.get('Host') != f'127.0.0.1:{port}' or self.headers.get('Sec-Fetch-Site') == 'cross-site' or self.headers.get('Origin') != origin:
                return self.error(403,'ORIGIN_DENIED')
            if not self.has_session():
                return self.error(401,'AUTH_REQUIRED')
            path = unquote(urlsplit(self.path).path)
            if not path.startswith('/api/workflow/'):
                return self.error(405,'READ_ONLY_API')
            try: length = int(self.headers.get('Content-Length','0'))
            except ValueError: return self.error(400,'INVALID_LENGTH')
            if length > MAX_BODY_BYTES:
                return self.error(413,'BODY_TOO_LARGE')
            body = self.rfile.read(length) if length > 0 else b''
            if path == '/api/workflow/execute-step' and self.headers.get('Content-Type','').split(';')[0].strip() != 'application/json':
                return self.error(415,'JSON_REQUIRED')
            result = workflow.handle('POST',path,body)
            return self.send(result[0],result[1],extra=result[2]) if result else self.error(404,'NOT_FOUND')
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8848)
    parser.add_argument('--issue-link',action='store_true')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535: parser.error('Invalid port')
    store = Store(ROOT / '.runtime' / 'brain.db')
    link = f'http://127.0.0.1:{args.port}/connect/{store.issue("bootstrap",1800)}'
    (ROOT / '.runtime' / 'connect.url').write_text(link,encoding='utf-8')
    if args.issue_link:
        print('Single-use link saved in .runtime/connect.url (30 minutes).')
        return
    server = ThreadingHTTPServer(('127.0.0.1',args.port),handler_for(store,ROOT/'dashboard',args.port))
    server.daemon_threads = True
    collector = Collector(store)
    thread = threading.Thread(target=collector.run,daemon=True,name='hub-observation-daemon')
    thread.start()
    print(f'BFF listening on loopback port {args.port}; collector enabled.',flush=True)
    try: server.serve_forever()
    finally:
        collector.stop.set()
        server.server_close()


if __name__ == '__main__': main()
