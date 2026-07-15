from .controllers import playback_controller as _implementation
from .controllers.playback_controller import PlaybackController

# テスト可能な構成境界として、外部依存をこのモジュールから注入する。
QtCore = _implementation.QtCore
diagnostics = _implementation.diagnostics
vlc = _implementation.vlc


def _create_vlc_instance():
    _implementation.vlc = vlc
    return _implementation._create_vlc_instance()


class MainWindow(PlaybackController):
    """依存を組み立て、各UI責務を統合するメインウィンドウ。"""

    def __init__(self, file=None):
        _implementation.vlc = vlc
        super().__init__(file=file)
