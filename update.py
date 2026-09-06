import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


# ============================================================
# PODESAVANJA
# ============================================================

CALENDAR_URL = "https://turskeserije.tv/kalendar/"

MAP_FILE = "series-map.json"
OUTPUT_FILE = "next-episodes.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    )
}

# TurskeSerije kalendar koristi GMT +1
SOURCE_TIMEZONE = timezone(timedelta(hours=1))


# ============================================================
# UCITAVANJE JSON FAJLA
# ============================================================

def load_json(filename):
    path = Path(filename)

    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as e:
        print(f"Greska pri ucitavanju {filename}: {e}")
        return {}


# ============================================================
# CUVANJE JSON FAJLA
# ============================================================

def save_json(filename, data):
    path = Path(filename)

    with path.open("w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

        f.write("\n")


# ============================================================
# NORMALIZACIJA
# ============================================================

def normalize(text):
    if not text:
        return ""

    text = unicodedata.normalize("NFKD", text)

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    text = text.lower()

    text = re.sub(r"[^a-z0-9]+", "-", text)

    text = text.strip("-")

    return text


# ============================================================
# IZDVAJANJE SLUGA IZ URL-a
# ============================================================

def extract_slug(url):
    if not url:
        return None

    match = re.search(
        r"turskeserije\.tv/([^/?#]+)/?",
        url
    )

    if not match:
        return None

    return match.group(1).strip().lower()


# ============================================================
# DATUM
# ============================================================

MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "maj": 5,
    "jun": 6,
    "jul": 7,
    "avg": 8,
    "sep": 9,
    "okt": 10,
    "nov": 11,
    "dec": 12,

    # ako sajt eventualno koristi engleske nazive
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12
}


def parse_date(day_text, time_text):
    """
    Primer:

    day_text  = 'subota 12. sep'
    time_text = '23:59 (GMT +1)'

    Rezultat:

    2026-09-12T23:59:00+01:00
    """

    if not day_text:
        return None

    if not time_text:
        return None

    day_text = day_text.strip().lower()
    time_text = time_text.strip().lower()

    # --------------------------------------------------------
    # DAN
    # --------------------------------------------------------

    match = re.search(
        r"(\d{1,2})\.\s*([a-z]+)",
        day_text
    )

    if not match:
        return None

    day = int(match.group(1))
    month_name = match.group(2)

    month = MONTHS.get(month_name)

    if not month:
        return None

    # --------------------------------------------------------
    # VREME
    # --------------------------------------------------------

    time_match = re.search(
        r"(\d{1,2}):(\d{2})",
        time_text
    )

    if not time_match:
        return None

    hour = int(time_match.group(1))
    minute = int(time_match.group(2))

    # --------------------------------------------------------
    # GODINA
    # --------------------------------------------------------

    now = datetime.now(SOURCE_TIMEZONE)

    year = now.year

    # Ako je kalendar na prelazu godine
    # i datum je vec prosao dovoljno daleko,
    # pokusavamo sledecu godinu.
    try:
        result = datetime(
            year,
            month,
            day,
            hour,
            minute,
            tzinfo=SOURCE_TIMEZONE
        )

        # Ako je datum vise od ~6 meseci u proslosti,
        # pretpostavljamo sledecu godinu.
        if result < now - timedelta(days=180):
            result = datetime(
                year + 1,
                month,
                day,
                hour,
                minute,
                tzinfo=SOURCE_TIMEZONE
            )

        return result

    except ValueError:
        return None


# ============================================================
# EPIZODA
# ============================================================

