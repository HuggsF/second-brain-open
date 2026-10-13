"""
System Design Course Ingestion Engine for KIOSK Second Brain.
Scans and indexes 'Descomplicando System Design' course into the Second Brain Vault,
mapping lessons, durations, and architectural patterns to the 4 specialist agents:
(DEV, DEVOPS, QA, PRODUTO / ARQUITETURA).
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

COURSE_ROOT = Path(r"C:\Users\huggs\Downloads\Descomplicando System Design")
VAULT_DIR = Path(r"c:\Huggs\seccond-brain\vault")
SYSTEM_DESIGN_VAULT = VAULT_DIR / "architecture" / "system-design"
OUTPUT_DIR = Path(r"c:\Huggs\seccond-brain\extracted_system_design")


def probe_video(file_path: Path):
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(file_path)
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        raw_out = res.stdout.decode("utf-8", errors="replace")
        data = json.loads(raw_out)
        duration_sec = float(data.get("format", {}).get("duration", 0))
    except Exception:
        duration_sec = 0.0

    size_mb = file_path.stat().st_size / (1024 * 1024)
    return {
        "file_name": file_path.name,
        "duration_sec": duration_sec,
        "duration_min": round(duration_sec / 60, 2),
        "size_mb": round(size_mb, 2),
        "path": str(file_path)
    }


def ingest_system_design():
    if not COURSE_ROOT.exists():
        print(f"Error: Course root not found at {COURSE_ROOT}")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SYSTEM_DESIGN_VAULT.mkdir(parents=True, exist_ok=True)

    print(f"Scanning course modules in: {COURSE_ROOT}")
    module_dirs = sorted([d for d in COURSE_ROOT.iterdir() if d.is_dir()])

    catalog = []
    total_videos = 0
    total_duration_sec = 0
    total_size_mb = 0

    for m_dir in module_dirs:
        mp4_files = sorted([f for f in m_dir.glob("*.mp4")])
        if not mp4_files:
            continue

        print(f"Processing module: {m_dir.name} ({len(mp4_files)} videos)...")
        with ThreadPoolExecutor(max_workers=8) as executor:
            probed_lessons = list(executor.map(probe_video, mp4_files))

        mod_duration = sum(l["duration_sec"] for l in probed_lessons)
        mod_size = sum(l["size_mb"] for l in probed_lessons)

        mod_info = {
            "module_name": m_dir.name,
            "lesson_count": len(probed_lessons),
            "total_duration_min": round(mod_duration / 60, 2),
            "total_duration_hours": round(mod_duration / 3600, 2),
            "total_size_mb": round(mod_size, 2),
            "lessons": probed_lessons
        }
        catalog.append(mod_info)
        total_videos += len(probed_lessons)
        total_duration_sec += mod_duration
        total_size_mb += mod_size

    manifest = {
        "course_title": "Descomplicando System Design",
        "ingested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_path": str(COURSE_ROOT),
        "module_count": len(catalog),
        "lesson_count": total_videos,
        "total_duration_hours": round(total_duration_sec / 3600, 2),
        "total_size_gb": round(total_size_mb / 1024, 2),
        "modules": catalog
    }

    manifest_path = OUTPUT_DIR / "system_design_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"Manifest generated successfully: {manifest_path}")
    print(f"Total modules: {len(catalog)} | Total lessons: {total_videos} | Total hours: {manifest['total_duration_hours']}h | Size: {manifest['total_size_gb']} GB")
    return manifest


if __name__ == "__main__":
    ingest_system_design()
