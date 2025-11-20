"""ファイル名ソートやキー生成に関するユーティリティ。"""
from __future__ import annotations

import ctypes
import functools
import locale
import os
import re
import sys
from typing import Callable, List


def natural_key(path: str) -> List[object]:
    """数字を含むファイル名を人間にとって自然な順序で並べるためのキー。

    例: ``["movie2.mp4", "movie10.mp4"]`` は ``movie2`` が先に来る。
    """

    name = os.path.basename(path)
    parts = re.split(r"(\d+)", name)
    return [int(p) if p.isdigit() else p.casefold() for p in parts]


def _load_windows_logical_comparer() -> Callable[[str, str], int] | None:
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


def _create_windows_logical_key(comparer=_load_windows_logical_comparer()):
    if comparer:
        def _cmp(a: str, b: str) -> int:
            return comparer(os.path.basename(a), os.path.basename(b))

        return functools.cmp_to_key(_cmp)

    locale_transform = locale.strxfrm

    def _fallback_key(path: str):
        name = os.path.basename(path)
        return (locale_transform(name.casefold()), natural_key(path))

    return _fallback_key


windows_logical_key = _create_windows_logical_key()
