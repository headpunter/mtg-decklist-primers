"""
Auto-suggest tags for a deck based on its card types and keywords.
Usage: python scripts/tag.py <deck-slug>
"""

import sys
import json
from pathlib import Path

KEYWORD_TAGS = {
    "token": ["token", "create a", "populate"],
    "graveyard": ["graveyard", "flashback", "unearth", "reanimate", "dredge", "delve"],
    "combo": ["tutor", "infinite", "untap", "storm count"],
    "voltron": ["aura", "equipment", "attach", "double strike", "hexproof"],
    "stax": ["can't untap", "can't cast", "each opponent", "tax"],
    "spellslinger": ["instant", "sorcery", "magecraft", "whenever you cast"],
    "artifacts": ["artifact", "improvise", "affinity"],
    "counters": ["+1/+1 counter", "proliferate", "counter"],
    "lands": ["land", "landfall", "fetch", "basic"],
}


def suggest_tags(cards: list[dict]) -> list[str]:
    text = " ".join(
        f"{c.get('name','')} {c.get('type','')}".lower() for c in cards
    )
    return [tag for tag, keywords in KEYWORD_TAGS.items() if any(kw in text for kw in keywords)]


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/tag.py <deck-slug>")
        sys.exit(1)

    slug = sys.argv[1]
    cards_path = Path("decks") / slug / "cards.json"

    if not cards_path.exists():
        print(f"No cards.json found — run scrape.py first: {cards_path}")
        sys.exit(1)

    cards = json.loads(cards_path.read_text())
    tags = suggest_tags(cards)
    print(f"Suggested tags for '{slug}':")
    for tag in tags:
        print(f"  - {tag}")
    print("\nAdd these to meta.yaml under 'themes:'")


if __name__ == "__main__":
    main()
