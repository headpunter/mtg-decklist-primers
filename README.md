# EDH Collection

A living repository of Commander decklists, primers, and build status.

## Quick Start

```bash
pip install -r requirements.txt

# 1. Import all decks from your Archidekt folders
python scripts/import_archidekt.py

# 2. Build a primer for a deck interactively (Gemini Q&A)
export GEMINI_API_KEY=your-key-here
python scripts/build_primer.py --list          # see what's available
python scripts/build_primer.py <deck-slug>     # start a session

# 3. See what you haven't built yet
python scripts/recommend.py
```

---

## Folder Structure

```
decks/<deck-slug>/
  decklist.md     HTML table — Qty | Card | Image | Oracle Text
  primer.md       strategy, game plan, win conditions, mulligan guide
  meta.yaml       commander, colors, themes, power level, build status
  cards.json      raw Scryfall-enriched card data (machine-readable)
scripts/
  import_archidekt.py   pull decklists from Archidekt, enrich via Scryfall
  build_primer.py       interactive Gemini CLI primer builder
  recommend.py          list unbuilt decks for AI build recommendations
  scrape.py             (legacy) fetch individual card data from Scryfall
  tag.py                (legacy) auto-suggest themes from card text
owned.yaml        tracks which decks are physically sleeved and built
```

---

## Importing Decklists

```bash
# Default: scans folders 1550171 and 1583741
python scripts/import_archidekt.py

# Override folders
python scripts/import_archidekt.py --folders 1550171 1583741

# Import specific deck IDs directly
python scripts/import_archidekt.py --decks 123456 789012

# Re-import everything (overwrites existing files)
python scripts/import_archidekt.py --force
```

### Private folders

If your folders are private, grab your bearer token from browser DevTools:
1. Open DevTools → Network tab
2. Visit archidekt.com and log in
3. Filter requests to `archidekt.com/api`
4. Copy the `Authorization: Bearer <token>` header value

```bash
export ARCHIDEKT_TOKEN=your-token-here
python scripts/import_archidekt.py
```

Each imported deck gets a `decklist.md` with a full card table:

| Qty | Card | Image | Oracle Text |
|-----|------|-------|-------------|
| 1 | Lightning Bolt | *(small Scryfall image)* | Deal 3 damage to any target. |

---

## Building Primers

The primer builder runs an interactive Q&A session in your terminal.
Gemini asks you questions about your deck and writes `primer.md` when done.

```bash
export GEMINI_API_KEY=your-key-here   # free key at aistudio.google.com

python scripts/build_primer.py <deck-slug>
```

**Session commands:**

| Input | Action |
|-------|--------|
| *(answer normally)* | send your answer to Gemini |
| `done` / `generate` | stop Q&A and write primer.md now |
| `skip` | skip the current question |
| `cards` | print the full card list |
| `meta` | print deck metadata |
| `quit` / `exit` | exit without saving |

To update an existing primer:
```bash
python scripts/build_primer.py <deck-slug> --resume
```

---

## Tracking Build Status

Mark a deck as built in `owned.yaml`:

```yaml
built:
  - slug: zur-the-enchanter
    built_date: 2025-03-12
    notes: first paper build
```

Also update the deck's `meta.yaml`:
```yaml
status: built   # concept | paper | built
```

---

## Deck Table

| Deck | Commander | Colors | Built |
|------|-----------|--------|-------|
| *(populate after import)* | | | |

---

## Next Build Recommendations

```bash
python scripts/recommend.py
# Paste the output into Claude/Gemini with your budget and preferences
```
