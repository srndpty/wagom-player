import os
import sys
import re
import json
from datetime import datetime
from typing import List, Optional

from PyQt5 import QtWidgets, QtCore, QtNetwork

from wagom_player.logger import log_message
from wagom_player.theme import (
    apply_dark_theme,
    apply_app_icon,
    apply_windows_app_user_model_id,
)
from wagom_player.main_window import VideoPlayer

# ログメッセージ関数を一時的にオーバーライドしてPIDとタイムスタンプを追加
original_log_message = log_message

def log_message(msg):
    pid = os.getpid()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    original_log_message(f"[{timestamp}][PID:{pid:5d}] {msg}")


SINGLE_INSTANCE_SERVER_NAME = "wagom-player-single-instance-v1"


def _find_initial_file(argv: List[str]) -> Optional[str]:
    """コマンドライン引数から、最初に存在するファイルパスを取得する。"""
    for arg in argv[1:]:
        if os.path.exists(arg) and os.path.isfile(arg):
            return arg
    return None


def _send_to_existing_instance(file_path: Optional[str], timeout_ms: int = 500) -> bool:
    socket = QtNetwork.QLocalSocket()
    socket.connectToServer(SINGLE_INSTANCE_SERVER_NAME, QtCore.QIODevice.WriteOnly)
    if not socket.waitForConnected(timeout_ms):
        return False

    payload = json.dumps({"file": file_path or ""}, ensure_ascii=False).encode("utf-8")
    socket.write(payload)
    socket.flush()
    socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    socket.waitForDisconnected(100)
    return True


def _create_single_instance_server() -> Optional[QtNetwork.QLocalServer]:
    server = QtNetwork.QLocalServer()
    if server.listen(SINGLE_INSTANCE_SERVER_NAME):
        return server

    # staleなサーバー名が残っている場合だけ掃除して再試行する。
    QtNetwork.QLocalServer.removeServer(SINGLE_INSTANCE_SERVER_NAME)
    if server.listen(SINGLE_INSTANCE_SERVER_NAME):
        return server

    log_message(f"Failed to start single-instance server: {server.errorString()}")
    return None


class SingleInstanceServer(QtCore.QObject):
    file_requested = QtCore.pyqtSignal(str)

    def __init__(self, server: QtNetwork.QLocalServer):
        super().__init__()
        self._server = server
        self._buffers = {}
        self._server.newConnection.connect(self._on_new_connection)

    def _on_new_connection(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            self._buffers[socket] = bytearray()
            socket.readyRead.connect(lambda s=socket: self._read_socket(s))
            socket.disconnected.connect(lambda s=socket: self._finish_socket(s))

    def _read_socket(self, socket: QtNetwork.QLocalSocket) -> None:
        if socket not in self._buffers:
            return
        self._buffers[socket].extend(bytes(socket.readAll()))

    def _finish_socket(self, socket: QtNetwork.QLocalSocket) -> None:
        self._read_socket(socket)
        data = bytes(self._buffers.pop(socket, b""))
        socket.deleteLater()

        if not data:
            self.file_requested.emit("")
            return

        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            log_message(f"Invalid single-instance payload: {e}")
            return

        file_path = payload.get("file", "")
        if isinstance(file_path, str):
            self.file_requested.emit(file_path)

def main_wrapper(argv: List[str]) -> int:
    try:
        return main(argv)
    except Exception:
        import traceback
        app = QtWidgets.QApplication.instance()
        if app is None:
            app = QtWidgets.QApplication(sys.argv)

        error_title = "Wagom Player - 致命的なエラー"
        error_message = "予期せぬエラーが発生したため、アプリケーションを終了します。"
        detailed_text = traceback.format_exc()
        log_message("!!!!!!!!!! UNHANDLED EXCEPTION !!!!!!!!!!")
        log_message(detailed_text)

        msg_box = QtWidgets.QMessageBox()
        msg_box.setIcon(QtWidgets.QMessageBox.Critical)
        msg_box.setText(error_message)
        msg_box.setInformativeText("エラーの詳細はログファイルに記録されました。")
        msg_box.setWindowTitle(error_title)
        msg_box.setDetailedText(detailed_text)
        msg_box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        msg_box.exec_()
        return 1

def main(argv: List[str]) -> int:
    # --- 基本的なアプリケーション設定 ---
    app = QtWidgets.QApplication(argv)
    QtCore.QCoreApplication.setOrganizationName("wagom")
    QtCore.QCoreApplication.setApplicationName("wagom-player")

    initial_file = _find_initial_file(argv)
    if _send_to_existing_instance(initial_file):
        log_message("Existing wagom-player instance found. Forwarded request and exiting.")
        return 0

    single_instance_server = _create_single_instance_server()
    apply_dark_theme(app)
    apply_windows_app_user_model_id("wagom-player")
    icon = apply_app_icon(app)

    # VideoPlayerウィンドウを作成し、単一のファイルパスを渡す
    print(f"Initial file: {initial_file}")
    player_window = VideoPlayer(file=initial_file)
    player_window.setWindowIcon(icon)
    if single_instance_server is not None:
        instance_ipc = SingleInstanceServer(single_instance_server)
        instance_ipc.file_requested.connect(player_window.open_external_file)
        app._single_instance_server = instance_ipc
    player_window.show()

    return app.exec_()

if __name__ == "__main__":
    sys.exit(main_wrapper(sys.argv))
