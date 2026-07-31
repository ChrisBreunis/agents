"""Controleer in één keer of de koppeling met je Outlook-agenda goed staat.

Draai dit vanuit deze map:

    uv run python check_setup.py

Het toont wat er wel en niet werkt. Er wordt niets aan je agenda gewijzigd, en
je token wordt nooit afgedrukt, dus de uitvoer kun je veilig delen.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def melden(gelukt: bool | None, tekst: str) -> None:
    teken = {True: "OK  ", False: "FOUT", None: "-   "}[gelukt]
    print(f"[{teken}] {tekst}")


def main() -> int:
    print("Controle van de Outlook-agendakoppeling\n")

    # 1. Benodigde pakketten
    ontbreekt = []
    for naam in ("requests", "dotenv", "mcp", "msal"):
        try:
            __import__(naam)
        except ImportError:
            ontbreekt.append("python-dotenv" if naam == "dotenv" else naam)
    if ontbreekt:
        melden(False, f"pakketten ontbreken: {', '.join(ontbreekt)}")
        print("\n    Los op met: uv sync   (of: pip install -r requirements.txt)")
        return 1
    melden(True, "benodigde pakketten aanwezig")

    # 2. .env-bestand
    env_pad = Path(__file__).resolve().parent / ".env"
    if env_pad.exists():
        melden(True, f".env gevonden: {env_pad}")
    else:
        melden(None, f"geen .env naast de server ({env_pad})")
        print("    Dat mag: de instellingen kunnen ook als omgevingsvariabelen "
              "staan.\n    Anders: kopieer .env.example naar .env en vul je "
              "client-id en tenant-id in.")

    # 3. Configuratie
    from config import ConfigError, load_config  # noqa: E402

    try:
        cfg = load_config()
    except ConfigError as exc:
        melden(False, "configuratie onvolledig")
        print(f"\n    {exc}")
        return 1
    melden(True, f"client-id ingesteld ({cfg.client_id})")
    melden(None, f"tenant: {cfg.tenant_id}")
    melden(None, f"tijdzone: {cfg.timezone}")

    # 4. Inloggen
    import auth  # noqa: E402

    try:
        rechten = auth.verleende_rechten(cfg)
    except auth.AuthError as exc:
        melden(False, "nog niet ingelogd")
        print(f"\n    {exc}")
        return 1
    melden(True, "token gevonden en geldig")

    mag_schrijven = any(recht.endswith("Calendars.ReadWrite") for recht in rechten)
    melden(mag_schrijven, f"verleende rechten: {', '.join(rechten) or 'geen'}")
    if not mag_schrijven:
        print("\n    Calendars.ReadWrite ontbreekt. Controleer de gedelegeerde")
        print("    machtigingen van de app-registratie in Entra ID (API-machtigingen)")
        print("    en log daarna opnieuw in met 'python login.py'.")

    # 5. Verbinding met Graph
    from client import GraphClient, GraphError  # noqa: E402

    client = GraphClient(cfg)
    try:
        ik = client.wie_ben_ik()
    except GraphError as exc:
        melden(False, "geen verbinding met Microsoft Graph")
        print(f"\n    {exc}\n")
        if exc.status == 401:
            print("    401 betekent: het token is niet (meer) geldig. Log opnieuw in")
            print("    met 'python login.py'.")
        elif exc.status == 403:
            print("    403 betekent: ingelogd, maar zonder de benodigde rechten.")
            print("    Controleer de machtigingen in Entra ID.")
        elif exc.status == 0:
            print("    Er kwam geen antwoord terug. Kijk naar je internetverbinding,")
            print("    een proxy of een firewall.")
        return 1
    melden(True, f"verbonden als {ik.get('mail') or ik.get('userPrincipalName')}")

    # 6. Agenda's en een blik op vandaag
    try:
        agendas = client.agendas()
        melden(True, f"{len(agendas)} agenda(s) gevonden")
        for agenda in agendas[:5]:
            merk = " (standaard)" if agenda.get("isDefaultCalendar") else ""
            schrijf = "schrijven" if agenda.get("canEdit") else "alleen lezen"
            print(f"       {agenda.get('name', '')}{merk} — {schrijf}")
    except GraphError as exc:
        melden(False, f"agenda's ophalen mislukt: {exc}")

    vandaag = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        afspraken = client.afspraken(
            vandaag.strftime("%Y-%m-%dT%H:%M:%S"),
            (vandaag + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S"),
            limit=100,
        )
        melden(True, f"{len(afspraken)} afspra(a)k(en) in de komende zeven dagen")
    except GraphError as exc:
        melden(False, f"afspraken ophalen mislukt: {exc}")

    print("\nKlaar.")
    if mag_schrijven:
        print("De koppeling is compleet: afspraken aanmaken en wijzigen kan.")
    else:
        print("Lezen werkt, schrijven nog niet — zie de melding hierboven.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
