from typing import Any

from PyQt5 import QtCore


class SettingsStore:
    """Typed boundary around QSettings while preserving access to the raw object."""

    def __init__(self, settings: QtCore.QSettings):
        self.settings = settings

    def volume(self, default: int = 80) -> int:
        try:
            value = int(self.settings.value("volume", default))
        except Exception:
            value = default
        return max(0, min(100, value))

    def repeat_enabled(self, default: bool = False) -> bool:
        return bool(self.settings.value("repeat", default, type=bool))

    def value(self, key: str, default: Any = None, **kwargs: Any) -> Any:
        return self.settings.value(key, default, **kwargs)

    def set_value(self, key: str, value: Any) -> None:
        self.settings.setValue(key, value)
