from __future__ import annotations

import json
import os
import urllib.request


TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "FOOTBALL_DATA_TOKEN ontbreekt. Controleer GitHub Secrets."
    )


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "X-Auth-Token": TOKEN,
            "User-Agent": "MijnVoetbalagenda-Test/1.0",
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


# Stap 1: Ajax-ID opzoeken via de Eredivisie.
teams_data = fetch_json(
    "https://api.football-data.org/v4/competitions/DED/teams"
)

ajax = None

for team in teams_data["teams"]:
    if team["name"].lower() == "ajax":
        ajax = team
        break

if ajax is None:
    raise RuntimeError("Ajax niet gevonden.")

ajax_id = ajax["id"]

print(f"Ajax gevonden. Team-ID: {ajax_id}")
print()


# Stap 2: alle wedstrijden ophalen die jouw abonnement
# voor dit team beschikbaar stelt.
matches_data = fetch_json(
    f"https://api.football-data.org/v4/teams/{ajax_id}/matches"
)

matches = matches_data.get("matches", [])

print(f"Aantal wedstrijden gevonden: {len(matches)}")
print()


# Stap 3: laten zien welke competities daarin voorkomen.
competitions = {}

for match in matches:
    competition = match.get("competition", {})

    name = competition.get("name", "Onbekend")
    code = competition.get("code")

    competitions[name] = code

print("Competities gevonden:")

for name in sorted(competitions):
    code = competitions[name]
    print(f"- {name} ({code})")

print()
print("Wedstrijden:")
print()

for match in matches:
    competition = match.get("competition", {}).get(
        "name",
        "Onbekend",
    )

    home = match.get("homeTeam", {}).get(
        "name",
        "?",
    )

    away = match.get("awayTeam", {}).get(
        "name",
        "?",
    )

    date = match.get("utcDate", "")
    status = match.get("status", "")

    print(
        f"{date} | "
        f"{competition} | "
        f"{home} - {away} | "
        f"{status}"
    )
