import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


# ============================================================
# PODESAVANJA
# ============================================================

MAP_FILE = "series-map.json"
OUTPUT_FILE = "next-episodes.json"

SOURCE_TIMEZONE = ZoneInfo("Europe/Belgrade")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "sr-RS,sr;q=0.9,en-US;q=0.8,en;q=0.7",
}


# ============================================================
# DANI U NEDELJI
# ============================================================

DAY_NAMES = {
    0: "Ponedeljak",
    1: "Utorak",
    2: "Sreda",
    3: "Četvrtak",
    4: "Petak",
    5: "Subota",
    6: "Nedelja",
}


# ============================================================
# UCITAJ JSON
# ============================================================

def load_json(filename):

    path = Path(filename)

    if not path.exists():

        print(
            f"GRESKA: fajl ne postoji: {filename}"
        )

        return {}

    try:

        with path.open(
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception as e:

        print(
            f"GRESKA pri citanju {filename}: {e}"
        )

        return {}


# ============================================================
# SACUVAJ JSON
# ============================================================

def save_json(filename, data):

    path = Path(filename)

    with path.open(
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

        f.write("\n")


# ============================================================
# UCITAJ STRANICU
# ============================================================

def fetch_page(url):

    print(
        f"  Otvaram: {url}"
    )

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    print(
        f"  HTTP: {response.status_code}"
    )

    print(
        f"  HTML: {len(response.text):,} karaktera"
    )

    return response.text


# ============================================================
# DATUM SLEDECE EPIZODE
# ============================================================

def parse_countdown(soup):

    countdown = soup.find(
        id="tvshow-countdown"
    )

    if not countdown:

        print(
            "  NIJE PRONADJEN #tvshow-countdown"
        )

        return None

    # --------------------------------------------------------
    # DATA-TARGET-TIME
    # --------------------------------------------------------

    target_time = countdown.get(
        "data-target-time"
    )

    if target_time:

        target_time = target_time.strip()

        print(
            f"  Datum: {target_time}"
        )

        return target_time

    # --------------------------------------------------------
    # TEKST
    # --------------------------------------------------------

    text = countdown.get_text(
        " ",
        strip=True
    )

    print(
        f"  Countdown tekst: {text}"
    )

    # --------------------------------------------------------
    # PAUZIRANA SERIJA
    # --------------------------------------------------------

    if "pauzirana" in text.lower():

        print(
            "  Serija je trenutno pauzirana."
        )

        return None

    return None


# ============================================================
# PARSIRAJ DATUM
# ============================================================

def parse_target_datetime(value):

    if not value:
        return None

    value = value.strip()

    # --------------------------------------------------------
    # ISO DATUM
    # --------------------------------------------------------

    try:

        dt = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00"
            )
        )

        # Ako nema timezone, tretiramo ga kao Srbiju
        if dt.tzinfo is None:

            dt = dt.replace(
                tzinfo=SOURCE_TIMEZONE
            )

        else:

            dt = dt.astimezone(
                SOURCE_TIMEZONE
            )

        return dt

    except Exception:
        pass

    # --------------------------------------------------------
    # REZERVA - DATUM BEZ ISO FORMATIRANJA
    # --------------------------------------------------------

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]

    for fmt in formats:

        try:

            dt = datetime.strptime(
                value,
                fmt
            )

            return dt.replace(
                tzinfo=SOURCE_TIMEZONE
            )

        except Exception:
            continue

    return None


# ============================================================
# PRONADJI SLIKU
# ============================================================

