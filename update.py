name: Update next episodes

on:
  schedule:
    - cron: "0 3 * * *"

  workflow_dispatch:

permissions:
  contents: write

jobs:
  update:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          pip install requests beautifulsoup4

      - name: Run updater
        run: |
          python update.py

      - name: Save changes
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

          git add next-episodes.json

          if git diff --cached --quiet; then
            echo "Nema promena."
            exit 0
          fi

          git commit -m "Update next episode dates"
          git push