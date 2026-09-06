#!/usr/bin/env python3
"""Italia Troller Site Toolkit — unified management interface.

A lightweight CLI/TUI over the existing static site modules.

Usage:
    ./site-tk.py              Interactive menu
    ./site-tk.py build        Build the site
    ./site-tk.py posts        List posts
    ./site-tk.py new-post     Create a post
    ./site-tk.py edit-post    Edit a post
    ./site-tk.py delete-post  Delete a post
    ./site-tk.py pages        List pages
    ./site-tk.py new-page     Create a page
    ./site-tk.py edit-page    Edit a page
    ./site-tk.py delete-page  Delete a page
    ./site-tk.py translate    Translate content
    ./site-tk.py clean        Clean build output
    ./site-tk.py info         Show site information
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Project modules
# ---------------------------------------------------------------------------
import siteconfig
from frontmatter import PostMeta, parse_meta, split_front_matter
from list_posts import (
    collect_all_pages,
    collect_all_posts,
    format_pages_table,
    format_posts_table,
)
from new_post import create_post
from slug import slugify

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VERSION = "1.0.0"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"

DEBUG = False


# ===========================================================================
# Utilities
# ===========================================================================

def header(text: str) -> None:
    width = max(len(text) + 4, 32)
    print(f"\n{BOLD}{text}")
    print("─" * width)
    print(RESET, end="")


def info(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}!{RESET} {msg}")


def error(msg: str) -> None:
    print(f"  {RED}✗{RESET} {msg}")


def fatal(msg: str) -> None:
    error(msg)
    sys.exit(1)


def prompt(text: str, default: str | None = None) -> str:
    if default is not None:
        return input(f"{text} [{default}]: ").strip() or default
    return input(f"{text}: ").strip()


def ask_yes_no(text: str, default: str = "y") -> bool:
    suffix = " [Y/n]" if default.lower().startswith("y") else " [y/N]"
    answer = input(f"{text}{suffix}: ").strip().lower()
    if not answer:
        return default.lower().startswith("y")
    return answer.startswith("y")


def open_in_editor(filepath: Path) -> None:
    """Open a file in the user's $EDITOR."""
    editor = os.environ.get("EDITOR", "vi")
    try:
        subprocess.run([editor, str(filepath)], check=True)
    except FileNotFoundError:
        fatal(f"Editor not found: {editor}\nSet $EDITOR to a valid editor.")
    except subprocess.CalledProcessError:
        warn(f"Editor exited with non-zero status.")


# ===========================================================================
# Post file helpers
# ===========================================================================

def find_post_file(slug: str) -> Optional[Path]:
    """Find the source .md file for a post by slug."""
    for src in siteconfig.POSTS_DIR.rglob("*.md"):
        try:
            meta, _ = parse_meta(src.read_text(encoding="utf-8"),
                                 require_author=False)
        except ValueError:
            # Try deriving slug from filename
            from slug import slug_from_filename
            if slug_from_filename(src.stem) == slug:
                return src
            continue
        if meta.slug == slug:
            return src
    return None


def find_page_file(slug: str) -> Optional[Path]:
    """Find the source .md file for a page by slug."""
    for src in siteconfig.PAGES_DIR.glob("*.md"):
        try:
            meta, _ = parse_meta(src.read_text(encoding="utf-8"),
                                 require_date=False, require_author=False)
        except ValueError:
            continue
        if meta.slug == slug:
            return src
    return None


def find_translations(slug: str) -> dict[str, Path]:
    """Find translated versions of a post. Returns {lang: path}."""
    translations = {}
    if not siteconfig.TRANSLATIONS_DIR.exists():
        return translations
    for lang_dir in siteconfig.TRANSLATIONS_DIR.iterdir():
        if lang_dir.is_dir():
            trans_file = lang_dir / f"{slug}.md"
            if trans_file.exists():
                translations[lang_dir.name] = trans_file
    return translations


