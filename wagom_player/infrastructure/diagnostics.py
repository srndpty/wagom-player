import faulthandler
import io
import os
import platform
import sys
import tempfile
import threading
import time
import traceback
from collections import deque
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any, Optional

from .logger import configure_session_log, log_message, logs_dir

try:
    from PyQt5 import QtCore
except Exception:  # pragma: no cover
    QtCore = None  # type: ignore[assignment]


MAX_BREADCRUMBS = 100
MAX_REPORTS = 20
HANG_THRESHOLD_SECONDS = 5.0
HANG_CHECK_INTERVAL_SECONDS = 1.0

_lock = threading.RLock()
_breadcrumbs = deque(maxlen=MAX_BREADCRUMBS)
_state_snapshot: dict[str, Any] = {}
_session_id = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}"
_started_at = datetime.now()
_argv: Iterable[str] = ()
_last_heartbeat = time.monotonic()
_hang_reported = False
_monitor_stop = threading.Event()
_monitor_thread: Optional[threading.Thread] = None
_heartbeat_timer = None
_previous_excepthook = sys.excepthook


def start_session(argv: Iterable[str]) -> str:
    global _argv
    try:
        with _lock:
            _argv = tuple(argv)
        configure_session_log(_session_id)
        _ensure_report_dir()
        _cleanup_old_files(_reports_dir(), "hang-*.txt", MAX_REPORTS)
        _cleanup_old_files(_reports_dir(), "exception-*.txt", MAX_REPORTS)
        _cleanup_old_files(logs_dir(), "session-*.txt", MAX_REPORTS)
        record_breadcrumb("session_start", argv=list(_argv), cwd=os.getcwd())
        log_message(f"Diagnostics session started: session_id={_session_id}")
    except Exception:
        pass
    return _session_id


def install_excepthook() -> None:
    sys.excepthook = _excepthook


def start_heartbeat_timer(parent: Any) -> Any:
    if QtCore is None:
        return None
    global _heartbeat_timer
    timer = QtCore.QTimer(parent)
    timer.setInterval(500)
    timer.timeout.connect(heartbeat)
    timer.start()
    _heartbeat_timer = timer
    return timer


def start_hang_monitor(
    threshold_seconds: float = HANG_THRESHOLD_SECONDS,
    interval_seconds: float = HANG_CHECK_INTERVAL_SECONDS,
) -> None:
    global _monitor_thread
    if _monitor_thread and _monitor_thread.is_alive():
        return
    _monitor_stop.clear()
    _monitor_thread = threading.Thread(
        target=_monitor_loop,
        args=(threshold_seconds, interval_seconds),
        name="wagom-diagnostics-hang-monitor",
        daemon=True,
    )
    _monitor_thread.start()


def stop_hang_monitor() -> None:
    _monitor_stop.set()


def heartbeat() -> None:
    global _hang_reported, _last_heartbeat
    now = time.monotonic()
    recovered = False
    with _lock:
        if _hang_reported:
            recovered = True
            _hang_reported = False
        _last_heartbeat = now
    if recovered:
        log_message("UI recovered after hang report")
        record_breadcrumb("ui_recovered")


def record_breadcrumb(event: str, **fields: Any) -> None:
    item = {
        "time": datetime.now().isoformat(timespec="milliseconds"),
        "event": event,
        "fields": _safe_value(fields),
    }
    with _lock:
        _breadcrumbs.append(item)


def update_state_snapshot(**fields: Any) -> None:
    snapshot = {
        "time": datetime.now().isoformat(timespec="milliseconds"),
        **_safe_value(fields),
    }
    with _lock:
        _state_snapshot.clear()
        _state_snapshot.update(snapshot)


def record_exception(context: str, error: BaseException, **fields: Any) -> None:
    log_message(f"{context}: {error!r}")
    record_breadcrumb(f"{context}_error", error=repr(error), **fields)


def run_safely(
    context: str,
    func: Callable[[], Any],
    default: Any = None,
    **fields: Any,
) -> Any:
    try:
        return func()
    except Exception as e:
        record_exception(context, e, **fields)
        return default


def write_exception_report(
    exc_type: Any,
    exc_value: BaseException,
    exc_tb: Any,
) -> str:
    formatted = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    return _write_report("exception", "Unhandled Exception Report", formatted)


def write_hang_report(stalled_seconds: float) -> str:
    header = f"UI heartbeat stalled for {stalled_seconds:.1f} seconds"
    return _write_report("hang", "UI Hang Report", header)


