"""
Fetch card data from Scryfall for a given deck slug.
Usage: python scripts/scrape.py <deck-slug>
"""

import sys
import json
import urllib.request
import urllib.parse
from pathlib import Path

SCRYFALL_NAMED = "https://api.scryfall.com/cards/named"


def fetch_card(name: str) -> dict:
    url = f"{SCRYFALL_NAMED}?{urllib.parse.urlencode({'fuzzy': name})}"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read())


def parse_decklist(decklist_path: Path) -> list[str]:
    cards = []
    for line in decklist_path.read_text().splitlines():
        line = line.strip()
        # skip headers, blanks, and HTML comments
        if not line or line.startswith("#") or line.startswith("<!--") or line.startswith("-" * 3):
            continue
        # lines like "- 1 Card Name" or "1 Card Name"
        if line.startswith("- "):
            line = line[2:]
        parts = line.split(" ", 1)
        if len(parts) == 2 and parts[0].isdigit():
            cards.append(parts[1])
    return cards


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/scrape.py <deck-slug>")
        sys.exit(1)

    slug = sys.argv[1]
    deck_dir = Path("decks") / slug
    decklist_path = deck_dir / "decklist.md"

    if not decklist_path.exists():
        print(f"No decklist found at {decklist_path}")
        sys.exit(1)

    cards = parse_decklist(decklist_path)
    out = []
    for name in cards:
        print(f"  fetching: {name}")
        try:
            data = fetch_card(name)
            out.append({"name": data["name"], "cmc": data["cmc"], "type": data["type_line"], "colors": data.get("colors", [])})
        except Exception as e:
            print(f"  WARN: could not fetch '{name}': {e}")

    out_path = deck_dir / "cards.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {len(out)} cards to {out_path}")


if __name__ == "__main__":
    main()
