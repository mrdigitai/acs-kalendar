# ACS Kalendář — neoficiální fanouškovský .ics kalendář AC Sparta Praha 2026/2027

Auto-aktualizovaný kalendář zápasů (Chance Liga + evropské poháry + MOL Cup),
zdarma, kompatibilní s Google Calendar (Android) i Apple Calendar (iOS).
Postaveno jako ukázka "AI v praxi" (mr_digit_ai).

## Stav (2026-07-31)

Hotovo, otestováno naživo a nasazeno:
- `build_ics.py` — generátor `.ics` (RFC5545), stabilní UID = žádné duplicity při update. **Otestováno, roundtrip parse OK.**
- `main.py` — orchestrátor, zkusí API-Football, při selhání spadne na scraping sparta.cz.
- `scraper_sparta.py` — **ověřeno naživo proti produkční stránce.** Data se čtou z Next.js flight (RSC) payloadu vloženého v HTML, ne z hashovaných CSS tříd — mnohem stabilnější než DOM scraping. Detekuje i to, kdy klub ještě nezveřejnil přesný čas výkopu (takové zápasy dostanou celodenní placeholder místo vymyšleného času).
- `api_football_fetch.py` — kód/mapování polí funkční (ověřeno na starší sezóně), ale **free tier API-Football nepodporuje aktuální sezónu 2026** (jen 2022–2024) → v praxi se vždy použije scraper fallback, dokud by nebyl placený plán.
- `.github/workflows/update-calendar.yml` — cron 2x týdně (po, čt) + ruční spuštění, nasazeno a odzkoušeno.

## Známé mezery

- **Jaro 2027 (od cca 20. kola dál)** zatím v kalendáři není — sparta.cz ho na stránce kalendáře dotahuje přes tlačítko "Načíst další", které je čistě klientská komponenta (ne veřejné REST API), takže se to nedá získat prostým HTTP requestem. Vyžadovalo by to skutečný prohlížeč (Playwright/Selenium).

## Jak si lidé kalendář přidají

- **Google Calendar (Android/web):** Nastavení → Přidat kalendář → Z adresy URL → vlož `https://.../sparta.ics`
- **Apple Calendar (iOS):** Nastavení → Kalendář → Účty → Přidat účet → Jiný → Přidat odebíraný kalendář → vlož URL (nebo `webcal://` verze pro jedno klepnutí)

## Známá omezení (řekni si o ně, než to půjde ven veřejně)

- **Přesný čas výkopu** bývá zveřejněný klubem jen pár týdnů dopředu (TV rozpis). Do té doby kalendář ukáže celodenní placeholder s `[čas upřesní klub]` — to je fér chování, ne bug.
- **Scraping sparta.cz** (fallback) je reverse-engineering cizích dat bez JS renderu — křehké, může se rozbít při redesignu webu. API-Football je proto primární zdroj.
- **Transparentnost:** v popisu každé události je poznámka "neoficiální fanouškovský kalendář, data z veřejně dostupných zdrojů" — doporučuju stejnou formulaci použít i v postu na sítě.