def parse_image(soup, source_url):

    # --------------------------------------------------------
    # GLAVNI POSTER
    #
    # div.thumb.mvic-thumb
    # background-image: url(...)
    # --------------------------------------------------------

    image_box = soup.select_one(
        "div.thumb.mvic-thumb"
    )

    if image_box:

        style = image_box.get(
            "style",
            ""
        )

        match = re.search(
            r"background-image\s*:\s*url\(['\"]?([^'\")]+)",
            style,
            re.IGNORECASE
        )

        if match:

            image_url = match.group(1).strip()

            image_url = urljoin(
                source_url,
                image_url
            )

            print(
                f"  Slika: {image_url}"
            )

            return image_url

        # ----------------------------------------------------
        # IMG UNUTAR POSTERA
        # ----------------------------------------------------

        image = image_box.find(
            "img"
        )

        if image:

            image_url = (
                image.get("src")
                or image.get("data-src")
                or image.get("data-lazy-src")
            )

            if image_url:

                image_url = image_url.strip()

                image_url = urljoin(
                    source_url,
                    image_url
                )

                print(
                    f"  Slika: {image_url}"
                )

                return image_url

    # --------------------------------------------------------
    # REZERVA
    # --------------------------------------------------------

    image_box = soup.select_one(
        ".mvic-thumb"
    )

    if image_box:

        style = image_box.get(
            "style",
            ""
        )

        match = re.search(
            r"background-image\s*:\s*url\(['\"]?([^'\")]+)",
            style,
            re.IGNORECASE
        )

        if match:

            image_url = match.group(1).strip()

            image_url = urljoin(
                source_url,
                image_url
            )

            print(
                f"  Slika: {image_url}"
            )

            return image_url

    # --------------------------------------------------------
    # NIJE PRONADJENA
    # --------------------------------------------------------

    print(
        "  Slika nije pronadjena."
    )

    return None


# ============================================================
# GLAVNI PROGRAM
# ============================================================

