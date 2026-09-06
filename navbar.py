"""Renders the reusable navbar HTML fragment loaded into every page.

The fragment is a plain <nav> with no <!DOCTYPE>/<html>/<head>/<body>, because
it is inserted into an existing document at runtime.
"""

from __future__ import annotations

import html

import siteconfig


def render_navbar(prefix: str = "") -> str:
    logo = (f'<img src="{prefix}favicon.png" alt="" '
            'width="42" height="42" class="nav-logo">')

    links = "".join(
        f'<a href="{prefix}{html.escape(href)}">{html.escape(label)}</a>'
        for label, href in siteconfig.NAV_ITEMS
    )

    title = html.escape(siteconfig.SITE_TITLE)

    return (
        f'<link rel="stylesheet" href="{prefix}navbar.css">\n'
        "<nav>\n"
        f"    {logo}\n"
        f'    <a href="{prefix}index.html" class="main">{title}</a>\n'
        f'    <div class="nav-links">\n{links}\n    </div>\n'
        "</nav>\n"
    )


def write_navbar(output_path=siteconfig.ROOT / "navbar.html", prefix: str = "") -> None:
    output_path.write_text(render_navbar(prefix), encoding="utf-8")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    write_navbar()
