import os
import sys
import json
import getpass
from datetime import datetime
from typing import List

from PyQt5 import QtWidgets, QtCore, QtNetwork

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
    sock = QtNetwork.QLocalSocket()
    sock.connectToServer(server_name, QtCore.QIODevice.WriteOnly)
    if sock.waitForConnected(100):
        try:
            files_cli = [a for a in argv[1:] if os.path.exists(a)]
            _log("client connected; send files=" + repr(files_cli))
            payload = json.dumps(files_cli).encode("utf-8")
            sock.write(payload)
            sock.flush()
            sock.waitForBytesWritten(200)
        finally:
            sock.disconnectFromServer()
        return 0

    # 最初のインスタンス: サーバを立て、後続プロセスの引数を受け取る
    try:
        QtNetwork.QLocalServer.removeServer(server_name)
    except Exception:
        pass

    files = [a for a in argv[1:] if os.path.exists(a)]
    _log("first instance files=" + repr(files))
    w = VideoPlayer(files=files)
    w.setWindowIcon(icon)
    w.show()

    server = QtNetwork.QLocalServer()
    server.listen(server_name)

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
                    play_first = not getattr(w, "playlist", [])
                    w.add_to_playlist(new_files, play_first=play_first)
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
