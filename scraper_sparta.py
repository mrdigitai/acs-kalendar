"""
scraper_sparta.py
FALLBACK zdroj dat -- přímo z https://sparta.cz/cs/zapasy/1-muzi-a/2026-2027/kalendar

STATUS: OVĚŘENO ŽIVĚ (2026-07-31), včetně mechanismu "Načíst další" (viz níže).

Stránka je Next.js (App Router). Zdálo by se logické scrapovat vyrenderované HTML
přes BeautifulSoup, ale nejde to spolehlivě -- datum/čas zápasu se u KAŽDÉ karty
dokresluje až na klientovi (v HTML je na jejich místě
`<template data-dgst="BAILOUT_TO_CLIENT_SIDE_RENDERING">`), protože komponenta
potřebuje znát časovou zónu prohlížeče.

PRIMÁRNÍ CESTA -- přímé volání Next.js Server Action (`fetch_full_season`):
Tlačítko "Načíst další" ve skutečnosti POSTuje na tu samou URL stránky, s
hlavičkou `Next-Action: <hash>` a tělem `["cs", {team, season, limit,
start_after, order, offset}]`. Zjištěno živě přes Chrome (monkey-patched
window.fetch + click na tlačítko) a ověřeno, že jde replikovat čistým
`requests.post()` bez cookies/session -- při `offset=0` a dostatečně velkém
`limit` vrátí RSC "flight" odpověď obsahující *celou* zbylou sezónu v jednom
requestu (u sezóny 2026/2027 to bylo 31 zápasů, 2. kolo -- 30. kolo/duben 2027),
ne jen prvních ~20 jako starý SSR-only přístup. Odpověď má tvar
`0:[...]\n1:{"items":[{"match":..,"opponent":..,"stadium":..,"league":..}]}`
-- objekty jsou už plně rozbalené (na rozdíl od SSR payloadu níž), žádné $ref.

RIZIKO: `FIXTURES_ACTION_ID` je hash zkompilované server akce -- při redeployi
webu (nová verze frontendu) se změní a tenhle POST přestane fungovat (server
vrátí chybu/jiný tvar). Pro tenhle případ je tu fallback na starší,
odolnější (ale méně kompletní) SSR-payload metodu níž.

FALLBACK -- SSR "flight" payload z prvního načtení stránky:
Next.js embedduje do HTML tzv. "flight" RSC payload jako sled
`<script>self.__next_f.push([1, "..."])</script>` bloků s escapovaným
JSON-like textem (formát `<label>:<json>`, kde stringové hodnoty tvaru
`"$xy"` jsou reference na jiný label ve stejném payloadu). Obsahuje ale jen
prvních ~20 zápasů (to, co server stihne vyrenderovat při prvním loadu) --
zbytek sezóny v něm není. Používá se jen když primární POST selže.

Detail URL (`/cs/zapas/{id}-{slug}`): u fallbacku se bere přímým regexem nad
syrovým HTML (tam je jako normální href, žádné escapování). Primární cesta
slug nedostane (Server Action ho nevrací), takže se skládá sám -- ověřeno na
všech 20 zápasech ze SSR payloadu (přesná shoda: lowercase + odstranění
diakritiky (NFKD) + non-alfanumerické znaky pryč + mezery na pomlčky), a
zpětně ověřeno i pro dva zápasy z druhé "strany" (mimo SSR payload) přes
přímý HTTP dotaz -- obě sestavené URL vrátily 200.

PŘESNÝ ČAS VÝKOPU -- DŮLEŽITÉ ZJIŠTĚNÍ:
Klub čas skutečně nezveřejňuje dopředu pro celou sezónu. Zápasy bez potvrzeného
času mají v datech pole "start" nastavené na PŮLNOC v Europe/Prague (empiricky
ověřeno: UTC offset tohoto "start" přesně kopíruje přechod letní/zimní čas na
25. 10. 2026 -- 22:00Z před přechodem, 23:00Z po přechodu -- což by čirá náhoda
nevysvětlila). Tenhle scraper takové zápasy detekuje (lokální čas výkopu == 00:00:00)
a vrací pro ně kickoff_utc=None + date_hint (lokální datum), aby build_ics.py
neudělal z půlnoci falešně přesný čas -- viz komentář v build_ics.py o "TBD
raději než tichá lež o čase 18:00".
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

CALENDAR_URL = "https://sparta.cz/cs/zapasy/1-muzi-a/2026-2027/kalendar"
HEADERS = {
    "User-Agent": "mr_digit_ai-fanousek-kalendar/1.0 (+neoficialni fanouskovsky projekt, "
                  "kontakt: rosslermichal@gmail.com; nizka frekvence requestu ~2x/tyden)"
}

HOME_CLUB_NAME = "AC Sparta Praha"
PRAGUE_TZ = ZoneInfo("Europe/Prague")

# Next.js Server Action za tlačítkem "Načíst další" -- viz docstring. Interní
# team/season ID sparta.cz (ne API-Football ID) pro Muži A, sezónu 2026/2027.
FIXTURES_ACTION_ID = "ce004dba8924b88fd0c1c83b01ae34719144b7b5"
FIXTURES_TEAM_ID = 1
FIXTURES_SEASON_ID = 34
FIXTURES_LIMIT = 60  # pohodlná rezerva nad 31 zápasy zbytku sezóny 2026/2027

# self.__next_f.push([1,"<escaped JSON-ish flight text>"]) -- fallback SSR payload.
FLIGHT_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
FLIGHT_LINE_RE = re.compile(r'^([0-9a-zA-Z]+):(\{.*\})$')
DETAIL_HREF_RE = re.compile(r'href="(/cs/zapas/(\d+)-[^"]*)"')


def fetch_calendar_html(url: str = CALENDAR_URL) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def _slugify(name: str) -> str:
    """lowercase + bez diakritiky + jen [a-z0-9], mezery -> pomlčky.
    Ověřeno proti 20 skutečným slugům ze SSR payloadu, viz docstring."""
    normalized = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in normalized if not unicodedata.combining(c))
    cleaned = re.sub(r"[^a-z0-9\s]", "", ascii_only.lower())
    return re.sub(r"\s+", "-", cleaned.strip())


def _split_kickoff(start_iso: str) -> tuple[str | None, str | None]:
    """Vrátí (kickoff_utc, date_hint). Půlnoc v Europe/Prague = čas ještě není
    potvrzený -> kickoff_utc None, date_hint na lokální datum."""
    dt_utc = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    local = dt_utc.astimezone(PRAGUE_TZ)
    if (local.hour, local.minute, local.second) == (0, 0, 0):
        return None, local.date().isoformat()
    return start_iso, None


def _build_fixture(match: dict, opponent: dict | None, league: dict | None,
                    stadium: dict | None, detail_url: str | None = None) -> dict | None:
    if not match or "id" not in match or "start" not in match:
        return None
    match_id = match["id"]
    is_home = match.get("home") is True
    opponent_name = opponent["name"] if opponent else "?"
    home = HOME_CLUB_NAME if is_home else opponent_name
    away = opponent_name if is_home else HOME_CLUB_NAME
    kickoff_utc, date_hint = _split_kickoff(match["start"])

    if not detail_url:
        detail_url = f"https://sparta.cz/cs/zapas/{match_id}-{_slugify(HOME_CLUB_NAME)}-{_slugify(opponent_name)}"

    return {
        "id": str(match_id),
        "competition": league["name"] if league else "",
        "round": match.get("round", ""),
        "home": home,
        "away": away,
        "venue": stadium["name"] if stadium else None,
        "kickoff_utc": kickoff_utc,
        "date_hint": date_hint,
        "detail_url": detail_url,
    }


def fetch_full_season_fixtures() -> list[dict] | None:
    """Primární cesta: přímé POST volání Server Action za "Načíst další".
    Vrátí None (ne vyhodí), pokud cokoliv selže -- volající pak zkusí fallback."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    body = json.dumps(["cs", {
        "team": FIXTURES_TEAM_ID,
        "season": FIXTURES_SEASON_ID,
        "limit": FIXTURES_LIMIT,
        "start_after": now,
        "order": "asc",
        "offset": 0,
    }])
    headers = {
        **HEADERS,
        "Accept": "text/x-component",
        "Content-Type": "text/plain;charset=UTF-8",
        "Next-Action": FIXTURES_ACTION_ID,
    }
    try:
        resp = requests.post(CALENDAR_URL, headers=headers, data=body.encode("utf-8"), timeout=30)
        resp.raise_for_status()
        # Server posílá "Content-Type: text/x-component" bez charsetu -> requests
        # by defaultně hádal ISO-8859-1 a diakritiku by rozbil. Obsah je vždy UTF-8.
        text = resp.content.decode("utf-8")
        line = next(l for l in text.split("\n") if l.startswith("1:"))
        items = json.loads(line[2:])["items"]
    except Exception:
        return None

    fixtures: list[dict] = []
    seen_ids: set[int] = set()
    for item in items:
        match = item.get("match")
        if not match or match.get("id") in seen_ids:
            continue
        fixture = _build_fixture(match, item.get("opponent"), item.get("league"), item.get("stadium"))
        if fixture is None:
            continue
        seen_ids.add(match["id"])
        fixtures.append(fixture)

    if not fixtures:
        return None
    fixtures.sort(key=lambda f: f.get("kickoff_utc") or f.get("date_hint") or "")
    return fixtures


