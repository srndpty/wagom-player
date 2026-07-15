from dataclasses import dataclass
from typing import Any, Optional

from PyQt5 import QtCore


@dataclass
class PlayerSettings:
    volume: int = 80
    geometry: Optional[QtCore.QByteArray] = None
    maximized: bool = False
    repeat_enabled: bool = False
    preferred_audio_language: str = "ja"
    subtitle_enabled: bool = False
    preferred_subtitle_language: str = "ja"
    last_directory: str = ""


class SettingsRepository:
    """プレイヤー設定をQSettingsへ保存する境界。"""

    def __init__(self, settings: Optional[QtCore.QSettings] = None):
        self._settings = settings if settings is not None else QtCore.QSettings()

    def load(self) -> PlayerSettings:
        return PlayerSettings(
            volume=self._bounded_int("volume", 80, 0, 100),
            geometry=self._settings.value("geometry"),
            maximized=bool(self._settings.value("isMaximized", False, type=bool)),
            repeat_enabled=bool(self._settings.value("repeat", False, type=bool)),
            preferred_audio_language=str(
                self._settings.value("preferred_audio_language", "ja") or "ja"
            ),
            subtitle_enabled=bool(self._settings.value("subtitle_enabled", False, type=bool)),
            preferred_subtitle_language=str(
                self._settings.value("preferred_subtitle_language", "ja") or "ja"
            ),
            last_directory=str(self._settings.value("last_dir", "") or ""),
        )

    def save(self, values: PlayerSettings) -> None:
        self.set_value("volume", values.volume)
        if values.geometry is not None:
            self.set_value("geometry", values.geometry)
        self.set_value("isMaximized", values.maximized)
        self.set_value("repeat", values.repeat_enabled)
        self.set_value("preferred_audio_language", values.preferred_audio_language)
        self.set_value("subtitle_enabled", values.subtitle_enabled)
        self.set_value("preferred_subtitle_language", values.preferred_subtitle_language)
        self.set_value("last_dir", values.last_directory)

    def value(self, key: str, default: Any = None, **kwargs: Any) -> Any:
        return self._settings.value(key, default, **kwargs)

    def set_value(self, key: str, value: Any) -> None:
        self._settings.setValue(key, value)

    def _bounded_int(self, key: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(self._settings.value(key, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))
