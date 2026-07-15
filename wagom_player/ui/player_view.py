from dataclasses import dataclass

from PyQt5 import QtCore, QtGui, QtWidgets

from .seek_slider import SeekSlider
from .styles import VOLUME_SLIDER_STYLE
from .theme import resource_path


@dataclass(frozen=True)
class PlayerView:
    video_frame: QtWidgets.QFrame
    seek_slider: SeekSlider
    btn_open: QtWidgets.QPushButton
    btn_play: QtWidgets.QPushButton
    btn_stop: QtWidgets.QPushButton
    btn_prev: QtWidgets.QPushButton
    btn_next: QtWidgets.QPushButton
    btn_repeat: QtWidgets.QPushButton
    btn_shuffle: QtWidgets.QPushButton
    volume_icon: QtWidgets.QLabel
    volume_label: QtWidgets.QLabel
    volume_slider: SeekSlider
    status: QtWidgets.QStatusBar


def build_player_view(window: QtWidgets.QMainWindow) -> PlayerView:
    central = QtWidgets.QWidget(window)
    window.setCentralWidget(central)
    layout = QtWidgets.QVBoxLayout(central)

    video_frame = QtWidgets.QFrame(window)
    video_frame.setFrameShape(QtWidgets.QFrame.NoFrame)
    video_frame.setStyleSheet("background: #000;")
    layout.addWidget(video_frame, 1)

    seek_slider = SeekSlider(QtCore.Qt.Horizontal, window)
    seek_slider.setMinimumHeight(22)
    seek_slider.setRange(0, 0)
    seek_slider.setEnabled(False)
    layout.addWidget(seek_slider)

    controls = QtWidgets.QHBoxLayout()
    layout.addLayout(controls)
    buttons = [QtWidgets.QPushButton() for _ in range(7)]
    btn_open, btn_play, btn_stop, btn_prev, btn_next, btn_repeat, btn_shuffle = buttons
    btn_repeat.setCheckable(True)
    btn_shuffle.setCheckable(True)
    for button in buttons:
        controls.addWidget(button)
    controls.addStretch(1)

    volume_icon = QtWidgets.QLabel()
    volume_icon.setFixedSize(18, 18)
    volume_icon.setAlignment(QtCore.Qt.AlignCenter)
    volume_label = QtWidgets.QLabel("音量")
    volume_slider = SeekSlider(QtCore.Qt.Horizontal, window)
    volume_slider.setObjectName("VolumeSlider")
    volume_slider.setMinimumHeight(22)
    volume_slider.setRange(0, 100)
    volume_slider.setFixedWidth(140)
    volume_slider.setValue(80)
    controls.addWidget(volume_icon)
    controls.addWidget(volume_label)
    controls.addWidget(volume_slider)

    window.setStyleSheet(window.styleSheet() + VOLUME_SLIDER_STYLE)
    status = window.statusBar()
    status.showMessage("準備完了")
    return PlayerView(
        video_frame,
        seek_slider,
        btn_open,
        btn_play,
        btn_stop,
        btn_prev,
        btn_next,
        btn_repeat,
        btn_shuffle,
        volume_icon,
        volume_label,
        volume_slider,
        status,
    )


def icon(path: str) -> QtGui.QIcon:
    return QtGui.QIcon(resource_path("resources", "icons", path))


def style_button(button: QtWidgets.QPushButton, icon_path: str, tooltip: str) -> None:
    button.setIcon(icon(icon_path))
    button.setToolTip(tooltip)
    button.setFixedSize(36, 28)
    button.setIconSize(QtCore.QSize(18, 18))


def apply_control_icons(window) -> None:
    """コントローラーが保持するボタンへ共通アイコンを設定する。"""
    style_button(window.btn_open, "open.svg", "開く")
    style_button(window.btn_stop, "stop.svg", "停止")
    style_button(window.btn_prev, "prev.svg", "前へ")
    style_button(window.btn_next, "next.svg", "次へ")
    window._icon_play = icon("play.svg")
    window._icon_pause = icon("pause.svg")
    window.btn_play.setFixedSize(36, 28)
    window.btn_play.setIconSize(QtCore.QSize(18, 18))
    window._last_playing_state = None
    window._update_play_button()
    window._icon_volume = icon("volume.svg")
    window._icon_mute = icon("mute.svg")
    window.volume_icon.setPixmap(window._icon_volume.pixmap(18, 18))
    window._icon_repeat_on = icon("repeat.svg")
    window._icon_repeat_off = icon("repeat_off.svg")
    window.btn_repeat.setFixedSize(36, 28)
    window.btn_repeat.setIconSize(QtCore.QSize(18, 18))
    window.btn_repeat.setToolTip("リピート再生")
    window.repeat_enabled = False
    window._update_repeat_button()
    window._icon_shuffle_on = icon("shuffle.svg")
    window._icon_shuffle_off = icon("shuffle_off.svg")
    window.btn_shuffle.setFixedSize(36, 28)
    window.btn_shuffle.setIconSize(QtCore.QSize(18, 18))
    window.btn_shuffle.setToolTip("シャッフル再生")
    window._update_shuffle_button()
