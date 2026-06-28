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

    def _ok_unless_false_or_minus_one(self, result: Any) -> bool:
        return result is not False and result != -1

    def _to_int(self, context: str, value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError) as e:
            diagnostics.record_exception(context, e, value=repr(value))
            return default

    def _to_float(self, context: str, value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError) as e:
            diagnostics.record_exception(context, e, value=repr(value))
            return default

    def stop(self, context: str = "vlc_stop", **fields: Any) -> bool:
        return self._ok_unless_false_or_minus_one(
            self.call(context, self._player.stop, default=-1, **fields)
        )

    def play(self, context: str = "vlc_play", **fields: Any) -> bool:
        return self._ok_unless_false_or_minus_one(
            self.call(context, self._player.play, default=-1, **fields)
        )

    def pause(self, context: str = "vlc_pause", **fields: Any) -> bool:
        return self._ok_unless_false_or_minus_one(
            self.call(context, self._player.pause, default=-1, **fields)
        )

    def set_media(self, media: Any, context: str = "vlc_set_media", **fields: Any) -> bool:
        return self._ok_unless_false_or_minus_one(
            self.call(
                context,
                lambda: self._player.set_media(media),
                default=-1,
                **fields,
            )
        )

    def set_time(self, value: int, context: str = "vlc_set_time", **fields: Any) -> bool:
        return self._ok_unless_false_or_minus_one(
            self.call(
                context,
                lambda: self._player.set_time(value),
                default=-1,
                value=value,
                **fields,
            )
        )

    def set_rate(self, value: float, context: str = "vlc_set_rate", **fields: Any) -> bool:
        return self._ok_unless_false_or_minus_one(
            self.call(
                context,
                lambda: self._player.set_rate(value),
                default=-1,
                rate=value,
                **fields,
            )
        )

    def get_state(self, default: Any = None) -> Any:
        return self.call("vlc_get_state", self._player.get_state, default=default)

    def get_time(self, default: int = -1) -> int:
        value = self.call("vlc_get_time", self._player.get_time, default=default)
        return self._to_int("vlc_get_time_convert", value, default)

    def get_length(self, default: int = -1) -> int:
        value = self.call("vlc_get_length", self._player.get_length, default=default)
        return self._to_int("vlc_get_length_convert", value, default)

    def get_rate(self, default: float = 1.0) -> float:
        value = self.call("vlc_get_rate", self._player.get_rate, default=default)
        return self._to_float("vlc_get_rate_convert", value, default)

    def is_playing(self) -> bool:
        return bool(self.call("vlc_is_playing", self._player.is_playing, default=False))

    def audio_set_volume(self, value: int, context: str = "vlc_audio_set_volume") -> bool:
        return self._ok_unless_false_or_minus_one(
            self.call(
                context,
                lambda: self._player.audio_set_volume(value),
                default=-1,
                value=value,
            )
        )

    def audio_get_mute(self) -> int:
        value = self.call("vlc_audio_get_mute", self._player.audio_get_mute, default=-1)
        return self._to_int("vlc_audio_get_mute_convert", value, -1)

    def audio_set_mute(self, value: bool, context: str = "vlc_audio_set_mute") -> bool:
        return self._ok_unless_false_or_minus_one(
            self.call(
                context,
                lambda: self._player.audio_set_mute(value),
                default=-1,
                muted=value,
            )
        )

    def audio_toggle_mute(self, context: str = "vlc_audio_toggle_mute") -> bool:
        return self._ok_unless_false_or_minus_one(
            self.call(context, self._player.audio_toggle_mute, default=-1)
        )

    def audio_get_track(self, default: int = -1) -> int:
        value = self.call("vlc_audio_get_track", self._player.audio_get_track, default=default)
        return self._to_int("vlc_audio_get_track_convert", value, default)

    def audio_set_track(self, value: int, context: str = "vlc_audio_set_track") -> bool:
        return self._ok_unless_false_or_minus_one(
            self.call(
                context,
                lambda: self._player.audio_set_track(value),
                default=-1,
                track_id=value,
            )
        )

    def audio_get_track_description(self) -> list[tuple[int, str]]:
        descriptions = self.call(
            "vlc_audio_get_track_description",
            self._player.audio_get_track_description,
            default=[],
        )
        if not descriptions:
            return []

        result: list[tuple[int, str]] = []
        for item in descriptions:
            try:
                track_id, name = item
                if isinstance(name, bytes):
                    name = name.decode("utf-8", errors="replace")
                result.append((int(track_id), str(name)))
            except (TypeError, ValueError) as e:
                diagnostics.record_exception(
                    "vlc_audio_track_description_convert",
                    e,
                    value=repr(item),
                )
        return result

    def video_get_spu(self, default: int = -1) -> int:
        value = self.call("vlc_video_get_spu", self._player.video_get_spu, default=default)
        return self._to_int("vlc_video_get_spu_convert", value, default)

    def video_set_spu(self, value: int, context: str = "vlc_video_set_spu") -> bool:
        return self._ok_unless_false_or_minus_one(
            self.call(
                context,
                lambda: self._player.video_set_spu(value),
                default=-1,
                spu_id=value,
            )
        )

    def video_get_spu_description(self) -> list[tuple[int, str]]:
        descriptions = self.call(
            "vlc_video_get_spu_description",
            self._player.video_get_spu_description,
            default=[],
        )
        if not descriptions:
            return []

        result: list[tuple[int, str]] = []
        for item in descriptions:
            try:
                spu_id, name = item
                if isinstance(name, bytes):
                    name = name.decode("utf-8", errors="replace")
                result.append((int(spu_id), str(name)))
            except (TypeError, ValueError) as e:
                diagnostics.record_exception(
                    "vlc_video_spu_description_convert",
                    e,
                    value=repr(item),
                )
        return result
