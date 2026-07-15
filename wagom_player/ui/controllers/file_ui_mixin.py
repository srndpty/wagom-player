import os
import threading
from typing import Optional

from PyQt5 import QtCore, QtWidgets

from ...application.file_actions import (
    CollisionResolution,
    InvalidMoveTargetError,
    TargetFileExistsError,
    target_path_for_subfolder,
    validate_move_to_subfolder,
)
from ...domain.playlist import next_path as next_playlist_path
from ...infrastructure import diagnostics
from ...infrastructure.logger import log_message


class FileUiMixin:
    def _release_current_media_for_file_operation(self) -> bool:
        """ファイル操作のため再生を止め、メディアを解放する。

        解放が完了したら ``True``、タイムアウトで完了を確認できなかった場合は
        ``False`` を返す。``False`` のときは、呼び出し側はファイル操作・次再生を
        中止すること。
        """
        log_message("ファイルロックを解放するため再生を停止します。")
        released = self._stop_and_clear_media_without_blocking_ui()
        # UI（オーバーレイ・シークバー等）の後始末はメインスレッドで行う
        self._apply_stopped_ui_state()
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.ExcludeUserInputEvents)
        return released is True

    def _stop_and_clear_media_without_blocking_ui(
        self,
        timeout_ms: int = 8000,
        context: str = "move_current_file_stop",
        clear_media: bool = True,
    ) -> Optional[bool]:
        """VLC の停止をワーカースレッドで行い、UI を固めずに完了を待つ。

        VLC の同期 ``stop()`` は埋め込みビデオウィンドウの破棄を伴い、その破棄完了を
        メインスレッドのウィンドウメッセージ処理に依存する。そのままメインスレッドで
        呼ぶとデッドロック（応答なし）になるため、``stop()`` はワーカースレッドで実行し、
        メインスレッドはイベントループをポンプし続ける。

        ワーカーから呼ぶのは ``VlcPlayerAdapter.stop()`` だけで、これは純粋な libVLC
        呼び出し（+ スレッドセーフな diagnostics）のみで Qt の QWidget / signal / UI
        状態には一切触れない、という前提に依存している。

        ``clear_media`` が有効な場合、``set_media(None)`` は **メインスレッドで、かつ
        stop 完了後にのみ** 実行する。
        こうすることで、タイムアウト後に遅れて生き残ったワーカーが、後から再生し直した
        新しいメディアを ``set_media(None)`` で消してしまう事故を防ぐ。さらに timeout
        時は player 自体を差し替え、遅延した ``stop()`` の影響を古い player に閉じ込める。

        戻り値は stop 完了を確認できたら ``True``、``timeout_ms`` 以内に完了を確認
        できなければ ``False``。別の stop が進行中なら ``None`` を返し、呼び出し側は
        同じ player に対する後続処理を中止すること。
        """
        if self._vlc_stop_in_progress:
            log_message(f"[release] duplicate VLC stop ignored: context={context}")
            return None

        done = threading.Event()
        vlc_player = self.vlc_player
        generation = self._vlc_generation

        def _worker() -> None:
            # libVLC 呼び出しのみ。Qt オブジェクトには触れないこと。
            try:
                vlc_player.stop(context=context)
            finally:
                done.set()

        thread = threading.Thread(target=_worker, name="vlc-release", daemon=True)
        log_message(f"[release] starting VLC stop on worker thread: context={context}")
        self._vlc_stop_in_progress = True
        try:
            thread.start()

            deadline = QtCore.QDateTime.currentMSecsSinceEpoch() + timeout_ms
            while not done.wait(0):
                # ウィンドウメッセージは処理し続ける。ただし、この間に発火する UI
                # タイマーは _vlc_stop_in_progress を見て VLC への問い合わせを避ける。
                QtWidgets.QApplication.processEvents(
                    QtCore.QEventLoop.ExcludeUserInputEvents,
                    50,
                )
                if QtCore.QDateTime.currentMSecsSinceEpoch() >= deadline:
                    log_message(f"[release] VLC stop timed out: context={context}")
                    diagnostics.record_breadcrumb(
                        "vlc_release_timeout_recreate_player", context=context
                    )
                    # old player/instance は worker closure が保持する。明示 release は行わず、
                    # 遅延 stop の影響を fresh player への差し替えと generation guard で隔離する。
                    log_message("[release] stale VLC player may remain until delayed stop finishes")
                    self._create_fresh_vlc_player()
                    return False

            # stop 完了をメインスレッドで確認してから、メインスレッドでメディアを解放する。
            if self.vlc_player is vlc_player and self._vlc_generation == generation:
                if clear_media:
                    vlc_player.set_media(None, context=f"{context}_clear_media")
                    log_message(f"[release] VLC stop finished; media cleared: context={context}")
                else:
                    log_message(f"[release] VLC stop finished; media preserved: context={context}")
            else:
                log_message("[release] player changed while releasing; skip clear_media")
            return True
        finally:
            self._vlc_stop_in_progress = False

    def _prompt_target_file_exists(
        self,
        file_name: str,
        subfolder_name: str,
    ) -> CollisionResolution:
        """移動先に同名ファイルがある場合の対応をユーザーに尋ねる。

        現在のファイルを破棄、別名で移動、キャンセルのいずれかを返す。
        """
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setWindowTitle("移動先に同名ファイルが存在します")
        box.setText(
            f"移動先フォルダ '{subfolder_name}' に同名のファイル\n'{file_name}' が既に存在します。"
        )
        box.setInformativeText("どうしますか？")
        if self.trash_service.available:
            delete_button = box.addButton(
                "現在のファイルをごみ箱へ移動",
                QtWidgets.QMessageBox.DestructiveRole,
            )
        else:
            delete_button = None
            box.setInformativeText("ごみ箱機能が利用できないため、現在のファイルは削除できません。")
        rename_button = box.addButton("別名で移動保存", QtWidgets.QMessageBox.AcceptRole)
        cancel_button = box.addButton("キャンセル", QtWidgets.QMessageBox.RejectRole)
        box.setDefaultButton(cancel_button)
        log_message(f"[DEBUG move] Showing target-exists dialog for '{file_name}'.")
        box.exec_()
        log_message("[DEBUG move] target-exists dialog closed.")

        clicked = box.clickedButton()
        if delete_button is not None and clicked is delete_button:
            log_message("[DEBUG move] dialog choice = delete")
            return CollisionResolution.DISCARD
        if clicked is rename_button:
            log_message("[DEBUG move] dialog choice = rename")
            return CollisionResolution.RENAME
        log_message("[DEBUG move] dialog choice = cancel")
        return CollisionResolution.CANCEL

    def _move_current_file_and_play_next(self, subfolder_name: str):
        """現在再生中のファイルを指定されたサブフォルダに移動し、次の曲を再生する"""
        diagnostics.record_breadcrumb("move_current_file_requested", subfolder=subfolder_name)
        if self._file_operation_in_progress:
            log_message("別のファイル操作中のため、移動要求を無視します。")
            return

        # 再生中でない、またはプレイリストが空の場合は何もしない
        if not (0 <= self.current_index < len(self.directory_playlist)):
            log_message("再生中のファイルがないため、移動要求を無視します。")
            return

        # --- 重要な情報を先に保存しておく ---
        index_to_remove = self.current_index
        current_file_path = self.directory_playlist[index_to_remove]
        diagnostics.record_breadcrumb(
            "move_current_file_start",
            path=current_file_path,
            subfolder=subfolder_name,
            index=index_to_remove,
        )

        try:
            self._file_operation_in_progress = True

            # ★ シャッフル時に「シャッフル順の次」を覚えておく
            next_path = None
            if self.shuffle_enabled:
                playlist = self._get_current_playlist()
                next_path = next_playlist_path(playlist, current_file_path)

            # --- ファイルパスの準備 ---
            file_name = os.path.basename(current_file_path)
            collision_resolution: Optional[CollisionResolution] = None
            try:
                target_file_path = validate_move_to_subfolder(current_file_path, subfolder_name)
            except TargetFileExistsError:
                existing_target = target_path_for_subfolder(current_file_path, subfolder_name)
                log_message(f"移動先に同名ファイルが存在するため確認します: '{file_name}'")
                diagnostics.record_breadcrumb(
                    "move_current_file_target_exists", target=existing_target
                )
                collision_resolution = self._prompt_target_file_exists(file_name, subfolder_name)
                diagnostics.record_breadcrumb(
                    "move_current_file_collision_choice", choice=collision_resolution
                )
                target_file_path = None  # 実際の移動先は解決方法に応じて後で決める
                if collision_resolution == CollisionResolution.CANCEL:
                    log_message(f"ユーザーがファイル移動をキャンセルしました: '{file_name}'")
                    self._show_status_message("移動をキャンセルしました", 4000)
                    return
            except (FileNotFoundError, InvalidMoveTargetError) as e:
                log_message(f"移動前の検証に失敗しました: {e}")
                self._show_status_message(f"移動失敗: {e}", 5000)
                diagnostics.record_breadcrumb("move_current_file_validation_error", error=str(e))
                return

            # 検証が通ってから、VLCプレイヤーを完全に停止してファイルロックを解放する。
            # タイムアウトで解放を確認できなかった場合、遅延ワーカーが後続再生を壊さない
            # よう、ここで中止する。
            if not self._release_current_media_for_file_operation():
                log_message("メディア解放がタイムアウトしたため、ファイル操作を中止します。")
                self._show_status_message(
                    "移動失敗: 再生中ファイルの解放が完了しませんでした", 5000
                )
                diagnostics.record_breadcrumb("move_current_file_release_timeout")
                return

            # --- 移動（または削除）処理 ---
            try:
                resolution = (
                    collision_resolution
                    if collision_resolution is not None
                    else CollisionResolution.MOVE
                )
                try:
                    result = self.file_operation_controller.execute(
                        current_file_path,
                        subfolder_name,
                        resolution,
                    )
                except Exception as e:
                    if resolution != CollisionResolution.DISCARD:
                        raise
                    log_message(f"ごみ箱への移動に失敗しました: {e}")
                    self._show_status_message(
                        f"ごみ箱への移動に失敗: {e}（再生は停止しました）",
                        5000,
                    )
                    diagnostics.record_breadcrumb("move_current_file_trash_error", error=str(e))
                    return

                target_file_path = result.target_path
                if resolution == CollisionResolution.DISCARD:
                    log_message(
                        f"移動先に同名ファイルがあるため、ごみ箱へ移動しました: "
                        f"'{current_file_path}'"
                    )
                    self._show_status_message(
                        f"ごみ箱へ移動: {file_name}（移動先に同名ファイルが存在）",
                        4000,
                    )
                    diagnostics.record_breadcrumb(
                        "move_current_file_source_discarded", source=current_file_path
                    )
                elif resolution == CollisionResolution.RENAME:
                    log_message(f"別名でファイルを移動します: '{file_name}' -> '{subfolder_name}'")
                    moved_name = os.path.basename(target_file_path)
                    self._show_status_message(
                        f"別名で移動完了: {file_name} -> {subfolder_name}/{moved_name}", 4000
                    )
                    log_message(f"ファイルを移動しました: '{target_file_path}'")
                    diagnostics.record_breadcrumb(
                        "move_current_file_success",
                        source=current_file_path,
                        target=target_file_path,
                    )
                else:
                    log_message(f"ファイルを移動します: '{file_name}' -> '{subfolder_name}'")
                    self._show_status_message(f"移動完了: {file_name} -> {subfolder_name}", 4000)
                    log_message(f"ファイルを移動しました: '{target_file_path}'")
                    diagnostics.record_breadcrumb(
                        "move_current_file_success",
                        source=current_file_path,
                        target=target_file_path,
                    )

            except TargetFileExistsError:
                log_message(f"移動先に同名ファイルが存在するため移動しません: '{file_name}'")
                self._show_status_message(f"移動失敗: {file_name}は移動先に既に存在します", 5000)
                diagnostics.record_breadcrumb(
                    "move_current_file_target_exists", target=target_file_path
                )
                # ファイルが存在した場合、次の曲の再生は行わずに待機する
                return
            except Exception as e:
                log_message(f"ファイルの移動に失敗しました: {e}")
                self._show_status_message(f"ファイル移動中にエラーが発生しました: {e}", 5000)
                diagnostics.record_breadcrumb("move_current_file_error", error=str(e))
                # エラーが発生した場合も、次の曲の再生は行わずに待機する
                return

            # --- プレイリストの更新と次の曲の再生 ---

            next_index = self.playlist_session.remove_current(next_path)

            # ウィンドウタイトルの表示を更新
            self._update_window_title()

            # もう再生できるものがない
            if not self.directory_playlist:
                log_message("プレイリストが空になったため、停止状態を維持します。")
                self.stop()
                return

            if next_index is None:
                log_message("次の項目がないため、停止状態を維持します。")
                self.stop()
            else:
                log_message(f"次の項目を再生します: index={next_index}")
                QtCore.QTimer.singleShot(50, lambda idx=next_index: self.play_at(idx))
        finally:
            self._file_operation_in_progress = False
