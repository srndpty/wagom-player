import importlib
import sys
import threading
import uuid

import pytest

QtCore = pytest.importorskip("PyQt5.QtCore", exc_type=ImportError)
QtNetwork = pytest.importorskip("PyQt5.QtNetwork", exc_type=ImportError)

single_instance = importlib.import_module("wagom_player.single_instance")


@pytest.mark.skipif(
    not sys.platform.startswith("win"),
    reason="named-mutex primary lock is Windows-specific",
)
def test_primary_instance_lock_is_exclusive():
    name = f"wagom-player-test-lock-{uuid.uuid4()}"

    # 最初の取得は primary。保持中の2つ目は primary になれない。
    first = single_instance.acquire_primary_instance_lock(name)
    try:
        assert first.is_primary
        second = single_instance.acquire_primary_instance_lock(name)
        try:
            assert not second.is_primary
        finally:
            second.release()
    finally:
        first.release()

    # 全て解放されたら、次の取得は再び primary になれる。
    third = single_instance.acquire_primary_instance_lock(name)
    try:
        assert third.is_primary
    finally:
        third.release()


def _wait_until(qapp, predicate, timeout_ms=1000):
    deadline = QtCore.QDeadlineTimer(timeout_ms)
    while not deadline.hasExpired():
        qapp.processEvents()
        if predicate():
            return True
        QtCore.QThread.msleep(10)
    return predicate()


def test_single_instance_server_receives_forwarded_file(qapp):
    server_name = f"wagom-player-test-{uuid.uuid4()}"
    server = single_instance.create_single_instance_server(server_name)
    assert server is not None
    received = []
    send_result = []
    instance = single_instance.SingleInstanceServer(server)
    instance.file_requested.connect(received.append)

    try:
        sender = threading.Thread(
            target=lambda: send_result.append(
                single_instance.send_to_existing_instance(
                    r"C:\videos\movie.mp4",
                    server_name=server_name,
                )
            )
        )
        sender.start()
        assert _wait_until(qapp, lambda: received)
        sender.join(timeout=1)

        assert send_result == [True]
        assert received == [r"C:\videos\movie.mp4"]
    finally:
        server.close()
        QtNetwork.QLocalServer.removeServer(server_name)


def test_send_to_existing_instance_returns_false_without_server():
    server_name = f"wagom-player-test-{uuid.uuid4()}"

    assert not single_instance.send_to_existing_instance(
        "movie.mp4",
        timeout_ms=20,
        server_name=server_name,
    )


def test_single_instance_server_ignores_invalid_and_large_payload(qapp):
    server_name = f"wagom-player-test-{uuid.uuid4()}"
    server = single_instance.create_single_instance_server(server_name)
    assert server is not None
    received = []
    instance = single_instance.SingleInstanceServer(server)
    instance.file_requested.connect(received.append)

    def send_raw(data: bytes) -> None:
        socket = QtNetwork.QLocalSocket()
        socket.connectToServer(server_name, QtCore.QIODevice.WriteOnly)
        assert socket.waitForConnected(500)
        socket.write(data)
        socket.flush()
        socket.waitForBytesWritten(500)
        socket.disconnectFromServer()
        socket.waitForDisconnected(100)

    try:
        send_raw(b"{invalid json")
        send_raw(b"x" * (single_instance.MAX_SINGLE_INSTANCE_PAYLOAD_BYTES + 1))
        assert _wait_until(qapp, lambda: not server.hasPendingConnections(), timeout_ms=500)
        qapp.processEvents()
        assert received == []
    finally:
        server.close()
        QtNetwork.QLocalServer.removeServer(server_name)
