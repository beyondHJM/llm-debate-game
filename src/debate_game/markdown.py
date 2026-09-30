from __future__ import annotations

import html
import re
from collections.abc import Sequence
from typing import Any

from latex2mathml.converter import convert
from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML
from markdown_it.rules_inline import StateInline
from markdown_it.token import Token

_BARE_TEX_COMMAND = re.compile(
    r"\\[A-Za-z]+(?:\[[^\]\n]*\])?"
    r"(?:\{(?:[^{}\n]|\{[^{}\n]*\})*\})*"
    r"[0-9A-Za-z.+\-*/=^_()]*"
)


def create_markdown_renderer() -> MarkdownIt:
    renderer = MarkdownIt("commonmark", {"html": False, "linkify": False})
    renderer.inline.ruler.before("escape", "tex_math", _parse_math)
    renderer.add_render_rule("tex_math", _render_math)
    return renderer


def _parse_math(state: StateInline, silent: bool) -> bool:
    source = state.src
    start = state.pos
    located = _find_delimited_math(source, start)
    if located is None:
        bare = _BARE_TEX_COMMAND.match(source, start)
        if bare is None:
            return False
        content = bare.group(0)
        end = bare.end()
        display = False
        markup = "bare-tex"
    else:
        content, end, display, markup = located

    if not content.strip():
        return False
    if not silent:
        token = state.push("tex_math", "math", 0)
        token.content = content
        token.markup = markup
        token.info = "block" if display else "inline"
    state.pos = end
    return True


def _find_delimited_math(
    source: str,
    start: int,
) -> tuple[str, int, bool, str] | None:
    delimiters = (
        ("$$", "$$", True),
        (r"\[", r"\]", True),
        (r"\(", r"\)", False),
        ("$", "$", False),
    )
    for opening, closing, display in delimiters:
        if not source.startswith(opening, start):
            continue
        content_start = start + len(opening)
        closing_at = _find_unescaped(source, closing, content_start)
        if closing_at < 0:
            return None
        return (
            source[content_start:closing_at],
            closing_at + len(closing),
            display,
            opening,
        )
    return None


def _find_unescaped(source: str, closing: str, start: int) -> int:
    position = start
    while True:
        position = source.find(closing, position)
        if position < 0:
            return -1
        backslashes = 0
        cursor = position - 1
        while cursor >= 0 and source[cursor] == "\\":
            backslashes += 1
            cursor -= 1
        if backslashes % 2 == 0:
            return position
        position += len(closing)


def _render_math(
    renderer: RendererHTML,
    tokens: Sequence[Token],
    index: int,
    options: dict[str, Any],
    env: dict[str, Any],
) -> str:
    del renderer, options, env
    token = tokens[index]
    display = token.info == "block"
    try:
        mathml = convert(token.content, display="block" if display else "inline")
    except Exception:
        escaped = html.escape(token.content)
        return f'<code class="math-error">{escaped}</code>'
    if display:
        return f'<div class="math-block">{mathml}</div>'
    return f'<span class="math-inline">{mathml}</span>'
