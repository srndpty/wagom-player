import os

import pytest

from wagom_player import logger


def _import_qt_theme_or_skip():
    QtGui = pytest.importorskip("PyQt5.QtGui", exc_type=ImportError)
    QtWidgets = pytest.importorskip("PyQt5.QtWidgets", exc_type=ImportError)
    from wagom_player import theme

    return QtGui, QtWidgets, theme


def test_logs_dir_uses_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert logger.logs_dir() == os.path.join(str(tmp_path), "wagom-player", "logs")


def test_configure_session_log_and_log_message_write_files(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(logger, "_session_log_path", None)

    logger.configure_session_log("abc")
    logger.log_message("hello")

    log_dir = tmp_path / "wagom-player" / "logs"
    assert (log_dir / "last-run.txt").read_text(encoding="utf-8").endswith("hello\n")
    assert (log_dir / "session-abc.txt").read_text(encoding="utf-8").endswith("hello\n")


def test_configure_session_log_is_best_effort(monkeypatch):
    monkeypatch.setattr(logger, "logs_dir", lambda: "")
    monkeypatch.setattr(logger, "_session_log_path", "old")

    logger.configure_session_log("ignored")

    assert logger._session_log_path == "old"


def test_log_message_is_best_effort(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    def fail_open(*args, **kwargs):
        raise OSError("no write")

    monkeypatch.setattr("builtins.open", fail_open)

    logger.log_message("ignored")


def test_resource_path_selects_package_or_project_resource_root():
    _QtGui, _QtWidgets, theme = _import_qt_theme_or_skip()

    package_path = theme.resource_path("icons", "play.svg")
    resource_path = theme.resource_path("resources", "icons", "play.svg")

    assert package_path.endswith(os.path.join("wagom_player", "icons", "play.svg"))
    assert resource_path.endswith(os.path.join("resources", "icons", "play.svg"))


def test_apply_dark_theme_and_app_icon(qapp):
    QtGui, QtWidgets, theme = _import_qt_theme_or_skip()

    theme.apply_dark_theme(qapp)
    icon = theme.apply_app_icon(qapp)

    assert qapp.palette().color(QtGui.QPalette.Highlight) == QtGui.QColor(0, 120, 215)
    assert "QToolTip" in qapp.styleSheet()
    assert not icon.isNull()
    assert isinstance(QtWidgets.QApplication.windowIcon(), QtGui.QIcon)


def test_apply_windows_app_user_model_id_noops_off_windows(monkeypatch):
    _QtGui, _QtWidgets, theme = _import_qt_theme_or_skip()
    monkeypatch.setattr(theme.sys, "platform", "linux")

    theme.apply_windows_app_user_model_id("test-id")
