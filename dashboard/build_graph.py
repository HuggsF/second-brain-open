"""Build a reproducible, bounded local snapshot; never traverse outside the vault."""
from pathlib import Path
import argparse
import hashlib
import json
import math
from datetime import datetime, timezone

try:
    import yaml  # PyYAML
except ImportError:
    yaml = None

def _load_teams(vault):
    """Load vault/teams/teams.yaml if present and PyYAML is available."""
    teams_file = vault / 'teams' / 'teams.yaml'
    if not teams_file.is_file():
        return None
    raw = teams_file.read_text(encoding='utf-8')
    if yaml:
        return yaml.safe_load(raw)
    # Fallback: try to parse as JSON if no PyYAML (won't work for YAML, but keeps the build safe)
    return None

def _load_templates(vault):
    """Load vault/_templates/*.md metadata (name, first heading, path)."""
    templates_dir = vault / '_templates'
    if not templates_dir.is_dir():
        return []
    templates = []
    for tpl in sorted(templates_dir.glob('*.md')):
        content = tpl.read_text(encoding='utf-8-sig')
        title = next((ln.lstrip('#').strip() for ln in content.splitlines() if ln.startswith('# ')), tpl.stem)
        templates.append({
            'id': tpl.stem,
            'title': title,
            'path': '_templates/' + tpl.name,
            'lines': len(content.split('\n')),
        })
    return templates

def build(root, catalog, output):
    root, catalog, output = Path(root).resolve(), Path(catalog).resolve(), Path(output).resolve()
    vault = (root / 'vault').resolve()
    data = json.loads(catalog.read_text(encoding='utf-8-sig'))
    if data.get('version') != 1:
        raise ValueError('Unsupported catalog version')
    views = {v['id'] for v in data['views']}
    ids = [n['id'] for n in data['nodes']]
    if len(ids) != len(set(ids)) or len(views) != len(data['views']):
        raise ValueError('Duplicate node/view IDs')
    edge_ids = [e['id'] for e in data['edges']]
    if len(edge_ids) != len(set(edge_ids)):
        raise ValueError('Duplicate edge IDs')
    def safe_source(ref):
        source = (vault / ref).resolve()
        if not source.is_relative_to(vault) or source.suffix != '.md' or not source.is_file():
            raise ValueError('Invalid source: ' + ref)
        return source
    for node in data['nodes']:
        safe_source(node['document'])
        if not node.get('views') or not set(node['views']).issubset(views):
            raise ValueError('Invalid view for node: ' + node['id'])
        for pos in node['views'].values():
            if len(pos) != 2 or any(not isinstance(x, (float, int)) or not math.isfinite(x) for x in pos):
                raise ValueError('Invalid coordinates')
    by_id = {n['id']: n for n in data['nodes']}
    for edge in data['edges']:
        if edge['source'] not in by_id or edge['target'] not in by_id:
            raise ValueError('Orphan edge: ' + edge['id'])
        if any(edge['view'] not in by_id[edge[k]]['views'] for k in ('source', 'target')):
            raise ValueError('Edge outside view: ' + edge['id'])
        safe_source(edge['source_file'])
    documents = {}
    for source in sorted(vault.rglob('*.md')):
        resolved = safe_source(source.relative_to(vault).as_posix())
        raw = resolved.read_bytes()
        if len(raw) > 1_000_000:
            raise ValueError('Document exceeds 1MB: ' + source.name)
        content = raw.decode('utf-8-sig')
        ref = source.relative_to(vault).as_posix()
        title = next((ln.lstrip('#').strip() for ln in content.splitlines() if ln.startswith('# ')), source.stem)
        documents[ref] = {'text': content, 'title': title, 'category': ref.split('/')[0] if '/' in ref else 'general',
                          'sha256': hashlib.sha256(raw).hexdigest(), 'lines': len(content.split('\n')),
                          'modified_at': datetime.fromtimestamp(resolved.stat().st_mtime, timezone.utc).isoformat()}
    data['documents'] = documents
    # Teams and templates metadata
    teams_data = _load_teams(vault)
    if teams_data:
        data['teams'] = teams_data.get('teams', [])
        data['protocols'] = teams_data.get('protocols', {})
    else:
        data['teams'] = []
        data['protocols'] = {}
    data['templates'] = _load_templates(vault)
    data['built_from'] = 'vault + dashboard/graph-catalog.json'
    signature = json.dumps(data, ensure_ascii=False, sort_keys=True).encode('utf-8')
    data['snapshot_id'] = hashlib.sha256(signature).hexdigest()
    data['built_at'] = datetime.now(timezone.utc).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('window.KIOSK_GRAPH = ' + json.dumps(data, ensure_ascii=False).replace('<', '\\u003c') + ';\n', encoding='utf-8')
    teams_count = len(data.get('teams', []))
    tpl_count = len(data.get('templates', []))
    print(json.dumps({'nodes': len(ids), 'edges': len(edge_ids), 'sources': len(documents), 'teams': teams_count, 'templates': tpl_count, 'snapshot_id': data['snapshot_id']}, ensure_ascii=True))
    return data

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    default = Path(__file__).resolve().parent.parent
    parser.add_argument('--root', default=default)
    parser.add_argument('--catalog')
    parser.add_argument('--output')
    args = parser.parse_args()
    build(args.root, args.catalog or Path(args.root) / 'dashboard/graph-catalog.json', args.output or Path(args.root) / 'dashboard/graph-data.js')
