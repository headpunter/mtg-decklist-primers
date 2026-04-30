#!/usr/bin/env python3
"""
Interactively build a deck primer using Google Gemini.

Gemini asks you questions one at a time about your deck — your strategy,
key card interactions, win conditions, and mulligan approach. When you're
done answering, it writes a polished primer.md to your deck directory.

Usage:
    python3 scripts/build_primer.py <deck-slug>

    # List available decks
    python3 scripts/build_primer.py --list

    # Resume a session (re-reads existing primer.md as context)
    python3 scripts/build_primer.py <deck-slug> --resume

Environment:
    GEMINI_API_KEY   required — get one free at https://aistudio.google.com/

Requires:
    pip install google-generativeai pyyaml
"""

import argparse
import json
import os
import sys
import textwrap
from pathlib import Path

import yaml

try:
    import google.generativeai as genai
except ImportError:
    sys.exit(
        "Missing dependency: pip install google-generativeai\n"
        "Also make sure GEMINI_API_KEY is set."
    )

DECKS_DIR = Path(__file__).parent.parent / "decks"

# ---------------------------------------------------------------------------
# Colour / terminal helpers
# ---------------------------------------------------------------------------

RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[36m"
YELLOW = "\033[33m"
GREEN  = "\033[32m"
DIM    = "\033[2m"


def c(text: str, code: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"{code}{text}{RESET}"


def wrap(text: str, width: int = 90, indent: str = "  ") -> str:
    lines = text.splitlines()
    out = []
    for line in lines:
        if not line.strip():
            out.append("")
        else:
            out.extend(
                textwrap.wrap(line, width=width, initial_indent=indent,
                              subsequent_indent=indent)
            )
    return "\n".join(out)


def hr() -> None:
    print(c("─" * 70, DIM))


# ---------------------------------------------------------------------------
# Deck loading
# ---------------------------------------------------------------------------

def load_deck(slug: str) -> tuple[dict, list[dict]]:
    """Return (meta, cards) for the given slug. Raises SystemExit on error."""
    deck_dir = DECKS_DIR / slug

    meta_path  = deck_dir / "meta.yaml"
    cards_path = deck_dir / "cards.json"

    if not deck_dir.exists():
        sys.exit(f"Deck not found: {deck_dir}\nRun: python3 scripts/import_archidekt.py first.")

    meta: dict = {}
    if meta_path.exists():
        with open(meta_path, encoding="utf-8") as fh:
            meta = yaml.safe_load(fh) or {}

    cards: list[dict] = []
    if cards_path.exists():
        cards = json.loads(cards_path.read_text(encoding="utf-8"))

    return meta, cards


def summarise_deck(meta: dict, cards: list[dict]) -> str:
    """Build a compact deck summary to inject as system context."""
    commander = meta.get("commander") or "Unknown Commander"
    colors    = "/".join(meta.get("colors") or []) or "?"
    themes    = ", ".join(meta.get("themes") or []) or "(none tagged yet)"
    power     = meta.get("power_level") or "?"
    archidekt = meta.get("links", {}).get("archidekt", "")

    # Group cards by category for the summary
    by_cat: dict[str, list[str]] = {}
    for c_card in cards:
        cat = c_card.get("category", "Other")
        by_cat.setdefault(cat, []).append(
            f"{c_card['qty']}x {c_card['name']}"
        )

    cat_blocks = []
    for cat, names in sorted(by_cat.items()):
        cat_blocks.append(f"{cat} ({len(names)}):\n  " + ", ".join(names))

    card_summary = "\n".join(cat_blocks)

    return f"""\
Commander : {commander}
Colors    : {colors}
Themes    : {themes}
Power     : {power}
Archidekt : {archidekt}

Full card list:
{card_summary}
"""


# ---------------------------------------------------------------------------
# Gemini setup
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert Magic: The Gathering Commander (EDH) deck-building assistant \
helping the pilot of this deck write a detailed primer.

Your job is to interview the player about their deck through a series of \
targeted, conversational questions — one question at a time. After they answer, \
ask the next most relevant follow-up. Keep questions specific and tactical.

Cover these areas before writing the primer:
1. Core strategy and game plan (what does the deck *do*?)
2. Key card interactions and combo lines
3. Win conditions (fast vs. slow, primary vs. backup)
4. How to sequence the early turns (ramp, setup)
5. What the ideal board state looks like at turns 4–6
6. Mulligan philosophy: what lands/cards must a keepable hand have?
7. Meta context: what power level, what kind of pod does it face?
8. Weaknesses and how to play around them

When the user types "done" or "generate", stop asking questions and output \
a complete, well-structured primer in GitHub-flavoured Markdown. The primer \
must include these sections:
  ## Overview
  ## Game Plan (Early / Mid / Late)
  ## Key Cards  (table: Card | Role)
  ## Combo Lines / Win Conditions
  ## Mulligan Guide  (Keep / Throw Back, 2-3 example hands)
  ## Weaknesses

Be direct and tactical — write for a player who knows Magic but may be \
learning this deck. No filler. Use bullet points and tables where helpful.
"""


def build_model(api_key: str) -> genai.GenerativeModel:
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=SYSTEM_PROMPT,
    )


# ---------------------------------------------------------------------------
# Interactive session
# ---------------------------------------------------------------------------

HELP_TEXT = """
Commands (type at the prompt):
  done / generate   — stop Q&A and generate the primer now
  skip              — skip this question
  cards             — print the full card list
  meta              — print deck metadata
  quit / exit       — exit without saving
  help              — show this message
"""


def run_session(slug: str, resume: bool = False) -> None:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        sys.exit(
            "GEMINI_API_KEY not set.\n"
            "Get a free key at https://aistudio.google.com/ then:\n"
            "  export GEMINI_API_KEY=your-key-here"
        )

    meta, cards = load_deck(slug)
    deck_name = meta.get("deck_name") or meta.get("commander") or slug
    primer_path = DECKS_DIR / slug / "primer.md"

    print()
    hr()
    print(c(f"  Primer Builder — {deck_name}", BOLD + CYAN))
    hr()
    print(c("  Type 'help' for commands, 'done' when ready to generate.\n", DIM))

    # Build initial context message
    deck_summary = summarise_deck(meta, cards)
    initial_msg = (
        f"Here is the deck I want to build a primer for:\n\n{deck_summary}\n\n"
        "Please start by asking me your first question about this deck."
    )

    if resume and primer_path.exists():
        existing = primer_path.read_text(encoding="utf-8")
        initial_msg = (
            f"Here is the deck I want to update the primer for:\n\n{deck_summary}\n\n"
            f"Here is the existing primer:\n\n{existing}\n\n"
            "Please ask me questions to fill in gaps or improve weak sections."
        )

    model = build_model(api_key)
    chat  = model.start_chat()

    # Kick off with deck context
    print(c("  Sending deck context to Gemini …\n", DIM))
    response = chat.send_message(initial_msg)
    gemini_text = response.text.strip()

    print(c("Gemini:", YELLOW + BOLD))
    print(wrap(gemini_text))
    print()

    final_primer: str | None = None

    while True:
        try:
            user_input = input(c("You: ", GREEN + BOLD)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            print(c("\nSession ended (no primer saved).", DIM))
            sys.exit(0)

        if not user_input:
            continue

        cmd = user_input.lower()

        if cmd in ("help", "?"):
            print(c(HELP_TEXT, DIM))
            continue

        if cmd in ("quit", "exit"):
            print(c("Exiting without saving.", DIM))
            sys.exit(0)

        if cmd == "cards":
            hr()
            for cat_name, lines in sorted(
                {
                    cat: [f"  {c2['qty']}x {c2['name']}" for c2 in cs]
                    for cat, cs in {
                        c3.get("category", "Other"): [] for c3 in cards
                    }.items()
                }.items()
            ):
                print(c(f"{cat_name}", BOLD))
            # Simpler version:
            by_cat: dict[str, list] = {}
            for card in cards:
                by_cat.setdefault(card.get("category", "Other"), []).append(card)
            for cat in sorted(by_cat):
                print(c(f"\n{cat}", BOLD))
                for card in sorted(by_cat[cat], key=lambda x: x["name"]):
                    print(f"  {card['qty']}x {card['name']}")
            hr()
            continue

        if cmd == "meta":
            hr()
            print(yaml.dump(meta, default_flow_style=False, allow_unicode=True))
            hr()
            continue

        if cmd in ("done", "generate"):
            print()
            print(c("  Generating primer …", DIM))
            generate_msg = (
                "The player has finished answering questions. "
                "Now write the complete, polished primer in GitHub-flavoured Markdown "
                "using all the information gathered. Output ONLY the markdown — "
                "no preamble, no 'here is the primer' header."
            )
            response = chat.send_message(generate_msg)
            final_primer = response.text.strip()
            break

        if cmd == "skip":
            response = chat.send_message(
                "(The player skipped this question.) Please ask the next question."
            )
        else:
            response = chat.send_message(user_input)

        gemini_text = response.text.strip()
        print()
        print(c("Gemini:", YELLOW + BOLD))
        print(wrap(gemini_text))
        print()

        # If Gemini spontaneously generated the primer (it sometimes does),
        # detect it and treat it as the final output.
        if gemini_text.startswith("# ") and "## " in gemini_text:
            confirm = input(
                c("Gemini generated a primer. Save it? [Y/n]: ", CYAN)
            ).strip().lower()
            if confirm in ("", "y", "yes"):
                final_primer = gemini_text
                break

    # -------------------------------------------------------------------
    # Save the primer
    # -------------------------------------------------------------------
    if final_primer:
        primer_path.write_text(final_primer + "\n", encoding="utf-8")
        print()
        hr()
        print(c(f"  Primer saved to {primer_path}", GREEN + BOLD))
        hr()
        print()
        # Preview first 20 lines
        preview = "\n".join(final_primer.splitlines()[:20])
        print(wrap(preview))
        if len(final_primer.splitlines()) > 20:
            print(c("  … (truncated — open primer.md to read the full text)", DIM))
        print()
    else:
        print(c("  No primer generated.", DIM))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Interactively build a deck primer with Google Gemini",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument(
        "slug", nargs="?",
        help="Deck slug (folder name under decks/)",
    )
    ap.add_argument(
        "--list", action="store_true",
        help="List all available deck slugs and exit",
    )
    ap.add_argument(
        "--resume", action="store_true",
        help="Load existing primer.md as context before asking new questions",
    )
    args = ap.parse_args()

    if args.list or not args.slug:
        slugs = sorted(
            d.name for d in DECKS_DIR.iterdir()
            if d.is_dir() and not d.name.startswith("_")
        )
        if not slugs:
            print("No decks imported yet. Run: python3 scripts/import_archidekt.py")
        else:
            print("Available decks:")
            for s in slugs:
                meta_path = DECKS_DIR / s / "meta.yaml"
                commander = ""
                if meta_path.exists():
                    m = yaml.safe_load(meta_path.read_text()) or {}
                    commander = m.get("commander", "")
                primer_exists = (DECKS_DIR / s / "primer.md").exists()
                stub_marker   = "(stub)" if not primer_exists else ""
                print(f"  {s:<40} {commander:<30} {stub_marker}")
        if not args.slug:
            ap.print_help()
        sys.exit(0)

    run_session(args.slug, resume=args.resume)


if __name__ == "__main__":
    main()
