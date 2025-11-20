"""プレイリスト管理用のシンプルなロジック層。"""
from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from .sorting import windows_logical_key


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"}


def is_supported_video(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS


@dataclass
class PlaylistManager:
    """ディレクトリを超えてもシンプルに使えるプレイリスト管理クラス。"""

    files: List[str] = field(default_factory=list)
    current_index: int = -1
    shuffle_enabled: bool = False
    repeat_enabled: bool = False
    _shuffled: List[str] = field(default_factory=list)
    _random: random.Random = field(default_factory=random.Random)

    def load(self, files: Iterable[str], current: Optional[str] = None) -> None:
        filtered = [os.path.abspath(p) for p in files if is_supported_video(p)]
        filtered.sort(key=windows_logical_key)
        self.files = filtered
        self._rebuild_shuffle(force_empty=True)
        self.current_index = self._resolve_index(current)

    def _resolve_index(self, current: Optional[str]) -> int:
        if not self.files:
            return -1
        if current is None:
            return 0
        try:
            return self.files.index(os.path.abspath(current))
        except ValueError:
            return 0

    def _rebuild_shuffle(self, force_empty: bool = False) -> None:
        if force_empty:
            self._shuffled = []
        if not self.shuffle_enabled or not self.files:
            return

        current_path = self.current_path
        remaining = [p for p in self.files if p != current_path]
        self._random.shuffle(remaining)
        if current_path:
            self._shuffled = [current_path] + remaining
        else:
            self._shuffled = remaining

    @property
    def current_playlist(self) -> List[str]:
        if self.shuffle_enabled and self._shuffled:
            return self._shuffled
        return self.files

    @property
    def current_path(self) -> str:
        if 0 <= self.current_index < len(self.files):
            return self.files[self.current_index]
        return ""

    def set_shuffle(self, enabled: bool) -> None:
        self.shuffle_enabled = enabled
        self._rebuild_shuffle(force_empty=True)

    def set_repeat(self, enabled: bool) -> None:
        self.repeat_enabled = enabled

    def next_index(self) -> Optional[int]:
        playlist = self.current_playlist
        if not playlist:
            return None
        if self.repeat_enabled and self.current_path:
            return self.current_index
        if not self.current_path:
            return 0
        try:
            idx = playlist.index(self.current_path)
        except ValueError:
            return None
        if idx + 1 >= len(playlist):
            return None
        next_path = playlist[idx + 1]
        try:
            return self.files.index(next_path)
        except ValueError:
            return None

    def previous_index(self) -> Optional[int]:
        playlist = self.current_playlist
        if not playlist or not self.current_path:
            return None
        try:
            idx = playlist.index(self.current_path)
        except ValueError:
            return None
        if idx - 1 < 0:
            return None
        prev_path = playlist[idx - 1]
        try:
            return self.files.index(prev_path)
        except ValueError:
            return None

    def remove(self, index: int) -> None:
        if not (0 <= index < len(self.files)):
            return
        removed_path = self.files.pop(index)
        if self.shuffle_enabled:
            try:
                self._shuffled.remove(removed_path)
            except ValueError:
                pass
        if index < self.current_index:
            self.current_index -= 1
        elif index == self.current_index:
            self.current_index = min(self.current_index, len(self.files) - 1)
        if not self.files:
            self.current_index = -1
            self._shuffled = []

    def describe(self) -> str:
        total = len(self.current_playlist)
        if total == 0:
            return "0 / 0"
        position = 0
        if self.current_path:
            try:
                position = self.current_playlist.index(self.current_path) + 1
            except ValueError:
                position = 0
        return f"{position} / {total}"
