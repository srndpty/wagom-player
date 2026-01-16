import os
import sys
import shutil
import re
import ctypes
import functools
import locale
from typing import List, Optional

from PyQt5 import QtCore, QtGui, QtWidgets

from .seek_slider import SeekSlider
from .theme import resource_path
from .logger import log_message

try:
    import vlc
except ImportError as e:
    raise SystemExit(
        "python-vlc が見つかりません。`pip install python-vlc` を実行してください"
    ) from e

SUPPORTED_VIDEO_EXTENSIONS = (
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".ts",
    ".m4v",
    ".3gp",
    ".3g2",
    ".mpeg",
    ".mpg",
    ".mpe",
    ".rm",
    ".rmvb",
    ".vob",
    ".webm",
)

def natural_key(path: str):
    """ファイル名を自然順ソートするためのキーを生成する (例: 2.mp4 < 10.mp4)"""
    name = os.path.basename(path)
    parts = re.split(r"(\d+)", name)
    return [int(p) if p.isdigit() else p.casefold() for p in parts]


def _load_windows_logical_comparer():
    if not sys.platform.startswith("win"):
        return None

    try:
        shlwapi = ctypes.windll.Shlwapi
    except Exception:
        return None

    try:
        cmp_func = shlwapi.StrCmpLogicalW
        cmp_func.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        cmp_func.restype = ctypes.c_int
    except Exception:
        return None

    return cmp_func


_STRCMP_LOGICALW = _load_windows_logical_comparer()


def _create_windows_logical_key(comparer=_STRCMP_LOGICALW):
    """Windowsの論理順比較に基づくキーを生成する。"""

    if comparer:
        def _cmp(a: str, b: str) -> int:
            return comparer(os.path.basename(a), os.path.basename(b))

        return functools.cmp_to_key(_cmp)

    locale_transform = locale.strxfrm

    def _fallback_key(path: str):
        name = os.path.basename(path)
        return (locale_transform(name.casefold()), natural_key(path))

    return _fallback_key


windows_logical_key = _create_windows_logical_key()

def _create_vlc_instance() -> "vlc.Instance":
    lib_path = os.environ.get("PYTHON_VLC_LIB_PATH")
    if lib_path and os.path.isdir(lib_path):
        return vlc.Instance([f"--plugin-path={lib_path}", "--audio-time-stretch"])
    return vlc.Instance(["--audio-time-stretch"])

class MetadataDialog(QtWidgets.QDialog):
    """メタデータを表示・コピーするためのダイアログ"""
    def __init__(self, metadata_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("動画ファイルのメタデータ")
        self.setMinimumSize(500, 400)

        # --- UI要素の作成 ---
        # メタデータ表示用のテキストエリア (読み取り専用)
        self.text_edit = QtWidgets.QPlainTextEdit(self)
        self.text_edit.setPlainText(metadata_text)
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QtGui.QFont("Courier New", 10)) # 等幅フォントで見やすく

        # ボタン
        self.copy_button = QtWidgets.QPushButton("クリップボードにコピー")
        self.close_button = QtWidgets.QPushButton("閉じる")

        # --- レイアウト設定 ---
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.copy_button)
        button_layout.addWidget(self.close_button)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addWidget(self.text_edit)
        main_layout.addLayout(button_layout)

        # --- シグナル接続 ---
        self.copy_button.clicked.connect(self._copy_to_clipboard)
        self.close_button.clicked.connect(self.accept) # ダイアログを閉じる

    def _copy_to_clipboard(self):
        """テキストエリアの内容をクリップボードにコピーする"""
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(self.text_edit.toPlainText())
        # ユーザーにフィードバック
        self.copy_button.setText("コピーしました！")
        QtCore.QTimer.singleShot(1500, lambda: self.copy_button.setText("クリップボードにコピー"))

class VlcEvents(QtCore.QObject):
    media_ended = QtCore.pyqtSignal()


