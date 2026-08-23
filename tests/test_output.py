from kinebeat.domain import OutputFormat, resolve_output_format


def test_auto_output_uses_vertical_canvas_for_vertical_footage() -> None:
    result = resolve_output_format(
        OutputFormat.AUTO,
        ((1080, 1920), (720, 1280), (1080, 1920)),
    )

    assert result is OutputFormat.VERTICAL_9_16
    assert result.preview_size == (360, 640)


def test_auto_output_uses_four_five_for_portrait_footage() -> None:
    result = resolve_output_format(OutputFormat.AUTO, ((1080, 1350), (2160, 2700)))

    assert result is OutputFormat.PORTRAIT_4_5


def test_explicit_output_overrides_source_orientation() -> None:
    result = resolve_output_format(OutputFormat.SQUARE_1_1, ((1920, 1080),))

    assert result is OutputFormat.SQUARE_1_1
