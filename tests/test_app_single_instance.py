import importlib

app_module = importlib.import_module("app")


def test_claim_single_instance_retries_forward_before_removing_stale(monkeypatch):
    send_calls = []
    create_calls = []
    server = object()

    def fake_send(file_path, timeout_ms=500):
        send_calls.append((file_path, timeout_ms))
        return len(send_calls) == 2

    def fake_create(*, remove_stale=True):
        create_calls.append(remove_stale)
        return None if len(create_calls) == 1 else server

    monkeypatch.setattr(app_module, "send_to_existing_instance", fake_send)
    monkeypatch.setattr(app_module, "create_single_instance_server", fake_create)

    claimed_server, forwarded = app_module._claim_single_instance("movie.mp4")

    assert claimed_server is None
    assert forwarded
    assert create_calls == [False]
    assert send_calls == [("movie.mp4", 500), ("movie.mp4", 1000)]


def test_claim_single_instance_uses_server_when_available(monkeypatch):
    server = object()
    monkeypatch.setattr(app_module, "send_to_existing_instance", lambda _file_path: False)
    monkeypatch.setattr(
        app_module,
        "create_single_instance_server",
        lambda *, remove_stale=True: server if not remove_stale else None,
    )

    claimed_server, forwarded = app_module._claim_single_instance("movie.mp4")

    assert claimed_server is server
    assert not forwarded
