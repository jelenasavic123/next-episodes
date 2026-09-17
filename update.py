import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


# ============================================================
# PODEŠAVANJA
# ============================================================

MAP_FILE = "series-map.json"
OUTPUT_FILE = "next-episodes.json"

BASE_URL = "https://turskeserije.tv/"

# Koliko dana unapred da proveravamo
# 14 = trenutna + sledeća nedelja
DAYS_TO_SHOW = 14


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": (
        "sr-RS,sr;q=0.9,en-US;q=0.8,en;q=0.7"
    ),
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
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
# UČITAVANJE JSON-a
# ============================================================

def load_json(filename):

    path = Path(filename)

    if not path.exists():

        raise FileNotFoundError(
            f"Fajl ne postoji: {filename}"
        )

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


# ============================================================
# ČUVANJE JSON-a
# ============================================================

def save_json(filename, data):

    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as f:

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
            timeout=30
        )

        response.raise_for_status()

        return response.text

    except Exception as e:

        print(
            f"   ❌ Greška pri učitavanju: {e}"
        )

        return None


# ============================================================
# PRONALAŽENJE COUNTDOWN-a
# ============================================================

def parse_countdown(soup):

    # --------------------------------------------------------
    # GLAVNI NAČIN
    # --------------------------------------------------------

    countdown = soup.find(
        id="tvshow-countdown"
    )

    if countdown:

        countdown_text = countdown.get_text(
            " ",
            strip=True
        ).lower()

        # Serija je pauzirana
        if "pauzirana" in countdown_text:

            return None

        target_time = countdown.get(
            "data-target-time"
        )

        if target_time:

            return target_time.strip()


    # ========================================================
    # DODATNI NAČIN
    #
    # Ako HTML promeni strukturu, pokušavamo pronaći
    # datum direktno u tekstu stranice.
    # ========================================================

    page_text = soup.get_text(
        " ",
        strip=True
    )

    # Primer:
    #
    # Sledeća epizoda se očekuje
    # 23/09/2026 23:59 GMT +1
    #
    # ili:
    #
    # 23/09/2026 23:59 GMT+1

    match = re.search(
        r"(\d{1,2})/(\d{1,2})/(\d{4})"
        r"\s+"
        r"(\d{1,2}):(\d{2})"
        r"\s*"
        r"GMT\s*([+-]\d{1,2})",
        page_text,
        re.IGNORECASE
    )

    if match:

        day = match.group(1).zfill(2)
        month = match.group(2).zfill(2)
        year = match.group(3)

        hour = match.group(4).zfill(2)
        minute = match.group(5)

        timezone = match.group(6)

        if not timezone.startswith(
            ("+", "-")
        ):

            timezone = "+" + timezone

        if len(timezone) == 2:

            timezone = (
                timezone[0]
                + "0"
                + timezone[1]
            )

        return (
            f"{year}-{month}-{day}"
            f"T{hour}:{minute}:00"
            f"{timezone}:00"
        )

    return None


# ============================================================
# PARSIRANJE DATUMA
#
# BITNO:
# NE PRETVARAMO TIMEZONE.
#
# Ako sajt kaže:
#
# 2026-09-23T23:59:00+01:00
#
# koristimo:
#
# datum = 2026-09-23
# vreme = 23:59
#
# Ne pretvaramo u drugo vreme.
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
            value.replace(
                "Z",
                "+00:00"
            )
        )

        return dt.replace(
            tzinfo=None
        )

    except Exception:

        pass


    # --------------------------------------------------------
    # REZERVNI FORMATI
    # --------------------------------------------------------

    formats = [

        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M%z",

        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M%z",

        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",

        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",

    ]


    for fmt in formats:

        try:

            dt = datetime.strptime(
                value,
                fmt
            )

            return dt.replace(
                tzinfo=None
            )

        except Exception:

            continue


    # --------------------------------------------------------
    # FORMAT DD/MM/YYYY HH:MM GMT +1
    # --------------------------------------------------------

    match = re.search(
        r"(\d{1,2})/(\d{1,2})/(\d{4})"
        r"\s+"
        r"(\d{1,2}):(\d{2})",
        value
    )

    if match:

        try:

            day = int(
                match.group(1)
            )

            month = int(
                match.group(2)
            )

            year = int(
                match.group(3)
            )

            hour = int(
                match.group(4)
            )

            minute = int(
                match.group(5)
            )

            return datetime(
                year,
                month,
                day,
                hour,
                minute
            )

        except Exception:

            pass


    return None


# ============================================================
# PRONALAŽENJE POSTERA
# ============================================================

