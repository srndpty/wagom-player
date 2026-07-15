import functools
import os
import re
from collections.abc import Callable, MutableSequence, Sequence
from dataclasses import dataclass, field
from typing import Optional

SUPPORTED_VIDEO_EXTENSIONS = (
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".asf",
    ".ts",
    ".m2ts",
    ".m4v",
    ".3gp",
    ".3g2",
    ".mpeg",
    ".mpg",
    ".mpe",
    ".rm",
    ".rmvb",
    ".vob",
    ".webm",
)


def natural_key(path: str) -> list[object]:
    """ファイル名を、大文字と小文字を区別しない自然順へ変換する。"""
    parts = re.split(r"(\d+)", os.path.basename(path))
    return [int(part) if part.isdigit() else part.casefold() for part in parts]


def create_windows_logical_key(comparer=None):
    """Windowsの論理順比較関数、または自然順の代替キーを返す。"""
    if comparer:

        def compare(left: str, right: str) -> int:
            return comparer(os.path.basename(left), os.path.basename(right))

        return functools.cmp_to_key(compare)
    return natural_key


def is_supported_video_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUPPORTED_VIDEO_EXTENSIONS


def active_playlist(
    directory_playlist: Sequence[str],
    shuffled_playlist: Sequence[str],
    shuffle_enabled: bool,
) -> list[str]:
    return list(shuffled_playlist if shuffle_enabled else directory_playlist)


def create_shuffled_playlist(
    directory_playlist: Sequence[str],
    current_index: int,
    shuffle_func: Callable[[MutableSequence[str]], None],
) -> list[str]:
    if not 0 <= current_index < len(directory_playlist):
        return []
    current = directory_playlist[current_index]
    remaining = [path for path in directory_playlist if path != current]
    shuffle_func(remaining)
    return [current, *remaining]


def adjacent_index(
    directory_playlist: Sequence[str],
    active: Sequence[str],
    current_index: int,
    offset: int,
) -> Optional[int]:
    if not active or not 0 <= current_index < len(directory_playlist):
        return None
    try:
        current_path = directory_playlist[current_index]
        target_index = active.index(current_path) + offset
        if not 0 <= target_index < len(active):
            return None
        target_path = active[target_index]
        return directory_playlist.index(target_path)
    except (IndexError, ValueError):
        return None


def next_path(active: Sequence[str], current_path: str) -> Optional[str]:
    try:
        return active[active.index(current_path) + 1]
    except (IndexError, ValueError):
        return None


def next_index_after_removal(
    directory_playlist: Sequence[str],
    removed_index: int,
    shuffle_enabled: bool,
    remembered_next_path: Optional[str],
) -> Optional[int]:
    if not directory_playlist:
        return None
    if shuffle_enabled:
        return (
            directory_playlist.index(remembered_next_path)
            if remembered_next_path in directory_playlist
            else None
        )
    return removed_index if removed_index < len(directory_playlist) else None


@dataclass
class PlaylistSession:
    """プレイリストと現在位置を一貫した状態として管理する。"""

    paths: list[str] = field(default_factory=list)
    current_index: int = -1
    shuffle_enabled: bool = False
    shuffled_paths: list[str] = field(default_factory=list)

    @property
    def current_path(self) -> Optional[str]:
        if 0 <= self.current_index < len(self.paths):
            return self.paths[self.current_index]
        return None

    def load(self, paths: Sequence[str], current_path: Optional[str] = None) -> int:
        self.paths = list(paths)
        self.shuffled_paths = []
        self.shuffle_enabled = False
        if not self.paths:
            self.current_index = -1
        elif current_path in self.paths:
            self.current_index = self.paths.index(current_path)
        else:
            self.current_index = 0
        return self.current_index

    def select(self, index: int) -> bool:
        if not 0 <= index < len(self.paths):
            return False
        self.current_index = index
        return True

    def active_paths(self) -> list[str]:
        return active_playlist(self.paths, self.shuffled_paths, self.shuffle_enabled)

    def adjacent(self, offset: int) -> Optional[int]:
        return adjacent_index(self.paths, self.active_paths(), self.current_index, offset)

    def set_shuffle(
        self,
        enabled: bool,
        shuffle_func: Callable[[MutableSequence[str]], None],
    ) -> None:
        self.shuffle_enabled = enabled
        self.shuffled_paths = (
            create_shuffled_playlist(self.paths, self.current_index, shuffle_func)
            if enabled
            else []
        )

    def remove_current(self, remembered_next_path: Optional[str] = None) -> Optional[int]:
        if not 0 <= self.current_index < len(self.paths):
            return None
        removed_index = self.current_index
        removed_path = self.paths.pop(removed_index)
        if removed_path in self.shuffled_paths:
            self.shuffled_paths.remove(removed_path)
        self.current_index = next_index_after_removal(
            self.paths,
            removed_index,
            self.shuffle_enabled,
            remembered_next_path,
        )
        if self.current_index is None:
            self.current_index = -1
            return None
        return self.current_index


__all__ = [
    "SUPPORTED_VIDEO_EXTENSIONS",
    "PlaylistSession",
    "active_playlist",
    "adjacent_index",
    "create_shuffled_playlist",
    "create_windows_logical_key",
    "is_supported_video_file",
    "natural_key",
    "next_index_after_removal",
    "next_path",
]
