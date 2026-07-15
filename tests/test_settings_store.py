from PyQt5 import QtCore

from wagom_player.infrastructure.settings_store import PlayerSettings, SettingsRepository


def test_settings_repository_round_trip(qapp):
    raw = QtCore.QSettings("wagom-player-tests", "settings-round-trip")
    raw.clear()
    repository = SettingsRepository(raw)
    expected = PlayerSettings(
        volume=42,
        geometry=QtCore.QByteArray(b"geometry"),
        maximized=True,
        repeat_enabled=True,
        preferred_audio_language="en",
        subtitle_enabled=True,
        preferred_subtitle_language="ja",
        last_directory="C:/videos",
    )

    repository.save(expected)

    assert repository.load() == expected
    raw.clear()


def test_settings_repository_recovers_invalid_volume(qapp):
    raw = QtCore.QSettings("wagom-player-tests", "settings-invalid-volume")
    raw.setValue("volume", "invalid")

    assert SettingsRepository(raw).load().volume == 80
    raw.clear()
