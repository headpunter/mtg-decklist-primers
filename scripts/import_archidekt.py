#!/usr/bin/env python3
"""
Import all decks from Archidekt folders into the decks/ directory.

Each deck gets:
  decks/<slug>/decklist.md   — HTML table with Qty | Card | Image | Oracle Text
  decks/<slug>/cards.json    — full Scryfall-enriched card data
  decks/<slug>/meta.yaml     — commander, colors, themes, status
  decks/<slug>/primer.md     — empty stub (fill with build_primer.py)

Usage:
    # Import default folders (1550171 page 1, 1550171 page 2, 1583741)
    python3 scripts/import_archidekt.py

    # Override which folders to scan
    python3 scripts/import_archidekt.py --folders 1550171 1583741

    # Import specific deck IDs directly (skips folder lookup)
    python3 scripts/import_archidekt.py --decks 123456 789012

    # Re-import decks that already exist
    python3 scripts/import_archidekt.py --force

Environment:
    ARCHIDEKT_TOKEN   (optional) Bearer token for private folders/decks
                      Get it from your browser's DevTools → Network →
                      any archidekt.com/api request → Authorization header

Requires:
    pip install requests pyyaml
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
import yaml

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ARCHIDEKT_API = "https://archidekt.com/api"
SCRYFALL_API  = "https://api.scryfall.com"
DECKS_DIR     = Path(__file__).parent.parent / "decks"

DEFAULT_FOLDER_IDS = [1550171, 1583741]

# Scryfall image sizes: small (146×204), normal (488×680), large (672×936)
IMAGE_SIZE = "small"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s.strip())
    s = re.sub(r"-+", "-", s)
    return s[:80]  # cap length


def archidekt_session(token: str | None) -> requests.Session:
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "mtg-decklist-primers/1.0 (personal collection tool)",
        "Accept": "application/json",
    })
    if token:
        sess.headers["Authorization"] = f"Bearer {token}"
    return sess


def scryfall_session() -> requests.Session:
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "mtg-decklist-primers/1.0 (personal collection tool)",
        "Accept": "application/json",
    })
    return sess


# ---------------------------------------------------------------------------
# Archidekt API
# ---------------------------------------------------------------------------

def scrape_folder_page(folder_id: int, sess: requests.Session) -> list[dict]:
    """
    Fallback: fetch the Archidekt folder HTML page and extract deck IDs
    from links of the form /decks/<id>/... — no API key required.
    """
    url = f"https://archidekt.com/folders/{folder_id}"
    # Request as a browser so Cloudflare/SSR doesn't block us
    html_sess = requests.Session()
    html_sess.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    # Copy auth cookies if the session has them
    html_sess.cookies.update(sess.cookies)

    try:
        resp = html_sess.get(url, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"  Could not fetch folder page: {e}")
        return []

    # Extract all unique deck IDs from href="/decks/<id>" links
    ids_seen: set[int] = set()
    stubs: list[dict] = []
    for m in re.finditer(r'href=["\']?/decks/(\d+)(?:/[^"\'> ]*)?["\']?', resp.text):
        deck_id = int(m.group(1))
        if deck_id not in ids_seen:
            ids_seen.add(deck_id)
            stubs.append({"id": deck_id})

    return stubs


def _probe_folder_endpoint(folder_id: int, sess: requests.Session) -> str | None:
    """
    Try several known Archidekt API patterns and return the base URL of the
    first one that returns HTTP 200. Returns None if all fail.
    """
    candidates = [
        f"{ARCHIDEKT_API}/decks/?folder={folder_id}&pageSize=1",
        f"{ARCHIDEKT_API}/decks/?folders={folder_id}&pageSize=1",
        f"{ARCHIDEKT_API}/decks/folders/{folder_id}/",
        f"https://archidekt.com/api/v2/decks/?folder={folder_id}&pageSize=1",
    ]
    for url in candidates:
        try:
            r = sess.get(url, timeout=10)
            if r.status_code == 200:
                print(f"  ✓  API endpoint: {url.split('?')[0]}")
                return url.split("?")[0]
        except Exception:
            pass
    return None


def get_folder_decks(folder_id: int, sess: requests.Session) -> list[dict]:
    """
    Return all deck stubs (id + name) from an Archidekt folder.
    Tries the JSON API first; falls back to HTML scraping for public folders.
    """
    base = _probe_folder_endpoint(folder_id, sess)

    if base is not None:
        decks = []
        page = 1
        while True:
            params: dict = {"pageSize": 50, "page": page}
            if "folder" not in base:
                params["folder"] = folder_id
            try:
                resp = sess.get(base, params=params, timeout=15)
                resp.raise_for_status()
            except requests.HTTPError as e:
                code = e.response.status_code
                if code == 403:
                    print("  403 — folder may be private. Set ARCHIDEKT_TOKEN and retry.")
                else:
                    print(f"  HTTP {code} on page {page}: {e}")
                return decks
            data = resp.json()
            if isinstance(data, list):
                results, has_next = data, False
            else:
                results, has_next = data.get("results", []), bool(data.get("next"))
            decks.extend(results)
            print(f"    page {page}: {len(results)} decks")
            if not has_next:
                break
            page += 1
            time.sleep(0.4)
        return decks

    # API failed — fall back to scraping the folder HTML page
    print(f"  API endpoints all failed. Falling back to HTML scrape of folder page …")
    stubs = scrape_folder_page(folder_id, sess)
    if stubs:
        print(f"  Found {len(stubs)} deck link(s) in page HTML.")
    else:
        print(
            f"\n  Could not find decks in folder {folder_id} via API or HTML.\n"
            f"  If the folder is private, log into Archidekt in your browser,\n"
            f"  open DevTools → Network → any /api/ request → copy the\n"
            f"  'Authorization: Bearer ...' header value, then:\n"
            f"\n      export ARCHIDEKT_TOKEN='Bearer xxxxx'\n"
            f"      python3 scripts/import_archidekt.py\n"
            f"\n  Or pass deck URLs/IDs directly:\n"
            f"      python3 scripts/import_archidekt.py --decks "
            f"https://archidekt.com/decks/123456\n"
        )
    return stubs
        page += 1
        time.sleep(0.4)

    return decks


def get_deck_full(deck_id: int, sess: requests.Session) -> dict:
    """Fetch a full deck (with cards) from Archidekt."""
    url = f"{ARCHIDEKT_API}/decks/{deck_id}/"
    resp = sess.get(url, timeout=20)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Scryfall API
# ---------------------------------------------------------------------------

def fetch_scryfall_batch(names: list[str], sf_sess: requests.Session) -> dict[str, dict]:
    """
    Batch-fetch card data from Scryfall using the /cards/collection endpoint.
    Returns a dict keyed by exact card name (as returned by Scryfall).
    """
    results: dict[str, dict] = {}

    for i in range(0, len(names), 75):
        batch = names[i : i + 75]
        payload = {"identifiers": [{"name": n} for n in batch]}
        resp = sf_sess.post(f"{SCRYFALL_API}/cards/collection", json=payload, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        for card in data.get("data", []):
            results[card["name"]] = card

        for nf in data.get("not_found", []):
            print(f"    WARN Scryfall: not found → {nf.get('name', nf)}")

        time.sleep(0.12)  # respect Scryfall rate limit (10 req/s)

    return results


def card_image_url(card: dict, size: str = IMAGE_SIZE) -> str:
    """Resolve image URL, handling double-faced cards."""
    if "image_uris" in card:
        return card["image_uris"].get(size, "")
    faces = card.get("card_faces", [])
    if faces and "image_uris" in faces[0]:
        return faces[0]["image_uris"].get(size, "")
    return ""


def card_oracle_text(card: dict) -> str:
    """Resolve oracle text, joining DFC faces with ' // '."""
    if "oracle_text" in card:
        return card["oracle_text"]
    faces = card.get("card_faces", [])
    if faces:
        return " // ".join(f.get("oracle_text", "") for f in faces)
    return ""


# ---------------------------------------------------------------------------
# Archidekt card parsing
# ---------------------------------------------------------------------------

def parse_archidekt_cards(deck: dict) -> list[dict]:
    """
    Pull the card list out of an Archidekt deck response.
    Returns a list of dicts with keys: name, qty, categories.
    """
    entries = []
    for entry in deck.get("cards", []):
        qty = entry.get("qty", 1)

        # card name lives at different depths depending on API version
        card_blob = entry.get("card", {})
        oracle_blob = card_blob.get("oracleCard", {})
        name = (
            oracle_blob.get("name")
            or card_blob.get("name")
            or entry.get("name", "")
        ).strip()

        if not name:
            continue

        # categories is a list of objects with a "name" key
        raw_cats = entry.get("categories", [])
        if raw_cats and isinstance(raw_cats[0], dict):
            cats = [c.get("name", "") for c in raw_cats]
        elif raw_cats and isinstance(raw_cats[0], str):
            cats = raw_cats
        else:
            cats = []

        entries.append({"name": name, "qty": qty, "categories": cats})

    return entries


# ---------------------------------------------------------------------------
# Output builders
# ---------------------------------------------------------------------------

CATEGORY_ORDER = [
    "Commander",
    "Creature",
    "Instant",
    "Sorcery",
    "Enchantment",
    "Artifact",
    "Planeswalker",
    "Land",
    "Other",
]


def _sort_key(cat: str) -> tuple[int, str]:
    try:
        return (CATEGORY_ORDER.index(cat), cat)
    except ValueError:
        return (len(CATEGORY_ORDER), cat)


def build_decklist_md(deck_name: str, enriched: list[dict]) -> str:
    """
    Build decklist.md as an HTML table (renders on GitHub) with columns:
    Qty | Card (linked to Scryfall) | Image | Oracle Text
    Cards are grouped by category.
    """
    by_cat: dict[str, list[dict]] = {}
    for c in enriched:
        cat = c.get("category", "Other")
        by_cat.setdefault(cat, []).append(c)

    lines: list[str] = []
    lines.append(f"# {deck_name}\n")
    lines.append(
        f"*{sum(c['qty'] for c in enriched)} cards total "
        f"(including commander)*\n"
    )
    lines.append('<table>')
    lines.append('<thead>')
    lines.append(
        '<tr>'
        '<th>Qty</th>'
        '<th>Card</th>'
        '<th>Image</th>'
        '<th>Oracle Text</th>'
        '</tr>'
    )
    lines.append('</thead>')
    lines.append('<tbody>')

    for cat in sorted(by_cat.keys(), key=_sort_key):
        cat_cards = sorted(by_cat[cat], key=lambda c: c["name"])
        lines.append(
            f'<tr><td colspan="4" align="center"><strong>{cat}</strong></td></tr>'
        )
        for c in cat_cards:
            sf_url   = c.get("scryfall_url", "").replace(r"\?", "?")
            img_url  = c.get("image_url", "")
            oracle   = (c.get("oracle_text", "") or "").replace("\n", "<br>")
            mana     = c.get("mana_cost", "")
            type_ln  = c.get("type_line", "")

            name_cell = (
                f'<a href="{sf_url}">{c["name"]}</a>' if sf_url
                else c["name"]
            )
            if mana:
                name_cell += f'<br><sub>{mana}</sub>'
            if type_ln:
                name_cell += f'<br><em>{type_ln}</em>'

            img_cell = (
                f'<img src="{img_url}" width="100" alt="{c["name"]}">'
                if img_url else ""
            )

            lines.append(
                f'<tr>'
                f'<td align="center">{c["qty"]}</td>'
                f'<td>{name_cell}</td>'
                f'<td>{img_cell}</td>'
                f'<td>{oracle}</td>'
                f'</tr>'
            )

    lines.append('</tbody>')
    lines.append('</table>')

    return "\n".join(lines) + "\n"


def build_meta_yaml(deck: dict, enriched: list[dict]) -> dict:
    deck_id   = deck.get("id", "")
    deck_name = deck.get("name", "")

    # Derive color identity from all cards
    color_set: set[str] = set()
    for c in enriched:
        color_set.update(c.get("colors", []))

    # Find commander
    commander = next(
        (
            c["name"]
            for c in enriched
            if "Commander" in c.get("categories", [])
        ),
        "",
    )

    return {
        "slug": slugify(deck_name),
        "commander": commander,
        "deck_name": deck_name,
        "colors": sorted(color_set),
        "themes": [],
        "power_level": None,
        "format": "EDH",
        "status": "concept",
        "links": {
            "archidekt": f"https://archidekt.com/decks/{deck_id}",
            "moxfield": "",
        },
    }


PRIMER_STUB = """\
# {name} — Primer

