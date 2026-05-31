import os
from datetime import datetime
from typing import Optional

_session_log_path: Optional[str] = None

_LAST_RUN_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


def logs_dir() -> str:
    return os.path.join(os.getenv("LOCALAPPDATA", ""), "wagom-player", "logs")


def configure_session_log(session_id: str) -> None:
    global _session_log_path
    try:
        base = logs_dir()
        if not base:
            return
        os.makedirs(base, exist_ok=True)
        _session_log_path = os.path.join(base, f"session-{session_id}.txt")
        _rotate_last_run(base)
    except Exception:
        _session_log_path = None


def _rotate_last_run(base: str) -> None:
    path = os.path.join(base, "last-run.txt")
    try:
        if os.path.getsize(path) > _LAST_RUN_MAX_BYTES:
            with open(path, "w", encoding="utf-8"):
                pass
    except OSError:
        pass


def log_message(msg: str) -> None:
    """
    アプリケーションの動作ログをファイルに記録するグローバル関数
    """
    try:
        base = logs_dir()
        if base:
            os.makedirs(base, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(
                os.path.join(base, "last-run.txt"),
                "a",
                encoding="utf-8",
                errors="ignore",
            ) as f:
                f.write(f"[{ts}] {msg}\n")
            if _session_log_path:
                with open(
                    _session_log_path,
                    "a",
                    encoding="utf-8",
                    errors="ignore",
                ) as f:
                    f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass
