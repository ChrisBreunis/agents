"""Lokale inlezing: doorzoek een map met documenten, lees elk bestand uit en
schrijf een manifest (bronregister) + per document de geëxtraheerde tekst.

Geen SharePoint, geen authenticatie. Zet je bestanden in input_documenten/
(submappen mogen) en draai:  python local_ingest.py
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from extractors import extract_text
from paths import load_paths


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w.\- ]+", "_", name).strip()[:150] or "bestand"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def main() -> None:
    paths = load_paths()
    if not paths.input_dir.exists():
        raise SystemExit(f"Invoermap bestaat niet: {paths.input_dir}")

    files = sorted(
        p for p in paths.input_dir.rglob("*")
        if p.is_file() and p.name != ".gitkeep"
    )
    if not files:
        raise SystemExit(
            f"Geen bestanden gevonden in {paths.input_dir}. "
            "Zet je documenten daar neer en draai opnieuw."
        )

    paths.text_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict] = []
    print(f"→ {len(files)} bestanden gevonden in {paths.input_dir}")
    for n, path in enumerate(files, 1):
        stat = path.stat()
        text, note = extract_text(path)

        text_file = paths.text_dir / f"{n:04d}_{_safe_name(path.name)}.txt"
        text_file.write_text(text, encoding="utf-8")

        rel = path.relative_to(paths.input_dir)
        record = {
            "nr": n,
            "naam": path.name,
            "pad": str(rel),
            "bron_url": path.resolve().as_uri(),  # file:// link naar het origineel
            "aangemaakt": _iso(stat.st_ctime),
            "gewijzigd": _iso(stat.st_mtime),
            "aangemaakt_door": "onbekend (lokaal bestand)",
            "gewijzigd_door": "onbekend (lokaal bestand)",
            "grootte_bytes": stat.st_size,
            "sha256": _sha256(path),
            "tekst_bestand": str(text_file),
            "tekens_geextraheerd": len(text),
            "notitie": note,
        }
        manifest.append(record)
        flag = "  ⚠ " + note if note else ""
        print(f"  [{n:04d}] {rel} ({len(text)} tekens){flag}")

    manifest_obj = {
        "bron": "lokale map",
        "invoermap": str(paths.input_dir),
        "opgehaald_op": datetime.now(timezone.utc).isoformat(),
        "aantal_bestanden": len(manifest),
        "bestanden": manifest,
    }
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    paths.manifest_path.write_text(
        json.dumps(manifest_obj, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n✓ Klaar. {len(manifest)} bestanden verwerkt.")
    print(f"  Bronregister : {paths.manifest_path}")
    print(f"  Tekst per doc: {paths.text_dir}/")
    print("  Volgende stap: python report.py  (feiten)  en  python analyze.py  (duiding)")


if __name__ == "__main__":
    main()
