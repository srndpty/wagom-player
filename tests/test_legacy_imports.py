import importlib


def test_legacy_main_window_import_exports_video_player():
    legacy = importlib.import_module("wagom_player.main_window")
    modern = importlib.import_module("wagom_player.ui.main_window")

    assert legacy.VideoPlayer is modern.VideoPlayer


def test_legacy_file_actions_import_exports_same_symbols():
    legacy = importlib.import_module("wagom_player.file_actions")
    modern = importlib.import_module("wagom_player.application.file_actions")

    assert legacy.move_file_to_subfolder is modern.move_file_to_subfolder
    assert legacy.TargetFileExistsError is modern.TargetFileExistsError
