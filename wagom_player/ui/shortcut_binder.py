from collections.abc import Sequence
from typing import Any

from PyQt5 import QtCore, QtGui, QtWidgets


def bind_shortcuts(window: Any, shortcut_rows: Sequence[tuple[str, str, str]]) -> None:
    window._shortcut_rows = shortcut_rows

    def make_shortcut(key: int, handler: object) -> QtWidgets.QShortcut:
        shortcut = QtWidgets.QShortcut(QtGui.QKeySequence(key), window)
        shortcut.setContext(QtCore.Qt.ApplicationShortcut)
        shortcut.activated.connect(handler)  # type: ignore[arg-type]
        return shortcut

    window._sc_left = make_shortcut(
        QtCore.Qt.Key_Left,
        lambda: window.seek_by(-window.SEEK_SHORT_MS),
    )
    window._sc_right = make_shortcut(
        QtCore.Qt.Key_Right,
        lambda: window.seek_by(window.SEEK_SHORT_MS),
    )
    window._sc_frame_prev = make_shortcut(QtCore.Qt.Key_Comma, lambda: window.step_frame(-1))
    window._sc_frame_next = make_shortcut(QtCore.Qt.Key_Period, lambda: window.step_frame(1))
    window._sc_up = make_shortcut(QtCore.Qt.Key_Up, lambda: window._adjust_volume(+10))
    window._sc_down = make_shortcut(QtCore.Qt.Key_Down, lambda: window._adjust_volume(-10))
    window._sc_mute = make_shortcut(QtCore.Qt.Key_M, window._toggle_mute)
    window._sc_num0 = make_shortcut(
        int(QtCore.Qt.Key_0 | QtCore.Qt.KeypadModifier),
        window.showMaximized,
    )
    window._sc_prev_track = make_shortcut(QtCore.Qt.Key_PageUp, window.play_previous)
    window._sc_next_track = make_shortcut(QtCore.Qt.Key_PageDown, window.play_next)
    window._sc_repeat = make_shortcut(QtCore.Qt.Key_R, lambda: window.btn_repeat.toggle())
    window._sc_shuffle = make_shortcut(QtCore.Qt.Key_S, lambda: window.btn_shuffle.toggle())
    window._sc_space = make_shortcut(QtCore.Qt.Key_Space, window.toggle_play)
    window._sc_speed_up = make_shortcut(
        QtCore.Qt.Key_C,
        lambda: window._change_playback_rate(+0.1),
    )
    window._sc_speed_up.setAutoRepeat(True)
    window._sc_speed_down = make_shortcut(
        QtCore.Qt.Key_X,
        lambda: window._change_playback_rate(-0.1),
    )
    window._sc_speed_down.setAutoRepeat(True)
    window._sc_move_ok = make_shortcut(
        int(QtCore.Qt.Key_9 | QtCore.Qt.KeypadModifier),
        lambda: window._move_current_file_and_play_next("_ok"),
    )
    window._sc_move_ng = make_shortcut(
        int(QtCore.Qt.Key_7 | QtCore.Qt.KeypadModifier),
        lambda: window._move_current_file_and_play_next("_ng"),
    )
    window._sc_metadata = make_shortcut(QtCore.Qt.Key_I, window._show_metadata_dialog)
