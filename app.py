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

    log_message("argv=" + repr(argv))

    # --- 単一インスタンス制御 (ファイルベースIPC) ---
    temp_dir = QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.TempLocation)
    user_id = getpass.getuser()
    lock_path = os.path.join(temp_dir, f"wagom-player-{user_id}.lock")
    ipc_file_path = os.path.join(temp_dir, f"wagom-player-{user_id}.ipc")

    lock_file = QtCore.QLockFile(lock_path)
    lock_file.setStaleLockTime(0)

    # <<< 決定的なプライマリ/セカンダリの分岐 >>>
    if lock_file.tryLock(100):
        #
        # --- プライマリインスタンスの処理 ---
        #
        log_message("Primary instance: Lock acquired. Starting.")

        # 起動時に既存のIPCファイルをクリア
        if os.path.exists(ipc_file_path):
            try:
                os.remove(ipc_file_path)
            except OSError:
                pass

        # メインウィンドウとプレイリスト処理の準備
        player_window = VideoPlayer(files=[])
        player_window.setWindowIcon(icon)
        player_window.show()

        pending_files: List[str] = []
        flush_timer = QtCore.QTimer(player_window)
        flush_timer.setSingleShot(True)
        flush_timer.setInterval(300) # 少し長めに設定

        # flush_pending_filesを、診断ログを大量に追加した最終バージョンに置き換える
        def flush_pending_files():
            nonlocal pending_files
            if not pending_files: return

            log_message(f"--- Flush sequence started with {len(pending_files)} pending files. ---")

            try:
                # --- 容疑箇所 1: プレイリスト取得 ---
                log_message("Flush Step 1: Getting current playlist...")
                current_playlist = player_window.playlist
                current_playlist_set = set(p.casefold() for p in current_playlist)
                log_message(f"Flush Step 1 SUCCESS: Playlist has {len(current_playlist)} items.")

                # --- 容疑箇所 2: 重複排除 ---
                log_message("Flush Step 2: Building unique file list...")
                unique_files = []
                for f in pending_files:
                    f_norm = os.path.normpath(f)
                    if f_norm.casefold() not in current_playlist_set:
                        unique_files.append(f_norm)
                        current_playlist_set.add(f_norm.casefold())
                
                pending_files = []
                if not unique_files:
                    log_message("Flush Step 2 SUCCESS: No new unique files to add. Sequence finished.")
                    return
                log_message(f"Flush Step 2 SUCCESS: Found {len(unique_files)} new unique files.")

                # --- 容疑箇所 3: ソート ---
                log_message("Flush Step 3: Sorting unique files...")
                unique_files.sort(key=lambda p: (os.path.dirname(p).casefold(), natural_key(p)))
                log_message("Flush Step 3 SUCCESS: Sorting complete.")

                # --- 反復処理の準備 ---
                import functools
                files_to_add = unique_files
                total_files = len(files_to_add)
                is_first_addition_in_batch = not current_playlist

                def add_file_iteratively(index):
                    log_message(f"Inside add_file_iteratively, index={index}")
                    if index >= total_files:
                        log_message("Finished adding batch of files.")
                        player_window.showNormal(); player_window.raise_(); player_window.activateWindow()
                        return

                    file_path = files_to_add[index]
                    play_this_file = is_first_addition_in_batch and index == 0
                    
                    log_message(f"Attempting to add file {index + 1}/{total_files}: {file_path}")
                    player_window.add_to_playlist([file_path], play_first=play_this_file)
                    log_message(f"Successfully added file {index + 1}/{total_files}")

                    next_index = index + 1
                    QtCore.QTimer.singleShot(0, functools.partial(add_file_iteratively, next_index))

                log_message("Flush Step 4: Starting iterative adding process...")
                add_file_iteratively(0)

            except Exception as e:
                import traceback
                log_message("!!!!!!!!!! CRITICAL ERROR inside flush_pending_files !!!!!!!!!!")
                log_message(traceback.format_exc())
                raise # クラッシュさせる

        # flush_timerの接続先は変更なし
        flush_timer.timeout.connect(flush_pending_files)

        def enqueue_files(files: List[str]):
            if not files: return
            pending_files.extend(files)
            flush_timer.start()

        # IPCファイルの内容を処理する関数
        def process_ipc_file():
            if not os.path.exists(ipc_file_path):
                return
            
            try:
                with open(ipc_file_path, "r+", encoding='utf-8') as f:
                    lines = [line.strip() for line in f if line.strip()]
                    if lines:
                        log_message(f"IPC file changed. Read {len(lines)} files.")
                        f.seek(0)
                        f.truncate() # ファイルをクリア
                        valid_files = [path for path in lines if os.path.exists(path)]
                        enqueue_files(valid_files)
            except (IOError, OSError) as e:
                 log_message(f"Error processing IPC file: {e}")

        # ファイル監視を開始
        file_watcher = QtCore.QFileSystemWatcher([ipc_file_path])
        file_watcher.fileChanged.connect(process_ipc_file)

        # 起動時引数と、監視開始前に書き込まれた可能性のあるIPCファイルを処理
        initial_files = [a for a in argv[1:] if os.path.exists(a)]
        if initial_files:
            enqueue_files(initial_files)
        process_ipc_file() # 初期チェック

        result = app.exec_()
        lock_file.unlock()
        return result

    else:
        #
        # --- セカンダリインスタンスの処理 ---
        #
        log_message("Secondary instance: Lock busy. Appending to IPC file.")
        files_to_send = [a for a in argv[1:] if os.path.exists(a)]
        if files_to_send:
            try:
                # ファイルに追記するだけ
                with open(ipc_file_path, "a", encoding='utf-8') as f:
                    for path in files_to_send:
                        f.write(path + "\n")
            except (IOError, OSError) as e:
                log_message(f"Secondary instance could not write to IPC file: {e}")
                return 1 # エラー終了
        
        return 0 # 正常終了

if __name__ == "__main__":
    sys.exit(main_wrapper(sys.argv))