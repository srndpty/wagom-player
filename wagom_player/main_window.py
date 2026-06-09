import sys

from .ui import main_window as _main_window

sys.modules[__name__] = _main_window
