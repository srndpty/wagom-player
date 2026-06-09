import ctypes
import sys

from .. import diagnostics


def apply_windows_dark_titlebar(hwnd: int) -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        dwmapi = ctypes.windll.dwmapi
        value = ctypes.c_int(1)
        for attr in (20, 19):
            try:
                dwmapi.DwmSetWindowAttribute(
                    ctypes.c_void_p(hwnd),
                    ctypes.c_int(attr),
                    ctypes.byref(value),
                    ctypes.sizeof(value),
                )
            except Exception as e:
                diagnostics.record_exception("apply_windows_dark_titlebar_attribute", e, attr=attr)
    except Exception as e:
        diagnostics.record_exception("apply_windows_dark_titlebar", e)
