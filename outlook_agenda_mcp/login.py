"""Log eenmalig in bij Microsoft, zodat de agenda-server je agenda mag lezen
en beschrijven.

    uv run --directory outlook_agenda_mcp python login.py

Je krijgt een code te zien die je op microsoft.com/devicelogin invult. Daarna
wordt het token bewaard in de kluis van je besturingssysteem (Windows
Credential Manager, macOS Keychain of Linux Secret Service) en vernieuwt de
server zichzelf. Er komt geen wachtwoord in dit venster of in je
opdrachtgeschiedenis terecht.

Uitloggen kan met:

    uv run --directory outlook_agenda_mcp python login.py --uitloggen
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import auth  # noqa: E402
from config import ConfigError, load_config  # noqa: E402


def main(argumenten: list[str]) -> int:
    if "--uitloggen" in argumenten or "--logout" in argumenten:
        auth.wis_cache()
        print("Uitgelogd: het bewaarde token is verwijderd.")
        return 0

    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"Configuratie onvolledig:\n\n    {exc}")
        return 1

    print(f"Inloggen bij Microsoft voor tenant {cfg.tenant_id}.")
    print(f"Gevraagde rechten: {', '.join(cfg.scopes)}\n")

    try:
        resultaat = auth.login(cfg)
    except auth.AuthError as exc:
        print(f"\n{exc}")
        return 1
    except KeyboardInterrupt:
        print("\nAfgebroken; er is niet ingelogd.")
        return 1

    account = resultaat.get("id_token_claims", {}) or {}
    naam = account.get("preferred_username") or account.get("name") or "onbekend account"
    print(f"\nIngelogd als {naam}.")

    verleend = (resultaat.get("scope") or "").split()
    if verleend:
        print(f"Verleende rechten: {', '.join(verleend)}")
    if not any(recht.endswith("Calendars.ReadWrite") for recht in verleend):
        print(
            "\nLet op: Calendars.ReadWrite zit niet in het token. Afspraken aanmaken "
            "zal mislukken.\nControleer de gedelegeerde machtigingen van de "
            "app-registratie in Entra ID en log daarna opnieuw in."
        )
        return 1

    print("\nControleer nu met: python check_setup.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
