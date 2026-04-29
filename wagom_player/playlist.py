import ctypes
import functools
import os
import re
import sys
from typing import List


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


def natural_key(path: str):
    """ファイル名を自然順ソートするためのキーを生成する (例: 2.mp4 < 10.mp4)"""
    name = os.path.basename(path)
    parts = re.split(r"(\d+)", name)
    return [int(p) if p.isdigit() else p.casefold() for p in parts]


def _load_windows_logical_comparer():
    if not sys.platform.startswith("win"):
        return None

    try:
        shlwapi = ctypes.windll.Shlwapi
    except Exception:
        return None

    try:
        cmp_func = shlwapi.StrCmpLogicalW
        cmp_func.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        cmp_func.restype = ctypes.c_int
    except Exception:
        return None

    return cmp_func


_STRCMP_LOGICALW = _load_windows_logical_comparer()


def _create_windows_logical_key(comparer=_STRCMP_LOGICALW):
    """Windowsの論理順比較に基づくキーを生成する。"""

    if comparer:

        def _cmp(a: str, b: str) -> int:
            return comparer(os.path.basename(a), os.path.basename(b))

        return functools.cmp_to_key(_cmp)

    def _fallback_key(path: str):
        return natural_key(path)

    return _fallback_key


windows_logical_key = _create_windows_logical_key()


def is_supported_video_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUPPORTED_VIDEO_EXTENSIONS


def collect_video_files(directory: str) -> List[str]:
    video_files = [
        os.path.join(directory, name)
        for name in os.listdir(directory)
        if is_supported_video_file(name)
    ]
    video_files.sort(key=windows_logical_key)
    return video_files
