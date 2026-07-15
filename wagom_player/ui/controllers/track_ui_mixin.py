# ruff: noqa: F401
import os
import sys
import threading
from typing import Optional

from PyQt5 import QtCore, QtGui, QtWidgets

from ...application.file_actions import (
    CollisionResolution,
    InvalidMoveTargetError,
    TargetFileExistsError,
    target_path_for_subfolder,
    validate_move_to_subfolder,
)
from ...domain.formatting import format_ms
from ...domain.playlist import SUPPORTED_VIDEO_EXTENSIONS, PlaylistSession
from ...domain.playlist import next_path as next_playlist_path
from ...domain.window_title import build_window_title
from ...infrastructure import diagnostics, vlc_backend
from ...infrastructure.logger import log_message
from ...infrastructure.media_files import collect_video_files
from ...infrastructure.settings_store import PlayerSettings, SettingsRepository
from ...infrastructure.trash import TrashService
from ...infrastructure.windows_integration import apply_windows_dark_titlebar
from ..dialogs import MetadataDialog, ShortcutListDialog
from ..overlay import OverlayLabel
from ..player_view import apply_control_icons, build_player_view
from ..shortcut_binder import bind_shortcuts
from ..shortcuts import SHORTCUT_ROWS
from ..styles import (
    SEEK_SLIDER_STYLE_NORMAL,
    SEEK_SLIDER_STYLE_WARNING,
)
from .file_operation_controller import FileOperationController
from .track_controller import TrackController

vlc = vlc_backend.vlc
VlcEvents = vlc_backend.VlcEvents
VlcPlayerAdapter = vlc_backend.VlcPlayerAdapter

try:
    from send2trash import send2trash
except ImportError:
    send2trash = None  # type: ignore[assignment]


def _create_vlc_instance() -> "vlc.Instance":
    vlc_backend.vlc = vlc
    return vlc_backend.create_vlc_instance()


