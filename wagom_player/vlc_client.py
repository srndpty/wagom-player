"""python-vlc とのやり取りを薄くラップするモジュール。"""
from __future__ import annotations

import os
from typing import Optional

try:
    import vlc
except ImportError as e:  # pragma: no cover - ランタイム依存のため
    raise SystemExit(
        "python-vlc が見つかりません。`pip install python-vlc` を実行してください"
    ) from e


class VlcController:
    def __init__(self, lib_path: Optional[str] = None):
        args = ["--audio-time-stretch"]
        if lib_path and os.path.isdir(lib_path):
            args.append(f"--plugin-path={lib_path}")
        self.instance = vlc.Instance(args)
        self.player: vlc.MediaPlayer = self.instance.media_player_new()

    def set_widget(self, widget_id: int) -> None:
        try:
            self.player.set_hwnd(widget_id)
        except Exception:
            try:
                self.player.set_xwindow(widget_id)
            except Exception:
                pass

    def play_file(self, path: str) -> None:
        media = self.instance.media_new(path)
        self.player.set_media(media)
        self.player.play()

    def pause_or_play(self) -> None:
        if self.player.is_playing():
            self.player.pause()
        else:
            self.player.play()

    def stop(self) -> None:
        self.player.stop()

    def set_time(self, position_ms: int) -> None:
        self.player.set_time(position_ms)

    def get_time(self) -> int:
        return self.player.get_time()

    def get_length(self) -> int:
        return self.player.get_length()

    def set_rate(self, rate: float) -> None:
        self.player.set_rate(rate)

    def get_state(self):
        return self.player.get_state()
