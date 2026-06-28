import os
from typing import Any

from PyQt5 import QtCore

from ..vlc_adapter import VlcPlayerAdapter

try:
    import vlc
except (FileNotFoundError, ImportError, OSError):
    vlc = None  # type: ignore[assignment]


class VlcEvents(QtCore.QObject):
    media_ended = QtCore.pyqtSignal()
    media_playing = QtCore.pyqtSignal()


def create_vlc_instance() -> Any:
    if vlc is None:
        raise RuntimeError(
            "VLC が見つかりません。VLC 本体をインストールするか、"
            "PYTHON_VLC_LIB_PATH に libvlc.dll のディレクトリを設定してください。"
        )

    lib_path = os.environ.get("PYTHON_VLC_LIB_PATH")
    if lib_path and os.path.isdir(lib_path):
        return vlc.Instance([f"--plugin-path={lib_path}", "--audio-time-stretch"])
    return vlc.Instance(["--audio-time-stretch"])


__all__ = ["VlcEvents", "VlcPlayerAdapter", "create_vlc_instance", "vlc"]
