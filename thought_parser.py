"""
thought_parser.py — Classifies raw Chain-of-Thought text into typed ThoughtChunks.

The LLM returns a free-form "thinking" string as part of the CoT envelope.
This module splits it into paragraphs and classifies each as one of:
  understanding, decision, assumption, warning

Used by pipeline_runner.py to build structured thoughts for the frontend.
"""

from __future__ import annotations

import re
import time
from typing import List, Literal

from api_models import ThoughtChunk

ThoughtType = Literal["understanding", "decision", "assumption", "warning"]

_KEYWORDS: dict[ThoughtType, list[str]] = {
    "understanding": [
        "user wants", "user needs", "request", "requirement", "interpret",
        "need to", "they want", "asking for", "description says",
        "the prompt", "understand", "looking for",
    ],
    "decision": [
        "choose", "select", "use", "will use", "opted", "pattern",
        "topology", "connect", "architecture", "design", "place",
        "deploy", "assign", "configure", "router-on-a-stick",
        "hierarchical", "star", "ring", "mesh", "core switch",
    ],
    "assumption": [
        "assume", "assuming", "expect", "presumably", "should have",
        "likely", "probably", "by default", "unless specified",
        "not mentioned", "no specific",
    ],
    "warning": [
        "limit", "constraint", "cannot", "max", "exceed", "careful",
        "risk", "workaround", "insufficient", "only supports",
        "restriction", "not enough", "bus limit", "pci",
    ],
}

_COMPILED: dict[ThoughtType, re.Pattern] = {
    ttype: re.compile("|".join(re.escape(kw) for kw in kws), re.IGNORECASE)
    for ttype, kws in _KEYWORDS.items()
}


def _classify_paragraph(text: str) -> ThoughtType:
    scores: dict[ThoughtType, int] = {t: 0 for t in _KEYWORDS}
    for ttype, pattern in _COMPILED.items():
        scores[ttype] = len(pattern.findall(text))

    best = max(scores, key=lambda t: scores[t])
    if scores[best] == 0:
        return "decision"
    return best


def _split_into_paragraphs(raw: str) -> List[str]:
    raw = raw.strip()
    if not raw:
        return []

    chunks = re.split(r"\n\s*\n", raw)

    result: List[str] = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        sub = re.split(r"(?m)^(?=[a-e]\)|[1-9]\.)\s*", chunk)
        for s in sub:
            s = s.strip()
            if s:
                result.append(s)

    return result


def parse_thinking_text(raw_thinking: str) -> List[ThoughtChunk]:
    paragraphs = _split_into_paragraphs(raw_thinking)
    chunks: List[ThoughtChunk] = []

    for i, para in enumerate(paragraphs):
        ttype = _classify_paragraph(para)
        chunks.append(ThoughtChunk(
            id=f"thought-{i}",
            type=ttype,
            content=para,
            timestamp=time.time(),
        ))

    return chunks
