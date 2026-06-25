import ctypes
import json
import sys
from typing import Optional

from PyQt5 import QtCore, QtNetwork

from .logger import log_message

SINGLE_INSTANCE_SERVER_NAME = "wagom-player-single-instance-v1"
MAX_SINGLE_INSTANCE_PAYLOAD_BYTES = 64 * 1024

# 「最初の1つ」を原子的に決めるための名前付き mutex。
# QLocalServer.listen() は Windows の名前付きパイプ仕様上、複数プロセスが同名で
# 同時に成功しうるため、起動が同一ミリ秒で衝突すると両方がホスト化してしまう。
# CreateMutexW はカーネルで直列化され、ERROR_ALREADY_EXISTS が原子的に返るため、
# 同時起動でも primary は必ず 1 プロセスだけになる。
PRIMARY_INSTANCE_MUTEX_NAME = "wagom-player-single-instance-lock-v1"
_ERROR_ALREADY_EXISTS = 183


class PrimaryInstanceLock:
    """起動プロセスがこのセッションで最初の(=ホストになるべき)インスタンスか保持する。

    ``is_primary`` が True のプロセスだけが IPC サーバを立てる。ホストである限り
    OS にこの mutex ハンドルを保持させ続ける必要があるため、ホスト側ではプロセス
    終了まで ``release()`` を呼ばない。
    """

    def __init__(self, is_primary: bool, handle: Optional[int] = None):
        self.is_primary = is_primary
        self._handle = handle

    def release(self) -> None:
        if self._handle is not None:
            try:
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
                kernel32.CloseHandle(self._handle)
            except Exception as e:  # pragma: no cover - 解放失敗は致命的ではない
                log_message(f"Failed to release primary-instance lock: {e!r}")
            self._handle = None


def acquire_primary_instance_lock(
    name: str = PRIMARY_INSTANCE_MUTEX_NAME,
) -> PrimaryInstanceLock:
    """名前付き mutex を取得し、自プロセスが primary かどうかを原子的に判定する。

    Windows 以外、または mutex 取得に失敗した場合は ``is_primary=True``
    (フェイルオープン) を返し、従来どおり listen() ベースの調停に委ねる。
    """
    if not sys.platform.startswith("win"):
        return PrimaryInstanceLock(True)
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_bool,
            ctypes.c_wchar_p,
        ]
        handle = kernel32.CreateMutexW(None, False, name)
        last_error = ctypes.get_last_error()
        if not handle:
            log_message(f"CreateMutexW failed (err={last_error}); assuming primary instance.")
            return PrimaryInstanceLock(True)
        is_primary = last_error != _ERROR_ALREADY_EXISTS
        return PrimaryInstanceLock(is_primary, handle)
    except Exception as e:
        log_message(f"Primary-instance lock unavailable: {e!r}")
        return PrimaryInstanceLock(True)


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
        log_message(
            f"Single-instance server not acquired without stale removal: {server.errorString()}"
        )
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
        self._discarded_sockets = set()
        self._server.newConnection.connect(self._on_new_connection)

    def _on_new_connection(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            self._buffers[socket] = bytearray()
            socket.readyRead.connect(lambda s=socket: self._read_socket(s))
            socket.destroyed.connect(lambda _=None, s=socket: self._cleanup_socket(s))
            socket.disconnected.connect(
                lambda s=socket: QtCore.QTimer.singleShot(0, lambda: self._finish_socket(s))
            )
            self._read_socket(socket)

    def _read_socket(self, socket: QtNetwork.QLocalSocket) -> None:
        if socket not in self._buffers:
            return
        self._buffers[socket].extend(bytes(socket.readAll()))
        if len(self._buffers[socket]) > MAX_SINGLE_INSTANCE_PAYLOAD_BYTES:
            log_message("Single-instance payload too large; discarding request.")
            self._discarded_sockets.add(socket)
            socket.abort()

    def _finish_socket(self, socket: QtNetwork.QLocalSocket) -> None:
        self._read_socket(socket)
        data = bytes(self._buffers.pop(socket, b""))
        discarded = socket in self._discarded_sockets
        self._discarded_sockets.discard(socket)
        socket.deleteLater()

        if discarded:
            return

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

    def _cleanup_socket(self, socket: QtNetwork.QLocalSocket) -> None:
        self._buffers.pop(socket, None)
        self._discarded_sockets.discard(socket)
