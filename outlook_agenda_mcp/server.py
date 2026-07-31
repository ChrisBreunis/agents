"""MCP-server voor je Outlook-agenda via Microsoft Graph.

Werkwijze: kijk eerst met list_events of het tijdstip vrij is, maak de afspraak
met create_event, en gebruik het id daaruit om later te wijzigen of te
verwijderen. Alleen create_event, update_event en delete_event schrijven.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as Server  # noqa: E402
except ImportError:  # mcp 2.x noemt dezelfde klasse MCPServer
    from mcp.server.mcpserver import MCPServer as Server  # noqa: E402

import auth  # noqa: E402
from client import GraphClient, GraphError  # noqa: E402
from config import Config, ConfigError, load_config  # noqa: E402

mcp = Server("outlook-agenda")

_client: GraphClient | None = None
_config: Config | None = None


def client() -> GraphClient:
    """Client bij eerste gebruik opzetten, zodat een ontbrekende .env pas bij
    de eerste tool-aanroep een duidelijke fout geeft."""
    global _client, _config
    if _client is None:
        _config = load_config()
        _client = GraphClient(_config)
    return _client


def config() -> Config:
    client()
    assert _config is not None
    return _config


# ── hulpfuncties ────────────────────────────────────────────────────────
def _tijdstip(waarde: str, veld: str) -> datetime:
    """'2026-08-20T09:00', '2026-08-20 09:00' en '2026-08-20' worden allemaal
    geaccepteerd; een datum zonder tijd wordt middernacht."""
    tekst = (waarde or "").strip().replace(" ", "T")
    if not tekst:
        raise ValueError(f"{veld} ontbreekt. Gebruik JJJJ-MM-DDTUU:MM.")
    if tekst.endswith("Z"):
        tekst = tekst[:-1]
    try:
        gelezen = datetime.fromisoformat(tekst)
    except ValueError as exc:
        raise ValueError(
            f"{veld} {waarde!r} is geen geldig tijdstip. Gebruik JJJJ-MM-DDTUU:MM, "
            "bijvoorbeeld 2026-08-20T09:00."
        ) from exc
    # Een eventuele tijdzone laten we vallen: Graph krijgt de zone apart mee.
    return gelezen.replace(tzinfo=None)


def _graph_tijd(moment: datetime, zone: str) -> dict:
    return {"dateTime": moment.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": zone}


def _dag(waarde: str, veld: str) -> date:
    return _tijdstip(waarde, veld).date()


def _kort(afspraak: dict) -> dict:
    """Een afspraak terugbrengen tot wat je in een gesprek wilt zien."""
    plaats = (afspraak.get("location") or {}).get("displayName") or ""
    organisator = ((afspraak.get("organizer") or {}).get("emailAddress") or {}).get("address", "")
    genodigden = [
        ((deelnemer.get("emailAddress") or {}).get("address") or "")
        for deelnemer in afspraak.get("attendees") or []
    ]
    return {
        "id": afspraak.get("id"),
        "onderwerp": afspraak.get("subject"),
        "start": (afspraak.get("start") or {}).get("dateTime"),
        "eind": (afspraak.get("end") or {}).get("dateTime"),
        "tijdzone": (afspraak.get("start") or {}).get("timeZone"),
        "heleDag": afspraak.get("isAllDay", False),
        "locatie": plaats,
        "organisator": organisator,
        "genodigden": [adres for adres in genodigden if adres],
        "geannuleerd": afspraak.get("isCancelled", False),
        "weergaveAls": afspraak.get("showAs"),
        "webLink": afspraak.get("webLink"),
    }


def _bouw_afspraak(
    subject: str,
    start: str,
    end: str,
    duration_minutes: int,
    location: str,
    body: str,
    attendees: list[str] | None,
    reminder_minutes: int | None,
    all_day: bool,
    show_as: str,
    timezone: str,
) -> dict:
    zone = (timezone or "").strip() or config().timezone
    payload: dict = {"subject": subject}

    if all_day:
        eerste = _dag(start, "start")
        # Graph verwacht bij een hele dag de dág ná de laatste dag als eind.
        laatste = _dag(end, "end") if end else eerste
        if laatste < eerste:
            raise ValueError("De einddatum ligt vóór de startdatum.")
        payload["isAllDay"] = True
        payload["start"] = {"dateTime": f"{eerste.isoformat()}T00:00:00", "timeZone": zone}
        payload["end"] = {
            "dateTime": f"{(laatste + timedelta(days=1)).isoformat()}T00:00:00",
            "timeZone": zone,
        }
    else:
        begint = _tijdstip(start, "start")
        if end:
            eindigt = _tijdstip(end, "end")
        else:
            if duration_minutes <= 0:
                raise ValueError("duration_minutes moet groter dan 0 zijn.")
            eindigt = begint + timedelta(minutes=duration_minutes)
        if eindigt <= begint:
            raise ValueError(
                f"Het eind ({eindigt:%Y-%m-%d %H:%M}) ligt niet ná het begin "
                f"({begint:%Y-%m-%d %H:%M})."
            )
        payload["start"] = _graph_tijd(begint, zone)
        payload["end"] = _graph_tijd(eindigt, zone)

    if location:
        payload["location"] = {"displayName": location}
    if body:
        payload["body"] = {"contentType": "text", "content": body}
    if attendees:
        payload["attendees"] = [
            {"emailAddress": {"address": adres}, "type": "required"}
            for adres in attendees
            if adres and adres.strip()
        ]
    if reminder_minutes is not None:
        payload["isReminderOn"] = reminder_minutes >= 0
        if reminder_minutes >= 0:
            payload["reminderMinutesBeforeStart"] = int(reminder_minutes)
    if show_as:
        payload["showAs"] = show_as
    return payload


# ── verbinding ──────────────────────────────────────────────────────────
@mcp.tool()
async def check_connection() -> dict:
    """Controleer of het inloggen werkt en toon met welk account, welke rechten
    er verleend zijn en welke tijdzone gebruikt wordt.

    Draai dit eerst bij twijfel: het maakt geen wijzigingen.
    """
    try:
        cfg = config()
        ik = client().wie_ben_ik()
        rechten = auth.verleende_rechten(cfg)
    except (ConfigError, auth.AuthError, GraphError) as exc:
        return {"ok": False, "melding": str(exc)}

    mag_schrijven = any(recht.endswith("Calendars.ReadWrite") for recht in rechten)
    resultaat = {
        "ok": True,
        "account": ik.get("mail") or ik.get("userPrincipalName"),
        "naam": ik.get("displayName"),
        "tijdzone": cfg.timezone,
        "rechten": rechten,
        "magAfsprakenAanmaken": mag_schrijven,
    }
    if not mag_schrijven:
        resultaat["melding"] = (
            "Calendars.ReadWrite zit niet in het token. Aanmaken zal mislukken. "
            "Controleer de gedelegeerde machtigingen van de app-registratie in "
            "Entra ID en log daarna opnieuw in met login.py."
        )
    return resultaat


@mcp.tool()
async def list_calendars(calendar_owner: str = "") -> list[dict]:
    """Toon je agenda's, met hun id en of je erin mag schrijven.

    Args:
        calendar_owner: e-mailadres van iemand anders wiens agenda je mag zien.
            Leeg = je eigen agenda's.
    """
    return [
        {
            "id": agenda.get("id"),
            "naam": agenda.get("name"),
            "standaard": agenda.get("isDefaultCalendar", False),
            "magSchrijven": agenda.get("canEdit", False),
            "eigenaar": ((agenda.get("owner") or {}).get("address") or ""),
        }
        for agenda in client().agendas(eigenaar=calendar_owner)
    ]


# ── kijken ──────────────────────────────────────────────────────────────
@mcp.tool()
async def list_events(
    start: str,
    end: str = "",
    limit: int = 25,
    calendar_id: str = "",
    calendar_owner: str = "",
) -> list[dict]:
    """Toon de afspraken in een periode. Gebruik dit om te controleren of een
    tijdstip vrij is voordat je iets aanmaakt.

    Args:
        start: begin van de periode, JJJJ-MM-DD of JJJJ-MM-DDTUU:MM.
        end: eind van de periode; leeg = 24 uur na start.
        limit: maximaal aantal afspraken (standaard 25).
        calendar_id: id van een specifieke agenda; leeg = je hoofdagenda.
        calendar_owner: e-mailadres van iemand anders wiens agenda je mag zien.
    """
    begint = _tijdstip(start, "start")
    eindigt = _tijdstip(end, "end") if end else begint + timedelta(days=1)
    if eindigt <= begint:
        raise ValueError("end moet ná start liggen.")

    afspraken = client().afspraken(
        begint.strftime("%Y-%m-%dT%H:%M:%S"),
        eindigt.strftime("%Y-%m-%dT%H:%M:%S"),
        limit=limit,
        agenda_id=calendar_id,
        eigenaar=calendar_owner,
    )
    return [_kort(afspraak) for afspraak in afspraken]


@mcp.tool()
async def get_event(event_id: str, calendar_owner: str = "") -> dict:
    """Haal één afspraak op met alle details.

    Args:
        event_id: het id uit list_events of create_event.
        calendar_owner: e-mailadres van de eigenaar bij een gedeelde agenda.
    """
    afspraak = client().afspraak(event_id, eigenaar=calendar_owner)
    kort = _kort(afspraak)
    kort["omschrijving"] = (afspraak.get("body") or {}).get("content") or ""
    kort["herinneringMinuten"] = afspraak.get("reminderMinutesBeforeStart")
    return kort


# ── schrijven ───────────────────────────────────────────────────────────
@mcp.tool()
async def create_event(
    subject: str,
    start: str,
    end: str = "",
    duration_minutes: int = 60,
    location: str = "",
    body: str = "",
    attendees: list[str] | None = None,
    reminder_minutes: int = 30,
    all_day: bool = False,
    show_as: str = "",
    timezone: str = "",
    calendar_id: str = "",
    calendar_owner: str = "",
) -> dict:
    """Maak een afspraak aan in de agenda. Dit schrijft direct weg.

    Controleer eerst met list_events of het tijdstip vrij is. Let op: geef je
    genodigden op, dan stuurt Outlook hun meteen een uitnodiging per mail.

    Args:
        subject: de titel van de afspraak (verplicht).
        start: begintijd als JJJJ-MM-DDTUU:MM, bijvoorbeeld 2026-08-20T09:00.
        end: eindtijd; leeg = start plus duration_minutes.
        duration_minutes: duur in minuten als er geen end is (standaard 60).
        location: locatie, bijvoorbeeld 'Praktijk het Bospad, Wezep'.
        body: toelichting in de afspraak.
        attendees: e-mailadressen die een uitnodiging krijgen. Laat leeg voor
            een afspraak alleen in je eigen agenda.
        reminder_minutes: herinnering zoveel minuten vooraf; -1 zet hem uit.
        all_day: hele dag; start en end zijn dan datums zonder tijd.
        show_as: free, tentative, busy, oof, workingElsewhere. Leeg = busy.
        timezone: afwijkende tijdzone, standaard die uit .env (Europe/Amsterdam).
        calendar_id: id van een specifieke agenda; leeg = je hoofdagenda.
        calendar_owner: e-mailadres van de eigenaar bij een gedeelde agenda.
    """
    if not subject.strip():
        raise ValueError("subject ontbreekt: geef de afspraak een titel.")

    payload = _bouw_afspraak(
        subject=subject,
        start=start,
        end=end,
        duration_minutes=duration_minutes,
        location=location,
        body=body,
        attendees=attendees,
        reminder_minutes=reminder_minutes,
        all_day=all_day,
        show_as=show_as,
        timezone=timezone,
    )
    aangemaakt = client().maak_afspraak(
        payload, agenda_id=calendar_id, eigenaar=calendar_owner
    )
    return {
        "aangemaakt": True,
        "uitnodigingVerstuurd": bool(payload.get("attendees")),
        "afspraak": _kort(aangemaakt),
    }


@mcp.tool()
async def update_event(
    event_id: str,
    subject: str = "",
    start: str = "",
    end: str = "",
    duration_minutes: int = 0,
    location: str = "",
    body: str = "",
    reminder_minutes: int | None = None,
    show_as: str = "",
    timezone: str = "",
    calendar_owner: str = "",
) -> dict:
    """Wijzig een bestaande afspraak. Alleen wat je meegeeft verandert.

    Args:
        event_id: het id uit list_events of create_event.
        subject: nieuwe titel.
        start: nieuwe begintijd als JJJJ-MM-DDTUU:MM.
        end: nieuwe eindtijd. Verzet je alleen start, geef dan end of
            duration_minutes mee, anders blijft de oude eindtijd staan.
        duration_minutes: nieuwe duur in minuten, gerekend vanaf start.
        location: nieuwe locatie.
        body: nieuwe toelichting.
        reminder_minutes: nieuwe herinnering in minuten vooraf; -1 zet hem uit.
        show_as: free, tentative, busy, oof, workingElsewhere.
        timezone: tijdzone voor nieuwe tijden; standaard die uit .env.
        calendar_owner: e-mailadres van de eigenaar bij een gedeelde agenda.
    """
    zone = (timezone or "").strip() or config().timezone
    wijziging: dict = {}

    if subject:
        wijziging["subject"] = subject
    if location:
        wijziging["location"] = {"displayName": location}
    if body:
        wijziging["body"] = {"contentType": "text", "content": body}
    if show_as:
        wijziging["showAs"] = show_as
    if reminder_minutes is not None:
        wijziging["isReminderOn"] = reminder_minutes >= 0
        if reminder_minutes >= 0:
            wijziging["reminderMinutesBeforeStart"] = int(reminder_minutes)

    if start:
        begint = _tijdstip(start, "start")
        wijziging["start"] = _graph_tijd(begint, zone)
        if end:
            wijziging["end"] = _graph_tijd(_tijdstip(end, "end"), zone)
        elif duration_minutes > 0:
            wijziging["end"] = _graph_tijd(begint + timedelta(minutes=duration_minutes), zone)
    elif end:
        wijziging["end"] = _graph_tijd(_tijdstip(end, "end"), zone)
    elif duration_minutes > 0:
        # Zonder nieuwe start rekenen we de duur vanaf de bestaande begintijd.
        huidig = client().afspraak(event_id, eigenaar=calendar_owner)
        ruw = (huidig.get("start") or {}).get("dateTime") or ""
        begint = _tijdstip(ruw[:19], "start")
        wijziging["end"] = _graph_tijd(begint + timedelta(minutes=duration_minutes), zone)

    if not wijziging:
        raise ValueError("Geef minstens één veld op dat gewijzigd moet worden.")

    gewijzigd = client().wijzig_afspraak(event_id, wijziging, eigenaar=calendar_owner)
    return {"gewijzigd": True, "velden": sorted(wijziging), "afspraak": _kort(gewijzigd)}


@mcp.tool()
async def delete_event(event_id: str, calendar_owner: str = "") -> dict:
    """Verwijder een afspraak uit de agenda. Dit is niet ongedaan te maken.

    Vraag de gebruiker eerst om akkoord, en laat zien om welke afspraak het
    gaat: haal hem op met get_event voordat je verwijdert.

    Args:
        event_id: het id uit list_events of create_event.
        calendar_owner: e-mailadres van de eigenaar bij een gedeelde agenda.
    """
    # Eerst ophalen, zodat we in het antwoord kunnen tonen wat er weg is.
    try:
        verdwijnt = _kort(client().afspraak(event_id, eigenaar=calendar_owner))
    except GraphError:
        verdwijnt = {"id": event_id}
    client().verwijder_afspraak(event_id, eigenaar=calendar_owner)
    return {"verwijderd": True, "afspraak": verdwijnt}


@mcp.resource("outlook-agenda://werkwijze")
async def werkwijze() -> str:
    return (
        "Afspraak zetten in Outlook:\n"
        "1. check_connection als je niet zeker weet of het inloggen nog werkt.\n"
        "2. list_events voor de dag in kwestie, om te zien of het tijdstip vrij is.\n"
        "3. create_event met onderwerp, start en duur (of eind).\n"
        "4. Het id uit het antwoord bewaren; daarmee kun je later update_event\n"
        "   of delete_event gebruiken.\n"
        "Genodigden opgeven betekent dat Outlook hun een uitnodiging mailt.\n"
        "Alleen create_event, update_event en delete_event schrijven in de agenda."
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
