import json
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urljoin


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
    "Accept-Language": (
        "sr-RS,sr;q=0.9,en-US;q=0.8,en;q=0.7"
    ),
}


# ============================================================
# UČITAVANJE JSON-A
# ============================================================

def load_json(filename):

    with open(
        filename,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


# ============================================================
# ČUVANJE JSON-A
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
            timeout=20
        )

        response.raise_for_status()

        return response.text

    except Exception as e:

        print(
            f"   ❌ Greška pri učitavanju: {e}"
        )

        return None


# ============================================================
# PRONALAŽENJE SLEDEĆE EPIZODE
# ============================================================

def parse_next_episode(soup):

    # ========================================================
    # CEO TEKST STRANICE
    # ========================================================

    text = soup.get_text(
        " ",
        strip=True
    )


    # ========================================================
    # TRAŽIMO:
    #
    # Sledeća epizoda se očekuje
    # 23/09/2026 23:59 GMT +1
    #
    # ========================================================

    pattern = re.compile(
        r"Sledeća\s+epizoda\s+se\s+očekuje\s+"
        r"(\d{1,2}/\d{1,2}/\d{4})"
        r"\s+"
        r"(\d{1,2}:\d{2})"
        r"(?:\s+GMT\s*([+-]\d{1,2}))?",
        re.IGNORECASE
    )


    match = pattern.search(text)


    if not match:

        return None


    date_part = match.group(1)

    time_part = match.group(2)

    timezone_part = match.group(3)


    # ========================================================
    # DATUM
    # ========================================================

    try:

        dt = datetime.strptime(
            date_part + " " + time_part,
            "%d/%m/%Y %H:%M"
        )

    except ValueError:

        return None


    # ========================================================
    # ISO DATUM
    # ========================================================

    iso_date = dt.strftime(
        "%Y-%m-%d"
    )


    display_date = dt.strftime(
        "%d.%m.%Y"
    )


    display_time = dt.strftime(
        "%H:%M"
    )


    # ========================================================
    # ORIGINALNI TIMEZONE
    #
    # Ako stranica kaže:
    #
    # GMT +1
    #
    # ostaje +01:00.
    #
    # NE PRETVARAMO VREME.
    # ========================================================

    if timezone_part:

        offset = int(
            timezone_part
        )

        sign = "+" if offset >= 0 else "-"

        offset_abs = abs(offset)

        next_episode = (
            f"{iso_date}T"
            f"{display_time}:00"
            f"{sign}"
            f"{offset_abs:02d}:00"
        )

    else:

        next_episode = (
            f"{iso_date}T"
            f"{display_time}:00"
        )


    return {
        "nextEpisode": next_episode,
        "date": display_date,
        "dateISO": iso_date,
        "time": display_time
    }


# ============================================================
# PRONALAŽENJE SLIKE
# ============================================================

def parse_image(soup):

    # ========================================================
    # 1. THUMB BACKGROUND
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
            r'background-image\s*:\s*url\(["\']?(.*?)["\']?\)',
            style,
            re.IGNORECASE
        )

        if match:

            image = match.group(1)

            return image.strip()


    # ========================================================
    # 2. IMG / OG IMAGE
    # ========================================================

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

            image = element.get(
                "content"
            )

        else:

            image = (
                element.get("src")
                or element.get("data-src")
                or element.get("data-lazy-src")
                or element.get("data-original")
            )


        if image:

            return image.strip()


    return ""


# ============================================================
# NORMALIZACIJA URL-A SLIKE
# ============================================================

def normalize_url(url):

    if not url:

        return ""

    return urljoin(
        BASE_URL,
        url
    )


# ============================================================
# GLAVNI PROGRAM
# ============================================================

