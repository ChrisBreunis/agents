"""Configuratie laden uit .env (of omgevingsvariabelen)."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv niet geïnstalleerd: dan alleen echte env-vars
    pass

GRAPH_SCOPES = ["Files.Read.All", "Sites.Read.All"]
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


@dataclass
class Config:
    tenant_id: str
    client_id: str
    site_url: str
    library_name: str
    output_dir: Path

    @property
    def authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}"

    @property
    def site_hostname(self) -> str:
        return urlparse(self.site_url).netloc

    @property
    def site_path(self) -> str:
        # bv. "/sites/Raadsonderzoek"
        return urlparse(self.site_url).path.rstrip("/")


def load_config() -> Config:
    tenant_id = os.getenv("SP_TENANT_ID", "").strip()
    client_id = os.getenv("SP_CLIENT_ID", "").strip()
    site_url = os.getenv("SP_SITE_URL", "").strip()
    library_name = os.getenv("SP_LIBRARY_NAME", "").strip()
    output_dir = Path(os.getenv("OUTPUT_DIR", "output").strip() or "output")

    missing = [
        name
        for name, val in [
            ("SP_TENANT_ID", tenant_id),
            ("SP_CLIENT_ID", client_id),
            ("SP_SITE_URL", site_url),
        ]
        if not val
    ]
    if missing:
        sys.exit(
            "Ontbrekende configuratie: "
            + ", ".join(missing)
            + "\nKopieer .env.example naar .env en vul de waarden in."
        )

    return Config(
        tenant_id=tenant_id,
        client_id=client_id,
        site_url=site_url,
        library_name=library_name,
        output_dir=output_dir,
    )
