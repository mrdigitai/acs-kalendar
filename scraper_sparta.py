"""
scraper_sparta.py
FALLBACK zdroj dat -- přímo z https://sparta.cz/cs/zapasy/1-muzi-a/2026-2027/kalendar

STATUS: OVĚŘENO ŽIVĚ (2026-07-31) proti skutečné produkční stránce.

Stránka je Next.js (App Router). Zdálo by se logické scrapovat vyrenderované HTML
přes BeautifulSoup, ale nejde to spolehlivě -- datum/čas zápasu se u KAŽDÉ karty
dokresluje až na klientovi (v HTML je na jejich místě
`<template data-dgst="BAILOUT_TO_CLIENT_SIDE_RENDERING">`), protože komponenta
potřebuje znát časovou zónu prohlížeče. Bez spuštěného JS bys z DOMu nedostal
žádné datum, jen text kola ("2. kolo") a jména týmů.

Skutečná data (soutěž, kolo, oba týmy, stadion -- včetně adresy, přesný kickoff
v UTC, TV přenos) ALE jsou v HTML přítomná jinde: Next.js embedduje tzv. "flight"
RSC payload jako sled `<script>self.__next_f.push([1, "..."])</script>` bloků
s escapovaným JSON-like textem (formát `<label>:<json>`, kde stringové hodnoty
tvaru `"$xy"` jsou reference na jiný label ve stejném payloadu). Z toho se dá
zápas rekonstruovat mnohem spolehlivěji než z DOMu -- especially protože hashovaná
CSS jména tříd (`MatchPreview_Container__2yhKE` apod.) i struktura DOMu se běžně
mění mezi buildy, kdežto tvar JSON objektů (klíče jako "match"/"opponent"/
"stadium"/"league"/"round"/"start"/"home") je stabilnější API kontrakt.

Detail URL (`/cs/zapas/{id}-{slug}`) se bere zvlášť přímým regexem nad syrovým
HTML (tam už je jako normální href, žádné escapování) -- je to spolehlivější než
skládat slug sám (diakritika, zkratky klubů apod.).

PŘESNÝ ČAS VÝKOPU -- DŮLEŽITÉ ZJIŠTĚNÍ:
Klub čas skutečně nezveřejňuje dopředu pro celou sezónu. Zápasy bez potvrzeného
času mají v datech pole "start" nastavené na PŮLNOC v Europe/Prague (empiricky
ověřeno: UTC offset tohoto "start" přesně kopíruje přechod letní/zimní čas na
25. 10. 2026 -- 22:00Z před přechodem, 23:00Z po přechodu -- což by čirá náhoda
nevysvětlila). Tenhle scraper takové zápasy detekuje (lokální čas výkopu == 00:00:00)
a vrací pro ně kickoff_utc=None + date_hint (lokální datum), aby build_ics.py
neudělal z půlnoci falešně přesný čas -- viz komentář v build_ics.py o "TBD
raději než tichá lež o čase 18:00". Zápasy s reálně potvrzeným časem (typicky
jen ty v nejbližších ~2-3 týdnech) mají "start" beze změny.

PAGINACE ("Načíst další"):
SSR payload při prvním načtení stránky obsahuje jen část sezóny -- u sezóny
2026/2027 to bylo 20 zápasů, 31. 7. 2026 -- 29. 1. 2027 (celý podzim + zimní
předkola). Tlačítko "Načíst další" NEVOLÁ žádné veřejné REST/XHR API, které by
šlo replikovat přes requests: je to čistě klientská komponenta z lazy-loaded JS
chunku, který se stahuje až za běhu (jeho hashované jméno souboru není nikde
staticky v HTML ani v runtime webpack manifestu, který se stahuje při prvním
loadu -- resolvuje se to až za běhu přes webpack chunk-loading mechanismus).
Zkoušeny a vyloučeny byly i běžné GET-pagination vzorce (?page=2, ?offset=20,
?cursor=20 apod.) -- server je ignoruje, vrací pořád stejných 20 zápasů.
Jediná cesta k reálnému zjištění, jak "Načíst další" funguje, je prohlížeč s
otevřeným Network tabem (Chrome DevTools, nebo Claude s připojeným Chrome
extensionem -- v tomhle běhu nebyl extension připojený, takže tenhle bod zůstává
neověřený). Než se to ověří, `parse_fixtures()` vrátí jen to, co je v prvním
SSR loadu -- což prakticky pokrývá "co už má smysl mít v kalendáři" (jarní
termíny bývají navíc stejně upřesňované/dohrávané průběžně přes sezónu).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

CALENDAR_URL = "https://sparta.cz/cs/zapasy/1-muzi-a/2026-2027/kalendar"
HEADERS = {
    "User-Agent": "mr_digit_ai-fanousek-kalendar/1.0 (+neoficialni fanouskovsky projekt, "
                  "kontakt: rosslermichal@gmail.com; nizka frekvence requestu ~2x/tyden)"
}

HOME_CLUB_NAME = "AC Sparta Praha"
PRAGUE_TZ = ZoneInfo("Europe/Prague")

# self.__next_f.push([1,"<escaped JSON-ish flight text>"]) -- viz docstring výše.
FLIGHT_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
# Řádek flight payloadu tvaru "<label>:<json object>".
FLIGHT_LINE_RE = re.compile(r'^([0-9a-zA-Z]+):(\{.*\})$')
# Skutečný odkaz na detail zápasu, jak je v renderovaném HTML (ne v payloadu).
DETAIL_HREF_RE = re.compile(r'href="(/cs/zapas/(\d+)-[^"]*)"')


def fetch_calendar_html(url: str = CALENDAR_URL) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def _extract_flight_objects(html: str) -> dict[str, dict]:
    """Poskládá Next.js flight payload zpět a vrátí mapu label -> JSON objekt.

    Ignoruje řádky, které nejsou tvaru "<label>:{...}" (reference na pole,
    HL/preload záznamy apod. nás nezajímají -- chceme jen JSON objekty).
    """
    full_text_parts: list[str] = []
    for m in FLIGHT_CHUNK_RE.finditer(html):
        # Zachycený text je tělo JS string literálu -> rozescapovat přes JSON.
        try:
            full_text_parts.append(json.loads('"' + m.group(1) + '"'))
        except json.JSONDecodeError:
            continue

    id_map: dict[str, dict] = {}
    for line in "".join(full_text_parts).split("\n"):
        m = FLIGHT_LINE_RE.match(line)
        if not m:
            continue
        try:
            obj = json.loads(m.group(2))
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            id_map[m.group(1)] = obj
    return id_map


def _resolve(id_map: dict[str, dict], ref):
    if isinstance(ref, str) and ref.startswith("$") and not ref.startswith("$@"):
        return id_map.get(ref[1:])
    return ref


def _extract_detail_urls(html: str) -> dict[int, str]:
    urls: dict[int, str] = {}
    for m in DETAIL_HREF_RE.finditer(html):
        match_id = int(m.group(2))
        urls.setdefault(match_id, f"https://sparta.cz{m.group(1)}")
    return urls


def _split_kickoff(start_iso: str) -> tuple[str | None, str | None]:
    """Vrátí (kickoff_utc, date_hint). Půlnoc v Europe/Prague = čas ještě není
    potvrzený -> kickoff_utc None, date_hint na lokální datum."""
    dt_utc = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    local = dt_utc.astimezone(PRAGUE_TZ)
    if (local.hour, local.minute, local.second) == (0, 0, 0):
        return None, local.date().isoformat()
    return start_iso, None


def parse_fixtures(html: str) -> list[dict]:
    id_map = _extract_flight_objects(html)
    detail_urls = _extract_detail_urls(html)

    fixtures: list[dict] = []
    seen_ids: set[int] = set()

    for obj in id_map.values():
        if not ({"match", "opponent", "league"} <= obj.keys()):
            continue

        match = _resolve(id_map, obj.get("match"))
        opponent = _resolve(id_map, obj.get("opponent"))
        league = _resolve(id_map, obj.get("league"))
        stadium = _resolve(id_map, obj.get("stadium")) if obj.get("stadium") else None

        if not match or "id" not in match or "start" not in match:
            continue
        match_id = match["id"]
        if match_id in seen_ids:
            continue
        seen_ids.add(match_id)

        is_home = match.get("home") is True
        opponent_name = opponent["name"] if opponent else "?"
        home = HOME_CLUB_NAME if is_home else opponent_name
        away = opponent_name if is_home else HOME_CLUB_NAME

        kickoff_utc, date_hint = _split_kickoff(match["start"])

        fixtures.append({
            "id": str(match_id),
            "competition": league["name"] if league else "",
            "round": match.get("round", ""),
            "home": home,
            "away": away,
            "venue": stadium["name"] if stadium else None,
            "kickoff_utc": kickoff_utc,
            "date_hint": date_hint,
            "detail_url": detail_urls.get(match_id, f"https://sparta.cz/cs/zapas/{match_id}"),
        })

    fixtures.sort(key=lambda f: f.get("kickoff_utc") or f.get("date_hint") or "")
    return fixtures


if __name__ == "__main__":
    html = fetch_calendar_html()
    fixtures = parse_fixtures(html)
    print(json.dumps(fixtures, ensure_ascii=False, indent=2))
    confirmed = sum(1 for f in fixtures if f["kickoff_utc"])
    print(f"\n--> Nalezeno {len(fixtures)} zápasů, z toho {confirmed} s potvrzeným časem výkopu.")