def parse_image(
    soup,
    source_url
):

    # ========================================================
    # PRVI NAČIN
    # ========================================================

    thumb = soup.select_one(
        "div.thumb.mvic-thumb"
    )

    if thumb:

        style = thumb.get(
            "style",
            ""
        )

        match = re.search(
            r"background-image\s*:"
            r"\s*url\(\s*['\"]?"
            r"([^'\")]+)",
            style,
            re.IGNORECASE
        )

        if match:

            image = match.group(
                1
            ).strip()

            return urljoin(
                source_url,
                image
            )


        # ----------------------------------------------------
        # IMG UNUTAR DIV-a
        # ----------------------------------------------------

        img = thumb.find(
            "img"
        )

        if img:

            for attr in [
                "src",
                "data-src",
                "data-lazy-src",
                "data-original"
            ]:

                image = img.get(
                    attr
                )

                if image:

                    return urljoin(
                        source_url,
                        image
                    )


    # ========================================================
    # DRUGI NAČIN
    # ========================================================

    thumb = soup.select_one(
        ".mvic-thumb"
    )

    if thumb:

        style = thumb.get(
            "style",
            ""
        )

        match = re.search(
            r"background-image\s*:"
            r"\s*url\(\s*['\"]?"
            r"([^'\")]+)",
            style,
            re.IGNORECASE
        )

        if match:

            image = match.group(
                1
            ).strip()

            return urljoin(
                source_url,
                image
            )


        img = thumb.find(
            "img"
        )

        if img:

            for attr in [
                "src",
                "data-src",
                "data-lazy-src",
                "data-original"
            ]:

                image = img.get(
                    attr
                )

                if image:

                    return urljoin(
                        source_url,
                        image
                    )


    # ========================================================
    # DODATNI FALLBACK
    # ========================================================

    selectors = [

        "meta[property='og:image']",

        "meta[name='twitter:image']",

        ".poster img",

        ".post-thumb img",

        ".movie-thumb img",

    ]


    for selector in selectors:

        element = soup.select_one(
            selector
        )

        if not element:

            continue


        image = (
            element.get("content")
            or element.get("src")
            or element.get("data-src")
            or element.get("data-lazy-src")
        )


        if image:

            return urljoin(
                source_url,
                image
            )


    return None


# ============================================================
# GLAVNI PROGRAM
# ============================================================