class VideoPlayer(QtWidgets.QMainWindow):
    SEEK_SHORT_MS = 10_000
    SEEK_LONG_MS = 60_000

    def __init__(self, file: Optional[str] = None):
        super().__init__()
        self._is_changing_media = False
        self.playback_rate_min = 0.25
        self.playback_rate_max = 4.0
        self.playback_rate = 1.0

        self.setWindowTitle("wagom-player")
        self.resize(960, 540)
        self.settings = QtCore.QSettings()

        # VLC
        self.vlc_instance = _create_vlc_instance()
        self.player: vlc.MediaPlayer = self.vlc_instance.media_player_new()
        self.vlc_events = VlcEvents()
        self._attach_vlc_events()

        # ### 変更点 1/6: シャッフル関連の変数を追加 ###
        self.repeat_enabled: bool = False
        self.shuffle_enabled: bool = False
        self.shuffled_playlist: List[str] = []

        # UI
        self._build_ui()

        # ### 変更点 1/5: オーバーレイ用ラベルとタイマーを追加 ###
        # 1. オーバーレイ表示用のラベルを作成 (video_frameの子だと表示されない)
        self.duration_overlay_label = QtWidgets.QLabel(self)
        self.duration_overlay_label.setWindowFlags(
            QtCore.Qt.FramelessWindowHint | # ウィンドウの枠を消す
            QtCore.Qt.Tool |                # タスクバーに表示させない
            QtCore.Qt.WindowStaysOnTopHint  # 常に最前面に表示するヒント
        )
        self.duration_overlay_label.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.duration_overlay_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.duration_overlay_label.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        self.duration_overlay_label.setStyleSheet("""
            background-color: transparent;
            border: none;
            color: white;
            font-size: 48px; /* 少し小さくして見やすく */
            font-weight: bold;
            padding: 10px; /* ウィンドウの角からの余白 */
            text-shadow:
                2px 0px 3px #000, -2px 0px 3px #000,
                0px 2px 3px #000, 0px -2px 3px #000,
                1px 1px 3px #000, -1px -1px 3px #000,
                1px -1px 3px #000, -1px 1px 3px #000;
        """)
        self.duration_overlay_label.hide() # 最初は非表示

        # 2. ラベルを1.5秒後に非表示にするためのタイマー
        self.duration_overlay_timer = QtCore.QTimer(self)
        self.duration_overlay_timer.setSingleShot(True)
        self.duration_overlay_timer.setInterval(1500) # 1.5秒
        self.duration_overlay_timer.timeout.connect(self.duration_overlay_label.hide)

        self.SEEK_SLIDER_STYLE_NORMAL = """
            QSlider::groove:horizontal {
                border: none;
                height: 4px;
                background: #555;
                border-radius: 2px;
                margin: 0px 4px;
            }
            QSlider::handle:horizontal {
                background: #4a90e2; /* 青色 */
                border: none;
                width: 8px;
                height: 14px;
                border-radius: 4px;
                margin: -5px -4px;
            }
            QSlider::sub-page:horizontal {
                background: #4a90e2; /* 青色 */
                border: none;
                border-radius: 2px;
            }
        """
        self.SEEK_SLIDER_STYLE_WARNING = """
            QSlider::groove:horizontal {
                border: none;
                height: 4px;
                background: #555;
                border-radius: 2px;
                margin: 0px 4px;
            }
            QSlider::handle:horizontal {
                background: #f5a623; /* 黄色 */
                border: none;
                width: 8px;
                height: 14px;
                border-radius: 4px;
                margin: -5px -4px;
            }
            QSlider::sub-page:horizontal {
                background: #f5a623; /* 黄色 */
                border: none;
                border-radius: 2px;
            }
        """
        # 現在のシークバーの状態を管理するフラグ
        self._is_seek_bar_warning = False
        # 初期スタイルを適用
        self.seek_slider.setStyleSheet(self.SEEK_SLIDER_STYLE_NORMAL)

        # プレイリスト
        self.directory_playlist: List[str] = [] # ディレクトリ内の動画リスト
        self.current_index: int = -1

        # タイマー
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._update_status_time)
        self.timer.start(200)

        # シーク状態
        self._seeking_user: bool = False
        self._media_length: int = -1
        self._ending: bool = False

        # 初期音量
        try:
            self.player.audio_set_volume(int(self.volume_slider.value()))
        except Exception:
            pass
        self._muted: bool = False
        try:
            m = self.player.audio_get_mute()
            if m in (0, 1):
                self._muted = m == 1
        except Exception:
            pass
        self._update_volume_label()
        try:
            self.player.set_rate(self.playback_rate)
        except Exception:
            pass

        # ショートカット
        self._setup_shortcuts()

        # 設定の復元（レイアウト構築・初期化後）
        self._load_settings()

        # 起動時にファイルが渡された場合、そのファイルをロードする
        if file:
            self._load_file_and_directory(file)
            

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)

        layout = QtWidgets.QVBoxLayout(central)

        # 映像
        self.video_frame = QtWidgets.QFrame(self)
        self.video_frame.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.video_frame.setStyleSheet("background: #000;")
        layout.addWidget(self.video_frame, 1)

        # シークバー
        self.seek_slider = SeekSlider(QtCore.Qt.Horizontal, self)
        self.seek_slider.setMinimumHeight(22)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setEnabled(False)
        layout.addWidget(self.seek_slider)

        # コントロール
        ctrl = QtWidgets.QHBoxLayout()
        layout.addLayout(ctrl)

        self.btn_open = QtWidgets.QPushButton()
        self.btn_play = QtWidgets.QPushButton()
        self.btn_stop = QtWidgets.QPushButton()
        self.btn_prev = QtWidgets.QPushButton()
        self.btn_next = QtWidgets.QPushButton()
        self.btn_repeat = QtWidgets.QPushButton()
        self.btn_repeat.setCheckable(True)
        self.btn_shuffle = QtWidgets.QPushButton()
        self.btn_shuffle.setCheckable(True)

        for b in (
            self.btn_open,
            self.btn_play,
            self.btn_stop,
            self.btn_prev,
            self.btn_next,
            self.btn_repeat,
            self.btn_shuffle,
        ):
            ctrl.addWidget(b)
        ctrl.addStretch(1)

        # 音量
        self.volume_icon = QtWidgets.QLabel()
        self.volume_icon.setFixedSize(18, 18)
        self.volume_icon.setAlignment(QtCore.Qt.AlignCenter)
        self.volume_label = QtWidgets.QLabel("音量")
        self.volume_slider = SeekSlider(QtCore.Qt.Horizontal, self)
        self.volume_slider.setObjectName("VolumeSlider")
        self.volume_slider.setMinimumHeight(22)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setFixedWidth(140)
        self.volume_slider.setValue(80)
        ctrl.addWidget(self.volume_icon)
        ctrl.addWidget(self.volume_label)
        ctrl.addWidget(self.volume_slider)
        volume_slider_style = """
            #VolumeSlider {
                min-height: 22px;
            }
            #VolumeSlider::groove:horizontal {
                border: none;
                height: 4px;
                background: #555;
                border-radius: 2px;
                margin: 0px 4px; /* ハンドルの幅の半分 */
            }
            #VolumeSlider::handle:horizontal {
                background: #4a90e2;
                border: none;
                width: 8px;   /* 幅を狭く */
                height: 14px; /* 高さを確保 */
                border-radius: 4px; /* 角を丸める */
                margin: -5px -4px; /* (14-4)/2=5, 8/2=4 */
            }
            #VolumeSlider::sub-page:horizontal {
                background: #4a90e2;
                border: none;
                border-radius: 2px;
            }
        """
        # 既存のスタイルシートに追記する
        self.setStyleSheet(self.styleSheet() + volume_slider_style)
        self.status = self.statusBar()
        self.status.showMessage("準備完了")

        # シグナル
        self.btn_open.clicked.connect(self.open_files_dialog)
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_prev.clicked.connect(self.play_previous)
        self.btn_next.clicked.connect(self.play_next)
        self.btn_repeat.toggled.connect(self._on_repeat_toggled)
        self.btn_shuffle.toggled.connect(self._on_shuffle_toggled)
        self.seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)
        self.seek_slider.sliderMoved.connect(self._on_slider_moved)
        self.seek_slider.clickedValue.connect(self._on_slider_clicked)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.volume_slider.clickedValue.connect(self._on_volume_clicked)

        # アイコン
        self._apply_control_icons()

        # メニュー
        menu = self.menuBar().addMenu("ファイル")
        act_open = menu.addAction("開く...")
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self.open_files_dialog)

        # ドロップ
        self.setAcceptDrops(True)

    def _apply_control_icons(self) -> None:
        def style_btn(btn: QtWidgets.QPushButton, icon_path: str, tip: str):
            btn.setIcon(QtGui.QIcon(icon_path))
            btn.setToolTip(tip)
            btn.setFixedSize(36, 28)
            btn.setIconSize(QtCore.QSize(18, 18))

        style_btn(
            self.btn_open, resource_path("resources", "icons", "open.svg"), "開く"
        )
        style_btn(
            self.btn_stop, resource_path("resources", "icons", "stop.svg"), "停止"
        )
        style_btn(
            self.btn_prev, resource_path("resources", "icons", "prev.svg"), "前へ"
        )
        style_btn(
            self.btn_next, resource_path("resources", "icons", "next.svg"), "次へ"
        )

        self._icon_play = QtGui.QIcon(resource_path("resources", "icons", "play.svg"))
        self._icon_pause = QtGui.QIcon(resource_path("resources", "icons", "pause.svg"))
        self.btn_play.setFixedSize(36, 28)
        self.btn_play.setIconSize(QtCore.QSize(18, 18))
        self._last_playing_state: Optional[bool] = None
        self._update_play_button()
        # 音量アイコン
        self._icon_volume = QtGui.QIcon(
            resource_path("resources", "icons", "volume.svg")
        )
        self._icon_mute = QtGui.QIcon(resource_path("resources", "icons", "mute.svg"))
        if hasattr(self, "volume_icon"):
            self.volume_icon.setPixmap((self._icon_volume).pixmap(18, 18))

        # リピートアイコン
        self._icon_repeat_on = QtGui.QIcon(resource_path("resources", "icons", "repeat.svg"))
        self._icon_repeat_off = QtGui.QIcon(resource_path("resources", "icons", "repeat_off.svg"))
        self.btn_repeat.setFixedSize(36, 28)
        self.btn_repeat.setIconSize(QtCore.QSize(18, 18))
        self.btn_repeat.setToolTip("リピート再生")
        self.repeat_enabled = False
        self._update_repeat_button()

        # シャッフルアイコン (新規)
        self._icon_shuffle_on = QtGui.QIcon(resource_path("resources", "icons", "shuffle.svg"))
        self._icon_shuffle_off = QtGui.QIcon(resource_path("resources", "icons", "shuffle_off.svg"))
        self.btn_shuffle.setFixedSize(36, 28)
        self.btn_shuffle.setIconSize(QtCore.QSize(18, 18))
        self.btn_shuffle.setToolTip("シャッフル再生")
        self._update_shuffle_button()

    # タイトルバーのダーク化（Windows）
    def showEvent(self, event: QtGui.QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._apply_windows_dark_titlebar()

    def _apply_windows_dark_titlebar(self) -> None:
        if not sys.platform.startswith("win"):
            return
        try:
            import ctypes

            hwnd = int(self.winId())
            dwmapi = ctypes.windll.dwmapi
            value = ctypes.c_int(1)
            for attr in (20, 19):
                try:
                    dwmapi.DwmSetWindowAttribute(
                        ctypes.c_void_p(hwnd),
                        ctypes.c_int(attr),
                        ctypes.byref(value),
                        ctypes.sizeof(value),
                    )
                except Exception:
                    pass
        except Exception:
            pass

    def _load_file_and_directory(self, file_path: str):
        """指定されたファイルを開き、そのディレクトリ内の動画ファイルをリストアップする"""
        if not os.path.isfile(file_path):
            return

        directory = os.path.dirname(file_path)
        log_message(f"Scanning directory: {directory}")

        # サポートする動画ファイルの拡張子
        supported_extensions = set(SUPPORTED_VIDEO_EXTENSIONS)

        # ディレクトリをスキャンし、動画ファイルだけをフィルタリング
        try:
            all_files = os.listdir(directory)
            video_files = [
                os.path.join(directory, f) for f in all_files
                if os.path.splitext(f)[1].lower() in supported_extensions
            ]
        except OSError as e:
            log_message(f"Error scanning directory: {e}")
            self.status.showMessage(f"ディレクトリのスキャンに失敗しました: {e}", 5000)
            return

        if not video_files:
            log_message("No video files found in the directory.")
            # 動画が1つも見つからない場合でも、指定されたファイルだけは再生する
            video_files = [file_path]

        # Windowsの論理順（または可能な限り近い順序）でソート
        video_files.sort(key=windows_logical_key)

        self.directory_playlist = video_files

        # ### 変更点 3/6: シャッフル状態をリセット ###
        if self.shuffle_enabled:
            # シャッフルが有効な状態で新しいディレクトリを開いたら、一度無効にする
            self.shuffle_enabled = False
            self.shuffled_playlist = []
            self._update_shuffle_button()

        # 渡されたファイルがリストの何番目にあるかを探す
        try:
            # パスを正規化して比較
            normalized_path = os.path.normpath(file_path)
            normalized_playlist = [os.path.normpath(p) for p in self.directory_playlist]
            self.current_index = normalized_playlist.index(normalized_path)
        except ValueError:
            # 万が一見つからない場合は、最初のファイルを再生
            log_message(f"Could not find '{file_path}' in scanned list. Defaulting to first file.")
            self.current_index = 0

        # 再生開始
        self.play_at(self.current_index)

    # --------------- 設定保存/復元 ---------------
    def _load_settings(self) -> None:
        try:
            vol = int(self.settings.value("volume", 80))
        except Exception:
            vol = 80
        vol = max(0, min(100, vol))
        if vol != int(self.volume_slider.value()):
            self.volume_slider.setValue(vol)

        # ミュート状態は保存しない（常に起動時はミュートOFF）
        self._muted = False
        try:
            self.player.audio_set_mute(False)
        except Exception:
            pass
        self._update_volume_label()

        # ウィンドウ配置
        geom = self.settings.value("geometry")
        if isinstance(geom, QtCore.QByteArray):
            self.restoreGeometry(geom)
        is_max = bool(self.settings.value("isMaximized", False, type=bool))
        if is_max:
            self.setWindowState(self.windowState() | QtCore.Qt.WindowMaximized)
        # リピート状態（デフォルトOFF）
        repeat = bool(self.settings.value("repeat", False, type=bool))
        self.btn_repeat.setChecked(repeat)
        self.repeat_enabled = repeat
        self._update_repeat_button()

    def _save_settings(self) -> None:
        try:
            self.settings.setValue("volume", int(self.volume_slider.value()))
            self.settings.setValue("geometry", self.saveGeometry())
            self.settings.setValue("isMaximized", self.isMaximized())
            self.settings.setValue("repeat", bool(self.repeat_enabled))
        except Exception:
            pass

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        self._save_settings()
        super().closeEvent(event)

    # --------------- VLC ---------------
    def _attach_vlc_events(self) -> None:
        em = self.player.event_manager()
        em.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_vlc_end)
        self.vlc_events.media_ended.connect(self._on_media_end)


    def _on_vlc_end(self, event) -> None:
        log_message(f"_on_vlc_end(): VLC EndReached fired, current_index={self.current_index}")
        self.vlc_events.media_ended.emit()

    def _on_media_end(self) -> None:
        log_message(
            f"_on_media_end(): ENTER, "
            f"_ending={getattr(self, '_ending', False)}, "
            f"current_index={self.current_index}, "
            f"dir_len={len(self.directory_playlist)}, "
            f"plist_len={len(self._get_current_playlist())}"
        )

        # 再生切替中なら無視
        if getattr(self, "_is_changing_media", False):
            log_message("_on_media_end(): ignored because _is_changing_media")
            return

        playlist = self._get_current_playlist()
        if not playlist:
            log_message("_on_media_end(): empty playlist")
            return

        # index が変になってないか一応チェック
        if not (0 <= self.current_index < len(self.directory_playlist)):
            log_message(f"_on_media_end(): current_index out of range: {self.current_index}")
            return

        # ============================
        # ★ 単曲リピート（repeat_enabled=True）の処理
        # ============================
        if self.repeat_enabled:
            path = self.directory_playlist[self.current_index]
            log_message(
                f"_on_media_end(): repeat_enabled=True -> reload same media "
                f"index={self.current_index}, path={path}"
            )

            def _restart_current() -> None:
                try:
                    # VLC の状態をログしておくと後で分析しやすい
                    try:
                        state_before = self.player.get_state()
                        t_before = self.player.get_time()
                    except Exception:
                        state_before = None
                        t_before = None
                    log_message(
                        f"_restart_current(): BEFORE reload "
                        f"state={state_before}, time={t_before}"
                    )

                    # ★ 同じパスでメディアを作り直す（stop は呼ばない）
                    media = self.vlc_instance.media_new(path)
                    media.parse()
                    self.player.set_media(media)
                    self.player.play()

                    # シークバー状態を軽くリセットしておく
                    self._media_length = -1
                    self.seek_slider.blockSignals(True)
                    self.seek_slider.setEnabled(True)
                    self.seek_slider.setRange(0, 0)
                    self.seek_slider.setValue(0)
                    self.seek_slider.blockSignals(False)

                    try:
                        state_after = self.player.get_state()
                        t_after = self.player.get_time()
                    except Exception:
                        state_after = None
                        t_after = None
                    log_message(
                        f"_restart_current(): AFTER reload "
                        f"state={state_after}, time={t_after}"
                    )

                except Exception as e:
                    log_message(f"_restart_current(): error: {e!r}")

            QtCore.QTimer.singleShot(80, _restart_current)
            return


        # ============================
        # ★ 通常モード（repeat_enabled=False）：次のファイルへ
        # ============================

        if getattr(self, "_ending", False):
            log_message("_on_media_end(): ignored because _ending already True")
            return
        self._ending = True

        try:
            current_path = self.directory_playlist[self.current_index]
            try:
                current_playlist_idx = playlist.index(current_path)
            except ValueError:
                log_message("_on_media_end(): current_path not in playlist")
                return

            next_playlist_idx = -1
            if current_playlist_idx + 1 < len(playlist):
                next_playlist_idx = current_playlist_idx + 1

            if next_playlist_idx != -1:
                next_path = playlist[next_playlist_idx]
                next_original_idx = self.directory_playlist.index(next_path)
                log_message(
                    f"_on_media_end(): moving to next track idx={next_original_idx}, path={next_path}"
                )
                QtCore.QTimer.singleShot(
                    80, lambda idx=next_original_idx: self._end_after(idx)
                )
            else:
                log_message("_on_media_end(): reached end of playlist (repeat off) -> stop()")
                self.stop()
        finally:
            # 次の曲に進む処理が終わったら _ending を戻す
            self._ending = False


    def _end_after(self, idx: int) -> None:
        log_message(f"_end_after(): idx={idx}, current_index(before)={self.current_index}")
        self._ending = False
        self._play_at_with_reason(idx, "from_end")

    def _bind_video_surface(self) -> None:
        wid = int(self.video_frame.winId())
        if sys.platform.startswith("win"):
            self.player.set_hwnd(wid)
        elif sys.platform == "darwin":
            self.player.set_nsobject(wid)  # type: ignore[attr-defined]
        else:
            self.player.set_xwindow(wid)  # type: ignore[attr-defined]

    # ------------- プレイリスト -------------


    def play_at(self, index: int) -> None:

        if not (0 <= index < len(self.directory_playlist)):
            log_message("play_at(): index out of range")
            return
        
        if getattr(self, "_is_changing_media", False):
            log_message(f"play_at(): SKIP index={index} because _is_changing_media is True")
            return
        self._is_changing_media = True
        
        try:
            old = self.current_index
            log_message(f"play_at(): START index={index}, old_index={old}")
            self.current_index = index
            path = self.directory_playlist[index]
            log_message(f"play_at(): path={path}")

            try:
                log_message("play_at(): before player.stop()")
                self.player.stop()
                log_message("play_at(): after player.stop()")
            except Exception as e:
                log_message(f"play_at(): player.stop() error: {e}")

            try:
                log_message("play_at(): before media_new/parse")
                media = self.vlc_instance.media_new(path)
                media.parse()  # ← ここで固まるか確認したい
                log_message("play_at(): after media.parse()")
                self.player.set_media(media)
            except Exception as e:
                log_message(f"play_at(): media setup error: {e}")
                return

            QtWidgets.QApplication.processEvents()
            self._bind_video_surface()

            try:
                self.player.set_rate(self.playback_rate)
            except Exception:
                pass

            self.player.play()
            log_message(f"play_at(): player.play() done, current_index={self.current_index}, path={path}")
            self._update_window_title(os.path.basename(path))
            self.status.showMessage(f"再生中: {path}")

            # 新しい動画を再生する際に、シークバーの色を通常に戻す
            if self._is_seek_bar_warning:
                self.seek_slider.setStyleSheet(self.SEEK_SLIDER_STYLE_NORMAL)
                self._is_seek_bar_warning = False
            
            self._media_length = -1
            self.seek_slider.blockSignals(True)
            self.seek_slider.setEnabled(True)
            self.seek_slider.setRange(0, 0)
            self.seek_slider.setValue(0)
            self.seek_slider.blockSignals(False)
            log_message("play_at(): end")
        finally:
            self._is_changing_media = False
    
    def _get_current_playlist(self) -> List[str]:
        """現在の再生モードに応じたプレイリストを返すヘルパーメソッド"""
        return self.shuffled_playlist if self.shuffle_enabled else self.directory_playlist

    def play_next(self) -> None:
        playlist = self._get_current_playlist()
        log_message(f"play_next(): current_index={self.current_index}, playlist_len={len(playlist)}")
        if not playlist:
            return
        # 現在再生中のファイルがシャッフルリストの何番目にあるかを探す
        current_path = self.directory_playlist[self.current_index]
        log_message(f"play_next(): current_path={current_path}")
        try:
            shuffled_idx = playlist.index(current_path)
            if (shuffled_idx + 1) < len(playlist):
                next_path = playlist[shuffled_idx + 1]
                # 元のリストでのインデックスを見つけて再生
                next_original_idx = self.directory_playlist.index(next_path)
                QtCore.QTimer.singleShot(50, lambda: self._play_at_with_reason(next_original_idx, "from_next"))
        except ValueError:
            pass
        log_message(f"play_next(): scheduling play_at({next_original_idx}) in 50ms")

    def _play_at_with_reason(self, index: int, reason: str) -> None:
        log_message(f"_play_at_with_reason(): index={index}, reason={reason}")
        self.play_at(index)

    def play_previous(self) -> None:
        playlist = self._get_current_playlist()
        if not playlist:
            return
        current_path = self.directory_playlist[self.current_index]
        try:
            shuffled_idx = playlist.index(current_path)
            if (shuffled_idx - 1) >= 0:
                prev_path = playlist[shuffled_idx - 1]
                prev_original_idx = self.directory_playlist.index(prev_path)
                QtCore.QTimer.singleShot(50, lambda: self.play_at(prev_original_idx))
        except ValueError:
            pass

    # ------------- 再生操作 -------------
    def toggle_play(self) -> None:
        """再生/一時停止を切り替える。停止状態からの再開も考慮する。"""
        player_state = self.player.get_state()

        # プレイヤーが完全に停止または終了している場合
        if player_state in (vlc.State.Stopped, vlc.State.Ended, vlc.State.Error):
            # 再生可能なファイルがプレイリストにあれば、現在のファイルを最初から再生する
            if 0 <= self.current_index < len(self.directory_playlist):
                self.play_at(self.current_index)
        # 再生中または一時停止中の場合
        elif self.player.is_playing():
            self.player.pause()
        else:
            self.player.play()
        
        self._update_play_button()

    def stop(self) -> None:
        self.player.stop()
        self.duration_overlay_label.hide()
        # 停止時にシークバーの色を通常に戻す
        if self._is_seek_bar_warning:
            self.seek_slider.setStyleSheet(self.SEEK_SLIDER_STYLE_NORMAL)
            self._is_seek_bar_warning = False
        
        self.seek_slider.blockSignals(True)
        self.seek_slider.setEnabled(False)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setValue(0)
        self.seek_slider.blockSignals(False)
        self._update_play_button()

    def seek_by(self, delta_ms: int) -> None:
        try:
            t = self.player.get_time()
            length = self.player.get_length()
            if t == -1 or length <= 0:
                return

            new_t = max(0, t + delta_ms)

            # ★ 前方向のシークは、動画終端10秒前より先には行かない
            if delta_ms > 0 and length > 0:
                # 動画終了10秒前（ミリ秒）
                end_threshold = max(0, length - 10_000)
                if new_t > end_threshold:
                    new_t = end_threshold

            if length > 0:
                new_t = max(min(new_t, length - 1000), 0)
            self.player.set_time(new_t)
        except Exception:
            pass

    # ------------- キー操作 -------------
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        mods = event.modifiers()
        is_keypad = bool(mods & QtCore.Qt.KeypadModifier)

        # if key == QtCore.Qt.Key_Left:
        #     self.seek_by(-self.SEEK_SHORT_MS)
        #     event.accept()
        #     return
        # if key == QtCore.Qt.Key_Right:
        #     self.seek_by(self.SEEK_SHORT_MS)
        #     event.accept()
        #     return

        if is_keypad and key == QtCore.Qt.Key_4:
            # Num4: 60秒進む
            self.seek_by(self.SEEK_LONG_MS)
            event.accept()
            return
        if is_keypad and key == QtCore.Qt.Key_1:
            # Num1: 60秒戻る
            self.seek_by(-self.SEEK_LONG_MS)
            event.accept()
            return

        # if key == QtCore.Qt.Key_PageUp:
        #     self.play_previous()
        #     event.accept()
        #     return
        # if key == QtCore.Qt.Key_PageDown:
        #     self.play_next()
        #     event.accept()
        #     return

        if is_keypad and key == QtCore.Qt.Key_8:
            self.close()
            event.accept()
            return

        if is_keypad and key == QtCore.Qt.Key_0:
            # Num0 は常に最大化
            self.showMaximized()
            event.accept()
            return

        super().keyPressEvent(event)

    # ------------- グローバルショートカット -------------
    def _setup_shortcuts(self) -> None:
        def mk(key, handler):
            sc = QtWidgets.QShortcut(QtGui.QKeySequence(key), self)
            sc.setContext(QtCore.Qt.ApplicationShortcut)
            sc.activated.connect(handler)
            return sc

        self._sc_left = mk(
            QtCore.Qt.Key_Left, lambda: self.seek_by(-self.SEEK_SHORT_MS)
        )
        self._sc_right = mk(
            QtCore.Qt.Key_Right, lambda: self.seek_by(self.SEEK_SHORT_MS)
        )
        self._sc_up = mk(QtCore.Qt.Key_Up, lambda: self._adjust_volume(+10))
        self._sc_down = mk(QtCore.Qt.Key_Down, lambda: self._adjust_volume(-10))
        self._sc_mute = mk(QtCore.Qt.Key_M, self._toggle_mute)
        # Num 0（テンキー0）
        self._sc_num0 = QtWidgets.QShortcut(
            QtGui.QKeySequence(int(QtCore.Qt.Key_0 | QtCore.Qt.KeypadModifier)), self
        )
        self._sc_num0.setContext(QtCore.Qt.ApplicationShortcut)
        self._sc_num0.activated.connect(self.showMaximized)
        # 前/次動画
        self._sc_prev_track = mk(QtCore.Qt.Key_PageUp, self.play_previous)
        self._sc_next_track = mk(QtCore.Qt.Key_PageDown, self.play_next)
        # Rキーでリピート切替（任意）
        self._sc_repeat = mk(QtCore.Qt.Key_R, lambda: self.btn_repeat.toggle())
        self._sc_shuffle = mk(QtCore.Qt.Key_S, lambda: self.btn_shuffle.toggle())
        # スペースキーで再生/一時停止
        self._sc_space = mk(QtCore.Qt.Key_Space, self.toggle_play)
        self._sc_speed_up = mk(QtCore.Qt.Key_C, lambda: self._change_playback_rate(+0.1))
        self._sc_speed_up.setAutoRepeat(True)
        self._sc_speed_down = mk(QtCore.Qt.Key_X, lambda: self._change_playback_rate(-0.1))
        self._sc_speed_down.setAutoRepeat(True)

        # Num 9: "_ok" フォルダに移動
        self._sc_move_ok = QtWidgets.QShortcut(
            QtGui.QKeySequence(int(QtCore.Qt.Key_9 | QtCore.Qt.KeypadModifier)), self
        )
        self._sc_move_ok.setContext(QtCore.Qt.ApplicationShortcut)
        self._sc_move_ok.activated.connect(
            lambda: self._move_current_file_and_play_next("_ok")
        )

        # Num 6: "_ng" フォルダに移動
        self._sc_move_ng = QtWidgets.QShortcut(
            QtGui.QKeySequence(int(QtCore.Qt.Key_7 | QtCore.Qt.KeypadModifier)), self
        )
        self._sc_move_ng.setContext(QtCore.Qt.ApplicationShortcut)
        self._sc_move_ng.activated.connect(
            lambda: self._move_current_file_and_play_next("_ng")
        )

        # Iキーでメタデータ情報表示
        self._sc_metadata = mk(QtCore.Qt.Key_I, self._show_metadata_dialog)

    # ------------- D&D -------------
    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        files = [u.toLocalFile() for u in urls if u.isLocalFile()]
        if files:
            self._load_file_and_directory(files[0])
            event.acceptProposedAction()

    def _format_ms(self, ms: int) -> str:
        """ミリ秒を MM:SS または HH:MM:SS 形式の文字列に変換する"""
        if ms <= 0:
            return "00:00"
        s = ms // 1000
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

    def _show_overlay(self, text: str, duration_ms: int = 1500) -> None:
        """オーバーレイラベルにテキストを表示し、一定時間後に非表示にする"""
        self.duration_overlay_label.setText(text)
        self._update_overlay_geometry()
        self.duration_overlay_label.show()
        self.duration_overlay_label.raise_()
        self.duration_overlay_timer.stop()
        self.duration_overlay_timer.setInterval(duration_ms)
        self.duration_overlay_timer.start()

    # ------------- ステータス更新 -------------
    def _update_status_time(self) -> None:
        if not self.player:
            return
        cur = self.player.get_time()
        total = self.player.get_length()

        if cur >= 0 and total > 0:
            self.status.showMessage(f"{self._format_ms(cur)} / {self._format_ms(total)}")
            if total != self._media_length:
                self._media_length = total
                self.seek_slider.blockSignals(True)
                self.seek_slider.setEnabled(True)
                self.seek_slider.setRange(0, total)
                self.seek_slider.blockSignals(False)
                self._update_window_title()
                formatted_time = self._format_ms(total)
                self._show_overlay(formatted_time)
            
            if not self._seeking_user:
                self.seek_slider.blockSignals(True)
                self.seek_slider.setValue(cur)
                self.seek_slider.blockSignals(False)

            is_near_end = (cur > total - 12_000) # 10秒だと判定が微妙なので12秒に余裕を持たせる
            if is_near_end and not self._is_seek_bar_warning:
                # 黄色に変更
                self.seek_slider.setStyleSheet(self.SEEK_SLIDER_STYLE_WARNING)
                self._is_seek_bar_warning = True
            elif not is_near_end and self._is_seek_bar_warning:
                # 青色に戻す
                self.seek_slider.setStyleSheet(self.SEEK_SLIDER_STYLE_NORMAL)
                self._is_seek_bar_warning = False
        # 再生ボタン表示
        self._update_play_button()

    def _update_window_title(self, filename: Optional[str] = None) -> None:
        playlist = self._get_current_playlist()
        current_path = self.directory_playlist[self.current_index] if 0 <= self.current_index < len(self.directory_playlist) else ""
        
        name = filename or (os.path.basename(current_path) if current_path else "")
        
        # シャッフルリスト内でのインデックスを探す
        try:
            idx = playlist.index(current_path) + 1 if current_path else 0
        except ValueError:
            idx = 0
            
        total = len(playlist)
        prefix = f"[{idx}/{total}] " if total else ""
        shuffle_indicator = "[S] " if self.shuffle_enabled else ""

        duration_str = ""
        if self._media_length > 0:
            duration_str = f" [{self._format_ms(self._media_length)}]"

        self.setWindowTitle(f"{shuffle_indicator}{prefix}{name}{duration_str}")

    def _update_play_button(self) -> None:
        try:
            playing = bool(self.player.is_playing())
        except Exception:
            playing = False
        if (
            getattr(self, "_last_playing_state", None) is None
            or self._last_playing_state != playing
        ):
            self.btn_play.setIcon(self._icon_pause if playing else self._icon_play)
            self.btn_play.setToolTip("一時停止" if playing else "再生")
            self._last_playing_state = playing

    # ------------- シークバー操作 -------------
    def _on_seek_pressed(self) -> None:
        self._seeking_user = True

    def _on_seek_released(self) -> None:
        self._seeking_user = False
        val = self.seek_slider.value()
        try:
            self.player.set_time(val)
        except Exception:
            pass

    def _on_slider_moved(self, value: int) -> None:
        total = (
            self._media_length if self._media_length > 0 else self.player.get_length()
        )

        def f(ms: int) -> str:
            if ms <= 0:
                return "00:00"
            s = ms // 1000
            m, s = divmod(s, 60)
            h, m = divmod(m, 60)
            return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

        if total > 0:
            self.status.showMessage(f"{f(value)} / {f(total)}")

    def _on_slider_clicked(self, value: int) -> None:
        try:
            self.player.set_time(value)
        except Exception:
            pass

    # ------------- 再生速度操作 -------------
    def _change_playback_rate(self, delta: float) -> None:
        new_rate = max(
            self.playback_rate_min, min(self.playback_rate_max, self.playback_rate + delta)
        )
        try:
            self.player.set_rate(new_rate)
        except Exception:
            pass
        self.playback_rate = new_rate
        self._show_overlay(f"[再生速度:{new_rate:.1f}倍]")

    # ------------- 音量操作 -------------
    def _on_volume_changed(self, value: int) -> None:
        try:
            self.player.audio_set_volume(int(value))
        except Exception:
            pass
        self._update_volume_label()
        self._show_overlay(f"[ボリューム:{int(value)}%]")

    def _adjust_volume(self, delta: int) -> None:
        v = int(self.volume_slider.value())
        nv = max(0, min(100, v + delta))
        if nv != v:
            self.volume_slider.setValue(nv)
        else:
            self._show_overlay(f"[ボリューム:{nv}%]")

    def _on_volume_clicked(self, value: int) -> None:
        # クリック位置を即時反映（valueChangedで反映される）
        pass

    def _update_volume_label(self) -> None:
        v = int(self.volume_slider.value())
        self.volume_label.setText(f"音量: {v}%")
        # アイコン切り替え
        icon = self._icon_mute if self._muted else self._icon_volume
        if hasattr(self, "volume_icon"):
            self.volume_icon.setPixmap(icon.pixmap(18, 18))

    def _on_repeat_toggled(self, checked: bool) -> None:
        self.repeat_enabled = bool(checked)
        self._update_repeat_button()

    def _update_repeat_button(self) -> None:
        self.btn_repeat.setIcon(
            self._icon_repeat_on if self.repeat_enabled else self._icon_repeat_off
        )
        # 押下状態の視覚フィードバック
        self.btn_repeat.setChecked(self.repeat_enabled)

    def _on_shuffle_toggled(self, checked: bool) -> None:
        self.shuffle_enabled = bool(checked)
        self._create_or_clear_shuffled_playlist()
        self._update_shuffle_button()
        self._update_window_title()

    def _create_or_clear_shuffled_playlist(self):
        """シャッフルリストを作成またはクリアする"""
        import random
        if self.shuffle_enabled and self.directory_playlist:
            log_message("Shuffle mode enabled. Creating shuffled playlist.")
            current_path = self.directory_playlist[self.current_index]
            temp_list = self.directory_playlist[:]
            temp_list.remove(current_path)
            random.shuffle(temp_list)
            self.shuffled_playlist = [current_path] + temp_list
        else:
            log_message("Shuffle mode disabled.")
            self.shuffled_playlist = []
            
    # _toggle_shuffleから_update_shuffle_buttonに名前を変更したものを流用
    def _update_shuffle_button(self):
        self.btn_shuffle.setIcon(
            self._icon_shuffle_on if self.shuffle_enabled else self._icon_shuffle_off
        )
        self.btn_shuffle.setChecked(self.shuffle_enabled)

    def _toggle_mute(self) -> None:
        self._muted = not self._muted
        try:
            self.player.audio_toggle_mute()
        except Exception:
            pass
        self._update_volume_label()

    # ------------- ファイルダイアログ -------------
    def open_files_dialog(self) -> None:
        start_dir = self.settings.value("last_dir", os.path.expanduser("~"))
        supported_patterns = " ".join(f"*{ext}" for ext in SUPPORTED_VIDEO_EXTENSIONS)
        file_filter = f"動画ファイル ({supported_patterns});;すべてのファイル (*.*)"
        file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "動画ファイルを選択",
            start_dir,
            file_filter,
        )
        if file:
            try:
                self.settings.setValue("last_dir", os.path.dirname(file))
            except Exception:
                pass
            self._load_file_and_directory(file)

    # ------------- ファイル移動と次の動画再生 -------------
    def _move_current_file_and_play_next(self, subfolder_name: str):
        """現在再生中のファイルを指定されたサブフォルダに移動し、次の曲を再生する"""
        # 再生中でない、またはプレイリストが空の場合は何もしない
        if not (0 <= self.current_index < len(self.directory_playlist)):
            log_message("Move requested, but no file is playing.")
            return

        # --- 重要な情報を先に保存しておく ---
        index_to_remove = self.current_index
        current_file_path = self.directory_playlist[index_to_remove]

        # ★ シャッフル時に「シャッフル順の次」を覚えておく
        next_path = None
        if self.shuffle_enabled:
            playlist = self._get_current_playlist()
            try:
                cur_in_playlist = playlist.index(current_file_path)
            except ValueError:
                cur_in_playlist = -1
            if cur_in_playlist != -1 and cur_in_playlist + 1 < len(playlist):
                next_path = playlist[cur_in_playlist + 1]

        # ファイル操作の前に、VLCプレイヤーを完全に停止してファイルロックを解放する
        log_message("Stopping playback to release file lock...")
        self.stop()

        # --- ファイルパスの準備 (停止後に行っても問題ない) ---
        file_name = os.path.basename(current_file_path)
        source_dir = os.path.dirname(current_file_path)

        target_dir = os.path.join(source_dir, subfolder_name)
        target_file_path = os.path.join(target_dir, file_name)

        log_message(f"Attempting to move '{file_name}' to '{subfolder_name}' folder.")

        # --- 移動処理 ---
        try:
            os.makedirs(target_dir, exist_ok=True)

            if os.path.exists(target_file_path):
                log_message(
                    f"File '{file_name}' already exists in target directory. Skipping move."
                )
                self.status.showMessage(
                    f"移動失敗: {file_name}は移動先に既に存在します", 5000
                )
                # ファイルが存在した場合、次の曲の再生は行わずに待機する
                return

            shutil.move(current_file_path, target_file_path)
            self.status.showMessage(f"移動完了: {file_name} -> {subfolder_name}", 4000)
            log_message(f"Successfully moved file to '{target_file_path}'")

        except Exception as e:
            log_message(f"Error moving file: {e}")
            self.status.showMessage(f"ファイル移動中にエラーが発生しました: {e}", 5000)
            # エラーが発生した場合も、次の曲の再生は行わずに待機する
            return

        # --- プレイリストの更新と次の曲の再生 ---

        # プレイリストから該当ファイルを削除
        self.directory_playlist.pop(index_to_remove)
        # 2. シャッフルリストからも削除
        if self.shuffle_enabled and current_file_path in self.shuffled_playlist:
            self.shuffled_playlist.remove(current_file_path)

        # ウィンドウタイトルの表示を更新
        self._update_window_title()

        # もう再生できるものがない
        if not self.directory_playlist:
            log_message("Playlist is now empty. Playback remains stopped.")
            self.stop()
            return

        # 次に再生する index を決定
        next_index = None

        if self.shuffle_enabled and next_path is not None:
            # シャッフルリストで「次」だったパスを、ソート済みリスト上のインデックスに変換
            if next_path in self.directory_playlist:
                next_index = self.directory_playlist.index(next_path)
        elif not self.shuffle_enabled:
            # 通常モードでは、今の位置 index_to_remove に来たファイルをそのまま再生
            if index_to_remove < len(self.directory_playlist):
                next_index = index_to_remove

        if next_index is None:
            log_message("No next item to play after move. Playback remains stopped.")
            self.stop()
        else:
            log_message(f"Playing next item at index {next_index}.")
            QtCore.QTimer.singleShot(
                50, lambda idx=next_index: self.play_at(idx)
            )
                
    def _update_overlay_geometry(self):
        """
        オーバーレイウィンドウの位置とサイズを、video_frameに正確に合わせる。
        VLCウィンドウのグローバル座標を計算して追従させる。
        """
        if not self.video_frame.isVisible():
            return
        
        # ### ★★★ 変更点 ★★★ ###
        # video_frame の左上の座標を、スクリーン全体のグローバル座標系に変換する
        global_pos = self.video_frame.mapToGlobal(QtCore.QPoint(0, 0))
        
        # video_frame のサイズを取得する
        frame_size = self.video_frame.size()
        
        # オーバーレイウィンドウのジオメトリを設定する
        self.duration_overlay_label.setGeometry(
            global_pos.x(),
            global_pos.y(),
            frame_size.width(),
            frame_size.height()
        )

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        """ウィンドウのリサイズに合わせてオーバーレイラベルのサイズを調整する"""
        super().resizeEvent(event)
        # video_frameの現在の大きさにラベルをぴったり合わせる
        self.duration_overlay_label.setGeometry(self.video_frame.rect())
    
    def moveEvent(self, event: QtGui.QMoveEvent) -> None:
        """メインウィンドウの移動に合わせてオーバーレイの位置を更新する"""
        super().moveEvent(event)
        # 表示されている場合のみ、位置を更新する
        if self.duration_overlay_label.isVisible():
            self._update_overlay_geometry()

    # VideoPlayer クラスの末尾あたりに追加
    # ### 変更点 4/4: メタデータを収集してダイアログを表示するメソッドを新規作成 ###
    def _show_metadata_dialog(self):
        """現在再生中の動画のメタデータを抽出し、ダイアログで表示する"""
        print("Show Metadata Dialog triggered")
        # 再生中でなければ何もしない
        if not (0 <= self.current_index < len(self.directory_playlist)):
            self.status.showMessage("再生中のファイルがありません", 3000)
            return

        media = self.player.get_media()
        if not media:
            return

        # --- メタデータの収集 ---
        metadata_lines = []
        
        # 1. 基本情報
        file_path = self.directory_playlist[self.current_index]
        metadata_lines.append(f"ファイルパス: {file_path}")
        
        duration_ms = media.get_duration()
        if duration_ms > 0:
            metadata_lines.append(f"長さ: {self._format_ms(duration_ms)} ({duration_ms} ms)")
        
        metadata_lines.append("-" * 20)

        # 2. VLCから取得できるメタデータ
        # 取得したいメタデータの種類を定義
        # 表示したいメタデータの種類を、表示名とvlc.Meta enumのマッピングで定義
        meta_fields = {
            # --- 基本情報 ---
            "Title": vlc.Meta.Title,
            "Artist": vlc.Meta.Artist,
            "Album": vlc.Meta.Album,
            "Album Artist": vlc.Meta.AlbumArtist,
            "Genre": vlc.Meta.Genre,
            "Date": vlc.Meta.Date,
            "Description": vlc.Meta.Description,
            # --- トラック/ディスク情報 ---
            "Track Number": vlc.Meta.TrackNumber,
            "Track Total": vlc.Meta.TrackTotal,
            "Disc Number": vlc.Meta.DiscNumber,
            "Disc Total": vlc.Meta.DiscTotal,
            "Track ID": vlc.Meta.TrackID,
            # --- TV/映画情報 ---
            "Show Name": vlc.Meta.ShowName,
            "Season": vlc.Meta.Season,
            "Episode": vlc.Meta.Episode,
            "Director": vlc.Meta.Director,
            "Actors": vlc.Meta.Actors,
            # --- その他 ---
            "Rating": vlc.Meta.Rating,
            "Language": vlc.Meta.Language,
            "Copyright": vlc.Meta.Copyright,
            "Publisher": vlc.Meta.Publisher,
            "Encoded By": vlc.Meta.EncodedBy,
            "Setting": vlc.Meta.Setting,
            "URL": vlc.Meta.URL,
            "Artwork URL": vlc.Meta.ArtworkURL,
            "Now Playing": vlc.Meta.NowPlaying,
        }
        
        # ### 変更点: 値が空でも項目を表示するようにループ処理を変更 ###
        for name, field_enum in meta_fields.items():
            # media.get_meta() は値がなければ None を返す
            value = media.get_meta(field_enum)
            
            # valueがNoneなら空文字列に変換し、そうでなければそのままの値を使う
            # これにより、値がなくても "項目名: " という行が必ず追加される
            display_value = value or ""
            
            metadata_lines.append(f"{name}: {display_value}")

        # --- ダイアログの表示 ---
        final_text = "\n".join(metadata_lines)
        
        # 作成したMetadataDialogクラスのインスタンスを生成して表示
        dialog = MetadataDialog(final_text, self)
        dialog.exec_() # モーダルダイアログとして表示
