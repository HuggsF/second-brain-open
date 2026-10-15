"""Package the same local product UI and snapshot into one offline HTML file."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / 'dashboard'
MODULES = ('schema.js', 'core.js', 'markdown.js', 'knowledge-model.js',
           'knowledge-motion.js', 'knowledge-view.js')


def _inline_script(source: str) -> str:
    return re.sub(r'</script', lambda _: r'<\/script', source, flags=re.IGNORECASE)


def build_html(dashboard: Path = DASHBOARD) -> str:
    raw = (dashboard / 'graph-data.js').read_text(encoding='utf-8-sig')
    prefix = 'window.KIOSK_GRAPH = '
    if not raw.startswith(prefix):
        raise ValueError('Expected the generated KIOSK_GRAPH snapshot.')
    snapshot = json.loads(raw[len(prefix):].strip().removesuffix(';'))
    payload = json.dumps(snapshot, ensure_ascii=False, separators=(',', ':'))
    payload = payload.replace('<', r'\u003c').replace('\u2028', r'\u2028').replace('\u2029', r'\u2029')
    css = (dashboard / 'knowledge.css').read_text(encoding='utf-8-sig')
    if re.search(r'</style', css, re.IGNORECASE):
        raise ValueError('Unexpected closing style tag in stylesheet.')
    scripts = '\n'.join(
        '<script data-module="' + name + '">\n' + _inline_script(
            (dashboard / name).read_text(encoding='utf-8-sig')) + '\n</script>'
        for name in MODULES
    )
    return '''<!doctype html>
<html lang="pt-BR" data-theme="dark">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'">
<meta name="description" content="Um explorador local de conhecimento: encontre uma informação, entenda suas conexões e leia a fonte.">
<title>Second Brain · Conhecimento com contexto</title>
<style>''' + css + '''</style></head>
<body class="knowledge-standalone"><div id="knowledge-product"><p>Preparando seu conhecimento…</p></div>
<noscript>Este explorador precisa de JavaScript para pesquisar e navegar os dados locais.</noscript>
<script data-module="snapshot">window.KIOSK_GRAPH = ''' + payload + ''';</script>
''' + scripts + '''
<script data-module="bootstrap">
(function(){
const host=document.getElementById('knowledge-product');host.replaceChildren();
if(!window.BrainSchema.validateSnapshot(window.KIOSK_GRAPH).ok){host.textContent='O snapshot local está inválido. Gere o showcase novamente.';return;}
const route=new URLSearchParams(location.hash.slice(1));
window.knowledgeProduct=window.BrainKnowledgeView.mount(host,{graph:window.KIOSK_GRAPH,initialQuery:route.get('q')||'',initialNode:route.get('node')||null});
})();
</script></body></html>'''


def write_showcase(target: Path, html: str, *, backup: bool = False) -> Path:
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if backup and target.exists():
        preserved = target.with_name(target.stem + '.original-2026-10-15' + target.suffix)
        if not preserved.exists():
            shutil.copy2(target, preserved)
    target.write_text(html, encoding='utf-8', newline='\n')
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DASHBOARD / 'knowledge-showcase.html')
    parser.add_argument('--export', type=Path, help='Also update a standalone showcase; preserve its original once.')
    args = parser.parse_args()
    html = build_html()
    print(write_showcase(args.output, html))
    if args.export:
        print(write_showcase(args.export, html, backup=True))


if __name__ == '__main__':
    main()
