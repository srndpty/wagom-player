from typing import Any

from PyQt5 import QtCore, QtGui, QtWidgets

from ..seek_slider import SeekSlider
from ..theme import resource_path
from ..ui_styles import VOLUME_SLIDER_STYLE


def build_player_view(window: Any) -> None:
    central = QtWidgets.QWidget(window)
    window.setCentralWidget(central)

    layout = QtWidgets.QVBoxLayout(central)

    window.video_frame = QtWidgets.QFrame(window)
    window.video_frame.setFrameShape(QtWidgets.QFrame.NoFrame)
    window.video_frame.setStyleSheet("background: #000;")
    layout.addWidget(window.video_frame, 1)

    window.seek_slider = SeekSlider(QtCore.Qt.Horizontal, window)
    window.seek_slider.setMinimumHeight(22)
    window.seek_slider.setRange(0, 0)
    window.seek_slider.setEnabled(False)
    layout.addWidget(window.seek_slider)

    controls = QtWidgets.QHBoxLayout()
    layout.addLayout(controls)

    window.btn_open = QtWidgets.QPushButton()
    window.btn_play = QtWidgets.QPushButton()
    window.btn_stop = QtWidgets.QPushButton()
    window.btn_prev = QtWidgets.QPushButton()
    window.btn_next = QtWidgets.QPushButton()
    window.btn_repeat = QtWidgets.QPushButton()
    window.btn_repeat.setCheckable(True)
    window.btn_shuffle = QtWidgets.QPushButton()
    window.btn_shuffle.setCheckable(True)

    for button in (
        window.btn_open,
        window.btn_play,
        window.btn_stop,
        window.btn_prev,
        window.btn_next,
        window.btn_repeat,
        window.btn_shuffle,
    ):
        controls.addWidget(button)
    controls.addStretch(1)

    window.volume_icon = QtWidgets.QLabel()
    window.volume_icon.setFixedSize(18, 18)
    window.volume_icon.setAlignment(QtCore.Qt.AlignCenter)
    window.volume_label = QtWidgets.QLabel("音量")
    window.volume_slider = SeekSlider(QtCore.Qt.Horizontal, window)
    window.volume_slider.setObjectName("VolumeSlider")
    window.volume_slider.setMinimumHeight(22)
    window.volume_slider.setRange(0, 100)
    window.volume_slider.setFixedWidth(140)
    window.volume_slider.setValue(80)
    controls.addWidget(window.volume_icon)
    controls.addWidget(window.volume_label)
    controls.addWidget(window.volume_slider)

    window.setStyleSheet(window.styleSheet() + VOLUME_SLIDER_STYLE)
    window.status = window.statusBar()
    window.status.showMessage("準備完了")


def apply_control_icons(window: Any) -> None:
    def style_button(button: QtWidgets.QPushButton, icon_path: str, tooltip: str) -> None:
        button.setIcon(QtGui.QIcon(icon_path))
        button.setToolTip(tooltip)
        button.setFixedSize(36, 28)
        button.setIconSize(QtCore.QSize(18, 18))

    style_button(window.btn_open, resource_path("resources", "icons", "open.svg"), "開く")
    style_button(window.btn_stop, resource_path("resources", "icons", "stop.svg"), "停止")
    style_button(window.btn_prev, resource_path("resources", "icons", "prev.svg"), "前へ")
    style_button(window.btn_next, resource_path("resources", "icons", "next.svg"), "次へ")

    window._icon_play = QtGui.QIcon(resource_path("resources", "icons", "play.svg"))
    window._icon_pause = QtGui.QIcon(resource_path("resources", "icons", "pause.svg"))
    window.btn_play.setFixedSize(36, 28)
    window.btn_play.setIconSize(QtCore.QSize(18, 18))
    window._last_playing_state = None
    window._update_play_button()

    window._icon_volume = QtGui.QIcon(resource_path("resources", "icons", "volume.svg"))
    window._icon_mute = QtGui.QIcon(resource_path("resources", "icons", "mute.svg"))
    window.volume_icon.setPixmap(window._icon_volume.pixmap(18, 18))

    window._icon_repeat_on = QtGui.QIcon(resource_path("resources", "icons", "repeat.svg"))
    window._icon_repeat_off = QtGui.QIcon(resource_path("resources", "icons", "repeat_off.svg"))
    window.btn_repeat.setFixedSize(36, 28)
    window.btn_repeat.setIconSize(QtCore.QSize(18, 18))
    window.btn_repeat.setToolTip("リピート再生")
    window.repeat_enabled = False
    window._update_repeat_button()

    window._icon_shuffle_on = QtGui.QIcon(resource_path("resources", "icons", "shuffle.svg"))
    window._icon_shuffle_off = QtGui.QIcon(resource_path("resources", "icons", "shuffle_off.svg"))
    window.btn_shuffle.setFixedSize(36, 28)
    window.btn_shuffle.setIconSize(QtCore.QSize(18, 18))
    window.btn_shuffle.setToolTip("シャッフル再生")
    window._update_shuffle_button()
