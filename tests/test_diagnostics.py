import os
import sys
from types import SimpleNamespace

from wagom_player import diagnostics


def test_breadcrumbs_are_limited_to_maximum():
    diagnostics._breadcrumbs.clear()

    for i in range(diagnostics.MAX_BREADCRUMBS + 5):
        diagnostics.record_breadcrumb("event", index=i)

    assert len(diagnostics._breadcrumbs) == diagnostics.MAX_BREADCRUMBS
    assert diagnostics._breadcrumbs[0]["fields"]["index"] == 5


def test_report_contains_session_state_breadcrumbs_and_stack_heading(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    diagnostics._breadcrumbs.clear()
    diagnostics.update_state_snapshot(current_file=r"C:\videos\movie.mp4")
    diagnostics.record_breadcrumb("open_file", path=r"C:\videos\movie.mp4")

    report = diagnostics.format_diagnostic_report("Test Report", "details")

    assert "Session" in report
    assert "State Snapshot" in report
    assert "Breadcrumbs" in report
    assert "Python Thread Stacks" in report
    assert r"C:\videos\movie.mp4" in report


def test_exception_report_writes_full_path(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    full_path = os.path.join(str(tmp_path), "movie.mp4")
    diagnostics._breadcrumbs.clear()
    diagnostics.update_state_snapshot(current_file=full_path)

    try:
        raise RuntimeError("boom")
    except RuntimeError as e:
        path = diagnostics.write_exception_report(type(e), e, e.__traceback__)

    assert os.path.exists(path)
    assert os.path.dirname(path).endswith(os.path.join("logs", "reports"))
    with open(path, encoding="utf-8") as f:
        text = f.read()
    assert full_path in text
    assert "RuntimeError: boom" in text


def test_start_session_is_best_effort_when_report_dir_fails(monkeypatch):
    def fail_report_dir():
        raise OSError("read only")

    monkeypatch.setattr(diagnostics, "_ensure_report_dir", fail_report_dir)

    assert diagnostics.start_session(["wagom-player"]) == diagnostics._session_id


def test_start_session_records_cleanup_and_breadcrumb(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    diagnostics._breadcrumbs.clear()

    session_id = diagnostics.start_session(["wagom-player", "movie.mp4"])

    assert session_id == diagnostics._session_id
    assert diagnostics._breadcrumbs[-1]["event"] == "session_start"
    assert diagnostics._breadcrumbs[-1]["fields"]["argv"] == ["wagom-player", "movie.mp4"]


def test_install_excepthook_and_excepthook_delegate(monkeypatch):
    calls = []
    previous = sys.excepthook
    monkeypatch.setattr(diagnostics, "_previous_excepthook", lambda *args: calls.append(args))
    monkeypatch.setattr(diagnostics, "write_exception_report", lambda *args: "report.txt")

    diagnostics.install_excepthook()
    try:
        assert sys.excepthook == diagnostics._excepthook
        diagnostics._excepthook(RuntimeError, RuntimeError("boom"), None)
    finally:
        sys.excepthook = previous

    assert calls


def test_heartbeat_records_recovery(monkeypatch):
    events = []
    monkeypatch.setattr(diagnostics, "log_message", lambda msg: events.append(("log", msg)))
    monkeypatch.setattr(
        diagnostics,
        "record_breadcrumb",
        lambda event, **fields: events.append((event, fields)),
    )
    monkeypatch.setattr(diagnostics, "_hang_reported", True)

    diagnostics.heartbeat()

    assert not diagnostics._hang_reported
    assert events[-1] == ("ui_recovered", {})


def test_start_heartbeat_timer_creates_running_timer(qapp):
    parent = diagnostics.QtCore.QObject()

    timer = diagnostics.start_heartbeat_timer(parent)

    assert timer.interval() == 500
    assert timer.isActive()
    timer.stop()


def test_start_hang_monitor_does_not_start_twice(monkeypatch):
    started = []

    class FakeThread:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def is_alive(self):
            return False

        def start(self):
            started.append(self.kwargs)

    monkeypatch.setattr(diagnostics, "_monitor_thread", None)
    monkeypatch.setattr(diagnostics.threading, "Thread", lambda **kwargs: FakeThread(**kwargs))

    diagnostics.start_hang_monitor(1.0, 0.1)
    assert started[0]["name"] == "wagom-diagnostics-hang-monitor"

    monkeypatch.setattr(diagnostics, "_monitor_thread", SimpleNamespace(is_alive=lambda: True))
    diagnostics.start_hang_monitor()
    assert len(started) == 1


def test_monitor_loop_writes_hang_report_once(monkeypatch):
    waits = iter([False, True])
    events = []
    monkeypatch.setattr(diagnostics._monitor_stop, "wait", lambda _interval: next(waits))
    monkeypatch.setattr(diagnostics.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(diagnostics, "_last_heartbeat", 90.0)
    monkeypatch.setattr(diagnostics, "_hang_reported", False)
    monkeypatch.setattr(diagnostics, "write_hang_report", lambda stalled: "hang.txt")
    monkeypatch.setattr(diagnostics, "log_message", lambda msg: events.append(("log", msg)))
    monkeypatch.setattr(
        diagnostics,
        "record_breadcrumb",
        lambda event, **fields: events.append((event, fields)),
    )

    diagnostics._monitor_loop(5.0, 1.0)

    assert diagnostics._hang_reported
    assert ("ui_hang_reported", {"stalled_seconds": 10.0}) in events


def test_monitor_loop_logs_report_failure(monkeypatch):
    waits = iter([False, True])
    events = []
    monkeypatch.setattr(diagnostics._monitor_stop, "wait", lambda _interval: next(waits))
    monkeypatch.setattr(diagnostics.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(diagnostics, "_last_heartbeat", 90.0)
    monkeypatch.setattr(diagnostics, "_hang_reported", False)

    def fail_report(_stalled):
        raise OSError("no write")

    monkeypatch.setattr(diagnostics, "write_hang_report", fail_report)
    monkeypatch.setattr(diagnostics, "log_message", events.append)

    diagnostics._monitor_loop(5.0, 1.0)

    assert any("Failed to write UI hang report" in message for message in events)


def test_write_hang_report_and_cleanup_old_files(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    path = diagnostics.write_hang_report(6.25)
    with open(path, encoding="utf-8") as f:
        text = f.read()

    assert os.path.exists(path)
    assert "UI heartbeat stalled for 6.2 seconds" in text

    report_dir = os.path.dirname(path)
    old = os.path.join(report_dir, "hang-old.txt")
    keep = os.path.join(report_dir, "hang-keep.txt")
    with open(old, "w", encoding="utf-8") as f:
        f.write("old")
    with open(keep, "w", encoding="utf-8") as f:
        f.write("keep")
    os.utime(old, (1, 1))
    os.utime(keep, (2, 2))

    diagnostics._cleanup_old_files(report_dir, "hang-*.txt", 2)

    assert os.path.exists(keep)
    assert not os.path.exists(old)


def test_format_helpers_and_safe_value_edge_cases(monkeypatch):
    class BadRepr:
        def __repr__(self):
            raise RuntimeError("bad repr")

    monkeypatch.setattr(diagnostics, "QtCore", None)

    assert diagnostics._format_mapping({}) == "(empty)"
    assert "a: 1" in diagnostics._format_mapping({"a": 1})
    assert diagnostics._format_breadcrumbs([]) == "(empty)"
    assert diagnostics._format_report_value("text") == "text"
    assert diagnostics._safe_value({"x": (BadRepr(),)}) == {"x": ["<unrepresentable BadRepr>"]}
    assert diagnostics._qt_version() == ""


def test_dump_tracebacks_returns_exception_text(monkeypatch):
    def fail_dump(*args, **kwargs):
        raise RuntimeError("dump failed")

    monkeypatch.setattr(diagnostics.faulthandler, "dump_traceback", fail_dump)

    assert "RuntimeError: dump failed" in diagnostics._dump_tracebacks()
