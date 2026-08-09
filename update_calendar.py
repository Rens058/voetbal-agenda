from __future__ import annotations

import os
import urllib.request
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


API_URL = "https://api.football-data.org/v4/competitions/DED/matches"
OUTPUT = Path("heerenveen.ics")
TZ = ZoneInfo("Europe/Amsterdam")

TEAM_NAME = "SC Heerenveen"


def fetch_matches() -> list[dict]:
    token = os.environ.get("FOOTBALL_DATA_TOKEN")

    if not token:
        raise RuntimeError(
            "FOOTBALL_DATA_TOKEN ontbreekt. "
            "Voeg deze toe als GitHub Actions secret."
        )

    request = urllib.request.Request(
        API_URL,
        headers={
            "X-Auth-Token": token,
            "User-Agent": "Abe-Agenda/0.1",
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)

    return data.get("matches", [])


def is_heerenveen_match(match: dict) -> bool:
    home = match.get("homeTeam", {}).get("name", "")
    away = match.get("awayTeam", {}).get("name", "")

    return TEAM_NAME.lower() in {
        home.lower(),
        away.lower(),
    }


def escape_ics(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def format_ics_datetime(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def make_uid(match: dict) -> str:
    """
    Een stabiele UID is belangrijk.

    We gebruiken bewust NIET de datum of tijd in de UID.
    Als KNVB/football-data.org een wedstrijd verplaatst,
    herkent de kalender het daardoor als dezelfde afspraak.
    """

    match_id = match.get("id")

    if match_id:
        return f"football-data-{match_id}@abe-agenda"

    home = match.get("homeTeam", {}).get("name", "home")
    away = match.get("awayTeam", {}).get("name", "away")

    return (
        f"{home.lower().replace(' ', '-')}-"
        f"{away.lower().replace(' ', '-')}@abe-agenda"
    )


def make_event(match: dict) -> list[str]:
    home = match["homeTeam"]["name"]
    away = match["awayTeam"]["name"]

    utc_date = match.get("utcDate")

    if not utc_date:
        raise ValueError(f"Wedstrijd zonder utcDate: {home} - {away}")

    start_utc = datetime.fromisoformat(
        utc_date.replace("Z", "+00:00")
    )

    start_local = start_utc.astimezone(TZ)

    # Voorlopig reserveren we 2 uur voor een wedstrijd.
    end_local = start_local + timedelta(hours=2)

    if home.lower() == TEAM_NAME.lower():
        summary = f"⚽ {TEAM_NAME} – {away}"
        location = "Abe Lenstra Stadion, Heerenveen"
    else:
        summary = f"⚽ {home} – {TEAM_NAME}"
        location = home

    status = match.get("status", "")
    matchday = match.get("matchday")

    description_parts = [
        "SC Heerenveen – Eredivisie",
        "Bron: Football-Data / KNVB wedstrijdschema.",
    ]

    if matchday:
        description_parts.append(f"Speelronde: {matchday}")

    if status:
        description_parts.append(f"Status: {status}")

    description = "\\n".join(description_parts)

    now_utc = datetime.now(timezone.utc)

    return [
        "BEGIN:VEVENT",
        f"UID:{escape_ics(make_uid(match))}",
        f"DTSTAMP:{now_utc.strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART;TZID=Europe/Amsterdam:{format_ics_datetime(start_local)}",
        f"DTEND;TZID=Europe/Amsterdam:{format_ics_datetime(end_local)}",
        f"SUMMARY:{escape_ics(summary)}",
        f"LOCATION:{escape_ics(location)}",
        f"DESCRIPTION:{escape_ics(description)}",
        "END:VEVENT",
    ]


def generate_calendar(matches: list[dict]) -> str:
    heerenveen_matches = [
        match
        for match in matches
        if is_heerenveen_match(match)
    ]

    heerenveen_matches.sort(
        key=lambda match: match.get("utcDate", "")
    )

    print(
        f"Gevonden: {len(heerenveen_matches)} "
        f"wedstrijden van {TEAM_NAME}"
    )

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Abe Agenda//SC Heerenveen//NL",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Abe Agenda – SC Heerenveen",
        "X-WR-TIMEZONE:Europe/Amsterdam",
        "X-WR-CALDESC:Automatisch bijgewerkte kalender van SC Heerenveen.",
    ]

    for match in heerenveen_matches:
        home = match["homeTeam"]["name"]
        away = match["awayTeam"]["name"]
        utc_date = match.get("utcDate")

        print(f"  {utc_date} | {home} - {away}")

        lines.extend(make_event(match))

    lines.append("END:VCALENDAR")

    return "\r\n".join(lines) + "\r\n"


def main() -> None:
    print("Abe Agenda – SC Heerenveen")
    print("Wedstrijden ophalen via football-data.org...")

    matches = fetch_matches()

    print(
        f"API levert {len(matches)} "
        "Eredivisiewedstrijden."
    )

    calendar = generate_calendar(matches)

    OUTPUT.write_text(
        calendar,
        encoding="utf-8",
        newline="",
    )

    print(f"Kalender geschreven naar {OUTPUT}")


if __name__ == "__main__":
    main()
