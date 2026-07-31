"""Sla je e-Boekhouden API-sleutel op in de kluis van je besturingssysteem.

    uv run python save_token.py

Op Windows is dat Credential Manager, op macOS de Keychain en op Linux de
Secret Service. De sleutel staat daarna nergens in een leesbaar bestand, en
je hoeft hem niet meer in .env te zetten.

Je typt de sleutel in bij een verborgen prompt: hij verschijnt niet op je
scherm en komt niet in je opdrachtgeschiedenis terecht.
"""
from __future__ import annotations

import sys
from getpass import getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import KEYRING_DIENST, KEYRING_GEBRUIKER  # noqa: E402


def main() -> int:
    try:
        import keyring
    except ImportError:
        print("Het pakket 'keyring' ontbreekt. Installeer het met:\n")
        print("    uv add keyring        (of: pip install keyring)\n")
        return 1

    print("e-Boekhouden API-sleutel opslaan in de kluis van je besturingssysteem.")
    print("Plak de sleutel hieronder en druk op Enter. Je ziet geen tekens "
          "verschijnen; dat hoort zo.\n")

    try:
        token = getpass("API-sleutel: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nAfgebroken; er is niets opgeslagen.")
        return 1

    if not token:
        print("Er is niets ingevoerd; er is niets opgeslagen.")
        return 1

    try:
        keyring.set_password(KEYRING_DIENST, KEYRING_GEBRUIKER, token)
    except Exception as exc:
        print(f"\nOpslaan mislukt: {exc}")
        print("Je systeem heeft blijkbaar geen werkende sleutelkluis. Zet de "
              "sleutel dan in .env als EBOEKHOUDEN_API_TOKEN.")
        return 1

    terug = keyring.get_password(KEYRING_DIENST, KEYRING_GEBRUIKER)
    if terug != token:
        print("\nDe sleutel is opgeslagen maar kwam anders terug uit de kluis. "
              "Controleer je sleutelkluis handmatig.")
        return 1

    print(f"\nOpgeslagen in de kluis ({len(token)} tekens) onder "
          f"'{KEYRING_DIENST}/{KEYRING_GEBRUIKER}'.")

    env_pad = Path(__file__).resolve().parent / ".env"
    if env_pad.exists() and "EBOEKHOUDEN_API_TOKEN=" in env_pad.read_text(encoding="utf-8"):
        print("\nLet op: in .env staat ook nog een regel EBOEKHOUDEN_API_TOKEN.")
        print("Die wint van de kluis. Maak die regel leeg of haal hem weg, dan "
              "staat je sleutel alleen nog versleuteld in de kluis.")

    print("\nControleer nu met: python check_setup.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
