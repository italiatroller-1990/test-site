#!/usr/bin/env python3
"""Build the entire static site into dist/.

Orchestration:
    posts/  ──►  front matter + Markdown render  ──►  dist/<slug>/index.html
    pages/  ──►  front matter + Markdown render  ──►  dist/<page>/index.html
    translations/<lang>/... ──► rendered at dist/<lang>/<slug>/index.html
    static assets populated from config           ──►  dist/

Usage:
    python3 build.py            # full build
    python3 build.py --clean    # delete dist/ first
    python3 build.py --translate # run translation before building (requires API key)
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

import siteconfig
from frontmatter import PostMeta, parse_meta
from renderer import (
    css_path_for,
    render_page,
    render_post,
    render_post_listing,
    write_atomic,
)
from slug import slug_from_filename

# Posts in these directories (or directly in posts/) form the site's blog.
COLLECTIONS = {"lifelogs": "Lifelogs", "guides": "Guides"}

LISTING_MARKER = "<!-- POSTLIST -->"


def clean() -> None:
    if siteconfig.DIST_DIR.exists():
        shutil.rmtree(siteconfig.DIST_DIR)
        print(f"Cleaned {siteconfig.DIST_DIR}")


def copy_static() -> None:
    # Regenerate the navbar fragment so links match NAV_ITEMS exactly.
    import navbar as navbar_mod
    navbar_mod.write_navbar(siteconfig.ROOT / "navbar.html")

    for item in siteconfig.STATIC_ASSETS:
        src = siteconfig.ROOT / item
        if not src.exists():
            print(f"WARN: static asset missing: {item}")
            continue
        dst = siteconfig.DIST_DIR / item
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        print(f"  copy {item}")


def collect_posts():
    """Yield (src, meta, body) for every post under posts/ (recursively).

    The parent directory name (or 'lifelogs' for posts directly in posts/)
    determines the collection. Slugs come from explicit frontmatter or the
    filename.
    """
    for src in sorted(siteconfig.POSTS_DIR.rglob("*.md")):
        meta, body = parse_meta(src.read_text(encoding="utf-8"),
                                require_author=False,
                                require_date=True)
        rel = src.parent.relative_to(siteconfig.POSTS_DIR)
        collection = rel.parts[0] if rel.parts else "lifelogs"
        meta.slug = meta.slug or slug_from_filename(src.stem)
        meta.extra["collection"] = collection
        yield src, meta, body


def render_pages(collections) -> int:
    """Render pages/ → dist/<slug>/index.html. Returns count.

    A page with matching ``collection`` frontmatter and a LISTING_MARKER in
    its body gets a generated post listing injected at that marker.
    """
    count = 0
    for src in sorted(siteconfig.PAGES_DIR.glob("*.md")):
        try:
            meta, body = parse_meta(src.read_text(encoding="utf-8"),
                                    require_date=False, require_author=False)
        except ValueError as e:
            print(f"  ERROR {src.name}: {e}", file=sys.stderr)
            continue

        slug = meta.slug or slug_from_filename(src.stem)
        if slug in ("index", "home"):
            out = siteconfig.DIST_DIR / "index.html"
        else:
            out = siteconfig.DIST_DIR / slug / "index.html"

        collection = meta.extra.get("collection") or ""
        if LISTING_MARKER in body and collection in collections:
            posts = sorted(collections[collection],
                           key=lambda m: m.date, reverse=True)
            listing = render_post_listing(posts, prefix="../")
            body = body.replace(LISTING_MARKER, f"\n{listing}\n")
            print(f"  listing {len(posts)} posts into {src.name}")

        html = render_page(
            meta.title, body, lang=meta.lang,
            description=meta.description, css_path=css_path_for(out),
        )
        write_atomic(out, html)
        print(f"  page {src.name} -> {out.relative_to(siteconfig.DIST_DIR)}")
        count += 1
    return count


def render_posts(posts, lang: str = "en", lang_prefix: str = "") -> int:
    """Render posts into dist[/<lang_prefix>]/<slug>/index.html."""
    count = 0
    for src, meta, body in posts:
        base = siteconfig.DIST_DIR
        if lang_prefix:
            base = siteconfig.DIST_DIR / lang
        out = base / meta.slug / "index.html"

        html = render_post(meta, body, css_path=css_path_for(out))
        write_atomic(out, html)
        print(f"  post {src.name} -> {out.relative_to(siteconfig.DIST_DIR)}")
        count += 1
    return count


def render_translations() -> int:
    """Render any existing translations/ import so translated pages appear in dist.

    Structure: translations/<lang>/<slug>.md  →  dist/<lang>/<slug>/index.html
    """
    count = 0
    if not siteconfig.TRANSLATIONS_DIR.exists():
        return 0
    for lang_dir in sorted(p for p in siteconfig.TRANSLATIONS_DIR.iterdir() if p.is_dir()):
        lang = lang_dir.name
        files = sorted(lang_dir.glob("*.md"))
        for f in files:
            try:
                meta, body = parse_meta(f.read_text(encoding="utf-8"))
            except ValueError as e:
                print(f"  ERROR {f.name}: {e}", file=sys.stderr)
                continue
            meta.lang = lang
            out = siteconfig.DIST_DIR / lang / meta.slug / "index.html"
            html = render_post(meta, body, css_path=css_path_for(out))
            write_atomic(out, html)
            print(f"  l10n {lang}/{f.name} -> {out.relative_to(siteconfig.DIST_DIR)}")
            count += 1
    return count


def write_navbars() -> None:
    """Drop a navbar.html fragment into every page directory.

    Each fragment gets relative paths (../ repeated by depth) so stylesheets,
    the favicon and links resolve correctly regardless of page depth.
    """
    import navbar as navbar_mod
    for index in siteconfig.DIST_DIR.rglob("index.html"):
        depth = len(index.parent.relative_to(siteconfig.DIST_DIR).parts)
        prefix = "../" * depth
        navbar_mod.write_navbar(index.parent / "navbar.html", prefix=prefix)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--clean", action="store_true", help="delete dist/ before building")
    p.add_argument("--translate", action="store_true",
                   help="run translation before building (requires NVIDIA_API_KEY)")
    p.add_argument("--langs", default=",".join(siteconfig.LANGS),
                   help="languages for --translate")
    args = p.parse_args(argv)

    if args.clean:
        clean()

    siteconfig.DIST_DIR.mkdir(parents=True, exist_ok=True)

    print("Building static site...")
    print(f"Output dir: {siteconfig.DIST_DIR}")

    if args.translate:
        print("Translating (before rendering)...")
        import translate
        rc = translate.main(["--langs", args.langs])
        if rc != 0:
            print("Translation failed; aborting build.", file=sys.stderr)
            return rc

    print("Static assets:")
    copy_static()

    print("Collecting posts:")
    all_posts = list(collect_posts())
    collections: dict[str, list[PostMeta]] = {}
    for src, meta, body in all_posts:
        collections.setdefault(meta.extra.get("collection", "lifelogs"), []).append(meta)
    for name, items in collections.items():
        print(f"  {name}: {len(items)} posts")

    print("Pages:")
    np = render_pages(collections)

    print("Posts:")
    npost = render_posts(all_posts)

    print("Translations:")
    nt = render_translations()

    print("Navbars:")
    write_navbars()

    print()
    print(f"Done. {np} pages, {npost} posts, {nt} translated docs -> {siteconfig.DIST_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())