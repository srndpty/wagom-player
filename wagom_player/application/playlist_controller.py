from collections.abc import Callable, Sequence

from ..domain.playlist import (
    active_playlist,
    adjacent_index,
    create_shuffled_playlist,
    next_index_after_removal,
)


class PlaylistController:
    def active(
        self,
        directory_playlist: Sequence[str],
        shuffled_playlist: Sequence[str],
        shuffle_enabled: bool,
    ) -> list[str]:
        return active_playlist(directory_playlist, shuffled_playlist, shuffle_enabled)

    def shuffled(
        self,
        directory_playlist: Sequence[str],
        current_index: int,
        shuffle_func: Callable[[list[str]], None],
    ) -> list[str]:
        return create_shuffled_playlist(directory_playlist, current_index, shuffle_func)

    def adjacent_index(
        self,
        directory_playlist: Sequence[str],
        active: Sequence[str],
        current_index: int,
        offset: int,
    ) -> int | None:
        return adjacent_index(directory_playlist, active, current_index, offset)

    def next_index_after_removal(
        self,
        directory_playlist: Sequence[str],
        removed_index: int,
        shuffle_enabled: bool,
        remembered_next_path: str | None,
    ) -> int | None:
        return next_index_after_removal(
            directory_playlist,
            removed_index,
            shuffle_enabled,
            remembered_next_path,
        )
