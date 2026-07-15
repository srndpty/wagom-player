import ctypes
import os
import sys

from ..domain.playlist import create_windows_logical_key, is_supported_video_file


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
