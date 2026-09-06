"""Slug generation using only the Python standard library."""

from __future__ import annotations

import re
import unicodedata


def slugify(text: str, *, max_length: int = 80) -> str:
    """Turn arbitrary text into a URL-safe slug.

    - lowercases text
    - replaces spaces with hyphens
    - removes unnecessary punctuation
    - collapses repeated hyphens
    - strips leading/trailing hyphens
    - handles Unicode titles reasonably (keeping non-ASCII letters/digits)
    """
    text = unicodedata.normalize("NFKC", text).lower()

    chars = []
    for ch in text:
        if ch.isalnum():
            chars.append(ch)
        elif ch in (" ", "-", "/", "_", "."):
            chars.append(" ")
        else:
            chars.append(" ")

    slug = re.sub(r"[\s\-_]+", "-", "".join(chars)).strip("-.")

    if len(slug) > max_length:
        cut = slug[:max_length]
        if "-" in cut:
            cut = cut.rsplit("-", 1)[0]
        slug = cut.rstrip("-")

    if not slug:
        raise ValueError(f"Could not generate a slug from {text!r}")

    return slug


def slug_from_filename(filename: str) -> str:
    """Derive a slug from a Markdown filename (e.g. 'my-first-post.md').

    A leading YYYY-MM-DD- date prefix is dropped, e.g.
    '2026-08-01-how-to-buy-a-laptop.md' -> 'how-to-buy-a-laptop'.
    """
    stem = filename.rsplit(".", 1)[0]
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", stem)
    return slugify(stem)
