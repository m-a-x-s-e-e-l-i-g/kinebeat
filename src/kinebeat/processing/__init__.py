"""Local audio processing with no Qt dependencies."""

from kinebeat.processing.analyser import MusicAnalysisService
from kinebeat.processing.audio_probe import probe_song

__all__ = ["MusicAnalysisService", "probe_song"]
