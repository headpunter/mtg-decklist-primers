"""
Print deck concepts not yet built, for use when prompting an AI for next-build advice.
Usage: python3 scripts/recommend.py

Outputs a summary of unbuilt decks you can paste into a Claude/ChatGPT prompt.
"""

import sys
from pathlib import Path
import yaml  # pip install pyyaml


def load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def main():
    owned_path = Path("owned.yaml")
    decks_dir = Path("decks")

    built_slugs = set()
    if owned_path.exists():
        data = load_yaml(owned_path)
        built_slugs = {d["slug"] for d in (data.get("built") or [])}

    unbuilt = []
    for deck_dir in sorted(decks_dir.iterdir()):
        if deck_dir.name.startswith("_"):
            continue
        meta_path = deck_dir / "meta.yaml"
        if not meta_path.exists():
            continue
        meta = load_yaml(meta_path)
        if meta.get("slug") not in built_slugs:
            unbuilt.append(meta)

    if not unbuilt:
        print("All decks are built — nothing left to recommend!")
        return

    print("# Unbuilt decks (paste into AI prompt)\n")
    for m in unbuilt:
        colors = "/".join(m.get("colors") or [])
        themes = ", ".join(m.get("themes") or [])
        print(f"- **{m.get('commander', m.get('slug'))}** [{colors}] — {themes} (power {m.get('power_level','?')})")

    print(f"\nTotal unbuilt: {len(unbuilt)}")


if __name__ == "__main__":
    main()
