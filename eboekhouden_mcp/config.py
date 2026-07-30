"""Configuratie voor de e-Boekhouden MCP-server, geladen uit .env of echte
omgevingsvariabelen.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv niet geïnstalleerd: dan alleen echte env-vars
    pass

API_BASE = "https://api.e-boekhouden.nl"


class ConfigError(RuntimeError):
    """Ontbrekende of onbruikbare configuratie."""


@dataclass(frozen=True)
class Config:
    api_token: str
    source: str
    base_url: str
    timeout: int
    default_template_id: int | None
    default_ledger_id: int | None
    default_vat_code: str
    allow_email: bool


def _int_or_none(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} moet een getal zijn, kreeg: {raw!r}") from exc


def load_config() -> Config:
    api_token = os.getenv("EBOEKHOUDEN_API_TOKEN", "").strip()
    if not api_token:
        raise ConfigError(
            "EBOEKHOUDEN_API_TOKEN ontbreekt. Maak een API-sleutel aan in "
            "e-Boekhouden (Beheer > Koppelingen > API) en zet die in .env. "
            "Kopieer .env.example naar .env als startpunt."
        )

    return Config(
        api_token=api_token,
        # 'source' wordt door e-Boekhouden gelogd als herkomst van de koppeling.
        source=os.getenv("EBOEKHOUDEN_SOURCE", "").strip() or "claude-mcp",
        base_url=os.getenv("EBOEKHOUDEN_API_BASE", "").strip() or API_BASE,
        timeout=int(os.getenv("EBOEKHOUDEN_TIMEOUT", "30")),
        default_template_id=_int_or_none("EBOEKHOUDEN_DEFAULT_TEMPLATE_ID"),
        default_ledger_id=_int_or_none("EBOEKHOUDEN_DEFAULT_LEDGER_ID"),
        default_vat_code=os.getenv("EBOEKHOUDEN_DEFAULT_VAT_CODE", "").strip()
        or "HOOG_VERK_21",
        # Facturen mailen staat standaard uit: eerst zelf controleren in e-Boekhouden.
        allow_email=os.getenv("EBOEKHOUDEN_ALLOW_EMAIL", "").strip().lower()
        in ("1", "true", "ja", "yes"),
    )
