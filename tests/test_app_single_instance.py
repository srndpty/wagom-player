import importlib

app_module = importlib.import_module("app")


class _FakeLock:
    def __init__(self, is_primary):
        self.is_primary = is_primary
        self.released = False

    def release(self):
        self.released = True


def test_claim_single_instance_forwards_when_not_primary(monkeypatch):
    lock = _FakeLock(is_primary=False)
    send_calls = []
    create_calls = []

    monkeypatch.setattr(app_module, "acquire_primary_instance_lock", lambda: lock)

    def fake_send(file_path, timeout_ms=500):
        send_calls.append(file_path)
        return True

    monkeypatch.setattr(app_module, "send_to_existing_instance", fake_send)
    monkeypatch.setattr(
        app_module,
        "create_single_instance_server",
        lambda *, remove_stale=True: create_calls.append(remove_stale),
    )

    server, forwarded, returned_lock = app_module._claim_single_instance("movie.mp4")

    assert forwarded
    assert server is None
    assert returned_lock is lock
    assert send_calls == ["movie.mp4"]
    assert create_calls == []  # 転送できたらホスト化しない


def test_claim_single_instance_hosts_when_primary(monkeypatch):
    sentinel = object()
    lock = _FakeLock(is_primary=True)
    send_calls = []

    monkeypatch.setattr(app_module, "acquire_primary_instance_lock", lambda: lock)
    monkeypatch.setattr(
        app_module,
        "send_to_existing_instance",
        lambda file_path, timeout_ms=500: send_calls.append(file_path) or False,
    )
    monkeypatch.setattr(
        app_module,
        "create_single_instance_server",
        lambda *, remove_stale=True: sentinel,
    )

    server, forwarded, returned_lock = app_module._claim_single_instance("movie.mp4")

    assert not forwarded
    assert server is sentinel
    assert returned_lock is lock
    assert send_calls == []  # primary は転送を試みない


def test_claim_single_instance_takes_over_when_primary_unreachable(monkeypatch):
    sentinel = object()
    lock = _FakeLock(is_primary=False)

    monkeypatch.setattr(app_module, "acquire_primary_instance_lock", lambda: lock)
    # 転送が一度も成功しない(primary が起動途中で落ちた等)
    monkeypatch.setattr(app_module, "_forward_to_primary", lambda _file_path: False)
    monkeypatch.setattr(
        app_module,
        "create_single_instance_server",
        lambda *, remove_stale=True: sentinel,
    )

    server, forwarded, returned_lock = app_module._claim_single_instance("movie.mp4")

    assert not forwarded
    assert server is sentinel
    assert returned_lock is lock