def main():

    print()
    print("=" * 70)
    print(" NEXT EPISODES - NEDELJNI KALENDAR")
    print("=" * 70)
    print()

    # ========================================================
    # TRENUTNI DATUM
    # ========================================================

    now = datetime.now(
        SOURCE_TIMEZONE
    )

    today = now.date()

    # ========================================================
    # TEKUCA NEDELJA
    # PON - NED
    # ========================================================

    monday = (
        today
        - timedelta(
            days=today.weekday()
        )
    )

    sunday = (
        monday
        + timedelta(
            days=6
        )
    )

    print(
        f"Danas: {today}"
    )

    print(
        f"Tekuca nedelja: "
        f"{monday} -> {sunday}"
    )

    print()

    # ========================================================
    # MAPA
    # ========================================================

    series_map = load_json(
        MAP_FILE
    )

    if not series_map:

        print(
            "Nema podataka u series-map.json"
        )

        return

    print(
        f"Pronadjeno serija: "
        f"{len(series_map)}"
    )

    print()

    # ========================================================
    # NAPRAVI 7 DANA
    # ========================================================

    days = {}

    for i in range(7):

        current_date = (
            monday
            + timedelta(days=i)
        )

        date_key = (
            current_date.isoformat()
        )

        days[date_key] = {

            "date":
                date_key,

            "day":
                DAY_NAMES[
                    current_date.weekday()
                ],

            "episodes":
                []

        }

    # ========================================================
    # STATISTIKA
    # ========================================================

    total_series = 0
    successful_dates = 0
    images_found = 0
    outside_week = 0
    paused = 0
    errors = 0

    # ========================================================
    # SVAKA SERIJA
    # ========================================================

    for internal_id, source_url in series_map.items():

        total_series += 1

        print(
            "-" * 70
        )

        print(
            f"Serija: {internal_id}"
        )

        print(
            f"Izvor: {source_url}"
        )

        # ----------------------------------------------------
        # PREUZMI STRANICU
        # ----------------------------------------------------

        try:

            html = fetch_page(
                source_url
            )

        except Exception as e:

            errors += 1

            print(
                f"  GRESKA: {e}"
            )

            continue

        # ----------------------------------------------------
        # BEAUTIFULSOUP
        # ----------------------------------------------------

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        # ----------------------------------------------------
        # DATUM SLEDECE EPIZODE
        # ----------------------------------------------------

        next_episode = parse_countdown(
            soup
        )

        if not next_episode:

            paused += 1

            print(
                "  Nema datuma sledece epizode."
            )

            continue

        # ----------------------------------------------------
        # PRETVORI U DATETIME
        # ----------------------------------------------------

        target_dt = parse_target_datetime(
            next_episode
        )

        if not target_dt:

            errors += 1

            print(
                f"  NEPREPOZNAT DATUM: "
                f"{next_episode}"
            )

            continue

        # ----------------------------------------------------
        # DATUM
        # ----------------------------------------------------

        target_date = target_dt.date()

        target_date_key = (
            target_date.isoformat()
        )

        # ----------------------------------------------------
        # SAMO TEKUCA NEDELJA
        # ----------------------------------------------------

        if (
            target_date < monday
            or target_date > sunday
        ):

            outside_week += 1

            print(
                f"  Van tekuce nedelje: "
                f"{target_date_key}"
            )

            continue

        # ----------------------------------------------------
        # DAN U NEDELJI
        # ----------------------------------------------------

        day_name = DAY_NAMES[
            target_date.weekday()
        ]

        # ----------------------------------------------------
        # SLIKA
        # ----------------------------------------------------

        image = parse_image(
            soup,
            source_url
        )

        if image:

            images_found += 1

        # ----------------------------------------------------
        # EPIZODA
        # ----------------------------------------------------

        episode = {

            "id":
                internal_id,

            "title":
                internal_id,

            "sourceUrl":
                source_url,

            "nextEpisode":
                next_episode,

            "date":
                target_date_key,

            "day":
                day_name,

            "time":
                target_dt.strftime(
                    "%H:%M"
                ),

            "image":
                image
        }

        # ----------------------------------------------------
        # DODAJ U DAN
        # ----------------------------------------------------

        days[
            target_date_key
        ][
            "episodes"
        ].append(
            episode
        )

        successful_dates += 1

        print(
            f"  OK: "
            f"{target_date_key} "
            f"({day_name}) "
            f"{target_dt.strftime('%H:%M')}"
        )

    # ========================================================
    # SORTIRANJE
    # ========================================================

    for date_key in days:

        days[
            date_key
        ][
            "episodes"
        ].sort(
            key=lambda item: (
                item.get("time")
                or "99:99",

                item.get("title")
                or ""
            )
        )

    # ========================================================
    # UKUPAN BROJ EPIZODA
    # ========================================================

    total_episodes = sum(
        len(
            day["episodes"]
        )
        for day in days.values()
    )

    # ========================================================
    # FINALNI JSON
    # ========================================================

    output = {

        "updatedAt":
            now.isoformat(),

        "week": {

            "start":
                monday.isoformat(),

            "end":
                sunday.isoformat(),

            "days":
                7

        },

        "days":
            days

    }

    # ========================================================
    # SACUVAJ
    # ========================================================

    save_json(
        OUTPUT_FILE,
        output
    )

    # ========================================================
    # REZULTAT
    # ========================================================

    print()
    print("=" * 70)
    print(" GOTOVO")
    print("=" * 70)
    print()

    print(
        f"Ukupno serija: "
        f"{total_series}"
    )

    print(
        f"Pronadjeni datumi: "
        f"{successful_dates}"
    )

    print(
        f"Pronadjene slike: "
        f"{images_found}"
    )

    print(
        f"Van tekuce nedelje: "
        f"{outside_week}"
    )

    print(
        f"Bez datuma / pauzirane: "
        f"{paused}"
    )

    print(
        f"Greske: "
        f"{errors}"
    )

    print(
        f"Ukupno u kalendaru: "
        f"{total_episodes}"
    )

    print()

    print(
        "KALENDAR:"
    )

    print()

    for date_key, day in days.items():

        print(
            f"{day['day']} "
            f"{date_key}: "
            f"{len(day['episodes'])} epizoda"
        )

        for episode in day["episodes"]:

            print(
                f"    "
                f"{episode['time']} - "
                f"{episode['id']}"
            )

    print()

    print(
        f"Sacuvano: "
        f"{OUTPUT_FILE}"
    )

    print()

    print("=" * 70)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
