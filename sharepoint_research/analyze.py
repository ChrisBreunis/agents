"""Inhoudelijke duiding door Claude (Anthropic SDK).

Per document: een gestructureerde analyse (samenvatting, betrokkenen, genoemde
gebeurtenissen, relevantie). Daarna een overkoepelende synthese: een
chronologisch verhaal voor het raadsonderzoek, waarbij elke bewering met `[nr]`
verwijst naar het bronregister uit local_ingest.py.

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
    "Je bent een ervaren, onafhankelijke raadsonderzoeker. Je analyseert documenten "
    "feitelijk en zorgvuldig voor een raadsonderzoek. Je maakt onderscheid tussen wat "
    "een document letterlijk vermeldt en wat een interpretatie is. Je benoemt onzekerheid "
    "expliciet en verzint nooit feiten, namen of datums die niet in de tekst staan."
)

# Tekst per document begrenzen om kosten/contextgebruik beheersbaar te houden.
MAX_TEKENS_PER_DOC = 60_000


class Gebeurtenis(BaseModel):
    datum: str          # ISO (YYYY-MM-DD) of vrije omschrijving als geen exacte datum
    omschrijving: str   # wat er gebeurde, feitelijk


class DocAnalyse(BaseModel):
    samenvatting: str
    betrokkenen: list[str]
    gebeurtenissen: list[Gebeurtenis]
    relevantie: str     # waarom dit document relevant kan zijn voor het onderzoek


def analyse_document(client: anthropic.Anthropic, model: str, f: dict, tekst: str) -> DocAnalyse:
    knip = tekst[:MAX_TEKENS_PER_DOC]
    afgekapt = "\n\n[NB: tekst afgekapt voor analyse]" if len(tekst) > MAX_TEKENS_PER_DOC else ""
    prompt = (
        f"Document [{f['nr']}]: {f['naam']}\n"
        f"Pad: {f['pad']}\n"
        f"Aangemaakt: {f.get('aangemaakt')}  Gewijzigd: {f.get('gewijzigd')}\n\n"
        f"INHOUD:\n{knip}{afgekapt}\n\n"
        "Analyseer dit document feitelijk voor een raadsonderzoek. Vul de velden in. "
        "Noem bij gebeurtenissen alleen datums die letterlijk in de tekst of metadata staan."
    )
    resp = client.messages.parse(
        model=model,
        max_tokens=4000,
        system=ROL_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_format=DocAnalyse,
    )
    return resp.parsed_output


def synthese(client: anthropic.Anthropic, model: str, per_doc: list[dict], bron: str) -> str:
    """Overkoepelend verhaal + tijdlijn met bronverwijzingen [nr]. Streamt."""
    materiaal = json.dumps(per_doc, ensure_ascii=False, indent=2)
    prompt = (
        f"Hieronder staan per document de feitelijke analyses uit de bron: {bron}.\n\n"
        f"{materiaal}\n\n"
        "Schrijf een rapportage voor het raadsonderzoek in het Nederlands, in Markdown, met:\n"
        "1. **Bevindingen** — de belangrijkste, onderbouwde observaties.\n"
        "2. **Chronologisch verhaal** — wat er, voor zover de documenten laten zien, "
        "in welke volgorde is gebeurd.\n"
        "3. **Openstaande vragen / hiaten** — wat de documenten niet beantwoorden.\n\n"
        "Vereisten: verwijs bij ELKE feitelijke bewering met `[nr]` naar het brondocument "
        "(meerdere mag: `[3][7]`). Verzin niets dat niet in de analyses staat. Maak helder "
        "onderscheid tussen feit en interpretatie. Begin met de kern, niet met een inleiding."
    )
    with client.messages.stream(
        model=model,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=ROL_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
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
            "  export ANTHROPIC_API_KEY=sk-ant-...\n"
            "(of zet hem in .env) en draai opnieuw."
        )
    if not paths.manifest_path.exists():
        raise SystemExit("manifest.json niet gevonden. Draai eerst: python local_ingest.py")

    data = json.loads(paths.manifest_path.read_text(encoding="utf-8"))
    files = data["bestanden"]
    bron = data.get("invoermap") or data.get("bron", "lokale map")

    client = anthropic.Anthropic()
    model = paths.llm_model
    analyse_dir = paths.output_dir / "analyse"
    analyse_dir.mkdir(parents=True, exist_ok=True)

    per_doc: list[dict] = []
    print(f"→ Per document analyseren met {model} ...")
    for f in files:
        tekst_bestand = Path(f["tekst_bestand"])
        tekst = tekst_bestand.read_text(encoding="utf-8", errors="replace") if tekst_bestand.exists() else ""
        if not tekst.strip():
            print(f"  [{f['nr']:04d}] {f['naam']} — overgeslagen (geen tekst: {f.get('notitie')})")
            per_doc.append({
                "nr": f["nr"], "naam": f["naam"],
                "analyse": {"samenvatting": f"Geen tekst beschikbaar: {f.get('notitie')}",
                            "betrokkenen": [], "gebeurtenissen": [], "relevantie": "onbekend"},
            })
            continue
        try:
            analyse = analyse_document(client, model, f, tekst)
            per_doc.append({"nr": f["nr"], "naam": f["naam"], "analyse": analyse.model_dump()})
            (analyse_dir / f"{f['nr']:04d}.json").write_text(
                analyse.model_dump_json(indent=2), encoding="utf-8"
            )
            print(f"  [{f['nr']:04d}] {f['naam']} — geanalyseerd")
        except anthropic.APIStatusError as exc:
            print(f"  [{f['nr']:04d}] {f['naam']} — API-fout: {exc.status_code} {exc.message}")
            per_doc.append({"nr": f["nr"], "naam": f["naam"],
                            "analyse": {"samenvatting": f"Analyse mislukt: {exc.message}",
                                        "betrokkenen": [], "gebeurtenissen": [], "relevantie": "onbekend"}})

    print("\n→ Overkoepelende synthese opstellen ...\n")
    verhaal = synthese(client, model, per_doc, bron)

    duiding_path = paths.output_dir / "duiding.md"
    header = (
        "# Inhoudelijke duiding raadsonderzoek\n\n"
        f"_Bron: {bron} — {len(files)} documenten. Opgesteld met {model}._\n"
        "_Verwijzingen `[nr]` verwijzen naar het bronregister in `rapportage.md` (paragraaf 3)._\n\n"
        "---\n\n"
    )
    duiding_path.write_text(header + verhaal + "\n", encoding="utf-8")
    print(f"\n✓ Duiding geschreven: {duiding_path}")
    print(f"  Analyse per document: {analyse_dir}/")


if __name__ == "__main__":
    main()
