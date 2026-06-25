from wagom_player.domain.formatting import format_size
from wagom_player.domain.window_title import build_window_title


def test_format_size_units():
    assert format_size(0) == "0 B"
    assert format_size(512) == "512 B"
    assert format_size(2048) == "2.00 KB"
    assert format_size(5 * 1024 * 1024) == "5.00 MB"
    assert format_size(3 * 1024**3) == "3.00 GB"
    assert format_size(-1) == ""


def test_build_window_title_appends_size_after_duration():
    title = build_window_title(
        playlist=[r"C:\v\a.mp4", r"C:\v\b.mp4"],
        current_path=r"C:\v\b.mp4",
        shuffle_enabled=False,
        media_length_ms=65_000,
        file_size_bytes=2048,
    )
    assert title == "[2/2] b.mp4 [01:05] [2.00 KB]"


def test_build_window_title_omits_size_when_unknown():
    title = build_window_title(
        playlist=[r"C:\v\a.mp4"],
        current_path=r"C:\v\a.mp4",
        shuffle_enabled=False,
        media_length_ms=0,
        file_size_bytes=-1,
    )
    assert title == "[1/1] a.mp4"
