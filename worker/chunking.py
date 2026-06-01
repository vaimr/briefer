"""Text chunking for long transcripts.

Splits long texts into sentence-bound chunks suitable for LLM processing,
and merges per-chunk summaries back into a single coherent summary.
"""

import re


def chunk_text(text: str, chunk_size: int = 3000) -> list[str]:
    """Split *text* into chunks bounded by sentence boundaries.

    Parameters
    ----------
    text : str
        Input text to split.
    chunk_size : int
        Maximum characters per chunk (default 3000).

    Returns
    -------
    list[str]
        Non-empty chunks, each at least 200 characters.
        Returns ``[text]`` if ``len(text) <= chunk_size``.
        Returns ``[]`` for empty/whitespace-only input.
    """
    if not text or not text.strip():
        return []

    if len(text) <= chunk_size:
        return [text]

    # Split on sentence-ending punctuation followed by whitespace
    sentences = re.split(r'(?<=[.!?])\s+', text)

    chunks: list[str] = []
    current: str = ""

    for sentence in sentences:
        candidate = (current + " " + sentence) if current else sentence
        if len(candidate) > chunk_size and current:
            chunks.append(current.strip())
            current = sentence
        else:
            current = candidate

    if current.strip():
        chunks.append(current.strip())

    # Filter out micro-chunks (< 200 chars)
    return [c for c in chunks if len(c) >= 200]


def merge_summaries(summaries: list[str]) -> str:
    """Merge per-chunk summaries into a single text.

    Parameters
    ----------
    summaries : list[str]
        List of summary strings produced by LLM per chunk.

    Returns
    -------
    str
        Merged summary, or sentinel if no summaries provided.
    """
    if not summaries:
        return "Не удалось создать саммари"
    if len(summaries) == 1:
        return summaries[0]

    return "\n\n---\n\n".join(summaries)