def update_frontmatter(filepath: Path, updates: dict) -> None:
    """Update specific frontmatter fields in a Markdown file.

    Preserves the body. Updates is a dict of field names to new values.
    Set a value to None to remove the field.
    """
    text = filepath.read_text(encoding="utf-8")
    data, body = split_front_matter(text)
    if data is None:
        data = {}

    for key, value in updates.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value

    # Rebuild the file
    lines = ["---"]
    for key in ("title", "slug", "date", "author", "description", "lang",
                "collection", "tags"):
        if key in data:
            val = data[key]
            if key == "tags" and isinstance(val, list):
                lines.append("tags:")
                for t in val:
                    lines.append(f'  - "{_yaml_quote(str(t))}"')
            elif isinstance(val, date):
                lines.append(f"{key}: {val.isoformat()}")
            elif isinstance(val, str):
                lines.append(f'{key}: "{_yaml_quote(val)}"')
            else:
                lines.append(f"{key}: {val}")
    # Any remaining keys not in the standard order
    for key, val in data.items():
        if key not in ("title", "slug", "date", "author", "description",
                        "lang", "collection", "tags"):
            if isinstance(val, str):
                lines.append(f'{key}: "{_yaml_quote(val)}"')
            else:
                lines.append(f"{key}: {val}")
    lines.append("---")
    lines.append(body)
    filepath.write_text("\n".join(lines), encoding="utf-8")


