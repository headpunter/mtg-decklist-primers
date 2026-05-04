# MTG Decklist Primers

A personal Commander deck management repo. Three runtime modes:

- **Web app** (`app.py`) — FastAPI server, browse decks, AI-powered recommendations
- **Importer** (`scripts/import_archidekt.py`) — pulls decklists from Archidekt, enriches via Scryfall
- **Primer builder** (`scripts/build_primer.py`) — interactive Gemini Q&A session that writes `primer.md`

## Key Files

```
app.py                          web server
scripts/import_archidekt.py     deck importer (Archidekt + Scryfall)
scripts/build_primer.py         interactive primer builder (Gemini)
scripts/recommend.py            list unbuilt decks
decks/<slug>/
  meta.yaml                     commander, colors, themes, power level, status
  cards.json                    Scryfall-enriched card data
  decklist.md                   rendered card table
  primer.md                     strategy writeup
owned.yaml                      tracks physically built decks
```

## Decision Log

All architectural and design decisions are recorded in `context.md`.

After any discussion where we decide how to approach something — whether to use a library, how to structure a feature, what to rule out — append an entry to `context.md` before closing the task. Do this without being asked. Format:

```
## YYYY-MM-DD — Short title

**Decision:** what was chosen or ruled out

**Rationale:** why — constraints, trade-offs, what was considered
```

Read `context.md` at the start of each session to understand past decisions before making new ones.
