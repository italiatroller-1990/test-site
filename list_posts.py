#!/usr/bin/env python3
"""List all posts in posts/ with their front-matter metadata.

Usage:
    python3 list_posts.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Tuple

import siteconfig
from frontmatter import PostMeta, parse_meta


def collect_all_posts() -> List[Tuple[PostMeta, Path]]:
    """Collect all posts recursively from posts/.

    Returns a list of (PostMeta, source_path) tuples sorted newest-first.
    """
    rows = []
    for src in sorted(siteconfig.POSTS_DIR.rglob("*.md")):
        try:
            meta, _ = parse_meta(src.read_text(encoding="utf-8"),
                                 require_author=False)
        except ValueError as e:
            print(f"ERROR in {src.name}: {e}", file=sys.stderr)
            continue
        rows.append((meta, src))
    rows.sort(key=lambda r: r[0].date, reverse=True)
    return rows


def collect_all_pages() -> List[Tuple[PostMeta, Path]]:
    """Collect all pages from pages/.

    Returns a list of (PostMeta, source_path) tuples sorted by title.
    """
    rows = []
    for src in sorted(siteconfig.PAGES_DIR.glob("*.md")):
        try:
            meta, _ = parse_meta(src.read_text(encoding="utf-8"),
                                 require_date=False, require_author=False)
        except ValueError as e:
            print(f"ERROR in {src.name}: {e}", file=sys.stderr)
            continue
        rows.append((meta, src))
    rows.sort(key=lambda r: r[0].title)
    return rows


def format_posts_table(posts: List[Tuple[PostMeta, Path]]) -> str:
    """Format a list of posts as a readable table string."""
    if not posts:
        return "No posts found."

    lines = []
    lines.append(f"{'Date':<12} {'Title':<40} {'Slug':<40} Tags")
    lines.append("-" * 110)
    for meta, _ in posts:
        tags = ", ".join(meta.tags)
        lines.append(
            f"{meta.date.isoformat():<12} "
            f"{meta.title[:40]:<40} "
            f"{meta.slug[:40]:<40} "
            f"{tags}"
        )
    lines.append(f"\n{len(posts)} post{'s' if len(posts) != 1 else ''}")
    return "\n".join(lines)


def format_pages_table(pages: List[Tuple[PostMeta, Path]]) -> str:
    """Format a list of pages as a readable table string."""
    if not pages:
        return "No pages found."

    lines = []
    lines.append(f"{'Title':<40} {'Slug':<30}")
    lines.append("-" * 72)
    for meta, _ in pages:
        lines.append(
            f"{meta.title[:40]:<40} "
            f"{meta.slug[:30]:<30}"
        )
    lines.append(f"\n{len(pages)} page{'s' if len(pages) != 1 else ''}")
    return "\n".join(lines)


def main():
    posts = collect_all_posts()
    print(format_posts_table(posts))


if __name__ == "__main__":
    main()
