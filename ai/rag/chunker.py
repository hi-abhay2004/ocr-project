"""
L6 — answer chunking.

Splits reconstructed answer text (ai.reconstruct, L5) into sentence-level
chunks for retrieval against a question's Concept embeddings — long
sentences are further split on clause (comma) boundaries, since a single
40-word sentence covering three separate concepts would otherwise force
retrieval to match all three against one overly-broad vector.

Chunks overlapping an `underlined_spans` character range are tagged
`underlined=True` — ai.scoring.apply_underline_boost applies only to what
the student themselves emphasised, not to every chunk indiscriminately.
"""

import re
from dataclasses import dataclass

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_CLAUSE_SPLIT_RE = re.compile(r"(,\s+)")

# A sentence longer than this is worth splitting further on its clauses —
# short sentences rarely bundle more than one concept, so splitting them
# too would just produce noisy, under-sized chunks.
LONG_SENTENCE_CHARS = 90
MIN_CLAUSE_CHARS = 15  # a clause fragment shorter than this isn't worth its own chunk


@dataclass
class Chunk:
    text: str
    start: int  # character offset into the source text
    end: int
    underlined: bool = False


def _overlaps_any(start: int, end: int, spans: tuple) -> bool:
    return any(start < e and s < end for s, e in spans)


def _split_sentence(sentence: str) -> list[str]:
    if len(sentence) <= LONG_SENTENCE_CHARS:
        return [sentence]
    parts = _CLAUSE_SPLIT_RE.split(sentence)
    if len(parts) <= 1:
        return [sentence]
    merged = []
    # parts looks like: [clause1, delim1, clause2, delim2, clause3]
    for i in range(0, len(parts)):
        piece = parts[i]
        if i % 2 == 1:
            # this is a delimiter, just append to the last merged clause
            if merged:
                merged[-1] += piece
        else:
            # this is a clause
            if merged and len(piece) < MIN_CLAUSE_CHARS:
                merged[-1] += piece
            else:
                merged.append(piece)
    return merged


def chunk_text(text: str, underlined_spans: tuple = ()) -> list[Chunk]:
    text = text.strip()
    if not text:
        return []

    chunks = []
    cursor = 0
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        for piece in _split_sentence(sentence):
            piece = piece.strip()
            if not piece:
                continue
            start = text.index(piece, cursor)
            end = start + len(piece)
            cursor = end
            chunks.append(
                Chunk(
                    text=piece,
                    start=start,
                    end=end,
                    underlined=_overlaps_any(start, end, underlined_spans),
                )
            )
    return chunks
