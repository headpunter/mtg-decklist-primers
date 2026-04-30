#!/usr/bin/env python3
"""
EDH Collection — web interface.

Start:  uvicorn app:app --reload
Docker: docker compose up
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DECKS_DIR = Path(os.environ.get("DECKS_DIR", "decks"))
GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ARCHIDEKT_USERNAME = os.environ.get("ARCHIDEKT_USERNAME", "")

AI_PROVIDER = "gemini" if GEMINI_API_KEY else "claude" if ANTHROPIC_API_KEY else None

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="EDH Collection")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

NOTICE_MARKER = "<!-- deck-updated-notice -->"
STUB_MARKER   = "This primer is a stub"

COLOR_ORDER = ["W", "U", "B", "R", "G", "C"]


def primer_status(deck_dir: Path) -> str:
    p = deck_dir / "primer.md"
    if not p.exists():
        return "missing"
    text = p.read_text(encoding="utf-8")
    if STUB_MARKER in text:
        return "stub"
    if NOTICE_MARKER in text:
        return "needs-update"
    return "done"


def load_decks() -> list[dict]:
    decks = []
    if not DECKS_DIR.exists():
        return decks

    for deck_dir in sorted(DECKS_DIR.iterdir()):
        if not deck_dir.is_dir() or deck_dir.name.startswith("_"):
            continue
        meta_path = deck_dir / "meta.yaml"
        if not meta_path.exists():
            continue

        try:
            meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue

        # Commander art — pull from cards.json
        commander_art = ""
        cards_path = deck_dir / "cards.json"
        if cards_path.exists():
            try:
                cards = json.loads(cards_path.read_text(encoding="utf-8"))
                cmd_card = next(
                    (c for c in cards if "Commander" in c.get("categories", [])),
                    None,
                )
                if cmd_card:
                    commander_art = (
                        cmd_card.get("image_url_normal")
                        or cmd_card.get("image_url")
                        or ""
                    )
            except Exception:
                pass

        colors = meta.get("colors") or []
        colors_sorted = sorted(colors, key=lambda x: COLOR_ORDER.index(x) if x in COLOR_ORDER else 99)

        decks.append({
            **meta,
            "slug": deck_dir.name,
            "commander_art": commander_art,
            "primer_status": primer_status(deck_dir),
            "colors_sorted": colors_sorted,
            "archidekt_url": meta.get("links", {}).get("archidekt", ""),
        })

    return decks


def deck_summary_for_ai(decks: list[dict]) -> str:
    lines = []
    for d in decks:
        colors = "/".join(d.get("colors_sorted") or []) or "?"
        themes = ", ".join(d.get("themes") or []) or "none tagged"
        power  = d.get("power_level") or "?"
        status = d.get("status") or "concept"
        commander = d.get("commander") or d.get("deck_name") or d["slug"]
        lines.append(
            f"- **{commander}** | {colors} | {themes} | power {power} | {status}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# AI recommendation
# ---------------------------------------------------------------------------

RECOMMEND_SYSTEM = (
    "You are an expert Magic: The Gathering Commander deckbuilder. "
    "Be direct and specific. Format your response in clean markdown."
)

RECOMMEND_PROMPT = """\
Here are all the Commander decks in my collection (built and planned):

{deck_list}

{user_context}

Based on this collection, recommend 3 Commander decks I should build next.
For each recommendation include:
- **Commander name** and color identity
- **Play style** (aggro / control / combo / midrange / stax / etc.)
- **Power level** estimate (1-10)
- **Why it fits** — what gap it fills in my collection (color coverage, archetype, play style)
- **2-3 key cards** that make the deck tick

Consider: color identity gaps, archetype diversity, play style variety, and
commanders that are interesting and fun to pilot.
"""


async def stream_gemini(prompt: str):
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        "gemini-1.5-flash",
        system_instruction=RECOMMEND_SYSTEM,
    )
    response = model.generate_content(prompt, stream=True)
    for chunk in response:
        if chunk.text:
            yield chunk.text


async def stream_claude(prompt: str):
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=RECOMMEND_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    decks = load_decks()
    built   = sum(1 for d in decks if d.get("status") == "built")
    concept = sum(1 for d in decks if d.get("status") != "built")
    primers_done = sum(1 for d in decks if d["primer_status"] == "done")

    return templates.TemplateResponse("index.html", {
        "request":      request,
        "decks":        decks,
        "total":        len(decks),
        "built":        built,
        "concept":      concept,
        "primers_done": primers_done,
        "ai_provider":  AI_PROVIDER,
        "username":     ARCHIDEKT_USERNAME,
    })


@app.get("/recommend", response_class=HTMLResponse)
async def recommend_page(request: Request):
    decks = load_decks()
    return templates.TemplateResponse("recommend.html", {
        "request":     request,
        "decks":       decks,
        "ai_provider": AI_PROVIDER,
        "total":       len(decks),
    })


@app.post("/recommend/generate")
async def generate_recommendation(
    user_context: str = Form(default=""),
):
    if not AI_PROVIDER:
        async def no_key():
            yield "**Error:** No AI API key configured. Set GEMINI_API_KEY or ANTHROPIC_API_KEY."
        return StreamingResponse(no_key(), media_type="text/plain")

    decks = load_decks()
    deck_list = deck_summary_for_ai(decks)
    context_block = f"Additional context from me:\n{user_context}" if user_context.strip() else ""
    prompt = RECOMMEND_PROMPT.format(deck_list=deck_list, user_context=context_block)

    stream = stream_gemini(prompt) if AI_PROVIDER == "gemini" else stream_claude(prompt)
    return StreamingResponse(stream, media_type="text/plain")


@app.get("/deck/{slug}", response_class=HTMLResponse)
async def deck_detail(request: Request, slug: str):
    deck_dir = DECKS_DIR / slug
    if not deck_dir.exists():
        return HTMLResponse("Deck not found", status_code=404)

    meta = {}
    meta_path = deck_dir / "meta.yaml"
    if meta_path.exists():
        meta = yaml.safe_load(meta_path.read_text()) or {}

    cards = []
    cards_path = deck_dir / "cards.json"
    if cards_path.exists():
        cards = json.loads(cards_path.read_text())

    primer = ""
    primer_path = deck_dir / "primer.md"
    if primer_path.exists():
        raw = primer_path.read_text(encoding="utf-8")
        primer = re.sub(r"<!-- deck-updated-notice -->.*?\n\n", "", raw, flags=re.DOTALL).strip()

    # Group cards by category
    by_cat: dict[str, list] = {}
    for c in cards:
        by_cat.setdefault(c.get("category", "Other"), []).append(c)

    colors = meta.get("colors") or []
    colors_sorted = sorted(colors, key=lambda x: COLOR_ORDER.index(x) if x in COLOR_ORDER else 99)

    return templates.TemplateResponse("deck.html", {
        "request":        request,
        "meta":           meta,
        "slug":           slug,
        "cards":          cards,
        "by_cat":         by_cat,
        "primer":         primer,
        "primer_status":  primer_status(deck_dir),
        "colors_sorted":  colors_sorted,
        "total_cards":    sum(c["qty"] for c in cards),
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
