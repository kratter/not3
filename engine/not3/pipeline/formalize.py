"""Formalize manual notes and convert text into transcript segments.

Supports transforming informal shorthand, fragments, and bullet points into
professional executive prose using local LLMs (Ollama), and segmenting text
with simulated timestamps for downstream distillation, highlighting, and lens analysis.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import Settings
    from ..llm.ollama import Client

FORMALIZE_SYSTEM = (
    "You are an expert executive editor. Your task is to transform informal, shorthand, "
    "or fragmented notes into clear, professional, grammatically complete, and formal language.\n"
    "Strict rules:\n"
    "1. Preserve ALL factual information, names, decisions, technical terms, and action items exactly as intended.\n"
    "2. Do NOT invent new facts or assume information not present or directly implied in the raw notes.\n"
    "3. Expand abbreviations and shorthand into proper professional English.\n"
    "4. Output ONLY the formalized text without preamble, pleasantries, or commentary."
)

STYLE_GUIDES: dict[str, str] = {
    "formal": (
        "Convert these shorthand/draft notes into clear, professional, executive-ready prose "
        "with well-formed, complete sentences."
    ),
    "technical": (
        "Convert these shorthand/draft notes into precise, concise technical prose "
        "suitable for engineering and architectural documentation."
    ),
    "bullet_structured": (
        "Convert these shorthand/draft notes into structured, professional bullet points "
        "and clear, formal action statements."
    ),
}


def formalize_notes(
    raw_text: str,
    style: str = "formal",
    *,
    client: Client | None = None,
    model: str | None = None,
    settings: Settings | None = None,
) -> str:
    """Rewrite raw notes into formal language using Ollama."""
    from ..config import Settings

    if not raw_text.strip():
        return ""

    s = settings or Settings.load()
    c = client or s.llm_client()
    m = model or s.model_distill

    guide = STYLE_GUIDES.get(style, STYLE_GUIDES["formal"])
    messages = [
        {"role": "system", "content": FORMALIZE_SYSTEM},
        {
            "role": "user",
            "content": f"Format and style instruction: {guide}\n\nRaw notes:\n{raw_text.strip()}",
        },
    ]

    out = c.chat(m, messages, temperature=0.2)
    return out.strip()


def text_to_segments(text: str) -> tuple[list[dict], int]:
    """Break text into sentence-level segments with simulated timestamps.

    Returns:
        (segments, total_duration_ms)
        Each segment dict contains: idx, start_ms, end_ms, text, confidence, words_json,
        and optionally _speaker if speaker prefix was detected.
    """
    raw_lines = text.strip().splitlines()
    units: list[tuple[str, str]] = []  # (speaker, text)

    for line in raw_lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Check for bullet point
        is_bullet = bool(re.match(r"^[-*•]\s+", line) or re.match(r"^\d+\.\s+", line))
        cleaned_line = re.sub(r"^[-*•]\s+", "", line)

        speaker = ""
        # Check for "Speaker: statement" or "Alice: statement"
        if ":" in cleaned_line and not is_bullet:
            possible_spk, sep, rest = cleaned_line.partition(":")
            if 0 < len(possible_spk.strip()) < 30 and rest.strip():
                speaker = possible_spk.strip()
                cleaned_line = rest.strip()

        if is_bullet:
            # Keep bullet points as atomic units
            if cleaned_line:
                units.append((speaker, cleaned_line))
        else:
            # Split regular paragraph into sentences
            sentences = re.split(r"(?<=[.!?])\s+", cleaned_line)
            for s in sentences:
                s = s.strip()
                if s:
                    units.append((speaker, s))

    rows: list[dict] = []
    cursor_ms = 0
    for idx, (spk, sentence) in enumerate(units):
        # Roughly 150 words per minute speaking rate (~400ms per word, min 1200ms)
        word_count = len(sentence.split())
        duration = max(1200, int(word_count / 150 * 60_000))
        row = {
            "idx": idx,
            "start_ms": cursor_ms,
            "end_ms": cursor_ms + duration,
            "text": sentence,
            "confidence": 1.0,
            "words_json": None,
        }
        if spk:
            row["_speaker"] = spk
        rows.append(row)
        cursor_ms += duration + 250  # 250ms simulated natural pause between sentences

    return rows, cursor_ms
