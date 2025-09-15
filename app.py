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
        forwarded = False
        for _ in range(160):  # 約1.5秒
            sock = QtNetwork.QLocalSocket()
            sock.connectToServer(server_name, QtCore.QIODevice.WriteOnly)
            if sock.waitForConnected(100):
                try:
                    sock.write(payload)
                    sock.flush()
                    sock.waitForBytesWritten(200)
                    _log("client forwarded files OK")
                    forwarded = True
                finally:
                    sock.disconnectFromServer()
                break
            QtCore.QThread.msleep(50)
        if forwarded:
            return 0
        # ここまで来たらサーバが存在しない可能性が高い→スタレロックを除去して一次インスタンスとして継続
        try:
            if hasattr(lock, "removeStaleLock"):
                lock.removeStaleLock()
        except Exception:
            pass
        # 念のためロック再取得を試みる（失敗しても続行）
        try:
            lock.tryLock(0)
        except Exception:
            pass

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
    flush_timer = QtCore.QTimer(w)
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
        flush_timer.start(800)  # 少し待ってからまとめて投入（安定化）

    # 一度だけハンドラを接続
    flush_timer.timeout.connect(flush_pending)

    # 起動時引数はそのまま投入（%*で一括渡し時は即反映される）
    if files:
        files_sorted = sorted(files, key=lambda p: (os.path.dirname(p).casefold(), natural_key(p)))
        w.add_to_playlist(files_sorted, play_first=True)

    socket_buffers: dict = {}

    def on_new_conn() -> None:
        c = server.nextPendingConnection()
        if not c:
            return
        try:
            c.setParent(server)
        except Exception:
            pass
        socket_buffers[c] = bytearray()

        def on_ready():
            try:
                socket_buffers[c] += bytes(c.readAll())
            except Exception:
                pass

        def on_done():
            # 切断直前に届いた未処理データも取り込む
            try:
                socket_buffers[c] += bytes(c.readAll())
            except Exception:
                pass
            data = socket_buffers.pop(c, b"")
            try:
                arr = json.loads(bytes(data).decode("utf-8", errors="ignore")) if data else []
            except Exception:
                arr = []
            new_files = [a for a in arr if os.path.exists(a)]
            _log("server received files=" + repr(new_files))
            if new_files:
                enqueue(new_files)
                w.showNormal(); w.raise_(); w.activateWindow()
            try:
                c.deleteLater()
            except Exception:
                pass

        c.readyRead.connect(on_ready)
        c.disconnected.connect(on_done)

    server.newConnection.connect(on_new_conn)

    return app.exec_()


if __name__ == "__main__":
    sys.exit(main(sys.argv))


