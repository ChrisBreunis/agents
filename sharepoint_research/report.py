"""Bouwt een rapportage (Markdown) uit het manifest + geëxtraheerde tekst.

Levert op:
  - output/rapportage.md  met:
      1. Verantwoording / methode
      2. Bronregister (alle bestanden + volledige bronvermelding)
      3. Chronologische tijdlijn (datums uit metadata én uit de tekst),
         elke regel met bronverwijzing [nr] naar het bronregister.

Substantieve duiding (wie deed wat, waarom relevant) is bewust NIET
automatisch ingevuld: dat is mensenwerk / analyse. De tijdlijn en het
bronregister vormen de feitelijke, herleidbare basis daarvoor.

Gebruik:  python report.py
"""
from __future__ import annotations

import json
import re
from collections import namedtuple
from pathlib import Path

from paths import load_paths

MAANDEN = {
    "januari": 1, "februari": 2, "maart": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "augustus": 8, "september": 9, "oktober": 10, "november": 11,
    "december": 12,
}

RE_NUM = re.compile(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b")
RE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
RE_TEXT = re.compile(
    r"\b(\d{1,2})\s+(" + "|".join(MAANDEN) + r")\s+(\d{4})\b", re.IGNORECASE
)

Event = namedtuple("Event", "date nr naam url bron context")


def _valid(y: int, m: int, d: int) -> bool:
    return 1900 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31


def _snippet(text: str, start: int, end: int, width: int = 90) -> str:
    s = max(0, start - width)
    e = min(len(text), end + width)
    return re.sub(r"\s+", " ", text[s:e]).strip()


def dates_in_text(text: str) -> list[tuple[str, str]]:
    """Geef (iso-datum, context-snippet) terug voor elke datum in de tekst."""
    found: list[tuple[str, str]] = []
    for m in RE_ISO.finditer(text):
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
        if _valid(y, mo, d):
            found.append((f"{y:04d}-{mo:02d}-{d:02d}", _snippet(text, *m.span())))
    for m in RE_NUM.finditer(text):
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
        if _valid(y, mo, d):
            found.append((f"{y:04d}-{mo:02d}-{d:02d}", _snippet(text, *m.span())))
    for m in RE_TEXT.finditer(text):
        d, mo, y = int(m[1]), MAANDEN[m[2].lower()], int(m[3])
        if _valid(y, mo, d):
            found.append((f"{y:04d}-{mo:02d}-{d:02d}", _snippet(text, *m.span())))
    return found


def _bron_url(f: dict) -> str:
    # Werkt voor zowel de lokale flow (bron_url) als de Graph-flow (sharepoint_url).
    return f.get("bron_url") or f.get("sharepoint_url") or ""


def build_report(paths) -> Path:
    manifest_path = paths.manifest_path
    if not manifest_path.exists():
        raise SystemExit("manifest.json niet gevonden. Draai eerst: python local_ingest.py")

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = data["bestanden"]

    events: list[Event] = []
    for f in files:
        nr, naam, url = f["nr"], f["naam"], _bron_url(f)
        # 1) metadata-datums (altijd betrouwbaar herleidbaar)
        if f.get("aangemaakt"):
            events.append(Event(f["aangemaakt"][:10], nr, naam, url,
                                "metadata: aangemaakt", f"Document aangemaakt door {f.get('aangemaakt_door')}"))
        if f.get("gewijzigd"):
            events.append(Event(f["gewijzigd"][:10], nr, naam, url,
                                "metadata: gewijzigd", f"Laatst gewijzigd door {f.get('gewijzigd_door')}"))
        # 2) datums die in de inhoud genoemd worden
        tekst_bestand = Path(f["tekst_bestand"])
        if tekst_bestand.exists():
            text = tekst_bestand.read_text(encoding="utf-8", errors="replace")
            for iso, ctx in dates_in_text(text):
                events.append(Event(iso, nr, naam, url, "in tekst genoemd", ctx))

    events.sort(key=lambda e: e.date)

    # ── Markdown opbouwen ────────────────────────────────────────────────
    out = []
    out.append("# Rapportage raadsonderzoek — feitenbasis en tijdlijn\n")
    out.append("## 1. Verantwoording\n")
    bron_omschrijving = data.get("invoermap") or data.get("site_url") or data.get("bron", "")
    out.append(
        f"- **Bron:** {bron_omschrijving}\n"
        f"- **Verwerkt op:** {data['opgehaald_op']}\n"
        f"- **Aantal bestanden:** {data['aantal_bestanden']}\n"
        "- **Methode:** alle bestanden zijn lokaal ingelezen en geëxtraheerd tot "
        "platte tekst. Datums zijn afgeleid uit (a) de bestandsmetadata en (b) datums "
        "die letterlijk in de tekst voorkomen. Elke tijdlijnregel verwijst met `[nr]` "
        "naar het bronregister in paragraaf 3.\n"
        "- **Let op:** dit document bevat de feitelijke, herleidbare basis. "
        "Datums uit de tekst zijn machinaal herkend en moeten bij twijfel handmatig "
        "bij de bron geverifieerd worden.\n"
    )

    out.append("\n## 2. Chronologische tijdlijn\n")
    out.append("| Datum | Gebeurtenis / context | Type | Bron |")
    out.append("|---|---|---|---|")
    for e in events:
        ctx = e.context.replace("|", "\\|")
        out.append(f"| {e.date} | {ctx} | {e.bron} | [{e.nr}] {e.naam} |")

    out.append("\n## 3. Bronregister\n")
    out.append("| Nr | Bestand | Pad | Aangemaakt | Gewijzigd | SHA-256 | Bron |")
    out.append("|---|---|---|---|---|---|---|")
    for f in files:
        url = _bron_url(f)
        link = f"[bestand]({url})" if url else ""
        sha = (f.get("sha256") or "")[:12]
        out.append(
            f"| {f['nr']} | {f['naam']} | `{f['pad']}` | "
            f"{(f.get('aangemaakt') or '')[:10]} | {(f.get('gewijzigd') or '')[:10]} | "
            f"`{sha}` | {link} |"
        )

    # Bestanden die niet (volledig) uitgelezen konden worden, apart benoemen.
    problemen = [f for f in files if f.get("notitie")]
    if problemen:
        out.append("\n## 4. Aandachtspunten bij de bronnen\n")
        for f in problemen:
            out.append(f"- **[{f['nr']}] {f['naam']}** — {f['notitie']}")

    report_path = paths.output_dir / "rapportage.md"
    report_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return report_path


def main() -> None:
    paths = load_paths()
    path = build_report(paths)
    print(f"✓ Rapportage geschreven: {path}")


if __name__ == "__main__":
    main()
