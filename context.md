# Decision Log

Reverse-chronological log of architectural and design decisions.

---

## 2026-05-04 — No Rust rewrite

**Decision:** Keep the codebase in Python. Do not rewrite in Rust.

**Rationale:** The app is almost entirely I/O-bound — Archidekt and Scryfall API latency is the bottleneck, not Python execution speed. The interactive primer builder (`build_primer.py`) relies on Gemini, which has no official Rust SDK, and the terminal Q&A loop would be significantly more painful to implement in Rust (raw SSE parsing, rustyline). The project is a personal tool, so Docker image size (~250 MB Python vs ~15 MB Rust static binary) doesn't matter in practice. A rewrite would take 2–3 weeks for no perceptible day-to-day improvement.
