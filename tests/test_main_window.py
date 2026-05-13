import importlib
import os

import pytest

QtCore = pytest.importorskip("PyQt5.QtCore", exc_type=ImportError)
QtGui = pytest.importorskip("PyQt5.QtGui", exc_type=ImportError)

main_window = importlib.import_module("wagom_player.main_window")


class FakeEventManager:
    def __init__(self):
        self.attached = []

    def event_attach(self, event_type, callback):
        self.attached.append((event_type, callback))


class FakeMedia:
    def __init__(self, path=""):
        self.path = path
        self.parsed = False
        self.duration = 125_000
        self.meta = {}

    def parse(self):
        self.parsed = True

    def get_duration(self):
        return self.duration

    def get_meta(self, field):
        return self.meta.get(field)


class FakePlayer:
    def __init__(self):
        self.events = FakeEventManager()
        self.volume = 80
        self.muted = False
        self.rate = 1.0
        self.time = 0
        self.length = 120_000
        self.playing = False
        self.state = "Paused"
        self.media = FakeMedia()
        self.stopped = 0
        self.played = 0
        self.surface = None

    def event_manager(self):
        return self.events

    def audio_set_volume(self, value):
        self.volume = value

    def audio_get_mute(self):
        return int(self.muted)

    def audio_set_mute(self, value):
        self.muted = bool(value)

    def audio_toggle_mute(self):
        self.muted = not self.muted

    def set_rate(self, value):
        self.rate = value

    def get_rate(self):
        return self.rate

    def get_state(self):
        return self.state

    def is_playing(self):
        return self.playing

    def pause(self):
        self.playing = False
        self.state = "Paused"

    def play(self):
        self.played += 1
        self.playing = True
        self.state = "Playing"

    def stop(self):
        self.stopped += 1
        self.playing = False
        self.state = "Stopped"

    def get_time(self):
        return self.time

    def set_time(self, value):
        self.time = value

    def get_length(self):
        return self.length

    def set_media(self, media):
        self.media = media

    def get_media(self):
        return self.media

    def set_hwnd(self, wid):
        self.surface = ("hwnd", wid)

    def set_nsobject(self, wid):
        self.surface = ("nsobject", wid)

    def set_xwindow(self, wid):
        self.surface = ("xwindow", wid)


class FakeInstance:
    def __init__(self, args=None):
        self.args = args or []
        self.player = FakePlayer()
        self.created_media = []

    def media_player_new(self):
        return self.player

    def media_new(self, path):
        media = FakeMedia(path)
        self.created_media.append(media)
        return media


class FakeVlc:
    class EventType:
        MediaPlayerEndReached = "ended"

    class State:
        Stopped = "Stopped"
        Ended = "Ended"
        Error = "Error"

    class Meta:
        Title = "Title"
        Artist = "Artist"
        Album = "Album"
        AlbumArtist = "AlbumArtist"
        Genre = "Genre"
        Date = "Date"
        Description = "Description"
        TrackNumber = "TrackNumber"
        TrackTotal = "TrackTotal"
        DiscNumber = "DiscNumber"
        DiscTotal = "DiscTotal"
        TrackID = "TrackID"
        ShowName = "ShowName"
        Season = "Season"
        Episode = "Episode"
        Director = "Director"
        Actors = "Actors"
        Rating = "Rating"
        Language = "Language"
        Copyright = "Copyright"
        Publisher = "Publisher"
        EncodedBy = "EncodedBy"
        Setting = "Setting"
        URL = "URL"
        ArtworkURL = "ArtworkURL"
        NowPlaying = "NowPlaying"

    def __init__(self):
        self.instances = []

    def Instance(self, args):
        instance = FakeInstance(args)
        self.instances.append(instance)
        return instance

    def libvlc_get_version(self):
        return b"fake-vlc"


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
    assert player.player.events.attached == [("ended", player._on_vlc_end)]
    assert player.btn_repeat.isCheckable()
    assert player.btn_shuffle.isCheckable()


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
