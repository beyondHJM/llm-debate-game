from debate_game.markdown import create_markdown_renderer


def test_bare_overline_command_is_rendered_as_mathml() -> None:
    rendered = create_markdown_renderer().render(r"0.\overline{9}")

    assert "0." in rendered
    assert "<math" in rendered
    assert "<mover>" in rendered
    assert "<mn>9</mn>" in rendered


def test_delimited_inline_and_block_math_are_rendered() -> None:
    renderer = create_markdown_renderer()

    inline = renderer.render(r"The value is $\frac{1}{2}$.")
    block = renderer.render("$$x^2 + y^2 = z^2$$")

    assert 'class="math-inline"' in inline
    assert "<mfrac>" in inline
    assert 'class="math-block"' in block
    assert 'display="block"' in block


def test_tex_inside_code_span_is_not_rendered() -> None:
    rendered = create_markdown_renderer().render(r"`\overline{9}`")

    assert "<code>\\overline{9}</code>" in rendered
    assert "<math" not in rendered
