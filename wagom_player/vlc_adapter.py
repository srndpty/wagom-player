from collections.abc import Callable
from typing import Any

from . import diagnostics


class VlcPlayerAdapter:
    """Small exception-safe boundary around python-vlc player calls."""

    def __init__(self, player: Any):
        self._player = player

    @property
    def raw(self) -> Any:
        return self._player

    def call(
        self, context: str, func: Callable[[], Any], default: Any = None, **fields: Any
    ) -> Any:
        return diagnostics.run_safely(context, func, default=default, **fields)

    def stop(self, context: str = "vlc_stop", **fields: Any) -> bool:
        return self.call(context, self._player.stop, default=False, **fields) is not False

    def play(self, context: str = "vlc_play", **fields: Any) -> bool:
        return self.call(context, self._player.play, default=False, **fields) is not False

    def pause(self, context: str = "vlc_pause", **fields: Any) -> bool:
        return self.call(context, self._player.pause, default=False, **fields) is not False

    def set_media(self, media: Any, context: str = "vlc_set_media", **fields: Any) -> bool:
        return (
            self.call(
                context,
                lambda: self._player.set_media(media),
                default=False,
                **fields,
            )
            is not False
        )

    def set_time(self, value: int, context: str = "vlc_set_time", **fields: Any) -> bool:
        return (
            self.call(
                context,
                lambda: self._player.set_time(value),
                default=False,
                value=value,
                **fields,
            )
            is not False
        )

    def set_rate(self, value: float, context: str = "vlc_set_rate", **fields: Any) -> bool:
        return (
            self.call(
                context,
                lambda: self._player.set_rate(value),
                default=False,
                rate=value,
                **fields,
            )
            is not False
        )

    def get_state(self, default: Any = None) -> Any:
        return self.call("vlc_get_state", self._player.get_state, default=default)

    def get_time(self, default: int = -1) -> int:
        return int(self.call("vlc_get_time", self._player.get_time, default=default))

    def get_length(self, default: int = -1) -> int:
        return int(self.call("vlc_get_length", self._player.get_length, default=default))

    def get_rate(self, default: float = 1.0) -> float:
        return float(self.call("vlc_get_rate", self._player.get_rate, default=default))

    def is_playing(self) -> bool:
        return bool(self.call("vlc_is_playing", self._player.is_playing, default=False))

    def audio_set_volume(self, value: int, context: str = "vlc_audio_set_volume") -> bool:
        return (
            self.call(
                context,
                lambda: self._player.audio_set_volume(value),
                default=False,
                value=value,
            )
            is not False
        )

    def audio_get_mute(self) -> int:
        return int(self.call("vlc_audio_get_mute", self._player.audio_get_mute, default=-1))

    def audio_set_mute(self, value: bool, context: str = "vlc_audio_set_mute") -> bool:
        return (
            self.call(
                context,
                lambda: self._player.audio_set_mute(value),
                default=False,
                muted=value,
            )
            is not False
        )

    def audio_toggle_mute(self, context: str = "vlc_audio_toggle_mute") -> bool:
        return self.call(context, self._player.audio_toggle_mute, default=False) is not False
