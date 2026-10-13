"""Script de geração: exporta core/domain/nexus/entities.py para JSON canônico.

Este arquivo pode ser importado pelo Nexus frontend em vez de ter constantes duplicadas.
Gera: nexus/src/generated/nexus-entities.json

Uso:
    python scripts/generate_nexus_entities.py

O arquivo gerado é versionado no git e deve ser regenerado quando entities.py mudar.
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.domain.nexus.entities import (
    AGENT_ROLES,
    AGENT_STATUSES,
    ALLOWED_ROLES,
    ALLOWED_TOOLS,
    AUTO_TOOLS,
    HANDOFF_TYPES,
    ROOMS,
    TOOL_REGISTRY,
)

OUTPUT_DIR = PROJECT_ROOT / "nexus" / "src" / "generated"
OUTPUT_FILE = OUTPUT_DIR / "nexus-entities.json"


def build_payload() -> dict:
    """Build the canonical JSON payload from Python entities."""
    # Transform ROOMS to array format (matching constants3d.js structure)
    rooms = []
    for room_id, data in ROOMS.items():
        # Extract XZ size [width, depth] from 3D size [w, h, d]
        size_3d = data["size"]  # [w, h, d]
        size_xz = [size_3d[0], size_3d[2]]  # XZ plane for Three.js floor
        rooms.append({
            "id": room_id,
            "label": data["label"],
            "position": data["position"],
            "size": size_xz,       # [width, depth] for Three.js
            "size3d": size_3d,     # full [w, h, d] for reference
            "colorKey": data["colorKey"],
        })

    # Transform AGENT_ROLES — note: constants3d.js uses label=name, role=label
    # We output both keys to avoid breaking changes in the frontend
    agents = {}
    for agent_id, data in AGENT_ROLES.items():
        agents[agent_id] = {
            "id": agent_id,
            "name": data["name"],       # "Maia" — entities.py canonical field
            "label": data["name"],      # alias for constants3d.js compatibility
            "agentLabel": data["label"],# "Orquestradora" — functional role label
            "role": data["label"],      # alias for constants3d.js compatibility
            "color": data["color"],
            "room": data["room"],       # entities.py canonical field
            "roomId": data["room"],     # alias for constants3d.js compatibility
        }

    return {
        "_meta": {
            "source": "core/domain/nexus/entities.py",
            "generator": "scripts/generate_nexus_entities.py",
            "warning": "DO NOT EDIT — regenerate with: python scripts/generate_nexus_entities.py",
        },
        "AGENT_ROLES": agents,
        "ALLOWED_ROLES": sorted(ALLOWED_ROLES),
        "ROOMS": rooms,
        "TOOL_REGISTRY": TOOL_REGISTRY,
        "ALLOWED_TOOLS": sorted(ALLOWED_TOOLS),
        "AUTO_TOOLS": sorted(AUTO_TOOLS),
        "AGENT_STATUSES": sorted(AGENT_STATUSES),
        "HANDOFF_TYPES": sorted(HANDOFF_TYPES),
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_payload()
    OUTPUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated: {OUTPUT_FILE}")
    print(f"  Agents:  {len(payload['AGENT_ROLES'])}")
    print(f"  Rooms:   {len(payload['ROOMS'])}")
    print(f"  Tools:   {len(payload['ALLOWED_TOOLS'])}")


if __name__ == "__main__":
    main()
