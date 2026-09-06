#!/usr/bin/env python3
"""Render a single Markdown file (post or page) to a standalone HTML page.

Usage:
    python3 render-md.py posts/my-first-post.md
    python3 render-md.py pages/about.md

Output:
    dist/my-first-post/index.html      (post)
    dist/about/index.html              (page)

The directory-style output gives clean URLs on static hosts.
"""

from __future__ import annotations

import sys
from pathlib import Path

import siteconfig
from frontmatter import parse_meta
from renderer import css_path_for, render_page, render_post, write_atomic
from slug import slug_from_filename


def render_file(src: Path):
    text = src.read_text(encoding="utf-8")

    is_post = src.resolve().is_relative_to(siteconfig.POSTS_DIR.resolve())
    meta, body = parse_meta(text, require_author=is_post,
                            require_date=is_post)
    meta.slug = meta.slug or slug_from_filename(src.stem)

    if is_post:
        html_out = siteconfig.DIST_DIR / meta.slug / "index.html"
        page = render_post(meta, body, css_path=css_path_for(html_out))
        print(f"{src.name} -> {html_out}")
    else:
        # Normal page: no date required; slug maps under dist/
        # If slug is "index", output dist/index.html, else dist/<slug>/index.html
        if meta.slug in ("index", "home"):
            html_out = siteconfig.DIST_DIR / "index.html"
        else:
            html_out = siteconfig.DIST_DIR / meta.slug / "index.html"
        page = render_page(
            meta.title,
            body,
            lang=meta.lang,
            description=meta.description,
            css_path=css_path_for(html_out),
        )
        print(f"{src.name} -> {html_out}")

    write_atomic(html_out, page)
    write_navbar_for(html_out)


def write_navbar_for(index_path: Path) -> None:
    import navbar as navbar_mod
    depth = len(index_path.parent.relative_to(siteconfig.DIST_DIR).parts)
    prefix = "../" * depth
    navbar_mod.write_navbar(index_path.parent / "navbar.html", prefix=prefix)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    for raw in sys.argv[1:]:
        src = Path(raw)
        if not src.exists():
            print(f"ERROR: not found: {src}", file=sys.stderr)
            sys.exit(1)
        try:
            render_file(src)
        except ValueError as e:
            print(f"ERROR in {src}: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
