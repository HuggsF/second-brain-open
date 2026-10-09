import asyncio
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer
from backend.store import Store
from backend.server import Collector, handler_for
from mcp_servers.hub_observability_mcp import command_for, normalize, EXPECTED


class WaveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'brain.db')

    def tearDown(self): self.tmp.cleanup()

    def test_bootstrap_consumed_once_and_expired(self):
        token=self.store.issue('bootstrap',60)
        self.assertTrue(self.store.authorize(token,'bootstrap',True))
        self.assertFalse(self.store.authorize(token,'bootstrap',True))
        self.assertFalse(self.store.authorize(self.store.issue('session',-1),'session'))

    def test_failed_attempt_preserves_previous_and_stale(self):
        self.store.record('production',{'ok':True})
        self.store.record('production',error='SOURCE_UNAVAILABLE')
        view=self.store.latest('production',max_age=-1)
        self.assertTrue(view['stale']);self.assertTrue(view['collection_failed'])
        self.assertTrue(view['observation']['report']['ok'])
        self.assertIsNone(self.store.latest('hml')['observation'])

    def test_fixed_command_rejects_injection(self):
        for value in ['production; reboot','../hub','staging']:
            with self.assertRaises(ValueError): command_for(value)
        self.assertIn('--worker-enabled 0',command_for('hml'))
        self.assertIn('--worker-enabled 1',command_for('production'))

    def test_output_whitelist(self):
        sample={'ok':True,'process':{'status':'online','TOKEN':'secret'},'database':{'ok':True,'orders':['private']},'failures':[],'warnings':[]}
        report=normalize({'environment':'production','expectedSha':EXPECTED,'snapshots':[sample,sample]},'production')
        self.assertNotIn('secret',json.dumps(report));self.assertNotIn('private',json.dumps(report))

    def test_collector_failure_and_exclusion(self):
        async def source(environment):
            if environment=='hml': raise RuntimeError('secret')
            return {'environment':environment,'ok':False}
        collector=Collector(self.store,source)
        collector.lock.acquire();self.assertFalse(collector.cycle());collector.lock.release()
        self.assertTrue(collector.cycle())
        self.assertFalse(self.store.latest('production')['observation']['report']['ok'])
        self.assertEqual(self.store.latest('hml')['last_attempt']['error'],'SOURCE_UNAVAILABLE')

    def test_http_auth_scope_origin_and_traversal(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(self.store,Path(self.tmp.name),0))
        port=server.server_port
        server.RequestHandlerClass=handler_for(self.store,Path(self.tmp.name),port)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        token=self.store.issue('session',60)
        cookie='brain_session='+token
        def request(path,headers=None):
            return urlopen(Request(f'http://127.0.0.1:{port}'+path,headers=headers or {}),timeout=2)
        try:
            for path,headers,status in [('/v1/capabilities',{},401),('/v1/observability?space=other',{'Cookie':cookie},403),('/v1/observability?environment=other',{'Cookie':cookie},400),('/dashboard/%2e%2e/brain.db',{'Cookie':cookie},404),('/v1/capabilities',{'Cookie':cookie,'Origin':'https://evil.example'},403)]:
                with self.assertRaises(HTTPError) as caught:request(path,headers)
                self.assertEqual(caught.exception.code,status);caught.exception.close()
            with request('/v1/capabilities',{'Cookie':cookie}) as response:
                data=json.load(response)
                self.assertFalse(data['agent_execution']);self.assertFalse(data['semantic_retrieval'])
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
