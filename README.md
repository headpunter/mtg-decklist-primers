# EDH Collection

A living repository of Commander decklists, primers, and build status.

## Structure

```
decks/<deck-slug>/
  decklist.md   # full 99 + commander
  primer.md     # strategy, lines, mulligan guide
  meta.yaml     # tags, colors, themes, build status
scripts/
  scrape.py     # pull card data from Scryfall
  tag.py        # auto-tag decks by theme/color
  recommend.py  # suggest next deck to build
owned.yaml      # tracks which decks are physically built
```

## Deck Status

| Deck | Commander | Colors | Built |
|------|-----------|--------|-------|
| *(add decks here)* | | | |

## Adding a New Deck

1. Create `decks/<deck-slug>/` with `decklist.md`, `primer.md`, and `meta.yaml`
2. If the deck is physically built, add an entry to `owned.yaml`

## Querying for Next Build

The `owned.yaml` file lists all built decks so they can be excluded when
asking an AI to recommend what to build next. When prompting, share the
contents of `owned.yaml` and the list of deck slugs in `decks/` to get
recommendations based on what you don't yet own.
