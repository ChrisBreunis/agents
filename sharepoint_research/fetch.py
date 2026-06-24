"""Hoofdscript: inloggen, bibliotheek inventariseren, bestanden downloaden,
tekst extraheren en een manifest (bronregister) wegschrijven.

Gebruik:  python fetch.py
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from auth import get_access_token
from config import load_config
from extractors import extract_text
from graph_client import GraphClient


def _safe_name(name: str) -> str:
    """Bestandsnaam veilig maken voor het lokale bestandssysteem."""
    return re.sub(r"[^\w.\- ]+", "_", name).strip()[:150] or "bestand"


def _person(field: dict | None) -> str:
    if not field:
        return "onbekend"
    user = field.get("user") or {}
    return user.get("displayName") or user.get("email") or "onbekend"


def main() -> None:
    config = load_config()
    token = get_access_token(config)
    client = GraphClient(token)

    print(f"→ Site opzoeken: {config.site_url}")
    site_id = client.resolve_site_id(config)
    drive_id, drive_name = client.resolve_drive_id(site_id, config.library_name)
    print(f"→ Bibliotheek: {drive_name}")

    docs_dir = config.output_dir / "documenten"
    text_dir = config.output_dir / "tekst"
    docs_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict] = []
    print("→ Bestanden inventariseren en uitlezen...")
    for n, item in enumerate(client.iter_files(drive_id), 1):
        parent_path = (item.get("parentReference") or {}).get("path", "")
        # parent_path ziet eruit als '/drives/<id>/root:/Map/Submap'
        rel = parent_path.split("root:", 1)[-1] if "root:" in parent_path else ""
        full_path = f"{rel}/{item['name']}".replace("//", "/")

        local_doc = docs_dir / f"{n:04d}_{_safe_name(item['name'])}"
        client.download(drive_id, item["id"], local_doc)
        text, note = extract_text(local_doc)

        text_file = text_dir / f"{n:04d}_{_safe_name(item['name'])}.txt"
        text_file.write_text(text, encoding="utf-8")

        record = {
            "nr": n,
            "naam": item["name"],
            "pad": full_path,
            "sharepoint_url": item.get("webUrl"),
            "aangemaakt": item.get("createdDateTime"),
            "gewijzigd": item.get("lastModifiedDateTime"),
            "aangemaakt_door": _person(item.get("createdBy")),
            "gewijzigd_door": _person(item.get("lastModifiedBy")),
            "grootte_bytes": item.get("size"),
            "item_id": item["id"],
            "quickxor_hash": ((item.get("file") or {}).get("hashes") or {}).get("quickXorHash"),
            "tekst_bestand": str(text_file),
            "tekens_geextraheerd": len(text),
            "notitie": note,
        }
        manifest.append(record)
        flag = "  ⚠ " + note if note else ""
        print(f"  [{n:04d}] {full_path} ({len(text)} tekens){flag}")

    manifest_obj = {
        "site_url": config.site_url,
        "bibliotheek": drive_name,
        "opgehaald_op": datetime.now(timezone.utc).isoformat(),
        "aantal_bestanden": len(manifest),
        "bestanden": manifest,
    }
    manifest_path = config.output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_obj, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n✓ Klaar. {len(manifest)} bestanden verwerkt.")
    print(f"  Bronregister : {manifest_path}")
    print(f"  Tekst per doc: {text_dir}/")
    print("  Volgende stap: python report.py")


if __name__ == "__main__":
    main()
