from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


API_URL = "https://api.football-data.org/v4/competitions/DED/matches"

TZ = ZoneInfo("Europe/Amsterdam")
UTC = ZoneInfo("UTC")


TEAMS = {
    "heerenveen": {
        "names": ["SC Heerenveen"],
        "calendar_name": "Voetbalagenda – SC Heerenveen",
        "output": Path("heerenveen.ics"),
    },
    "cambuur": {
        "names": ["SC Cambuur-Leeuwarden"],
        "calendar_name": "Voetbalagenda – SC Cambuur",
        "output": Path("cambuur.ics"),
    },
}


STADIUMS = {
    "SC Heerenveen": "Abe Lenstra Stadion, Heerenveen",
    "SC Cambuur-Leeuwarden": "Kooi Stadion, Leeuwarden",
}


# Bij deze statussen is het aanvangstijdstip daadwerkelijk bekend.
TIMED_STATUSES = {
    "TIMED",
    "IN_PLAY",
    "PAUSED",
    "FINISHED",
}


def escape_ics(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def fetch_matches() -> list[dict]:
    token = os.environ.get("FOOTBALL_DATA_TOKEN")

    if not token:
        raise RuntimeError(
            "FOOTBALL_DATA_TOKEN ontbreekt. "
            "Controleer GitHub Secrets."
        )

    request = urllib.request.Request(
        API_URL,
        headers={
            "X-Auth-Token": token,
            "User-Agent": "Voetbalagenda/1.0",
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))

    return data["matches"]


def team_match(match: dict, team_names: list[str]) -> bool:
    home = match["homeTeam"]["name"]
    away = match["awayTeam"]["name"]

    return home in team_names or away in team_names


def make_event(match: dict, team_key: str) -> list[str]:
    team = TEAMS[team_key]

    home = match["homeTeam"]["name"]
    away = match["awayTeam"]["name"]

    utc_date = match.get("utcDate")

    if not utc_date:
        return []

    start_utc = datetime.fromisoformat(
        utc_date.replace("Z", "+00:00")
    )

    start = start_utc.astimezone(TZ)

    match_id = match["id"]
    matchday = match.get("matchday", "")
    status = match.get("status", "")
STATUS_TEXT = {
    "SCHEDULED": "Tijdstip nog niet bekend",
    "TIMED": "Tijdstip vastgesteld",
    "IN_PLAY": "Wedstrijd bezig",
    "PAUSED": "Rust",
    "FINISHED": "Gespeeld",
    "POSTPONED": "Uitgesteld",
    "CANCELLED": "Afgelast",
}

status_text = STATUS_TEXT.get(status, status)
    
    location = STADIUMS.get(home, "")
    summary = f"⚽ {home} – {away}"

    description_parts = [
        team["calendar_name"].replace("Voetbalagenda – ", ""),
        "Bron: football-data.org",
    ]

    if matchday:
        description_parts.append(f"Speelronde: {matchday}")

    if status:
        description_parts.append(f"Status: {status_text}")

    # Hier gebruiken we echte nieuwe regels.
    # escape_ics zet die daarna correct om voor het ICS-bestand.
    description = "\n".join(description_parts)

    now = datetime.now(tz=UTC)

    lines = [
        "BEGIN:VEVENT",

        # UID bewust hetzelfde gehouden als in de oude kalender.
        # Daardoor worden bestaande afspraken bijgewerkt
        # in plaats van dubbel toegevoegd.
        f"UID:football-data-{match_id}@abe-agenda",

        f"DTSTAMP:{now.strftime('%Y%m%dT%H%M%SZ')}",
    ]

    if status in TIMED_STATUSES:
        # Tijdstip is definitief bekend.
        end = start + timedelta(hours=2)

        lines.extend(
            [
                f"DTSTART;TZID=Europe/Amsterdam:{start.strftime('%Y%m%dT%H%M%S')}",
                f"DTEND;TZID=Europe/Amsterdam:{end.strftime('%Y%m%dT%H%M%S')}",
            ]
        )

    else:
        # Tijdstip is nog niet definitief bekend.
        # Wedstrijd wordt daarom als hele-dag-afspraak weergegeven.
        match_date = start.date()
        next_date = match_date + timedelta(days=1)

        lines.extend(
            [
                f"DTSTART;VALUE=DATE:{match_date.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{next_date.strftime('%Y%m%d')}",
            ]
        )

    lines.extend(
        [
            f"SUMMARY:{escape_ics(summary)}",
            f"LOCATION:{escape_ics(location)}",
            f"DESCRIPTION:{escape_ics(description)}",
            "END:VEVENT",
        ]
    )

    return lines


def create_calendar(matches: list[dict], team_key: str) -> None:
    team = TEAMS[team_key]

    selected_matches = [
        match
        for match in matches
        if team_match(match, team["names"])
    ]

    selected_matches.sort(
        key=lambda match: match.get("utcDate", "")
    )

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Voetbalagenda//Wedstrijdkalender//NL",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{team['calendar_name']}",
        "X-WR-TIMEZONE:Europe/Amsterdam",
        f"X-WR-CALDESC:Automatisch bijgewerkte kalender van "
        f"{team['calendar_name'].replace('Voetbalagenda – ', '')}.",
    ]

    for match in selected_matches:
        lines.extend(make_event(match, team_key))

    lines.append("END:VCALENDAR")

    team["output"].write_text(
        "\r\n".join(lines) + "\r\n",
        encoding="utf-8",
    )

    print(
        f"{team['output']} aangemaakt met "
        f"{len(selected_matches)} wedstrijden."
    )


def main() -> None:
    matches = fetch_matches()

    print(f"Totaal aantal Eredivisie-wedstrijden: {len(matches)}")

    for team_key in TEAMS:
        create_calendar(matches, team_key)


if __name__ == "__main__":
    main()
