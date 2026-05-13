import os

from wagom_player import diagnostics


def test_breadcrumbs_are_limited_to_maximum():
    diagnostics._breadcrumbs.clear()

    for i in range(diagnostics.MAX_BREADCRUMBS + 5):
        diagnostics.record_breadcrumb("event", index=i)

    assert len(diagnostics._breadcrumbs) == diagnostics.MAX_BREADCRUMBS
    assert diagnostics._breadcrumbs[0]["fields"]["index"] == 5


def test_report_contains_session_state_breadcrumbs_and_stack_heading(
    tmp_path, monkeypatch
):
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
