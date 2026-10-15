"""Verify standalone packaging, canonical data and preservation of supplied work."""
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('showcase_builder', ROOT / 'scripts/build_knowledge_showcase.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class ShowcaseTests(unittest.TestCase):
    def test_embeds_same_snapshot_and_modules_without_network_dependencies(self):
        html = builder.build_html()
        payload = re.search(r'<script data-module="snapshot">window.KIOSK_GRAPH = (.*?);</script>', html, re.S).group(1)
        exported = json.loads(payload)
        original = json.loads((ROOT / 'dashboard/graph-data.js').read_text(encoding='utf-8')[len('window.KIOSK_GRAPH = '):].strip().removesuffix(';'))
        self.assertEqual(exported, original)
        self.assertEqual(len(exported['nodes']), 84)
        self.assertNotRegex(html, r'<script[^>]+src=|<link[^>]+(?:stylesheet|preload)')
        self.assertIn("connect-src 'none'", html)
        self.assertNotIn('data-module="graph-events.js"', html)
        for name in builder.MODULES:
            self.assertIn(f'data-module="{name}"', html)

    def test_script_terminators_in_source_text_cannot_escape_the_inline_bundle(self):
        hostile = 'const text="</ScRiPt><img src=x onerror=alert(1)>";'
        result = builder._inline_script(hostile)
        self.assertNotRegex(result, r'(?i)</script')
        self.assertIn(r'<\/script>', result)

    def test_export_preserves_the_first_supplied_showcase(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'knowledge.html'
            target.write_text('original reference', encoding='utf-8')
            builder.write_showcase(target, 'first product', backup=True)
            builder.write_showcase(target, 'second product', backup=True)
            backup = target.with_name('knowledge.original-2026-10-15.html')
            self.assertEqual(backup.read_text(encoding='utf-8'), 'original reference')
            self.assertEqual(target.read_text(encoding='utf-8'), 'second product')


if __name__ == '__main__':
    unittest.main()
