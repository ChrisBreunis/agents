# Outlook-agenda MCP-server

Laat Claude afspraken lezen, aanmaken, wijzigen en verwijderen in je
Outlook-agenda, via Microsoft Graph en je eigen app-registratie in Entra ID.

Bedoeld als aanvulling op de Microsoft 365-connector van claude.ai: die kan
alleen lezen en zoeken. Deze server kan wél schrijven.

## Wat de server kan

| Tool | Doet | Schrijft |
| --- | --- | --- |
| `check_connection` | Toont met welk account je verbonden bent en welke rechten je hebt | nee |
| `list_calendars` | Je agenda's met hun id | nee |
| `list_events` | Afspraken in een periode | nee |
| `get_event` | Eén afspraak met alle details | nee |
| `create_event` | Nieuwe afspraak aanmaken | **ja** |
| `update_event` | Bestaande afspraak wijzigen | **ja** |
| `delete_event` | Afspraak verwijderen | **ja** |

## Eenmalig instellen

### 1. App-registratie in Entra ID

Ga naar [entra.microsoft.com](https://entra.microsoft.com) → **App-registraties**.
Gebruik een bestaande registratie of maak er een aan (**Nieuwe registratie**,
account type "Alleen accounts in deze organisatiemap").

Noteer van het tabblad **Overzicht**:

- **Application (client) ID**
- **Directory (tenant) ID**

Dan twee instellingen:

**a. Machtigingen** — ga naar **API-machtigingen** → **Een machtiging toevoegen**
→ **Microsoft Graph** → **Gedelegeerde machtigingen** en voeg toe:

- `Calendars.ReadWrite` — afspraken lezen en aanmaken
- `User.Read` — staat er meestal al
- `Calendars.ReadWrite.Shared` — alleen nodig voor agenda's van anderen

Gedelegeerd, dus niet "Toepassingsmachtigingen": de server werkt namens jou als
ingelogde gebruiker, niet als achtergronddienst met toegang tot de hele tenant.

Klik daarna **Beheerderstoestemming verlenen** als je die knop hebt. Zonder dat
krijgt elke gebruiker bij de eerste keer inloggen zelf een toestemmingsscherm,
wat ook prima werkt.

**b. Openbare clientstromen aanzetten** — ga naar **Verificatie** →
**Geavanceerde instellingen** → zet **Openbare clientstromen toestaan** op
**Ja**. Zonder dit werkt het inloggen met een code niet en krijg je bij
`login.py` de melding dat er geen inlogcode opgevraagd kon worden.

### 2. Instellen en inloggen

```bash
cd outlook_agenda_mcp
cp .env.example .env          # vul OUTLOOK_CLIENT_ID en OUTLOOK_TENANT_ID in
uv sync                       # of: pip install -r requirements.txt
uv run python login.py
```

`login.py` toont een code en een adres (microsoft.com/devicelogin). Voer de code
daar in, log in met je werkaccount en geef toestemming. Dat is eenmalig: daarna
vernieuwt de server het token zelf.

Controleer met:

```bash
uv run python check_setup.py
```

Uitloggen kan met `uv run python login.py --uitloggen`.

### 3. Registreren bij Claude

De server staat al in `.mcp.json` in de hoofdmap van deze repo. Start Claude
Code opnieuw op vanuit die map, dan verschijnen de tools vanzelf.

## Waar je gegevens staan

- **Client-id en tenant-id** staan in `.env`. Geen geheimen, maar `.env` staat
  in `.gitignore` en hoort daar te blijven.
- **Het token** gaat in de kluis van je besturingssysteem (Windows Credential
  Manager, macOS Keychain, Linux Secret Service). Is er geen kluis, dan valt de
  server terug op `.token-cache.json` naast de server, met leesrechten alleen
  voor jezelf. Ook dat bestand staat in `.gitignore`.
- **Wachtwoorden** komen nergens langs: het inloggen gebeurt in je browser bij
  Microsoft zelf.

## In gebruik

Vraag Claude bijvoorbeeld:

> Zet donderdag 20 augustus om 9:00 een afspraak van een uur met de psycholoog
> in mijn agenda, locatie Praktijk het Bospad in Wezep.

Wat er dan gebeurt: eerst `list_events` om te zien of het tijdstip vrij is, dan
`create_event`. Je krijgt het id van de afspraak terug, waarmee later
`update_event` of `delete_event` kan.

Twee dingen om te weten:

- **Genodigden betekent uitnodigingen.** Geef je bij `create_event` adressen mee
  in `attendees`, dan mailt Outlook die mensen meteen. Laat het veld leeg voor
  een afspraak die alleen in je eigen agenda staat.
- **`delete_event` is definitief.** De afspraak wordt niet geannuleerd maar
  verwijderd. Laat Claude eerst tonen om welke afspraak het gaat.

## Tijden opgeven

Tijden gaan als `JJJJ-MM-DDTUU:MM`, bijvoorbeeld `2026-08-20T09:00`. Een spatie
in plaats van de T mag ook. Zonder tijdzone geldt de zone uit `.env`
(standaard `Europe/Amsterdam`); zomer- en wintertijd rekent Graph zelf om.

Voor een afspraak van een hele dag: `all_day=true` en datums zonder tijd. Het
eind is dan de laatste dag zelf, niet de dag erna — de server rekent dat om naar
wat Graph verwacht.

## Als er iets misgaat

| Melding | Wat er aan de hand is |
| --- | --- |
| `Nog niet ingelogd bij Microsoft` | Draai `python login.py` |
| `Kon geen inlogcode opvragen` | "Openbare clientstromen toestaan" staat nog op Nee |
| `Calendars.ReadWrite zit niet in het token` | Machtiging ontbreekt in Entra ID, of je moet na het toevoegen opnieuw inloggen |
| Graph geeft `403` | Ingelogd, maar zonder de benodigde rechten |
| Graph geeft `404` op een event-id | De afspraak bestaat niet meer, of staat in een andere agenda |

Na het toevoegen van een machtiging in Entra ID moet je altijd opnieuw
inloggen: het bestaande token blijft anders op de oude rechten hangen.
