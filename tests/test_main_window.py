import importlib
import os

import pytest

from tests.fakes.vlc import FakeVlc
from wagom_player.infrastructure.trash import TrashService

QtCore = pytest.importorskip("PyQt5.QtCore", exc_type=ImportError)
QtGui = pytest.importorskip("PyQt5.QtGui", exc_type=ImportError)
QtWidgets = pytest.importorskip("PyQt5.QtWidgets", exc_type=ImportError)

main_window = importlib.import_module("wagom_player.ui.main_window")


@pytest.fixture
def player(qapp, monkeypatch, tmp_path):
    fake_vlc = FakeVlc()
    monkeypatch.setattr(main_window, "vlc", fake_vlc)
    monkeypatch.setattr(main_window.diagnostics, "start_heartbeat_timer", lambda parent: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    qapp.setOrganizationName("wagom-player-tests")
    qapp.setApplicationName("wagom-player-tests")
    QtCore.QSettings().clear()
    window = main_window.VideoPlayer()
    yield window
    window.timer.stop()
    window.close()


def test_create_vlc_instance_raises_without_vlc(monkeypatch):
    monkeypatch.setattr(main_window, "vlc", None)

    with pytest.raises(RuntimeError, match="VLC"):
        main_window._create_vlc_instance()


def test_create_vlc_instance_passes_plugin_path(monkeypatch, tmp_path):
    fake_vlc = FakeVlc()
    monkeypatch.setattr(main_window, "vlc", fake_vlc)
    monkeypatch.setenv("PYTHON_VLC_LIB_PATH", str(tmp_path))

    instance = main_window._create_vlc_instance()

    assert instance.args == [f"--plugin-path={tmp_path}", "--audio-time-stretch"]


def test_video_player_initializes_ui_and_vlc_events(player):
    assert player.windowTitle() == "wagom-player"
    assert player.volume_slider.value() == 80
    assert len(player.player.events.attached) == 1
    assert player.player.events.attached[0][0] == "ended"
    assert player.btn_repeat.isCheckable()
    assert player.btn_shuffle.isCheckable()


def test_vlc_end_generation_ignores_stale_events(player, monkeypatch):
    calls = []
    monkeypatch.setattr(player, "_on_vlc_end", lambda event: calls.append(event))

    player._on_vlc_end_for_generation("old", player._vlc_generation - 1)
    player._on_vlc_end_for_generation("current", player._vlc_generation)

    assert calls == ["current"]


def test_create_fresh_vlc_player_rebinds_video_surface(player):
    player._create_fresh_vlc_player()

    assert player.player.surface is not None
    assert len(player.player.events.attached) == 1


def test_stale_vlc_event_callback_is_ignored_after_fresh_player(player, monkeypatch):
    old_callback = player.player.events.attached[0][1]
    calls = []
    monkeypatch.setattr(player, "_on_vlc_end", lambda event: calls.append(event))

    player._create_fresh_vlc_player()
    old_callback("old")
    player.player.events.attached[0][1]("current")

    assert calls == ["current"]


def test_load_file_and_directory_collects_playlist_and_plays(player, tmp_path):
    first = tmp_path / "clip2.mp4"
    second = tmp_path / "clip10.mp4"
    first.write_text("", encoding="utf-8")
    second.write_text("", encoding="utf-8")

    player._load_file_and_directory(str(second))

    assert [os.path.basename(path) for path in player.directory_playlist] == [
        "clip2.mp4",
        "clip10.mp4",
    ]
    assert player.current_index == 1
    assert player.player.played == 1
    assert player.windowTitle().startswith("[2/2] clip10.mp4")


def test_open_external_file_ignores_missing_and_duplicate(player, tmp_path, monkeypatch):
    loaded = []
    file_path = tmp_path / "movie.mp4"
    file_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(player, "_load_file_and_directory", loaded.append)

    player.open_external_file("")
    player.open_external_file(str(tmp_path / "missing.mp4"))
    player.open_external_file(str(file_path))
    player.open_external_file(str(file_path))

    assert loaded == [str(file_path)]


def test_current_playlist_title_and_formatting(player):
    player.directory_playlist = [r"C:\v\a.mp4", r"C:\v\b.mp4"]
    player.current_index = 1
    player._media_length = 3_660_000

    assert player._format_ms(-1) == "00:00"
    assert player._format_ms(65_000) == "01:05"
    assert player._format_ms(3_660_000) == "01:01:00"
    assert player._current_file_path() == r"C:\v\b.mp4"

    player._update_window_title()
    assert player.windowTitle() == "[2/2] b.mp4 [01:01:00]"

    player.shuffle_enabled = True
    player.shuffled_playlist = [r"C:\v\b.mp4", r"C:\v\a.mp4"]
    player._update_window_title("custom.mp4")
    assert player.windowTitle() == "[S] [1/2] custom.mp4 [01:01:00]"


def test_window_title_includes_file_size(player, tmp_path):
    movie = tmp_path / "movie.mp4"
    movie.write_bytes(b"x" * 2048)
    player.directory_playlist = [str(movie)]
    player.current_index = 0
    player._media_length = 65_000

    player._update_window_title()

    assert player.windowTitle() == f"[1/1] movie.mp4 [01:05] [{2.0:.2f} KB]"


def test_current_file_size_bytes_missing_file_returns_minus_one(player, tmp_path):
    assert player._current_file_size_bytes("") == -1
    assert player._current_file_size_bytes(str(tmp_path / "nope.mp4")) == -1


def test_playback_controls_seek_rate_volume_and_mute(player):
    player.directory_playlist = ["a.mp4"]
    player.current_index = 0
    player.player.state = main_window.vlc.State.Stopped
    player.toggle_play()
    assert player.player.played == 1

    player.player.state = "Playing"
    player.player.playing = True
    player.toggle_play()
    assert not player.player.playing

    player.player.time = 115_000
    player.player.length = 120_000
    player.seek_by(20_000)
    assert player.player.time == 110_000
    player.seek_by(-200_000)
    assert player.player.time == 0

    player._change_playback_rate(10)
    assert player.playback_rate == player.playback_rate_max
    player._change_playback_rate(-10)
    assert player.playback_rate == player.playback_rate_min

    player.volume_slider.setValue(95)
    player._adjust_volume(10)
    assert player.volume_slider.value() == 100
    player._toggle_mute()
    assert player._muted


def test_preferred_audio_language_defaults_to_japanese(player):
    player.player.audio_track_descriptions = [
        (1, "Track 1 - English"),
        (2, "Track 2 - Japanese"),
    ]
    player.player.audio_track = 1

    assert player.preferred_audio_language == "ja"
    assert player._apply_preferred_audio_track(show_message=False)

    assert player.player.audio_track == 2


def test_select_audio_track_saves_language_preference(player):
    player.player.audio_track_descriptions = [
        (1, "Track 1 - Japanese"),
        (2, "Track 2 - English"),
    ]

    player._select_audio_track(2, "Track 2 - English")

    assert player.player.audio_track == 2
    assert player.preferred_audio_language == "en"
    assert player.settings.value("preferred_audio_language") == "en"


def test_saved_audio_language_applies_to_next_matching_track(player):
    player._select_audio_track(2, "English")
    player.player.audio_track_descriptions = [
        (3, "日本語"),
        (4, "English Commentary"),
    ]
    player.player.audio_track = 3

    assert player._apply_preferred_audio_track(show_message=False)

    assert player.player.audio_track == 4


def test_audio_track_menu_lists_tracks_and_marks_current(player):
    player.player.audio_track_descriptions = [(1, "English"), (2, "Japanese")]
    player.player.audio_track = 2
    menu = QtWidgets.QMenu()

    player._populate_audio_track_menu(menu)

    actions = menu.actions()
    assert [action.text() for action in actions] == ["English", "Japanese"]
    assert [action.isChecked() for action in actions] == [False, True]


def test_select_subtitle_track_saves_enabled_language_preference(player):
    player.player.spu_descriptions = [(-1, "Disable"), (3, "Japanese"), (4, "English")]

    player._select_subtitle_track(3, "Japanese")

    assert player.player.spu == 3
    assert player.subtitle_enabled
    assert player.preferred_subtitle_language == "ja"
    assert player.settings.value("subtitle_enabled", type=bool)
    assert player.settings.value("preferred_subtitle_language") == "ja"


def test_select_subtitle_off_saves_disabled_state(player):
    player.player.spu = 4

    player._select_subtitle_track(-1, "Disable")

    assert player.player.spu == -1
    assert not player.subtitle_enabled
    assert not player.settings.value("subtitle_enabled", type=bool)


def test_saved_subtitle_language_applies_when_enabled(player):
    player._select_subtitle_track(4, "English")
    player.player.spu_descriptions = [(-1, "Disable"), (8, "日本語"), (9, "English SDH")]
    player.player.spu = -1

    assert player._apply_preferred_subtitle_track(show_message=False)

    assert player.player.spu == 9


def test_subtitle_menu_lists_off_and_tracks(player):
    player.player.spu_descriptions = [(-1, "Disable"), (3, "English"), (4, "Japanese")]
    player.player.spu = -1
    menu = QtWidgets.QMenu()

    player._populate_subtitle_track_menu(menu)

    actions = menu.actions()
    assert [action.text() for action in actions] == ["オフ", "English", "Japanese"]
    assert [action.isChecked() for action in actions] == [True, False, False]


def test_menu_bar_contains_common_player_menus(player):
    titles = [action.text() for action in player.menuBar().actions()]

    assert titles == ["ファイル", "再生", "音声", "字幕", "表示", "ツール", "ヘルプ"]


def test_status_time_updates_slider_warning_and_snapshot(player):
    player.directory_playlist = ["a.mp4"]
    player.current_index = 0
    player.player.time = 119_000
    player.player.length = 120_000

    player._update_status_time()

    assert player.seek_slider.maximum() == 120_000
    assert player.seek_slider.value() == 119_000
    assert player._media_length == 120_000
    assert player._is_seek_bar_warning

    player.player.time = 1_000
    player._update_status_time()
    assert not player._is_seek_bar_warning


def test_slider_handlers_set_player_time_and_status(player):
    player._media_length = 120_000
    player.seek_slider.setValue(42_000)

    player._on_seek_pressed()
    player._on_slider_moved(60_000)
    player._on_seek_released()
    player._on_slider_clicked(10_000)

    assert not player._seeking_user
    assert player.player.time == 10_000


def test_repeat_and_shuffle_toggles(player, monkeypatch):
    player.directory_playlist = ["a.mp4", "b.mp4", "c.mp4"]
    player.current_index = 1
    monkeypatch.setattr("random.shuffle", lambda items: items.reverse())

    player._on_repeat_toggled(True)
    assert player.repeat_enabled
    assert player.btn_repeat.isChecked()

    player._on_shuffle_toggled(True)
    assert player.shuffle_enabled
    assert player.shuffled_playlist == ["b.mp4", "c.mp4", "a.mp4"]
    assert player.btn_shuffle.isChecked()

    player._on_shuffle_toggled(False)
    assert player.shuffled_playlist == []


def test_play_next_previous_and_media_end_schedule_expected_indices(player, monkeypatch):
    calls = []
    monkeypatch.setattr(
        main_window.QtCore.QTimer,
        "singleShot",
        lambda _delay, callback: callback(),
    )
    monkeypatch.setattr(player, "play_at", calls.append)
    player.directory_playlist = ["a.mp4", "b.mp4", "c.mp4"]
    player.current_index = 1
    player.repeat_enabled = False
    player.shuffle_enabled = False

    player.play_next()
    player.play_previous()

    assert calls == [2, 0]

    end_calls = []
    monkeypatch.setattr(
        player, "_play_at_with_reason", lambda index, reason: end_calls.append((index, reason))
    )
    player._on_media_end()
    assert end_calls == [(2, "from_end")]


def test_media_end_repeat_reloads_current_media(player, monkeypatch):
    monkeypatch.setattr(
        main_window.QtCore.QTimer,
        "singleShot",
        lambda _delay, callback: callback(),
    )
    player.directory_playlist = ["a.mp4", "b.mp4"]
    player.current_index = 0
    player.repeat_enabled = True
    player.shuffle_enabled = False
    player.player.time = 12_000
    player.player.state = "Ended"

    player._on_media_end()

    assert player.vlc_instance.created_media[-1].path == "a.mp4"
    assert player.vlc_instance.created_media[-1].parsed
    assert player.player.media.path == "a.mp4"
    assert player.player.playing
    assert player.seek_slider.maximum() == 0


def test_move_current_file_updates_playlist_without_real_play(player, tmp_path, monkeypatch):
    first = tmp_path / "a.mp4"
    second = tmp_path / "b.mp4"
    first.write_text("a", encoding="utf-8")
    second.write_text("b", encoding="utf-8")
    player.directory_playlist = [str(first), str(second)]
    player.current_index = 0
    calls = []
    monkeypatch.setattr(
        main_window.QtCore.QTimer,
        "singleShot",
        lambda _delay, callback: callback(),
    )
    monkeypatch.setattr(player, "play_at", calls.append)

    player._move_current_file_and_play_next("_ok")

    assert not first.exists()
    assert (tmp_path / "_ok" / "a.mp4").exists()
    assert player.directory_playlist == [str(second)]
    assert calls == [0]
    assert player.player.media is None
    assert not player._file_operation_in_progress


def test_move_current_file_target_exists_cancel_keeps_playlist_and_playback(player, tmp_path):
    first = tmp_path / "a.mp4"
    second = tmp_path / "b.mp4"
    first.write_text("a", encoding="utf-8")
    second.write_text("b", encoding="utf-8")
    target_dir = tmp_path / "_ok"
    target_dir.mkdir()
    (target_dir / "a.mp4").write_text("existing", encoding="utf-8")
    player.directory_playlist = [str(first), str(second)]
    player.current_index = 0
    player.player.playing = True
    player._prompt_target_file_exists = lambda *args, **kwargs: "cancel"

    player._move_current_file_and_play_next("_ok")

    assert first.exists()
    assert player.directory_playlist == [str(first), str(second)]
    assert player.current_index == 0
    assert player.player.stopped == 0
    assert player.player.playing
    assert not player._file_operation_in_progress


def test_move_current_file_target_exists_delete_sends_source_to_trash(
    player, tmp_path, monkeypatch
):
    first = tmp_path / "a.mp4"
    second = tmp_path / "b.mp4"
    first.write_text("a", encoding="utf-8")
    second.write_text("b", encoding="utf-8")
    target_dir = tmp_path / "_ok"
    target_dir.mkdir()
    (target_dir / "a.mp4").write_text("existing", encoding="utf-8")
    player.directory_playlist = [str(first), str(second)]
    player.current_index = 0
    player._prompt_target_file_exists = lambda *args, **kwargs: "delete"
    # 実際のごみ箱を汚さないよう、TrashService を fake に差し替える
    trashed = []
    player.trash_service = TrashService(lambda path: trashed.append(path))
    calls = []
    monkeypatch.setattr(
        main_window.QtCore.QTimer,
        "singleShot",
        lambda _delay, callback: callback(),
    )
    monkeypatch.setattr(player, "play_at", calls.append)

    player._move_current_file_and_play_next("_ok")

    assert trashed == [str(first)]
    assert (target_dir / "a.mp4").read_text(encoding="utf-8") == "existing"
    assert player.directory_playlist == [str(second)]
    assert calls == [0]
    assert not player._file_operation_in_progress


def test_move_current_file_target_exists_delete_keeps_playlist_when_trash_fails(
    player, tmp_path, monkeypatch
):
    first = tmp_path / "a.mp4"
    second = tmp_path / "b.mp4"
    first.write_text("a", encoding="utf-8")
    second.write_text("b", encoding="utf-8")
    target_dir = tmp_path / "_ok"
    target_dir.mkdir()
    (target_dir / "a.mp4").write_text("existing", encoding="utf-8")
    player.directory_playlist = [str(first), str(second)]
    player.current_index = 0
    player._prompt_target_file_exists = lambda *args, **kwargs: "delete"
    player.trash_service = TrashService(
        lambda path: (_ for _ in ()).throw(RuntimeError("trash failed"))
    )
    calls = []
    monkeypatch.setattr(player, "play_at", calls.append)

    player._move_current_file_and_play_next("_ok")

    assert first.exists()
    assert player.directory_playlist == [str(first), str(second)]
    assert calls == []
    assert "ごみ箱への移動に失敗" in player.status.currentMessage()
    assert not player._file_operation_in_progress


def test_move_current_file_target_exists_delete_does_not_fall_back_to_remove(
    player, tmp_path, monkeypatch
):
    first = tmp_path / "a.mp4"
    first.write_text("a", encoding="utf-8")
    target_dir = tmp_path / "_ok"
    target_dir.mkdir()
    (target_dir / "a.mp4").write_text("existing", encoding="utf-8")
    player.directory_playlist = [str(first)]
    player.current_index = 0
    player._prompt_target_file_exists = lambda *args, **kwargs: "delete"
    # ごみ箱が無い環境では完全削除にフォールバックしない
    player.trash_service = TrashService(None)

    player._move_current_file_and_play_next("_ok")

    assert first.exists()
    assert (target_dir / "a.mp4").read_text(encoding="utf-8") == "existing"
    assert player.directory_playlist == [str(first)]
    assert not player._file_operation_in_progress


def test_move_current_file_release_timeout_aborts_operation(player, tmp_path, monkeypatch):
    first = tmp_path / "a.mp4"
    second = tmp_path / "b.mp4"
    first.write_text("a", encoding="utf-8")
    second.write_text("b", encoding="utf-8")
    player.directory_playlist = [str(first), str(second)]
    player.current_index = 0
    # メディア解放がタイムアウトした状況を模す
    monkeypatch.setattr(player, "_release_current_media_for_file_operation", lambda: False)
    trashed = []
    player.trash_service = TrashService(lambda path: trashed.append(path))
    calls = []
    monkeypatch.setattr(player, "play_at", calls.append)

    player._move_current_file_and_play_next("_ok")

    # ファイル操作・次再生は一切行われない
    assert first.exists()
    assert not (tmp_path / "_ok").exists()
    assert trashed == []
    assert player.directory_playlist == [str(first), str(second)]
    assert calls == []
    assert not player._file_operation_in_progress


def test_stop_and_clear_media_timeout_skips_set_media(player, monkeypatch):
    # stop() がブロックし続ける状況を模し、タイムアウトで False を返すこと、
    # set_media(None) が呼ばれず、player が差し替えられることを確認する。
    block = main_window.threading.Event()
    old_player = player.player
    old_vlc_player = player.vlc_player
    set_media_calls = []

    def blocking_stop(*args, **kwargs):
        block.wait(2.0)
        return True

    monkeypatch.setattr(old_vlc_player, "stop", blocking_stop)
    monkeypatch.setattr(
        old_vlc_player,
        "set_media",
        lambda *a, **k: set_media_calls.append(a),
    )

    try:
        result = player._stop_and_clear_media_without_blocking_ui(timeout_ms=80)
    finally:
        block.set()

    assert result is False
    assert set_media_calls == []
    assert player.player is not old_player
    assert player.vlc_player is not old_vlc_player
    assert player.player.surface is not None


def test_stop_and_clear_media_success_clears_media(player, monkeypatch):
    set_media_calls = []
    monkeypatch.setattr(player.vlc_player, "stop", lambda *a, **k: True)
    monkeypatch.setattr(
        player.vlc_player,
        "set_media",
        lambda media, **k: set_media_calls.append(media),
    )

    result = player._stop_and_clear_media_without_blocking_ui(timeout_ms=2000)

    assert result is True
    assert set_media_calls == [None]


def test_move_current_file_target_exists_rename_saves_with_unique_name(
    player, tmp_path, monkeypatch
):
    first = tmp_path / "a.mp4"
    second = tmp_path / "b.mp4"
    first.write_text("source", encoding="utf-8")
    second.write_text("b", encoding="utf-8")
    target_dir = tmp_path / "_ok"
    target_dir.mkdir()
    (target_dir / "a.mp4").write_text("existing", encoding="utf-8")
    player.directory_playlist = [str(first), str(second)]
    player.current_index = 0
    player._prompt_target_file_exists = lambda *args, **kwargs: "rename"
    calls = []
    monkeypatch.setattr(
        main_window.QtCore.QTimer,
        "singleShot",
        lambda _delay, callback: callback(),
    )
    monkeypatch.setattr(player, "play_at", calls.append)

    player._move_current_file_and_play_next("_ok")

    assert not first.exists()
    assert (target_dir / "a.mp4").read_text(encoding="utf-8") == "existing"
    assert (target_dir / "a (1).mp4").read_text(encoding="utf-8") == "source"
    assert player.directory_playlist == [str(second)]
    assert calls == [0]
    assert not player._file_operation_in_progress


def test_move_current_file_shuffle_uses_remembered_next_path(player, tmp_path, monkeypatch):
    first = tmp_path / "a.mp4"
    second = tmp_path / "b.mp4"
    third = tmp_path / "c.mp4"
    for path in (first, second, third):
        path.write_text(path.stem, encoding="utf-8")
    player.directory_playlist = [str(first), str(second), str(third)]
    player.current_index = 1
    player.shuffle_enabled = True
    player.shuffled_playlist = [str(second), str(first), str(third)]
    calls = []
    monkeypatch.setattr(
        main_window.QtCore.QTimer,
        "singleShot",
        lambda _delay, callback: callback(),
    )
    monkeypatch.setattr(player, "play_at", calls.append)

    player._move_current_file_and_play_next("_ok")

    assert player.directory_playlist == [str(first), str(third)]
    assert calls == [0]


def test_media_end_ignored_during_file_operation(player, monkeypatch):
    player.directory_playlist = ["a.mp4", "b.mp4"]
    player.current_index = 0
    player._file_operation_in_progress = True
    calls = []
    monkeypatch.setattr(player, "_play_at_with_reason", lambda index, reason: calls.append(index))

    player._on_media_end()

    assert calls == []


def test_vlc_operation_exceptions_do_not_crash_ui_handlers(player, monkeypatch):
    errors = []
    monkeypatch.setattr(
        main_window.diagnostics, "record_exception", lambda *args, **kwargs: errors.append(args)
    )

    player.player.set_time = lambda _value: (_ for _ in ()).throw(RuntimeError("set_time"))
    player.seek_slider.setValue(10_000)
    player._on_seek_released()
    player._on_slider_clicked(20_000)

    player.player.stop = lambda: (_ for _ in ()).throw(RuntimeError("stop"))
    player.stop()

    player.player.audio_toggle_mute = lambda: (_ for _ in ()).throw(RuntimeError("mute"))
    player._toggle_mute()

    assert [item[0] for item in errors] == [
        "seek_released_set_time",
        "slider_clicked_set_time",
        "stop_player_stop",
        "toggle_mute_audio_toggle_mute",
    ]


def test_playback_rate_state_updates_only_when_vlc_accepts_change(player):
    player.playback_rate = 1.0
    player.player.set_rate = lambda _value: -1

    player._change_playback_rate(0.1)

    assert player.playback_rate == 1.0
    assert "再生速度の変更に失敗" in player.status.currentMessage()


def test_mute_state_updates_only_when_vlc_toggle_succeeds(player):
    player._muted = False
    player.player.audio_toggle_mute = lambda: -1

    player._toggle_mute()

    assert not player._muted
    assert "ミュート切替に失敗" in player.status.currentMessage()


def test_vlc_adapter_coerces_invalid_numeric_results(player, monkeypatch):
    errors = []
    monkeypatch.setattr(
        main_window.diagnostics, "record_exception", lambda *args, **kwargs: errors.append(args)
    )
    player.player.get_time = lambda: None
    player.player.get_length = lambda: "bad"
    player.player.get_rate = lambda: object()
    player.player.audio_get_mute = lambda: None

    assert player.vlc_player.get_time() == -1
    assert player.vlc_player.get_length() == -1
    assert player.vlc_player.get_rate() == 1.0
    assert player.vlc_player.audio_get_mute() == -1
    assert [item[0] for item in errors] == [
        "vlc_get_time_convert",
        "vlc_get_length_convert",
        "vlc_get_rate_convert",
        "vlc_audio_get_mute_convert",
    ]


def test_metadata_dialog_receives_collected_text(player, monkeypatch):
    shown = []

    class FakeDialog:
        def __init__(self, text, parent):
            shown.append((text, parent))

        def exec_(self):
            shown.append("exec")

    player.directory_playlist = ["movie.mp4"]
    player.current_index = 0
    player.player.media.meta = {main_window.vlc.Meta.Title: "Sample"}
    monkeypatch.setattr(main_window, "MetadataDialog", FakeDialog)

    player._show_metadata_dialog()

    assert "ファイルパス: movie.mp4" in shown[0][0]
    assert "長さ: 02:05 (125000 ms)" in shown[0][0]
    assert "Title: Sample" in shown[0][0]
    assert shown[1] == "exec"


def test_drag_drop_and_keypad_events(player, tmp_path, monkeypatch):
    loaded = []
    monkeypatch.setattr(player, "_load_file_and_directory", loaded.append)
    path = tmp_path / "movie.mp4"
    path.write_text("", encoding="utf-8")

    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl.fromLocalFile(str(path))])
    drop = QtGui.QDropEvent(
        QtCore.QPointF(1, 1),
        QtCore.Qt.CopyAction,
        mime,
        QtCore.Qt.LeftButton,
        QtCore.Qt.NoModifier,
    )
    player.dropEvent(drop)
    assert [os.path.normpath(item) for item in loaded] == [os.path.normpath(str(path))]

    seeks = []
    monkeypatch.setattr(player, "seek_by", seeks.append)
    event = QtGui.QKeyEvent(
        QtCore.QEvent.KeyPress,
        QtCore.Qt.Key_4,
        QtCore.Qt.KeypadModifier,
    )
    player.keyPressEvent(event)
    assert seeks == [player.SEEK_LONG_MS]

    # 連打直後(スロットリング窓内)のオートリピートは無視される
    repeat_event = QtGui.QKeyEvent(
        QtCore.QEvent.KeyPress,
        QtCore.Qt.Key_4,
        QtCore.Qt.KeypadModifier,
        "",
        True,
    )
    player.keyPressEvent(repeat_event)
    assert seeks == [player.SEEK_LONG_MS]

    # 長押し継続でスロットリング窓を超えたオートリピートは連続シークとして受け付ける
    player._last_keypad_seek_msec_by_key[int(QtCore.Qt.Key_4)] = 0
    player.keyPressEvent(repeat_event)
    assert seeks == [player.SEEK_LONG_MS, player.SEEK_LONG_MS]

    previous_event = QtGui.QKeyEvent(
        QtCore.QEvent.KeyPress,
        QtCore.Qt.Key_1,
        QtCore.Qt.KeypadModifier,
    )
    player.keyPressEvent(previous_event)
    assert seeks == [player.SEEK_LONG_MS, player.SEEK_LONG_MS, -player.SEEK_LONG_MS]