def _extract_flight_objects(html: str) -> dict[str, dict]:
    """Poskládá Next.js SSR flight payload zpět a vrátí mapu label -> JSON objekt."""
    full_text_parts: list[str] = []
    for m in FLIGHT_CHUNK_RE.finditer(html):
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


def parse_fixtures(html: str) -> list[dict]:
    """Fallback parser nad SSR HTML -- viz docstring modulu. Pokrývá jen
    zápasy, co server stihl vyrenderovat při prvním loadu (~20)."""
    id_map = _extract_flight_objects(html)
    detail_urls = _extract_detail_urls(html)

    fixtures: list[dict] = []
    seen_ids: set[int] = set()

    for obj in id_map.values():
        if not ({"match", "opponent", "league"} <= obj.keys()):
            continue

        match = _resolve(id_map, obj.get("match"))
        if not match or match.get("id") in seen_ids:
            continue
        opponent = _resolve(id_map, obj.get("opponent"))
        league = _resolve(id_map, obj.get("league"))
        stadium = _resolve(id_map, obj.get("stadium")) if obj.get("stadium") else None

        fixture = _build_fixture(match, opponent, league, stadium, detail_urls.get(match["id"]))
        if fixture is None:
            continue
        seen_ids.add(match["id"])
        fixtures.append(fixture)

    fixtures.sort(key=lambda f: f.get("kickoff_utc") or f.get("date_hint") or "")
    return fixtures


def scrape_fixtures() -> list[dict]:
    """Veřejné vstupní místo pro main.py: primární Server Action POST,
    a když ten selže (např. po redeployi webu se změnil action hash),
    fallback na parsování SSR HTML z prvního loadu."""
    fixtures = fetch_full_season_fixtures()
    if fixtures:
        return fixtures
    return parse_fixtures(fetch_calendar_html())


if __name__ == "__main__":
    fixtures = scrape_fixtures()
    print(json.dumps(fixtures, ensure_ascii=False, indent=2))
    confirmed = sum(1 for f in fixtures if f["kickoff_utc"])
    print(f"\n--> Nalezeno {len(fixtures)} zápasů, z toho {confirmed} s potvrzeným časem výkopu.")
