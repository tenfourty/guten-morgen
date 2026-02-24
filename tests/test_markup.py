"""Tests for markup conversion."""

from __future__ import annotations

from guten_morgen.markup import html_to_markdown, markdown_to_html


class TestHtmlToMarkdown:
    def test_converts_bullet_list(self) -> None:
        html = "<ul><li><p>bullet one</p></li><li><p>bullet two</p></li></ul>"
        result = html_to_markdown(html)
        assert "bullet one" in result
        assert "bullet two" in result
        assert "* " in result or "- " in result

    def test_converts_bold(self) -> None:
        html = "<p><strong>bold text</strong></p>"
        result = html_to_markdown(html)
        assert "**bold text**" in result

    def test_converts_paragraph(self) -> None:
        html = "<p>normal text</p>"
        result = html_to_markdown(html)
        assert "normal text" in result
        assert "<p>" not in result

    def test_plain_text_passthrough(self) -> None:
        text = "Just a plain note with no formatting"
        result = html_to_markdown(text)
        assert result == text

    def test_none_returns_none(self) -> None:
        result = html_to_markdown(None)
        assert result is None

    def test_empty_string(self) -> None:
        result = html_to_markdown("")
        assert result == ""


class TestMarkdownToHtml:
    def test_converts_bullet_list(self) -> None:
        md = "- item one\n- item two"
        result = markdown_to_html(md)
        assert "<li>" in result
        assert "item one" in result

    def test_wraps_li_content_in_p_for_tiptap(self) -> None:
        md = "- item one\n- item two"
        result = markdown_to_html(md)
        assert "<li><p>item one</p></li>" in result
        assert "<li><p>item two</p></li>" in result

    def test_converts_bold(self) -> None:
        md = "**bold text**"
        result = markdown_to_html(md)
        assert "<strong>bold text</strong>" in result

    def test_plain_text_wraps_in_p(self) -> None:
        md = "Just plain text"
        result = markdown_to_html(md)
        assert "Just plain text" in result

    def test_none_returns_none(self) -> None:
        result = markdown_to_html(None)
        assert result is None

    def test_empty_string(self) -> None:
        result = markdown_to_html("")
        assert result == ""
