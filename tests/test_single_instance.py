import importlib
import threading
import uuid

import pytest

QtCore = pytest.importorskip("PyQt5.QtCore", exc_type=ImportError)
QtNetwork = pytest.importorskip("PyQt5.QtNetwork", exc_type=ImportError)

single_instance = importlib.import_module("wagom_player.single_instance")


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
