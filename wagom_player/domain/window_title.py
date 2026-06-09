import os
from collections.abc import Sequence
from typing import Optional

from .formatting import format_ms


def build_window_title(
    *,
    playlist: Sequence[str],
    current_path: str,
    shuffle_enabled: bool,
    media_length_ms: int,
    filename: Optional[str] = None,
) -> str:
    name = filename or (os.path.basename(current_path) if current_path else "")
    try:
        index = playlist.index(current_path) + 1 if current_path else 0
    except ValueError:
        index = 0

    prefix = f"[{index}/{len(playlist)}] " if playlist else ""
    shuffle_indicator = "[S] " if shuffle_enabled else ""
    duration = f" [{format_ms(media_length_ms)}]" if media_length_ms > 0 else ""
    return f"{shuffle_indicator}{prefix}{name}{duration}"
