#!/usr/bin/env python3
"""Interactive post creation tool.

Usage:
    python3 new_post.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import siteconfig
from slug import slugify


def prompt(prompt_text: str, default: str | None = None) -> str:
    if default is not None:
        return input(f"{prompt_text} [{default}]: ").strip() or default
    return input(f"{prompt_text}: ").strip()


def ask_yes_no(prompt_text: str, default: str = "y") -> bool:
    suffix = " [Y/n]" if default.lower().startswith("y") else " [y/N]"
    answer = input(f"{prompt_text}{suffix}: ").strip().lower()
    if not answer:
        return default.lower().startswith("y")
    return answer.startswith("y")


def _yaml_quote(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def create_post(
    title: str,
    slug: str,
    pub_date: date,
    author: str = "",
    tags: list[str] | None = None,
    description: str = "",
    collection: str = "lifelogs",
) -> Path:
    """Create a new post Markdown file.

    Returns the path to the created file.
    Raises FileExistsError if the slug already exists.
    """
    if not author:
        author = siteconfig.DEFAULT_AUTHOR
    if tags is None:
        tags = []

    out_dir = siteconfig.POSTS_DIR / collection
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{slug}.md"

    if out.exists():
        raise FileExistsError(f"{out} already exists")

    fm = []
    fm.append("---")
    fm.append(f'title: "{_yaml_quote(title)}"')
    fm.append(f'slug: "{_yaml_quote(slug)}"')
    fm.append(f"date: {pub_date.isoformat()}")
    fm.append(f'author: "{_yaml_quote(author)}"')
    if tags:
        fm.append("tags:")
        for t in tags:
            fm.append(f'  - "{_yaml_quote(t)}"')
    if description:
        fm.append(f'description: "{_yaml_quote(description)}"')
    fm.append("---")
    fm.append("")
    fm.append(f"# {title}")
    fm.append("")
    fm.append("Write your post here...")
    fm.append("")

    out.write_text("\n".join(fm), encoding="utf-8")
    return out


def main():
    title = None
    while not title:
        title = prompt("Title")

    generated = slugify(title)
    slug = prompt(f"Slug", generated) or generated

    tags_raw = prompt("Tags (comma-separated)")
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

    author = prompt("Author", siteconfig.DEFAULT_AUTHOR) or siteconfig.DEFAULT_AUTHOR

    if ask_yes_no("Use today's date?", "y"):
        pub_date = date.today()
    else:
        while True:
            custom = prompt("Custom date")
            try:
                pub_date = date.fromisoformat(custom)
                break
            except ValueError:
                print(f"Invalid date: {custom!r}. Use YYYY-MM-DD.")

    description = prompt("Description")  # may be empty

    collections = list(siteconfig.COLLECTIONS.keys()) if hasattr(siteconfig, 'COLLECTIONS') else ["lifelogs", "guides"]
    if len(collections) == 1:
        collection = collections[0]
    else:
        print("\nCollection:")
        for i, c in enumerate(collections, 1):
            print(f"  {i}. {c}")
        choice = prompt("Select collection", "1")
        try:
            collection = collections[int(choice) - 1]
        except (ValueError, IndexError):
            collection = collections[0]

    print()
    print("Summary:")
    print(f"  Title:       {title}")
    print(f"  Slug:        {slug}")
    print(f"  Tags:        {', '.join(tags) or '(none)'}")
    print(f"  Author:      {author}")
    print(f"  Date:        {pub_date.isoformat()}")
    print(f"  Description: {description or '(none)'}")
    print(f"  Collection:  {collection}")
    print()

    if not ask_yes_no("Create this post?", "y"):
        print("Aborted.")
        sys.exit(0)

    try:
        out = create_post(title, slug, pub_date, author, tags, description, collection)
        print(f"Created {out}")
    except FileExistsError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
