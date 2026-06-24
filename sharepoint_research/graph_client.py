"""Dunne Microsoft Graph-client: site & bibliotheek vinden, bestanden
inventariseren en downloaden. Bevat throttling/retry-afhandeling.
"""
from __future__ import annotations

import time
from typing import Iterator
from urllib.parse import quote

import requests

from config import GRAPH_BASE, Config

# Velden die we per bestand willen meenemen voor de bronvermelding.
ITEM_SELECT = (
    "id,name,size,webUrl,createdDateTime,lastModifiedDateTime,"
    "createdBy,lastModifiedBy,file,folder,parentReference"
)


class GraphClient:
    def __init__(self, access_token: str):
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {access_token}"})

    # ── lage-niveau request met retry op 429/5xx ─────────────────────────
    def _get(self, url: str, *, stream: bool = False, max_retries: int = 5):
        for attempt in range(max_retries):
            resp = self.session.get(url, stream=stream)
            if resp.status_code in (429, 503, 504):
                wait = int(resp.headers.get("Retry-After", 2 ** attempt))
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp

    # ── site & drive (documentbibliotheek) opzoeken ──────────────────────
    def resolve_site_id(self, config: Config) -> str:
        path = quote(config.site_path)
        url = f"{GRAPH_BASE}/sites/{config.site_hostname}:{path}"
        return self._get(url).json()["id"]

    def resolve_drive_id(self, site_id: str, library_name: str) -> tuple[str, str]:
        """Geef (drive_id, drive_name) terug voor de gekozen bibliotheek."""
        url = f"{GRAPH_BASE}/sites/{site_id}/drives"
        drives = self._get(url).json().get("value", [])
        if not drives:
            raise RuntimeError("Geen documentbibliotheken op deze site gevonden.")
        if library_name:
            for d in drives:
                if d.get("name", "").lower() == library_name.lower():
                    return d["id"], d["name"]
            names = ", ".join(d.get("name", "?") for d in drives)
            raise RuntimeError(
                f"Bibliotheek '{library_name}' niet gevonden. "
                f"Beschikbaar: {names}"
            )
        # Geen naam opgegeven: pak de standaard-documentbibliotheek.
        return drives[0]["id"], drives[0]["name"]

    # ── recursief alle bestanden in de bibliotheek inventariseren ────────
    def iter_files(self, drive_id: str, item_id: str = "root") -> Iterator[dict]:
        url = (
            f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/children"
            f"?$select={ITEM_SELECT}&$top=200"
        )
        while url:
            data = self._get(url).json()
            for item in data.get("value", []):
                if item.get("folder"):
                    yield from self.iter_files(drive_id, item["id"])
                elif item.get("file"):
                    yield item
            url = data.get("@odata.nextLink")

    # ── bestand downloaden naar schijf ───────────────────────────────────
    def download(self, drive_id: str, item_id: str, dest) -> None:
        url = f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/content"
        resp = self._get(url, stream=True)
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                if chunk:
                    fh.write(chunk)
