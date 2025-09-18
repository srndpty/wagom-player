import os
import sys
import re
from datetime import datetime
from typing import List

from PyQt5 import QtWidgets, QtCore

from wagom_player.logger import log_message
from wagom_player.theme import (
    apply_dark_theme,
    apply_app_icon,
    apply_windows_app_user_model_id,
)
from wagom_player.main_window import VideoPlayer

# ログメッセージ関数を一時的にオーバーライドしてPIDとタイムスタンプを追加
original_log_message = log_message

def log_message(msg):
    pid = os.getpid()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    original_log_message(f"[{timestamp}][PID:{pid:5d}] {msg}")

def main_wrapper(argv: List[str]) -> int:
    try:
        return main(argv)
    except Exception:
        import traceback
        app = QtWidgets.QApplication.instance()
        if app is None:
            app = QtWidgets.QApplication(sys.argv)

        error_title = "Wagom Player - 致命的なエラー"
        error_message = "予期せぬエラーが発生したため、アプリケーションを終了します。"
        detailed_text = traceback.format_exc()
        log_message("!!!!!!!!!! UNHANDLED EXCEPTION !!!!!!!!!!")
        log_message(detailed_text)

        msg_box = QtWidgets.QMessageBox()
        msg_box.setIcon(QtWidgets.QMessageBox.Critical)
        msg_box.setText(error_message)
        msg_box.setInformativeText("エラーの詳細はログファイルに記録されました。")
        msg_box.setWindowTitle(error_title)
        msg_box.setDetailedText(detailed_text)
        msg_box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        msg_box.exec_()
        return 1

def main(argv: List[str]) -> int:
    # --- 基本的なアプリケーション設定 ---
    app = QtWidgets.QApplication(argv)
    QtCore.QCoreApplication.setOrganizationName("wagom")
    QtCore.QCoreApplication.setApplicationName("wagom-player")
    apply_dark_theme(app)
    apply_windows_app_user_model_id("wagom-player")
    icon = apply_app_icon(app)

    # ### 変更点: IPC関連のロジックをすべて削除 ###
    
    # コマンドライン引数から、最初に存在するファイルパスを取得する
    # 複数ファイルが渡されても、最初の1つだけを対象とする
    initial_file = None
    for arg in argv[1:]:
        if os.path.exists(arg) and os.path.isfile(arg):
            initial_file = arg
            break

    # VideoPlayerウィンドウを作成し、単一のファイルパスを渡す
    print(f"Initial file: {initial_file}")
    player_window = VideoPlayer(file=initial_file)
    player_window.setWindowIcon(icon)
    player_window.show()

    return app.exec_()

if __name__ == "__main__":
    sys.exit(main_wrapper(sys.argv))