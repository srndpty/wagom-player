import os
import sys
from typing import List

from PyQt5 import QtWidgets

from wagom_player.theme import apply_dark_theme, apply_app_icon, apply_windows_app_user_model_id
from wagom_player.main_window import VideoPlayer


def main(argv: List[str]) -> int:
    app = QtWidgets.QApplication(argv)
    apply_dark_theme(app)
    apply_windows_app_user_model_id("wagom-player")
    icon = apply_app_icon(app)

    files = [a for a in argv[1:] if os.path.exists(a)]
    w = VideoPlayer(files=files)
    w.setWindowIcon(icon)
    w.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main(sys.argv))

