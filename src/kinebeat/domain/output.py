from __future__ import annotations

from enum import StrEnum


class OutputFormat(StrEnum):
    AUTO = "auto"
    LANDSCAPE_16_9 = "16:9"
    VERTICAL_9_16 = "9:16"
    SQUARE_1_1 = "1:1"
    PORTRAIT_4_5 = "4:5"

    @property
    def preview_size(self) -> tuple[int, int]:
        return {
            OutputFormat.LANDSCAPE_16_9: (640, 360),
            OutputFormat.VERTICAL_9_16: (360, 640),
            OutputFormat.SQUARE_1_1: (512, 512),
            OutputFormat.PORTRAIT_4_5: (512, 640),
        }.get(self, (640, 360))


def resolve_output_format(
    preference: OutputFormat,
    source_dimensions: tuple[tuple[int, int], ...],
) -> OutputFormat:
    if preference is not OutputFormat.AUTO:
        return preference
    valid = tuple(
        (width, height)
        for width, height in source_dimensions
        if width > 0 and height > 0
    )
    if not valid:
        return OutputFormat.LANDSCAPE_16_9

    landscape = sum(width / height > 1.1 for width, height in valid)
    portrait_dimensions = tuple(
        (width, height) for width, height in valid if width / height < 0.9
    )
    square = len(valid) - landscape - len(portrait_dimensions)
    if len(portrait_dimensions) > max(landscape, square):
        average_ratio = sum(width / height for width, height in portrait_dimensions) / len(
            portrait_dimensions
        )
        return min(
            (OutputFormat.VERTICAL_9_16, OutputFormat.PORTRAIT_4_5),
            key=lambda output: abs(output.preview_size[0] / output.preview_size[1] - average_ratio),
        )
    if square > landscape:
        return OutputFormat.SQUARE_1_1
    return OutputFormat.LANDSCAPE_16_9