def _yaml_quote(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def get_collection_for_post(filepath: Path) -> str:
    """Determine the collection name from a post's path."""
    rel = filepath.parent.relative_to(siteconfig.POSTS_DIR)
    if rel.parts:
        return rel.parts[0]
    return "lifelogs"


# ===========================================================================
# 1. Create Post
# ===========================================================================

def do_create_post() -> None:
    header("Create Post")

    title = None
    while not title:
        title = prompt("Title")

    generated = slugify(title)
    slug = prompt("Slug", generated) or generated

    # Check for conflicts
    if find_post_file(slug):
        error(f"A post with slug '{slug}' already exists.")
        return

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
                print(f"  Invalid date: {custom!r}. Use YYYY-MM-DD.")

    description = prompt("Description")

    # Collection selection
    collections = list(siteconfig.COLLECTIONS.keys()) if hasattr(siteconfig, 'COLLECTIONS') else ["lifelogs", "guides"]
    if len(collections) == 1:
        collection = collections[0]
    else:
        print("\nCollection:")
        for i, c in enumerate(collections, 1):
            print(f"    {i}. {c}")
        choice = prompt("Select", "1")
        try:
            collection = collections[int(choice) - 1]
        except (ValueError, IndexError):
            collection = collections[0]

    print()
    print(f"  Title:       {title}")
    print(f"  Slug:        {slug}")
    print(f"  Tags:        {', '.join(tags) or '(none)'}")
    print(f"  Author:      {author}")
    print(f"  Date:        {pub_date.isoformat()}")
    print(f"  Description: {description or '(none)'}")
    print(f"  Collection:  {collection}")
    print()

    if not ask_yes_no("Create this post?", "y"):
        print("  Aborted.")
        return

    try:
        out = create_post(title, slug, pub_date, author, tags, description, collection)
        info(f"Created {out.relative_to(siteconfig.ROOT)}")
    except FileExistsError as e:
        error(str(e))


# ===========================================================================
# 2. Edit Post
# ===========================================================================

def do_edit_post(slug_arg: str | None = None) -> None:
    header("Edit Post")

    posts = collect_all_posts()
    if not posts:
        warn("No posts found.")
        return

    if slug_arg:
        selected = find_post_file(slug_arg)
        if not selected:
            error(f"Post not found: {slug_arg}")
            return
    else:
        # Show list
        print(f"  {'#':<4} {'Date':<12} {'Title':<40} {'Slug'}")
        print("  " + "-" * 90)
        for i, (meta, path) in enumerate(posts, 1):
            print(f"  {i:<4} {meta.date.isoformat():<12} {meta.title[:40]:<40} {meta.slug}")
        print()
        choice = prompt("Select post")
        try:
            idx = int(choice) - 1
            _, selected = posts[idx]
        except (ValueError, IndexError):
            error("Invalid selection.")
            return

    meta, _ = parse_meta(selected.read_text(encoding="utf-8"),
                         require_author=False)
    print(f"\n  Editing: {meta.title} ({meta.slug})")

    while True:
        print(f"\n  {'#':<4} Field")
        print("  " + "-" * 30)
        print(f"  1.  Title        = {meta.title}")
        print(f"  2.  Slug         = {meta.slug}")
        print(f"  3.  Date         = {meta.date.isoformat()}")
        print(f"  4.  Author       = {meta.author}")
        print(f"  5.  Tags         = {', '.join(meta.tags) or '(none)'}")
        print(f"  6.  Description  = {meta.description or '(none)'}")
        print(f"  7.  Edit Markdown content")
        print(f"  8.  Open source file in editor")
        print(f"  9.  Back")
        print()

        choice = prompt("Select field")

        if choice == "1":
            new = prompt("New title", meta.title)
            if new != meta.title:
                update_frontmatter(selected, {"title": new})
                meta.title = new
                info("Title updated.")
        elif choice == "2":
            new = prompt("New slug", meta.slug)
            if new != meta.slug:
                # Check for conflicts
                if find_post_file(new):
                    error(f"A post with slug '{new}' already exists.")
                else:
                    update_frontmatter(selected, {"slug": new})
                    meta.slug = new
                    info("Slug updated.")
        elif choice == "3":
            new = prompt("New date (YYYY-MM-DD)", meta.date.isoformat())
            try:
                d = date.fromisoformat(new)
                update_frontmatter(selected, {"date": d})
                meta.date = d
                info("Date updated.")
            except ValueError:
                error(f"Invalid date: {new}")
        elif choice == "4":
            new = prompt("New author", meta.author)
            if new != meta.author:
                update_frontmatter(selected, {"author": new})
                meta.author = new
                info("Author updated.")
        elif choice == "5":
            current = ", ".join(meta.tags)
            new = prompt("New tags (comma-separated)", current)
            tags = [t.strip() for t in new.split(",") if t.strip()]
            update_frontmatter(selected, {"tags": tags})
            meta.tags = tags
            info("Tags updated.")
        elif choice == "6":
            new = prompt("New description", meta.description or "")
            update_frontmatter(selected, {"description": new or None})
            meta.description = new
            info("Description updated.")
        elif choice == "7":
            # Edit the full body in the editor
            open_in_editor(selected)
            info("Body edited. Re-read to see changes.")
        elif choice == "8":
            open_in_editor(selected)
        elif choice == "9":
            break
        else:
            error("Invalid choice.")


# ===========================================================================
# 3. Delete Post
# ===========================================================================

def do_delete_post(slug_arg: str | None = None) -> None:
    header("Delete Post")

    posts = collect_all_posts()
    if not posts:
        warn("No posts found.")
        return

    if slug_arg:
        selected = find_post_file(slug_arg)
        if not selected:
            error(f"Post not found: {slug_arg}")
            return
    else:
        print(f"  {'#':<4} {'Date':<12} {'Title':<40} {'Slug'}")
        print("  " + "-" * 90)
        for i, (meta, path) in enumerate(posts, 1):
            print(f"  {i:<4} {meta.date.isoformat():<12} {meta.title[:40]:<40} {meta.slug}")
        print()
        choice = prompt("Select post")
        try:
            idx = int(choice) - 1
            _, selected = posts[idx]
        except (ValueError, IndexError):
            error("Invalid selection.")
            return

    meta, _ = parse_meta(selected.read_text(encoding="utf-8"),
                         require_author=False)
    slug = meta.slug

    # Check for translations
    translations = find_translations(slug)
    if translations:
        warn(f"Translations found for '{slug}':")
        for lang, path in translations.items():
            lang_name = siteconfig.LANGS.get(lang, lang)
            print(f"    {lang_name} ({lang}): {path.relative_to(siteconfig.ROOT)}")

    print(f"\n  Delete \"{meta.title}\"?")
    print(f"  Source: {selected.relative_to(siteconfig.ROOT)}")
    print()

    if translations:
        print("  Options:")
        print("    1. Delete source post only")
        print("    2. Delete source post + translations")
        print("    3. Cancel")
        print()
        choice = prompt("Select", "3")
        if choice == "1":
            if not ask_yes_no(f"Delete \"{meta.title}\"?", "n"):
                print("  Cancelled.")
                return
            selected.unlink()
            info(f"Deleted {selected.relative_to(siteconfig.ROOT)}")
        elif choice == "2":
            if not ask_yes_no(f"Delete \"{meta.title}\" + {len(translations)} translation(s)?", "n"):
                print("  Cancelled.")
                return
            selected.unlink()
            info(f"Deleted {selected.relative_to(siteconfig.ROOT)}")
            for lang, path in translations.items():
                path.unlink()
                info(f"Deleted {path.relative_to(siteconfig.ROOT)}")
        else:
            print("  Cancelled.")
    else:
        if not ask_yes_no(f"Delete \"{meta.title}\"?", "n"):
            print("  Cancelled.")
            return
        selected.unlink()
        info(f"Deleted {selected.relative_to(siteconfig.ROOT)}")


# ===========================================================================
# 4. List Posts
# ===========================================================================

def do_list_posts(search: str | None = None) -> None:
    header("Posts")
    posts = collect_all_posts()
    if search:
        q = search.lower()
        posts = [(m, p) for m, p in posts if
                 q in m.title.lower() or q in m.slug.lower() or
                 q in m.description.lower() or
                 any(q in t.lower() for t in m.tags)]
    print(format_posts_table(posts))


# ===========================================================================
# 5. Manage Pages
# ===========================================================================

def do_list_pages() -> None:
    header("Pages")
    pages = collect_all_pages()
    print(format_pages_table(pages))


def do_create_page() -> None:
    header("Create Page")

    title = None
    while not title:
        title = prompt("Title")

    generated = slugify(title)
    slug = prompt("Slug", generated) or generated

    if find_page_file(slug):
        error(f"A page with slug '{slug}' already exists.")
        return

    description = prompt("Description")

    print(f"\n  Title:       {title}")
    print(f"  Slug:        {slug}")
    print(f"  Description: {description or '(none)'}")
    print()

    if not ask_yes_no("Create this page?", "y"):
        print("  Aborted.")
        return

    out = siteconfig.PAGES_DIR / f"{slug}.md"
    fm = [
        "---",
        f'title: "{_yaml_quote(title)}"',
        f'slug: "{_yaml_quote(slug)}"',
    ]
    if description:
        fm.append(f'description: "{_yaml_quote(description)}"')
    fm.extend([
        "---",
        "",
        f"# {title}",
        "",
        "Write your page content here...",
        "",
    ])
    out.write_text("\n".join(fm), encoding="utf-8")
    info(f"Created {out.relative_to(siteconfig.ROOT)}")


def do_edit_page(slug_arg: str | None = None) -> None:
    header("Edit Page")

    pages = collect_all_pages()
    if not pages:
        warn("No pages found.")
        return

    if slug_arg:
        selected = find_page_file(slug_arg)
        if not selected:
            error(f"Page not found: {slug_arg}")
            return
    else:
        print(f"  {'#':<4} {'Title':<40} {'Slug'}")
        print("  " + "-" * 72)
        for i, (meta, path) in enumerate(pages, 1):
            print(f"  {i:<4} {meta.title[:40]:<40} {meta.slug}")
        print()
        choice = prompt("Select page")
        try:
            idx = int(choice) - 1
            _, selected = pages[idx]
        except (ValueError, IndexError):
            error("Invalid selection.")
            return

    meta, _ = parse_meta(selected.read_text(encoding="utf-8"),
                         require_date=False, require_author=False)
    print(f"\n  Editing: {meta.title} ({meta.slug})")

    while True:
        print(f"\n  {'#':<4} Field")
        print("  " + "-" * 30)
        print(f"  1.  Title        = {meta.title}")
        print(f"  2.  Slug         = {meta.slug}")
        print(f"  3.  Description  = {meta.description or '(none)'}")
        print(f"  4.  Edit Markdown content")
        print(f"  5.  Open source file in editor")
        print(f"  6.  Back")
        print()

        choice = prompt("Select field")

        if choice == "1":
            new = prompt("New title", meta.title)
            if new != meta.title:
                update_frontmatter(selected, {"title": new})
                meta.title = new
                info("Title updated.")
        elif choice == "2":
            new = prompt("New slug", meta.slug)
            if new != meta.slug:
                if find_page_file(new):
                    error(f"A page with slug '{new}' already exists.")
                else:
                    update_frontmatter(selected, {"slug": new})
                    meta.slug = new
                    info("Slug updated.")
        elif choice == "3":
            new = prompt("New description", meta.description or "")
            update_frontmatter(selected, {"description": new or None})
            meta.description = new
            info("Description updated.")
        elif choice == "4":
            open_in_editor(selected)
            info("Body edited.")
        elif choice == "5":
            open_in_editor(selected)
        elif choice == "6":
            break
        else:
            error("Invalid choice.")


def do_delete_page(slug_arg: str | None = None) -> None:
    header("Delete Page")

    pages = collect_all_pages()
    if not pages:
        warn("No pages found.")
        return

    if slug_arg:
        selected = find_page_file(slug_arg)
        if not selected:
            error(f"Page not found: {slug_arg}")
            return
    else:
        print(f"  {'#':<4} {'Title':<40} {'Slug'}")
        print("  " + "-" * 72)
        for i, (meta, path) in enumerate(pages, 1):
            print(f"  {i:<4} {meta.title[:40]:<40} {meta.slug}")
        print()
        choice = prompt("Select page")
        try:
            idx = int(choice) - 1
            _, selected = pages[idx]
        except (ValueError, IndexError):
            error("Invalid selection.")
            return

    meta, _ = parse_meta(selected.read_text(encoding="utf-8"),
                         require_date=False, require_author=False)

    print(f"\n  Delete \"{meta.title}\"?")
    print(f"  Source: {selected.relative_to(siteconfig.ROOT)}")
    print()
    if not ask_yes_no("Continue?", "n"):
        print("  Cancelled.")
        return

    selected.unlink()
    info(f"Deleted {selected.relative_to(siteconfig.ROOT)}")


# ===========================================================================
# 6. Manage Translations
# ===========================================================================

def do_translate_menu() -> None:
    while True:
        header("Translation Management")

        has_api_key = bool(os.environ.get("NVIDIA_API_KEY"))
        if not has_api_key:
            warn("NVIDIA_API_KEY not set. Translation requires an API key.")

        print(f"  {'#':<4} Option")
        print("  " + "-" * 30)
        print("  1.  Translate post")
        print("  2.  Translate page")
        print("  3.  View translation status")
        print("  4.  Re-translate (force)")
        print("  5.  Back")
        print()

        choice = prompt("Select")

        if choice == "1":
            _do_translate_content("post")
        elif choice == "2":
            _do_translate_content("page")
        elif choice == "3":
            _do_translation_status()
        elif choice == "4":
            _do_translate_content("post", force=True)
        elif choice == "5":
            break
        else:
            error("Invalid choice.")


def _do_translate_content(kind: str, force: bool = False) -> None:
    if kind == "post":
        items = collect_all_posts()
    else:
        items = collect_all_pages()

    if not items:
        warn(f"No {kind}s found.")
        return

    header(f"Translate {kind.title()}")

    print(f"  {'#':<4} {'Title':<40} {'Slug'}")
    print("  " + "-" * 72)
    for i, (meta, path) in enumerate(items, 1):
        print(f"  {i:<4} {meta.title[:40]:<40} {meta.slug}")
    print()
    choice = prompt("Select")
    try:
        idx = int(choice) - 1
        meta, selected = items[idx]
    except (ValueError, IndexError):
        error("Invalid selection.")
        return

    # Show available languages
    print("\n  Available languages:")
    for code, name in siteconfig.LANGS.items():
        print(f"    {code} — {name}")
    print()

    langs_raw = prompt("Languages to translate (comma-separated)", ",".join(siteconfig.LANGS.keys()))
    target_langs = [l.strip() for l in langs_raw.split(",") if l.strip()]

    if not target_langs:
        error("No languages specified.")
        return

    # Check for existing translations
    if not force:
        for lang in target_langs:
            trans_file = siteconfig.TRANSLATIONS_DIR / lang / f"{meta.slug}.md"
            if trans_file.exists():
                warn(f"Translation already exists: {lang}/{meta.slug}.md")
        if not force and not ask_yes_no("Continue with translation?", "y"):
            print("  Cancelled.")
            return

    print(f"\n  Translating \"{meta.title}\" to: {', '.join(target_langs)}")
    if not has_api_key():
        error("NVIDIA_API_KEY not set. Cannot translate.")
        return

    try:
        import translate
        cache = translate.load_cache()
        stats = {"calls": 0, "cached": 0}

        try:
            import requests as _requests
        except ImportError:
            error("requests library not installed. pip install requests")
            return

        for lang in target_langs:
            print(f"  → {siteconfig.LANGS.get(lang, lang)}...", end=" ", flush=True)
            try:
                translate.translate_file(selected, lang, _requests, cache, stats, force)
                print(f"{GREEN}done{RESET}")
            except Exception as e:
                print(f"{RED}failed{RESET}")
                if DEBUG:
                    print(f"    {e}")

        translate.save_cache(cache)
        info(f"Translation complete. ({stats['calls']} API calls, {stats['cached']} cached)")

    except ImportError:
        error("translate.py module not available.")
    except Exception as e:
        error(f"Translation failed: {e}")
        if DEBUG:
            import traceback
            traceback.print_exc()


def _do_translation_status() -> None:
    header("Translation Status")

    posts = collect_all_posts()
    if not posts:
        warn("No posts found.")
        return

    print(f"  {'#':<4} {'Title':<40} {'Slug'}")
    print("  " + "-" * 72)
    for i, (meta, path) in enumerate(posts, 1):
        print(f"  {i:<4} {meta.title[:40]:<40} {meta.slug}")
    print()
    choice = prompt("Select post")
    try:
        idx = int(choice) - 1
        meta, _ = posts[idx]
    except (ValueError, IndexError):
        error("Invalid selection.")
        return

    print(f"\n  Post: {meta.slug}")
    print(f"  {'Language':<20} {'Status'}")
    print("  " + "-" * 40)

    for code, name in siteconfig.LANGS.items():
        trans_file = siteconfig.TRANSLATIONS_DIR / code / f"{meta.slug}.md"
        if trans_file.exists():
            print(f"  {name:<20} {GREEN}✓ translated{RESET}")
        else:
            print(f"  {name:<20} {DIM}— missing{RESET}")


def has_api_key() -> bool:
    return bool(os.environ.get("NVIDIA_API_KEY"))


# ===========================================================================
# 7. Build Site
# ===========================================================================

def do_build(clean_first: bool = False) -> None:
    header("Building Site")

    try:
        import build
        if clean_first:
            print("  Cleaning dist/...")
            build.clean()
        print("  Building...")
        rc = build.main([])
        if rc == 0:
            info(f"Build complete → {siteconfig.DIST_DIR.relative_to(siteconfig.ROOT)}/")
        else:
            error(f"Build failed (exit code {rc})")
    except Exception as e:
        error(f"Build failed: {e}")
        if DEBUG:
            import traceback
            traceback.print_exc()


# ===========================================================================
# 8. Clean Build
# ===========================================================================

def do_clean() -> None:
    header("Clean Build")

    if not siteconfig.DIST_DIR.exists():
        warn("dist/ does not exist. Nothing to clean.")
        return

    print(f"  This will delete generated files in {siteconfig.DIST_DIR.relative_to(siteconfig.ROOT)}/")
    print()
    if not ask_yes_no("Continue?", "n"):
        print("  Cancelled.")
        return

    import shutil
    shutil.rmtree(siteconfig.DIST_DIR)
    info(f"Cleaned {siteconfig.DIST_DIR.relative_to(siteconfig.ROOT)}/")


# ===========================================================================
# 9. Site Information
# ===========================================================================

def do_info() -> None:
    header("Site Information")

    posts = collect_all_posts()
    pages = collect_all_pages()
    trans_count = 0
    if siteconfig.TRANSLATIONS_DIR.exists():
        for d in siteconfig.TRANSLATIONS_DIR.iterdir():
            if d.is_dir():
                trans_count += 1

    has_api = has_api_key()

    print(f"  Site URL:         {siteconfig.SITE_URL or '(not set)'}")
    print(f"  Site title:       {siteconfig.SITE_TITLE}")
    print(f"  Default author:   {siteconfig.DEFAULT_AUTHOR}")
    print(f"  Default lang:     {siteconfig.DEFAULT_LANG}")
    print()
    print(f"  Posts:            {len(posts)}")
    print(f"  Pages:            {len(pages)}")
    print(f"  Languages:        {len(siteconfig.LANGS)} ({', '.join(siteconfig.LANGS.keys())})")
    print(f"  Translations:     {trans_count} translated files")
    print(f"  API key:          {'set' if has_api else 'not set'}")
    print()
    print(f"  Source:           posts/, pages/, translations/")
    print(f"  Templates:        templates/")
    print(f"  Output:           {siteconfig.DIST_DIR.relative_to(siteconfig.ROOT)}/")
    print(f"  Build system:     Python")
    print(f"  Content:          Markdown")
    print(f"  Frontend:         HTML/CSS")
    print(f"  Hosting:          Static hosting (Cloudflare Pages)")


# ===========================================================================
# Interactive Menu
# ===========================================================================

def interactive_menu() -> None:
    while True:
        print(f"\n{BOLD}Italia Troller Site Toolkit{RESET}")
        print("─" * 30)
        print()
        print(f"  {BOLD}1{RESET}.  Create post")
        print(f"  {BOLD}2{RESET}.  Edit post")
        print(f"  {BOLD}3{RESET}.  Delete post")
        print(f"  {BOLD}4{RESET}.  List posts")
        print(f"  {BOLD}5{RESET}.  Manage pages")
        print(f"  {BOLD}6{RESET}.  Manage translations")
        print(f"  {BOLD}7{RESET}.  Build site")
        print(f"  {BOLD}8{RESET}.  Clean build")
        print(f"  {BOLD}9{RESET}.  Site information")
        print(f"  {BOLD}0{RESET}.  Exit")
        print()

        choice = prompt("Select an option")

        if choice == "1":
            do_create_post()
        elif choice == "2":
            do_edit_post()
        elif choice == "3":
            do_delete_post()
        elif choice == "4":
            do_list_posts()
        elif choice == "5":
            _do_pages_menu()
        elif choice == "6":
            do_translate_menu()
        elif choice == "7":
            do_build()
        elif choice == "8":
            do_clean()
        elif choice == "9":
            do_info()
        elif choice == "0":
            print("\n  Bye!")
            break
        else:
            error("Invalid choice.")


def _do_pages_menu() -> None:
    while True:
        header("Manage Pages")
        print(f"  {'#':<4} Option")
        print("  " + "-" * 30)
        print("  1.  List pages")
        print("  2.  Create page")
        print("  3.  Edit page")
        print("  4.  Delete page")
        print("  5.  Back")
        print()

        choice = prompt("Select")

        if choice == "1":
            do_list_pages()
        elif choice == "2":
            do_create_page()
        elif choice == "3":
            do_edit_page()
        elif choice == "4":
            do_delete_page()
        elif choice == "5":
            break
        else:
            error("Invalid choice.")


# ===========================================================================
# CLI entry point
# ===========================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="site-tk",
        description="Italia Troller Site Toolkit — unified management interface",
    )
    parser.add_argument("--debug", action="store_true",
                        help="enable debug output")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("build", help="build the site")
    sub.add_parser("clean", help="clean build output")
    sub.add_parser("info", help="show site information")

    p_posts = sub.add_parser("posts", help="list posts")
    p_posts.add_argument("search", nargs="?", help="filter posts by keyword")

    sub.add_parser("new-post", help="create a new post")

    p_edit = sub.add_parser("edit-post", help="edit a post")
    p_edit.add_argument("slug", nargs="?", help="post slug")

    p_delete = sub.add_parser("delete-post", help="delete a post")
    p_delete.add_argument("slug", nargs="?", help="post slug")

    sub.add_parser("pages", help="list pages")

    sub.add_parser("new-page", help="create a new page")

    p_ep = sub.add_parser("edit-page", help="edit a page")
    p_ep.add_argument("slug", nargs="?", help="page slug")

    p_dp = sub.add_parser("delete-page", help="delete a page")
    p_dp.add_argument("slug", nargs="?", help="page slug")

    sub.add_parser("translate", help="manage translations")

    return parser


def main() -> int:
    global DEBUG

    parser = build_parser()
    args = parser.parse_args()

    DEBUG = args.debug

    if args.command is None:
        interactive_menu()
        return 0

    cmd = args.command

    if cmd == "build":
        do_build()
    elif cmd == "clean":
        do_clean()
    elif cmd == "info":
        do_info()
    elif cmd == "posts":
        do_list_posts(args.search if hasattr(args, "search") else None)
    elif cmd == "new-post":
        do_create_post()
    elif cmd == "edit-post":
        do_edit_post(args.slug if hasattr(args, "slug") else None)
    elif cmd == "delete-post":
        do_delete_post(args.slug if hasattr(args, "slug") else None)
    elif cmd == "pages":
        do_list_pages()
    elif cmd == "new-page":
        do_create_page()
    elif cmd == "edit-page":
        do_edit_page(args.slug if hasattr(args, "slug") else None)
    elif cmd == "delete-page":
        do_delete_page(args.slug if hasattr(args, "slug") else None)
    elif cmd == "translate":
        do_translate_menu()
    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n  Interrupted.")
        sys.exit(130)
    except Exception as e:
        if DEBUG:
            import traceback
            traceback.print_exc()
        else:
            fatal(f"Unexpected error: {e}")
