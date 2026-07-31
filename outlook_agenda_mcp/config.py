"""Configuratie voor de Outlook-agenda MCP-server, geladen uit .env of echte
omgevingsvariabelen.

Het client-id en tenant-id zijn geen geheimen (ze staan in elke inlog-URL),
maar het token dat je na het inloggen krijgt wél. Dat bewaren we in de kluis
van je besturingssysteem; zie auth.py.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    # Claude start de server vanuit een willekeurige werkmap, dus zoeken we de
    # .env eerst naast deze module en pas daarna op de gewone manier.
    _EIGEN_ENV = Path(__file__).resolve().parent / ".env"
    if _EIGEN_ENV.exists():
        load_dotenv(_EIGEN_ENV)
    else:
        load_dotenv()
except ImportError:  # python-dotenv niet geïnstalleerd: dan alleen echte env-vars
    pass

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
AUTHORITY_BASE = "https://login.microsoftonline.com"

# De rechten die we vragen. Calendars.ReadWrite is het minimum om afspraken te
# kunnen aanmaken; Calendars.ReadWrite.Shared komt er alleen bij als je ook
# agenda's van anderen wilt bewerken waar je toegang op hebt gekregen.
SCOPES = ["User.Read", "Calendars.ReadWrite"]
SCOPES_GEDEELD = ["User.Read", "Calendars.ReadWrite", "Calendars.ReadWrite.Shared"]

# Namen waaronder de tokencache in de sleutelkluis van het besturingssysteem
# staat (Windows Credential Manager, macOS Keychain of Linux Secret Service).
KEYRING_DIENST = "outlook-agenda-mcp"
KEYRING_GEBRUIKER = "token-cache"


class ConfigError(RuntimeError):
    """Ontbrekende of onbruikbare configuratie."""


@dataclass(frozen=True)
class Config:
    client_id: str
    tenant_id: str
    timezone: str
    timeout: int
    graph_base: str
    gedeelde_agendas: bool

    @property
    def authority(self) -> str:
        return f"{AUTHORITY_BASE}/{self.tenant_id}"

    @property
    def scopes(self) -> list[str]:
        return SCOPES_GEDEELD if self.gedeelde_agendas else SCOPES


def _ja(naam: str) -> bool:
    return os.getenv(naam, "").strip().lower() in ("1", "true", "ja", "yes")


def load_config() -> Config:
    client_id = os.getenv("OUTLOOK_CLIENT_ID", "").strip()
    if not client_id:
        raise ConfigError(
            "OUTLOOK_CLIENT_ID ontbreekt. Dat is de Application (client) ID van je "
            "app-registratie in Entra ID. Kopieer .env.example naar .env en vul hem "
            "in; zie README.md voor waar je dat id vindt."
        )

    tenant_id = os.getenv("OUTLOOK_TENANT_ID", "").strip()
    if not tenant_id:
        raise ConfigError(
            "OUTLOOK_TENANT_ID ontbreekt. Vul je Directory (tenant) ID in .env in, "
            "of gebruik 'organizations' als je met een werkaccount inlogt."
        )

    return Config(
        client_id=client_id,
        tenant_id=tenant_id,
        # Graph rekent zelf om; deze zone geldt voor tijden zonder expliciete zone.
        timezone=os.getenv("OUTLOOK_TIMEZONE", "").strip() or "Europe/Amsterdam",
        timeout=int(os.getenv("OUTLOOK_TIMEOUT", "30")),
        graph_base=os.getenv("OUTLOOK_GRAPH_BASE", "").strip() or GRAPH_BASE,
        gedeelde_agendas=_ja("OUTLOOK_GEDEELDE_AGENDAS"),
    )
