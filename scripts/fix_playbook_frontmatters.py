"""
Fase 1 DDD — Fix frontmatters PB-008, PB-009, PB-010.

PB-008: Adiciona id, status, validates, environment, targets mantendo campos originais no body
PB-009: Idem
PB-010: Corrige environment 'prod/hml' → 'hml'
"""
from pathlib import Path

VAULT = Path(__file__).parent.parent / 'vault' / 'playbooks'


def replace_frontmatter(path: Path, new_fm: str) -> None:
    """Preserva o body (tudo após o segundo '---') e substitui apenas o frontmatter."""
    raw = path.read_bytes()
    text = raw.decode('utf-8', errors='replace')
    # Find second ---
    first = text.find('---')
    if first == -1:
        raise ValueError(f"No frontmatter in {path.name}")
    second = text.find('\n---', first + 3)
    if second == -1:
        raise ValueError(f"No closing --- in {path.name}")
    body = text[second + 4:]  # everything after \n---
    new_text = f"---\n{new_fm.strip()}\n---\n{body}"
    path.write_bytes(new_text.encode('utf-8'))
    print(f"  OK: {path.name}")


# ── PB-008 ────────────────────────────────────────────────────────────────────
PB008_FM = """\
id: PB-008
title: "Diagnóstico e Recuperação de Falhas OAuth no Hub Logístico"
status: active
validates: [RULE-001, RULE-002]
environment: production
targets: [Hub Logístico, Bling OAuth, J&T Adapter]
severity: P1
trigger: "Pedidos entrando em 'failed' com erros 404/FORBIDDEN na API do Bling"
tags: [playbook, hub-logistico, bling, oauth, incidente]
"""
replace_frontmatter(VAULT / 'PB-008-diagnostico-recuperacao-oauth-hub.md', PB008_FM)

# ── PB-009 ────────────────────────────────────────────────────────────────────
PB009_FM = """\
id: PB-009
title: "Plano de Observabilidade do Hub Logístico"
status: active
validates: [RULE-001, RULE-002]
environment: production
targets: [Hub Logístico, Srv-API, PM2, SQLite]
origin: "Post-mortem incidente OAuth 13/10/2026"
tags: [playbook, observabilidade, monitoramento, hub-logistico, alertas]
"""
replace_frontmatter(VAULT / 'PB-009-plano-observabilidade-hub-logistico.md', PB009_FM)

# ── PB-010 ────────────────────────────────────────────────────────────────────
p010 = VAULT / 'PB-010-pipeline-hub-fluxo-completo-regras-testes.md'
text010 = p010.read_bytes().decode('utf-8', errors='replace')
text010 = text010.replace('environment: prod/hml', 'environment: hml', 1)
p010.write_bytes(text010.encode('utf-8'))
print(f"  OK: {p010.name} (environment: prod/hml → hml)")

print("\nDone — validating with load_definitions()...")
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.evidence import load_definitions, lint

vault_dir = Path(__file__).parent.parent / 'vault'
defs = load_definitions(vault_dir)
problems = lint(defs)

print(f"\nPlaybooks loaded: {len(defs.playbooks)}")
print(f"Rules loaded: {len(defs.rules)}")
print(f"Lint errors: {len(problems)}")

if problems:
    for p in problems:
        print(f"  WARN: {p}")
else:
    print("  All clean!")

# Check our 3 fixes explicitly
for pb_id in ('PB-008', 'PB-009', 'PB-010'):
    pb = defs.playbooks.get(pb_id)
    if pb:
        print(f"  {pb_id}: id={pb.id}, env={pb.environment}, status={pb.status}, validates={pb.validates}")
    else:
        print(f"  {pb_id}: NOT FOUND — still broken")
