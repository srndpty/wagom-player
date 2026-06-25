import ctypes
import json
import sys
from typing import Optional

from PyQt5 import QtCore, QtNetwork

from .logger import log_message

SINGLE_INSTANCE_SERVER_NAME = "wagom-player-single-instance-v1"
MAX_SINGLE_INSTANCE_PAYLOAD_BYTES = 64 * 1024

# ホスト(=IPC サーバを立てるプロセス)を 1 つに絞るための名前付き mutex。
# QLocalServer.listen() は Windows の名前付きパイプ仕様上、複数プロセスが同名で
# 同時に成功しうるため、同一ミリ秒で衝突すると両方がホスト化してしまう。
# そこで mutex の「存在」ではなく「所有権」でホストを選出する。所有権は排他的で、
# 所有者が異常終了すると WAIT_ABANDONED で待機中の 1 プロセスだけが引き継げるため、
# 同時起動でも、ホストが listen 前に死んだ後の乗っ取りでも、ホストは常に 1 つになる。
PRIMARY_INSTANCE_MUTEX_NAME = "wagom-player-single-instance-lock-v1"
_WAIT_OBJECT_0 = 0x00000000
_WAIT_ABANDONED = 0x00000080


class PrimaryInstanceLock:
    """このプロセスがホスト(=IPC サーバを立てるべきインスタンス)かを保持する。

    ``is_primary`` が True のプロセスだけが IPC サーバを立てる。ホストである限り
    mutex の所有権を保持し続ける必要があるため、ホスト側ではプロセス終了まで
    ``release()`` を呼ばない。``try_become_primary()`` は所有権の獲得を試み、
    既存ホストが生きていれば失敗、ホストが所有権を手放した/異常終了していれば
    ただ 1 プロセスだけが成功する。
    """

    def __init__(
        self,
        is_primary: bool,
        handle: Optional[int] = None,
        kernel32=None,
        available: bool = False,
    ):
        self.is_primary = is_primary
        # available=False は「mutex が使えない(非 Windows / 作成失敗)」を意味し、
        # 呼び出し側は所有権ベースの選出ではなく従来の send/listen 調停に戻す。
        self.available = available
        self._handle = handle
        self._kernel32 = kernel32
        self._owns = False

    def try_become_primary(self, timeout_ms: int = 0) -> bool:
        """mutex の所有権(ホスト権)の獲得を試みる。獲得できれば primary になる。

        既存ホストが所有権を保持していれば WAIT_TIMEOUT で False。ホストが
        ``release()``/異常終了で手放していれば、待機プロセスのうち 1 つだけが
        WAIT_OBJECT_0 / WAIT_ABANDONED を受け取り True を返す。
        """
        if self._handle is None:
            # 非 Windows / フェイルオープン: 常にホスト扱い。
            self.is_primary = True
            return True
        if self._owns:
            return True
        try:
            k = self._kernel32
            k.WaitForSingleObject.restype = ctypes.c_uint32
            k.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            rc = k.WaitForSingleObject(self._handle, timeout_ms)
        except Exception as e:  # pragma: no cover - 取得失敗は致命的ではない
            log_message(f"Failed to acquire primary-instance ownership: {e!r}")
            return False
        if rc in (_WAIT_OBJECT_0, _WAIT_ABANDONED):
            self.is_primary = True
            self._owns = True
            return True
        return False

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            k = self._kernel32
            if self._owns:
                k.ReleaseMutex.argtypes = [ctypes.c_void_p]
                k.ReleaseMutex(self._handle)
                self._owns = False
            k.CloseHandle.argtypes = [ctypes.c_void_p]
            k.CloseHandle(self._handle)
        except Exception as e:  # pragma: no cover - 解放失敗は致命的ではない
            log_message(f"Failed to release primary-instance lock: {e!r}")
        self._handle = None


def acquire_primary_instance_lock(
    name: str = PRIMARY_INSTANCE_MUTEX_NAME,
) -> PrimaryInstanceLock:
    """名前付き mutex を作成し、所有権(ホスト権)の獲得を非ブロッキングで試みる。

    所有権を取れたプロセスが primary(ホスト)。Windows 以外、または mutex 作成に
    失敗した場合は ``is_primary=True`` (フェイルオープン) を返し、従来どおり
    listen() ベースの調停に委ねる。
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
        if not handle:
            err = ctypes.get_last_error()
            log_message(f"CreateMutexW failed (err={err}); assuming primary instance.")
            return PrimaryInstanceLock(True)
        lock = PrimaryInstanceLock(
            is_primary=False, handle=handle, kernel32=kernel32, available=True
        )
        lock.try_become_primary(timeout_ms=0)
        return lock
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
