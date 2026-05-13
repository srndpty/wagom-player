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
    if not (0 <= current_index < len(directory_playlist)):
        return []

    current_path = directory_playlist[current_index]
    remaining = list(directory_playlist)
    remaining.remove(current_path)
    shuffle_func(remaining)
    return [current_path, *remaining]


def adjacent_index(
    directory_playlist: Sequence[str],
    active: Sequence[str],
    current_index: int,
    offset: int,
) -> Optional[int]:
    if not active or not (0 <= current_index < len(directory_playlist)):
        return None

    current_path = directory_playlist[current_index]
    try:
        active_index = active.index(current_path)
        target_index = active_index + offset
        if not (0 <= target_index < len(active)):
            return None
        target_path = active[target_index]
        return directory_playlist.index(target_path)
    except ValueError:
        return None


def next_path(active: Sequence[str], current_path: str) -> Optional[str]:
    try:
        active_index = active.index(current_path)
        return active[active_index + 1]
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
        if remembered_next_path in directory_playlist:
            return directory_playlist.index(remembered_next_path)
        return None

    if removed_index < len(directory_playlist):
        return removed_index
    return None
