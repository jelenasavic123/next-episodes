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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
# UČITAVANJE JSON-a
# ============================================================

def load_json(filename):
    path = Path(filename)

    if not path.exists():
        raise FileNotFoundError(
            f"Fajl ne postoji: {filename}"
        )

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# ČUVANJE JSON-a
# ============================================================

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
            timeout=30
        )

        response.raise_for_status()

        return response.text

    except Exception as e:
        print(f"   ❌ Greška pri učitavanju: {e}")
        return None


# ============================================================
# PRONALAŽENJE COUNTDOWN-a
# ============================================================

def parse_countdown(soup):

    countdown = soup.find(
        id="tvshow-countdown"
    )

    if not countdown:
        return None

    # Ako je serija pauzirana
    countdown_text = countdown.get_text(
        " ",
        strip=True
    ).lower()

    if "pauzirana" in countdown_text:
        return None

    target_time = countdown.get(
        "data-target-time"
    )

    if not target_time:
        return None

    return target_time.strip()


# ============================================================
# PARSIRANJE DATUMA
#
# BITNO:
# NE PRETVARAMO TIMEZONE.
#
# Ako sajt kaže:
#
# 2026-09-14T23:59:00+01:00
#
# koristimo:
#
# datum = 2026-09-14
# vreme = 23:59
#
# a NE pretvaramo u 00:59.
# ============================================================

def parse_target_datetime(value):

    if not value:
        return None

    value = value.strip()

    # --------------------------------------------------------
    # ISO format
    # --------------------------------------------------------

    try:

        dt = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        # Uklanjamo timezone info BEZ pomeranja vremena.
        #
        # 23:59 +01:00
        # ostaje
        # 23:59

        return dt.replace(tzinfo=None)

    except Exception:
        pass


    # --------------------------------------------------------
    # Rezervni formati
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

    return None


# ============================================================
# PRONALAŽENJE POSTERA
#
# Cilj:
#
# <div class="thumb mvic-thumb"
#      style="background-image: url('...');">
#
# ============================================================

def parse_image(soup, source_url):

    # --------------------------------------------------------
    # PRVI I NAJPOUZDANIJI NAČIN
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
            r"background-image\s*:\s*url\(\s*['\"]?([^'\")]+)",
            style,
            re.IGNORECASE
        )

        if match:

            image = match.group(1).strip()

            return urljoin(
                source_url,
                image
            )


        # ----------------------------------------------------
        # FALLBACK - IMG UNUTAR DIV-a
        # ----------------------------------------------------

        img = thumb.find("img")

        if img:

            for attr in [
                "src",
                "data-src",
                "data-lazy-src"
            ]:

                image = img.get(attr)

                if image:
                    return urljoin(
                        source_url,
                        image
                    )


    # ========================================================
    # DODATNI FALLBACK
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
            r"background-image\s*:\s*url\(\s*['\"]?([^'\")]+)",
            style,
            re.IGNORECASE
        )

        if match:

            image = match.group(1).strip()

            return urljoin(
                source_url,
                image
            )


        img = thumb.find("img")

        if img:

            for attr in [
                "src",
                "data-src",
                "data-lazy-src"
            ]:

                image = img.get(attr)

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
    print("=" * 70)
    print(" TV KALENDAR - AŽURIRANJE")
    print("=" * 70)
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
            f"❌ Ne mogu da učitam {MAP_FILE}: {e}"
        )

        return


    print(
        f"Pronađeno serija u mapi: {len(series_map)}"
    )

    print()


    # ========================================================
    # DATUM DANAS
    #
    # Bitno:
    # Koristimo datum računara.
    #
    # ========================================================

    now = datetime.now()

    today = now.date()


    # ========================================================
    # PONEDELJAK TE NEDELJE
    # ========================================================

    monday = today - timedelta(
        days=today.weekday()
    )

    sunday = monday + timedelta(
        days=6
    )


    print(
        f"Nedelja: {monday} → {sunday}"
    )

    print()


    # ========================================================
    # KREIRAJ SVIH 7 DANA
    # ========================================================

    days = {}

    for i in range(7):

        current_date = monday + timedelta(
            days=i
        )

        date_string = current_date.isoformat()

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

    for index, (series_id, source_url) in enumerate(
        series_map.items(),
        start=1
    ):

        print(
            f"[{index}/{len(series_map)}] "
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

        date_string = episode_date.isoformat()


        # ----------------------------------------------------
        # PROVERA DA LI JE U TEKUĆOJ NEDELJI
        # ----------------------------------------------------

        if not (
            monday <= episode_date <= sunday
        ):

            skipped += 1

            print(
                f"   ⏭️ Van ove nedelje: {date_string}"
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
                f"   Poster: pronađen"
            )

        else:

            print(
                f"   Poster: nije pronađen"
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

        days[date_string]["episodes"].append(
            episode
        )

        added += 1


        print(
            f"   ✅ Dodato: "
            f"{day_name} {date_string} "
            f"u {time_string}"
        )

        print()


    # ========================================================
    # SORTIRANJE EPIZODA
    # ========================================================

    for date_string, day_data in days.items():

        day_data["episodes"].sort(
            key=lambda episode: (
                episode.get("time", "99:99"),
                episode.get("title", "")
            )
        )


    # ========================================================
    # KONAČNI JSON
    # ========================================================

    output = {
        "updatedAt": datetime.now().astimezone().isoformat(),

        "week": {
            "start": monday.isoformat(),
            "end": sunday.isoformat(),
            "days": 7
        },

        "days": days
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
            f"❌ Greška pri čuvanju JSON-a: {e}"
        )

        return


    # ========================================================
    # STATISTIKA
    # ========================================================

    total_episodes = sum(
        len(day["episodes"])
        for day in days.values()
    )


    print()
    print("=" * 70)
    print(" GOTOVO")
    print("=" * 70)

    print()
    print(
        f"Serija u mapi:       {len(series_map)}"
    )

    print(
        f"Pronađen countdown:  {found}"
    )

    print(
        f"Dodato u kalendar:   {added}"
    )

    print(
        f"Preskočeno:          {skipped}"
    )

    print(
        f"Greške:              {errors}"
    )

    print(
        f"Ukupno epizoda:      {total_episodes}"
    )

    print()
    print(
        f"Nedelja: {monday} → {sunday}"
    )

    print(
        f"JSON: {OUTPUT_FILE}"
    )

    print()


    # ========================================================
    # PRIKAŽI KALENDAR
    # ========================================================

    print("=" * 70)
    print(" KALENDAR")
    print("=" * 70)

    print()

    for date_string, day_data in days.items():

        episodes = day_data["episodes"]

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
                    f"   {episode['time']}  "
                    f"{episode['title']}"
                )

        print()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
