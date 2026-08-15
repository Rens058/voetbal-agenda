from __future__ import annotations

import json
import os
import re
import unicodedata
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


MATCHES_API_URL = (
    "https://api.football-data.org/v4/competitions/DED/matches"
)

TZ = ZoneInfo("Europe/Amsterdam")
UTC = ZoneInfo("UTC")


# Bestaande bestandsnamen houden we bewust in stand.
# Zo blijven bestaande abonnementen gewoon werken.
FILENAME_OVERRIDES = {
    "SC Heerenveen": "heerenveen.ics",
    "SC Cambuur-Leeuwarden": "cambuur.ics",
}


# Nettere clubnamen voor weergave.
DISPLAY_NAME_OVERRIDES = {
    "SC Cambuur-Leeuwarden": "SC Cambuur",
}


# Voor deze clubs weten we het stadion zeker.
# Andere stadions kunnen we later automatisch of handmatig aanvullen.
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


# Vertaling van technische API-statussen naar duidelijke voetbaltaal.
STATUS_TEXT = {
    "SCHEDULED": "Tijdstip nog niet bekend",
    "TIMED": "Tijdstip vastgesteld",
    "IN_PLAY": "Wedstrijd bezig",
    "PAUSED": "Rust",
    "FINISHED": "Gespeeld",
    "POSTPONED": "Uitgesteld",
    "CANCELLED": "Afgelast",
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
        MATCHES_API_URL,
        headers={
            "X-Auth-Token": token,
            "User-Agent": "MijnVoetbalagenda/2.0",
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))

    return data["matches"]


def display_name(team_name: str) -> str:
    return DISPLAY_NAME_OVERRIDES.get(team_name, team_name)


def slugify(text: str) -> str:
    """
    Zet een clubnaam om naar een nette bestandsnaam.

    Voorbeeld:
    'Fortuna Sittard' -> 'fortuna-sittard'
    """
    normalized = unicodedata.normalize("NFKD", text)

    ascii_text = normalized.encode(
        "ascii",
        "ignore",
    ).decode("ascii")

    ascii_text = ascii_text.lower()

    ascii_text = re.sub(
        r"[^a-z0-9]+",
        "-",
        ascii_text,
    )

    return ascii_text.strip("-")


def filename_for_team(team_name: str) -> str:
    if team_name in FILENAME_OVERRIDES:
        return FILENAME_OVERRIDES[team_name]

    return f"{slugify(display_name(team_name))}.ics"


def get_teams(matches: list[dict]) -> list[str]:
    """
    Haal automatisch alle clubs uit de Eredivisie-wedstrijden.
    """
    teams: set[str] = set()

    for match in matches:
        home = match.get("homeTeam", {}).get("name")
        away = match.get("awayTeam", {}).get("name")

        if home:
            teams.add(home)

        if away:
            teams.add(away)

    return sorted(
        teams,
        key=lambda name: display_name(name).lower(),
    )


def team_match(match: dict, team_name: str) -> bool:
    home = match["homeTeam"]["name"]
    away = match["awayTeam"]["name"]

    return home == team_name or away == team_name


def make_event(match: dict, team_name: str) -> list[str]:
    home = match["homeTeam"]["name"]
    away = match["awayTeam"]["name"]

    home_display = display_name(home)
    away_display = display_name(away)

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
    status_text = STATUS_TEXT.get(status, status)

    location = STADIUMS.get(home, "")

    summary = (
        f"⚽ {home_display} – {away_display}"
    )

    description_parts = [
        display_name(team_name),
        "Bron: football-data.org",
    ]

    if matchday:
        description_parts.append(
            f"Speelronde: {matchday}"
        )

    if status:
        description_parts.append(
            f"Status: {status_text}"
        )

    description = "\n".join(description_parts)

    now = datetime.now(tz=UTC)

    lines = [
        "BEGIN:VEVENT",

        # Bewust hetzelfde UID-formaat als in de bestaande agenda's.
        # Zo voorkomen we dubbele wedstrijden bij bestaande abonnees.
        f"UID:football-data-{match_id}@abe-agenda",

        f"DTSTAMP:{now.strftime('%Y%m%dT%H%M%SZ')}",
    ]

    if status in TIMED_STATUSES:
        end = start + timedelta(hours=2)

        lines.extend(
            [
                (
                    "DTSTART;TZID=Europe/Amsterdam:"
                    f"{start.strftime('%Y%m%dT%H%M%S')}"
                ),
                (
                    "DTEND;TZID=Europe/Amsterdam:"
                    f"{end.strftime('%Y%m%dT%H%M%S')}"
                ),
            ]
        )

    else:
        match_date = start.date()
        next_date = match_date + timedelta(days=1)

        lines.extend(
            [
                (
                    "DTSTART;VALUE=DATE:"
                    f"{match_date.strftime('%Y%m%d')}"
                ),
                (
                    "DTEND;VALUE=DATE:"
                    f"{next_date.strftime('%Y%m%d')}"
                ),
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


def create_calendar(
    matches: list[dict],
    team_name: str,
) -> dict:
    selected_matches = [
        match
        for match in matches
        if team_match(match, team_name)
    ]

    selected_matches.sort(
        key=lambda match: match.get(
            "utcDate",
            "",
        )
    )

    club_name = display_name(team_name)
    calendar_name = (
        f"Voetbalagenda – {club_name}"
    )

    output = Path(
        filename_for_team(team_name)
    )

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Voetbalagenda//Wedstrijdkalender//NL",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{calendar_name}",
        "X-WR-TIMEZONE:Europe/Amsterdam",
        (
            "X-WR-CALDESC:"
            "Automatisch bijgewerkte kalender van "
            f"{club_name}."
        ),
    ]

    for match in selected_matches:
        lines.extend(
            make_event(
                match,
                team_name,
            )
        )

    lines.append("END:VCALENDAR")

    output.write_text(
        "\r\n".join(lines) + "\r\n",
        encoding="utf-8",
    )

    print(
        f"{output} aangemaakt met "
        f"{len(selected_matches)} wedstrijden."
    )

    return {
        "name": club_name,
        "file": output.name,
        "matches": len(selected_matches),
    }


def create_clubs_json(clubs: list[dict]) -> None:
    """
    Dit bestand kunnen we straks gebruiken om de website
    automatisch alle beschikbare clubs te laten tonen.
    """
    Path("clubs.json").write_text(
        json.dumps(
            clubs,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        f"clubs.json aangemaakt met "
        f"{len(clubs)} clubs."
    )


def main() -> None:
    matches = fetch_matches()

    print(
        f"Totaal aantal Eredivisie-wedstrijden: "
        f"{len(matches)}"
    )

    teams = get_teams(matches)

    print(
        f"Aantal Eredivisieclubs gevonden: "
        f"{len(teams)}"
    )

    clubs = []

    for team_name in teams:
        club = create_calendar(
            matches,
            team_name,
        )

        clubs.append(club)

    create_clubs_json(clubs)

    print()
    print("Klaar.")
    print(
        f"{len(clubs)} voetbalagenda's "
        "aangemaakt."
    )


if __name__ == "__main__":
    main()
