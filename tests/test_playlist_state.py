from wagom_player.playlist_state import (
    active_playlist,
    adjacent_index,
    create_shuffled_playlist,
    next_index_after_removal,
    next_path,
)


def test_active_playlist_uses_shuffle_only_when_enabled():
    directory = ["a.mp4", "b.mp4"]
    shuffled = ["b.mp4", "a.mp4"]

    assert active_playlist(directory, shuffled, False) == directory
    assert active_playlist(directory, shuffled, True) == shuffled


def test_create_shuffled_playlist_keeps_current_item_first():
    def reverse_shuffle(items):
        items.reverse()

    shuffled = create_shuffled_playlist(["a.mp4", "b.mp4", "c.mp4"], 1, reverse_shuffle)

    assert shuffled == ["b.mp4", "c.mp4", "a.mp4"]


def test_create_shuffled_playlist_returns_empty_for_invalid_current_index():
    assert create_shuffled_playlist(["a.mp4"], -1, lambda items: None) == []
    assert create_shuffled_playlist(["a.mp4"], 1, lambda items: None) == []


def test_adjacent_index_returns_original_index_for_active_order():
    directory = ["a.mp4", "b.mp4", "c.mp4"]
    active = ["b.mp4", "c.mp4", "a.mp4"]

    assert adjacent_index(directory, active, 1, 1) == 2
    assert adjacent_index(directory, active, 1, -1) is None
    assert adjacent_index(directory, active, 2, 1) == 0


def test_adjacent_index_handles_missing_or_end_of_playlist():
    assert adjacent_index(["a.mp4"], ["a.mp4"], 0, 1) is None
    assert adjacent_index(["a.mp4"], ["missing.mp4"], 0, 1) is None
    assert adjacent_index(["a.mp4"], ["a.mp4"], 3, 1) is None


def test_next_path_returns_following_active_item():
    assert next_path(["a.mp4", "b.mp4"], "a.mp4") == "b.mp4"
    assert next_path(["a.mp4", "b.mp4"], "b.mp4") is None
    assert next_path(["a.mp4"], "missing.mp4") is None


def test_next_index_after_removal_for_normal_order():
    assert next_index_after_removal(["b.mp4", "c.mp4"], 0, False, None) == 0
    assert next_index_after_removal(["a.mp4"], 1, False, None) is None
    assert next_index_after_removal([], 0, False, None) is None


def test_next_index_after_removal_for_shuffle_order():
    directory = ["a.mp4", "c.mp4"]

    assert next_index_after_removal(directory, 1, True, "c.mp4") == 1
    assert next_index_after_removal(directory, 1, True, "missing.mp4") is None
    assert next_index_after_removal(directory, 1, True, None) is None
