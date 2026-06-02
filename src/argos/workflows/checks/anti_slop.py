"""Deterministic anti-slop lint for LLM-generated letter bodies.

Lifted from `scripts/bake_off_drafter.py` after the v1 system prompt
locked. The metrics are the deterministic signal layer for any
workflow that emits prose to be sent to a human recipient
(Outreach Drafter today; future correspondence workflows reuse).

`run_anti_slop_lint(text)` returns a dict with per-metric counts and
a `passes` boolean. Pass/fail is a SIGNAL for the adjuster, not a
hard gate — the workflow surfaces the metrics and lets the human
decide whether to send or edit.

Metric rationale lives in the bake-off iteration log (Tom's voice
feedback rounds 2026-06-01); the thresholds below are the v1 defaults
landed from that work.

Decision context: docs/DECISIONS.md →
  "Outreach Drafter v1" (when shipped)
"""
from __future__ import annotations

import re


BANNED_WORDS = {
    "delve", "leverage", "tapestry", "underscore", "foster", "robust",
    "pivotal", "intricate", "paramount", "multifaceted", "beacon",
    "realm", "enhance", "showcase", "boast", "testament", "vibrant",
    "holistic", "seamless", "elevate", "empower", "unlock",
}
BANNED_OPENERS = {
    "furthermore", "moreover", "additionally", "in today's",
    "it's worth noting that", "i am writing to inform you",
}


def _sentence_split(text: str) -> list[str]:
    """Split on sentence-end punctuation followed by whitespace + capital."""
    return [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip())
        if s.strip()
    ]


def _first_word(s: str) -> str:
    m = re.match(r"\W*([A-Za-z']+)", s)
    return m.group(1).lower() if m else ""


_NUMBERED_LIST_RE = re.compile(r"^\d+\.\s")


def _is_bullet_paragraph(p: str) -> bool:
    """A paragraph counts as a list when 2+ of its lines start with either
    an unordered bullet ("- ") or a numbered marker ("1. ", "2. ", ...).
    List paragraphs are exempt from prose word-count limits — their length
    is a structural choice, not a wall-of-text failure."""
    lines = p.split("\n")
    list_lines = sum(
        1 for ln in lines
        if ln.lstrip().startswith("- ") or _NUMBERED_LIST_RE.match(ln.lstrip())
    )
    return list_lines >= 2


def run_anti_slop_lint(text: str) -> dict:
    """Run the deterministic anti-slop checks on a letter body.

    Returns a dict of per-metric counts plus `passes` (overall boolean).
    The metrics:

    - em_dash_count            : presence of em-dashes (banned in prose)
    - banned_word_hits         : sorted list of banned words found
    - banned_opener_hits       : paragraphs opening with banned phrases
    - not_x_but_y_construction : True if "not just" or ", it's " present
    - word_count               : total words
    - paragraph_count          : number of paragraphs (split on \\n\\n)
    - avg_words_per_paragraph
    - please_count             : sentences opening with "please"
    - we_sentence_opener_count : sentences opening with "we"
    - we_paragraph_openers     : paragraphs opening with "we"
    - consecutive_we_paragraphs
    - max_paragraph_words      : longest prose paragraph (bullets exempt)
    - max_sentence_words       : longest sentence
    - paragraph_word_counts    : per-paragraph word counts (prose only)
    - max_consecutive_same_sentence_opener
    - paragraph_opener_collisions : 2+ consecutive paragraphs starting same
    - paragraph_first_words
    - first_paragraph_is_ror   : ROR formula must NOT be paragraph 1
    - passes                   : all thresholds satisfied
    """
    lower = text.lower()
    em_dashes = text.count("—")
    banned_hits = sorted(
        w for w in BANNED_WORDS if f" {w}" in lower or lower.startswith(w)
    )
    paras = [p for p in text.strip().split("\n\n") if p.strip()]
    opener_hits = [
        p[:80] for p in paras
        if any(p.lower().lstrip().startswith(o) for o in BANNED_OPENERS)
    ]
    not_x_but_y = "not just" in lower or ", it's " in lower
    word_count = len(text.split())
    avg_para_words = word_count / max(len(paras), 1)

    sentences_all = _sentence_split(text)
    please_count = sum(1 for s in sentences_all if _first_word(s) == "please")
    we_sentence_opener_count = sum(
        1 for s in sentences_all if _first_word(s) == "we"
    )

    we_paragraph_openers = sum(
        1 for p in paras
        if _first_word(_sentence_split(p)[0] if _sentence_split(p) else "") == "we"
    )
    para_first_words_check = [
        _first_word(_sentence_split(p)[0] if _sentence_split(p) else "") for p in paras
    ]
    consecutive_we_paragraphs = sum(
        1 for i in range(1, len(para_first_words_check))
        if para_first_words_check[i] == "we"
        and para_first_words_check[i - 1] == "we"
    )

    prose_paragraphs = [p for p in paras if not _is_bullet_paragraph(p)]
    paragraph_word_counts = [len(p.split()) for p in prose_paragraphs]
    max_paragraph_words = (
        max(paragraph_word_counts) if paragraph_word_counts else 0
    )
    sentence_word_counts = [len(s.split()) for s in sentences_all]
    max_sentence_words = (
        max(sentence_word_counts) if sentence_word_counts else 0
    )

    first_paragraph_is_ror = (
        bool(paras) and "reservation of rights" in paras[0].lower()
    )

    sentence_openers = [_first_word(s) for s in sentences_all]
    max_consecutive_same_opener = 0
    run, prev = 0, None
    for w in sentence_openers:
        if w and w == prev:
            run += 1
        else:
            run = 1
        max_consecutive_same_opener = max(max_consecutive_same_opener, run)
        prev = w

    para_first_words = [_first_word(p) for p in paras]
    paragraph_opener_collisions = sum(
        1 for i in range(1, len(para_first_words))
        if para_first_words[i] and para_first_words[i] == para_first_words[i - 1]
    )

    passes = (
        em_dashes == 0
        and not banned_hits
        and not opener_hits
        and not not_x_but_y
        and 80 <= word_count <= 200
        and 2 <= len(paras) <= 4
        and please_count <= 3
        and we_sentence_opener_count <= 2
        and we_paragraph_openers <= 1
        and consecutive_we_paragraphs == 0
        and max_paragraph_words <= 32
        and max_sentence_words <= 24
        and max_consecutive_same_opener <= 2
        and paragraph_opener_collisions == 0
        and not first_paragraph_is_ror
    )

    return {
        "em_dash_count": em_dashes,
        "banned_word_hits": banned_hits,
        "banned_opener_hits": opener_hits,
        "not_x_but_y_construction": not_x_but_y,
        "word_count": word_count,
        "paragraph_count": len(paras),
        "avg_words_per_paragraph": round(avg_para_words, 1),
        "please_count": please_count,
        "we_sentence_opener_count": we_sentence_opener_count,
        "we_paragraph_openers": we_paragraph_openers,
        "consecutive_we_paragraphs": consecutive_we_paragraphs,
        "max_paragraph_words": max_paragraph_words,
        "max_sentence_words": max_sentence_words,
        "paragraph_word_counts": paragraph_word_counts,
        "max_consecutive_same_sentence_opener": max_consecutive_same_opener,
        "paragraph_opener_collisions": paragraph_opener_collisions,
        "paragraph_first_words": para_first_words,
        "first_paragraph_is_ror": first_paragraph_is_ror,
        "passes": passes,
    }


__all__ = [
    "BANNED_OPENERS",
    "BANNED_WORDS",
    "run_anti_slop_lint",
]
