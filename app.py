import os
import sys
import json
import getpass
from typing import List

from PyQt5 import QtWidgets, QtCore

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

    # 単一インスタンス: 既存インスタンスがいれば引数を送って終了
    server_name = f"wagom-player-{getpass.getuser()}"
    sock = QtCore.QLocalSocket()
    sock.connectToServer(server_name, QtCore.QIODevice.WriteOnly)
    if sock.waitForConnected(100):
        try:
            payload = json.dumps([a for a in argv[1:] if os.path.exists(a)]).encode("utf-8")
            sock.write(payload)
            sock.flush()
            sock.waitForBytesWritten(200)
        finally:
            sock.disconnectFromServer()
        return 0

    # 最初のインスタンス: サーバを立て、後続プロセスの引数を受け取る
    try:
        QtCore.QLocalServer.removeServer(server_name)
    except Exception:
        pass

    files = [a for a in argv[1:] if os.path.exists(a)]
    w = VideoPlayer(files=files)
    w.setWindowIcon(icon)
    w.show()

    server = QtCore.QLocalServer()
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
