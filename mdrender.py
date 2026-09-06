"""Markdown -> HTML rendering with build-time Pygments highlighting.

Output uses highlight.js-style token classes (hljs-*) so the existing
Everforest syntax-highlighting CSS in global-style.css applies without any
client-side JavaScript.
"""

from __future__ import annotations

import re

import markdown
from pygments import highlight
from pygments.formatter import Formatter
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.util import ClassNotFound

# Map Pygments token types (lowercase dotted paths) to hljs-* class names.
# Deeper/more specific paths are matched first.
_PYGMENTS_TO_HLJS: dict[str, str] = {
    "comment": "hljs-comment",
    "comment.shebang": "hljs-meta",
    "keyword": "hljs-keyword",
    "keyword.constant": "hljs-keyword",
    "keyword.namespace": "hljs-keyword",
    "name.builtin": "hljs-built_in",
    "name.class": "hljs-class",
    "name.function": "hljs-function",
    "name.tag": "hljs-name",
    "name.attribute": "hljs-attr",
    "literal.string": "hljs-string",
    "literal.string.doc": "hljs-doctag",
    "literal.string.regex": "hljs-regexp",
    "literal.number": "hljs-number",
    "generic.deleted": "hljs-deletion",
    "generic.inserted": "hljs-addition",
    "generic.emph": "hljs-emphasis",
    "generic.strong": "hljs-strong",
    "name.variable": "hljs-variable",
    "name.title": "hljs-title",
    "name.constant": "hljs-title",
}


class HljsFormatter(Formatter):
    """Inline formatter emitting <span class="hljs-..."> per token."""

    def _hljs_class(self, ttype) -> str:
        parts = [p for p in str(ttype).lower().split(".") if p != "token"] or [""]
        for i in range(len(parts), 0, -1):
            key = ".".join(parts[:i])
            if key in _PYGMENTS_TO_HLJS:
                return _PYGMENTS_TO_HLJS[key]
        return ""

    def _escape(self, value: str) -> str:
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def format(self, tokensource, outfile):
        for ttype, value in tokensource:
            if not value:
                continue
            cls = self._hljs_class(ttype) if ttype != 0 else ""
            value = self._escape(value)
            if cls:
                outfile.write(f'<span class="{cls}">{value}</span>')
            else:
                outfile.write(value)


_hljs_formatter = HljsFormatter()


def _escape_block(code: str) -> str:
    return code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def highlight_code(code: str, lang: str | None) -> tuple[str, str | None]:
    """Return (inner_hljs_html_or_escaped, resolved_language)."""
    lexer = None
    resolved = lang
    try:
        if lang:
            try:
                lexer = get_lexer_by_name(lang, stripnl=False)
            except ClassNotFound:
                lexer = None
        if lexer is None:
            try:
                lexer = guess_lexer(code)
                resolved = lexer.name.lower().split()[0]
            except Exception:
                lexer = None
        if lexer is not None:
            return highlight(code, lexer, _hljs_formatter), resolved
    except Exception:
        pass
    return _escape_block(code), resolved


# Matches a fenced <pre><code class="language-...">...</code></pre> emitted by
# the standard fenced_code extension (no codehilite). The inner content is the
# escaped code; we must unescape it before re-highlighting.
_PRE_CODE_RE = re.compile(
    r'<pre><code(?P<attrs>\s[^>]*?)?>(?P<inner>.*?)</code></pre>',
    re.DOTALL,
)

_LANG_RE = re.compile(r'class="[^"]*language-([A-Za-z0-9_+-]+)')


def _unescape(html: str) -> str:
    return (
        html.replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&gt;", ">")
        .replace("&lt;", "<")
        .replace("&amp;", "&")
    )


def _post_highlight(html: str) -> str:
    def repl(match: re.Match) -> str:
        attrs = match.group("attrs") or ""
        inner = match.group("inner")
        if "<span" in inner or "<" not in inner:
            # Either already highlighted or a plain code element; re-highlight
            # from the raw (escaped) text.
            code = _unescape(inner)
            lang = None
            m = _LANG_RE.search(attrs)
            if m:
                lang = m.group(1)
            highlighted, resolved = highlight_code(code, lang)
            lang_attr = f'class="language-{resolved}"' if resolved else ""
            return f'<pre><code {lang_attr}>{highlighted}</code></pre>'
        return match.group(0)

    return _PRE_CODE_RE.sub(repl, html)


def render_markdown(text: str) -> str:
    """Convert Markdown to HTML with build-time hljs syntax highlighting."""
    md = markdown.Markdown(
        extensions=[
            "fenced_code",
            "tables",
            "attr_list",
            "def_list",
            "footnotes",
            "toc",
            "admonition",
            "md_in_html",
        ],
        extension_configs={
            "toc": {"permalink": False},
        },
        output_format="html5",
    )
    html = md.convert(text).strip()
    return _post_highlight(html)
