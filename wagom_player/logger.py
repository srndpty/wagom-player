import os
from datetime import datetime

def log_message(msg: str) -> None:
    """
    アプリケーションの動作ログをファイルに記録するグローバル関数
    """
    try:
        base = os.path.join(os.getenv("LOCALAPPDATA", ""), "wagom-player", "logs")
        if base:
            os.makedirs(base, exist_ok=True)
            with open(os.path.join(base, "last-run.txt"), "a", encoding="utf-8", errors="ignore") as f:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass