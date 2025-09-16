import os
import sys
import shutil
from typing import List, Optional

from PyQt5 import QtCore, QtGui, QtWidgets

from .seek_slider import SeekSlider
from .theme import resource_path
from .logger import log_message

try:
    import vlc
except ImportError as e:
    raise SystemExit(
        "python-vlc が見つかりません。`pip install python-vlc` を実行してください"
    ) from e


def _create_vlc_instance() -> "vlc.Instance":
    lib_path = os.environ.get("PYTHON_VLC_LIB_PATH")
    if lib_path and os.path.isdir(lib_path):
        return vlc.Instance([f"--plugin-path={lib_path}"])  # type: ignore[arg-type]
    return vlc.Instance()


class VlcEvents(QtCore.QObject):
    media_ended = QtCore.pyqtSignal()


class VideoPlayer(QtWidgets.QMainWindow):
    SEEK_SHORT_MS = 10_000
    SEEK_LONG_MS = 60_000

    def __init__(self, files: Optional[List[str]] = None):
        super().__init__()
        self.setWindowTitle("wagom-player")
        self.resize(960, 540)
        self.settings = QtCore.QSettings()

        # VLC
        self.vlc_instance = _create_vlc_instance()
        self.player: vlc.MediaPlayer = self.vlc_instance.media_player_new()
        self.vlc_events = VlcEvents()
        self._attach_vlc_events()

        # UI
        self._build_ui()

        # プレイリスト
        self.playlist: List[str] = []
        self.current_index: int = -1
        if files:
            self.add_to_playlist(files, play_first=True)

        # タイマー
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._update_status_time)
        self.timer.start(200)

        # シーク状態
        self._seeking_user: bool = False
        self._media_length: int = -1
        self._ending: bool = False

        # 初期音量
        try:
            self.player.audio_set_volume(int(self.volume_slider.value()))
        except Exception:
            pass
        self._muted: bool = False
        try:
            m = self.player.audio_get_mute()
            if m in (0, 1):
                self._muted = m == 1
        except Exception:
            pass
        self._update_volume_label()

        # ショートカット
        self._setup_shortcuts()

        # 設定の復元（レイアウト構築・初期化後）
        self._load_settings()

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)

        layout = QtWidgets.QVBoxLayout(central)

        # 映像
        self.video_frame = QtWidgets.QFrame(self)
        self.video_frame.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.video_frame.setStyleSheet("background: #000;")
        layout.addWidget(self.video_frame, 1)

        # シークバー
        self.seek_slider = SeekSlider(QtCore.Qt.Horizontal, self)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setEnabled(False)
        layout.addWidget(self.seek_slider)

        # コントロール
        ctrl = QtWidgets.QHBoxLayout()
        layout.addLayout(ctrl)

        self.btn_open = QtWidgets.QPushButton()
        self.btn_play = QtWidgets.QPushButton()
        self.btn_stop = QtWidgets.QPushButton()
        self.btn_prev = QtWidgets.QPushButton()
        self.btn_next = QtWidgets.QPushButton()
        self.btn_repeat = QtWidgets.QPushButton()
        self.btn_repeat.setCheckable(True)
        for b in (
            self.btn_open,
            self.btn_play,
            self.btn_stop,
            self.btn_prev,
            self.btn_next,
            self.btn_repeat,
        ):
            ctrl.addWidget(b)
        ctrl.addStretch(1)

        # 音量
        self.volume_icon = QtWidgets.QLabel()
        self.volume_icon.setFixedSize(18, 18)
        self.volume_icon.setAlignment(QtCore.Qt.AlignCenter)
        self.volume_label = QtWidgets.QLabel("音量")
        self.volume_slider = SeekSlider(QtCore.Qt.Horizontal, self)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setFixedWidth(140)
        self.volume_slider.setValue(80)
        ctrl.addWidget(self.volume_icon)
        ctrl.addWidget(self.volume_label)
        ctrl.addWidget(self.volume_slider)

        self.status = self.statusBar()
        self.status.showMessage("準備完了")

        # シグナル
        self.btn_open.clicked.connect(self.open_files_dialog)
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_prev.clicked.connect(self.play_previous)
        self.btn_next.clicked.connect(self.play_next)
        self.btn_repeat.toggled.connect(self._on_repeat_toggled)
        self.seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)
        self.seek_slider.sliderMoved.connect(self._on_slider_moved)
        self.seek_slider.clickedValue.connect(self._on_slider_clicked)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.volume_slider.clickedValue.connect(self._on_volume_clicked)

        # アイコン
        self._apply_control_icons()

        # メニュー
        menu = self.menuBar().addMenu("ファイル")
        act_open = menu.addAction("開く...")
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self.open_files_dialog)

        # ドロップ
        self.setAcceptDrops(True)

    def _apply_control_icons(self) -> None:
        def style_btn(btn: QtWidgets.QPushButton, icon_path: str, tip: str):
            btn.setIcon(QtGui.QIcon(icon_path))
            btn.setToolTip(tip)
            btn.setFixedSize(36, 28)
            btn.setIconSize(QtCore.QSize(18, 18))

        style_btn(
            self.btn_open, resource_path("resources", "icons", "open.svg"), "開く"
        )
        style_btn(
            self.btn_stop, resource_path("resources", "icons", "stop.svg"), "停止"
        )
        style_btn(
            self.btn_prev, resource_path("resources", "icons", "prev.svg"), "前へ"
        )
        style_btn(
            self.btn_next, resource_path("resources", "icons", "next.svg"), "次へ"
        )

        self._icon_play = QtGui.QIcon(resource_path("resources", "icons", "play.svg"))
        self._icon_pause = QtGui.QIcon(resource_path("resources", "icons", "pause.svg"))
        self.btn_play.setFixedSize(36, 28)
        self.btn_play.setIconSize(QtCore.QSize(18, 18))
        self._last_playing_state: Optional[bool] = None
        self._update_play_button()
        # 音量アイコン
        self._icon_volume = QtGui.QIcon(
            resource_path("resources", "icons", "volume.svg")
        )
        self._icon_mute = QtGui.QIcon(resource_path("resources", "icons", "mute.svg"))
        if hasattr(self, "volume_icon"):
            self.volume_icon.setPixmap((self._icon_volume).pixmap(18, 18))
        # リピートアイコン
        self._icon_repeat_on = QtGui.QIcon(
            resource_path("resources", "icons", "repeat.svg")
        )
        self._icon_repeat_off = QtGui.QIcon(
            resource_path("resources", "icons", "repeat_off.svg")
        )
        self.btn_repeat.setFixedSize(36, 28)
        self.btn_repeat.setIconSize(QtCore.QSize(18, 18))
        self.btn_repeat.setToolTip("リピート再生")
        self.repeat_enabled = False
        self._update_repeat_button()

    # タイトルバーのダーク化（Windows）
    def showEvent(self, event: QtGui.QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._apply_windows_dark_titlebar()

    def _apply_windows_dark_titlebar(self) -> None:
        if not sys.platform.startswith("win"):
            return
        try:
            import ctypes

            hwnd = int(self.winId())
            dwmapi = ctypes.windll.dwmapi
            value = ctypes.c_int(1)
            for attr in (20, 19):
                try:
                    dwmapi.DwmSetWindowAttribute(
                        ctypes.c_void_p(hwnd),
                        ctypes.c_int(attr),
                        ctypes.byref(value),
                        ctypes.sizeof(value),
                    )
                except Exception:
                    pass
        except Exception:
            pass

    # --------------- 設定保存/復元 ---------------
    def _load_settings(self) -> None:
        try:
            vol = int(self.settings.value("volume", 80))
        except Exception:
            vol = 80
        vol = max(0, min(100, vol))
        if vol != int(self.volume_slider.value()):
            self.volume_slider.setValue(vol)

        # ミュート状態は保存しない（常に起動時はミュートOFF）
        self._muted = False
        try:
            self.player.audio_set_mute(False)
        except Exception:
            pass
        self._update_volume_label()

        # ウィンドウ配置
        geom = self.settings.value("geometry")
        if isinstance(geom, QtCore.QByteArray):
            self.restoreGeometry(geom)
        is_max = bool(self.settings.value("isMaximized", False, type=bool))
        if is_max:
            self.setWindowState(self.windowState() | QtCore.Qt.WindowMaximized)
        # リピート状態（デフォルトOFF）
        repeat = bool(self.settings.value("repeat", False, type=bool))
        self.btn_repeat.setChecked(repeat)
        self.repeat_enabled = repeat
        self._update_repeat_button()

    def _save_settings(self) -> None:
        try:
            self.settings.setValue("volume", int(self.volume_slider.value()))
            self.settings.setValue("geometry", self.saveGeometry())
            self.settings.setValue("isMaximized", self.isMaximized())
            self.settings.setValue("repeat", bool(self.repeat_enabled))
        except Exception:
            pass

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        self._save_settings()
        super().closeEvent(event)

    # --------------- VLC ---------------
    def _attach_vlc_events(self) -> None:
        em = self.player.event_manager()
        em.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_vlc_end)
        self.vlc_events.media_ended.connect(self._on_media_end)

    def _on_vlc_end(self, event) -> None:
        self.vlc_events.media_ended.emit()

    def _on_media_end(self) -> None:
        # 単曲リピートを最優先。処理の重複を避けるため遅延して切替。
        if getattr(self, "_ending", False):
            return
        self._ending = True
        cur = self.current_index
        total = len(self.playlist)
        if self.repeat_enabled and 0 <= cur < total:
            QtCore.QTimer.singleShot(80, lambda idx=cur: self._end_after(idx))
            return
        if cur + 1 < total:
            QtCore.QTimer.singleShot(80, lambda idx=cur + 1: self._end_after(idx))
        else:
            self._ending = False
            self.stop()

    def _end_after(self, idx: int) -> None:
        self._ending = False
        self.play_at(idx)

    def _on_media_ended_in_qt(self) -> None:
        # 最後まで到達したらリピート設定に従う
        if self.current_index + 1 < len(self.playlist):
            self.play_next()
        elif self.repeat_enabled:
            QtCore.QTimer.singleShot(50, lambda: self.play_at(self.current_index))
        else:
            self.stop()

    def _bind_video_surface(self) -> None:
        wid = int(self.video_frame.winId())
        if sys.platform.startswith("win"):
            self.player.set_hwnd(wid)
        elif sys.platform == "darwin":
            self.player.set_nsobject(wid)  # type: ignore[attr-defined]
        else:
            self.player.set_xwindow(wid)  # type: ignore[attr-defined]

    # ------------- プレイリスト -------------
    def add_to_playlist(self, files: List[str], play_first: bool = False) -> None:
        added = [f for f in files if os.path.isfile(f)]
        if not added:
            return
        start_index = len(self.playlist)
        self.playlist.extend(added)
        # タイトルの総数表示を更新（再生中のトラックは維持）
        try:
            self._update_window_title()
        except Exception:
            pass
        if play_first:
            self.play_at(start_index)
        log_message(
            f"add_to_playlist called with {len(files)} files. play_first={play_first}"
        )

    def play_at(self, index: int) -> None:
        if not (0 <= index < len(self.playlist)):
            return
        self.current_index = index
        path = self.playlist[index]
        # 切替安定化のため一旦停止
        try:
            self.player.stop()
        except Exception:
            pass
        media = self.vlc_instance.media_new(path)
        self.player.set_media(media)

        QtWidgets.QApplication.processEvents()
        self._bind_video_surface()

        self.player.play()
        self._update_window_title(os.path.basename(path))
        self.status.showMessage(f"再生中: {path}")

        self._media_length = -1
        self.seek_slider.blockSignals(True)
        self.seek_slider.setEnabled(True)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setValue(0)
        self.seek_slider.blockSignals(False)

    def play_next(self) -> None:
        if not self.playlist:
            return
        if (self.current_index + 1) < len(self.playlist):
            QtCore.QTimer.singleShot(50, lambda: self.play_at(self.current_index + 1))

    def play_previous(self) -> None:
        if not self.playlist:
            return
        if (self.current_index - 1) >= 0:
            QtCore.QTimer.singleShot(50, lambda: self.play_at(self.current_index - 1))

    # ------------- 再生操作 -------------
    def toggle_play(self) -> None:
        """再生/一時停止を切り替える。停止状態からの再開も考慮する。"""
        player_state = self.player.get_state()

        # プレイヤーが完全に停止または終了している場合
        if player_state in (vlc.State.Stopped, vlc.State.Ended, vlc.State.Error):
            # 再生可能なファイルがプレイリストにあれば、現在のファイルを最初から再生する
            if 0 <= self.current_index < len(self.playlist):
                self.play_at(self.current_index)
        # 再生中または一時停止中の場合
        elif self.player.is_playing():
            self.player.pause()
        else:
            self.player.play()
        
        self._update_play_button()

    def stop(self) -> None:
        self.player.stop()
        self.seek_slider.blockSignals(True)
        self.seek_slider.setEnabled(False)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setValue(0)
        self.seek_slider.blockSignals(False)
        self._update_play_button()

    def seek_by(self, delta_ms: int) -> None:
        try:
            t = self.player.get_time()
            if t == -1:
                return
            new_t = max(0, t + delta_ms)
            length = self.player.get_length()
            if length > 0:
                new_t = min(new_t, length - 1000)
            self.player.set_time(new_t)
        except Exception:
            pass

    # ------------- キー操作 -------------
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        mods = event.modifiers()
        is_keypad = bool(mods & QtCore.Qt.KeypadModifier)

        if key == QtCore.Qt.Key_Left:
            self.seek_by(-self.SEEK_SHORT_MS)
            event.accept()
            return
        if key == QtCore.Qt.Key_Right:
            self.seek_by(self.SEEK_SHORT_MS)
            event.accept()
            return

        if is_keypad and key == QtCore.Qt.Key_4:
            # Num4: 60秒進む
            self.seek_by(self.SEEK_LONG_MS)
            event.accept()
            return
        if is_keypad and key == QtCore.Qt.Key_1:
            # Num1: 60秒戻る
            self.seek_by(-self.SEEK_LONG_MS)
            event.accept()
            return

        if key == QtCore.Qt.Key_PageUp:
            self.play_previous()
            event.accept()
            return
        if key == QtCore.Qt.Key_PageDown:
            self.play_next()
            event.accept()
            return

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
        def mk(key, handler):
            sc = QtWidgets.QShortcut(QtGui.QKeySequence(key), self)
            sc.setContext(QtCore.Qt.ApplicationShortcut)
            sc.activated.connect(handler)
            return sc

        self._sc_left = mk(
            QtCore.Qt.Key_Left, lambda: self.seek_by(-self.SEEK_SHORT_MS)
        )
        self._sc_right = mk(
            QtCore.Qt.Key_Right, lambda: self.seek_by(self.SEEK_SHORT_MS)
        )
        self._sc_up = mk(QtCore.Qt.Key_Up, lambda: self._adjust_volume(+10))
        self._sc_down = mk(QtCore.Qt.Key_Down, lambda: self._adjust_volume(-10))
        self._sc_mute = mk(QtCore.Qt.Key_M, self._toggle_mute)
        # Num 0（テンキー0）
        self._sc_num0 = QtWidgets.QShortcut(
            QtGui.QKeySequence(int(QtCore.Qt.Key_0 | QtCore.Qt.KeypadModifier)), self
        )
        self._sc_num0.setContext(QtCore.Qt.ApplicationShortcut)
        self._sc_num0.activated.connect(self.showMaximized)
        # 前/次動画
        self._sc_prev_track = mk(QtCore.Qt.Key_PageUp, self.play_previous)
        self._sc_next_track = mk(QtCore.Qt.Key_PageDown, self.play_next)
        # Rキーでリピート切替（任意）
        self._sc_repeat = mk(QtCore.Qt.Key_R, lambda: self.btn_repeat.toggle())
        # スペースキーで再生/一時停止
        self._sc_space = mk(QtCore.Qt.Key_Space, self.toggle_play)

        # Num 9: "_ok" フォルダに移動
        self._sc_move_ok = QtWidgets.QShortcut(
            QtGui.QKeySequence(int(QtCore.Qt.Key_9 | QtCore.Qt.KeypadModifier)), self
        )
        self._sc_move_ok.setContext(QtCore.Qt.ApplicationShortcut)
        self._sc_move_ok.activated.connect(
            lambda: self._move_current_file_and_play_next("_ok")
        )

        # Num 6: "_ng" フォルダに移動
        self._sc_move_ng = QtWidgets.QShortcut(
            QtGui.QKeySequence(int(QtCore.Qt.Key_6 | QtCore.Qt.KeypadModifier)), self
        )
        self._sc_move_ng.setContext(QtCore.Qt.ApplicationShortcut)
        self._sc_move_ng.activated.connect(
            lambda: self._move_current_file_and_play_next("_ng")
        )

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
            first = not self.playlist
            self.add_to_playlist(files, play_first=first)
            event.acceptProposedAction()

    # ------------- ステータス更新 -------------
    def _update_status_time(self) -> None:
        if not self.player:
            return
        cur = self.player.get_time()
        total = self.player.get_length()

        def f(ms: int) -> str:
            if ms <= 0:
                return "00:00"
            s = ms // 1000
            m, s = divmod(s, 60)
            h, m = divmod(m, 60)
            return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

        if cur >= 0 and total > 0:
            self.status.showMessage(f"{f(cur)} / {f(total)}")
            if total != self._media_length:
                self._media_length = total
                self.seek_slider.blockSignals(True)
                self.seek_slider.setEnabled(True)
                self.seek_slider.setRange(0, total)
                self.seek_slider.blockSignals(False)
            if not self._seeking_user:
                self.seek_slider.blockSignals(True)
                self.seek_slider.setValue(cur)
                self.seek_slider.blockSignals(False)
        # 再生ボタン表示
        self._update_play_button()

    def _update_window_title(self, filename: Optional[str] = None) -> None:
        name = filename or (
            os.path.basename(self.playlist[self.current_index])
            if 0 <= self.current_index < len(self.playlist)
            else ""
        )
        idx = (self.current_index + 1) if self.current_index >= 0 else 0
        total = len(self.playlist)
        prefix = f"[{idx}/{total}] " if total else ""
        self.setWindowTitle(f"wagom-player - {prefix}{name}")

    def _update_play_button(self) -> None:
        try:
            playing = bool(self.player.is_playing())
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
        self._seeking_user = True

    def _on_seek_released(self) -> None:
        self._seeking_user = False
        val = self.seek_slider.value()
        try:
            self.player.set_time(val)
        except Exception:
            pass

    def _on_slider_moved(self, value: int) -> None:
        total = (
            self._media_length if self._media_length > 0 else self.player.get_length()
        )

        def f(ms: int) -> str:
            if ms <= 0:
                return "00:00"
            s = ms // 1000
            m, s = divmod(s, 60)
            h, m = divmod(m, 60)
            return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

        if total > 0:
            self.status.showMessage(f"{f(value)} / {f(total)}")

    def _on_slider_clicked(self, value: int) -> None:
        try:
            self.player.set_time(value)
        except Exception:
            pass

    # ------------- 音量操作 -------------
    def _on_volume_changed(self, value: int) -> None:
        try:
            self.player.audio_set_volume(int(value))
        except Exception:
            pass
        self._update_volume_label()

    def _adjust_volume(self, delta: int) -> None:
        v = int(self.volume_slider.value())
        nv = max(0, min(100, v + delta))
        if nv != v:
            self.volume_slider.setValue(nv)

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

    def _toggle_mute(self) -> None:
        self._muted = not self._muted
        try:
            self.player.audio_toggle_mute()
        except Exception:
            pass
        self._update_volume_label()

    # ------------- ファイルダイアログ -------------
    def open_files_dialog(self) -> None:
        start_dir = self.settings.value("last_dir", os.path.expanduser("~"))
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "動画ファイルを選択",
            start_dir,
            "動画ファイル (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.ts *.m4v *.3gp *.3g2 *.mpeg *.mpg *.mpe *.rm *.rmvb *.vob *.webm);;すべてのファイル (*.*)",
        )
        if files:
            try:
                self.settings.setValue("last_dir", os.path.dirname(files[0]))
            except Exception:
                pass
            play_first = not self.playlist
            self.add_to_playlist(files, play_first=play_first)

    # ------------- ファイル移動と次の動画再生 -------------
    def _move_current_file_and_play_next(self, subfolder_name: str):
        """現在再生中のファイルを指定されたサブフォルダに移動し、次の曲を再生する"""
        # 再生中でない、またはプレイリストが空の場合は何もしない
        if not (0 <= self.current_index < len(self.playlist)):
            log_message("Move requested, but no file is playing.")
            return

        # --- 重要な情報を先に保存しておく ---
        index_to_remove = self.current_index
        current_file_path = self.playlist[index_to_remove]

        # ★★★★★ 修正の核心 ★★★★★
        # ファイル操作の前に、VLCプレイヤーを完全に停止してファイルロックを解放する
        log_message("Stopping playback to release file lock...")
        self.stop()

        # --- ファイルパスの準備 (停止後に行っても問題ない) ---
        file_name = os.path.basename(current_file_path)
        source_dir = os.path.dirname(current_file_path)

        target_dir = os.path.join(source_dir, subfolder_name)
        target_file_path = os.path.join(target_dir, file_name)

        log_message(f"Attempting to move '{file_name}' to '{subfolder_name}' folder.")

        # --- 移動処理 ---
        try:
            os.makedirs(target_dir, exist_ok=True)

            if os.path.exists(target_file_path):
                log_message(
                    f"File '{file_name}' already exists in target directory. Skipping move."
                )
                self.status.showMessage(
                    f"移動失敗: {file_name}は移動先に既に存在します", 5000
                )
                # ファイルが存在した場合、次の曲の再生は行わずに待機する
                return

            shutil.move(current_file_path, target_file_path)
            self.status.showMessage(f"移動完了: {file_name} -> {subfolder_name}", 4000)
            log_message(f"Successfully moved file to '{target_file_path}'")

        except Exception as e:
            log_message(f"Error moving file: {e}")
            self.status.showMessage(f"ファイル移動中にエラーが発生しました: {e}", 5000)
            # エラーが発生した場合も、次の曲の再生は行わずに待機する
            return

        # --- プレイリストの更新と次の曲の再生 ---

        # プレイリストから該当ファイルを削除
        self.playlist.pop(index_to_remove)

        # ウィンドウタイトルの表示を更新
        self._update_window_title()

        if not self.playlist:
            log_message("Playlist is now empty. Playback remains stopped.")
            self.stop()  # 念のため再度stopを呼び、UIを停止状態に保つ
        else:
            if index_to_remove >= len(self.playlist):
                log_message(
                    "Last item in playlist was moved. Playback remains stopped."
                )
                self.stop()  # 最後のアイテムを消した場合も停止状態を維持
            else:
                # 削除したアイテムの位置に次のアイテムが来たので、同じインデックスで再生を開始
                log_message(f"Playing next item at index {index_to_remove}.")
                # 少しディレイを入れると、UIの応答性が良くなることがある
                QtCore.QTimer.singleShot(50, lambda: self.play_at(index_to_remove))
