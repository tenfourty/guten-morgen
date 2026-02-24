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


def markdown_to_html(md: str | None) -> str | None:
    """Convert markdown to HTML."""
    if md is None:
        return None
    if not md:
        return ""
    import markdown as md_lib  # type: ignore[import-untyped]

    result: str = md_lib.markdown(md)
    return result
