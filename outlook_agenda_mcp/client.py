"""Dunne client voor Microsoft Graph (v1.0).

Regelt het toegangstoken, retries op throttling/serverfouten en leesbare
foutmeldingen. De aanroepende code werkt met gewone dicts.
"""
from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

import requests

import auth
from config import Config

RETRY_STATUS = (429, 500, 502, 503, 504)


class GraphError(RuntimeError):
    """Fout uit Microsoft Graph, met status en (indien aanwezig) uitleg."""

    def __init__(self, status: int, bericht: str, pad: str = ""):
        self.status = status
        self.pad = pad
        super().__init__(f"Microsoft Graph gaf {status} op {pad}: {bericht}" if pad
                         else f"Microsoft Graph gaf {status}: {bericht}")


class GraphClient:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()

    # ── verzoeken ───────────────────────────────────────────────────────
    def _request(self, methode: str, pad: str, **kwargs: Any) -> Any:
        url = f"{self.config.graph_base}{pad}"
        token_vernieuwd = False

        for poging in range(5):
            headers = {
                "Authorization": f"Bearer {auth.token(self.config)}",
                "Accept": "application/json",
            }
            # Graph geeft tijden terug in de zone die je hier vraagt.
            headers["Prefer"] = f'outlook.timezone="{self.config.timezone}"'
            headers.update(kwargs.pop("headers", {}))

            try:
                resp = self.session.request(
                    methode, url, headers=headers, timeout=self.config.timeout, **kwargs
                )
            except requests.RequestException as exc:
                if poging == 4:
                    raise GraphError(
                        0,
                        f"kan {self.config.graph_base} niet bereiken "
                        f"({exc.__class__.__name__}). Controleer je internetverbinding, "
                        "een eventuele proxy of firewall.",
                        pad,
                    ) from exc
                time.sleep(2 ** poging)
                continue

            if resp.status_code == 401 and not token_vernieuwd:
                # Token net verlopen: één keer opnieuw ophalen en nog eens proberen.
                token_vernieuwd = True
                continue

            if resp.status_code in RETRY_STATUS and poging < 4:
                wacht = resp.headers.get("Retry-After")
                time.sleep(int(wacht) if wacht and wacht.isdigit() else 2 ** poging)
                continue

            if resp.status_code >= 400:
                raise GraphError(resp.status_code, _fouttekst(resp), pad)

            if not resp.content:
                return None
            try:
                return resp.json()
            except ValueError:
                return resp.text

        raise GraphError(0, "geen antwoord na meerdere pogingen", pad)

    def get(self, pad: str, params: dict | None = None) -> Any:
        return self._request("GET", pad, params=params)

    def post(self, pad: str, body: dict) -> Any:
        return self._request("POST", pad, json=body)

    def patch(self, pad: str, body: dict) -> Any:
        return self._request("PATCH", pad, json=body)

    def delete(self, pad: str) -> Any:
        return self._request("DELETE", pad)

    # ── endpoints ───────────────────────────────────────────────────────
    def wie_ben_ik(self) -> dict:
        return self.get("/me", {"$select": "displayName,mail,userPrincipalName,id"})

    def agendas(self, eigenaar: str = "") -> list[dict]:
        return items(self.get(f"{_basis(eigenaar)}/calendars", {"$top": 50}))

    def afspraken(
        self,
        start: str,
        eind: str,
        limit: int = 25,
        agenda_id: str = "",
        eigenaar: str = "",
    ) -> list[dict]:
        """Afspraken in een periode, inclusief losse voorkomens van herhalingen."""
        pad = _agendapad(agenda_id, eigenaar) + "/calendarView"
        antwoord = self.get(
            pad,
            {
                "startDateTime": start,
                "endDateTime": eind,
                "$orderby": "start/dateTime",
                "$top": max(1, min(limit, 100)),
                "$select": "id,subject,start,end,location,isAllDay,isCancelled,"
                           "organizer,attendees,showAs,bodyPreview,webLink",
            },
        )
        return items(antwoord)[:limit]

    def afspraak(self, event_id: str, eigenaar: str = "") -> dict:
        return self.get(f"{_basis(eigenaar)}/events/{quote(event_id, safe='')}")

    def maak_afspraak(self, body: dict, agenda_id: str = "", eigenaar: str = "") -> dict:
        return self.post(_agendapad(agenda_id, eigenaar) + "/events", body)

    def wijzig_afspraak(self, event_id: str, body: dict, eigenaar: str = "") -> dict:
        return self.patch(f"{_basis(eigenaar)}/events/{quote(event_id, safe='')}", body)

    def verwijder_afspraak(self, event_id: str, eigenaar: str = "") -> None:
        self.delete(f"{_basis(eigenaar)}/events/{quote(event_id, safe='')}")


def _basis(eigenaar: str = "") -> str:
    """/me voor je eigen mailbox, /users/<adres> voor een gedeelde agenda."""
    return f"/users/{quote(eigenaar)}" if eigenaar else "/me"


def _agendapad(agenda_id: str = "", eigenaar: str = "") -> str:
    basis = _basis(eigenaar)
    if agenda_id:
        return f"{basis}/calendars/{quote(agenda_id, safe='')}"
    return f"{basis}/calendar"


def items(payload: Any) -> list[dict]:
    """Haal de lijst uit een antwoord, ongeacht of Graph een kale array of een
    omhulsel met 'value' teruggeeft."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        waarde = payload.get("value")
        if isinstance(waarde, list):
            return waarde
        return [payload]
    return []


def _fouttekst(resp: requests.Response) -> str:
    try:
        data = resp.json()
    except ValueError:
        return (resp.text or "").strip()[:500] or resp.reason
    if isinstance(data, dict):
        fout = data.get("error")
        if isinstance(fout, dict):
            melding = fout.get("message") or fout.get("code") or ""
            code = fout.get("code") or ""
            if code and melding and code not in melding:
                return f"{melding} ({code})"
            return str(melding or code)
        for sleutel in ("message", "error_description", "title", "detail"):
            if data.get(sleutel):
                return str(data[sleutel])
    return str(data)[:500]
