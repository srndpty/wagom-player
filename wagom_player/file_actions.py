import sys

from .application import file_actions as _file_actions

sys.modules[__name__] = _file_actions
