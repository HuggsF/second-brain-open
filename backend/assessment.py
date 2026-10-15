"""Observation assessment for the BFF: per-aspect health plus rule/health contradictions.

Pure function of (latest by environment, rules, now); the HTTP handler only fetches the inputs.
"""
import sys
from dataclasses import asdict

from core.domain.observation.projection import detect_contradictions, project

TARGETS = ('production', 'hml')


def build_assessment(environment, latest_by_env, rules, now_seconds):
    """Assessment of `environment`, with contradictions against the green rule lights.

    Both environments are projected so detect_contradictions sees them; only the contradictions of the
    requested environment are returned. `rules` is a list of list_rules rows or a callable returning
    one; if it raises (evidence DB or definitions down) the assessment still answers, without
    contradictions and with rules_available=False: observation health never depends on the evidence DB.
    """
    snapshots = {env: project(env, latest_by_env.get(env), now_seconds) for env in TARGETS}
    rules_available = True
    try:
        rows = rules() if callable(rules) else rules
        found = detect_contradictions(rows, snapshots)
    except Exception as exc:  # noqa: BLE001 - observation must answer without the evidence side
        print(f'assessment: rules unavailable ({type(exc).__name__})', file=sys.stderr)
        rules_available, found = False, []
    snapshot = snapshots[environment]
    result = {
        'environment': environment,
        'status': snapshot.status,
        'reason': snapshot.reason,
        'stale': snapshot.stale,
        'nodes': [{'id': n.id, 'status': n.status, 'reason': n.reason} for n in snapshot.nodes],
        'contradictions': [asdict(c) for c in found if c.environment == environment],
        'rules_available': rules_available,
    }
    return result
