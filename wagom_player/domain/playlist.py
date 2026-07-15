from collections.abc import Callable, MutableSequence, Sequence
from typing import Optional


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
    remaining = list(directory_playlist)
    if current_index == -1:
        shuffle_func(remaining)
        return remaining
    if not 0 <= current_index < len(remaining):
        return []
    current = remaining.pop(current_index)
    shuffle_func(remaining)
    return [current, *remaining]


def _validate_unique_paths(paths: Sequence[str]) -> list[str]:
    candidate = list(paths)
    if len(candidate) != len(set(candidate)):
        raise ValueError("プレイリスト内のパスは一意である必要があります")
    return candidate


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


class PlaylistSession:
    """一意なパスのプレイリストと現在位置を一貫した状態として管理する。"""

    def __init__(
        self,
        paths: Sequence[str] = (),
        current_index: int = -1,
        shuffle_enabled: bool = False,
        shuffled_paths: Sequence[str] = (),
    ) -> None:
        self._paths = _validate_unique_paths(paths)
        self._current_index = -1
        self._shuffle_enabled = False
        self._shuffled_paths: list[str] = []
        if current_index != -1 and not self.select(current_index):
            raise ValueError(f"現在位置が範囲外です: {current_index}")
        if shuffle_enabled:
            self.replace_shuffle_order(shuffled_paths)

    @property
    def paths(self) -> list[str]:
        return list(self._paths)

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def shuffle_enabled(self) -> bool:
        return self._shuffle_enabled

    @property
    def shuffled_paths(self) -> list[str]:
        return list(self._shuffled_paths)

    @property
    def current_path(self) -> Optional[str]:
        if 0 <= self._current_index < len(self._paths):
            return self._paths[self._current_index]
        return None

    def load(self, paths: Sequence[str], current_path: Optional[str] = None) -> int:
        self.replace_playlist(paths)
        if not self._paths:
            self._current_index = -1
        elif current_path in self._paths:
            self._current_index = self._paths.index(current_path)
        else:
            self._current_index = 0
        return self._current_index

    def replace_playlist(self, paths: Sequence[str]) -> None:
        self._paths = _validate_unique_paths(paths)
        self._current_index = -1
        self._shuffle_enabled = False
        self._shuffled_paths = []

    def select(self, index: int) -> bool:
        if not 0 <= index < len(self._paths):
            return False
        self._current_index = index
        return True

    def clear_selection(self) -> None:
        self._current_index = -1

    def active_paths(self) -> list[str]:
        return active_playlist(self._paths, self._shuffled_paths, self._shuffle_enabled)

    def adjacent(self, offset: int) -> Optional[int]:
        return adjacent_index(self._paths, self.active_paths(), self._current_index, offset)

    def set_shuffle(
        self,
        enabled: bool,
        shuffle_func: Callable[[MutableSequence[str]], None],
    ) -> None:
        if not enabled:
            self._shuffle_enabled = False
            self._shuffled_paths = []
            return

        candidate = create_shuffled_playlist(
            self._paths,
            self._current_index,
            shuffle_func,
        )
        if sorted(candidate) != sorted(self._paths):
            raise ValueError("シャッフル順は元のプレイリストと同じ項目を含む必要があります")

        self._shuffle_enabled = True
        self._shuffled_paths = candidate

    def replace_shuffle_order(self, paths: Sequence[str]) -> None:
        candidate = list(paths)
        if sorted(candidate) != sorted(self._paths):
            raise ValueError("シャッフル順は元のプレイリストと同じ項目を含む必要があります")
        self._shuffle_enabled = True
        self._shuffled_paths = candidate

    def remove_current(self, remembered_next_path: Optional[str] = None) -> Optional[int]:
        if not 0 <= self._current_index < len(self._paths):
            return None
        removed_index = self._current_index
        removed_path = self._paths.pop(removed_index)
        if removed_path in self._shuffled_paths:
            self._shuffled_paths.remove(removed_path)
        next_index = next_index_after_removal(
            self._paths,
            removed_index,
            self._shuffle_enabled,
            remembered_next_path,
        )
        if next_index is None:
            self._current_index = -1
            return None
        self._current_index = next_index
        return next_index


__all__ = [
    "PlaylistSession",
    "active_playlist",
    "adjacent_index",
    "create_shuffled_playlist",
    "next_index_after_removal",
    "next_path",
]
