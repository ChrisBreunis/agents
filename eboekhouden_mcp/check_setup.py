"""Controleer in één keer of de koppeling met e-Boekhouden goed staat.

Draai dit vanuit deze map:

    uv run python check_setup.py

Het toont wat er wel en niet werkt, en welke regels je nog in .env kunt zetten.
Je API-sleutel wordt nooit afgedrukt, dus de uitvoer kun je veilig delen.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def melden(gelukt: bool | None, tekst: str) -> None:
    teken = {True: "OK  ", False: "FOUT", None: "-   "}[gelukt]
    print(f"[{teken}] {tekst}")


def main() -> int:
    print("Controle van de e-Boekhouden-koppeling\n")

    # 1. Benodigde pakketten
    ontbreekt = []
    for naam in ("requests", "dotenv", "mcp"):
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
        print("    Kopieer .env.example naar .env en vul je API-sleutel in.")

    # 3. Configuratie
    from config import ConfigError, load_config  # noqa: E402

    try:
        cfg = load_config()
    except ConfigError as exc:
        melden(False, "configuratie onvolledig")
        print(f"\n    {exc}")
        return 1
    melden(True, f"API-sleutel gevonden ({len(cfg.api_token)} tekens, niet getoond)")
    melden(None, f"API-adres: {cfg.base_url}")

    # 4. Verbinding
    from client import EBoekhoudenClient, EBoekhoudenError  # noqa: E402

    client = EBoekhoudenClient(cfg)
    try:
        administratie = client.administratie()
    except EBoekhoudenError as exc:
        melden(False, "geen verbinding met e-Boekhouden")
        print(f"\n    {exc}\n")
        if exc.status == 401:
            print("    401 betekent: sleutel niet herkend. Controleer of je de sleutel")
            print("    volledig hebt overgenomen en of je hem in e-Boekhouden hebt")
            print("    opgeslagen (Beheer > Inrichting > Koppelingen > API).")
        elif exc.status == 403:
            print("    403 betekent: de sleutel bestaat, maar mist rechten. Geef het")
            print("    token rechten op relaties en facturen.")
        elif exc.status == 0:
            print("    Er kwam geen antwoord terug. Kijk naar je internetverbinding,")
            print("    een proxy of een firewall.")
        return 1
    melden(True, f"verbinding werkt — administratie: {administratie}")

    # 5. Gegevens die je in .env wilt vastleggen
    tips: list[str] = []

    try:
        sjablonen = client.factuursjablonen()
        melden(True, f"{len(sjablonen)} factuursjabloon(en) gevonden")
        for sjabloon in sjablonen[:5]:
            print(f"       id={sjabloon.get('id')}  {sjabloon.get('name', '')}")
        if sjablonen and cfg.default_template_id is None:
            tips.append(f"EBOEKHOUDEN_DEFAULT_TEMPLATE_ID={sjablonen[0].get('id')}")
    except EBoekhoudenError as exc:
        melden(False, f"sjablonen ophalen mislukt: {exc}")

    try:
        omzet = [r for r in client.grootboekrekeningen()
                 if "omzet" in str(r.get("description", "")).lower()]
        melden(True, f"{len(omzet)} grootboekrekening(en) met 'omzet' in de naam")
        for rekening in omzet[:5]:
            print(f"       id={rekening.get('id')}  {rekening.get('code', '')} "
                  f"{rekening.get('description', '')}")
        if omzet and cfg.default_ledger_id is None:
            tips.append(f"EBOEKHOUDEN_DEFAULT_LEDGER_ID={omzet[0].get('id')}")
    except EBoekhoudenError as exc:
        melden(False, f"grootboekrekeningen ophalen mislukt: {exc}")

    try:
        melden(True, f"{len(client.relaties(limit=100))} relatie(s) opgehaald")
    except EBoekhoudenError as exc:
        melden(False, f"relaties ophalen mislukt: {exc}")

    client.sluit_sessie()

    print("\nKlaar.")
    if tips:
        print("Zet deze regels nog in .env, dan hoef je ze per factuur niet te noemen:")
        for tip in tips:
            print(f"    {tip}")
    else:
        print("De koppeling is compleet ingesteld.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