def format_diagnostic_report(title: str, details: str = "") -> str:
    with _lock:
        breadcrumbs = list(_breadcrumbs)
        snapshot = dict(_state_snapshot)
        argv = list(_argv)

    lines = [
        title,
        "=" * len(title),
        "",
        "Session",
        "-------",
        f"session_id: {_session_id}",
        f"pid: {os.getpid()}",
        f"started_at: {_started_at.isoformat(timespec='seconds')}",
        f"report_time: {datetime.now().isoformat(timespec='seconds')}",
        f"argv: {argv!r}",
        f"cwd: {os.getcwd()!r}",
        f"executable: {sys.executable!r}",
        f"frozen: {bool(getattr(sys, 'frozen', False))}",
        "",
        "Runtime",
        "-------",
        f"platform: {platform.platform()}",
        f"python: {sys.version.replace(os.linesep, ' ')}",
        f"qt: {_qt_version()}",
        f"vlc: {snapshot.get('vlc_version', '')!r}",
        "",
        "Details",
        "-------",
        details.rstrip(),
        "",
        "State Snapshot",
        "--------------",
        _format_mapping(snapshot),
        "",
        "Breadcrumbs",
        "-----------",
        _format_breadcrumbs(breadcrumbs),
        "",
        "Python Thread Stacks",
        "--------------------",
        _dump_tracebacks(),
        "",
    ]
    return "\n".join(lines)


def _excepthook(exc_type: Any, exc_value: BaseException, exc_tb: Any) -> None:
    try:
        write_exception_report(exc_type, exc_value, exc_tb)
    except Exception:
        pass
    _previous_excepthook(exc_type, exc_value, exc_tb)


def _monitor_loop(threshold_seconds: float, interval_seconds: float) -> None:
    global _hang_reported
    while not _monitor_stop.wait(interval_seconds):
        now = time.monotonic()
        with _lock:
            stalled = now - _last_heartbeat
            should_report = stalled >= threshold_seconds and not _hang_reported
            if should_report:
                _hang_reported = True
        if should_report:
            try:
                path = write_hang_report(stalled)
                log_message(f"UI hang report written: {path}")
                record_breadcrumb(
                    "ui_hang_reported",
                    stalled_seconds=round(stalled, 3),
                )
            except Exception as e:
                log_message(f"Failed to write UI hang report: {e!r}")


def _write_report(kind: str, title: str, details: str) -> str:
    report_dir = _ensure_report_dir()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{kind}-{timestamp}-{os.getpid()}.txt"
    path = os.path.join(report_dir, filename)
    text = format_diagnostic_report(title, details)
    with open(path, "w", encoding="utf-8", errors="ignore") as f:
        f.write(text)
    return path


def _reports_dir() -> str:
    return os.path.join(logs_dir(), "reports")


def _ensure_report_dir() -> str:
    report_dir = _reports_dir()
    os.makedirs(report_dir, exist_ok=True)
    return report_dir


def _cleanup_old_files(directory: str, pattern: str, keep: int) -> None:
    try:
        import glob

        paths = glob.glob(os.path.join(directory, pattern))
        paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        for path in paths[keep:]:
            try:
                os.remove(path)
            except OSError:
                pass
    except Exception:
        pass


def _dump_tracebacks() -> str:
    try:
        with tempfile.TemporaryFile("w+b") as stream:
            faulthandler.dump_traceback(file=stream, all_threads=True)
            stream.seek(0)
            return stream.read().decode("utf-8", errors="replace").rstrip()
    except Exception:
        stream = io.StringIO()
        stream.write(traceback.format_exc())
        return stream.getvalue().rstrip()


def _format_mapping(mapping: dict[str, Any]) -> str:
    if not mapping:
        return "(empty)"
    return "\n".join(
        f"{key}: {_format_report_value(value)}" for key, value in sorted(mapping.items())
    )


def _format_breadcrumbs(items: Iterable[dict[str, Any]]) -> str:
    lines = []
    for item in items:
        fields = item.get("fields", {})
        lines.append(f"{item.get('time')} {item.get('event')} {_format_mapping(fields)}")
    return "\n".join(lines) if lines else "(empty)"


def _format_report_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return repr(value)


def _qt_version() -> str:
    if QtCore is None:
        return ""
    try:
        return f"Qt {QtCore.QT_VERSION_STR}, PyQt {QtCore.PYQT_VERSION_STR}"
    except Exception:
        return ""


def _safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _safe_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_value(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        return repr(value)
    except Exception:
        return f"<unrepresentable {type(value).__name__}>"
