# ACS Kalendář — neoficiální fanouškovský .ics kalendář AC Sparta Praha 2026/2027

Auto-aktualizovaný kalendář zápasů (Chance Liga + evropské poháry + MOL Cup),
zdarma, kompatibilní s Google Calendar (Android) i Apple Calendar (iOS).
Postaveno jako ukázka "AI v praxi" (mr_digit_ai).

## Stav (2026-07-31)

Hotovo, otestováno naživo a nasazeno:
- `build_ics.py` — generátor `.ics` (RFC5545), stabilní UID = žádné duplicity při update. **Otestováno, roundtrip parse OK.**
- `main.py` — orchestrátor, zkusí API-Football, při selhání spadne na scraping sparta.cz.
- `scraper_sparta.py` — **ověřeno naživo proti produkční stránce, včetně "Načíst další".** Primárně volá přímo tu samou Next.js Server Action, kterou na pozadí volá tlačítko "Načíst další" — vrátí celou sezónu v jednom requestu (žádný prohlížeč potřeba). Pokud by se po redeployi webu action hash změnil, spadne na odolnější fallback (SSR payload z prvního loadu stránky, pokrývá jen ~20 nejbližších zápasů). Detekuje i to, kdy klub ještě nezveřejnil přesný čas výkopu (takové zápasy dostanou celodenní placeholder místo vymyšleného času).
- `api_football_fetch.py` — kód/mapování polí funkční (ověřeno na starší sezóně), ale **free tier API-Football nepodporuje aktuální sezónu 2026** (jen 2022–2024) → v praxi se vždy použije scraper fallback, dokud by nebyl placený plán.
- `.github/workflows/update-calendar.yml` — cron 2x týdně (po, čt) + ruční spuštění, nasazeno a odzkoušeno.

## Odběr kalendáře

URL: **`https://mrdigitai.github.io/acs-kalendar/sparta.ics`**
Jedno-klik verze (webcal): **`webcal://mrdigitai.github.io/acs-kalendar/sparta.ics`**

- **Google Calendar (Android/web):** Nastavení → Přidat kalendář → Z adresy URL → vlož URL výše
- **Apple Calendar (iOS/macOS):** Nastavení → Kalendář → Účty → Přidat účet → Jiný → Přidat odebíraný kalendář → vlož URL (nebo klepni na `webcal://` odkaz pro rovnou přidání)

## Známá omezení

- **Přesný čas výkopu** bývá zveřejněný klubem jen pár týdnů dopředu (TV rozpis). Do té doby kalendář ukáže celodenní placeholder s `[čas upřesní klub]` — to je fér chování, ne bug.
- **Scraping sparta.cz** (fallback, aktuálně jediný fungující zdroj) je reverse-engineering cizích dat — křehké, může se rozbít při redesignu webu.
- **API-Football** (kód hotový) na free tieru nepokrývá aktuální sezónu 2026 — potřeboval by placený plán, aby se stal reálně primárním zdrojem.
- **Transparentnost:** v popisu každé události je poznámka "neoficiální fanouškovský kalendář, data z veřejně dostupných zdrojů".
