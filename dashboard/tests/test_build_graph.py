import unittest
from pathlib import Path
import tempfile, json, importlib.util
spec=importlib.util.spec_from_file_location('brain_builder',Path(__file__).resolve().parents[1]/'build_graph.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent,prefix='builder-fixture-')
        self.root=Path(self.tmp.name)
        (self.root/'vault/systems').mkdir(parents=True)
        (self.root/'vault/systems/a.md').write_text('# Documento\nConteudo <script>alert(1)</script>\n',encoding='utf-8')
        (self.root/'vault/systems/extra.md').write_text('# Sem entidade\nrollback\n',encoding='utf-8')
        self.data={'version':1,'views':[{'id':'flow','label':'Fluxo'}],'nodes':[{'id':'a','label':'A','type':'Sistema','domain':'hub','evidence':'documentado','document':'systems/a.md','views':{'flow':[0,0]}}],'edges':[]}
    def tearDown(self):
        assert self.root.resolve().is_relative_to(Path(__file__).resolve().parent)
        self.tmp.cleanup()
    def run_build(self):
        catalog=self.root/'catalog.json'
        catalog.write_text(json.dumps(self.data),encoding='utf-8')
        return builder.build(self.root,catalog,self.root/'output.js')
    def test_all_sources_escaped_and_stable_snapshot(self):
        first=self.run_build();second=self.run_build()
        self.assertEqual(first['snapshot_id'],second['snapshot_id'])
        self.assertIn('systems/extra.md',first['documents'])
        self.assertNotIn('<script>',(self.root/'output.js').read_text(encoding='utf-8'))
        self.assertIn(r'\u003cscript',(self.root/'output.js').read_text(encoding='utf-8'))
    def test_path_traversal_rejected(self):
        (self.root/'outside.md').write_text('# Outside',encoding='utf-8')
        self.data['nodes'][0]['document']='../outside.md'
        with self.assertRaises(ValueError):self.run_build()
    def test_duplicate_ids_and_nonfinite_coordinates_rejected(self):
        self.data['nodes'].append(dict(self.data['nodes'][0]))
        with self.assertRaises(ValueError):self.run_build()
        self.data['nodes'].pop();self.data['nodes'][0]['views']['flow']=[float('inf'),0]
        with self.assertRaises(ValueError):self.run_build()
    def test_orphan_and_duplicate_edges_rejected(self):
        edge={'id':'e','source':'a','target':'unknown','view':'flow','source_file':'systems/a.md','relation':'r','evidence':'documentado'}
        self.data['edges']=[edge]
        with self.assertRaises(ValueError):self.run_build()
        edge['target']='a';self.data['edges']=[edge,dict(edge)]
        with self.assertRaises(ValueError):self.run_build()
    def test_title_skips_frontmatter_comments(self):
        (self.root/'vault/adrs').mkdir()
        (self.root/'vault/adrs/ADR-001-x.md').write_bytes(b'---\r\ntype: adr\r\n# scope: second-brain\r\n---\r\n# ADR-001: Real\r\n')
        (self.root/'vault/_templates').mkdir()
        (self.root/'vault/_templates/adr.md').write_bytes(b'---\r\ntype: adr\r\n# scope: second-brain\r\n---\r\n# ADR-{NNN}: Modelo\r\n')
        data=self.run_build()
        self.assertEqual(data['documents']['adrs/ADR-001-x.md']['title'],'ADR-001: Real')
        self.assertEqual(data['templates'][0]['title'],'ADR-{NNN}: Modelo')
if __name__=='__main__':unittest.main()
