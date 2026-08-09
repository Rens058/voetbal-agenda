from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


OUTPUT = Path("heerenveen.ics")
TZ = ZoneInfo("Europe/Amsterdam")

API_URL = "https://api.football-data.org/v4/competitions/DED/matches"
API_TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN")

TEAM_KEYWORDS = ["heerenveen", "sc heerenveen"]


@dataclass
class Match:
    start: datetime
    home: str
    away: str

    @property
    def is_home(self) -> bool:
        return "heerenveen" in self.home.lower()

    @property
    def title(self) -> str:
        label = "Thuis" if self.is_home else "Uit"
        return f"{self.home} - {self.away} ({label})"


def fetch_matches() -> dict | None:
    if not API_TOKEN:
        print("FOUT: FOOTBALL_DATA_TOKEN ontbreekt.")
        return None

    request = urllib.request.Request(
        API_URL,
        headers={
            "X-Auth-Token": API_TOKEN,
            "User-Agent": "Abe-Agenda/1.0",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 200:
                print(f"API gaf HTTP-status {response.status}.")
                return None

            return json.loads(response.read().decode("utf-8"))

    except Exception as exc:
        print(f"Football-Data API niet beschikbaar: {exc}")
        return None


def is_heerenveen(home: str, away: str) -> bool:
    combined = f"{home} {away}".lower()

    return any(keyword in combined for keyword in TEAM_KEYWORDS)


def parse_matches(data: dict) -> list[Match]:
    matches: list[Match] = []

    for item in data.get("matches", []):
        home = item.get("homeTeam", {}).get("name", "").strip()
        away = item.get("awayTeam", {}).get("name", "").strip()
        utc_date = item.get("utcDate")

        if not home or not away or not utc_date:
            continue

        if not is_heerenveen(home, away):
            continue

        try:
            start_utc = datetime.fromisoformat(
                utc_date.replace("Z", "+00:00")
            )

            start_local = start_utc.astimezone(TZ)

        except ValueError:
            print(
                f"Ongeldige datum overgeslagen: "
                f"{home} - {away}: {utc_date}"
            )
            continue

        matches.append(
            Match(
                start=start_local,
                home=home,
                away=away,
            )
        )

    return sorted(matches, key=lambda match: match.start)


def escape_ics(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace(";", "\\;")
        .replace("\n", "\\n")
    )


def ics_time(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def make_uid(match: Match) -> str:
    """
    UID bewust NIET gebaseerd op datum/tijd.

    Hierdoor blijft dezelfde wedstrijd dezelfde agenda-afspraak
    wanneer KNVB/Football-Data later datum of aftraptijd wijzigt.
    """
    uid_base = f"{match.home}-{match.away}".lower()
    uid_base = re.sub(r"[^a-z0-9]+", "-", uid_base).strip("-")

    return f"{uid_base}@abe-agenda"


def make_ics(matches: list[Match]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Abe Agenda//SC Heerenveen//NL",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Abe Agenda - SC Heerenveen",
        "X-WR-TIMEZONE:Europe/Amsterdam",
    ]

    for match in matches:
        end = match.start + timedelta(hours=2)

        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{make_uid(match)}",
                f"DTSTAMP:{now}",
                f"DTSTART;TZID=Europe/Amsterdam:{ics_time(match.start)}",
                f"DTEND;TZID=Europe/Amsterdam:{ics_time(end)}",
                f"SUMMARY:{escape_ics(match.title)}",
                (
                    "DESCRIPTION:"
                    + escape_ics(
                        "Abe Agenda - SC Heerenveen kalender. "
                        "Bron: Football-Data / KNVB wedstrijdschema."
                    )
                ),
                "END:VEVENT",
            ]
        )

    lines.append("END:VCALENDAR")

    return "\r\n".join(lines) + "\r\n"


def main() -> int:
    print("Wedstrijden ophalen uit Football-Data API...")
    print(f"Endpoint: {API_URL}")

    data = fetch_matches()

    if data is None:
        print(
            "Geen bruikbare API-data ontvangen. "
            "Bestaande heerenveen.ics blijft behouden."
        )
        return 1

    matches = parse_matches(data)

    if not matches:
        print(
            "Geen SC Heerenveen-wedstrijden gevonden. "
            "Bestaande heerenveen.ics blijft behouden."
        )
        return 1

    OUTPUT.write_text(
        make_ics(matches),
        encoding="utf-8",
        newline="",
    )

    print()
    print(f"{OUTPUT} bijgewerkt met {len(matches)} wedstrijden.")
    print()

    for match in matches:
        print(
            f"{match.start:%d-%m-%Y %H:%M} | "
            f"{match.home} - {match.away}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
