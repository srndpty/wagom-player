import json
from typing import Optional

from PyQt5 import QtCore, QtNetwork

from .logger import log_message

SINGLE_INSTANCE_SERVER_NAME = "wagom-player-single-instance-v1"


def send_to_existing_instance(
    file_path: Optional[str],
    timeout_ms: int = 500,
    server_name: str = SINGLE_INSTANCE_SERVER_NAME,
) -> bool:
    socket = QtNetwork.QLocalSocket()
    socket.connectToServer(server_name, QtCore.QIODevice.WriteOnly)
    if not socket.waitForConnected(timeout_ms):
        return False

    payload = json.dumps({"file": file_path or ""}, ensure_ascii=False).encode("utf-8")
    bytes_written = socket.write(payload)
    if bytes_written != len(payload):
        socket.abort()
        return False
    socket.flush()
    socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    socket.waitForDisconnected(100)
    return True


def create_single_instance_server(
    server_name: str = SINGLE_INSTANCE_SERVER_NAME,
    *,
    remove_stale: bool = True,
) -> Optional[QtNetwork.QLocalServer]:
    server = QtNetwork.QLocalServer()
    if server.listen(server_name):
        return server

    if not remove_stale:
        log_message(f"Failed to start single-instance server: {server.errorString()}")
        return None

    QtNetwork.QLocalServer.removeServer(server_name)
    if server.listen(server_name):
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
            socket.disconnected.connect(
                lambda s=socket: QtCore.QTimer.singleShot(0, lambda: self._finish_socket(s))
            )
            self._read_socket(socket)

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
