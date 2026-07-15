from wagom_player.domain.tracks import find_track, language_key, normalize_language


def test_language_normalization_and_detection():
    assert normalize_language("Japanese") == "ja"
    assert normalize_language("ENG") == "en"
    assert language_key("Track 1 - 日本語") == "ja"
    assert language_key("Commentary") == ""


def test_language_normalization_accepts_locale_variants():
    assert normalize_language("en_US") == "en"
    assert normalize_language("en-US") == "en"
    assert normalize_language("JA_jp") == "ja"
    assert normalize_language("") == "ja"
    assert normalize_language("xx") == "xx"


def test_find_track_returns_matching_language_only():
    tracks = [(1, "日本語"), (2, "English"), (3, "Commentary")]

    assert find_track(tracks, "en") == (2, "English")
    assert find_track(tracks, "ko") is None
