"""
api_football_fetch.py
Primární datový zdroj: API-Football (api-football.com / RapidAPI).
Free tier: 100 requestů/den, bez karty -- víc než dost na 2x týdně refresh.

Proč tenhle zdroj a ne přímo scraping sparta.cz:
- Čistý JSON, žádné parsování HTML, žádné riziko že redesign webu ti to rozbije.
- Dotaz podle TEAM ID (ne league ID) -> vrátí zápasy napříč VŠEMI soutěžemi,
  kde tým aktuálně hraje. Kaskáda Liga mistrů -> Evropská liga -> Konferenční
  liga (podle výsledku v playoff/skupině) se řeší sama, nemusíš to hlídat ručně.

CO MUSÍŠ UDĚLAT TY (nemůžu za tebe -- založení účtu je mimo moje oprávnění):
1. Zaregistruj se zdarma na https://www.api-football.com/ (nebo přes RapidAPI).
2. V jejich dashboardu vyhledej "AC Sparta Praha" -> zjisti TEAM_ID.
3. Ověř, že v seznamu soutěží týmu figuruje "Chance Liga"/"Czech Liga" a
   "MOL Cup"/"Czech Cup" -- pokud MOL Cup ještě nezačal, nemusí se objevit,
   dokud nebude mít los. To je OK, stačí re-run po losu.
4. Ulož API klíč jako GitHub Actions secret API_FOOTBALL_KEY (viz README).
5. Dej mi vědět TEAM_ID a případně mismatch v pokrytí soutěží -- doladím mapping.

Response shape (dle veřejné dokumentace API-Football v3, NEOVĚŘENO ŽIVĚ --
ověř si prosím na první ostré volání, že pole sedí):
{
  "response": [
    {
      "fixture": {"id": 123456, "date": "2026-08-02T16:30:00+00:00",
                   "venue": {"name": "epet ARENA"}},
      "league": {"name": "Chance Liga", "round": "Regular Season - 2"},
      "teams": {"home": {"name": "..."}, "away": {"name": "..."}}
    },
    ...
  ]
}
"""

from __future__ import annotations
import os
import requests

API_BASE = "https://v3.football.api-sports.io"


def fetch_fixtures(team_id: int, season: int, api_key: str | None = None) -> list[dict]:
    """Stáhne fixtures pro daný tým/sezónu a převede je do interního formátu
    (viz build_ics.py docstring)."""
    api_key = api_key or os.environ.get("API_FOOTBALL_KEY")
    if not api_key:
        raise RuntimeError("Chybí API_FOOTBALL_KEY (env proměnná nebo GitHub secret).")

    resp = requests.get(
        f"{API_BASE}/fixtures",
        headers={"x-apisports-key": api_key},
        params={"team": team_id, "season": season},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("errors"):
        raise RuntimeError(f"API-Football vrátilo chybu: {data['errors']}")

    fixtures = []
    for item in data.get("response", []):
        fx = item["fixture"]
        league = item["league"]
        teams = item["teams"]
        venue = (fx.get("venue") or {}).get("name")

        fixtures.append({
            "id": str(fx["id"]),
            "competition": league.get("name", ""),
            "round": league.get("round", ""),
            "home": teams["home"]["name"],
            "away": teams["away"]["name"],
            "venue": venue,
            "kickoff_utc": fx["date"],  # API vrací už ISO8601 s offsetem
            "detail_url": None,
        })
    return fixtures


if __name__ == "__main__":
    import sys, json

    team_id = int(os.environ.get("SPARTA_TEAM_ID", "0"))
    season = int(os.environ.get("SEASON", "2026"))
    if not team_id:
        print("Nastav SPARTA_TEAM_ID (zjistíš v API-Football dashboardu po loginu).", file=sys.stderr)
        sys.exit(1)

    fixtures = fetch_fixtures(team_id, season)
    print(json.dumps(fixtures, ensure_ascii=False, indent=2))
