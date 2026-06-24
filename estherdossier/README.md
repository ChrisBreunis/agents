# Estherdossier

Leest **alle** documenten uit een lokale map, maakt een **feitelijke tijdlijn met
bronvermelding**, en laat **Claude een inhoudelijke duiding** schrijven waarin elke
bewering met `[nr]` naar het bronregister verwijst. Geen SharePoint, geen Microsoft
Graph, geen login — jij zet de map met bestanden klaar en draait één commando.

```
input_documenten/  ──►  local_ingest.py  ──►  report.py   ──►  rapportage.md   (feiten + tijdlijn)
   (jouw ±50 docs)        (tekst + bronregister)   analyze.py  ──►  duiding.md      (inhoudelijke analyse)
```

---

## Stap 1 — Documenten klaarzetten

Zet je bestanden hier neer (submappen mogen — alles wordt recursief doorzocht):

```
input_documenten/
```

Ondersteund: `.docx`, `.pdf`, `.xlsx`, `.pptx`, `.rtf`, `.txt`, `.csv`, `.md`, `.log`.

## Stap 2 — Installeren op je laptop

```bash
git clone https://github.com/ChrisBreunis/Estherdossier.git
cd Estherdossier
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e .
```

Daarna kun je de tool overal aanroepen met het commando `estherdossier`
(equivalent aan `python run.py`). Draai het vanuit de projectmap, zodat
`input_documenten/` en `onderzoeksvraag.md` worden gevonden.

## Stap 3 — API-sleutel voor de duiding

De feitelijke tijdlijn werkt zonder sleutel. Voor de **inhoudelijke duiding** door
Claude heb je je eigen Anthropic-sleutel nodig:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

(of zet hem in `.env` — kopieer eerst `.env.example` naar `.env`).

## Stap 3b — Onderzoeksvraag scherpstellen (aanbevolen)

Bewerk `onderzoeksvraag.md`. Daarin staat de situatieschets en stuur je de
inhoudelijke analyse:

- Vul bij `TERUGMELDING_BESTAND:` de exacte bestandsnaam van de terugmelding in
  (zoals die in `input_documenten/` staat). Dan toetst de analyse de beweringen
  daarin **woord voor woord** tegen de overige stukken.
- Plak desgewenst de letterlijke **JBT-vragen** (of laat leeg — dan zoekt de
  analyse ze op in de documenten).

`analyze.py` levert dan in `duiding.md`: **(A)** antwoorden op de JBT-vragen met
bronnen, en **(B)** een toetsingstabel van de terugmelding — per bewering wat de
stukken tonen, met letterlijk citaat, bron `[nr]` en classificatie
(ondersteund / weersproken / niet verifieerbaar, enz.).

## Stap 4 — Alles in één keer draaien

```bash
python run.py
```

Dit doet achter elkaar:

1. **`local_ingest.py`** — leest elk bestand uit → `output/tekst/` + `output/manifest.json` (bronregister)
2. **`report.py`** — `output/rapportage.md` met chronologische tijdlijn + bronregister
3. **`analyze.py`** — `output/duiding.md` met de inhoudelijke analyse van Claude (alleen als de sleutel is gezet)

> Liever stap voor stap? `python local_ingest.py` → `python report.py` → `python analyze.py`.

---

## Wat je krijgt in `output/`

| Bestand | Inhoud |
|---|---|
| `manifest.json`  | **Bronregister**: per bestand naam, pad, datums, grootte, **SHA-256**, `file://`-link |
| `tekst/`         | Per document de geëxtraheerde platte tekst |
| `rapportage.md`  | **Feiten**: verantwoording, chronologische tijdlijn (`[nr]`-verwijzingen), bronregister, aandachtspunten |
| `duiding.md`     | **Inhoud**: bevindingen, chronologisch verhaal, openstaande vragen — elke bewering met `[nr]` |
| `analyse/NNNN.json` | Per document de gestructureerde analyse (samenvatting, betrokkenen, gebeurtenissen, relevantie) |

## Twee niveaus, bewust gescheiden

- **Feitelijke basis** (`rapportage.md`) is machinaal en volledig herleidbaar: datums uit
  bestandsmetadata én datums die letterlijk in de tekst staan, elk gekoppeld aan een bron.
- **Inhoudelijke duiding** (`duiding.md`) is door Claude geschreven (model `claude-opus-4-8`,
  met *adaptive thinking*). De raadsonderzoeker-rol is zo ingesteld dat er onderscheid wordt
  gemaakt tussen feit en interpretatie, onzekerheid expliciet wordt benoemd, en er niets wordt
  verzonnen. **Controleer bevindingen altijd bij de bron** voordat je ze in een onderzoek gebruikt.

## Zorgvuldigheid

- `.env`, `output/` en `input_documenten/` (jouw documenten) staan in `.gitignore` en worden
  **nooit** gecommit.
- Het bronregister legt per bron de volledige herkomst vast (pad, datums, SHA-256-hash), zodat
  elk feit herleidbaar en verifieerbaar blijft.
- Gescande PDF's zonder tekstlaag leveren geen tekst op; die worden in `rapportage.md` onder
  *Aandachtspunten* gemarkeerd (OCR nodig).

---

## Configuratie (`.env`, optioneel)

| Variabele          | Standaard            | Betekenis |
|--------------------|----------------------|-----------|
| `ANTHROPIC_API_KEY`| —                    | Jouw Anthropic-sleutel (nodig voor `analyze.py`) |
| `INPUT_DIR`        | `input_documenten`   | Map met je documenten |
| `OUTPUT_DIR`       | `output`             | Map voor resultaten |
| `LLM_MODEL`        | `claude-opus-4-8`    | Claude-model voor de duiding |

## Optioneel: tóch via SharePoint/Microsoft Graph

Wil je later alsnog rechtstreeks koppelen i.p.v. lokaal? De bestanden `auth.py`,
`graph_client.py`, `config.py` en `fetch.py` bevatten de device-code-login-route
(zie de `SP_*`-variabelen in `.env.example`). Die produceert hetzelfde `manifest.json`,
waarna `report.py` en `analyze.py` identiek werken.
