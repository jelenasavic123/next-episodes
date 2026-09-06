import json
import re
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup


CALENDAR_URL = "https://turskeserije.tv/kalendar/"
JSON_FILE = "next-episodes.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    )
}

# ============================================================
# POMOCNE FUNKCIJE
# ============================================================

def normalize(text):
    """
    Normalizuje naziv serije radi lakseg prepoznavanja.
    """

    text = text.lower().strip()

    replacements = {
        "č": "c",
        "ć": "c",
        "š": "s",
        "ž": "z",
        "đ": "d",
        "ö": "o",
        "ü": "u",
        "ı": "i",
        "ğ": "g",
        "İ": "i",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"\([^)]*\)", "", text)

    text = re.sub(r"[^a-z0-9]+", "-", text)

    text = re.sub(r"-+", "-", text)

    return text.strip("-")


def load_existing():
    """
    Ucitava postojeci next-episodes.json.
    """

    try:
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    except FileNotFoundError:
        return {}

    except json.JSONDecodeError:
        print("Greska: next-episodes.json nije validan JSON.")
        return {}


def save_json(data):
    """
    Cuva JSON lepo formatiran.
    """

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

        f.write("\n")


# ============================================================
# UCITAVANJE KALENDARA
# ============================================================

def download_calendar():

    print("Ucitavam kalendar:")
    print(CALENDAR_URL)

    response = requests.get(
        CALENDAR_URL,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    print(
        "Kalendar ucitan:",
        response.status_code
    )

    return response.text


# ============================================================
# PARSIRANJE DATUMA
# ============================================================

MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def parse_calendar_date(day_text, month_text, time_text):
    """
    Pretvara:
        Sep 12
        23:59

    u:
        2026-09-12T23:59:00+01:00
    """

    match = re.search(
        r"([A-Za-z]+)\s+(\d{1,2})",
        day_text
    )

    if not match:
        return None

    month_name = match.group(1).lower()[:3]
    day = int(match.group(2))

    month = MONTHS.get(month_name)

    if not month:
        return None

    time_match = re.search(
        r"(\d{1,2}):(\d{2})",
        time_text
    )

    if not time_match:
        return None

    hour = int(time_match.group(1))
    minute = int(time_match.group(2))

    now = datetime.now(timezone.utc)

    year = now.year

    # Kalendar moze prelaziti u sledecu godinu.
    candidate = datetime(
        year,
        month,
        day,
        hour,
        minute,
        tzinfo=timezone(timedelta(hours=1))
    )

    if candidate < now - timedelta(days=30):
        candidate = datetime(
            year + 1,
            month,
            day,
            hour,
            minute,
            tzinfo=timezone(timedelta(hours=1))
        )

    return candidate.isoformat()


# ============================================================
# CITANJE KALENDARA
# ============================================================

def parse_calendar(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    entries = []

    current_day = None

    # Kalendar koristi H2 za dane,
    # a linkove za pojedinacne serije.
    for element in soup.find_all(["h2", "a"]):

        if element.name == "h2":

            text = element.get_text(
                " ",
                strip=True
            )

            # Primer:
            # Monday, Sep 7
            # Sunday, Sep 6
            if re.search(
                r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)",
                text,
                re.IGNORECASE
            ):
                current_day = text

            continue

        if element.name != "a":
            continue

        text = element.get_text(
            " ",
            strip=True
        )

        if not text:
            continue

        # Mora da sadrzi epizodu i vreme.
        episode_match = re.search(
            r"Epizoda\s+(\d+)",
            text,
            re.IGNORECASE
        )

        time_match = re.search(
            r"(\d{1,2}:\d{2})\s*\(GMT\s*\+1\)",
            text,
            re.IGNORECASE
        )

        if not episode_match or not time_match:
            continue

        # Izbacujemo "Epizoda X, Sezone Y..."
        series_part = re.split(
            r"\s+Epizoda\s+\d+",
            text,
            flags=re.IGNORECASE
        )[0].strip()

        episode_number = int(
            episode_match.group(1)
        )

        next_episode = parse_calendar_date(
            current_day or "",
            "",
            time_match.group(1)
        )

        if not next_episode:
            continue

        entries.append({
            "title": series_part,
            "normalized": normalize(series_part),
            "episode": episode_number,
            "nextEpisode": next_episode
        })

    return entries


# ============================================================
# PRONALAZENJE NAJBOLJEG DATUMA
# ============================================================

def choose_next(entries):

    now = datetime.now(timezone.utc)

    future = []

    for item in entries:

        try:
            date = datetime.fromisoformat(
                item["nextEpisode"]
            )

        except Exception:
            continue

        if date.astimezone(timezone.utc) >= now:
            future.append(item)

    if not future:
        return None

    future.sort(
        key=lambda x: datetime.fromisoformat(
            x["nextEpisode"]
        )
    )

    return future[0]


# ============================================================
# GLAVNI PROGRAM
# ============================================================

def main():

    print()
    print("==========================================")
    print(" NEXT EPISODE UPDATER")
    print("==========================================")
    print()

    # --------------------------------------------------------
    # 1. Ucitavanje postojeceg JSON-a
    # --------------------------------------------------------

    data = load_existing()

    print(
        "Postojecih serija:",
        len(data)
    )

    print()

    # --------------------------------------------------------
    # 2. Ucitavanje kalendara
    # --------------------------------------------------------

    html = download_calendar()

    # --------------------------------------------------------
    # 3. Parsiranje
    # --------------------------------------------------------

    entries = parse_calendar(html)

    print(
        "Pronadjeno stavki u kalendaru:",
        len(entries)
    )

    print()

    if not entries:
        print(
            "GRESKA: Kalendar nije parsiran."
        )

        return

    # --------------------------------------------------------
    # 4. Grupisanje po seriji
    # --------------------------------------------------------

    calendar_series = {}

    for item in entries:

        key = item["normalized"]

        calendar_series.setdefault(
            key,
            []
        ).append(item)

    # --------------------------------------------------------
    # 5. Azuriranje postojecih serija
    # --------------------------------------------------------

    updated = 0

    for series_id, info in data.items():

        # ----------------------------------------------------
        # Pokusaj direktnog poklapanja
        # ----------------------------------------------------

        candidates = calendar_series.get(
            normalize(series_id),
            []
        )

        # ----------------------------------------------------
        # Ako nema direktnog poklapanja,
        # pokusavamo preko postojeceg title-a
        # ----------------------------------------------------

        if not candidates and isinstance(info, dict):

            title = info.get(
                "title",
                ""
            )

            if title:

                normalized_title = normalize(
                    title
                )

                candidates = calendar_series.get(
                    normalized_title,
                    []
                )

        # ----------------------------------------------------
        # Posebni nazivi koji se razlikuju na sajtu
        # ----------------------------------------------------

        aliases = {
            "koralna-vila": [
                "mercan-kosk",
                "mercan-kosk-koralna-palata"
            ],

            "gonul-dagi": [
                "gonul-dagi"
            ]
        }

        if not candidates:

            for alias in aliases.get(
                series_id,
                []
            ):

                candidates = calendar_series.get(
                    normalize(alias),
                    []
                )

                if candidates:
                    break

        # ----------------------------------------------------
        # Ako serija nije pronadjena
        # ----------------------------------------------------

        if not candidates:

            print(
                "NEMA POKLAPANJA:",
                series_id
            )

            continue

        # ----------------------------------------------------
        # Nadji najblizu buducu epizodu
        # ----------------------------------------------------

        next_item = choose_next(
            candidates
        )

        if not next_item:
            print(
                "Nema buduce epizode:",
                series_id
            )

            continue

        old_value = info.get(
            "nextEpisode"
        )

        new_value = next_item[
            "nextEpisode"
        ]

        # ----------------------------------------------------
        # Azuriranje
        # ----------------------------------------------------

        info["nextEpisode"] = new_value

        if old_value != new_value:

            updated += 1

            print(
                f"AZURIRANO: {series_id}"
            )

            print(
                f"  Epizoda: {next_item['episode']}"
            )

            print(
                f"  Datum:   {new_value}"
            )

        else:

            print(
                f"BEZ PROMENE: {series_id}"
            )

    # --------------------------------------------------------
    # 6. Cuvanje
    # --------------------------------------------------------

    save_json(data)

    print()
    print("==========================================")
    print(" GOTOVO")
    print("==========================================")
    print(
        "Azurirano:",
        updated
    )
    print(
        "Ukupno serija:",
        len(data)
    )
    print()


if __name__ == "__main__":
    main()