def main():

    print()
    print("=" * 75)
    print(" TV KALENDAR - AŽURIRANJE")
    print("=" * 75)
    print()


    # ========================================================
    # UČITAJ MAPU
    # ========================================================

    try:

        series_map = load_json(
            MAP_FILE
        )

    except Exception as e:

        print(
            f"❌ Ne mogu da učitam "
            f"{MAP_FILE}: {e}"
        )

        return


    print(
        f"Pronađeno serija u mapi: "
        f"{len(series_map)}"
    )

    print()


    # ========================================================
    # DATUM DANAS
    # ========================================================

    now = datetime.now()

    today = now.date()


    # ========================================================
    # PONEDELJAK TEKUĆE NEDELJE
    # ========================================================

    monday = (
        today
        - timedelta(
            days=today.weekday()
        )
    )


    # ========================================================
    # KRAJ PERIODA
    #
    # 14 dana:
    #
    # 14.09 → 27.09.
    #
    # Ovo znači da će Ask ve Taht sa 23.09.
    # sada biti pronađen.
    # ========================================================

    end_date = (
        monday
        + timedelta(
            days=DAYS_TO_SHOW - 1
        )
    )


    print(
        f"Period: "
        f"{monday} → {end_date}"
    )

    print()


    # ========================================================
    # KREIRAJ SVE DANE
    # ========================================================

    days = {}


    for i in range(
        DAYS_TO_SHOW
    ):

        current_date = (
            monday
            + timedelta(days=i)
        )

        date_string = (
            current_date.isoformat()
        )

        days[date_string] = {

            "date": date_string,

            "day": DAY_NAMES[
                current_date.weekday()
            ],

            "episodes": []

        }


    # ========================================================
    # STATISTIKA
    # ========================================================

    found = 0
    added = 0
    skipped = 0
    errors = 0


    # ========================================================
    # OBRADA SVIH SERIJA
    # ========================================================

    total_series = len(
        series_map
    )


    for index, (
        series_id,
        source_url
    ) in enumerate(
        series_map.items(),
        start=1
    ):

        print(
            f"[{index}/{total_series}] "
            f"{series_id}"
        )

        print(
            f"   URL: {source_url}"
        )


        # ----------------------------------------------------
        # UČITAJ STRANICU
        # ----------------------------------------------------

        html = fetch_page(
            source_url
        )


        if not html:

            errors += 1

            print(
                "   ❌ Stranica nije učitana"
            )

            print()

            continue


        # ----------------------------------------------------
        # BEAUTIFULSOUP
        # ----------------------------------------------------

        soup = BeautifulSoup(
            html,
            "html.parser"
        )


        # ----------------------------------------------------
        # COUNTDOWN
        # ----------------------------------------------------

        target_time = parse_countdown(
            soup
        )


        if not target_time:

            skipped += 1

            print(
                "   ⚠️ Nema aktivnog countdown-a"
            )

            print()

            continue


        print(
            f"   Target: {target_time}"
        )


        # ----------------------------------------------------
        # PARSIRAJ DATUM
        # ----------------------------------------------------

        dt = parse_target_datetime(
            target_time
        )


        if not dt:

            errors += 1

            print(
                "   ❌ Ne mogu da parsiram datum"
            )

            print()

            continue


        found += 1


        # ----------------------------------------------------
        # DATUM
        # ----------------------------------------------------

        episode_date = dt.date()

        date_string = (
            episode_date.isoformat()
        )


        # ----------------------------------------------------
        # PROVERA DA LI JE U PERIODU
        #
        # Sada više nije samo trenutna nedelja.
        # ----------------------------------------------------

        if not (
            monday
            <= episode_date
            <= end_date
        ):

            skipped += 1

            print(
                f"   ⏭️ Van prikazanog perioda: "
                f"{date_string}"
            )

            print()

            continue


        # ----------------------------------------------------
        # DAN
        # ----------------------------------------------------

        day_name = DAY_NAMES[
            episode_date.weekday()
        ]


        # ----------------------------------------------------
        # VREME
        # ----------------------------------------------------

        time_string = dt.strftime(
            "%H:%M"
        )


        # ----------------------------------------------------
        # POSTER
        # ----------------------------------------------------

        image = parse_image(
            soup,
            source_url
        )


        if image:

            print(
                "   Poster: pronađen"
            )

        else:

            print(
                "   Poster: nije pronađen"
            )


        # ----------------------------------------------------
        # EPIZODA
        # ----------------------------------------------------

        episode = {

            "id": series_id,

            "title": series_id,

            "sourceUrl": source_url,

            "nextEpisode": target_time,

            "date": date_string,

            "day": day_name,

            "time": time_string,

            "image": image

        }


        # ----------------------------------------------------
        # DODAJ U DAN
        # ----------------------------------------------------

        days[
            date_string
        ][
            "episodes"
        ].append(
            episode
        )


        added += 1


        print(
            f"   ✅ DODATO: "
            f"{day_name} "
            f"{date_string} "
            f"u {time_string}"
        )

        print()


    # ========================================================
    # SORTIRANJE
    # ========================================================

    for date_string, day_data in days.items():

        day_data[
            "episodes"
        ].sort(

            key=lambda episode: (

                episode.get(
                    "time",
                    "99:99"
                ),

                episode.get(
                    "title",
                    ""
                )

            )

        )


    # ========================================================
    # KONAČNI JSON
    # ========================================================

    output = {

        "updatedAt":
            datetime.now()
            .astimezone()
            .isoformat(),

        "week": {

            "start":
                monday.isoformat(),

            "end":
                end_date.isoformat(),

            "days":
                DAYS_TO_SHOW

        },

        "days":
            days

    }


    # ========================================================
    # SAČUVAJ
    # ========================================================

    try:

        save_json(
            OUTPUT_FILE,
            output
        )

    except Exception as e:

        print()

        print(
            f"❌ Greška pri čuvanju "
            f"JSON-a: {e}"
        )

        return


    # ========================================================
    # STATISTIKA
    # ========================================================

    total_episodes = sum(

        len(
            day["episodes"]
        )

        for day in days.values()

    )


    print()
    print("=" * 75)
    print(" GOTOVO")
    print("=" * 75)

    print()

    print(
        f"Serija u mapi:       "
        f"{len(series_map)}"
    )

    print(
        f"Pronađen countdown:  "
        f"{found}"
    )

    print(
        f"Dodato u kalendar:   "
        f"{added}"
    )

    print(
        f"Preskočeno:          "
        f"{skipped}"
    )

    print(
        f"Greške:              "
        f"{errors}"
    )

    print(
        f"Ukupno epizoda:      "
        f"{total_episodes}"
    )

    print()

    print(
        f"Period: "
        f"{monday} → {end_date}"
    )

    print(
        f"JSON: {OUTPUT_FILE}"
    )

    print()


    # ========================================================
    # PRIKAŽI KALENDAR
    # ========================================================

    print("=" * 75)
    print(" KALENDAR")
    print("=" * 75)

    print()


    for date_string, day_data in days.items():

        episodes = day_data[
            "episodes"
        ]


        print(
            f"{day_data['day']} "
            f"({date_string})"
        )


        if not episodes:

            print(
                "   — nema epizoda"
            )

        else:

            for episode in episodes:

                print(
                    f"   "
                    f"{episode['time']}  "
                    f"{episode['title']}"
                )


        print()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
