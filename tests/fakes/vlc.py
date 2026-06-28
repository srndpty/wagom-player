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
        self.audio_track = 1
        self.audio_track_descriptions = [(1, "English"), (2, "Japanese")]
        self.spu = -1
        self.spu_descriptions = [(-1, "Disable"), (3, "English"), (4, "Japanese")]

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

    def audio_get_track(self):
        return self.audio_track

    def audio_set_track(self, value):
        if value not in [track_id for track_id, _name in self.audio_track_descriptions]:
            return -1
        self.audio_track = value
        return 0

    def audio_get_track_description(self):
        return self.audio_track_descriptions

    def video_get_spu(self):
        return self.spu

    def video_set_spu(self, value):
        if value not in [spu_id for spu_id, _name in self.spu_descriptions]:
            return -1
        self.spu = value
        return 0

    def video_get_spu_description(self):
        return self.spu_descriptions

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
        MediaPlayerPlaying = "playing"

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
