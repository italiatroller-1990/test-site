#!/usr/bin/env python3
"""Inject global styles/scripts into the <head> of every HTML page."""

import re
import sys
from pathlib import Path

SITE_DIR = Path(__file__).resolve().parent

HEAD_JS = '<script src="https://ajax.googleapis.com/ajax/libs/jquery/3.5.1/jquery.min.js"></script>'
HLJS = '<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>'
GLOBAL_CSS = '<link rel="stylesheet" href="global-style.css">'

SNIPPETS = (HEAD_JS, HLJS, GLOBAL_CSS)
BODY_INIT = [
    '$.get("navbar.html", function(data) { $("#navbar").replaceWith(data); });',
    'hljs.highlightAll();',
]

FRAGMENT_NAMES = {"navbar.html"}

# Fragments are partial HTML loaded into pages, not standalone documents.
def is_fragment(path: Path) -> bool:
    return path.name in FRAGMENT_NAMES or "<!DOCTYPE html>" not in path.read_text()


def inject_head(head: str) -> str:
    for snippet in SNIPPETS:
        if snippet not in head:
            head += f"\n        {snippet}"
    return head


def inject_body(body_end: str) -> str:
    script = "\n".join(f"            {line}" for line in BODY_INIT)
    return f"        <script>\n{script}\n        </script>\n    </body>"


def process(path: Path) -> bool:
    if is_fragment(path):
        print(f"SKIP {path.name}: fragment, not a standalone page")
        return False

    content = path.read_text()

    head_match = re.search(r"<head>.*?</head>", content, re.DOTALL)
    if not head_match:
        print(f"SKIP {path.name}: no <head> found")
        return False

    new_head = inject_head(head_match.group(0))
    content = content.replace(head_match.group(0), new_head)

    body_match = re.search(r"</script>\s*</body>|\s*</body>", content)
    if body_match and "highlightAll" not in content:
        content = content.replace(body_match.group(0), inject_body(body_match.group(0)))

    if "global-style.css" in content and "highlightAll" in content:
        print(f"OK   {path.name}: already complete")
        return False

    path.write_text(content)
    print(f"DONE {path.name}: injected")
    return True


def main() -> int:
    pages = [Path(p) for p in sys.argv[1:]] if len(sys.argv) > 1 else sorted(SITE_DIR.glob("*.html"))
    changed = any(process(p) for p in pages)
    return 0 if changed else 1


if __name__ == "__main__":
    sys.exit(main())
