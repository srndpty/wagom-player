import os
import sys
from typing import Optional

from PyQt5 import QtCore, QtGui, QtWidgets

from ...domain.formatting import format_ms
from ...domain.playlist import SUPPORTED_VIDEO_EXTENSIONS, PlaylistSession
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
from .file_ui_mixin import FileUiMixin
from .track_controller import TrackController
from .track_ui_mixin import TrackUiMixin

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


class PlaybackController(TrackUiMixin, FileUiMixin, QtWidgets.QMainWindow):
    SEEK_SHORT_MS = 10_000
    SEEK_LONG_MS = 60_000
    FRAME_STEP_FALLBACK_MS = 33
    DEFAULT_AUDIO_LANGUAGE = "ja"
    AUDIO_LANGUAGE_ALIASES = {
        "ja": ("ja", "jpn", "jp", "japanese", "japan", "日本語", "日本", "日語"),
        "en": ("en", "eng", "english", "英語"),
        "ko": ("ko", "kor", "korean", "韓国語", "朝鮮語"),
        "zh": ("zh", "chi", "zho", "cn", "chinese", "mandarin", "中国語", "中文"),
        "fr": ("fr", "fre", "fra", "french", "フランス語"),
        "de": ("de", "ger", "deu", "german", "ドイツ語"),
        "es": ("es", "spa", "spanish", "スペイン語"),
        "it": ("it", "ita", "italian", "イタリア語"),
        "pt": ("pt", "por", "portuguese", "ポルトガル語"),
        "ru": ("ru", "rus", "russian", "ロシア語"),
    }

    @property
    def directory_playlist(self):
        return self.playlist_session.paths

    @directory_playlist.setter
    def directory_playlist(self, value):
        self.playlist_session.paths = value

    @property
    def current_index(self):
        return self.playlist_session.current_index

    @current_index.setter
    def current_index(self, value):
        self.playlist_session.current_index = value

    @property
    def shuffle_enabled(self):
        return self.playlist_session.shuffle_enabled

    @shuffle_enabled.setter
    def shuffle_enabled(self, value):
        self.playlist_session.shuffle_enabled = value

    @property
    def shuffled_playlist(self):
        return self.playlist_session.shuffled_paths

    @shuffled_playlist.setter
    def shuffled_playlist(self, value):
        self.playlist_session.shuffled_paths = value

    def __getattr__(self, name):
        view = self.__dict__.get("view")
        if view is not None and hasattr(view, name):
            return getattr(view, name)
        raise AttributeError(name)

    def __init__(self, file: Optional[str] = None):
        super().__init__()
        self._is_changing_media = False
        self.playback_rate_min = 0.25
        self.playback_rate_max = 4.0
        self.playback_rate = 1.0

        self.setWindowTitle("wagom-player")
        self.resize(960, 540)
        self.settings_store = SettingsRepository(QtCore.QSettings())
        self.playlist_session = PlaylistSession()
        self.trash_service = TrashService(send2trash)
        self.file_operation_controller = FileOperationController(self.trash_service)

        # VLC
        self.vlc_instance = _create_vlc_instance()
        self.player: vlc.MediaPlayer = self.vlc_instance.media_player_new()
        self.vlc_player = VlcPlayerAdapter(self.player)
        self.track_controller = TrackController(self._audio_tracks, self._subtitle_tracks)
        self.vlc_events = VlcEvents()
        self._vlc_generation = 0
        # libVLC の stop() をワーカースレッドで待っている間は、UI タイマーから
        # 同じ player へ問い合わせない。stop と get_time/get_length が競合すると
        # Windows では双方が戻らなくなることがある。
        self._vlc_stop_in_progress = False
        self._vlc_events_signal_connected = False
        self._attach_vlc_events(self._next_vlc_generation())

        self.repeat_enabled: bool = False
        self.shuffle_enabled: bool = False
        self.shuffled_playlist: list[str] = []

        # UI
        self._build_ui()

        self.overlay = OverlayLabel(self, self.video_frame)
        self.duration_overlay_label = self.overlay.label
        self.duration_overlay_timer = self.overlay.timer

        self.SEEK_SLIDER_STYLE_NORMAL = SEEK_SLIDER_STYLE_NORMAL
        self.SEEK_SLIDER_STYLE_WARNING = SEEK_SLIDER_STYLE_WARNING
        # 現在のシークバーの状態を管理するフラグ
        self._is_seek_bar_warning = False
        # 初期スタイルを適用
        self.seek_slider.setStyleSheet(self.SEEK_SLIDER_STYLE_NORMAL)

        # プレイリスト
        self.directory_playlist: list[str] = []  # ディレクトリ内の動画リスト
        self.current_index: int = -1
        self._last_external_file_path: str = ""
        self._last_external_file_msec: int = 0
        self.preferred_audio_language = self.DEFAULT_AUDIO_LANGUAGE
        self._pending_audio_language_apply = False
        self.subtitle_enabled = False
        self.preferred_subtitle_language = self.DEFAULT_AUDIO_LANGUAGE
        self._pending_subtitle_apply = False
        # play_at() ごとに採番し、優先トラック適用の遅延 callback が古い動画のものか
        # 判定するための世代番号。切替直後に前動画のタイマーが新動画の pending を
        # 確定させてしまう事故を防ぐ。
        self._track_apply_generation = 0
        # 右クリックコンテキストメニューの二重表示を抑制するためのデバウンス用。
        self._last_context_menu_msec = 0

        # タイマー
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._update_status_time)
        self.timer.start(200)
        self._diagnostics_heartbeat_timer = diagnostics.start_heartbeat_timer(self)

        # シーク状態
        self._seeking_user: bool = False
        self._media_length: int = -1
        self._ending: bool = False
        self._last_long_seek_msec_by_key: dict[int, int] = {}
        self._file_operation_in_progress: bool = False
        self._status_priority_until_msec: int = 0

        # 初期音量
        self.vlc_player.audio_set_volume(
            int(self.volume_slider.value()),
            context="initial_audio_set_volume",
        )
        self._muted: bool = False
        m = self.vlc_player.audio_get_mute()
        if m in (0, 1):
            self._muted = m == 1
        self._update_volume_label()
        self.vlc_player.set_rate(self.playback_rate, context="initial_set_rate")

        # ショートカット
        self._setup_shortcuts()

        # 設定の復元（レイアウト構築・初期化後）
        self._load_settings()

        # 起動時にファイルが渡された場合、そのファイルをロードする
        if file:
            diagnostics.record_breadcrumb("initial_file", path=file)
            self._load_file_and_directory(file)
            self._remember_external_file(file)

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        self.view = build_player_view(self)
        self.btn_open.clicked.connect(self.open_files_dialog)
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_prev.clicked.connect(self.play_previous)
        self.btn_next.clicked.connect(self.play_next)
        self.btn_repeat.toggled.connect(self._on_repeat_toggled)
        self.btn_shuffle.toggled.connect(self._on_shuffle_toggled)
        self.seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)
        self.seek_slider.sliderMoved.connect(self._on_slider_moved)
        self.seek_slider.clickedValue.connect(self._on_slider_clicked)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.volume_slider.clickedValue.connect(self._on_volume_clicked)
        self.video_frame.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.video_frame.customContextMenuRequested.connect(self._show_video_context_menu)

        self._apply_control_icons()

        self._build_menus()

        # ドロップ
        self.setAcceptDrops(True)

    def _build_menus(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("ファイル")
        act_open = file_menu.addAction("開く...")
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self.open_files_dialog)
        act_copy_filename = file_menu.addAction("現在のファイル名をコピー")
        act_copy_filename.setShortcut("Ctrl+C")
        act_copy_filename.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        act_copy_filename.triggered.connect(self.copy_current_filename_to_clipboard)
        file_menu.addSeparator()
        file_menu.addAction("_ok フォルダへ移動して次を再生").triggered.connect(
            lambda: self._move_current_file_and_play_next("_ok")
        )
        file_menu.addAction("_ng フォルダへ移動して次を再生").triggered.connect(
            lambda: self._move_current_file_and_play_next("_ng")
        )
        file_menu.addSeparator()
        file_menu.addAction("終了").triggered.connect(self.close)

        playback_menu = menu_bar.addMenu("再生")
        playback_menu.addAction("再生 / 一時停止").triggered.connect(self.toggle_play)
        playback_menu.addAction("停止").triggered.connect(self.stop)
        playback_menu.addSeparator()
        playback_menu.addAction("前の動画へ").triggered.connect(self.play_previous)
        playback_menu.addAction("次の動画へ").triggered.connect(self.play_next)
        playback_menu.addSeparator()
        playback_menu.addAction("10秒戻る").triggered.connect(
            lambda: self.seek_by(-self.SEEK_SHORT_MS)
        )
        playback_menu.addAction("10秒進む").triggered.connect(
            lambda: self.seek_by(self.SEEK_SHORT_MS)
        )
        playback_menu.addSeparator()
        playback_menu.addAction("1コマ戻る").triggered.connect(lambda: self.step_frame(-1))
        playback_menu.addAction("1コマ進む").triggered.connect(lambda: self.step_frame(1))
        playback_menu.addSeparator()
        playback_menu.addAction("再生速度を下げる").triggered.connect(
            lambda: self._change_playback_rate(-0.1)
        )
        playback_menu.addAction("再生速度を上げる").triggered.connect(
            lambda: self._change_playback_rate(+0.1)
        )
        playback_menu.addSeparator()
        self.act_repeat = playback_menu.addAction("リピート再生")
        self.act_repeat.setCheckable(True)
        self.act_repeat.triggered.connect(lambda _checked=False: self.btn_repeat.toggle())
        self.act_shuffle = playback_menu.addAction("シャッフル再生")
        self.act_shuffle.setCheckable(True)
        self.act_shuffle.triggered.connect(lambda _checked=False: self.btn_shuffle.toggle())
        playback_menu.aboutToShow.connect(self._sync_playback_menu_state)

        self.audio_menu = menu_bar.addMenu("音声")
        self.audio_menu.aboutToShow.connect(self._rebuild_audio_menu)

        self.subtitle_menu = menu_bar.addMenu("字幕")
        self.subtitle_menu.aboutToShow.connect(self._rebuild_subtitle_menu)

        view_menu = menu_bar.addMenu("表示")
        view_menu.addAction("最大化").triggered.connect(self.showMaximized)

        tools_menu = menu_bar.addMenu("ツール")
        tools_menu.addAction("メディア情報").triggered.connect(self._show_metadata_dialog)

        help_menu = menu_bar.addMenu("ヘルプ")
        act_shortcuts = help_menu.addAction("ショートカット一覧")
        act_shortcuts.setShortcut("F1")
        act_shortcuts.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        act_shortcuts.triggered.connect(self._show_shortcut_list_dialog)

    def _sync_playback_menu_state(self) -> None:
        self.act_repeat.setChecked(self.repeat_enabled)
        self.act_shuffle.setChecked(self.shuffle_enabled)

    def _apply_control_icons(self) -> None:
        apply_control_icons(self)

    def nativeEvent(self, event_type, message):  # noqa: N802
        # ネイティブ VLC 子ウィンドウ上の右クリックは Qt の QContextMenuEvent として
        # video_frame に届かないことがあるため、WM_CONTEXTMENU を直接拾う。Qt 側の
        # CustomContextMenu signal と二重に発火し得るので、_show_video_context_menu()
        # 側のデバウンスで一方だけがメニューを開くようにしている。
        if sys.platform.startswith("win") and self._is_windows_context_menu_event(message):
            global_pos = QtGui.QCursor.pos()
            local_pos = self.video_frame.mapFromGlobal(global_pos)
            if self.video_frame.rect().contains(local_pos):
                self._show_video_context_menu(local_pos)
                return True, 0
        return super().nativeEvent(event_type, message)

    def _is_windows_context_menu_event(self, message) -> bool:
        try:
            from ctypes import wintypes

            msg = wintypes.MSG.from_address(int(message))
            return msg.message == 0x007B  # WM_CONTEXTMENU
        except Exception:
            return False

    # タイトルバーのダーク化（Windows）
    def showEvent(self, event: QtGui.QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._apply_windows_dark_titlebar()

    def _apply_windows_dark_titlebar(self) -> None:
        apply_windows_dark_titlebar(int(self.winId()))

    def _load_file_and_directory(self, file_path: str):
        """指定されたファイルを開き、そのディレクトリ内の動画ファイルをリストアップする"""
        diagnostics.record_breadcrumb("load_file_and_directory", path=file_path)
        if not os.path.isfile(file_path):
            return

        directory = os.path.dirname(file_path)
        log_message(f"ディレクトリを走査します: {directory}")

        try:
            video_files = collect_video_files(directory)
        except OSError as e:
            log_message(f"ディレクトリの走査に失敗しました: {e}")
            self._show_status_message(f"ディレクトリのスキャンに失敗しました: {e}", 5000)
            return

        if not video_files:
            log_message("ディレクトリに動画ファイルがありません。")
            # 動画が1つも見つからない場合でも、指定されたファイルだけは再生する
            video_files = [file_path]

        self.directory_playlist = video_files

        if self.shuffle_enabled:
            # シャッフルが有効な状態で新しいディレクトリを開いたら、一度無効にする
            self.shuffle_enabled = False
            self.shuffled_playlist = []
            self._update_shuffle_button()

        # 渡されたファイルがリストの何番目にあるかを探す
        try:
            # パスを正規化して比較
            normalized_path = os.path.normpath(file_path)
            normalized_playlist = [os.path.normpath(p) for p in self.directory_playlist]
            self.current_index = normalized_playlist.index(normalized_path)
        except ValueError:
            # 万が一見つからない場合は、最初のファイルを再生
            log_message(f"走査結果に '{file_path}' がないため、先頭の動画を選択します。")
            self.current_index = 0

        # 再生開始
        self.play_at(self.current_index)

    def open_external_file(self, file_path: str) -> None:
        """別プロセスから渡されたファイルを既存ウィンドウで開く。"""
        diagnostics.record_breadcrumb("open_external_file", path=file_path)
        self._bring_to_front()

        if not file_path:
            return

        if not os.path.isfile(file_path):
            log_message(f"ファイルが存在しないため外部からの要求を無視します: {file_path}")
            self._show_status_message(f"ファイルが見つかりません: {file_path}", 5000)
            return

        normalized = self._normalize_external_file_path(file_path)
        now = QtCore.QDateTime.currentMSecsSinceEpoch()
        if (
            normalized == self._last_external_file_path
            and now - self._last_external_file_msec < 3000
        ):
            log_message(f"重複した外部からの要求を無視します: {file_path}")
            self._show_status_message("同じファイルの連続起動を無視しました", 2500)
            return

        self._load_file_and_directory(file_path)
        self._remember_external_file(file_path)

    def _remember_external_file(self, file_path: str) -> None:
        self._last_external_file_path = self._normalize_external_file_path(file_path)
        self._last_external_file_msec = QtCore.QDateTime.currentMSecsSinceEpoch()

    def _normalize_external_file_path(self, file_path: str) -> str:
        return os.path.normcase(os.path.abspath(os.path.normpath(file_path)))

    def _bring_to_front(self) -> None:
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    # --------------- 設定保存/復元 ---------------
    def _load_settings(self) -> None:
        settings = self.settings_store.load()
        vol = settings.volume
        if vol != int(self.volume_slider.value()):
            self.volume_slider.setValue(vol)

        # ミュート状態は保存しない（常に起動時はミュートOFF）
        self._muted = False
        self.vlc_player.audio_set_mute(False, context="load_settings_audio_set_mute")
        self._update_volume_label()

        # ウィンドウ配置
        geom = settings.geometry
        if isinstance(geom, QtCore.QByteArray):
            self.restoreGeometry(geom)
        if settings.maximized:
            self.setWindowState(self.windowState() | QtCore.Qt.WindowMaximized)
        # リピート状態（デフォルトOFF）
        repeat = settings.repeat_enabled
        self.btn_repeat.setChecked(repeat)
        self.repeat_enabled = repeat
        self._update_repeat_button()

        self.preferred_audio_language = self._normalize_audio_language(
            settings.preferred_audio_language
        )
        self.subtitle_enabled = settings.subtitle_enabled
        self.preferred_subtitle_language = self._normalize_audio_language(
            settings.preferred_subtitle_language
        )

    def _save_settings(self) -> None:
        def _save() -> None:
            current = self.settings_store.load()
            self.settings_store.save(
                PlayerSettings(
                    volume=int(self.volume_slider.value()),
                    geometry=self.saveGeometry(),
                    maximized=self.isMaximized(),
                    repeat_enabled=bool(self.repeat_enabled),
                    preferred_audio_language=self.preferred_audio_language,
                    subtitle_enabled=bool(self.subtitle_enabled),
                    preferred_subtitle_language=self.preferred_subtitle_language,
                    last_directory=current.last_directory,
                )
            )

        diagnostics.run_safely("save_settings", _save)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        self._save_settings()
        super().closeEvent(event)

    # --------------- VLC ---------------
    def _next_vlc_generation(self) -> int:
        self._vlc_generation += 1
        return self._vlc_generation

    def _attach_vlc_events(self, generation: int) -> None:
        em = self.player.event_manager()
        em.event_attach(
            vlc.EventType.MediaPlayerEndReached,
            lambda event, gen=generation: self._on_vlc_end_for_generation(event, gen),
        )
        em.event_attach(
            vlc.EventType.MediaPlayerPlaying,
            lambda event, gen=generation: self._on_vlc_playing_for_generation(event, gen),
        )
        if not self._vlc_events_signal_connected:
            self.vlc_events.media_ended.connect(self._on_media_end)
            self.vlc_events.media_playing.connect(self._on_media_playing)
            self._vlc_events_signal_connected = True

    def _create_fresh_vlc_player(self) -> None:
        """現在の VLC player を破棄し、新しい player/adapter に差し替える。"""
        self.vlc_instance = _create_vlc_instance()
        self.player = self.vlc_instance.media_player_new()
        self.vlc_player = VlcPlayerAdapter(self.player)
        self._bind_video_surface()
        self._attach_vlc_events(self._next_vlc_generation())
        # stop タイムアウト後も、ユーザーが設定した再生状態を引き継ぐ。特に
        # ミュートを復元せずに次の動画を再生すると意図しない音声出力になる。
        self.vlc_player.audio_set_volume(
            int(self.volume_slider.value()),
            context="fresh_player_audio_set_volume",
        )
        self.vlc_player.audio_set_mute(
            bool(self._muted),
            context="fresh_player_audio_set_mute",
        )
        self.vlc_player.set_rate(
            self.playback_rate,
            context="fresh_player_set_rate",
        )

    def _on_vlc_end_for_generation(self, event, generation: int) -> None:
        if generation != self._vlc_generation:
            log_message(
                f"Ignoring stale VLC EndReached event: "
                f"generation={generation}, current={self._vlc_generation}"
            )
            return
        self._on_vlc_end(event)

    def _on_vlc_end(self, event) -> None:
        log_message(f"_on_vlc_end(): VLC EndReached fired, current_index={self.current_index}")
        self.vlc_events.media_ended.emit()

    def _on_vlc_playing_for_generation(self, event, generation: int) -> None:
        # VLC スレッドから呼ばれるため、Qt/VLC 操作はメインスレッドへ marshal する。
        if generation != self._vlc_generation:
            return
        self.vlc_events.media_playing.emit()

    def _on_media_playing(self) -> None:
        # 入力が有効化（Playing 到達）した時点で、現在の世代の pending を適用する。
        self._apply_preferred_tracks_if_pending(self._track_apply_generation)

    def _on_media_end(self) -> None:
        log_message(
            f"_on_media_end(): ENTER, "
            f"_ending={getattr(self, '_ending', False)}, "
            f"current_index={self.current_index}, "
            f"dir_len={len(self.directory_playlist)}, "
            f"plist_len={len(self._get_current_playlist())}"
        )

        # 再生切替中なら無視
        if getattr(self, "_is_changing_media", False):
            log_message("_on_media_end(): ignored because _is_changing_media")
            return
        if getattr(self, "_file_operation_in_progress", False):
            log_message("_on_media_end(): ignored because file operation is in progress")
            return

        playlist = self._get_current_playlist()
        if not playlist:
            log_message("_on_media_end(): empty playlist")
            return

        # index が変になってないか一応チェック
        if not (0 <= self.current_index < len(self.directory_playlist)):
            log_message(f"_on_media_end(): current_index out of range: {self.current_index}")
            return

        # ============================
        # ★ 単曲リピート（repeat_enabled=True）の処理
        # ============================
        if self.repeat_enabled:
            path = self.directory_playlist[self.current_index]
            log_message(
                f"_on_media_end(): repeat_enabled=True -> reload same media "
                f"index={self.current_index}, path={path}"
            )

            def _restart_current() -> None:
                if (
                    self._vlc_stop_in_progress
                    or self._is_changing_media
                    or self._file_operation_in_progress
                ):
                    log_message("_restart_current(): ignored during VLC/file transition")
                    diagnostics.record_breadcrumb("restart_current_ignored_during_transition")
                    return
                if not self.repeat_enabled or self._current_file_path() != path:
                    log_message("_restart_current(): ignored because repeat target changed")
                    diagnostics.record_breadcrumb(
                        "restart_current_ignored_stale_target",
                        scheduled_path=path,
                        current_path=self._current_file_path(),
                    )
                    return
                try:
                    # VLC の状態をログしておくと後で分析しやすい
                    try:
                        state_before = self.vlc_player.get_state()
                        t_before = self.vlc_player.get_time()
                    except Exception:
                        state_before = None
                        t_before = None
                    log_message(
                        f"_restart_current(): BEFORE reload state={state_before}, time={t_before}"
                    )

                    # ★ 同じパスでメディアを作り直す（stop は呼ばない）
                    media = self.vlc_instance.media_new(path)
                    media.parse()
                    if not self.vlc_player.set_media(
                        media,
                        context="restart_current_set_media",
                        path=path,
                    ):
                        return
                    self.vlc_player.play(context="restart_current_play", path=path)

                    # シークバー状態を軽くリセットしておく
                    self._media_length = -1
                    self.seek_slider.blockSignals(True)
                    self.seek_slider.setEnabled(True)
                    self.seek_slider.setRange(0, 0)
                    self.seek_slider.setValue(0)
                    self.seek_slider.blockSignals(False)

                    try:
                        state_after = self.vlc_player.get_state()
                        t_after = self.vlc_player.get_time()
                    except Exception:
                        state_after = None
                        t_after = None
                    log_message(
                        f"_restart_current(): AFTER reload state={state_after}, time={t_after}"
                    )

                except Exception as e:
                    log_message(f"_restart_current(): error: {e!r}")

            QtCore.QTimer.singleShot(80, _restart_current)
            return

        # ============================
        # ★ 通常モード（repeat_enabled=False）：次のファイルへ
        # ============================

        if getattr(self, "_ending", False):
            log_message("_on_media_end(): ignored because _ending already True")
            return
        self._ending = True

        try:
            next_original_idx = self.playlist_session.adjacent(1)
        except Exception as e:
            log_message(f"_on_media_end(): adjacent_index error: {e}")
            self._ending = False
            return

        if next_original_idx is not None:
            next_track_path = self.directory_playlist[next_original_idx]
            log_message(
                "_on_media_end(): moving to next track "
                f"idx={next_original_idx}, path={next_track_path}"
            )
            # _ending は _end_after が実行されるまで True のまま保持し、
            # その間に届く重複 EndReached イベントを抑制する
            QtCore.QTimer.singleShot(80, lambda idx=next_original_idx: self._end_after(idx))
        else:
            log_message("_on_media_end(): reached end of playlist (repeat off) -> stop()")
            self._ending = False
            self.stop()

    def _end_after(self, idx: int) -> None:
        log_message(f"_end_after(): idx={idx}, current_index(before)={self.current_index}")
        try:
            self._play_at_with_reason(idx, "from_end")
        finally:
            self._ending = False

    def _bind_video_surface(self) -> None:
        wid = int(self.video_frame.winId())
        if sys.platform.startswith("win"):
            self.player.set_hwnd(wid)
        elif sys.platform == "darwin":
            self.player.set_nsobject(wid)  # type: ignore[attr-defined]
        else:
            self.player.set_xwindow(wid)  # type: ignore[attr-defined]

    # ------------- プレイリスト -------------

    def play_at(self, index: int) -> None:
        diagnostics.record_breadcrumb("play_at_requested", index=index)

        if self._vlc_stop_in_progress:
            log_message(f"play_at(): SKIP index={index} because VLC stop is in progress")
            diagnostics.record_breadcrumb("play_at_ignored_during_vlc_stop", index=index)
            return

        if not (0 <= index < len(self.directory_playlist)):
            log_message("play_at(): indexが範囲外です")
            return

        if getattr(self, "_is_changing_media", False):
            log_message(f"play_at(): SKIP index={index} because _is_changing_media is True")
            return
        self._is_changing_media = True

        try:
            old = self.current_index
            log_message(f"play_at(): START index={index}, old_index={old}")
            self.current_index = index
            path = self.directory_playlist[index]
            log_message(f"play_at(): path={path}")
            diagnostics.record_breadcrumb("play_at_start", index=index, old_index=old, path=path)

            log_message("play_at(): before non-blocking player.stop()")
            diagnostics.record_breadcrumb("play_at_before_player_stop", path=path)
            stopped = self._stop_and_clear_media_without_blocking_ui(context="play_at_player_stop")
            if stopped is None:
                # processEvents() 中の再入。現在の player は外側の stop が使用中なので
                # media の設定や再生へ進んではならない。
                self.current_index = old
                log_message("play_at(): aborted because another VLC stop is in progress")
                diagnostics.record_breadcrumb("play_at_aborted_during_vlc_stop", index=index)
                return
            if stopped:
                log_message("play_at(): after non-blocking player.stop()")
                diagnostics.record_breadcrumb("play_at_after_player_stop", path=path)
            else:
                # タイムアウト時は helper が fresh player に差し替えている。古い
                # player の停止完了を待たず、新しい player で再生を継続できる。
                log_message("play_at(): player.stop() timed out; continuing with fresh player")
                diagnostics.record_breadcrumb("play_at_player_stop_timeout", path=path)

            try:
                log_message("play_at(): before media_new/parse")
                diagnostics.record_breadcrumb("play_at_before_media_new", path=path)
                media = self.vlc_instance.media_new(path)
                diagnostics.record_breadcrumb("play_at_after_media_new", path=path)
                diagnostics.record_breadcrumb("play_at_before_media_parse", path=path)
                media.parse()  # ← ここで固まるか確認したい
                log_message("play_at(): after media.parse()")
                diagnostics.record_breadcrumb("play_at_after_media_parse", path=path)
                diagnostics.record_breadcrumb("play_at_before_set_media", path=path)
                if not self.vlc_player.set_media(media, context="play_at_set_media", path=path):
                    return
                diagnostics.record_breadcrumb("play_at_after_set_media", path=path)
            except Exception as e:
                log_message(f"play_at(): media setup error: {e}")
                diagnostics.record_breadcrumb("play_at_media_setup_error", error=str(e))
                return

            self._bind_video_surface()

            self.vlc_player.set_rate(self.playback_rate, context="play_at_set_rate", path=path)

            diagnostics.record_breadcrumb("play_at_before_player_play", path=path)
            self.vlc_player.play(context="play_at_player_play", path=path)
            self._schedule_preferred_track_apply()
            diagnostics.record_breadcrumb("play_at_after_player_play", path=path)
            log_message(
                f"play_at(): player.play() done, current_index={self.current_index}, path={path}"
            )
            self._update_window_title(os.path.basename(path))
            # 優先メッセージ（移動完了など）の表示中は上書きしない。
            # 期限が切れれば _update_status_time が再生時間表示へ引き継ぐ。
            now_msec = QtCore.QDateTime.currentMSecsSinceEpoch()
            if now_msec >= self._status_priority_until_msec:
                self.status.showMessage(f"再生中: {path}")

            # 新しい動画を再生する際に、シークバーの色を通常に戻す
            if self._is_seek_bar_warning:
                self.seek_slider.setStyleSheet(self.SEEK_SLIDER_STYLE_NORMAL)
                self._is_seek_bar_warning = False

            self._media_length = -1
            self.seek_slider.blockSignals(True)
            self.seek_slider.setEnabled(True)
            self.seek_slider.setRange(0, 0)
            self.seek_slider.setValue(0)
            self.seek_slider.blockSignals(False)
            log_message("play_at(): end")
        finally:
            self._is_changing_media = False

    # ------------- 音声トラック -------------
    def _show_video_context_menu(self, pos: QtCore.QPoint) -> None:
        # 右クリック1回で Qt の CustomContextMenu signal とネイティブ WM_CONTEXTMENU の
        # 両経路が発火し得る。短時間の重複呼び出しは無視し、メニューが二重に開かないようにする。
        now_msec = QtCore.QDateTime.currentMSecsSinceEpoch()
        if now_msec - self._last_context_menu_msec < 250:
            return
        self._last_context_menu_msec = now_msec

        menu = QtWidgets.QMenu(self)
        menu.addAction("再生 / 一時停止").triggered.connect(self.toggle_play)
        menu.addAction("停止").triggered.connect(self.stop)
        menu.addSeparator()
        audio_menu = menu.addMenu("音声トラック")
        self._populate_audio_track_menu(audio_menu)
        subtitle_menu = menu.addMenu("字幕")
        self._populate_subtitle_track_menu(subtitle_menu)
        menu.exec_(self.video_frame.mapToGlobal(pos))

    def _get_current_playlist(self) -> list[str]:
        """現在の再生モードに応じたプレイリストを返すヘルパーメソッド"""
        return self.playlist_session.active_paths()

    def play_next(self) -> None:
        diagnostics.record_breadcrumb("play_next_requested")
        playlist = self._get_current_playlist()
        log_message(
            f"play_next(): current_index={self.current_index}, playlist_len={len(playlist)}"
        )
        next_original_idx = self.playlist_session.adjacent(1)
        if next_original_idx is None:
            return
        current_path = self.directory_playlist[self.current_index]
        log_message(f"play_next(): current_path={current_path}")
        QtCore.QTimer.singleShot(
            50, lambda: self._play_at_with_reason(next_original_idx, "from_next")
        )
        log_message(f"play_next(): scheduling play_at({next_original_idx}) in 50ms")

    def _play_at_with_reason(self, index: int, reason: str) -> None:
        log_message(f"_play_at_with_reason(): index={index}, reason={reason}")
        diagnostics.record_breadcrumb("play_at_with_reason", index=index, reason=reason)
        self.play_at(index)

    def play_previous(self) -> None:
        diagnostics.record_breadcrumb("play_previous_requested")
        prev_original_idx = self.playlist_session.adjacent(-1)
        if prev_original_idx is None:
            return
        QtCore.QTimer.singleShot(50, lambda: self.play_at(prev_original_idx))

    # ------------- 再生操作 -------------
    def toggle_play(self) -> None:
        """再生/一時停止を切り替える。停止状態からの再開も考慮する。"""
        player_state = self.vlc_player.get_state()
        has_media = self.vlc_player.get_media() is not None
        diagnostics.record_breadcrumb(
            "toggle_play",
            player_state=str(player_state),
            has_media=has_media,
        )

        # プレイヤーが完全に停止・終了している場合、または stop タイムアウトで
        # fresh player に差し替わりメディアが空の場合は、現在動画を読み直す。
        if not has_media or player_state in (vlc.State.Stopped, vlc.State.Ended, vlc.State.Error):
            # 再生可能なファイルがプレイリストにあれば、現在のファイルを最初から再生する
            if 0 <= self.current_index < len(self.directory_playlist):
                self.play_at(self.current_index)
        # 再生中または一時停止中の場合
        elif self.vlc_player.is_playing():
            self.vlc_player.pause(context="toggle_play_pause")
        else:
            self.vlc_player.play(context="toggle_play_play")

        self._update_play_button()

    def stop(self) -> None:
        diagnostics.record_breadcrumb("stop_requested")
        stopped = self._stop_and_clear_media_without_blocking_ui(
            context="stop_player_stop",
            clear_media=False,
        )
        if stopped is None:
            log_message("stop(): VLCの停止処理中のため要求を無視します")
            return
        if not stopped:
            log_message("stop(): VLC停止がタイムアウトしたため、新しいプレイヤーへ交換しました")
        self._apply_stopped_ui_state()

    def _apply_stopped_ui_state(self) -> None:
        """再生停止に伴うUI（オーバーレイ・シークバー・再生ボタン）の更新。"""
        self.overlay.hide()
        # 停止時にシークバーの色を通常に戻す
        if self._is_seek_bar_warning:
            self.seek_slider.setStyleSheet(self.SEEK_SLIDER_STYLE_NORMAL)
            self._is_seek_bar_warning = False

        self.seek_slider.blockSignals(True)
        self.seek_slider.setEnabled(False)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setValue(0)
        self.seek_slider.blockSignals(False)
        self._update_play_button()

    def seek_by(self, delta_ms: int) -> None:
        diagnostics.record_breadcrumb("seek_by", delta_ms=delta_ms)
        try:
            t = self.vlc_player.get_time()
            length = self.vlc_player.get_length()
            if t == -1 or length <= 0:
                return

            new_t = max(0, t + delta_ms)

            # ★ 前方向のシークは、動画終端10秒前より先には行かない
            if delta_ms > 0 and length > 0:
                # 動画終了10秒前（ミリ秒）
                end_threshold = max(0, length - 10_000)
                if new_t > end_threshold:
                    new_t = end_threshold

            if length > 0:
                new_t = max(min(new_t, length - 1000), 0)
            self.vlc_player.set_time(new_t, context="seek_by_set_time", delta_ms=delta_ms)
            percent = int(round(new_t / length * 100)) if length > 0 else 0
            self._show_overlay(f"[{self._format_ms(new_t)} ({percent}%)]")
        except Exception as e:
            diagnostics.record_exception("seek_by", e, delta_ms=delta_ms)

    def _frame_step_ms(self) -> int:
        fps = self.vlc_player.get_fps()
        if fps > 0:
            return max(1, int(round(1000 / fps)))
        return self.FRAME_STEP_FALLBACK_MS

    def step_frame(self, direction: int) -> None:
        diagnostics.record_breadcrumb("step_frame", direction=direction)
        try:
            t = self.vlc_player.get_time()
            length = self.vlc_player.get_length()
            if t == -1 or length <= 0:
                return

            step_ms = self._frame_step_ms()
            delta_ms = step_ms if direction > 0 else -step_ms
            new_t = max(0, min(t + delta_ms, length - 1))
            self.vlc_player.set_time(
                new_t,
                context="step_frame_set_time",
                direction=direction,
                step_ms=step_ms,
            )
            percent = int(round(new_t / length * 100)) if length > 0 else 0
            self._show_overlay(f"[{self._format_ms(new_t)} ({percent}%)]")
        except Exception as e:
            diagnostics.record_exception("step_frame", e, direction=direction)

    def _should_ignore_long_seek_key(self, key: int) -> bool:
        # 長押し中のオートリピートも受け付ける(矢印キーと挙動を揃える)。連続入力が
        # 速すぎないよう、キーごとに最小間隔でスロットリングするだけに留める。
        now = QtCore.QDateTime.currentMSecsSinceEpoch()
        last = self._last_long_seek_msec_by_key.get(key, 0)
        if now - last < 150:
            return True

        self._last_long_seek_msec_by_key[key] = now
        return False

    def _should_ignore_long_seek(self, event: QtGui.QKeyEvent) -> bool:
        return self._should_ignore_long_seek_key(int(event.key()))

    def _long_seek_forward(self) -> None:
        # Ctrl+→: 60秒進む(QShortcut から呼ばれる。フォーカス位置に依存しない)
        if self._should_ignore_long_seek_key(int(QtCore.Qt.Key_Right)):
            return
        self.seek_by(self.SEEK_LONG_MS)

    def _long_seek_backward(self) -> None:
        # Ctrl+←: 60秒戻る
        if self._should_ignore_long_seek_key(int(QtCore.Qt.Key_Left)):
            return
        self.seek_by(-self.SEEK_LONG_MS)

    # ------------- キー操作 -------------
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        mods = event.modifiers()
        is_keypad = bool(mods & QtCore.Qt.KeypadModifier)

        if is_keypad and key == QtCore.Qt.Key_4:
            # Num4: 60秒進む
            if self._should_ignore_long_seek(event):
                event.accept()
                return
            self.seek_by(self.SEEK_LONG_MS)
            event.accept()
            return
        if is_keypad and key == QtCore.Qt.Key_1:
            # Num1: 60秒戻る
            if self._should_ignore_long_seek(event):
                event.accept()
                return
            self.seek_by(-self.SEEK_LONG_MS)
            event.accept()
            return

        # if key == QtCore.Qt.Key_PageUp:
        #     self.play_previous()
        #     event.accept()
        #     return
        # if key == QtCore.Qt.Key_PageDown:
        #     self.play_next()
        #     event.accept()
        #     return

        if is_keypad and key == QtCore.Qt.Key_8:
            self.close()
            event.accept()
            return

        if is_keypad and key == QtCore.Qt.Key_0:
            # Num0 は常に最大化
            self.showMaximized()
            event.accept()
            return

        super().keyPressEvent(event)

    # ------------- グローバルショートカット -------------
    def _setup_shortcuts(self) -> None:
        bind_shortcuts(self, SHORTCUT_ROWS)

    def _current_file_path(self) -> str:
        if 0 <= self.current_index < len(self.directory_playlist):
            return self.directory_playlist[self.current_index]
        return ""

    def copy_current_filename_to_clipboard(self) -> None:
        """現在再生中のファイル名だけをクリップボードにコピーする"""
        current_path = self._current_file_path()
        if not current_path:
            self._show_status_message("再生中のファイルがありません", 3000)
            return

        filename = os.path.basename(current_path)
        QtWidgets.QApplication.clipboard().setText(filename)
        self._show_status_message(f"ファイル名をコピーしました: {filename}", 3000)
        self._show_overlay("[ファイル名をコピー]")

    def _show_shortcut_list_dialog(self) -> None:
        dialog = ShortcutListDialog(self._shortcut_rows, self)
        dialog.exec_()

    # ------------- D&D -------------
    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        files = [u.toLocalFile() for u in urls if u.isLocalFile()]
        if files:
            self._load_file_and_directory(files[0])
            event.acceptProposedAction()

    def _format_ms(self, ms: int) -> str:
        """ミリ秒を MM:SS または HH:MM:SS 形式の文字列に変換する"""
        return format_ms(ms)

    def _show_overlay(self, text: str, duration_ms: int = 1500) -> None:
        """オーバーレイラベルにテキストを表示し、一定時間後に非表示にする。

        オーバーレイは最前面固定の別ウィンドウのため、wagom-player が前面にいない
        ときに表示すると Chrome などの上に被ってしまう。プレイヤーが実際に見えている
        ときだけ表示する。
        """
        if not self._is_overlay_display_allowed():
            return
        self.overlay.show(text, duration_ms)

    def _is_overlay_display_allowed(self) -> bool:
        """オーバーレイを表示してよい状態か(プレイヤーが前面に見えているか)を返す。"""
        return self.isActiveWindow() and not self.isMinimized()

    def changeEvent(self, event: QtCore.QEvent) -> None:  # noqa: N802
        """非アクティブ化・最小化したら、最前面オーバーレイを隠して他アプリへの被りを防ぐ。"""
        super().changeEvent(event)
        if event.type() in (
            QtCore.QEvent.ActivationChange,
            QtCore.QEvent.WindowStateChange,
        ):
            if not self._is_overlay_display_allowed():
                self.overlay.hide()

    def _show_status_message(self, msg: str, timeout_ms: int) -> None:
        """タイムアウト付きステータスメッセージを表示し、その間タイマーの上書きを抑制する"""
        self._status_priority_until_msec = QtCore.QDateTime.currentMSecsSinceEpoch() + timeout_ms
        self.status.showMessage(msg, timeout_ms)

    # ------------- ステータス更新 -------------
    def _update_status_time(self) -> None:
        if self._vlc_stop_in_progress:
            diagnostics.heartbeat()
            return
        if not self.player:
            self._update_diagnostics_snapshot()
            return
        cur = self.vlc_player.get_time()
        total = self.vlc_player.get_length()

        if cur >= 0 and total > 0:
            now_msec = QtCore.QDateTime.currentMSecsSinceEpoch()
            if now_msec >= self._status_priority_until_msec:
                self.status.showMessage(f"{self._format_ms(cur)} / {self._format_ms(total)}")
            if total != self._media_length:
                self._media_length = total
                self.seek_slider.blockSignals(True)
                self.seek_slider.setEnabled(True)
                self.seek_slider.setRange(0, total)
                self.seek_slider.blockSignals(False)
                self._update_window_title()
                formatted_time = self._format_ms(total)
                self._show_overlay(formatted_time)

            if not self._seeking_user:
                self.seek_slider.blockSignals(True)
                self.seek_slider.setValue(cur)
                self.seek_slider.blockSignals(False)

            is_near_end = cur > total - 12_000  # 10秒だと判定が微妙なので12秒に余裕を持たせる
            if is_near_end and not self._is_seek_bar_warning:
                # 黄色に変更
                self.seek_slider.setStyleSheet(self.SEEK_SLIDER_STYLE_WARNING)
                self._is_seek_bar_warning = True
            elif not is_near_end and self._is_seek_bar_warning:
                # 青色に戻す
                self.seek_slider.setStyleSheet(self.SEEK_SLIDER_STYLE_NORMAL)
                self._is_seek_bar_warning = False
        # 再生ボタン表示
        self._update_play_button()
        self._update_diagnostics_snapshot()

    def _update_diagnostics_snapshot(self) -> None:
        if self._vlc_stop_in_progress:
            return
        current_path = self._current_file_path()
        try:
            player_state = str(self.vlc_player.get_state("")) if self.player else ""
        except Exception as e:
            player_state = f"error: {e!r}"
        try:
            player_time = self.vlc_player.get_time() if self.player else -1
        except Exception:
            player_time = -1
        try:
            player_length = self.vlc_player.get_length() if self.player else -1
        except Exception:
            player_length = -1
        try:
            player_rate = (
                self.vlc_player.get_rate(self.playback_rate) if self.player else self.playback_rate
            )
        except Exception:
            player_rate = self.playback_rate
        try:
            playing = self.vlc_player.is_playing() if self.player else False
        except Exception:
            playing = False
        try:
            vlc_version = vlc.libvlc_get_version().decode("utf-8", errors="ignore")
        except Exception:
            vlc_version = ""

        diagnostics.update_state_snapshot(
            current_file=current_path,
            current_index=self.current_index,
            playlist_len=len(self.directory_playlist),
            current_playlist_len=len(self._get_current_playlist()),
            shuffle_enabled=self.shuffle_enabled,
            repeat_enabled=self.repeat_enabled,
            is_changing_media=getattr(self, "_is_changing_media", False),
            is_file_operation_in_progress=getattr(self, "_file_operation_in_progress", False),
            is_ending=getattr(self, "_ending", False),
            is_seeking_user=getattr(self, "_seeking_user", False),
            player_state=player_state,
            player_time=player_time,
            player_length=player_length,
            player_rate=player_rate,
            playing=playing,
            media_length=self._media_length,
            window_title=self.windowTitle(),
            vlc_version=vlc_version,
        )

    def _update_window_title(self, filename: Optional[str] = None) -> None:
        current_path = (
            self.directory_playlist[self.current_index]
            if 0 <= self.current_index < len(self.directory_playlist)
            else ""
        )
        self.setWindowTitle(
            build_window_title(
                playlist=self._get_current_playlist(),
                current_path=current_path,
                shuffle_enabled=self.shuffle_enabled,
                media_length_ms=self._media_length,
                filename=filename,
                file_size_bytes=self._current_file_size_bytes(current_path),
            )
        )

    def _current_file_size_bytes(self, current_path: str) -> int:
        """現在のファイルサイズ(バイト)を返す。取得できない場合は -1。"""
        if not current_path:
            return -1
        try:
            return os.path.getsize(current_path)
        except OSError:
            return -1

    def _update_play_button(self) -> None:
        try:
            playing = self.vlc_player.is_playing()
        except Exception:
            playing = False
        if (
            getattr(self, "_last_playing_state", None) is None
            or self._last_playing_state != playing
        ):
            self.btn_play.setIcon(self._icon_pause if playing else self._icon_play)
            self.btn_play.setToolTip("一時停止" if playing else "再生")
            self._last_playing_state = playing

    # ------------- シークバー操作 -------------
    def _on_seek_pressed(self) -> None:
        diagnostics.record_breadcrumb("seek_pressed")
        self._seeking_user = True

    def _on_seek_released(self) -> None:
        self._seeking_user = False
        val = self.seek_slider.value()
        diagnostics.record_breadcrumb("seek_released", value=val)
        self.vlc_player.set_time(val, context="seek_released_set_time")

    def _on_slider_moved(self, value: int) -> None:
        diagnostics.record_breadcrumb("slider_moved", value=value)
        total = self._media_length if self._media_length > 0 else self.vlc_player.get_length()

        if total > 0:
            self.status.showMessage(f"{self._format_ms(value)} / {self._format_ms(total)}")

    def _on_slider_clicked(self, value: int) -> None:
        diagnostics.record_breadcrumb("slider_clicked", value=value)
        self.vlc_player.set_time(value, context="slider_clicked_set_time")

    # ------------- 再生速度操作 -------------
    def _change_playback_rate(self, delta: float) -> None:
        new_rate = max(
            self.playback_rate_min, min(self.playback_rate_max, self.playback_rate + delta)
        )
        if not self.vlc_player.set_rate(new_rate, context="change_playback_rate_set_rate"):
            self._show_status_message("再生速度の変更に失敗しました", 3000)
            return
        self.playback_rate = new_rate
        diagnostics.record_breadcrumb("change_playback_rate", rate=new_rate)
        self._show_overlay(f"[再生速度:{new_rate:.1f}倍]")

    # ------------- 音量操作 -------------
    def _on_volume_changed(self, value: int) -> None:
        diagnostics.record_breadcrumb("volume_changed", value=int(value))
        self.vlc_player.audio_set_volume(
            int(value),
            context="volume_changed_audio_set_volume",
        )
        self._update_volume_label()
        self._show_overlay(f"[ボリューム:{int(value)}%]")

    def _adjust_volume(self, delta: int) -> None:
        diagnostics.record_breadcrumb("adjust_volume", delta=delta)
        v = int(self.volume_slider.value())
        nv = max(0, min(100, v + delta))
        if nv != v:
            self.volume_slider.setValue(nv)
        else:
            self._show_overlay(f"[ボリューム:{nv}%]")

    def _on_volume_clicked(self, value: int) -> None:
        # クリック位置を即時反映（valueChangedで反映される）
        pass

    def _update_volume_label(self) -> None:
        v = int(self.volume_slider.value())
        self.volume_label.setText(f"音量: {v}%")
        # アイコン切り替え
        icon = self._icon_mute if self._muted else self._icon_volume
        if hasattr(self, "volume_icon"):
            self.volume_icon.setPixmap(icon.pixmap(18, 18))

    def _on_repeat_toggled(self, checked: bool) -> None:
        self.repeat_enabled = bool(checked)
        self._update_repeat_button()

    def _update_repeat_button(self) -> None:
        self.btn_repeat.setIcon(
            self._icon_repeat_on if self.repeat_enabled else self._icon_repeat_off
        )
        # 押下状態の視覚フィードバック
        self.btn_repeat.setChecked(self.repeat_enabled)

    def _on_shuffle_toggled(self, checked: bool) -> None:
        self.shuffle_enabled = bool(checked)
        self._create_or_clear_shuffled_playlist()
        self._update_shuffle_button()
        self._update_window_title()

    def _create_or_clear_shuffled_playlist(self):
        """シャッフルリストを作成またはクリアする"""
        import random

        if self.shuffle_enabled and self.directory_playlist:
            log_message("シャッフルを有効にし、再生順を作成します。")
            self.playlist_session.set_shuffle(True, random.shuffle)
        else:
            log_message("シャッフルを無効にします。")
            self.playlist_session.set_shuffle(False, random.shuffle)

    # _toggle_shuffleから_update_shuffle_buttonに名前を変更したものを流用
    def _update_shuffle_button(self):
        self.btn_shuffle.setIcon(
            self._icon_shuffle_on if self.shuffle_enabled else self._icon_shuffle_off
        )
        self.btn_shuffle.setChecked(self.shuffle_enabled)

    def _toggle_mute(self) -> None:
        next_muted = not self._muted
        diagnostics.record_breadcrumb("toggle_mute", muted=next_muted)
        if self.vlc_player.audio_toggle_mute(context="toggle_mute_audio_toggle_mute"):
            actual_muted = self.vlc_player.audio_get_mute()
            self._muted = actual_muted == 1 if actual_muted in (0, 1) else next_muted
        else:
            self._show_status_message("ミュート切替に失敗しました", 3000)
        self._update_volume_label()

    # ------------- ファイルダイアログ -------------
    def open_files_dialog(self) -> None:
        diagnostics.record_breadcrumb("open_files_dialog")
        start_dir = self.settings_store.load().last_directory or os.path.expanduser("~")
        supported_patterns = " ".join(f"*{ext}" for ext in SUPPORTED_VIDEO_EXTENSIONS)
        file_filter = f"動画ファイル ({supported_patterns});;すべてのファイル (*.*)"
        file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "動画ファイルを選択",
            start_dir,
            file_filter,
        )
        if file:
            diagnostics.record_breadcrumb("open_files_dialog_selected", path=file)
            try:
                self.settings_store.set_value("last_dir", os.path.dirname(file))
            except Exception as e:
                diagnostics.record_exception("open_files_dialog_save_last_dir", e, path=file)
            self._load_file_and_directory(file)

    # ------------- ファイル移動と次の動画再生 -------------
    def _update_overlay_geometry(self):
        """
        オーバーレイウィンドウの位置とサイズを、video_frameに正確に合わせる。
        VLCウィンドウのグローバル座標を計算して追従させる。
        """
        self.overlay.update_geometry()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        """ウィンドウのリサイズに合わせてオーバーレイラベルのサイズを調整する"""
        super().resizeEvent(event)
        # video_frameの現在の大きさにラベルをぴったり合わせる
        self.overlay.resize_to_frame_rect()

    def moveEvent(self, event: QtGui.QMoveEvent) -> None:
        """メインウィンドウの移動に合わせてオーバーレイの位置を更新する"""
        super().moveEvent(event)
        # 表示されている場合のみ、位置を更新する
        if self.duration_overlay_label.isVisible():
            self._update_overlay_geometry()

    def _show_metadata_dialog(self):
        """現在再生中の動画のメタデータを抽出し、ダイアログで表示する"""
        diagnostics.record_breadcrumb("show_metadata_dialog")
        # 再生中でなければ何もしない
        if not (0 <= self.current_index < len(self.directory_playlist)):
            self._show_status_message("再生中のファイルがありません", 3000)
            return

        media = self.player.get_media()
        if not media:
            return

        # --- メタデータの収集 ---
        metadata_lines = []

        # 1. 基本情報
        file_path = self.directory_playlist[self.current_index]
        metadata_lines.append(f"ファイルパス: {file_path}")

        duration_ms = media.get_duration()
        if duration_ms > 0:
            metadata_lines.append(f"長さ: {self._format_ms(duration_ms)} ({duration_ms} ms)")

        metadata_lines.append("-" * 20)

        # 2. VLCから取得できるメタデータ
        # 取得したいメタデータの種類を定義
        # 表示したいメタデータの種類を、表示名とvlc.Meta enumのマッピングで定義
        meta_fields = {
            # --- 基本情報 ---
            "Title": vlc.Meta.Title,
            "Artist": vlc.Meta.Artist,
            "Album": vlc.Meta.Album,
            "Album Artist": vlc.Meta.AlbumArtist,
            "Genre": vlc.Meta.Genre,
            "Date": vlc.Meta.Date,
            "Description": vlc.Meta.Description,
            # --- トラック/ディスク情報 ---
            "Track Number": vlc.Meta.TrackNumber,
            "Track Total": vlc.Meta.TrackTotal,
            "Disc Number": vlc.Meta.DiscNumber,
            "Disc Total": vlc.Meta.DiscTotal,
            "Track ID": vlc.Meta.TrackID,
            # --- TV/映画情報 ---
            "Show Name": vlc.Meta.ShowName,
            "Season": vlc.Meta.Season,
            "Episode": vlc.Meta.Episode,
            "Director": vlc.Meta.Director,
            "Actors": vlc.Meta.Actors,
            # --- その他 ---
            "Rating": vlc.Meta.Rating,
            "Language": vlc.Meta.Language,
            "Copyright": vlc.Meta.Copyright,
            "Publisher": vlc.Meta.Publisher,
            "Encoded By": vlc.Meta.EncodedBy,
            "Setting": vlc.Meta.Setting,
            "URL": vlc.Meta.URL,
            "Artwork URL": vlc.Meta.ArtworkURL,
            "Now Playing": vlc.Meta.NowPlaying,
        }

        for name, field_enum in meta_fields.items():
            # media.get_meta() は値がなければ None を返す
            value = media.get_meta(field_enum)

            # valueがNoneなら空文字列に変換し、そうでなければそのままの値を使う
            # これにより、値がなくても "項目名: " という行が必ず追加される
            display_value = value or ""

            metadata_lines.append(f"{name}: {display_value}")

        # --- ダイアログの表示 ---
        final_text = "\n".join(metadata_lines)

        # 作成したMetadataDialogクラスのインスタンスを生成して表示
        dialog = MetadataDialog(final_text, self)
        dialog.exec_()  # モーダルダイアログとして表示
