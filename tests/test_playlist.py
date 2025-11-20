from wagom_player.playlist import PlaylistManager, is_supported_video


def test_is_supported_video_checks_extension():
    assert is_supported_video("movie.mp4")
    assert not is_supported_video("document.txt")


def test_load_sorts_and_sets_current(monkeypatch):
    manager = PlaylistManager()
    files = ["/tmp/b2.mkv", "/tmp/a1.mkv"]
    manager.load(files, current="/tmp/b2.mkv")

    assert manager.files[0].endswith("a1.mkv")
    assert manager.current_path.endswith("b2.mkv")


def test_shuffle_preserves_current_and_randomizes(monkeypatch):
    manager = PlaylistManager()
    manager._random.seed(1)
    files = [f"/tmp/file{i}.mp4" for i in range(3)]
    manager.load(files, current=files[1])

    manager.set_shuffle(True)
    playlist = manager.current_playlist

    assert playlist[0].endswith("file1.mp4")
    assert set(playlist) == set(manager.files)


def test_next_and_previous_with_repeat_and_shuffle():
    manager = PlaylistManager()
    files = [f"/tmp/file{i}.mp4" for i in range(3)]
    manager.load(files, current=files[0])

    manager.set_repeat(True)
    assert manager.next_index() == 0

    manager.set_repeat(False)
    manager.set_shuffle(True)
    manager.current_index = manager.files.index(files[1])
    assert manager.previous_index() in (0, 2)


def test_remove_updates_current_index():
    manager = PlaylistManager()
    files = [f"/tmp/file{i}.mp4" for i in range(3)]
    manager.load(files, current=files[1])
    manager.set_shuffle(True)

    manager.remove(1)

    assert len(manager.files) == 2
    assert manager.current_index in (0, 1, -1)
    assert manager.describe().startswith("1 /")
