import json
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone


# ============================================================
# PODEŠAVANJA
# ============================================================

MAP_FILE = "series-map.json"
OUTPUT_FILE = "next-episodes.json"

BASE_URL = "https://turskeserije.tv/"

# Koliko dana kalendar treba da pokrije
DAYS_TO_SHOW = 14

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "sr-RS,sr;q=0.9,en-US;q=0.8,en;q=0.7",
}


# ============================================================
# NAZIVI DANA
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
# JSON
# ============================================================

def load_json(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# PREUZIMANJE STRANICE
# ============================================================

def fetch_page(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        response.raise_for_status()

        return response.text

    except Exception as e:
        print(f"   ❌ Greška: {e}")
        return None


# ============================================================
# PRONALAŽENJE DATUMA EPIZODE
# ============================================================

def parse_countdown(soup):

    # --------------------------------------------------------
    # 1. PRVO TRAŽIMO TVSHOW COUNTDOWN
    # --------------------------------------------------------

    countdown = soup.find(
        id="tvshow-countdown"
    )

    if countdown:

        text = countdown.get_text(
            " ",
            strip=True
        )

        # Ako je serija pauzirana
        if "pauzirana" in text.lower():
            return None

        # --------------------------------------------
        # data-target-time
        # --------------------------------------------

        target = countdown.get(
            "data-target-time"
        )

        if target:
            return target

        # --------------------------------------------
        # Ako nema data-target-time,
        # tražimo datum u tekstu
        # --------------------------------------------

        match = re.search(
            r"(\d{2}/\d{2}/\d{4})\s+"
            r"(\d{1,2}:\d{2})"
            r"\s*GMT\s*([+-]\d{1,2})?",
            text,
            re.IGNORECASE
        )

        if match:

            date_part = match.group(1)
            time_part = match.group(2)
            timezone_part = match.group(3)

            if timezone_part:
                offset = int(timezone_part)

                return (
                    f"{datetime.strptime(date_part + ' ' + time_part, '%d/%m/%Y %H:%M').strftime('%Y-%m-%d')}"
                    f"T{time_part}:00"
                    f"{offset:+03d}:00"
                )

            return (
                f"{datetime.strptime(date_part + ' ' + time_part, '%d/%m/%Y %H:%M').strftime('%Y-%m-%d')}"
                f"T{time_part}:00"
            )

    # ========================================================
    # 2. REZERVNI NAČIN
    # ========================================================
    # Tražimo direktno po celoj stranici:
    #
    # Sledeća epizoda se očekuje
    # 23/09/2026 23:59 GMT +1
    # ========================================================

    full_text = soup.get_text(
        " ",
        strip=True
    )

    match = re.search(
        r"Sledeća\s+epizoda\s+se\s+očekuje\s+"
        r"(\d{2}/\d{2}/\d{4})\s+"
        r"(\d{1,2}:\d{2})"
        r"\s*GMT\s*([+-]\d{1,2})?",
        full_text,
        re.IGNORECASE
    )

    if match:

        date_part = match.group(1)
        time_part = match.group(2)
        timezone_part = match.group(3)

        dt = datetime.strptime(
            date_part + " " + time_part,
            "%d/%m/%Y %H:%M"
        )

        if timezone_part:

            offset = int(timezone_part)

            return (
                dt.strftime("%Y-%m-%d")
                + "T"
                + dt.strftime("%H:%M:%S")
                + f"{offset:+03d}:00"
            )

        return (
            dt.strftime("%Y-%m-%d")
            + "T"
            + dt.strftime("%H:%M:%S")
        )

    return None


# ============================================================
# DATUM
# ============================================================

def parse_target_datetime(value):

    if not value:
        return None

    value = value.strip()

    # --------------------------------------------------------
    # ISO FORMAT
    # --------------------------------------------------------

    try:

        dt = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        # BITNO:
        # NE PRETVARAMO TIMEZONE.
        #
        # Ako sajt kaže:
        #
        # 23:59 GMT +1
        #
        # ostaje:
        #
        # 23:59
        #
        # Ne pomeramo ga na 22:59 ili 00:59.
        # --------------------------------------------------------

        if dt.tzinfo is not None:
            dt = dt.replace(
                tzinfo=None
            )

        return dt

    except Exception:
        pass

    # --------------------------------------------------------
    # DD/MM/YYYY HH:MM
    # --------------------------------------------------------

    try:

        return datetime.strptime(
            value,
            "%d/%m/%Y %H:%M"
        )

    except Exception:
        pass

    # --------------------------------------------------------
    # DD/MM/YYYY HH:MM:SS
    # --------------------------------------------------------

    try:

        return datetime.strptime(
            value,
            "%d/%m/%Y %H:%M:%S"
        )

    except Exception:
        pass

    return None


# ============================================================
# SLIKA
# ============================================================

def parse_image(soup):

    # --------------------------------------------------------
    # thumb
    # --------------------------------------------------------

    thumb = soup.select_one(
        "div.thumb.mvic-thumb"
    )

    if thumb:

        style = thumb.get(
            "style",
            ""
        )

        match = re.search(
            r'background-image\s*:\s*url\(["\']?(.*?)["\']?\)',
            style,
            re.IGNORECASE
        )

        if match:
            return match.group(1)

    # --------------------------------------------------------
    # img
    # --------------------------------------------------------

    selectors = [
        ".mvic-thumb img",
        ".poster img",
        ".post-thumb img",
        ".movie-thumb img",
        "meta[property='og:image']",
        "meta[name='twitter:image']",
    ]

    for selector in selectors:

        element = soup.select_one(
            selector
        )

        if not element:
            continue

        if element.name == "meta":

            value = element.get(
                "content"
            )

        else:

            value = (
                element.get("src")
                or element.get("data-src")
                or element.get("data-lazy-src")
                or element.get("data-original")
            )

        if value:
            return value

    return ""


# ============================================================
# GLAVNI PROGRAM
# ============================================================

def main():

    print()
    print("=" * 70)
    print(" TV KALENDAR - turskeserije.tv")
    print("=" * 70)
    print()

    # --------------------------------------------------------
    # UČITAVANJE MAP FILE
    # --------------------------------------------------------

    try:

        series_map = load_json(
            MAP_FILE
        )

    except Exception as e:

        print(
            f"❌ Ne mogu da učitam {MAP_FILE}: {e}"
        )

        return

    # --------------------------------------------------------
    # DATUMI
    # --------------------------------------------------------

    today = datetime.now().date()

    monday = (
        today
        - timedelta(
            days=today.weekday()
        )
    )

    end_date = (
        monday
        + timedelta(
            days=DAYS_TO_SHOW - 1
        )
    )

    print(
        f"📅 Period: "
        f"{monday} → {end_date}"
    )

    print()

    # --------------------------------------------------------
    # PRAZNI DANI
    # --------------------------------------------------------

    days = {}

    for i in range(DAYS_TO_SHOW):

        current_date = (
            monday
            + timedelta(days=i)
        )

        date_string = current_date.isoformat()

        days[date_string] = {
            "date": date_string,
            "day": DAY_NAMES[
                current_date.weekday()
            ],
            "episodes": []
        }

    # --------------------------------------------------------
    # STATISTIKA
    # --------------------------------------------------------

    total = 0
    found = 0
    added = 0
    errors = 0

    # --------------------------------------------------------
    # SVE SERIJE
    # --------------------------------------------------------

    for series_id, series_data in series_map.items():

        total += 1

        # ----------------------------------------------------
        # URL
        # ----------------------------------------------------

        if isinstance(series_data, str):

            source_url = series_data

        elif isinstance(series_data, dict):

            source_url = (
                series_data.get("url")
                or series_data.get("sourceUrl")
                or series_data.get("link")
            )

        else:

            source_url = None

        if not source_url:

            print(
                f"⚠️ {series_id} - nema URL"
            )

            errors += 1
            continue

        # ----------------------------------------------------
        # AKO JE RELATIVAN URL
        # ----------------------------------------------------

        if source_url.startswith("/"):

            source_url = (
                BASE_URL.rstrip("/")
                + source_url
            )

        elif not source_url.startswith("http"):

            source_url = (
                BASE_URL.rstrip("/")
                + "/"
                + source_url.lstrip("/")
            )

        print(
            f"[{total}] {series_id}"
        )

        # ----------------------------------------------------
        # STRANICA
        # ----------------------------------------------------

        html = fetch_page(
            source_url
        )

        if not html:

            errors += 1
            continue

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        # ----------------------------------------------------
        # DATUM
        # ----------------------------------------------------

        target_value = parse_countdown(
            soup
        )

        if not target_value:

            print(
                "   ⚪ Nema podatka o sledećoj epizodi"
            )

            continue

        # ----------------------------------------------------
        # DATETIME
        # ----------------------------------------------------

        target_dt = parse_target_datetime(
            target_value
        )

        if not target_dt:

            print(
                f"   ⚠️ Ne mogu da pročitam datum: "
                f"{target_value}"
            )

            continue

        found += 1

        episode_date = target_dt.date()

        # ----------------------------------------------------
        # PROVERA PERIODA
        # ----------------------------------------------------

        if not (
            monday
            <= episode_date
            <= end_date
        ):

            print(
                f"   ↪ Sledeća epizoda: "
                f"{episode_date} "
                f"{target_dt.strftime('%H:%M')} "
                f"(van perioda)"
            )

            continue

        # ----------------------------------------------------
        # SLIKA
        # ----------------------------------------------------

        image = parse_image(
            soup
        )

        # ----------------------------------------------------
        # DATUM STRING
        # ----------------------------------------------------

        date_string = (
            target_dt.strftime(
                "%d.%m.%Y"
            )
        )

        time_string = (
            target_dt.strftime(
                "%H:%M"
            )
        )

        date_iso = (
            target_dt.strftime(
                "%Y-%m-%d"
            )
        )

        # ----------------------------------------------------
        # EPIZODA
        # ----------------------------------------------------

        episode = {
            "id": series_id,
            "title": series_id,
            "sourceUrl": source_url,
            "nextEpisode": target_value,
            "date": date_string,
            "day": DAY_NAMES[
                target_dt.weekday()
            ],
            "time": time_string,
            "image": image
        }

        # ----------------------------------------------------
        # DODAVANJE
        # ----------------------------------------------------

        days[
            date_iso
        ]["episodes"].append(
            episode
        )

        added += 1

        print(
            f"   ✅ {date_string} "
            f"{time_string}"
        )

    # ========================================================
    # SORTIRANJE
    # ========================================================

    for date_data in days.values():

        date_data["episodes"].sort(
            key=lambda x: x.get(
                "time",
                "99:99"
            )
        )

    # ========================================================
    # FINALNI JSON
    # ========================================================

    result = {

        "updatedAt": datetime.now(
            timezone.utc
        ).isoformat(),

        "week": {

            "start": monday.isoformat(),

            "end": end_date.isoformat(),

            "days": DAYS_TO_SHOW
        },

        "days": days
    }

    # ========================================================
    # ČUVANJE
    # ========================================================

    save_json(
        OUTPUT_FILE,
        result
    )

    # ========================================================
    # STATISTIKA
    # ========================================================

    print()
    print("=" * 70)
    print(" GOTOVO")
    print("=" * 70)

    print(
        f"Ukupno serija:       {total}"
    )

    print(
        f"Pronađen termin:     {found}"
    )

    print(
        f"Upisano u kalendar:  {added}"
    )

    print(
        f"Greške:              {errors}"
    )

    print(
        f"Period:              {monday} → {end_date}"
    )

    print(
        f"Fajl:                {OUTPUT_FILE}"
    )

    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
