"""Loopback BFF and non-overlapping observation daemon. Local pilot only."""
import argparse
import asyncio
import json
import mimetypes
import queue as _queue
import re
import sys
import threading
import time
import uuid
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from fastmcp import Client
from backend.assessment import build_assessment
from backend.playbooks_api import PlaybooksApi
from backend.store import Store
from backend.workflow_api import MAX_BODY_BYTES, WorkflowApi
from core.events import subscribe, unsubscribe
from mcp_servers.hub_observability_mcp import mcp

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ('production','hml')
SSE_KEEPALIVE_SECONDS = 30
PLAYBOOK_GETS = ('/api/playbooks','/api/playbooks/','/api/playbooks/executions','/api/rules')
PLAYBOOK_ID_ROUTES = r'/api/playbooks/[A-Za-z0-9_.\-]+(/executions)?'
PLAYBOOK_RENDER_ROUTE = r'/api/playbooks/[A-Za-z0-9_.\-]+/render'


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


MAX_QUERY_CHARS = 500
MAX_RETRIEVAL_LIMIT = 10
DEFAULT_RETRIEVAL_LIMIT = 5
EXCERPT_CHARS = 400


def handler_for(store, dashboard, port, workflow=None, playbooks=None, retriever=None):
    origin = f'http://127.0.0.1:{port}'
    retriever_box = [retriever]
    retriever_lock = threading.Lock()
    workflow = workflow or WorkflowApi(ROOT, port=port)
    if not workflow.port: workflow.port = port
    playbooks = playbooks or PlaybooksApi(ROOT / 'vault')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass  # Includes bootstrap secrets in URL: deliberately never access-log them.

        def send(self,status,body,kind='application/json',extra=None,frame_self=False):
            content = json.dumps(body,ensure_ascii=False).encode() if kind=='application/json' else body
            self.send_response(status)
            self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(content)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors "+("'self'" if frame_self else "'none'"))
            for key,value in (extra or {}).items(): self.send_header(key,value)
            self.end_headers()
            self.wfile.write(content)

        def error(self,status,code):
            self.send(status,{'schema_version':1,'error':code,'request_id':str(uuid.uuid4())})

        def playbooks_call(self,path,method,body=b''):
            try: return playbooks.handle(path,method,body)
            except Exception as exc:
                print(f'playbooks api failed: {type(exc).__name__}',file=sys.stderr)
                return 500,{'schema_version':1,'error':'INTERNAL','request_id':str(uuid.uuid4())}

        def envelope(self,query):
            # Single-space pilot: any other space is refused. Returns None when denied.
            if query.get('space',['kiosk']) != ['kiosk']: return None
            return {'schema_version':1,'space_id':'kiosk','request_id':str(uuid.uuid4())}

        def get_retriever(self):
            with retriever_lock:
                if retriever_box[0] is None:
                    from core.retriever import BrainRetriever  # Lazy: the BFF must start without Qdrant.
                    retriever_box[0] = BrainRetriever()
                return retriever_box[0]

        def retrieval(self,body,envelope):
            try: data = json.loads(body.decode('utf-8'))
            except (ValueError, UnicodeDecodeError): return self.error(400,'INVALID_JSON')
            if not isinstance(data,dict): return self.error(400,'INVALID_JSON')
            question = data.get('query')
            if not isinstance(question,str) or not 1 <= len(question.strip()) <= MAX_QUERY_CHARS:
                return self.error(400,'INVALID_QUERY')
            limit = data.get('limit',DEFAULT_RETRIEVAL_LIMIT)
            if not isinstance(limit,int) or isinstance(limit,bool) or not 1 <= limit <= MAX_RETRIEVAL_LIMIT:
                return self.error(400,'INVALID_LIMIT')
            category = data.get('category')
            if category is not None and not isinstance(category,str):
                return self.error(400,'INVALID_JSON')
            question = question.strip()
            try: question.encode('utf-8')  # Lone surrogates are valid JSON but cannot be sent back.
            except UnicodeEncodeError: return self.error(400,'INVALID_QUERY')
            try:
                started = time.perf_counter()
                result = self.get_retriever().query(question,limit=limit,category=category,include_content=True)
                elapsed = int((time.perf_counter()-started)*1000)
                citations = [{**citation,'excerpt':str(source.get('content') or '')[:EXCERPT_CHARS]}
                             for citation,source in zip(result['citations'],result['sources'],strict=True)]
                payload = {**envelope,'mode':'vector','query':question,'index_version':result['index_version'],
                           'citations':citations,'gaps':result['gaps'],'timings_ms':{'retrieval':elapsed}}
                json.dumps(payload,ensure_ascii=False).encode()  # Fail here as a typed 503, never inside send().
            except Exception as exc:
                # The detail goes to the local log only; the response stays generic (INV-N07).
                print(f'retrieval failed: {type(exc).__name__}: {exc!r}',file=sys.stderr)
                return self.error(503,'RETRIEVAL_UNAVAILABLE')
            return self.send(200,payload)

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
            if path in PLAYBOOK_GETS or re.fullmatch(PLAYBOOK_ID_ROUTES,path):
                result = self.playbooks_call(path,'GET')
                return self.send(result[0],result[1]) if result else self.error(404,'NOT_FOUND')
            if path.startswith('/v1/'):
                envelope = self.envelope(query)
                if envelope is None:
                    return self.error(403,'SPACE_DENIED')
                if path == '/v1/capabilities':
                    return self.send(200,{**envelope,'authentication':'local-session','observability':{'enabled':True,'interval_seconds':60,'stale_after_seconds':180,'targets':list(TARGETS)},'semantic_retrieval':True,'agent_execution':False,'workflow_audit':True})
                if path in ('/v1/observability','/v1/observability/history','/v1/observability/assessment'):
                    env = query.get('environment',['production'])
                    if len(env)!=1 or env[0] not in TARGETS:
                        return self.error(400,'INVALID_ENVIRONMENT')
                    if path.endswith('/history'):
                        try: limit = int(query.get('limit',['30'])[0])
                        except ValueError: return self.error(400,'INVALID_LIMIT')
                        if not 1<=limit<=100: return self.error(400,'INVALID_LIMIT')
                        return self.send(200,{**envelope,'environment':env[0],'items':store.read(env[0],limit)})
                    if path.endswith('/assessment'):
                        latest = {target:store.latest(target) for target in TARGETS}
                        return self.send(200,{**envelope,**build_assessment(env[0],latest,playbooks.rules,time.time())})
                    return self.send(200,{**envelope,**store.latest(env[0])})
                # ── BUS-01: SSE Event Stream ──
                if path == '/v1/events':
                    self.close_connection = True
                    sub = subscribe()
                    try:
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/event-stream')
                        self.send_header('Cache-Control', 'no-cache')
                        self.send_header('Connection', 'keep-alive')
                        self.send_header('X-Accel-Buffering', 'no')
                        self.end_headers()
                        while True:
                            try:
                                event = sub.get(timeout=SSE_KEEPALIVE_SECONDS)
                                line = json.dumps(event, ensure_ascii=False)
                                self.wfile.write(f"id:{event.get('id','')}\ndata:{line}\n\n".encode())
                                self.wfile.flush()
                            except _queue.Empty:
                                self.wfile.write(b": keepalive\n\n")
                                self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        pass
                    finally:
                        unsubscribe(sub)
                    return
                return self.error(404,'NOT_FOUND')
            if not path.startswith('/dashboard/'):
                return self.error(404,'NOT_FOUND')
            relative = path.removeprefix('/dashboard/') or 'index.html'
            file = (dashboard / relative).resolve()
            if not file.is_relative_to(dashboard.resolve()) or file.suffix.lower() not in {'.html','.js','.css','.json','.svg','.png','.jpg','.webp','.md'} or not file.is_file():
                return self.error(404,'NOT_FOUND')
            # Only the embedded React JEV (dashboard/jev/) may be framed, and only by the dashboard itself.
            return self.send(200,file.read_bytes(),mimetypes.guess_type(file)[0] or 'application/octet-stream',frame_self=file.is_relative_to((dashboard/'jev').resolve()))

        def do_POST(self):
            # Read the (bounded) body before any refusal: closing a socket with unread data makes
            # Windows reset it, and the client sees a network error instead of the status.
            try: length = int(self.headers.get('Content-Length','0'))
            except ValueError: length = -1
            if length < 0 or length > MAX_BODY_BYTES:
                self.close_connection = True
                return self.error(400 if length < 0 else 413,'INVALID_LENGTH' if length < 0 else 'BODY_TOO_LARGE')
            body = self.rfile.read(length) if length > 0 else b''
            # Writes need an explicit same-origin Origin header, unlike reads (CSRF guard).
            if self.headers.get('Host') != f'127.0.0.1:{port}' or self.headers.get('Sec-Fetch-Site') == 'cross-site' or self.headers.get('Origin') != origin:
                return self.error(403,'ORIGIN_DENIED')
            if not self.has_session():
                return self.error(401,'AUTH_REQUIRED')
            url = urlsplit(self.path)
            path = unquote(url.path)
            if path == '/v1/retrievals':
                if self.headers.get('Content-Type','').split(';')[0].strip() != 'application/json':
                    return self.error(415,'JSON_REQUIRED')
                envelope = self.envelope(parse_qs(url.query))
                if envelope is None:
                    return self.error(403,'SPACE_DENIED')
                return self.retrieval(body,envelope)
            if path == '/api/playbooks/executions' or re.fullmatch(PLAYBOOK_RENDER_ROUTE,path):
                if self.headers.get('Content-Type','').split(';')[0].strip() != 'application/json':
                    return self.error(415,'JSON_REQUIRED')
                result = self.playbooks_call(path,'POST',body)
                return self.send(result[0],result[1]) if result else self.error(404,'NOT_FOUND')
            if not path.startswith('/api/workflow/'):
                return self.error(405,'READ_ONLY_API')
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
