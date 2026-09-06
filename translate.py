#!/usr/bin/env python3
"""Translate Markdown source files to target languages using NVIDIA Riva.

This system translates the WHOLE Markdown document (never generated HTML),
stores the translated Markdown under translations/<lang>/<slug>.md, and caches
responses so unchanged content is not re-sent to the API.

It is fully modular: build.py only calls it when translation is enabled, and
local rendering never requires it.

Usage:
    export NVIDIA_API_KEY="nvapi-..."
    python3 translate.py                 # translate all configured languages
    python3 translate.py --langs vi,fr   # specific languages
    python3 translate.py --force         # re-translate even if cached
    python3 translate.py --dry-run       # show what would be translated
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import siteconfig
from frontmatter import parse_meta, split_front_matter

NIM_ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
NIM_MODEL = "nvidia/riva-translate-4b-instruct-v2"

API_KEY = os.environ.get("NVIDIA_API_KEY", "").strip()

CACHE_VERSION = 1
MAX_TOKENS = 8192
REQUEST_TIMEOUT = 180
MAX_RETRIES = 4


def _import_requests():
    try:
        import requests
    except ImportError:
        print("requests is required for translation.", file=sys.stderr)
        print("Install it with: python3 -m pip install requests", file=sys.stderr)
        raise
    return requests


# ---------------------------------------------------------------------------
# Cache (keys on content hash + target language, survives between runs)
# ---------------------------------------------------------------------------

def cache_key(source_text: str, target_lang: str) -> str:
    raw = json.dumps({
        "v": CACHE_VERSION,
        "model": NIM_MODEL,
        "text": source_text,
        "target": target_lang,
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_cache() -> dict:
    if not siteconfig.TRANSLATION_CACHE.exists():
        return {"version": CACHE_VERSION, "entries": {}}
    try:
        data = json.loads(siteconfig.TRANSLATION_CACHE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": CACHE_VERSION, "entries": {}}
    if data.get("version") != CACHE_VERSION:
        return {"version": CACHE_VERSION, "entries": {}}
    data.setdefault("entries", {})
    return data


def save_cache(cache: dict) -> None:
    content = json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True)
    siteconfig.TRANSLATION_CACHE.parent.mkdir(parents=True, exist_ok=True)
    siteconfig.TRANSLATION_CACHE.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Markdown-aware protection (don't translate code / URLs / frontmatter keys)
# ---------------------------------------------------------------------------

# Protect non-translatable regions. Order matters (longest/most specific first).
_BLOCK_PATTERNS = [
    re.compile(r"````[\s\S]*?````"),
    re.compile(r"```[\s\S]*?```"),
    re.compile(r"<!--[\s\S]*?-->"),
]

# YAML front matter line:  key: "value"   or   key: value
_FM_KEY_RE = re.compile(r'^\s*([a-zA-Z0-9_-]+):\s*"?([^"\n]*)"?$')

_INLINE_PATTERNS = [
    re.compile(r"`[^`\n]+`"),                      # inline code
    re.compile(r"!\[[^\]]*\]\([^)]+\)"),           # images
    re.compile(r"\[[^\]]+\]\([^)]+\)"),            # links (keep URL, translate text)
    re.compile(r"<(https?://[^>]+)>"),             # autolinks
]


class _Segment:
    __slots__ = ("text", "protected", "link_text", "fm_line")

    def __init__(self, text: str, protected: bool = False, link_text: bool = False,
                 fm_line: bool = False):
        self.text = text
        self.protected = protected
        self.link_text = link_text
        self.fm_line = fm_line


def _segment_markdown(md: str) -> List[_Segment]:
    """Split the Markdown into protected and translatable segments."""
    segments: List[_Segment] = []

    # ---- Front matter: protect everything except title/description values ----
    fm_body = ""
    rest = md
    if md.startswith("---"):
        end = md.find("\n---", 3)
        if end != -1:
            fm_body = md[3:end]
            rest = md[end + len("\n---"):]
    # first newline after the opening '---' boundary
    if fm_body.startswith("\n"):
        fm_body = fm_body[1:]
    # strip the single leading blank line after the closing '---'
    rest = rest.lstrip("\n")

    if fm_body:
        segments.append(_Segment("---\n", protected=True, fm_line=True))
        for line in fm_body.split("\n"):
            key_match = _FM_KEY_RE.match(line)
            if key_match:
                key = key_match.group(1)
                if key in ("title", "description"):
                    # Reconstruct the value from the regex capture.
                    val = key_match.group(2)
                    if _is_translatable(val):
                        segments.append(_Segment(f'{key}: ', protected=True, fm_line=True))
                        segments.append(_Segment(val, fm_line=True))
                        segments.append(_Segment('"\n', protected=True, fm_line=True))
                        continue
                segments.append(_Segment(line + "\n", protected=True, fm_line=True))
            else:
                segments.append(_Segment(line + "\n", protected=True, fm_line=True))
        # Re-add the closing '---' line
        segments.append(_Segment("---\n", protected=True, fm_line=True))

    # ---- Rest of the document: block + inline protections ----
    body = rest
    protected_ranges: List[tuple] = []

    # Block-level protection
    for pat in _BLOCK_PATTERNS:
        for m in pat.finditer(body):
            start, end = m.start(), m.end()
            if not any(start < pe and end > ps for ps, pe in protected_ranges):
                protected_ranges.append((start, end, m.group(0)))

    # Sort and walk to make unprotected (prose) segments + protected segments
    protected_ranges.sort(key=lambda x: x[0])

    pos = 0
    for start, end, content in protected_ranges:
        if start > pos:
            segments.append(_Segment(body[pos:start]))
        segments.append(_Segment(content, protected=True))
        pos = end
    if pos < len(body):
        segments.append(_Segment(body[pos:]))

    # Split links further: keep surrounding braces protected, translate text.
    final: List[_Segment] = []
    for seg in segments:
        if seg.protected:
            final.append(seg)
            continue

        chunks = []
        last = 0
        for m in _INLINE_PATTERNS[2].finditer(seg.text):  # links only
            # Only handle links that are not part of an image (handled above)
            if m.start() > last:
                chunks.append(_Segment(seg.text[last:m.start()]))
            link = m.group(0)
            # link like [text](url)
            inner = link[1:link.find("]")]
            rest = link[link.find("]"):]
            chunks.append(_Segment("[", protected=True))
            chunks.append(_Segment(inner, link_text=True))
            chunks.append(_Segment(rest, protected=True))
            last = m.end()
        if last < len(seg.text):
            chunks.append(_Segment(seg.text[last:]))
        # Re-protect any inline code / images / autolinks inside prose chunks
        for chunk in chunks:
            if chunk.protected:
                final.append(chunk)
                continue
            _split_inline(chunk, final)
    return final


def _split_inline(chunk: _Segment, out: List[_Segment]) -> None:
    """Further protect inline code / images / autolinks inside a prose chunk."""
    patterns = [_INLINE_PATTERNS[0], _INLINE_PATTERNS[1], _INLINE_PATTERNS[3]]
    last = 0
    parts: List[tuple] = []
    # collect all inline matches
    matches = []
    for pat in patterns:
        for m in pat.finditer(chunk.text):
            matches.append(m)
    matches.sort(key=lambda m: m.start())

    for m in matches:
        if m.start() < last:
            continue
        if m.start() > last:
            out.append(_Segment(chunk.text[last:m.start()]))
        out.append(_Segment(m.group(0), protected=True))
        last = m.end()
    if last < len(chunk.text):
        out.append(_Segment(chunk.text[last:]))


def _is_translatable(text: str) -> bool:
    norm = re.sub(r"\s+", " ", text).strip()
    return len(norm) >= 2


# ---------------------------------------------------------------------------
# NVIDIA Riva
# ---------------------------------------------------------------------------

def _nim_translate(text: str, target_lang: str, requests) -> str:
    lang_full = siteconfig.LANGS.get(target_lang, target_lang)
    system = (
        f"You are translating a personal tech blog to {lang_full}.\n"
        "Rules:\n"
        "1. Preserve ALL Markdown syntax exactly (headings, lists, links, code)\n"
        "2. Do NOT translate proper nouns, brand names, or code identifiers\n"
        "3. Keep URLs, code, and HTML tags unchanged\n"
        "4. Use natural {lang_full} style; keep the casual tone\n"
    )
    payload = {
        "model": NIM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
        "max_tokens": MAX_TOKENS,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    last_error = "unknown"
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.post(NIM_ENDPOINT, headers=headers, json=payload,
                                 timeout=REQUEST_TIMEOUT)
            if resp.ok:
                data = resp.json()
                translated = data["choices"][0]["message"]["content"]
                if isinstance(translated, str) and translated.strip():
                    return translated.strip()
                raise RuntimeError("Empty translation returned")
            if resp.status_code in {400, 401, 403, 404, 422}:
                raise RuntimeError(f"NVIDIA HTTP {resp.status_code}: {resp.text[:300]}")
            last_error = f"HTTP {resp.status_code}"
        except requests.exceptions.RequestException as e:
            last_error = str(e)
        if attempt < MAX_RETRIES:
            delay = 2 ** attempt
            print(f"      retry {attempt + 1}/{MAX_RETRIES} in {delay}s ({last_error})")
            time.sleep(delay)
        else:
            break
    raise RuntimeError(f"NVIDIA failed: {last_error}")


def translate_markdown(md: str, target_lang: str, requests, cache: dict,
                      stats: dict) -> str:
    """Translate an entire Markdown document, protecting code/URLs, with cache."""
    segments = _segment_markdown(md)

    # Collect unique translatable texts
    unique: Dict[str, str] = {}
    for seg in segments:
        if seg.protected or not _is_translatable(seg.text):
            continue
        norm = re.sub(r"\s+", " ", seg.text).strip()
        if norm not in unique:
            unique[norm] = seg.text

    # Cache lookups; translate misses by whole-document prefix to reduce calls
    translations: Dict[str, str] = {}
    for norm, original in unique.items():
        key = cache_key(original, target_lang)
        cached = cache["entries"].get(key)
        if cached:
            stats["cache_hits"] += 1
            translations[norm] = cached["translation"]
        else:
            stats["cache_misses"] += 1
            stats["api_calls"] += 1
            translated = _nim_translate(original, target_lang, requests)
            translations[norm] = translated
            cache["entries"][key] = {
                "source": original, "target": target_lang,
                "translation": translated,
                "ts": int(time.time()),
            }

    # Reassemble
    out = []
    for seg in segments:
        if seg.protected:
            out.append(seg.text)
            continue
        text = seg.text
        norm = re.sub(r"\s+", " ", text).strip()
        if norm in translations:
            out.append(translations[norm])
        else:
            out.append(text)
    return "".join(out)


# ---------------------------------------------------------------------------
# File-level orchestration
# ---------------------------------------------------------------------------

def translate_file(src: Path, target_lang: str, requests, cache: dict,
                   stats: dict, force: bool) -> Optional[Path]:
    """Translate a post/page into translations/<lang>/<slug>.md."""
    text = src.read_text(encoding="utf-8")

    # Use content hash to skip unchanged files unless --force
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    key = f"{target_lang}:{src.name}"

    meta = None
    try:
        meta, _ = parse_meta(text, require_date=False, require_author=False)
    except ValueError:
        pass
    slug = meta.slug if meta else (src.stem.replace(" ", "-"))

    out = siteconfig.TRANSLATIONS_DIR / target_lang / f"{slug}.md"

    import json as _json
    state_file = siteconfig.ROOT / ".translation-state.json"
    state = {}
    if state_file.exists():
        try:
            state = _json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            state = {}

    if not force and state.get(key) == digest and out.exists():
        stats["files_skipped"] += 1
        return out

    translated = translate_markdown(text, target_lang, requests, cache, stats)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(translated, encoding="utf-8")
    state[key] = digest
    state_file.write_text(_json.dumps(state, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    stats["files_translated"] += 1
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Translate Markdown via NVIDIA Riva")
    p.add_argument("--langs", default=",".join(siteconfig.LANGS),
                   help="Comma-separated languages (default: all configured)")
    p.add_argument("--inputs", nargs="*", default=None,
                   help="Specific files to translate (default: all posts+pages)")
    p.add_argument("--force", action="store_true", help="Re-translate cached files")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would be translated without calling the API")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if args.dry_run:
        print("DRY RUN: no API calls will be made.")
    elif not API_KEY:
        print("ERROR: NVIDIA_API_KEY is not set.", file=sys.stderr)
        print('Run: export NVIDIA_API_KEY="nvapi-..."', file=sys.stderr)
        return 1

    requests = _import_requests()
    cache = load_cache()
    stats = {"cache_hits": 0, "cache_misses": 0, "api_calls": 0,
             "files_skipped": 0, "files_translated": 0}

    langs = [c for c in args.langs.split(",") if c]
    for lang in langs:
        if lang not in siteconfig.LANGS:
            print(f"ERROR: unknown language {lang!r}", file=sys.stderr)
            return 1

    if args.inputs:
        sources = [Path(p) for p in args.inputs]
    else:
        sources = sorted(siteconfig.POSTS_DIR.glob("*.md")) + \
                  sorted(siteconfig.PAGES_DIR.glob("*.md"))

    for lang in langs:
        print(f"[{lang}] {siteconfig.LANGS[lang]}")
        for src in sources:
            if not src.exists():
                continue
            if args.dry_run:
                print(f"  {src.name}: would translate")
                continue
            try:
                out = translate_file(src, lang, requests, cache, stats, args.force)
                print(f"  {src.name} -> {out}")
            except Exception as e:
                print(f"  ERROR {src.name}: {e}", file=sys.stderr)
                if os.environ.get("TRANSLATE_STRICT"):
                    return 1

    if not args.dry_run:
        save_cache(cache)
    print()
    print(f"API calls: {stats['api_calls']} | cache hits: {stats['cache_hits']} "
          f"| misses: {stats['cache_misses']} | files translated: "
          f"{stats['files_translated']} | skipped: {stats['files_skipped']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
