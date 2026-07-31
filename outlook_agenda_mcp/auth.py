"""Inloggen bij Microsoft met de device code flow.

Je logt één keer in met login.py; daarna vernieuwt de server het token zelf en
hoef je niets meer te doen. De tokencache gaat in de kluis van je
besturingssysteem, en valt terug op een bestand met beperkte rechten als er
geen kluis beschikbaar is (bijvoorbeeld op een kale server).
"""
from __future__ import annotations

import os
from pathlib import Path

from config import KEYRING_DIENST, KEYRING_GEBRUIKER, Config, ConfigError

CACHE_BESTAND = Path(__file__).resolve().parent / ".token-cache.json"


class AuthError(RuntimeError):
    """Inloggen of het vernieuwen van het token is mislukt."""


# ── tokencache bewaren ──────────────────────────────────────────────────
def _lees_cache() -> str:
    try:
        import keyring
    except ImportError:
        pass
    else:
        try:
            opgeslagen = keyring.get_password(KEYRING_DIENST, KEYRING_GEBRUIKER)
            if opgeslagen:
                return opgeslagen
        except Exception:
            pass  # geen werkende kluis: dan het bestand proberen
    if CACHE_BESTAND.exists():
        return CACHE_BESTAND.read_text(encoding="utf-8")
    return ""


def _schrijf_cache(inhoud: str) -> None:
    try:
        import keyring
    except ImportError:
        pass
    else:
        try:
            keyring.set_password(KEYRING_DIENST, KEYRING_GEBRUIKER, inhoud)
            return
        except Exception:
            pass
    # Terugval: alleen leesbaar voor de eigen gebruiker.
    CACHE_BESTAND.write_text(inhoud, encoding="utf-8")
    try:
        os.chmod(CACHE_BESTAND, 0o600)
    except OSError:
        pass


def wis_cache() -> None:
    """Uitloggen: het bewaarde token weggooien."""
    try:
        import keyring
    except ImportError:
        pass
    else:
        try:
            keyring.delete_password(KEYRING_DIENST, KEYRING_GEBRUIKER)
        except Exception:
            pass
    CACHE_BESTAND.unlink(missing_ok=True)


# ── tokens ophalen ──────────────────────────────────────────────────────
def _app(config: Config):
    try:
        import msal
    except ImportError as exc:
        raise AuthError(
            "Het pakket 'msal' ontbreekt. Installeer het met: uv add msal "
            "(of: pip install msal)."
        ) from exc

    cache = msal.SerializableTokenCache()
    opgeslagen = _lees_cache()
    if opgeslagen:
        try:
            cache.deserialize(opgeslagen)
        except ValueError:
            pass  # onleesbare cache: dan opnieuw inloggen
    return msal.PublicClientApplication(
        config.client_id, authority=config.authority, token_cache=cache
    ), cache


def _bewaar(cache) -> None:
    if cache.has_state_changed:
        _schrijf_cache(cache.serialize())


def token(config: Config) -> str:
    """Een geldig toegangstoken, zonder tussenkomst van de gebruiker.

    Werkt alleen als er eerder is ingelogd met login.py.
    """
    app, cache = _app(config)
    accounts = app.get_accounts()
    if not accounts:
        raise AuthError(
            "Nog niet ingelogd bij Microsoft. Draai eenmalig:\n"
            "    uv run --directory outlook_agenda_mcp python login.py"
        )

    resultaat = app.acquire_token_silent(config.scopes, account=accounts[0])
    _bewaar(cache)
    if not resultaat or "access_token" not in resultaat:
        raise AuthError(
            "Het opgeslagen token is verlopen of ingetrokken. Log opnieuw in met:\n"
            "    uv run --directory outlook_agenda_mcp python login.py"
        )
    return resultaat["access_token"]


def login(config: Config, toon=print) -> dict:
    """Interactief inloggen via de device code flow.

    Toont een code die je op microsoft.com/devicelogin invoert. Geeft de
    accountgegevens terug zodra het gelukt is.
    """
    app, cache = _app(config)

    accounts = app.get_accounts()
    if accounts:
        resultaat = app.acquire_token_silent(config.scopes, account=accounts[0])
        if resultaat and "access_token" in resultaat:
            _bewaar(cache)
            return resultaat

    flow = app.initiate_device_flow(scopes=config.scopes)
    if "user_code" not in flow:
        fout = flow.get("error_description") or flow.get("error") or str(flow)
        raise AuthError(f"Kon geen inlogcode opvragen: {fout}\n\n{_uitleg(fout)}")

    toon(flow["message"])
    resultaat = app.acquire_token_by_device_flow(flow)
    _bewaar(cache)

    if "access_token" not in resultaat:
        fout = resultaat.get("error_description") or resultaat.get("error") or str(resultaat)
        raise AuthError(f"Inloggen mislukt: {fout}\n\n{_uitleg(fout)}")
    return resultaat


def _uitleg(fout: str) -> str:
    """De foutcodes van Microsoft zijn cryptisch; vertaal de bekende naar de
    instelling die je moet aanpassen."""
    if "AADSTS7000218" in fout:
        return (
            "Microsoft behandelt de app als vertrouwelijke client en verwacht een "
            "geheim, terwijl deze inlogmethode er juist geen gebruikt. Zet in Entra "
            "ID bij je app-registratie onder Verificatie > Geavanceerde instellingen "
            "'Openbare clientstromen toestaan' op Ja, en sla op."
        )
    if "AADSTS700016" in fout:
        return (
            "De app bestaat niet in deze tenant. Controleer OUTLOOK_CLIENT_ID: dat "
            "moet de Toepassings-id (client) van de Overzicht-pagina zijn, niet het "
            "id van een clientgeheim of het object-id. Controleer ook of "
            "OUTLOOK_TENANT_ID bij die app hoort."
        )
    if "AADSTS7000112" in fout:
        return (
            "De bedrijfsapp staat uit. Zet in Entra ID onder Bedrijfsapps > Alle "
            "toepassingen > deze app > Eigenschappen 'Ingeschakeld voor aanmelding "
            "door gebruikers' op Ja. Let op: dat is een ander scherm dan de "
            "app-registratie met dezelfde naam."
        )
    if "AADSTS70016" in fout:
        return (
            "De inlogcode is verlopen voordat hij was goedgekeurd; hij is ongeveer "
            "vijftien minuten geldig. Draai login.py opnieuw voor een verse code."
        )
    if "AADSTS65001" in fout or "AADSTS90094" in fout:
        return (
            "De gevraagde rechten zijn nog niet toegestaan. Voeg in Entra ID onder "
            "API-machtigingen de gedelegeerde machtiging Calendars.ReadWrite toe, en "
            "verleen zo nodig beheerderstoestemming."
        )
    return "Zie README.md voor de instellingen die deze server in Entra ID verwacht."


def verleende_rechten(config: Config) -> list[str]:
    """De rechten die daadwerkelijk in het token zitten. Handig om te zien of
    Calendars.ReadWrite echt verleend is."""
    app, cache = _app(config)
    accounts = app.get_accounts()
    if not accounts:
        raise AuthError(
            "Nog niet ingelogd bij Microsoft. Draai eenmalig:\n"
            "    uv run --directory outlook_agenda_mcp python login.py"
        )
    resultaat = app.acquire_token_silent(config.scopes, account=accounts[0]) or {}
    _bewaar(cache)
    ruw = resultaat.get("scope") or ""
    if isinstance(ruw, list):
        return ruw
    return [deel for deel in ruw.split() if deel]


__all__ = ["AuthError", "ConfigError", "login", "token", "verleende_rechten", "wis_cache"]
