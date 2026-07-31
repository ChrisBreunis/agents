"""Configuratie voor de e-Boekhouden MCP-server, geladen uit .env of echte
omgevingsvariabelen.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    # Claude start de server vanuit een willekeurige werkmap, dus zoeken we de
    # .env eerst naast deze module en pas daarna op de gewone manier (werkmap
    # en hoger). Zonder dit wordt eboekhouden_mcp/.env simpelweg gemist.
    _EIGEN_ENV = Path(__file__).resolve().parent / ".env"
    if _EIGEN_ENV.exists():
        load_dotenv(_EIGEN_ENV)
    else:
        load_dotenv()
except ImportError:  # python-dotenv niet geïnstalleerd: dan alleen echte env-vars
    pass

API_BASE = "https://api.e-boekhouden.nl"

# Namen waaronder het token in de sleutelkluis van het besturingssysteem staat
# (Windows Credential Manager, macOS Keychain of Linux Secret Service).
KEYRING_DIENST = "eboekhouden-mcp"
KEYRING_GEBRUIKER = "api-token"


class ConfigError(RuntimeError):
    """Ontbrekende of onbruikbare configuratie."""


def token_uit_kluis() -> str:
    """Het API-token uit de sleutelkluis, of een lege tekst als er geen kluis
    beschikbaar is of er niets in staat."""
    try:
        import keyring
    except ImportError:
        return ""
    try:
        return (keyring.get_password(KEYRING_DIENST, KEYRING_GEBRUIKER) or "").strip()
    except Exception:
        # Geen werkende kluis op dit systeem (komt voor op kale servers).
        return ""


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
    # Een expliciet gezette omgevingsvariabele of .env wint; staat daar niets,
    # dan pakken we het token uit de sleutelkluis van het besturingssysteem.
    api_token = os.getenv("EBOEKHOUDEN_API_TOKEN", "").strip() or token_uit_kluis()
    if not api_token:
        raise ConfigError(
            "Geen API-token gevonden. Sla je sleutel op in de kluis van je "
            "besturingssysteem met 'python save_token.py' (aanbevolen), of zet "
            "EBOEKHOUDEN_API_TOKEN in .env — kopieer .env.example als startpunt."
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
