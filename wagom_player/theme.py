import os
import sys
from PyQt5 import QtCore, QtGui, QtWidgets

try:
    # SVGアイコンの読み込み安定化
    from PyQt5 import QtSvg  # noqa: F401
except Exception:
    QtSvg = None  # type: ignore


def apply_dark_theme(app: QtWidgets.QApplication) -> None:
    app.setStyle("Fusion")

    palette = QtGui.QPalette()
    base = QtGui.QColor(53, 53, 53)
    alt = QtGui.QColor(45, 45, 45)
    text = QtGui.QColor(220, 220, 220)
    hl = QtGui.QColor(0, 120, 215)

    palette.setColor(QtGui.QPalette.Window, base)
    palette.setColor(QtGui.QPalette.WindowText, text)
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor(35, 35, 35))
    palette.setColor(QtGui.QPalette.AlternateBase, alt)
    palette.setColor(QtGui.QPalette.ToolTipBase, alt)
    palette.setColor(QtGui.QPalette.ToolTipText, text)
    palette.setColor(QtGui.QPalette.Text, text)
    palette.setColor(QtGui.QPalette.Button, alt)
    palette.setColor(QtGui.QPalette.ButtonText, text)
    palette.setColor(QtGui.QPalette.BrightText, QtCore.Qt.red)
    palette.setColor(QtGui.QPalette.Link, hl)
    palette.setColor(QtGui.QPalette.Highlight, hl)
    palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(255, 255, 255))
    app.setPalette(palette)

    app.setStyleSheet(
        """
        QToolTip { color: #e6e6e6; background: #2a2a2a; border: 1px solid #3f3f3f; }
        QSlider::groove:horizontal { background: #3a3a3a; height: 6px; border-radius: 3px; }
        QSlider::sub-page:horizontal { background: #0078d7; height: 6px; border-radius: 3px; }
        QSlider::add-page:horizontal { background: #2a2a2a; height: 6px; border-radius: 3px; }
        QSlider::handle:horizontal { background: #1e90ff; width: 14px; margin: -6px 0; border-radius: 7px; }
        QMenuBar { background: #2d2d2d; color: #e6e6e6; }
        QMenuBar::item:selected { background: #3a3a3a; }
        QMenu { background: #2d2d2d; color: #e6e6e6; }
        QMenu::item:selected { background: #3a3a3a; }
        QPushButton { background: #2d2d2d; color: #e6e6e6; border: 1px solid #3f3f3f; padding: 4px 10px; }
        QPushButton:hover { background: #353535; }
        QPushButton:pressed { background: #2a2a2a; }
        QLabel { color: #e6e6e6; }
        QStatusBar { background: #2d2d2d; color: #e6e6e6; }
        """
    )


def resource_path(*parts: str) -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    return (
        os.path.join(os.path.dirname(base), *parts)
        if parts and parts[0] == "resources"
        else os.path.join(base, *parts)
    )


def apply_app_icon(app: QtWidgets.QApplication) -> QtGui.QIcon:
    icon_path = resource_path("resources", "icons", "app.svg")
    icon = QtGui.QIcon(icon_path)
    app.setWindowIcon(icon)
    return icon


def apply_windows_app_user_model_id(app_id: str = "wagom-player") -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass
