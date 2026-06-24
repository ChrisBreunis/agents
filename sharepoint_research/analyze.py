"""Inhoudelijke duiding door Claude (Anthropic SDK), toegespitst op de
onderzoeksvraag in onderzoeksvraag.md.

Levert twee dingen op in output/duiding.md:
  A. Antwoorden op de vragen van de Jeugdbeschermingstafel (JBT), met bronnen.
  B. Een toetsing van de terugmelding van Stip: per bewering wat de stukken
     tonen, met letterlijk citaat, bronverwijzing [nr] en een classificatie.

Methodische waarborg: er wordt alleen onjuistheid/verdraaiing benoemd waar de
documenten dat daadwerkelijk aantonen. Feit en interpretatie worden gescheiden;
hiaten worden expliciet benoemd. Niets wordt verzonnen.

Vereist een eigen Anthropic API-sleutel:  export ANTHROPIC_API_KEY=sk-ant-...
Draai:  python analyze.py   (nadat local_ingest.py heeft gedraaid)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel

import anthropic
from paths import load_paths

ROL_SYSTEM = (
    "Je bent een ervaren, onafhankelijke onderzoeker in een jeugdbeschermingszaak "
    "(raadsonderzoek / Jeugdbeschermingstafel). Je werkt strikt feitelijk en "
    "verifieerbaar. Kernregels:\n"
    "- Onderscheid altijd expliciet tussen wat een document LETTERLIJK vermeldt en "
    "wat een interpretatie is.\n"
    "- Markeer een bewering pas als 'onjuist', 'verdraaid' of 'weggelaten' als een "
    "concreet document dat aantoont; citeer dan letterlijk en noem de bron [nr].\n"
    "- Benoem onzekerheid en hiaten expliciet; verzin nooit feiten, namen of datums.\n"
    "- Wees evenwichtig: noem ook waar de stukken een bewering juist ondersteunen, "
    "en waar de stelling van betrokkene (nog) niet hard te maken is.\n"
    "- Blijf zakelijk en niet-suggestief; dit kan in een juridische procedure worden gebruikt."
)

MAX_TEKENS_PER_DOC = 60_000
MAX_TEKENS_TERUGMELDING = 40_000


class Passage(BaseModel):
    citaat: str          # letterlijk citaat uit het document
    waarom_relevant: str # waarom dit relevant is voor de onderzoeksvraag


class Gebeurtenis(BaseModel):
    datum: str
    omschrijving: str


class DocAnalyse(BaseModel):
    samenvatting: str
    betrokkenen: list[str]
    gebeurtenissen: list[Gebeurtenis]
    relevantie: str
    kernpassages: list[Passage]  # letterlijke citaten relevant voor de onderzoeksvraag


def _laad_context(paths) -> str:
    p = paths.input_dir.parent / "onderzoeksvraag.md"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return ""


def _vind_terugmelding(context: str, files: list[dict]) -> dict | None:
    """Zoek het terugmeld-document: eerst op expliciete TERUGMELDING_BESTAND-regel,
    anders op een bestandsnaam die in de context wordt genoemd, anders op 'terugmeld'."""
    expliciet = ""
    for line in context.splitlines():
        if line.strip().upper().startswith("TERUGMELDING_BESTAND:"):
            expliciet = line.split(":", 1)[1].strip()
    if expliciet:
        for f in files:
            if f["naam"].lower() == expliciet.lower() or expliciet.lower() in f["naam"].lower():
                return f
    low = context.lower()
    for f in files:
        if f["naam"].lower() in low:
            return f
    for f in files:  # laatste redmiddel: naam bevat 'terugmeld'
        if "terugmeld" in f["naam"].lower():
            return f
    return None


def analyse_document(client, model, f, tekst, context) -> DocAnalyse:
    knip = tekst[:MAX_TEKENS_PER_DOC]
    afgekapt = "\n\n[NB: tekst afgekapt voor analyse]" if len(tekst) > MAX_TEKENS_PER_DOC else ""
    prompt = (
        f"ONDERZOEKSCONTEXT:\n{context}\n\n"
        f"DOCUMENT [{f['nr']}]: {f['naam']}\n"
        f"Pad: {f['pad']}  |  Aangemaakt: {f.get('aangemaakt')}  |  Gewijzigd: {f.get('gewijzigd')}\n\n"
        f"INHOUD:\n{knip}{afgekapt}\n\n"
        "Analyseer dit document feitelijk in het licht van de onderzoekscontext. "
        "Vul de velden in. Neem in 'kernpassages' alleen LETTERLIJKE citaten op die "
        "relevant zijn voor de onderzoeksvraag (bijv. uitspraken over vader, contact, "
        "veiligheid, het veiligheidsplan, de focus op moeder, of het 'beter gaan'). "
        "Noem bij gebeurtenissen alleen datums die letterlijk in de tekst of metadata staan."
    )
    resp = client.messages.parse(
        model=model, max_tokens=4000, system=ROL_SYSTEM,
        messages=[{"role": "user", "content": prompt}], output_format=DocAnalyse,
    )
    return resp.parsed_output


def synthese(client, model, per_doc, context, terugmelding_tekst, terugmelding_nr) -> str:
    materiaal = json.dumps(per_doc, ensure_ascii=False, indent=2)
    tm_blok = ""
    if terugmelding_tekst:
        tm_blok = (
            f"\nVOLLEDIGE TEKST VAN DE TERUGMELDING [{terugmelding_nr}] (te toetsen):\n"
            f"{terugmelding_tekst[:MAX_TEKENS_TERUGMELDING]}\n"
        )
    prompt = (
        f"ONDERZOEKSCONTEXT:\n{context}\n\n"
        f"PER-DOCUMENT ANALYSES (met letterlijke kernpassages):\n{materiaal}\n"
        f"{tm_blok}\n"
        "Schrijf een onderbouwing in het Nederlands, in Markdown, met exact deze delen:\n\n"
        "## A. Antwoorden op de vragen van de Jeugdbeschermingstafel\n"
        "Vind de JBT-vragen in de onderzoekscontext of in de documenten. Som ze op en "
        "beantwoord elke vraag puntsgewijs, uitsluitend onderbouwd met de stukken "
        "(`[nr]` + waar nuttig een kort letterlijk citaat). Staat een antwoord niet in "
        "de stukken, zeg dat dan expliciet.\n\n"
        "## B. Toetsing van de terugmelding van Stip\n"
        "Maak een tabel met kolommen: | Bewering in de terugmelding | Wat de stukken tonen "
        "(met citaat) | Bron [nr] | Classificatie |. Gebruik als classificatie één van: "
        "ONDERSTEUND / DEELS ONDERSTEUND / NIET ONDERSTEUND / WEERSPROKEN / NIET VERIFIEERBAAR. "
        "Behandel in elk geval de bewering dat het 'beter gaat sinds vader in beeld is'.\n\n"
        "## C. Onjuistheden, weglatingen en verschoven focus\n"
        "Benoem alleen wat de documenten daadwerkelijk aantonen: feitelijke onjuistheden, "
        "weggelaten informatie, en of de focusverschuiving naar moeder uit de stukken blijkt. "
        "Scheid feit en interpretatie strikt; citeer letterlijk.\n\n"
        "## D. Feitelijke ankers\n"
        "Vat de harde, herleidbare feiten samen: de voorlopige voorziening (geen contact) en "
        "het verstreken termijn van het veiligheidsplan — met datums en bron [nr] waar bekend.\n\n"
        "## E. Wat (nog) niet uit de stukken blijkt\n"
        "Eerlijke opsomming van hiaten en punten waar de stelling van betrokkene nog niet "
        "met de stukken te onderbouwen is.\n\n"
        "Verwijs bij ELKE feitelijke bewering met `[nr]`. Verzin niets. Begin direct met deel A."
    )
    with client.messages.stream(
        model=model, max_tokens=32000,
        thinking={"type": "adaptive"}, output_config={"effort": "high"},
        system=ROL_SYSTEM, messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
        final = stream.get_final_message()
    print()
    return "".join(b.text for b in final.content if b.type == "text")


def main() -> None:
    paths = load_paths()
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "ANTHROPIC_API_KEY niet gezet. Zet je eigen sleutel:\n"
            "  export ANTHROPIC_API_KEY=sk-ant-...\n(of zet hem in .env) en draai opnieuw."
        )
    if not paths.manifest_path.exists():
        raise SystemExit("manifest.json niet gevonden. Draai eerst: python local_ingest.py")

    data = json.loads(paths.manifest_path.read_text(encoding="utf-8"))
    files = data["bestanden"]
    bron = data.get("invoermap") or data.get("bron", "lokale map")

    context = _laad_context(paths)
    if not context:
        print("⚠  onderzoeksvraag.md niet gevonden — analyse draait zonder gerichte context.")

    client = anthropic.Anthropic()
    model = paths.llm_model
    analyse_dir = paths.output_dir / "analyse"
    analyse_dir.mkdir(parents=True, exist_ok=True)

    terugmelding = _vind_terugmelding(context, files)
    if terugmelding:
        print(f"→ Terugmelding herkend als [{terugmelding['nr']}] {terugmelding['naam']}")
    else:
        print("⚠  Geen terugmeld-document herkend. Vul TERUGMELDING_BESTAND in onderzoeksvraag.md "
              "of zorg dat de bestandsnaam in de context staat. De toetsing gebeurt dan op basis "
              "van alle stukken.")

    per_doc: list[dict] = []
    terugmelding_tekst = ""
    print(f"\n→ Per document analyseren met {model} ...")
    for f in files:
        tekst_bestand = Path(f["tekst_bestand"])
        tekst = tekst_bestand.read_text(encoding="utf-8", errors="replace") if tekst_bestand.exists() else ""
        if terugmelding and f["nr"] == terugmelding["nr"]:
            terugmelding_tekst = tekst
        if not tekst.strip():
            print(f"  [{f['nr']:04d}] {f['naam']} — overgeslagen (geen tekst: {f.get('notitie')})")
            per_doc.append({"nr": f["nr"], "naam": f["naam"], "analyse": {
                "samenvatting": f"Geen tekst beschikbaar: {f.get('notitie')}",
                "betrokkenen": [], "gebeurtenissen": [], "relevantie": "onbekend", "kernpassages": []}})
            continue
        try:
            analyse = analyse_document(client, model, f, tekst, context)
            per_doc.append({"nr": f["nr"], "naam": f["naam"], "analyse": analyse.model_dump()})
            (analyse_dir / f"{f['nr']:04d}.json").write_text(
                analyse.model_dump_json(indent=2), encoding="utf-8")
            print(f"  [{f['nr']:04d}] {f['naam']} — geanalyseerd")
        except anthropic.APIStatusError as exc:
            print(f"  [{f['nr']:04d}] {f['naam']} — API-fout: {exc.status_code} {exc.message}")
            per_doc.append({"nr": f["nr"], "naam": f["naam"], "analyse": {
                "samenvatting": f"Analyse mislukt: {exc.message}",
                "betrokkenen": [], "gebeurtenissen": [], "relevantie": "onbekend", "kernpassages": []}})

    print("\n→ Onderbouwing opstellen (JBT-antwoorden + toetsing terugmelding) ...\n")
    tm_nr = terugmelding["nr"] if terugmelding else None
    verhaal = synthese(client, model, per_doc, context, terugmelding_tekst, tm_nr)

    duiding_path = paths.output_dir / "duiding.md"
    header = (
        "# Onderbouwing t.b.v. raadsonderzoek en Jeugdbeschermingstafel\n\n"
        f"_Bron: {bron} — {len(files)} documenten. Opgesteld met {model}._\n"
        "_Verwijzingen `[nr]` verwijzen naar het bronregister in `rapportage.md` (paragraaf 3)._\n\n"
        "> **Let op:** dit is beslissingsondersteuning op basis van de aangeleverde stukken, "
        "geen juridisch advies. Controleer elk punt bij de bron en laat het nakijken door een "
        "jeugdrechtadvocaat voordat je het in de procedure gebruikt.\n\n---\n\n"
    )
    duiding_path.write_text(header + verhaal + "\n", encoding="utf-8")
    print(f"\n✓ Onderbouwing geschreven: {duiding_path}")
    print(f"  Analyse per document: {analyse_dir}/")


if __name__ == "__main__":
    main()
