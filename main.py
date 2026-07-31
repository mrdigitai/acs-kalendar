"""
main.py -- orchestrátor. Spouští ho GitHub Actions.

Zkusí primární zdroj (API-Football). Pokud selže (chybí klíč, výpadek,
nedostatečné pokrytí soutěže), spadne na scraping sparta.cz jako fallback.
Výsledek zapíše do sparta.ics v rootu repa (odtud ho servíruje GitHub Pages).
"""

from __future__ import annotations
import os
import sys
import traceback

from build_ics import write_ics

OUTPUT_PATH = "sparta.ics"


def get_fixtures() -> list[dict]:
    api_key = os.environ.get("API_FOOTBALL_KEY")
    team_id = os.environ.get("SPARTA_TEAM_ID")

    if api_key and team_id:
        try:
            from api_football_fetch import fetch_fixtures
            season = int(os.environ.get("SEASON", "2026"))
            fixtures = fetch_fixtures(int(team_id), season, api_key)
            if fixtures:
                print(f"[main] API-Football: {len(fixtures)} zápasů.")
                return fixtures
            print("[main] API-Football vrátilo 0 zápasů, zkouším fallback.")
        except Exception:
            print("[main] API-Football selhalo, zkouším fallback:", file=sys.stderr)
            traceback.print_exc()
    else:
        print("[main] API_FOOTBALL_KEY / SPARTA_TEAM_ID nenastaveno, jdu rovnou na fallback.")

    try:
        from scraper_sparta import fetch_calendar_html, parse_fixtures
        html = fetch_calendar_html()
        fixtures = parse_fixtures(html)
        print(f"[main] scraper_sparta (fallback): {len(fixtures)} zápasů.")
        return fixtures
    except Exception:
        print("[main] I fallback scraper selhal:", file=sys.stderr)
        traceback.print_exc()
        return []


def main() -> int:
    fixtures = get_fixtures()
    if not fixtures:
        print("[main] Žádná data z žádného zdroje -- sparta.ics NEpřepisuji "
              "(radši starý platný soubor než prázdný).", file=sys.stderr)
        return 1

    n = write_ics(fixtures, OUTPUT_PATH)
    print(f"[main] Hotovo: {n} událostí zapsáno do {OUTPUT_PATH}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
