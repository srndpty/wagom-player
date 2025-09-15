import os
import sys
import json
import getpass
from datetime import datetime
from typing import List

from PyQt5 import QtWidgets, QtCore, QtNetwork
import re

from wagom_player.theme import apply_dark_theme, apply_app_icon, apply_windows_app_user_model_id
from wagom_player.main_window import VideoPlayer


def main(argv: List[str]) -> int:
    app = QtWidgets.QApplication(argv)
    # QSettings 用の識別子
    QtCore.QCoreApplication.setOrganizationName("wagom")
    QtCore.QCoreApplication.setApplicationName("wagom-player")
    apply_dark_theme(app)
    apply_windows_app_user_model_id("wagom-player")
    icon = apply_app_icon(app)

    # 簡易ログ（LocalAppData配下）
    def _log(msg: str) -> None:
        try:
            base = os.path.join(os.getenv("LOCALAPPDATA", ""), "wagom-player", "logs")
            if base:
                os.makedirs(base, exist_ok=True)
                with open(os.path.join(base, "last-run.txt"), "a", encoding="utf-8", errors="ignore") as f:
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"[{ts}] {msg}\n")
        except Exception:
            pass

    _log("argv=" + repr(argv))

    # 単一インスタンス: 既存インスタンスがいれば引数を送って終了
    server_name = f"wagom-player-{getpass.getuser()}"

    # 単一インスタンス制御: QLockFileで競合を防止
    la = os.getenv("LOCALAPPDATA", "") or os.path.expanduser("~")
    lock_dir = os.path.join(la, "wagom-player")
    try:
        os.makedirs(lock_dir, exist_ok=True)
    except Exception:
        pass
    lock_path = os.path.join(lock_dir, "instance.lock")
    lock = QtCore.QLockFile(lock_path)
    try:
        lock.setStaleLockTime(5000)  # 5秒で陳腐化
    except Exception:
        pass

    # すでに他インスタンスがロックを保持しているなら、既存サーバへ送って終了
    if not lock.tryLock(1):
        # サーバ起動待ちのレースを考慮し、短時間リトライ
        files_cli = [a for a in argv[1:] if os.path.exists(a)]
        _log("secondary instance; will forward files=" + repr(files_cli))
        payload = json.dumps(files_cli).encode("utf-8")
        for _ in range(30):  # 約1.5秒
            sock = QtNetwork.QLocalSocket()
            sock.connectToServer(server_name, QtCore.QIODevice.WriteOnly)
            if sock.waitForConnected(100):
                try:
                    sock.write(payload)
                    sock.flush()
                    sock.waitForBytesWritten(200)
                    _log("client forwarded files OK")
                finally:
                    sock.disconnectFromServer()
                break
            QtCore.QThread.msleep(50)
        return 0

    # 最初のインスタンス: サーバを立て、後続プロセスの引数を受け取る
    try:
        QtNetwork.QLocalServer.removeServer(server_name)
    except Exception:
        pass

    files = [a for a in argv[1:] if os.path.exists(a)]
    _log("first instance files=" + repr(files))
    w = VideoPlayer(files=[])  # 初期は待機し、後でまとめて投入
    w.setWindowIcon(icon)
    w.show()

    server = QtNetwork.QLocalServer()
    server.listen(server_name)

    # --- 複数選択を1つの順序にまとめるためのバッファリング ---
    pending: List[str] = []
    flush_timer = QtCore.QTimer()
    flush_timer.setSingleShot(True)

    def natural_key(path: str):
        name = os.path.basename(path)
        parts = re.split(r"(\d+)", name)
        return [int(p) if p.isdigit() else p.casefold() for p in parts]

    def flush_pending():
        nonlocal pending
        if not pending:
            return
        # 重複排除しつつ決定的順序へ（同一フォルダ内は自然順、異なるフォルダはフォルダ名→ファイル名）
        uniq = []
        seen = set(x.casefold() for x in w.playlist)  # 既存分は重複追加しない
        for p in pending:
            cf = p.casefold()
            if cf not in seen:
                uniq.append(p)
                seen.add(cf)
        uniq.sort(key=lambda p: (os.path.dirname(p).casefold(), natural_key(p)))
        play_first = not getattr(w, "playlist", [])
        if uniq:
            w.add_to_playlist(uniq, play_first=play_first)
        pending = []

    def enqueue(files_in: List[str]):
        nonlocal pending
        if not files_in:
            return
        pending.extend(files_in)
        flush_timer.stop()
        flush_timer.timeout.connect(flush_pending)
        flush_timer.start(150)  # 少し待ってからまとめて投入

    # 起動時引数もバッファへ（Explorerが複数起動する場合に備える）
    enqueue(files)

    def on_new_conn() -> None:
        c = server.nextPendingConnection()
        if not c:
            return
        def handle_ready():
            data = bytes(c.readAll())
            try:
                arr = json.loads(data.decode("utf-8"))
                new_files = [a for a in arr if os.path.exists(a)]
                _log("server received files=" + repr(new_files))
                if new_files:
                    enqueue(new_files)
                    w.showNormal(); w.raise_(); w.activateWindow()
            except Exception:
                pass
            finally:
                c.disconnectFromServer()
        c.readyRead.connect(handle_ready)

    server.newConnection.connect(on_new_conn)

    return app.exec_()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
