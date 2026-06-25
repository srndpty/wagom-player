import os
import sys
import time
from datetime import datetime
from typing import Optional

from PyQt5 import QtCore, QtWidgets

from wagom_player import diagnostics
from wagom_player.logger import log_message
from wagom_player.single_instance import (
    SingleInstanceServer,
    acquire_primary_instance_lock,
    create_single_instance_server,
    send_to_existing_instance,
)
from wagom_player.theme import (
    apply_app_icon,
    apply_dark_theme,
    apply_windows_app_user_model_id,
)
from wagom_player.ui.main_window import VideoPlayer

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


def _forward_or_take_over(
    initial_file: Optional[str],
    lock,
    attempts: int = 20,
    interval_ms: int = 50,
) -> bool:
    """primary へ転送する。primary は mutex 取得直後でまだ IPC サーバを listen して
    いないことがあるため、接続できるまで短くリトライする(最大 attempts*interval_ms ms)。

    リトライ中に primary が異常終了して mutex の所有権が解放された場合、二次プロセスの
    うち 1 つだけが ``try_become_primary()`` で所有権を獲得し ``lock.is_primary`` が
    True になる(=ホストを引き継ぐ)。所有権で直列化されるため、乗っ取り時もホストは
    1 つだけになり、複数が listen() レースに戻ることはない。

    戻り値: 転送できたら True。False の場合は ``lock.is_primary`` がホストを引き継いだ
    かどうか(True ならホスト化、False なら終了)を表す。
    """
    for _ in range(attempts):
        if send_to_existing_instance(initial_file):
            return True
        if lock.try_become_primary():
            return False
        time.sleep(interval_ms / 1000)
    return False


def _claim_via_send_listen(initial_file: Optional[str], lock):
    """既存 IPC を優先しつつホストを確保する(送信→排他 listen→再送)。

    mutex primary でも旧バイナリや mutex 不可 fallback で起動済みの IPC サーバが
    ありうるため、stale 削除つき listen の前に既存 IPC への送信と排他 listen を試す。
    """
    if send_to_existing_instance(initial_file):
        log_message("Existing wagom-player instance found. Forwarded request and exiting.")
        return None, True, lock
    single_instance_server = create_single_instance_server(remove_stale=False)
    if single_instance_server is not None:
        return single_instance_server, False, lock
    if send_to_existing_instance(initial_file):
        log_message("Existing wagom-player instance found. Forwarded request and exiting.")
        return None, True, lock
    single_instance_server = create_single_instance_server(remove_stale=True)
    if single_instance_server is None:
        if send_to_existing_instance(initial_file):
            log_message("Existing wagom-player instance found. Forwarded request and exiting.")
            return None, True, lock
        log_message("Single-instance server unavailable; continuing without IPC.")
    return single_instance_server, False, lock


def _claim_single_instance(initial_file: Optional[str]):
    """所有権ベースの mutex でホストを 1 つに選び、転送するか IPC サーバを確保する。

    返り値は ``(server, forwarded, lock)``。``lock`` はホストである限り保持し続ける
    必要があるため、呼び出し側がプロセス終了まで参照を維持する。
    """
    lock = acquire_primary_instance_lock()
    if not lock.available:
        # mutex が使えない(非 Windows / CreateMutexW 失敗)。常に primary 扱いになって
        # 単一インスタンス制御が無効化されるのを避けるため、send/listen 調停に戻す。
        return _claim_via_send_listen(initial_file, lock)
    if not lock.is_primary:
        # 既存インスタンスが居る/起動中。listen 完了までリトライしつつ転送。
        # primary が落ちたら、この中で所有権を取り直して 1 つだけが引き継ぐ。
        if _forward_or_take_over(initial_file, lock):
            log_message("Existing wagom-player instance found. Forwarded request and exiting.")
            return None, True, lock
        if lock.is_primary:
            log_message("Primary instance exited; taking over as primary instance.")
        else:
            # 所有権を取れない(primary が生存したまま応答しない等)。このまま続行すると
            # primary が生きたまま別ウィンドウを開くため、二次プロセスは終了する。
            log_message("Primary instance unresponsive; exiting secondary instance.")
            return None, True, lock

    return _claim_via_send_listen(initial_file, lock)


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
    single_instance_server, forwarded, instance_lock = _claim_single_instance(initial_file)
    if forwarded:
        instance_lock.release()
        return 0

    # ホストである限り mutex を保持し続ける必要があるため、app に紐付けて生かす。
    app._single_instance_lock = instance_lock

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
