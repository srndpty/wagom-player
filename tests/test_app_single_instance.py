import importlib

app_module = importlib.import_module("app")


class _FakeLock:
    def __init__(self, is_primary, take_over_after=None, available=True):
        self.is_primary = is_primary
        self.available = available
        # None: 所有権を取れない。int: try_become_primary の N 回目で取得して primary に。
        self._take_over_after = take_over_after
        self._calls = 0
        self.released = False

    def try_become_primary(self, timeout_ms=0):
        self._calls += 1
        if self._take_over_after is not None and self._calls >= self._take_over_after:
            self.is_primary = True
            return True
        return self.is_primary

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


def test_claim_single_instance_takes_over_when_primary_dies(monkeypatch):
    sentinel = object()
    # 転送は失敗するが、所有権を取り直してホストを引き継ぐ。
    lock = _FakeLock(is_primary=False, take_over_after=1)
    create_calls = []

    monkeypatch.setattr(app_module, "acquire_primary_instance_lock", lambda: lock)
    monkeypatch.setattr(
        app_module,
        "send_to_existing_instance",
        lambda file_path, timeout_ms=500: False,
    )
    monkeypatch.setattr(
        app_module,
        "create_single_instance_server",
        lambda *, remove_stale=True: create_calls.append(remove_stale) or sentinel,
    )

    server, forwarded, returned_lock = app_module._claim_single_instance("movie.mp4")

    assert not forwarded
    assert server is sentinel
    assert returned_lock is lock
    assert lock.is_primary
    assert create_calls == [True]  # 引き継いだ 1 プロセスだけがホスト化


def test_claim_single_instance_exits_when_takeover_fails(monkeypatch):
    # 転送できず所有権も取れない(primary 生存だが応答なし)場合は、別ウィンドウを
    # 開かないよう終了扱いにする。
    lock = _FakeLock(is_primary=False, take_over_after=None)
    create_calls = []

    monkeypatch.setattr(app_module, "acquire_primary_instance_lock", lambda: lock)
    monkeypatch.setattr(app_module.time, "sleep", lambda _s: None)
    monkeypatch.setattr(
        app_module,
        "send_to_existing_instance",
        lambda file_path, timeout_ms=500: False,
    )
    monkeypatch.setattr(
        app_module,
        "create_single_instance_server",
        lambda *, remove_stale=True: create_calls.append(remove_stale),
    )

    server, forwarded, returned_lock = app_module._claim_single_instance("movie.mp4")

    assert forwarded
    assert server is None
    assert returned_lock is lock
    assert not lock.is_primary
    assert create_calls == []  # サーバは立てない(レース回避)


def test_claim_single_instance_falls_back_to_forward_when_mutex_unavailable(monkeypatch):
    # mutex 不可(非 Windows / CreateMutexW 失敗)でも、既存インスタンスへは送信する。
    lock = _FakeLock(is_primary=True, available=False)
    send_calls = []
    create_calls = []

    monkeypatch.setattr(app_module, "acquire_primary_instance_lock", lambda: lock)
    monkeypatch.setattr(
        app_module,
        "send_to_existing_instance",
        lambda file_path, timeout_ms=500: send_calls.append(file_path) or True,
    )
    monkeypatch.setattr(
        app_module,
        "create_single_instance_server",
        lambda *, remove_stale=True: create_calls.append(remove_stale),
    )

    server, forwarded, returned_lock = app_module._claim_single_instance("movie.mp4")

    assert forwarded  # is_primary=True でも送信を試して転送する
    assert server is None
    assert returned_lock is lock
    assert send_calls == ["movie.mp4"]
    assert create_calls == []


def test_claim_single_instance_hosts_via_listen_when_mutex_unavailable(monkeypatch):
    # mutex 不可で既存インスタンスも無ければ listen で自分がホストになる。
    sentinel = object()
    lock = _FakeLock(is_primary=True, available=False)
    create_calls = []

    monkeypatch.setattr(app_module, "acquire_primary_instance_lock", lambda: lock)
    monkeypatch.setattr(
        app_module,
        "send_to_existing_instance",
        lambda file_path, timeout_ms=500: False,
    )
    monkeypatch.setattr(
        app_module,
        "create_single_instance_server",
        lambda *, remove_stale=True: create_calls.append(remove_stale) or sentinel,
    )

    server, forwarded, returned_lock = app_module._claim_single_instance("movie.mp4")

    assert not forwarded
    assert server is sentinel
    assert returned_lock is lock
    assert create_calls == [False]  # stale 削除前の排他 listen でホスト化


def test_claim_single_instance_retries_forward_before_stale_removal(monkeypatch):
    # mutex 不可で同時起動した場合、片方が排他 listen に成功した直後なら、
    # stale 削除へ進む前に再送して二次プロセスを終了させる。
    lock = _FakeLock(is_primary=True, available=False)
    send_calls = []
    create_calls = []

    monkeypatch.setattr(app_module, "acquire_primary_instance_lock", lambda: lock)

    def fake_send(file_path, timeout_ms=500):
        send_calls.append(file_path)
        return len(send_calls) == 2

    monkeypatch.setattr(app_module, "send_to_existing_instance", fake_send)
    monkeypatch.setattr(
        app_module,
        "create_single_instance_server",
        lambda *, remove_stale=True: create_calls.append(remove_stale) or None,
    )

    server, forwarded, returned_lock = app_module._claim_single_instance("movie.mp4")

    assert forwarded
    assert server is None
    assert returned_lock is lock
    assert send_calls == ["movie.mp4", "movie.mp4"]
    assert create_calls == [False]  # 稼働中サーバ名を removeServer しない


def test_claim_single_instance_removes_stale_after_exclusive_listen_and_retry_fail(
    monkeypatch,
):
    # 排他 listen と再送の両方が失敗した場合だけ stale 削除つき listen に進む。
    sentinel = object()
    lock = _FakeLock(is_primary=True, available=False)
    create_calls = []

    monkeypatch.setattr(app_module, "acquire_primary_instance_lock", lambda: lock)
    monkeypatch.setattr(
        app_module,
        "send_to_existing_instance",
        lambda file_path, timeout_ms=500: False,
    )

    def fake_create(*, remove_stale=True):
        create_calls.append(remove_stale)
        if remove_stale:
            return sentinel
        return None

    monkeypatch.setattr(app_module, "create_single_instance_server", fake_create)

    server, forwarded, returned_lock = app_module._claim_single_instance("movie.mp4")

    assert not forwarded
    assert server is sentinel
    assert returned_lock is lock
    assert create_calls == [False, True]