def test_status_time_does_not_overwrite_priority_message(player):
    player.directory_playlist = ["a.mp4"]
    player.current_index = 0
    player.player.time = 5_000
    player.player.length = 60_000

    player._show_status_message("移動完了: a.mp4", 5000)
    msg_after_priority = player.status.currentMessage()
    assert "移動完了" in msg_after_priority

    player._update_status_time()

    assert player.status.currentMessage() == msg_after_priority


def test_media_end_ending_flag_stays_true_until_end_after(player, monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        main_window.QtCore.QTimer,
        "singleShot",
        lambda _, cb: scheduled.append(cb),
    )
    player.directory_playlist = ["a.mp4", "b.mp4"]
    player.current_index = 0
    player.repeat_enabled = False
    player.shuffle_enabled = False

    # 1回目: _ending=True のまま timer をスケジュール
    player._on_media_end()
    assert player._ending
    assert len(scheduled) == 1

    # 2回目: _ending=True なので無視される
    player._on_media_end()
    assert len(scheduled) == 1

    # timer 発火: _end_after が _ending をリセット
    play_calls = []
    monkeypatch.setattr(player, "play_at", play_calls.append)
    scheduled[0]()
    assert not player._ending
    assert play_calls == [1]


def test_end_after_resets_ending_even_on_play_at_exception(player, monkeypatch):
    player.directory_playlist = ["a.mp4", "b.mp4"]
    player.current_index = 0
    player._ending = True

    def raise_error(_):
        raise RuntimeError("boom")

    monkeypatch.setattr(player, "play_at", raise_error)

    try:
        player._end_after(1)
    except RuntimeError:
        pass

    assert not player._ending