def extract_episode(text):
    if not text:
        return None

    match = re.search(
        r"Epizoda\s+(\d+)",
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    return int(match.group(1))


# ============================================================
# UCITAVANJE KALENDARA
# ============================================================

def fetch_calendar():
    print("Preuzimam kalendar...")

    response = requests.get(
        CALENDAR_URL,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    print(
        f"Kalendar preuzet: "
        f"{len(response.text):,} karaktera"
    )

    return response.text


# ============================================================
# PARSIRANJE KALENDARA
# ============================================================

def parse_calendar(html):
    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    results = []

    # --------------------------------------------------------
    # Prvo trazimo kalendarske dane
    # --------------------------------------------------------

    slides = soup.select(
        ".swiper-slide"
    )

    print(
        f"Pronadjeno kalendarskih blokova: "
        f"{len(slides)}"
    )

    for slide in slides:

        # ----------------------------------------------------
        # DATUM
        # ----------------------------------------------------

        heading = slide.find("h2")

        if not heading:
            continue

        day_text = heading.get_text(
            " ",
            strip=True
        )

        # ----------------------------------------------------
        # SERIJE
        # ----------------------------------------------------

        links = slide.select(
            'a[href*="turskeserije.tv/"]'
        )

        for link in links:

            href = link.get("href")

            slug = extract_slug(href)

            if not slug:
                continue

            # ------------------------------------------------
            # NASLOV
            # ------------------------------------------------

            title_element = link.find("h3")

            title = ""

            if title_element:
                title = title_element.get_text(
                    " ",
                    strip=True
                )

            # ------------------------------------------------
            # SPANOVI
            # ------------------------------------------------

            spans = link.find_all("span")

            episode_text = ""

            time_text = ""

            if len(spans) >= 1:
                episode_text = spans[0].get_text(
                    " ",
                    strip=True
                )

            if len(spans) >= 2:
                time_text = spans[1].get_text(
                    " ",
                    strip=True
                )

            # ------------------------------------------------
            # EPIZODA
            # ------------------------------------------------

            episode = extract_episode(
                episode_text
            )

            # ------------------------------------------------
            # DATUM
            # ------------------------------------------------

            date = parse_date(
                day_text,
                time_text
            )

            if not date:
                continue

            # ------------------------------------------------
            # REZULTAT
            # ------------------------------------------------

            item = {
                "slug": slug,
                "title": title,
                "episode": episode,
                "date": date
            }

            results.append(item)

    print(
        f"Ukupno pronadjeno termina: "
        f"{len(results)}"
    )

    return results


# ============================================================
# TRAZENJE SLEDECE EPIZODE
# ============================================================

def find_next_episode(items, slug):
    now = datetime.now(
        SOURCE_TIMEZONE
    )

    matches = []

    for item in items:

        if item["slug"] != slug:
            continue

        date = item["date"]

        if date <= now:
            continue

        matches.append(item)

    if not matches:
        return None

    matches.sort(
        key=lambda x: x["date"]
    )

    return matches[0]


# ============================================================
# GLAVNI PROGRAM
# ============================================================

def main():

    print()
    print("=" * 60)
    print(" UPDATE NEXT EPISODES")
    print("=" * 60)
    print()

    # --------------------------------------------------------
    # MAPA TVOJ ID -> NJIHOV SLUG
    # --------------------------------------------------------

    series_map = load_json(
        MAP_FILE
    )

    if not series_map:

        print(
            f"Greska: {MAP_FILE} je prazan "
            f"ili ne postoji."
        )

        return

    print(
        f"Pronadjeno serija u mapi: "
        f"{len(series_map)}"
    )

    print()

    # --------------------------------------------------------
    # KALENDAR
    # --------------------------------------------------------

    html = fetch_calendar()

    calendar_items = parse_calendar(
        html
    )

    print()

    # --------------------------------------------------------
    # REZULTAT
    # --------------------------------------------------------

    output = {}

    # --------------------------------------------------------
    # SVAKA TVOJA SERIJA
    # --------------------------------------------------------

    for internal_id, source_slug in series_map.items():

        source_slug = source_slug.strip().lower()

        print(
            f"[{internal_id}] -> "
            f"{source_slug}"
        )

        next_episode = find_next_episode(
            calendar_items,
            source_slug
        )

        if not next_episode:

            print(
                "  Nema sledece epizode."
            )

            output[internal_id] = {
                "sourceSlug": source_slug,
                "nextEpisode": None
            }

            continue

        date = next_episode["date"]

        iso_date = date.isoformat()

        output[internal_id] = {
            "sourceSlug": source_slug,
            "nextEpisode": iso_date,
            "episode": next_episode["episode"],
            "title": next_episode["title"]
        }

        print(
            f"  Epizoda: "
            f"{next_episode['episode']}"
        )

        print(
            f"  Datum: "
            f"{iso_date}"
        )

    # --------------------------------------------------------
    # CUVANJE
    # --------------------------------------------------------

    save_json(
        OUTPUT_FILE,
        output
    )

    print()
    print(
        f"Sacuvano u: {OUTPUT_FILE}"
    )

    print()
    print("=" * 60)
    print(" GOTOVO")
    print("=" * 60)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
