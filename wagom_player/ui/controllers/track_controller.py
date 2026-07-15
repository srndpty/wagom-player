from collections.abc import Callable
from typing import Optional

from ...domain.tracks import find_track, language_key, normalize_language


class TrackController:
    """音声・字幕トラックの言語判定を再生UIから分離する。"""

    def __init__(
        self,
        audio_tracks: Callable[[], list[tuple[int, str]]],
        subtitle_tracks: Callable[[], list[tuple[int, str]]],
    ) -> None:
        self._audio_tracks = audio_tracks
        self._subtitle_tracks = subtitle_tracks

    def normalize_language(self, value: object) -> str:
        normalized = normalize_language(value)
        return normalized.split("-", 1)[0]

    def language_key(self, name: str) -> str:
        return language_key(name)

    def find_audio(self, language: str) -> Optional[tuple[int, str]]:
        return find_track(self._audio_tracks(), language)

    def find_subtitle(self, language: str) -> Optional[tuple[int, str]]:
        tracks = [track for track in self._subtitle_tracks() if track[0] >= 0]
        return find_track(tracks, language)
