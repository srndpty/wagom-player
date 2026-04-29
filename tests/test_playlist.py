from pathlib import Path

from wagom_player import playlist


def test_is_supported_video_file_is_case_insensitive():
    assert playlist.is_supported_video_file("sample.MP4")
    assert playlist.is_supported_video_file("sample.m2ts")
    assert not playlist.is_supported_video_file("sample.txt")


def test_collect_video_files_filters_and_sorts(tmp_path: Path):
    for name in ["clip10.mp4", "clip2.mp4", "note.txt", "clip1.MKV"]:
        (tmp_path / name).write_text("", encoding="utf-8")

    files = playlist.collect_video_files(str(tmp_path))

    assert [Path(path).name for path in files] == [
        "clip1.MKV",
        "clip2.mp4",
        "clip10.mp4",
    ]
