from __future__ import annotations

import os
from typing import Optional

from PyQt5 import QtCore, QtGui, QtWidgets

from .logger import log_message
from .playlist import PlaylistManager, is_supported_video
from .seek_slider import SeekSlider
from .sorting import windows_logical_key
from .time_utils import format_ms
from .vlc_client import VlcController


class VideoPlayer(QtWidgets.QMainWindow):
    """旧来の巨大なウィンドウ実装をリプレースした軽量版。"""

    def __init__(self, file: Optional[str] = None):
        super().__init__()
        self.setWindowTitle("wagom-player")
        self.resize(960, 540)

        self.playlist = PlaylistManager()
        self.vlc = VlcController(os.environ.get("PYTHON_VLC_LIB_PATH"))

        self._build_ui()
        self._connect_signals()

        if file and os.path.exists(file):
            self._open_initial_file(file)

    # UI構築
    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        self.video_frame = QtWidgets.QFrame()
        self.video_frame.setFrameShape(QtWidgets.QFrame.Box)

        self.play_button = QtWidgets.QPushButton("再生/一時停止")
        self.stop_button = QtWidgets.QPushButton("停止")
        self.prev_button = QtWidgets.QPushButton("◀")
        self.next_button = QtWidgets.QPushButton("▶")
        self.open_file_button = QtWidgets.QPushButton("ファイル")
        self.open_dir_button = QtWidgets.QPushButton("ディレクトリ")
        self.shuffle_button = QtWidgets.QPushButton("シャッフル:OFF")
        self.repeat_button = QtWidgets.QPushButton("リピート:OFF")
        self.speed_box = QtWidgets.QDoubleSpinBox()
        self.speed_box.setRange(0.25, 3.0)
        self.speed_box.setSingleStep(0.1)
        self.speed_box.setValue(1.0)

        self.seek_slider = SeekSlider(QtCore.Qt.Horizontal)
        self.seek_slider.setEnabled(False)
        self.seek_slider.setRange(0, 0)
        self.seek_label = QtWidgets.QLabel("00:00 / 00:00")

        self.playlist_view = QtWidgets.QListWidget()

        control_layout = QtWidgets.QGridLayout()
        control_layout.addWidget(self.open_file_button, 0, 0)
        control_layout.addWidget(self.open_dir_button, 0, 1)
        control_layout.addWidget(self.prev_button, 0, 2)
        control_layout.addWidget(self.play_button, 0, 3)
        control_layout.addWidget(self.next_button, 0, 4)
        control_layout.addWidget(self.stop_button, 0, 5)
        control_layout.addWidget(self.shuffle_button, 0, 6)
        control_layout.addWidget(self.repeat_button, 0, 7)
        control_layout.addWidget(QtWidgets.QLabel("速度"), 0, 8)
        control_layout.addWidget(self.speed_box, 0, 9)

        slider_layout = QtWidgets.QHBoxLayout()
        slider_layout.addWidget(self.seek_slider)
        slider_layout.addWidget(self.seek_label)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.video_frame)
        layout.addLayout(control_layout)
        layout.addLayout(slider_layout)
        layout.addWidget(self.playlist_view)

        central.setLayout(layout)

    def _connect_signals(self) -> None:
        self.open_file_button.clicked.connect(self.open_file)
        self.open_dir_button.clicked.connect(self.open_directory)
        self.play_button.clicked.connect(self.vlc.pause_or_play)
        self.stop_button.clicked.connect(self._stop)
        self.prev_button.clicked.connect(self.play_previous)
        self.next_button.clicked.connect(self.play_next)
        self.shuffle_button.clicked.connect(self.toggle_shuffle)
        self.repeat_button.clicked.connect(self.toggle_repeat)
        self.speed_box.valueChanged.connect(self.vlc.set_rate)
        self.playlist_view.itemDoubleClicked.connect(self._play_selected_item)
        self.seek_slider.sliderMoved.connect(self._seek)

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._update_position)
        self._timer.start()

    # ファイル操作
    def _open_initial_file(self, path: str) -> None:
        directory = os.path.dirname(os.path.abspath(path))
        files = [os.path.join(directory, f) for f in os.listdir(directory)]
        self.playlist.load(files, current=path)
        self._refresh_playlist_view()
        self._play_current()

    def open_file(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "動画ファイルを開く")
        if not path:
            return
        self.playlist.load([path], current=path)
        self._refresh_playlist_view()
        self._play_current()

    def open_directory(self) -> None:
        directory = QtWidgets.QFileDialog.getExistingDirectory(self, "ディレクトリを開く")
        if not directory:
            return
        files = [os.path.join(directory, f) for f in os.listdir(directory) if is_supported_video(os.path.join(directory, f))]
        files.sort(key=windows_logical_key)
        self.playlist.load(files, current=files[0] if files else None)
        self._refresh_playlist_view()
        self._play_current()

    # プレイリスト操作
    def _refresh_playlist_view(self) -> None:
        self.playlist_view.clear()
        for path in self.playlist.current_playlist:
            item = QtWidgets.QListWidgetItem(os.path.basename(path))
            item.setToolTip(path)
            self.playlist_view.addItem(item)
        self._update_position_label()

    def _play_selected_item(self) -> None:
        row = self.playlist_view.currentRow()
        if row < 0 or row >= len(self.playlist.current_playlist):
            return
        path = self.playlist.current_playlist[row]
        try:
            self.playlist.current_index = self.playlist.files.index(path)
        except ValueError:
            return
        self._play_current()

    def _play_current(self) -> None:
        if not self.playlist.current_path:
            return
        widget_id = int(self.video_frame.winId())
        self.vlc.set_widget(widget_id)
        self.vlc.play_file(self.playlist.current_path)
        self._update_position_label()
        self.statusBar().showMessage(self.playlist.current_path)

    def _stop(self) -> None:
        self.vlc.stop()
        self.seek_slider.setEnabled(False)
        self.seek_slider.setRange(0, 0)
        self.seek_label.setText("00:00 / 00:00")

    def play_next(self) -> None:
        idx = self.playlist.next_index()
        if idx is None:
            log_message("play_next(): end of playlist")
            return
        self.playlist.current_index = idx
        self._play_current()

    def play_previous(self) -> None:
        idx = self.playlist.previous_index()
        if idx is None:
            return
        self.playlist.current_index = idx
        self._play_current()

    def toggle_shuffle(self) -> None:
        self.playlist.set_shuffle(not self.playlist.shuffle_enabled)
        state = "ON" if self.playlist.shuffle_enabled else "OFF"
        self.shuffle_button.setText(f"シャッフル:{state}")
        self._refresh_playlist_view()

    def toggle_repeat(self) -> None:
        self.playlist.set_repeat(not self.playlist.repeat_enabled)
        state = "ON" if self.playlist.repeat_enabled else "OFF"
        self.repeat_button.setText(f"リピート:{state}")

    # 再生位置
    def _seek(self, value: int) -> None:
        self.vlc.set_time(value)

    def _update_position(self) -> None:
        length = self.vlc.get_length()
        if length <= 0:
            return
        pos = max(0, self.vlc.get_time())
        if not self.seek_slider.isEnabled():
            self.seek_slider.setEnabled(True)
            self.seek_slider.setRange(0, length)
        self.seek_slider.blockSignals(True)
        self.seek_slider.setValue(pos)
        self.seek_slider.blockSignals(False)
        self.seek_label.setText(f"{format_ms(pos)} / {format_ms(length)}")

        if pos >= max(0, length - 500):
            self._handle_media_end()

    def _handle_media_end(self) -> None:
        idx = self.playlist.next_index()
        if idx is None:
            self._stop()
            return
        self.playlist.current_index = idx
        self._play_current()

    def _update_position_label(self) -> None:
        self.statusBar().showMessage(self.playlist.describe())
