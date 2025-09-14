import os
import sys
from typing import List, Optional

from PyQt5 import QtCore, QtGui, QtWidgets

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


class VlcEvents(QtCore.QObject):
    media_ended = QtCore.pyqtSignal()


class SeekSlider(QtWidgets.QSlider):
    """クリック位置に即ジャンプするシークスライダ"""
    clickedValue = QtCore.pyqtSignal(int)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.LeftButton:
            if self.orientation() == QtCore.Qt.Horizontal:
                pos = event.pos().x()
                span = max(1, self.width())
            else:
                pos = self.height() - event.pos().y()
                span = max(1, self.height())
            rng = self.maximum() - self.minimum()
            val = self.minimum() + int(rng * pos / span)
            val = max(self.minimum(), min(self.maximum(), val))
            self.setValue(val)
            self.clickedValue.emit(val)
            event.accept()
            return
        super().mousePressEvent(event)


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

        self.btn_open = QtWidgets.QPushButton("開く")
        self.btn_play = QtWidgets.QPushButton("再生/一時停止")
        self.btn_stop = QtWidgets.QPushButton("停止")
        self.btn_prev = QtWidgets.QPushButton("前へ")
        self.btn_next = QtWidgets.QPushButton("次へ")
        for b in (self.btn_open, self.btn_play, self.btn_stop, self.btn_prev, self.btn_next):
            ctrl.addWidget(b)

        # 右寄せスペース
        ctrl.addStretch(1)

        # ボリュームバー
        self.volume_label = QtWidgets.QLabel("音量")
        self.volume_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
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

        # メニュー（簡易）
        menu = self.menuBar().addMenu("ファイル")
        act_open = menu.addAction("開く...")
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self.open_files_dialog)

        # ドロップ対応
        self.setAcceptDrops(True)

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

    def stop(self) -> None:
        self.player.stop()
        self.seek_slider.blockSignals(True)
        self.seek_slider.setEnabled(False)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setValue(0)
        self.seek_slider.blockSignals(False)

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
    files = [a for a in argv[1:] if os.path.exists(a)]
    w = VideoPlayer(files=files)
    w.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
