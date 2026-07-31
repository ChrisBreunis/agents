# e-Boekhouden MCP-server (verkoopfacturen)

Een MCP-server waarmee je in Claude in gewone taal verkoopfacturen kunt
opstellen en boeken in [e-Boekhouden.nl](https://www.e-boekhouden.nl), via hun
REST API. Er bestaat geen kant-en-klare e-Boekhouden-connector voor Claude;
dit is die koppeling.

Bijvoorbeeld: *"Maak een factuur voor Bakkerij De Korenaar: 10 uur advies à
€ 95, plus € 45,50 reiskosten zonder btw."* Claude zoekt de klant op, stelt een
concept op met totalen, laat dat zien, en boekt het pas als jij akkoord geeft.

## Veiligheid vooraf

- **Twee stappen.** `prepare_invoice` maakt alleen een concept in het geheugen;
  `create_invoice` boekt het pas echt. Zo zie je altijd wat je bevestigt.
- **Mailen staat uit.** Facturen worden niet naar de klant gestuurd tenzij je
  `EBOEKHOUDEN_ALLOW_EMAIL=true` zet.
- **Alleen `create_invoice` en `create_relation` schrijven** in je
  administratie. Alle andere tools zijn puur lezen.
- **Je API-sleutel hoort in `.env`**, die door `.gitignore` buiten git blijft.

## Instellen

1. **API-sleutel maken** in e-Boekhouden: *Beheer → Koppelingen → API → REST
   API → Nieuwe API-sleutel aanmaken*. Geef de sleutel een herkenbare naam
   (bijvoorbeeld "Claude").

2. **Configuratie klaarzetten:**

   ```bash
   cd eboekhouden_mcp
   cp .env.example .env      # vul EBOEKHOUDEN_API_TOKEN in
   ```

3. **Afhankelijkheden installeren** (vanuit de repo-root, die `uv` gebruikt):

   ```bash
   uv sync                                   # of: pip install -r eboekhouden_mcp/requirements.txt
   ```

4. **Verbinding testen:**

   ```bash
   uv run python eboekhouden_mcp/server.py   # start de server; Ctrl-C om te stoppen
   ```

   Start hij zonder fout, dan is de server klaar. De echte controle doe je
   straks in Claude met de tool `check_connection`.

5. **Aan Claude koppelen.**

   In **Claude Code** hoef je niets in te stellen: de repo bevat een
   `.mcp.json` die deze server aanmeldt. Open de repo, bevestig eenmalig dat je
   de projectserver vertrouwt, en controleer met `/mcp` dat `eboekhouden`
   verbonden is. Wil je het toch handmatig:

   ```bash
   claude mcp add eboekhouden -- uv run --directory /pad/naar/agents/eboekhouden_mcp python server.py
   ```

   Claude Desktop — in `claude_desktop_config.json`:

   ```json
   {
     "mcpServers": {
       "eboekhouden": {
         "command": "uv",
         "args": ["run", "--directory", "/pad/naar/agents/eboekhouden_mcp", "python", "server.py"]
       }
     }
   }
   ```

6. **Vaste keuzes vastleggen.** Vraag in Claude één keer
   `list_invoice_templates` en `list_ledgers` op, en zet het sjabloon-id en je
   omzetrekening in `.env` als `EBOEKHOUDEN_DEFAULT_TEMPLATE_ID` en
   `EBOEKHOUDEN_DEFAULT_LEDGER_ID`. Daarna hoef je die per factuur niet meer te
   noemen.

## Beschikbare tools

| Tool | Doel |
| --- | --- |
| `check_connection` | Controleert de sleutel en toont de administratie |
| `list_relations` | Zoekt klanten op naam, e-mail of plaats |
| `get_relation` | Haalt één relatie op |
| `create_relation` | Maakt een nieuwe klant aan *(schrijft)* |
| `list_invoice_templates` | Toont de factuursjablonen |
| `list_ledgers` | Zoekt grootboekrekeningen, bijv. je omzetrekening |
| `list_vat_codes` | Toont de btw-codes voor verkoop |
| `prepare_invoice` | Stelt een concept op met totalen — boekt niets |
| `create_invoice` | Boekt een concept als echte factuur *(schrijft)* |
| `list_drafts` / `discard_draft` | Concepten bekijken of weggooien |
| `list_invoices` / `get_invoice` | Eerdere facturen terugzien |

Een factuurregel voor `prepare_invoice` ziet er zo uit:

```json
{"description": "Advies mei", "quantity": 10, "price_per_unit": 95,
 "vat_code": "HOOG_VERK_21", "ledger_id": 8000}
```

Alleen `description` en `price_per_unit` (excl. btw) zijn verplicht; `quantity`
is standaard 1 en `vat_code`/`ledger_id` komen uit `.env` als je ze weglaat.

`create_invoice` accepteert optioneel `expected_total_incl_vat`. Wijkt het
concepttotaal daarvan af, dan wordt er niets geboekt — een extra slot op de
deur als je een bedrag hebt afgesproken.

## Goed om te weten

- **De totalen in een concept zijn indicatief.** e-Boekhouden berekent de btw
  zelf en die uitkomst is leidend; het concept is bedoeld om te controleren wat
  je boekt, niet als btw-aangifte.
- **Onbekende btw-code?** Dan telt die regel in het *concept* als 0% en krijg je
  een waarschuwing. De factuur zelf gaat gewoon met jouw code naar
  e-Boekhouden.
- **Waar `.env` staat.** De server zoekt `.env` naast zichzelf (in
  `eboekhouden_mcp/`), ongeacht vanuit welke map hij gestart wordt. Staat daar
  geen `.env`, dan valt hij terug op de werkmap en hoger.
- **Authenticatie.** De server haalt met je API-sleutel een sessietoken op en
  vernieuwt dat automatisch. Verwacht jouw omgeving het `Bearer`-voorvoegsel in
  de `Authorization`-header, dan schakelt de client daar bij de eerste 401
  vanzelf naar over.
- **Nog niet getest tegen de live API.** De code is end-to-end getest tegen een
  nagemaakte API (sessie, zoeken, concept, boeken, foutafhandeling), maar
  `api.e-boekhouden.nl` was vanuit de bouwomgeving niet bereikbaar. Loopt een
  veldnaam bij jou anders, dan zit die op één plek: de methodes onderaan
  `client.py`. Begin daarom met `check_connection` en een testfactuur voor een
  eigen relatie.