class TrackUiMixin:
    def _rebuild_audio_menu(self) -> None:
        self.audio_menu.clear()
        self.audio_menu.addAction("ミュート切替").triggered.connect(self._toggle_mute)
        self.audio_menu.addAction("音量を上げる").triggered.connect(
            lambda: self._adjust_volume(+10)
        )
        self.audio_menu.addAction("音量を下げる").triggered.connect(
            lambda: self._adjust_volume(-10)
        )
        self.audio_menu.addSeparator()
        self._populate_audio_track_menu(self.audio_menu)

    def _populate_audio_track_menu(self, menu: QtWidgets.QMenu) -> None:
        tracks = self._audio_tracks()
        if not tracks:
            action = menu.addAction("音声トラックなし")
            action.setEnabled(False)
            return

        current_track_id = self.vlc_player.audio_get_track()
        for track_id, name in tracks:
            action = menu.addAction(self._audio_track_display_name(track_id, name))
            action.setCheckable(True)
            action.setChecked(track_id == current_track_id)
            action.triggered.connect(
                lambda _checked=False, tid=track_id, label=name: self._select_audio_track(
                    tid,
                    label,
                )
            )

    def _audio_tracks(self) -> list[tuple[int, str]]:
        return self.vlc_player.audio_get_track_description()

    def _audio_track_display_name(self, track_id: int, name: str) -> str:
        return name or f"Track {track_id}"

    def _select_audio_track(self, track_id: int, name: str) -> None:
        if not self.vlc_player.audio_set_track(track_id, context="select_audio_track"):
            self._show_status_message("音声トラックの切替に失敗しました", 3000)
            return

        # 手動選択が成功した時点で pending を確実に落とす。表示名から言語を取り出せない
        # トラック（"Commentary" 等）でも、残存タイマーが優先言語で上書きするのを防ぐ。
        self._pending_audio_language_apply = False

        language = self._audio_track_language_key(name)
        if language:
            self.preferred_audio_language = language
            self.settings_store.set_value("preferred_audio_language", language)
        display_name = self._audio_track_display_name(track_id, name)
        self._show_status_message(f"音声トラック: {display_name}", 3000)
        self._show_overlay(f"[音声: {display_name}]")

    def _schedule_preferred_track_apply(self) -> None:
        self._pending_audio_language_apply = True
        self._pending_subtitle_apply = True
        # この play_at に紐づく世代を採番。遅延 callback はこの世代を捕捉し、別の動画へ
        # 切り替わった後に発火しても何もしないようにする。Playing イベントも起点になる。
        generation = self._track_apply_generation = self._track_apply_generation + 1
        for delay_ms in (150, 500, 1200):
            QtCore.QTimer.singleShot(
                delay_ms,
                lambda gen=generation: self._apply_preferred_tracks_if_pending(gen),
            )

    def _apply_preferred_tracks_if_pending(self, generation: Optional[int] = None) -> None:
        if self._vlc_stop_in_progress:
            return
        # 別の動画へ切り替わった後の古い callback なら何もしない。
        if generation is not None and generation != self._track_apply_generation:
            return
        if self._pending_audio_language_apply and self._apply_preferred_audio_track(
            show_message=False
        ):
            self._pending_audio_language_apply = False
        if self._pending_subtitle_apply and self._apply_preferred_subtitle_track(
            show_message=False
        ):
            self._pending_subtitle_apply = False

    def _is_media_ready_for_tracks(self) -> bool:
        """メディアの入力が確定し、トラック操作が意味を持つ状態かを返す。

        ``audio_get_track()`` / ``video_get_spu()`` は入力未確定時にも ``-1`` を返すため、
        それらの値だけでは「確定済みでオフ」と「未確定」を区別できない。再生中であるか、
        長さが取得できていることをもって確定済みとみなす。
        """
        if self.vlc_player.is_playing():
            return True
        return self.vlc_player.get_length() > 0

    def _apply_preferred_audio_track(self, show_message: bool) -> bool:
        language = self._normalize_audio_language(self.preferred_audio_language)
        if not language:
            return True

        # トラック一覧が空＝まだ入力未確定。pending を維持して後続の試行に委ねる。
        if not self._audio_tracks():
            return False

        match = self._find_audio_track_for_language(language)
        if match is None:
            # 入力は確定済みだが該当言語が無い。これ以上の再試行は無意味なので確定扱い。
            return True

        track_id, name = match
        current_track_id = self.vlc_player.audio_get_track()
        if current_track_id == track_id:
            return True

        if not self.vlc_player.audio_set_track(track_id, context="apply_preferred_audio_track"):
            return False

        if show_message:
            self._show_status_message(
                f"音声トラック: {self._audio_track_display_name(track_id, name)}",
                3000,
            )
        return True

    def _find_audio_track_for_language(self, language: str) -> Optional[tuple[int, str]]:
        return self.track_controller.find_audio(language)

    def _normalize_audio_language(self, value: object) -> str:
        return self.track_controller.normalize_language(value)

    def _audio_track_language_key(self, name: str) -> str:
        return self.track_controller.language_key(name)

    # ------------- 字幕トラック -------------
    def _rebuild_subtitle_menu(self) -> None:
        self.subtitle_menu.clear()
        self._populate_subtitle_track_menu(self.subtitle_menu)

    def _populate_subtitle_track_menu(self, menu: QtWidgets.QMenu) -> None:
        tracks = self._subtitle_tracks()
        current_spu = self.vlc_player.video_get_spu()

        if not tracks:
            action = menu.addAction("字幕トラックなし")
            action.setEnabled(False)
            return

        for spu_id, name in tracks:
            action = menu.addAction(self._subtitle_track_display_name(spu_id, name))
            action.setCheckable(True)
            action.setChecked(spu_id == current_spu)
            action.triggered.connect(
                lambda _checked=False, sid=spu_id, label=name: self._select_subtitle_track(
                    sid,
                    label,
                )
            )

    def _subtitle_tracks(self) -> list[tuple[int, str]]:
        tracks = self.vlc_player.video_get_spu_description()
        if not tracks:
            return []
        if not any(spu_id < 0 for spu_id, _name in tracks):
            return [(-1, "オフ"), *tracks]
        return tracks

    def _subtitle_track_display_name(self, spu_id: int, name: str) -> str:
        if spu_id < 0:
            return "オフ"
        return name or f"Subtitle {spu_id}"

    def _select_subtitle_track(self, spu_id: int, name: str) -> None:
        if not self.vlc_player.video_set_spu(spu_id, context="select_subtitle_track"):
            self._show_status_message("字幕の切替に失敗しました", 3000)
            return

        # 手動選択が成功した時点で pending を確実に落とす。残存タイマーによる上書きを防ぐ。
        self._pending_subtitle_apply = False

        if spu_id < 0:
            self.subtitle_enabled = False
            self.settings_store.set_value("subtitle_enabled", False)
            self._show_status_message("字幕: オフ", 3000)
            self._show_overlay("[字幕: オフ]")
            return

        self.subtitle_enabled = True
        language = self._audio_track_language_key(name)
        if language:
            self.preferred_subtitle_language = language
            self.settings_store.set_value("preferred_subtitle_language", language)
        self.settings_store.set_value("subtitle_enabled", True)
        display_name = self._subtitle_track_display_name(spu_id, name)
        self._show_status_message(f"字幕: {display_name}", 3000)
        self._show_overlay(f"[字幕: {display_name}]")

    def _apply_preferred_subtitle_track(self, show_message: bool) -> bool:
        # 入力未確定のうちは何もできない。pending を維持して後続の試行に委ねる。
        if not self._is_media_ready_for_tracks():
            return False

        if not self.subtitle_enabled:
            # 現在 -1 でも「成功」とは扱わない。VLC の初期トラック選択が後から字幕を有効に
            # することがあるため、確定後の各試行で明示的にオフを指示し続ける。pending を
            # 落とさない（False を返す）ことで、最後の試行まで -1 を強制する。
            self.vlc_player.video_set_spu(-1, context="apply_subtitle_off")
            return False

        language = self._normalize_audio_language(self.preferred_subtitle_language)
        match = self._find_subtitle_track_for_language(language)
        if match is None:
            # 字幕トラックが既に存在するのに該当言語が無ければ確定扱い。まだ字幕トラックが
            # 出そろっていない可能性があるなら pending を維持して再試行する。
            return self._has_real_subtitle_tracks()

        spu_id, name = match
        current_spu = self.vlc_player.video_get_spu()
        if current_spu == spu_id:
            return True

        if not self.vlc_player.video_set_spu(spu_id, context="apply_preferred_subtitle_track"):
            return False

        if show_message:
            self._show_status_message(
                f"字幕: {self._subtitle_track_display_name(spu_id, name)}",
                3000,
            )
        return True

    def _find_subtitle_track_for_language(self, language: str) -> Optional[tuple[int, str]]:
        return self.track_controller.find_subtitle(language)

    def _has_real_subtitle_tracks(self) -> bool:
        """「オフ」を除いた実体のある字幕トラックが存在するかを返す。"""
        return any(spu_id >= 0 for spu_id, _name in self._subtitle_tracks())
