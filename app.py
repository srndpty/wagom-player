import os
import sys
from datetime import datetime
from typing import Optional

from PyQt5 import QtCore, QtWidgets

from wagom_player import diagnostics
from wagom_player.logger import log_message
from wagom_player.main_window import VideoPlayer
from wagom_player.single_instance import (
    SingleInstanceServer,
    create_single_instance_server,
    send_to_existing_instance,
)
from wagom_player.theme import (
    apply_app_icon,
    apply_dark_theme,
    apply_windows_app_user_model_id,
)

# ログメッセージ関数を一時的にオーバーライドしてPIDとタイムスタンプを追加
original_log_message = log_message


def log_message(msg):
    pid = os.getpid()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    original_log_message(f"[{timestamp}][PID:{pid:5d}] {msg}")


def _find_initial_file(argv: list[str]) -> Optional[str]:
    """コマンドライン引数から、最初に存在するファイルパスを取得する。"""
    for arg in argv[1:]:
        if os.path.exists(arg) and os.path.isfile(arg):
            return arg
    return None


def _configure_runtime_environment() -> None:
    if getattr(sys, "frozen", False):
        os.chdir(os.path.dirname(sys.executable))

    log_message(f"argv={sys.argv!r}")
    log_message(f"cwd={os.getcwd()!r}")
    log_message(f"executable={sys.executable!r}")
    log_message(f"frozen={bool(getattr(sys, 'frozen', False))}")
    log_message(f"PYTHON_VLC_LIB_PATH={os.environ.get('PYTHON_VLC_LIB_PATH', '')!r}")


def _claim_single_instance(initial_file: Optional[str]):
    """既存プロセスへ転送するか、このプロセス用の IPC サーバを確保する。"""
    if send_to_existing_instance(initial_file):
        log_message("Existing wagom-player instance found. Forwarded request and exiting.")
        return None, True

    single_instance_server = create_single_instance_server(remove_stale=False)
    if single_instance_server is not None:
        return single_instance_server, False

    # 同時起動時は、最初の送信時点ではサーバ未作成でも、この時点で他方が作成済みの
    # ことがある。stale socket を消す前に再送して、稼働中のインスタンスを壊さない。
    if send_to_existing_instance(initial_file, timeout_ms=1000):
        log_message("Existing wagom-player instance appeared. Forwarded request and exiting.")
        return None, True

    single_instance_server = create_single_instance_server(remove_stale=True)
    if single_instance_server is not None:
        return single_instance_server, False

    if send_to_existing_instance(initial_file, timeout_ms=1000):
        log_message("Existing wagom-player instance found after retry. Forwarded request.")
        return None, True

    log_message("Single-instance server unavailable; continuing without IPC.")
    return None, False


def main_wrapper(argv: list[str]) -> int:
    diagnostics.start_session(argv)
    diagnostics.install_excepthook()
    try:
        return main(argv)
    except Exception as e:
        import traceback

        app = QtWidgets.QApplication.instance()
        if app is None:
            app = QtWidgets.QApplication(sys.argv)

        error_title = "Wagom Player - 致命的なエラー"
        error_message = "予期せぬエラーが発生したため、アプリケーションを終了します。"
        detailed_text = traceback.format_exc()
        log_message("!!!!!!!!!! UNHANDLED EXCEPTION !!!!!!!!!!")
        log_message(detailed_text)
        try:
            diagnostics.write_exception_report(type(e), e, e.__traceback__)
        except Exception:
            pass

        msg_box = QtWidgets.QMessageBox()
        msg_box.setIcon(QtWidgets.QMessageBox.Critical)
        msg_box.setText(error_message)
        msg_box.setInformativeText("エラーの詳細はログファイルに記録されました。")
        msg_box.setWindowTitle(error_title)
        msg_box.setDetailedText(detailed_text)
        msg_box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        msg_box.exec_()
        return 1


def _create_application(argv: list[str]) -> QtWidgets.QApplication:
    app = QtWidgets.QApplication(argv)
    QtCore.QCoreApplication.setOrganizationName("wagom")
    QtCore.QCoreApplication.setApplicationName("wagom-player")
    return app


def _create_player_window(initial_file: Optional[str]) -> VideoPlayer:
    diagnostics.heartbeat()
    diagnostics.start_hang_monitor()
    return VideoPlayer(file=initial_file)


def main(argv: list[str]) -> int:
    _configure_runtime_environment()
    app = _create_application(argv)
    initial_file = _find_initial_file(argv)
    log_message(f"initial_file={initial_file!r}")
    single_instance_server, forwarded = _claim_single_instance(initial_file)
    if forwarded:
        return 0

    apply_dark_theme(app)
    apply_windows_app_user_model_id("wagom-player")
    icon = apply_app_icon(app)

    player_window = _create_player_window(initial_file)
    player_window.setWindowIcon(icon)
    if single_instance_server is not None:
        instance_ipc = SingleInstanceServer(single_instance_server)
        instance_ipc.file_requested.connect(player_window.open_external_file)
        app._single_instance_server = instance_ipc
    player_window.show()

    return app.exec_()


if __name__ == "__main__":
    sys.exit(main_wrapper(sys.argv))