> *This primer is a stub. Run the following to generate it interactively:*
> ```
> python3 scripts/build_primer.py {slug}
> ```
"""


# ---------------------------------------------------------------------------
# Core: process one deck
# ---------------------------------------------------------------------------

def process_deck(
    deck_stub: dict,
    arch_sess: requests.Session,
    sf_sess: requests.Session,
    force: bool = False,
) -> None:
    deck_id   = deck_stub["id"]
    deck_name = deck_stub.get("name") or f"deck-{deck_id}"
    slug      = slugify(deck_name)
    deck_dir  = DECKS_DIR / slug

    print(f"\n── {deck_name}  (id={deck_id})  →  {slug}")

    if not force and (deck_dir / "cards.json").exists():
        print("   skipping — already imported (use --force to re-import)")
        return

    # 1. Fetch full deck from Archidekt
    print("   fetching deck from Archidekt …")
    try:
        deck = get_deck_full(deck_id, arch_sess)
    except requests.HTTPError as e:
        print(f"   ERROR fetching deck: {e}")
        return
    time.sleep(0.4)

    # 2. Parse card list
    raw_cards = parse_archidekt_cards(deck)
    if not raw_cards:
        print("   WARNING: no cards found in Archidekt response — skipping")
        return

    unique_names = list(dict.fromkeys(c["name"] for c in raw_cards))
    print(f"   {len(raw_cards)} card entries, {len(unique_names)} unique names")

    # 3. Enrich with Scryfall
    print(f"   fetching {len(unique_names)} cards from Scryfall …")
    sf_map = fetch_scryfall_batch(unique_names, sf_sess)

    enriched: list[dict] = []
    for rc in raw_cards:
        sf = sf_map.get(rc["name"], {})
        enriched.append({
            "name":            rc["name"],
            "qty":             rc["qty"],
            "category":        rc["categories"][0] if rc["categories"] else "Other",
            "categories":      rc["categories"],
            "mana_cost":       sf.get("mana_cost", ""),
            "type_line":       sf.get("type_line", ""),
            "oracle_text":     card_oracle_text(sf),
            "cmc":             sf.get("cmc", 0),
            "colors":          sf.get("colors") or sf.get("color_identity", []),
            "image_url":       card_image_url(sf, IMAGE_SIZE),
            "image_url_normal": card_image_url(sf, "normal"),
            "scryfall_id":     sf.get("id", ""),
            "scryfall_url":    sf.get("scryfall_uri", ""),
        })

    # 4. Write files
    deck_dir.mkdir(parents=True, exist_ok=True)

    cards_json = deck_dir / "cards.json"
    cards_json.write_text(json.dumps(enriched, indent=2, ensure_ascii=False))
    print(f"   wrote {cards_json.name}")

    dl_md = deck_dir / "decklist.md"
    dl_md.write_text(build_decklist_md(deck_name, enriched))
    print(f"   wrote {dl_md.name}")

    meta_path = deck_dir / "meta.yaml"
    with open(meta_path, "w", encoding="utf-8") as fh:
        yaml.dump(
            build_meta_yaml(deck, enriched),
            fh,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
    print(f"   wrote {meta_path.name}")

    primer_path = deck_dir / "primer.md"
    if not primer_path.exists() or force:
        primer_path.write_text(
            PRIMER_STUB.format(name=deck_name, slug=slug)
        )
        print(f"   wrote {primer_path.name} (stub)")

    print(f"   ✓  done")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Import Archidekt decks into the local decks/ directory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument(
        "--folders", nargs="+", type=int, default=DEFAULT_FOLDER_IDS,
        metavar="ID",
        help="Archidekt folder IDs to scan (default: 1550171 1583741)",
    )
    ap.add_argument(
        "--decks", nargs="+", type=str, default=None,
        metavar="ID_OR_URL",
        help=(
            "Import specific decks by ID or full URL, skipping folder lookup. "
            "Accepts integers or https://archidekt.com/decks/<id> URLs."
        ),
    )
    ap.add_argument(
        "--force", action="store_true",
        help="Re-import decks that have already been imported",
    )
    args = ap.parse_args()

    token    = os.environ.get("ARCHIDEKT_TOKEN")
    arch_sess = archidekt_session(token)
    sf_sess   = scryfall_session()

    DECKS_DIR.mkdir(exist_ok=True)

    if args.decks:
        # Resolve IDs from integers or full Archidekt URLs
        def resolve_id(raw: str) -> int | None:
            raw = raw.strip().rstrip("/")
            if raw.isdigit():
                return int(raw)
            # https://archidekt.com/decks/123456  or  .../decks/123456/deckname
            m = re.search(r"/decks/(\d+)", raw)
            if m:
                return int(m.group(1))
            print(f"  WARN: could not parse deck ID from '{raw}' — skipping")
            return None

        for raw in args.decks:
            deck_id = resolve_id(raw)
            if deck_id is None:
                continue
            stub = {"id": deck_id}
            try:
                deck = get_deck_full(deck_id, arch_sess)
                stub["name"] = deck.get("name", f"deck-{deck_id}")
                process_deck(stub, arch_sess, sf_sess, force=args.force)
            except Exception as e:
                print(f"  ERROR on deck {deck_id}: {e}")
        return

    # Folder-based import
    all_stubs: list[dict] = []
    for folder_id in args.folders:
        print(f"\nScanning folder {folder_id} …")
        stubs = get_folder_decks(folder_id, arch_sess)
        print(f"  found {len(stubs)} decks")
        all_stubs.extend(stubs)

    if not all_stubs:
        print(
            "\nNo decks found. Possible reasons:\n"
            "  • Folders are private — export ARCHIDEKT_TOKEN and retry\n"
            "  • Deck IDs moved — use --decks <id1> <id2> ... directly\n"
        )
        sys.exit(1)

    print(f"\nTotal: {len(all_stubs)} decks to import\n")
    for stub in all_stubs:
        try:
            process_deck(stub, arch_sess, sf_sess, force=args.force)
        except Exception as e:
            print(f"   ERROR: {e}")

    print("\n\nAll done.")


if __name__ == "__main__":
    main()
