import os

from wagom_player import sorting


def test_fallback_key_prefers_case_insensitive_natural_order():
    key = sorting._create_windows_logical_key(None)

    files = [
        "/tmp/File10.mp4",
        "/tmp/file2.mp4",
        "/tmp/file-3.mp4",
        "/tmp/File1.mp4",
    ]

    expected = ["file-3.mp4", "File1.mp4", "File10.mp4", "file2.mp4"]
    sorted_files = sorted(files, key=key)

    assert expected == [os.path.basename(p) for p in sorted_files]


def test_cmp_to_key_path_uses_basename_and_comparer():
    calls = []

    def fake_comparer(a: str, b: str) -> int:
        calls.append((a, b))
        return -1 if a < b else (1 if a > b else 0)

    key = sorting._create_windows_logical_key(fake_comparer)
    files = ["/tmp/b.mp4", "/tmp/A.mp4"]

    sorted(files, key=key)

    assert ("A.mp4", "b.mp4") in calls
