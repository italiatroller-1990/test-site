"""Front matter parsing and validation for Markdown posts/pages."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

import siteconfig


@dataclass
class PostMeta:
    title: str
    slug: str
    date: date
    author: str
    tags: List[str] = field(default_factory=list)
    description: str = ""
    lang: str = "en"
    extra: Dict[str, Any] = field(default_factory=dict)


TITLE_CAPITALIZATION = False  # leave as-is; translation handles language specifics


def split_front_matter(text: str) -> tuple[Optional[Dict[str, Any]], str]:
    """Split YAML front matter from the Markdown body.

    Returns (front_matter_dict_or_None, body). Raises ValueError on malformed
    front matter that does not close.
    """
    if not text.startswith("---"):
        return None, text

    # Find the closing '---' line. Front matter must open and close on their
    # own lines.
    lines = text.split("\n")
    # The first line is the opening '---'. Find the matching close.
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            fm_lines = lines[1:idx]
            body = "\n".join(lines[idx + 1:])
            try:
                data = yaml.safe_load("\n".join(fm_lines)) or {}
            except yaml.YAMLError as exc:
                raise ValueError(f"Invalid YAML front matter: {exc}") from exc
            if not isinstance(data, dict):
                raise ValueError("Front matter must be a YAML mapping")
            return data, body

    raise ValueError("Front matter starts with '---' but never closes")


def parse_date(value: Any, field: str = "date") -> date:
    """Parse a date from YAML (date object or ISO string)."""
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError as exc:
            raise ValueError(
                f"Invalid {field!r} value {value!r} (expected YYYY-MM-DD)"
            ) from exc
    raise ValueError(f"Invalid {field!r} value {value!r} (expected YYYY-MM-DD)")


def parse_meta(text: str, *, require_date: bool = True,
               require_author: bool = True) -> tuple[PostMeta, str]:
    """Parse front matter + body into a validated PostMeta and the body.

    Slugs are optional here because callers derive them from filenames;
    missing authors default to siteconfig.DEFAULT_AUTHOR.
    """
    data, body = split_front_matter(text)

    if data is None:
        raise ValueError("Missing YAML front matter")

    # Required fields
    title = data.get("title")
    slug = data.get("slug")
    author = data.get("author")
    date_val = data.get("date")

    missing = []
    if not title or not str(title).strip():
        missing.append("title")
    if require_date and not date_val:
        missing.append("date")
    if require_author and not author:
        missing.append("author")

    if missing:
        raise ValueError(
            f"Missing required front matter field(s): {', '.join(missing)}"
        )

    parsed_date = parse_date(date_val) if date_val else date.today()
    author_str = str(author).strip() if author else siteconfig.DEFAULT_AUTHOR
    slug_str = str(slug).strip() if slug else ""

    tags_raw = data.get("tags") or []
    if isinstance(tags_raw, str):
        tags_raw = [t.strip() for t in tags_raw.split(",") if t.strip()]
    tags = [str(t).strip() for t in tags_raw if str(t).strip()]

    description = str(data.get("description") or "").strip()
    lang = str(data.get("lang") or "en")

    meta = PostMeta(
        title=str(title).strip(),
        slug=slug_str,
        date=parsed_date,
        author=str(author).strip(),
        tags=tags,
        description=description,
        lang=lang,
        extra=data,
    )
    return meta, body


def content_hash(text: str) -> str:
    """SHA-256 hex digest used for translation cache invalidation."""
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()
