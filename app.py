import os
import sys
from typing import List, Optional

from PyQt5 import QtCore, QtGui, QtWidgets
try:
    # QtSvg をimportしておくとSVGアイコンの読み込みが安定します
    from PyQt5 import QtSvg  # noqa: F401
except Exception:
    QtSvg = None  # type: ignore

try:
    import vlc  # python-vlc
except ImportError as e:
    raise SystemExit("python-vlc が見つかりません。`pip install python-vlc` を実行してください") from e


def _create_vlc_instance() -> "vlc.Instance":
    lib_path = os.environ.get("PYTHON_VLC_LIB_PATH")
    if lib_path and os.path.isdir(lib_path):
        return vlc.Instance([f"--plugin-path={lib_path}"])  # type: ignore[arg-type]
    # 通常は自動検出に任せる
    return vlc.Instance()


def apply_dark_theme(app: QtWidgets.QApplication) -> None:
    """アプリ全体にダークテーマを適用する"""
    app.setStyle("Fusion")

    palette = QtGui.QPalette()
    base = QtGui.QColor(53, 53, 53)
    alt = QtGui.QColor(45, 45, 45)
    text = QtGui.QColor(220, 220, 220)
    hl = QtGui.QColor(0, 120, 215)  # Windowsアクセントに近いブルー

    palette.setColor(QtGui.QPalette.Window, base)
    palette.setColor(QtGui.QPalette.WindowText, text)
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor(35, 35, 35))
    palette.setColor(QtGui.QPalette.AlternateBase, alt)
    palette.setColor(QtGui.QPalette.ToolTipBase, alt)
    palette.setColor(QtGui.QPalette.ToolTipText, text)
    palette.setColor(QtGui.QPalette.Text, text)
    palette.setColor(QtGui.QPalette.Button, alt)
    palette.setColor(QtGui.QPalette.ButtonText, text)
    palette.setColor(QtGui.QPalette.BrightText, QtCore.Qt.red)
    palette.setColor(QtGui.QPalette.Link, hl)
    palette.setColor(QtGui.QPalette.Highlight, hl)
    palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(255, 255, 255))
    app.setPalette(palette)

    # 必要最低限のスタイル調整（シーク/音量スライダの視認性向上）
    app.setStyleSheet(
        """
        QToolTip { color: #e6e6e6; background: #2a2a2a; border: 1px solid #3f3f3f; }
        QSlider::groove:horizontal { background: #3a3a3a; height: 6px; border-radius: 3px; }
        QSlider::sub-page:horizontal { background: #0078d7; height: 6px; border-radius: 3px; }
        QSlider::add-page:horizontal { background: #2a2a2a; height: 6px; border-radius: 3px; }
        QSlider::handle:horizontal { background: #1e90ff; width: 14px; margin: -6px 0; border-radius: 7px; }
        QMenuBar { background: #2d2d2d; color: #e6e6e6; }
        QMenuBar::item:selected { background: #3a3a3a; }
        QMenu { background: #2d2d2d; color: #e6e6e6; }
        QMenu::item:selected { background: #3a3a3a; }
        QPushButton { background: #2d2d2d; color: #e6e6e6; border: 1px solid #3f3f3f; padding: 4px 10px; }
        QPushButton:hover { background: #353535; }
        QPushButton:pressed { background: #2a2a2a; }
        QLabel { color: #e6e6e6; }
        QStatusBar { background: #2d2d2d; color: #e6e6e6; }
        """
    )


def resource_path(*parts: str) -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)


class VlcEvents(QtCore.QObject):
    media_ended = QtCore.pyqtSignal()


class SeekSlider(QtWidgets.QSlider):
    """クリック位置ジャンプ + ドラッグ追従するスライダ"""
    clickedValue = QtCore.pyqtSignal(int)

    def _pos_to_value(self, event: QtGui.QMouseEvent) -> int:
        if self.orientation() == QtCore.Qt.Horizontal:
            pos = event.pos().x()
            span = max(1, self.width())
        else:
            pos = self.height() - event.pos().y()
            span = max(1, self.height())
        rng = self.maximum() - self.minimum()
        val = self.minimum() + int(rng * pos / span)
        return max(self.minimum(), min(self.maximum(), val))

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.LeftButton:
            val = self._pos_to_value(event)
            self.setSliderDown(True)
            self.setValue(val)
            try:
                self.sliderPressed.emit()
                self.sliderMoved.emit(val)
            except Exception:
                pass
            self.clickedValue.emit(val)
            event.accept(); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.buttons() & QtCore.Qt.LeftButton and self.isSliderDown():
            val = self._pos_to_value(event)
            if val != self.value():
                self.setValue(val)
                try:
                    self.sliderMoved.emit(val)
                except Exception:
                    pass
            event.accept(); return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.LeftButton and self.isSliderDown():
            self.setSliderDown(False)
            try:
                self.sliderReleased.emit()
            except Exception:
                pass
            event.accept(); return
        super().mouseReleaseEvent(event)