def main():

    print()
    print("=" * 70)
    print(" TV KALENDAR - PREUZIMANJE DATUMA")
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
            f"❌ Ne mogu da učitam "
            f"{MAP_FILE}: {e}"
        )

        return


    # ========================================================
    # REZULTATI
    #
    # Ne ograničavamo na 7 ili 14 dana.
    #
    # Čuvamo sve što stranice trenutno prijavljuju.
    # ========================================================

    episodes = []


    total = 0

    found = 0

    not_found = 0

    errors = 0


    # ========================================================
    # SVE SERIJE IZ MAPE
    # ========================================================

    for series_id, series_data in series_map.items():

        total += 1


        # ====================================================
        # URL
        # ====================================================

        if isinstance(
            series_data,
            str
        ):

            source_url = series_data

        elif isinstance(
            series_data,
            dict
        ):

            source_url = (
                series_data.get("url")
                or series_data.get("sourceUrl")
                or series_data.get("link")
            )

        else:

            source_url = None


        if not source_url:

            print(
                f"[{total}] "
                f"{series_id}"
            )

            print(
                "   ⚠️ Nema URL"
            )

            errors += 1

            continue


        # ====================================================
        # NORMALIZUJ URL
        # ====================================================

        source_url = normalize_url(
            source_url
        )


        print(
            f"[{total}] {series_id}"
        )

        print(
            f"   🔗 {source_url}"
        )


        # ====================================================
        # PREUZMI STRANICU
        # ====================================================

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


        # ====================================================
        # DATUM
        # ====================================================

        result = parse_next_episode(
            soup
        )


        if not result:

            print(
                "   ⚪ Nema podatka o sledećoj epizodi"
            )

            not_found += 1

            continue


        found += 1


        # ====================================================
        # SLIKA
        # ====================================================

        image = parse_image(
            soup
        )


        image = normalize_url(
            image
        )


        # ====================================================
        # EPIZODA
        # ====================================================

        episode = {

            "id": series_id,

            "title": series_id,

            "sourceUrl": source_url,

            "nextEpisode":
                result["nextEpisode"],

            "date":
                result["date"],

            "dateISO":
                result["dateISO"],

            "time":
                result["time"],

            "image":
                image

        }


        episodes.append(
            episode
        )


        print(
            f"   ✅ {result['date']} "
            f"{result['time']}"
        )


    # ========================================================
    # SORTIRANJE
    #
    # Prvo datum,
    # zatim vreme.
    # ========================================================

    episodes.sort(
        key=lambda item: (
            item.get(
                "dateISO",
                "9999-99-99"
            ),
            item.get(
                "time",
                "99:99"
            )
        )
    )


    # ========================================================
    # GRUPISANJE PO DATUMU
    #
    # Python ovde NE određuje dan u nedelji.
    #
    # Samo pravi listu po datumu.
    # HTML će kasnije odrediti:
    #
    # 2026-09-23 = Sreda
    #
    # ========================================================

    days = {}


    for episode in episodes:

        date_iso = episode[
            "dateISO"
        ]


        if date_iso not in days:

            days[date_iso] = []


        days[
            date_iso
        ].append(
            episode
        )


    # ========================================================
    # FINALNI JSON
    # ========================================================

    result_json = {

        "updatedAt":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "episodes":
            episodes,

        "days":
            days

    }


    # ========================================================
    # SAČUVAJ
    # ========================================================

    save_json(
        OUTPUT_FILE,
        result_json
    )


    # ========================================================
    # STATISTIKA
    # ========================================================

    print()

    print("=" * 70)

    print(" GOTOVO")

    print("=" * 70)

    print()

    print(
        f"Ukupno serija:       {total}"
    )

    print(
        f"Pronađen termin:     {found}"
    )

    print(
        f"Bez termina:         {not_found}"
    )

    print(
        f"Greške:              {errors}"
    )

    print(
        f"Ukupno termina:      {len(episodes)}"
    )

    print()

    print(
        f"Fajl:                {OUTPUT_FILE}"
    )

    print()

    print("=" * 70)

    print()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
