import types

from wagom_player import vlc_client


class DummyPlayer:
    def __init__(self):
        self.media = None
        self.widget_id = None
        self.rate = 1.0
        self.time = 0
        self.playing = False

    def set_hwnd(self, wid):
        self.widget_id = wid

    def set_xwindow(self, wid):
        self.widget_id = wid

    def set_media(self, media):
        self.media = media

    def play(self):
        self.playing = True
        return "playing"

    def pause(self):
        self.playing = False
        return "paused"

    def stop(self):
        self.playing = False
        return "stopped"

    def is_playing(self):
        return self.playing

    def set_time(self, position):
        self.time = position

    def get_time(self):
        return self.time

    def get_length(self):
        return 1000

    def set_rate(self, rate):
        self.rate = rate

    def get_state(self):
        return "STATE"


class DummyInstance:
    def __init__(self, args=None):
        self.args = args or []

    def media_player_new(self):
        return DummyPlayer()

    def media_new(self, path):
        return f"media:{path}"


def test_controller_wraps_vlc(monkeypatch):
    dummy_module = types.SimpleNamespace(Instance=lambda args: DummyInstance(args))
    monkeypatch.setattr(vlc_client, "vlc", dummy_module)

    controller = vlc_client.VlcController()

    controller.set_widget(10)
    controller.play_file("/tmp/sample.mp4")
    controller.pause_or_play()
    controller.set_time(500)
    controller.set_rate(1.5)

    assert controller.player.widget_id == 10
    assert controller.player.media == "media:/tmp/sample.mp4"
    assert controller.player.get_time() == 500
    assert controller.player.rate == 1.5
    assert controller.get_length() == 1000
    assert controller.get_state() == "STATE"
