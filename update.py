import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup


# ============================================================
# PODESAVANJA
# ============================================================

MAP_FILE = "series-map.json"
OUTPUT_FILE = "next-episodes.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    )
}


# ============================================================
# UCITAJ JSON
# ============================================================

def load_json(filename):

    path = Path(filename)

    if not path.exists():
        print(f"GRESKA: fajl ne postoji: {filename}")
        return {}

    try:

        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as e:

        print(f"GRESKA pri citanju {filename}: {e}")

        return {}


# ============================================================
# SACUVAJ JSON
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
# UCITAJ HTML STRANICU
# ============================================================

def fetch_page(url):

    print(f"  Otvaram: {url}")

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
# PRONADJI SLEDECU EPIZODU
# ============================================================

def parse_countdown(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

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
            f"  Pronadjen datum: {target_time}"
        )

        return target_time

    # --------------------------------------------------------
    # AKO NEMA DATUM
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
# GLAVNI PROGRAM
# ============================================================

def main():

    print()
    print("=" * 60)
    print(" NEXT EPISODES UPDATE")
    print("=" * 60)
    print()

    # --------------------------------------------------------
    # MAPA
    # --------------------------------------------------------

    series_map = load_json(
        MAP_FILE
    )

    if not series_map:

        print(
            "Nema podataka u series-map.json"
        )

        return

    print(
        f"Pronadjeno serija: {len(series_map)}"
    )

    print()

    # --------------------------------------------------------
    # REZULTAT
    # --------------------------------------------------------

    output = {}

    # --------------------------------------------------------
    # SVAKA SERIJA
    # --------------------------------------------------------

    for internal_id, source_url in series_map.items():

        print("-" * 60)

        print(
            f"Serija: {internal_id}"
        )

        print(
            f"Izvor: {source_url}"
        )

        try:

            html = fetch_page(
                source_url
            )

        except Exception as e:

            print(
                f"  GRESKA pri preuzimanju: {e}"
            )

            output[internal_id] = {
                "sourceUrl": source_url,
                "nextEpisode": None
            }

            continue

        # ----------------------------------------------------
        # PRONADJI DATUM
        # ----------------------------------------------------

        next_episode = parse_countdown(
            html
        )

        # ----------------------------------------------------
        # SACUVAJ REZULTAT
        # ----------------------------------------------------

        output[internal_id] = {
            "sourceUrl": source_url,
            "nextEpisode": next_episode
        }

        if next_episode:

            print(
                f"  OK -> {next_episode}"
            )

        else:

            print(
                "  Nema zakazane sledece epizode."
            )

    # --------------------------------------------------------
    # SACUVATI
    # --------------------------------------------------------

    save_json(
        OUTPUT_FILE,
        output
    )

    print()
    print("=" * 60)
    print(
        f"Sacuvano: {OUTPUT_FILE}"
    )
    print("=" * 60)
    print()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
