"""
build_ics.py
Vezme seznam zápasů (list dictů) a vygeneruje RFC5545-validní .ics soubor
kompatibilní s Google Calendar (Android) i Apple Calendar (iOS).

Vstupní formát jednoho zápasu (co musí dodat scraper/API vrstva):
{
    "id": "5725",                          # stabilní ID zápasu ze zdroje -> stabilní UID
    "competition": "Chance LIGA",
    "round": "2. kolo",
    "home": "AC Sparta Praha",
    "away": "FC Zlín",
    "venue": "epet ARENA",                 # None/"" pokud neznámé
    "kickoff_utc": "2026-08-02T16:30:00Z",  # ISO8601 UTC, None pokud čas zatím neurčen
    "detail_url": "https://sparta.cz/cs/zapas/5725-ac-sparta-praha-fc-zlin",
}

Klíčová věc: UID = f"acs-{id}@mrdigit.ai" je STABILNÍ napříč běhy.
Google/Apple kalendář díky tomu při dalším refreshi UPDATNE existující
událost (posun kickoffu kvůli TV, upřesnění stadionu...), místo aby
vytvořil duplicitu. Bez tohohle celá "auto-update" vlastnost nefunguje.
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta
from icalendar import Calendar, Event
import sys


CAL_NAME = "AC Sparta Praha 2026/2027"
UID_DOMAIN = "mrdigit.ai"
DEFAULT_DURATION_MIN = 120  # zápas + rezerva, pokud neznáme přesný čas


def _parse_kickoff(kickoff_utc: str | None) -> tuple[datetime | None, bool]:
    """Vrátí (datetime, is_confirmed). Pokud čas neznáme, vrací None."""
    if not kickoff_utc:
        return None, False
    dt = datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00"))
    return dt, True


def build_calendar(fixtures: list[dict]) -> Calendar:
    cal = Calendar()
    cal.add("prodid", f"-//mr_digit_ai//{CAL_NAME}//CZ")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", CAL_NAME)
    cal.add("x-wr-timezone", "Europe/Prague")
    # hint pro klienty, co refresh-interval respektují (ne všechny, ale neškodí)
    cal.add("refresh-interval;value=duration", "P3D")
    cal.add("x-published-ttl", "P3D")

    now = datetime.now(timezone.utc)

    for f in fixtures:
        if not f.get("id"):
            raise ValueError(f"Zápas bez 'id' -> nelze vytvořit stabilní UID: {f}")

        e = Event()
        uid = f"acs-{f['id']}@{UID_DOMAIN}"
        e.add("uid", uid)

        home = f.get("home", "?")
        away = f.get("away", "?")
        competition = f.get("competition", "")
        round_ = f.get("round", "")

        summary_bits = [f"{home} – {away}"]
        if competition:
            summary_bits.append(f"({competition}{', ' + round_ if round_ else ''})")
        e.add("summary", " ".join(summary_bits))

        kickoff, confirmed = _parse_kickoff(f.get("kickoff_utc"))
        if confirmed:
            e.add("dtstart", kickoff)
            e.add("dtend", kickoff + timedelta(minutes=DEFAULT_DURATION_MIN))
        else:
            # čas zatím neurčen -> celodenní placeholder, ne vymyšlený čas
            # (raději "TBD" než tichá lež o čase 18:00)
            fallback_date = f.get("date_hint")  # 'YYYY-MM-DD' pokud aspoň den known
            if fallback_date:
                d = datetime.fromisoformat(fallback_date).date()
                e.add("dtstart", d)
                e.add("dtend", d + timedelta(days=1))
            else:
                # bez dne vůbec nejde založit VEVENT s DTSTART -> přeskočit a nahlásit
                print(f"[SKIP] {home} vs {away}: chybí kickoff_utc i date_hint", file=sys.stderr)
                continue
            e["summary"] = e["summary"] + " [čas upřesní klub]"

        if f.get("venue"):
            e.add("location", f["venue"])
        if f.get("detail_url"):
            e.add("description", f"Detail zápasu: {f['detail_url']}\n\nNeoficiální fanouškovský kalendář (mr_digit_ai) — data z veřejně dostupných zdrojů.")
            e.add("url", f["detail_url"])

        e.add("dtstamp", now)
        e.add("sequence", 0)
        e.add("status", "CONFIRMED")

        cal.add_component(e)

    return cal


def write_ics(fixtures: list[dict], path: str) -> int:
    cal = build_calendar(fixtures)
    with open(path, "wb") as fp:
        fp.write(cal.to_ical())
    return len(cal.subcomponents)


if __name__ == "__main__":
    # Smoke test s ukázkovými daty NENÍ skutečný rozpis Sparty — jen ověření,
    # že pipeline (UID, DTSTART, refresh-friendly hlavičky) je RFC5545 validní.
    demo_fixtures = [
        {
            "id": "TEST-1",
            "competition": "Chance LIGA",
            "round": "2. kolo",
            "home": "AC Sparta Praha",
            "away": "FC Zlín",
            "venue": "epet ARENA",
            "kickoff_utc": "2026-08-02T16:30:00Z",
            "detail_url": "https://sparta.cz/cs/zapas/5725-ac-sparta-praha-fc-zlin",
        },
        {
            "id": "TEST-2",
            "competition": "Liga mistrů UEFA",
            "round": "3. předkolo",
            "home": "AC Sparta Praha",
            "away": "Olympique Lyonnais",
            "venue": "epet ARENA",
            "kickoff_utc": None,
            "date_hint": "2026-08-11",
            "detail_url": "https://sparta.cz/cs/zapas/5844-ac-sparta-praha-olympique-lyonnais",
        },
    ]
    n = write_ics(demo_fixtures, "demo_test.ics")
    print(f"OK: zapsáno {n} událostí do demo_test.ics")
