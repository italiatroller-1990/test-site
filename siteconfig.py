"""Site-wide configuration for the static site generator."""

from __future__ import annotations

from pathlib import Path

# Project root (directory containing this file)
ROOT = Path(__file__).resolve().parent

# Directories
POSTS_DIR = ROOT / "posts"
PAGES_DIR = ROOT / "pages"
TEMPLATES_DIR = ROOT / "templates"
TRANSLATIONS_DIR = ROOT / "translations"
DIST_DIR = ROOT / "dist"

# Site metadata
SITE_TITLE = "Italia Troller's site"
SITE_URL = ""  # e.g. "https://example.com" (leave empty for relative links)
DEFAULT_AUTHOR = "Italia Troller"
DEFAULT_LANG = "en"

# Ordered navigation items shown in the navbar: (label, href)
# hrefs are relative so the fragment works from any depth and via file://.
NAV_ITEMS = [
    ("Welcome!", "index.html"),
    ("About myself!", "about/"),
    ("Lifelogs", "lifelog/"),
    ("Guides", "guides/"),
]

# Languages the site can be translated into.
# Map language code -> human-readable name.
LANGS = {
    "vi": "Vietnamese",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "ja": "Japanese",
}

# Translation cache location (kept out of dist/)
TRANSLATION_CACHE = ROOT / ".translation-cache.json"

# Copy these static files/assets into dist/ during build.
# Patterns are relative to ROOT.
STATIC_ASSETS = [
    "navbar.html",
    "navbar.css",
    "style.css",
    "global-style.css",
    "everforest.css",
    "fonts.css",
    "favicon.png",
    "jquery.min.js",
    "fonts",  # directory
]
