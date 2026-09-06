"""Shared page/post rendering logic used by render-md.py and build.py."""

from __future__ import annotations

import html
from datetime import date
from pathlib import Path

import siteconfig
from frontmatter import PostMeta
from mdrender import render_markdown

# Template path placeholders filled by str.format. The template uses {name}
# style; css_path is relative to the output file's directory.
_PAGE_TPL = (siteconfig.TEMPLATES_DIR / "page.html").read_text(encoding="utf-8")
_POST_TPL = (siteconfig.TEMPLATES_DIR / "post.html").read_text(encoding="utf-8")


def tags_html(meta: PostMeta) -> str:
    if not meta.tags:
        return ""
    tags = "".join(
        f'<a class="tag" href="/{tag_slug(t)}/">{html.escape(t)}</a>'
        for t in meta.tags
    )
    return f'<span class="tags">&middot; {tags}</span>'


def tag_slug(tag: str) -> str:
    from slug import slugify

    return slugify(tag)


def _description_html(meta: PostMeta) -> str:
    if not meta.description:
        return ""
    return f'<p class="post-excerpt">{html.escape(meta.description)}</p>'


def render_post(meta: PostMeta, body_md: str, css_path: str = "") -> str:
    content = render_markdown(body_md)
    desc = html.escape(meta.description or "")
    date_display = meta.date.strftime("%B %d, %Y")

    return _POST_TPL.format(
        lang=meta.lang,
        title=html.escape(meta.title),
        description=desc,
        css_path=css_path,
        content=content,
        date_iso=meta.date.isoformat(),
        date_display=date_display,
        author=html.escape(meta.author),
        tags_html=tags_html(meta),
        description_html=_description_html(meta),
    )


def render_page(title: str, body_md: str, *, lang: str = "en",
                description: str = "", css_path: str = "") -> str:
    content = render_markdown(body_md)
    return _PAGE_TPL.format(
        lang=lang,
        title=html.escape(title),
        description=html.escape(description or ""),
        css_path=css_path,
        content=content,
    )


def render_post_listing(posts, prefix: str = "../") -> str:
    """Build a <ul> linking to each post's clean-URL directory.

    ``posts`` is a list of PostMeta sorted newest-first. ``prefix`` is the
    relative path from the listing page's directory to site root
    (e.g. '../' for pages at dist/<page>/index.html).
    """
    items = []
    for meta in posts:
        when = meta.date.strftime("%B %d, %Y")
        tags = "".join(
            f'<span class="tag">{html.escape(t)}</span>' for t in meta.tags
        )
        items.append(
            f'<li><a href="{prefix}{meta.slug}/">{html.escape(meta.title)}</a>'
            f' <time datetime="{meta.date.isoformat()}">{when}</time>'
            f'{(" " + tags) if tags else ""}</li>'
        )
    return '<ul class="post-list">\n' + "\n".join(items) + "\n</ul>"


def css_path_for(out_path: Path) -> str:
    """Compute the relative 'css_path' prefix from an output dir to site root.

    Example: dist/about/index.html -> '../../'
    """
    rel = out_path.parent.relative_to(siteconfig.DIST_DIR)
    depth = len(rel.parts)
    return "../" * depth


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
