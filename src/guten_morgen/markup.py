"""Transparent markdown <-> HTML conversion for task descriptions.

The Morgen API stores descriptions as HTML but agents work with markdown.
This module converts transparently in both directions.
"""

from __future__ import annotations

import re


def _is_html(text: str) -> bool:
    """Check if text contains HTML tags."""
    return bool(re.search(r"<[a-zA-Z][^>]*>", text))


def html_to_markdown(html: str | None) -> str | None:
    """Convert HTML to markdown. Plain text passes through unchanged."""
    if html is None:
        return None
    if not html:
        return ""
    if not _is_html(html):
        return html
    import markdownify

    result: str = markdownify.markdownify(html, strip=["img"])
    return result.strip()


def _wrap_bare_li(html: str) -> str:
    """Wrap bare <li> content in <p> tags for Morgen's TipTap editor.

    TipTap expects ``<li><p>text</p></li>``; bare ``<li>text</li>``
    renders with empty bullet artifacts.
    """
    return re.sub(
        r"<li>(?!<p>)(.*?)</li>",
        r"<li><p>\1</p></li>",
        html,
        flags=re.DOTALL,
    )


def markdown_to_html(md: str | None) -> str | None:
    """Convert markdown to HTML."""
    if md is None:
        return None
    if not md:
        return ""
    import markdown as md_lib  # type: ignore[import-untyped]

    result: str = md_lib.markdown(md)
    return _wrap_bare_li(result)
