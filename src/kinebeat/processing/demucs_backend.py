from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from kinebeat.domain import StemArtifact

ProgressCallback = Callable[[int, str], None]
CancelCheck = Callable[[], bool]


class AnalysisRuntimeUnavailable(RuntimeError):
    pass


class SeparationCancelled(RuntimeError):
    pass


class DemucsSeparator:
    model_name = "htdemucs_6s"
    stem_names = ("vocals", "drums", "bass", "guitar", "piano", "other")

    @staticmethod
    def is_available() -> bool:
        return importlib.util.find_spec("demucs") is not None

    def separate(
        self,
        source: Path,
        output_root: Path,
        *,
        progress: ProgressCallback,
        cancelled: CancelCheck,
    ) -> tuple[StemArtifact, ...]:
        if not self.is_available():
            raise AnalysisRuntimeUnavailable(
                "Music separation is not installed. Install Kinebeat with the analysis extra."
            )
        output_root.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            "-m",
            "demucs",
            "--name",
            self.model_name,
            "--out",
            str(output_root),
            str(source),
        ]
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        process = subprocess.Popen(  # noqa: S603 - fixed interpreter/module command
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation_flags,
        )
        output_lines: list[str] = []
        assert process.stdout is not None
        progress(15, "Separating instruments")
        while process.poll() is None:
            if cancelled():
                process.terminate()
                process.wait(timeout=10)
                raise SeparationCancelled("Music analysis cancelled.")
            line = process.stdout.readline()
            if line:
                output_lines.append(line.rstrip())
                progress(_demucs_progress(line), "Separating instruments")
        output_lines.extend(line.rstrip() for line in process.stdout.readlines())
        if process.returncode:
            detail = next((line for line in reversed(output_lines) if line), "Unknown error")
            raise RuntimeError(f"Instrument separation failed: {detail}")

        song_folder = output_root / self.model_name / source.stem
        artifacts = tuple(
            StemArtifact(name=name, path=song_folder / f"{name}.wav") for name in self.stem_names
        )
        missing = [artifact.path.name for artifact in artifacts if not artifact.path.is_file()]
        if missing:
            raise RuntimeError(f"Instrument separation did not create: {', '.join(missing)}")
        progress(72, "Instrument separation complete")
        return artifacts


def _demucs_progress(line: str) -> int:
    marker = "%"
    if marker not in line:
        return 20
    before = line.split(marker, 1)[0].rsplit(" ", 1)[-1].strip()
    try:
        percentage = int(before)
    except ValueError:
        return 20
    return 15 + round(max(0, min(100, percentage)) * 0.55)