class VideoPlayer(QtWidgets.QMainWindow):
    SEEK_SHORT_MS = 10_000
    SEEK_LONG_MS = 60_000

    def __init__(self, files: Optional[List[str]] = None):
        super().__init__()
        self.setWindowTitle("wagom-player")
        self.resize(960, 540)

        # VLC
        self.vlc_instance = _create_vlc_instance()
        self.player: vlc.MediaPlayer = self.vlc_instance.media_player_new()
        self.vlc_events = VlcEvents()
        self._attach_vlc_events()

        # UI 構築
        self._build_ui()

        # プレイリスト
        self.playlist: List[str] = []
        self.current_index: int = -1
        if files:
            self.add_to_playlist(files, play_first=True)

        # タイマーで経過時間表示を更新
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._update_status_time)
        self.timer.start(200)

        # シーク状態
        self._seeking_user: bool = False
        self._media_length: int = -1

        # 初期音量をVLCへ反映
        try:
            self.player.audio_set_volume(int(self.volume_slider.value()))
        except Exception:
            pass
        # ミュート状態の初期化（VLCが-1を返す場合は False を既定）
        self._muted: bool = False
        try:
            m = self.player.audio_get_mute()
            if m in (0, 1):
                self._muted = (m == 1)
        except Exception:
            pass
        self._update_volume_label()

        # アプリ全体のショートカット
        self._setup_shortcuts()

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)

        layout = QtWidgets.QVBoxLayout(central)

        # 映像領域
        self.video_frame = QtWidgets.QFrame(self)
        self.video_frame.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.video_frame.setStyleSheet("background: #000;")
        layout.addWidget(self.video_frame, 1)

        # シークバー（クリック位置へジャンプ）
        self.seek_slider = SeekSlider(QtCore.Qt.Horizontal, self)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setEnabled(False)
        layout.addWidget(self.seek_slider)

        # コントロールバー
        ctrl = QtWidgets.QHBoxLayout()
        layout.addLayout(ctrl)

        self.btn_open = QtWidgets.QPushButton()
        self.btn_play = QtWidgets.QPushButton()
        self.btn_stop = QtWidgets.QPushButton()
        self.btn_prev = QtWidgets.QPushButton()
        self.btn_next = QtWidgets.QPushButton()
        for b in (self.btn_open, self.btn_play, self.btn_stop, self.btn_prev, self.btn_next):
            ctrl.addWidget(b)

        # 右寄せスペース
        ctrl.addStretch(1)

        # ボリュームバー
        self.volume_label = QtWidgets.QLabel("音量")
        self.volume_slider = SeekSlider(QtCore.Qt.Horizontal, self)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setFixedWidth(140)
        self.volume_slider.setValue(80)
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
        self.seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)
        self.seek_slider.sliderMoved.connect(self._on_slider_moved)
        self.seek_slider.clickedValue.connect(self._on_slider_clicked)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.volume_slider.clickedValue.connect(self._on_volume_clicked)

        # 記号アイコン設定
        self._apply_control_icons()

        # メニュー（簡易）
        menu = self.menuBar().addMenu("ファイル")
        act_open = menu.addAction("開く...")
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self.open_files_dialog)

        # ドロップ対応
        self.setAcceptDrops(True)

    def _apply_control_icons(self) -> None:
        # 記号（Unicode）を利用したシンプルなアイコン
        def style_btn(btn: QtWidgets.QPushButton, icon_path: str, tip: str):
            btn.setIcon(QtGui.QIcon(icon_path))
            btn.setToolTip(tip)
            btn.setFixedSize(36, 28)
            btn.setIconSize(QtCore.QSize(18, 18))

        style_btn(self.btn_open, resource_path("resources", "icons", "open.svg"), "開く")
        style_btn(self.btn_stop, resource_path("resources", "icons", "stop.svg"), "停止")
        style_btn(self.btn_prev, resource_path("resources", "icons", "prev.svg"), "前へ")
        style_btn(self.btn_next, resource_path("resources", "icons", "next.svg"), "次へ")

        # 再生/一時停止は状態に応じて更新（アイコン2種を保持）
        self._icon_play = QtGui.QIcon(resource_path("resources", "icons", "play.svg"))
        self._icon_pause = QtGui.QIcon(resource_path("resources", "icons", "pause.svg"))
        self.btn_play.setFixedSize(36, 28)
        self.btn_play.setIconSize(QtCore.QSize(18, 18))
        self._last_playing_state: Optional[bool] = None
        self._update_play_button()

    # --------------- VLC ---------------
    def _attach_vlc_events(self) -> None:
        em = self.player.event_manager()
        em.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_vlc_end)
        self.vlc_events.media_ended.connect(self._on_media_ended_in_qt)

    def _on_vlc_end(self, event) -> None:  # VLC側スレッド
        # Qtスレッドへシグナルで橋渡し
        self.vlc_events.media_ended.emit()

    def _on_media_ended_in_qt(self) -> None:
        self.play_next()

    def _bind_video_surface(self) -> None:
        # Windows: set_hwnd にネイティブハンドルを渡す
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
        if play_first:
            self.play_at(start_index)

    def play_at(self, index: int) -> None:
        if not (0 <= index < len(self.playlist)):
            return
        self.current_index = index
        path = self.playlist[index]
        media = self.vlc_instance.media_new(path)
        self.player.set_media(media)

        # ネイティブハンドルの確保を安定させる
        QtWidgets.QApplication.processEvents()
        self._bind_video_surface()

        self.player.play()
        self.setWindowTitle(f"wagom-player - {os.path.basename(path)}")
        self.status.showMessage(f"再生中: {path}")

        # シーク初期化
        self._media_length = -1
        self.seek_slider.blockSignals(True)
        self.seek_slider.setEnabled(True)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setValue(0)
        self.seek_slider.blockSignals(False)

    def play_next(self) -> None:
        if not self.playlist:
            return
        next_index = (self.current_index + 1) if (self.current_index + 1) < len(self.playlist) else 0
        self.play_at(next_index)

    def play_previous(self) -> None:
        if not self.playlist:
            return
        prev_index = (self.current_index - 1) if (self.current_index - 1) >= 0 else len(self.playlist) - 1
        self.play_at(prev_index)

    # ------------- 再生操作 -------------
    def toggle_play(self) -> None:
        if self.player.is_playing():
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

        if key == QtCore.Qt.Key_Space:
            self.toggle_play()
            event.accept(); return

        if key == QtCore.Qt.Key_Left:
            self.seek_by(-self.SEEK_SHORT_MS)
            event.accept(); return
        if key == QtCore.Qt.Key_Right:
            self.seek_by(self.SEEK_SHORT_MS)
            event.accept(); return

        if is_keypad and key == QtCore.Qt.Key_4:
            self.seek_by(-self.SEEK_LONG_MS)
            event.accept(); return
        if is_keypad and key == QtCore.Qt.Key_1:
            self.seek_by(self.SEEK_LONG_MS)
            event.accept(); return

        if key == QtCore.Qt.Key_PageUp:
            self.play_previous()
            event.accept(); return
        if key == QtCore.Qt.Key_PageDown:
            self.play_next()
            event.accept(); return

        if is_keypad and key == QtCore.Qt.Key_8:
            self.close()
            event.accept(); return

        if is_keypad and key == QtCore.Qt.Key_0:
            if self.isMaximized():
                self.showNormal()
            else:
                self.showMaximized()
            event.accept(); return

        super().keyPressEvent(event)

    # ------------- グローバルショートカット -------------
    def _setup_shortcuts(self) -> None:
        def mk(key, handler):
            sc = QtWidgets.QShortcut(QtGui.QKeySequence(key), self)
            sc.setContext(QtCore.Qt.ApplicationShortcut)
            sc.activated.connect(handler)
            return sc

        self._sc_left = mk(QtCore.Qt.Key_Left, lambda: self.seek_by(-self.SEEK_SHORT_MS))
        self._sc_right = mk(QtCore.Qt.Key_Right, lambda: self.seek_by(self.SEEK_SHORT_MS))
        self._sc_up = mk(QtCore.Qt.Key_Up, lambda: self._adjust_volume(+10))
        self._sc_down = mk(QtCore.Qt.Key_Down, lambda: self._adjust_volume(-10))
        self._sc_mute = mk(QtCore.Qt.Key_M, self._toggle_mute)

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
            # シークバー更新（ユーザー操作中は追従しない）
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
        # 再生ボタン（▶/⏸）の表示を更新
        self._update_play_button()

    def _update_play_button(self) -> None:
        try:
            playing = bool(self.player.is_playing())
        except Exception:
            playing = False
        if getattr(self, "_last_playing_state", None) is None or self._last_playing_state != playing:
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
        # スライダ移動中はステータス表示だけ更新
        total = self._media_length if self._media_length > 0 else self.player.get_length()
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
        # つまみ以外の地点クリックで即シーク
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
        # クリック位置を即時反映（valueChangedが発火するためここでは何もしない）
        pass

    def _update_volume_label(self) -> None:
        # UIはキャッシュされたミュート状態を信頼して即時反映
        v = int(self.volume_slider.value())
        text = f"音量: {v}%" + (" (ミュート)" if self._muted else "")
        self.volume_label.setText(text)

    def _toggle_mute(self) -> None:
        # VLCの戻りが遅延する場合があるため、まずキャッシュを反転して即時UI反映
        self._muted = not self._muted
        try:
            self.player.audio_toggle_mute()
        except Exception:
            pass
        self._update_volume_label()

    # ------------- ファイルダイアログ -------------
    def open_files_dialog(self) -> None:
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "動画ファイルを選択",
            os.path.expanduser("~"),
            "動画ファイル (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.ts *.m4v);;すべてのファイル (*.*)",
        )
        if files:
            play_first = not self.playlist
            self.add_to_playlist(files, play_first=play_first)


def main(argv: List[str]) -> int:
    app = QtWidgets.QApplication(argv)
    apply_dark_theme(app)
    files = [a for a in argv[1:] if os.path.exists(a)]
    w = VideoPlayer(files=files)
    w.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
