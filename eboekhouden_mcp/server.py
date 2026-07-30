"""MCP-server voor verkoopfacturen in e-Boekhouden.nl.

Werkwijze: zoek de relatie, stel een concept samen met prepare_invoice, laat
dat concept aan de gebruiker zien en boek het pas na akkoord met create_invoice.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as Server  # noqa: E402
except ImportError:  # mcp 2.x noemt dezelfde klasse MCPServer
    from mcp.server.mcpserver import MCPServer as Server  # noqa: E402

from btw import bereken_totalen, beschrijf_btw_codes, btw_percentage  # noqa: E402
from client import EBoekhoudenClient, EBoekhoudenError  # noqa: E402
from config import Config, ConfigError, load_config  # noqa: E402
from drafts import ConceptStore  # noqa: E402

mcp = Server("eboekhouden")
concepten = ConceptStore()

_client: EBoekhoudenClient | None = None
_config: Config | None = None


def client() -> EBoekhoudenClient:
    """Client bij eerste gebruik opzetten, zodat een ontbrekende .env pas bij
    de eerste tool-aanroep een duidelijke fout geeft."""
    global _client, _config
    if _client is None:
        _config = load_config()
        _client = EBoekhoudenClient(_config)
    return _client


def config() -> Config:
    client()
    assert _config is not None
    return _config


# ── hulpfuncties ────────────────────────────────────────────────────────
def _matcht(record: dict, zoekterm: str) -> bool:
    """Zoek de term terug in alle tekstvelden van een record. Zo werkt zoeken
    ook als de API andere veldnamen hanteert dan we verwachten."""
    term = zoekterm.lower()
    return any(
        isinstance(waarde, str) and term in waarde.lower() for waarde in record.values()
    )


def _naam(record: dict, standaard: str = "") -> str:
    for sleutel in ("name", "companyName", "description", "code", "title"):
        waarde = record.get(sleutel)
        if isinstance(waarde, str) and waarde:
            return waarde
    return standaard


def _id(record: dict) -> int | None:
    for sleutel in ("id", "relationId", "ledgerId", "templateId", "invoiceId"):
        waarde = record.get(sleutel)
        if isinstance(waarde, int):
            return waarde
    return None


def _normaliseer_regel(regel: dict, index: int, standaard_grootboek: int | None,
                       standaard_btw: str) -> dict:
    """Eén factuurregel omzetten naar de velden die de API verwacht."""
    def pak(*namen, standaard=None):
        for naam in namen:
            if naam in regel and regel[naam] not in (None, ""):
                return regel[naam]
        return standaard

    omschrijving = pak("description", "omschrijving")
    if not omschrijving:
        raise ValueError(f"Regel {index + 1}: 'description' ontbreekt.")

    prijs = pak("price_per_unit", "pricePerUnit", "prijs", "price")
    if prijs is None:
        raise ValueError(
            f"Regel {index + 1}: 'price_per_unit' ontbreekt (bedrag per stuk, excl. btw)."
        )
    try:
        prijs = float(prijs)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Regel {index + 1}: prijs {prijs!r} is geen bedrag.") from exc

    aantal = pak("quantity", "aantal", standaard=1)
    try:
        aantal = float(aantal)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Regel {index + 1}: aantal {aantal!r} is geen getal.") from exc
    if aantal <= 0:
        raise ValueError(f"Regel {index + 1}: aantal moet groter dan 0 zijn.")

    grootboek = pak("ledger_id", "ledgerId", "grootboek", standaard=standaard_grootboek)
    if grootboek is None:
        raise ValueError(
            f"Regel {index + 1}: 'ledger_id' ontbreekt. Zoek de juiste omzetrekening "
            "met list_ledgers, of zet EBOEKHOUDEN_DEFAULT_LEDGER_ID in .env."
        )

    genormaliseerd = {
        "description": str(omschrijving),
        "quantity": int(aantal) if float(aantal).is_integer() else aantal,
        "pricePerUnit": round(prijs, 2),
        "vatCode": str(pak("vat_code", "vatCode", "btw", standaard=standaard_btw)).upper(),
        "ledgerId": int(grootboek),
    }
    eenheid = pak("unit", "eenheid")
    if eenheid:
        genormaliseerd["unit"] = str(eenheid)
    return genormaliseerd


# ── verbinding en opzoeken ──────────────────────────────────────────────
@mcp.tool()
async def check_connection() -> dict:
    """Controleer of de API-sleutel werkt en toon om welke administratie het gaat.

    Draai dit eerst bij twijfel: het maakt geen wijzigingen.
    """
    try:
        administratie = client().administratie()
    except (ConfigError, EBoekhoudenError) as exc:
        return {"ok": False, "melding": str(exc)}
    return {
        "ok": True,
        "administratie": administratie,
        "standaardSjabloon": config().default_template_id,
        "standaardGrootboek": config().default_ledger_id,
        "standaardBtwCode": config().default_vat_code,
        "mailenToegestaan": config().allow_email,
    }


@mcp.tool()
async def list_relations(search: str = "", limit: int = 25) -> list[dict]:
    """Zoek klanten (relaties) in e-Boekhouden.

    Args:
        search: deel van een naam, e-mailadres of plaats. Leeg = de eerste relaties.
        limit: maximaal aantal resultaten (standaard 25).
    """
    gevonden: list[dict] = []
    offset = 0
    for _ in range(20):  # maximaal 20 pagina's doorzoeken
        pagina = client().relaties(limit=100, offset=offset)
        if not pagina:
            break
        for relatie in pagina:
            if not search or _matcht(relatie, search):
                gevonden.append(relatie)
                if len(gevonden) >= limit:
                    return gevonden
        if len(pagina) < 100:
            break
        offset += 100
    return gevonden


@mcp.tool()
async def get_relation(relation_id: int) -> dict:
    """Haal één relatie op met alle bekende velden.

    Args:
        relation_id: het id van de relatie.
    """
    return client().relatie(relation_id)


@mcp.tool()
async def create_relation(
    name: str,
    email: str = "",
    address: str = "",
    postal_code: str = "",
    city: str = "",
    country: str = "",
    phone: str = "",
    vat_number: str = "",
    contact: str = "",
    extra_fields: dict | None = None,
) -> dict:
    """Maak een nieuwe klant aan. Controleer eerst met list_relations of de klant
    al bestaat: dit schrijft direct weg in de administratie.

    Args:
        name: bedrijfs- of klantnaam (verplicht).
        email: e-mailadres voor facturen.
        address: straat en huisnummer.
        postal_code: postcode.
        city: plaats.
        country: land.
        phone: telefoonnummer.
        vat_number: btw-nummer.
        contact: naam van de contactpersoon.
        extra_fields: overige velden die je rechtstreeks aan de API wilt meegeven.
    """
    body: dict = {"name": name}
    for sleutel, waarde in (
        ("email", email),
        ("address", address),
        ("postalCode", postal_code),
        ("city", city),
        ("country", country),
        ("phone", phone),
        ("vatNumber", vat_number),
        ("contact", contact),
    ):
        if waarde:
            body[sleutel] = waarde
    if extra_fields:
        body.update(extra_fields)
    return {"aangemaakt": client().maak_relatie(body), "verzonden": body}


@mcp.tool()
async def list_invoice_templates() -> list[dict]:
    """Toon de factuursjablonen. Een sjabloon-id is verplicht bij het aanmaken
    van een factuur; zet je vaste sjabloon in EBOEKHOUDEN_DEFAULT_TEMPLATE_ID."""
    return client().factuursjablonen()


@mcp.tool()
async def list_ledgers(search: str = "", limit: int = 50) -> list[dict]:
    """Zoek grootboekrekeningen, bijvoorbeeld je omzetrekening.

    Args:
        search: deel van de omschrijving of code, bijvoorbeeld 'omzet'.
        limit: maximaal aantal resultaten.
    """
    alle = client().grootboekrekeningen()
    if search:
        alle = [rek for rek in alle if _matcht(rek, search)]
    return alle[:limit]


@mcp.tool()
async def list_vat_codes() -> list[dict]:
    """Toon de btw-codes voor verkoopfacturen met hun percentage."""
    return beschrijf_btw_codes()


# ── factuur opstellen en boeken ─────────────────────────────────────────
@mcp.tool()
async def prepare_invoice(
    relation_id: int,
    items: list[dict],
    template_id: int | None = None,
    date: str = "",
    term_of_payment: int | None = None,
    reference: str = "",
    invoice_number: str = "",
) -> dict:
    """Stel een conceptfactuur samen en reken de totalen uit. Dit boekt nog niets.

    Laat het concept altijd eerst aan de gebruiker zien en boek het pas na
    akkoord met create_invoice.

    Args:
        relation_id: id van de klant (zoek met list_relations).
        items: factuurregels. Per regel: description, price_per_unit (excl. btw),
            en optioneel quantity (standaard 1), vat_code, ledger_id, unit.
        template_id: id van het factuursjabloon; standaard uit .env.
        date: factuurdatum als JJJJ-MM-DD; leeg laat e-Boekhouden vandaag kiezen.
        term_of_payment: betaaltermijn in dagen.
        reference: referentie of kenmerk voor de klant.
        invoice_number: eigen factuurnummer; leeg laat e-Boekhouden nummeren.
    """
    if not items:
        raise ValueError("Geef minstens één factuurregel mee.")

    cfg = config()
    sjabloon = template_id if template_id is not None else cfg.default_template_id
    if sjabloon is None:
        raise ValueError(
            "template_id ontbreekt. Vraag de sjablonen op met list_invoice_templates "
            "of zet EBOEKHOUDEN_DEFAULT_TEMPLATE_ID in .env."
        )

    regels = [
        _normaliseer_regel(regel, i, cfg.default_ledger_id, cfg.default_vat_code)
        for i, regel in enumerate(items)
    ]

    payload: dict = {"relationId": relation_id, "templateId": sjabloon, "items": regels}
    if date:
        payload["date"] = date
    if term_of_payment is not None:
        payload["termOfPayment"] = term_of_payment
    if reference:
        payload["reference"] = reference
    if invoice_number:
        payload["invoiceNumber"] = invoice_number

    waarschuwingen: list[str] = []
    for regel in regels:
        if btw_percentage(regel["vatCode"]) is None:
            waarschuwingen.append(
                f"Btw-code {regel['vatCode']!r} is hier niet bekend; het btw-bedrag in "
                "dit concept telt die regel als 0%. e-Boekhouden rekent zelf definitief."
            )

    # Namen erbij zoeken, zodat de gebruiker ziet wát er geboekt wordt.
    toelichting: dict = {}
    try:
        relatie = client().relatie(relation_id)
        toelichting["relatie"] = _naam(relatie, f"relatie {relation_id}")
    except EBoekhoudenError as exc:
        waarschuwingen.append(f"Relatie {relation_id} kon niet opgehaald worden: {exc}")
    try:
        sjablonen = client().factuursjablonen()
        gekozen = next((s for s in sjablonen if _id(s) == sjabloon), None)
        if gekozen:
            toelichting["sjabloon"] = _naam(gekozen, str(sjabloon))
    except EBoekhoudenError:
        pass

    totalen = bereken_totalen(regels).as_dict()
    return concepten.nieuw(payload, totalen, toelichting, waarschuwingen).as_dict()


@mcp.tool()
async def create_invoice(
    draft_id: str,
    expected_total_incl_vat: float | None = None,
    email: bool = False,
) -> dict:
    """Boek een eerder voorbereid concept als echte verkoopfactuur in e-Boekhouden.

    Roep dit alleen aan nadat de gebruiker het concept heeft gezien en akkoord is.

    Args:
        draft_id: het conceptId uit prepare_invoice.
        expected_total_incl_vat: optionele controle; wijkt het concepttotaal af,
            dan wordt er niets geboekt.
        email: de factuur direct naar de klant mailen. Vereist
            EBOEKHOUDEN_ALLOW_EMAIL=true in .env.
    """
    concept = concepten.haal(draft_id)

    if expected_total_incl_vat is not None:
        werkelijk = concept.totalen["totaalInclBtw"]
        if abs(werkelijk - float(expected_total_incl_vat)) > 0.01:
            raise ValueError(
                f"Totaal komt niet overeen: concept is € {werkelijk:.2f} incl. btw, "
                f"verwacht was € {float(expected_total_incl_vat):.2f}. Er is niets geboekt."
            )

    if email and not config().allow_email:
        raise ValueError(
            "Mailen staat uit. Zet EBOEKHOUDEN_ALLOW_EMAIL=true in .env als je wilt "
            "dat facturen direct verstuurd mogen worden."
        )

    resultaat = client().maak_factuur(concept.payload, mailen=email)
    concepten.verwijder(draft_id)
    return {
        "geboekt": True,
        "gemaild": email,
        "antwoord": resultaat,
        "concept": concept.payload,
        "totalenConcept": concept.totalen,
    }


@mcp.tool()
async def list_drafts() -> list[dict]:
    """Toon de conceptfacturen die nog op akkoord wachten."""
    return concepten.alles()


@mcp.tool()
async def discard_draft(draft_id: str) -> str:
    """Gooi een conceptfactuur weg zonder te boeken.

    Args:
        draft_id: het conceptId uit prepare_invoice.
    """
    concepten.verwijder(draft_id)
    return f"Concept {draft_id} verwijderd."


# ── terugkijken ─────────────────────────────────────────────────────────
@mcp.tool()
async def list_invoices(limit: int = 25, offset: int = 0) -> list[dict]:
    """Toon eerder aangemaakte facturen.

    Args:
        limit: maximaal aantal facturen.
        offset: hoeveel facturen overslaan (voor bladeren).
    """
    return client().facturen(limit=limit, offset=offset)


@mcp.tool()
async def get_invoice(invoice_id: int) -> dict:
    """Haal één factuur op.

    Args:
        invoice_id: het id van de factuur.
    """
    return client().factuur(invoice_id)


@mcp.resource("eboekhouden://werkwijze")
async def werkwijze() -> str:
    return (
        "Verkoopfactuur maken in e-Boekhouden:\n"
        "1. list_relations om de klant te vinden (of create_relation als die nog niet bestaat).\n"
        "2. list_ledgers voor de omzetrekening en list_vat_codes voor de btw-code.\n"
        "3. prepare_invoice om een concept met totalen te maken.\n"
        "4. Concept aan de gebruiker tonen en om akkoord vragen.\n"
        "5. create_invoice met het conceptId om te boeken.\n"
        "Alleen create_invoice en create_relation schrijven in de administratie."
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
