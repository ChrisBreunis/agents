"""Device-code authenticatie tegen Microsoft Graph via MSAL.

Jij logt 1x in via een code in de browser. Het token wordt versleuteld
gecachet in .token_cache.json, zodat herhaald draaien niet telkens om een
nieuwe login vraagt (tot het token verloopt).
"""
from __future__ import annotations

import sys
from pathlib import Path

import msal

from config import Config, GRAPH_SCOPES

CACHE_FILE = Path(".token_cache.json")


def _build_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if CACHE_FILE.exists():
        cache.deserialize(CACHE_FILE.read_text())
    return cache


def _persist_cache(cache: msal.SerializableTokenCache) -> None:
    if cache.has_state_changed:
        CACHE_FILE.write_text(cache.serialize())
        # Beperk leesrechten: dit bestand bevat een toegangstoken.
        try:
            CACHE_FILE.chmod(0o600)
        except OSError:
            pass


def get_access_token(config: Config) -> str:
    """Geef een geldig Graph-accesstoken terug (device-code flow + cache)."""
    cache = _build_cache()
    app = msal.PublicClientApplication(
        config.client_id, authority=config.authority, token_cache=cache
    )

    result = None
    accounts = app.get_accounts()
    if accounts:
        # Probeer stil te verversen vanuit de cache.
        result = app.acquire_token_silent(GRAPH_SCOPES, account=accounts[0])

    if not result:
        flow = app.initiate_device_flow(scopes=GRAPH_SCOPES)
        if "user_code" not in flow:
            sys.exit(f"Kon device-flow niet starten: {flow.get('error_description', flow)}")
        print("\n" + "=" * 70)
        print(flow["message"])  # Ga naar URL en voer de code in.
        print("=" * 70 + "\n", flush=True)
        result = app.acquire_token_by_device_flow(flow)

    _persist_cache(cache)

    if "access_token" not in result:
        sys.exit(
            "Inloggen mislukt: "
            f"{result.get('error')}: {result.get('error_description')}"
        )
    return result["access_token"]
