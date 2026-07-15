import ctypes
import functools
import os
import re
import sys

SUPPORTED_VIDEO_EXTENSIONS = (
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".asf",
    ".ts",
    ".m2ts",
    ".m4v",
    ".3gp",
    ".3g2",
    ".mpeg",
    ".mpg",
    ".mpe",
    ".rm",
    ".rmvb",
    ".vob",
    ".webm",
)


def natural_key(path: str) -> list[object]:
    """ファイル名を、大文字と小文字を区別しない自然順へ変換する。"""
    parts = re.split(r"(\d+)", os.path.basename(path))
    return [int(part) if part.isdigit() else part.casefold() for part in parts]


def create_windows_logical_key(comparer=None):
    """Windowsの論理順比較関数、または自然順の代替キーを返す。"""
    if comparer:

        def compare(left: str, right: str) -> int:
            return comparer(os.path.basename(left), os.path.basename(right))

        return functools.cmp_to_key(compare)
    return natural_key


def is_supported_video_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUPPORTED_VIDEO_EXTENSIONS


def _load_windows_logical_comparer():
    if not sys.platform.startswith("win"):
        return None
    try:
        comparer = ctypes.windll.Shlwapi.StrCmpLogicalW
        comparer.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        comparer.restype = ctypes.c_int
        return comparer
    except (AttributeError, OSError):
        return None


windows_logical_key = create_windows_logical_key(_load_windows_logical_comparer())


def collect_video_files(directory: str) -> list[str]:
    paths = [
        os.path.join(directory, name)
        for name in os.listdir(directory)
        if is_supported_video_file(name)
    ]
    paths.sort(key=windows_logical_key)
    return paths
