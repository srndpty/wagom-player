import os
import sys
import json
import getpass
import re
from datetime import datetime
from typing import List

from PyQt5 import QtWidgets, QtCore, QtNetwork

from wagom_player.logger import log_message
from wagom_player.theme import apply_dark_theme, apply_app_icon, apply_windows_app_user_model_id
from wagom_player.main_window import VideoPlayer

# --- ユーティリティ関数 ---
import time

# ログメッセージ関数を一時的にオーバーライドしてPIDとタイムスタンプを追加
original_log_message = log_message
def log_message(msg):
    pid = os.getpid()
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    original_log_message(f"[{timestamp}][PID:{pid:5d}] {msg}")

def natural_key(path: str):
    """ファイル名を自然順ソートするためのキーを生成する (例: 2.mp4 < 10.mp4)"""
    name = os.path.basename(path)
    parts = re.split(r'(\d+)', name)
    return [int(p) if p.isdigit() else p.casefold() for p in parts]

# --- メイン処理 ---
def main_wrapper(argv: List[str]) -> int:
    try:
        main(argv)
        return 0
    except Exception as e:
        import traceback
        log_message("!!!!!!!!!! UNHANDLED EXCEPTION !!!!!!!!!!")
        log_message(traceback.format_exc())
        # エラーダイアログを表示するなどの処理
        return 1
    
def main(argv: List[str]) -> int:
    # --- 基本的なアプリケーション設定 ---
    app = QtWidgets.QApplication(argv)
    QtCore.QCoreApplication.setOrganizationName("wagom")
    QtCore.QCoreApplication.setApplicationName("wagom-player")
    apply_dark_theme(app)
    apply_windows_app_user_model_id("wagom-player")
    icon = apply_app_icon(app)

    # --- 単一インスタンス制御 (ファイルベースIPC) ---
    temp_dir = QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.TempLocation)
    user_id = getpass.getuser()
    lock_path = os.path.join(temp_dir, f"wagom-player-{user_id}.lock")
    ipc_file_path = os.path.join(temp_dir, f"wagom-player-{user_id}.ipc")

    # ★★★ 新ロジック Step 1: 全プロセスが自身の引数をIPCファイルに書き込む ★★★
    # 自分に渡されたファイル引数をIPCファイルに追記する
    files_to_send = [a for a in argv[1:] if os.path.exists(a)]
    if files_to_send:
        log_message(f"Instance started with {len(files_to_send)} file(s). Attempting to write to IPC.")
        try:
            with open(ipc_file_path, "a", encoding='utf-8') as f:
                for path in files_to_send:
                    f.write(path + "\n")
            log_message("Successfully wrote to IPC file.")
        except (IOError, OSError) as e:
            # ここで失敗しても致命的ではないのでログに残すだけ
            log_message(f"Process could not write to IPC file: {e}")

    # --- プライマリ/セカンダリの分岐 ---
    lock_file = QtCore.QLockFile(lock_path)
    lock_file.setStaleLockTime(0)

    log_message("Attempting to acquire lock...")
    if lock_file.tryLock(100):
        #
        # --- プライマリインスタンスの処理 ---
        #
        log_message("Primary instance: Lock acquired. Starting.")

        player_window = VideoPlayer(files=[])
        player_window.setWindowIcon(icon)
        player_window.show()

        pending_files: List[str] = []
        flush_timer = QtCore.QTimer(player_window)
        flush_timer.setSingleShot(True)
        flush_timer.setInterval(300)

        def flush_pending_files():
            nonlocal pending_files
            if not pending_files: return
            
            # (この関数の中身は変更なし)
            log_message(f"FLUSH: Timer fired. Processing {len(pending_files)} pending files.")
            current_playlist = player_window.playlist
            current_playlist_set = set(p.casefold() for p in current_playlist)
            unique_files = []
            for f in pending_files:
                f_norm = os.path.normpath(f)
                if f_norm.casefold() not in current_playlist_set:
                    unique_files.append(f_norm)
                    current_playlist_set.add(f_norm.casefold())
            
            pending_files = []
            if not unique_files: return

            unique_files.sort(key=lambda p: (os.path.dirname(p).casefold(), natural_key(p)))
            
            import functools
            files_to_add = unique_files
            total_files = len(files_to_add)
            is_first_addition_in_batch = not current_playlist

            def add_file_iteratively(index):
                if index >= total_files:
                    log_message("Finished adding batch of files.")
                    player_window.showNormal(); player_window.raise_(); player_window.activateWindow()
                    return

                file_path = files_to_add[index]
                play_this_file = is_first_addition_in_batch and index == 0
                player_window.add_to_playlist([file_path], play_first=play_this_file)
                next_index = index + 1
                QtCore.QTimer.singleShot(0, functools.partial(add_file_iteratively, next_index))
            
            add_file_iteratively(0)

        flush_timer.timeout.connect(flush_pending_files)

        def process_ipc_file():
            if not os.path.exists(ipc_file_path): return
            
            try:
                log_message("IPC: Watcher triggered or initial call. Reading IPC file...")
                with open(ipc_file_path, "r+", encoding='utf-8') as f:
                    lines = [line.strip() for line in f if line.strip()]
                    if lines:
                        log_message(f"IPC file processed. Read {len(lines)} files.")
                        f.seek(0)
                        f.truncate()
                        valid_files = [path for path in lines if os.path.exists(path)]
                        
                        # ★★★ 新ロジック Step 2: 処理キューに入れるだけ ★★★
                        nonlocal pending_files
                        if valid_files:
                            pending_files.extend(valid_files)
                            log_message(f"IPC: Added {len(valid_files)} files to queue. Total pending: {len(pending_files)}. Restarting flush timer.")
                            flush_timer.start() # タイマーを起動/再起動
                    else:
                        log_message("IPC: File was empty.")
            except (IOError, OSError) as e:
                 log_message(f"Error processing IPC file: {e}")

        # ★★★ 新ロジック Step 3: ファイルウォッチャーは将来の変更のためだけに使う ★★★
        file_watcher = QtCore.QFileSystemWatcher([ipc_file_path])
        file_watcher.fileChanged.connect(process_ipc_file)

        # ★★★ 修正ロジック: 起動直後に短いディレイを挟んでから初回処理を行う ★★★
        # これにより、同時に起動された他のプロセスがIPCファイルに書き込む時間を確保する。
        # 以前の process_ipc_file() の直接呼び出しをこのタイマーに置き換える。
        # 150ミリ秒もあれば、ほとんどのケースで全プロセスが書き込みを完了できるはず。
        QtCore.QTimer.singleShot(150, process_ipc_file)
        # process_ipc_file()
        
        # もしIPCファイルが空で、何も処理が始まらなかった場合の保険
        if not pending_files:
            flush_timer.start()

        result = app.exec_()
        lock_file.unlock()
        return result

    else:
        #
        # --- セカンダリインスタンスの処理 ---
        #
        # ★★★ 新ロジック Step 5: セカンダリは書き込んだら即終了 ★★★
        log_message("Secondary instance: Appended to IPC file and exiting.")
        return 0

if __name__ == "__main__":
    sys.exit(main_wrapper(sys.argv))