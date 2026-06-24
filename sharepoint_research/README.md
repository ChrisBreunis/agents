# SharePoint-bibliotheek uitlezen voor raadsonderzoek

Koppelt met een SharePoint-documentbibliotheek, leest **alle** bestanden uit en
maakt een **rapportage met tijdlijn en bronvermelding**. Je logt in met je eigen
account (device-code), dus je leest precies de bestanden waar jij toegang toe hebt.

```
┌──────────┐   device-code login   ┌──────────────┐   download + extract   ┌─────────────┐
│ jij/PC   │ ────────────────────▶ │ Microsoft     │ ─────────────────────▶ │ output/     │
│          │                       │ Graph (SharePt)│                        │ manifest +  │
│          │ ◀──────────────────── │               │                        │ tekst + md  │
└──────────┘     code in browser    └──────────────┘                        └─────────────┘
```

## Wat je krijgt

- `output/documenten/`  – de gedownloade originelen
- `output/tekst/`       – per document de geëxtraheerde platte tekst
- `output/manifest.json`– **bronregister**: per bestand naam, pad, SharePoint-URL, datums, auteur, hash
- `output/rapportage.md`– rapportage met **chronologische tijdlijn** en bronverwijzingen

---

## Stap 1 — Azure AD app-registratie (eenmalig, ±5 min)

Device-code login heeft een *public client* app-registratie nodig (geen secret).

1. Ga naar [entra.microsoft.com](https://entra.microsoft.com) → **Identity** →
   **Applications** → **App registrations** → **New registration**.
2. Naam: bv. `Raadsonderzoek-uitlezer`. Supported account types: *Single tenant*.
   Redirect URI: leeg laten. → **Register**.
3. Noteer op de overzichtspagina de **Application (client) ID** en de
   **Directory (tenant) ID**.
4. Ga naar **Authentication** → onder *Advanced settings* zet
   **Allow public client flows** op **Yes** → **Save**.
5. Ga naar **API permissions** → **Add a permission** → **Microsoft Graph** →
   **Delegated permissions** → voeg toe: `Sites.Read.All` en `Files.Read.All`.
   Klik daarna op **Grant admin consent** (of laat een beheerder dit doen).

> Geen rechten om dit te doen? Vraag een beheerder de app te registreren en
> jou de **client-id** en **tenant-id** te geven.

## Stap 2 — Installeren

```bash
cd sharepoint_research
python -m venv .venv && source .venv/bin/activate   # of: uv venv
pip install -r requirements.txt
```

## Stap 3 — Configureren

```bash
cp .env.example .env
```

Vul in `.env` in:

| Variabele        | Voorbeeld                                              |
|------------------|--------------------------------------------------------|
| `SP_TENANT_ID`   | `contoso.onmicrosoft.com` of de GUID                   |
| `SP_CLIENT_ID`   | de Application (client) ID uit stap 1                  |
| `SP_SITE_URL`    | `https://contoso.sharepoint.com/sites/Raadsonderzoek`  |
| `SP_LIBRARY_NAME`| `Documenten` (leeg = standaardbibliotheek van de site) |

> De site-URL vind je door in de browser naar de SharePoint-site te gaan; alles
> t/m `/sites/<naam>` is de site-URL. De bibliotheeknaam staat links in het menu.

## Stap 4 — Uitlezen

```bash
python fetch.py
```

Er verschijnt een melding als:

```
To sign in, use a web browser to open https://microsoft.com/devicelogin
and enter the code ABCD-EFGH to authenticate.
```

Open die URL, voer de code in, log in met je eigen account. Daarna worden alle
bestanden geïnventariseerd, gedownload en uitgelezen. Het token wordt gecachet
(`.token_cache.json`), dus de volgende keer hoef je meestal niet opnieuw in te loggen.

## Stap 5 — Rapportage maken

```bash
python report.py
```

Opent: `output/rapportage.md` — bronregister + chronologische tijdlijn.

---

## Ondersteunde bestandstypen

`.docx`, `.pdf`, `.xlsx`, `.pptx`, `.rtf`, `.txt`, `.csv`, `.md`, `.log`.

Gescande PDF's (beeld zonder tekstlaag) leveren geen tekst op; die worden in de
rapportage onder *Aandachtspunten* gemarkeerd (OCR is dan nodig). Oude `.doc`/
`.xls`/`.ppt` (binair) worden niet ondersteund — converteer ze naar het nieuwe
formaat of voeg een extractor toe.

## Veiligheid & zorgvuldigheid (raadsonderzoek)

- `.env` en `.token_cache.json` staan in `.gitignore` en worden **nooit** gecommit.
- Het token geeft alleen leesrechten (`*.Read.All`) — er wordt niets gewijzigd in SharePoint.
- Het `manifest.json` legt per bron de **volledige herkomst** vast (pad, URL, datums,
  auteur, hash) zodat elk feit in de rapportage herleidbaar en verifieerbaar is.
- Datums uit de tekst worden machinaal herkend; controleer bij twijfel altijd bij de bron.
