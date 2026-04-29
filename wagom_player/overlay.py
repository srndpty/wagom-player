from PyQt5 import QtCore, QtWidgets


class OverlayLabel:
    def __init__(self, window: QtWidgets.QWidget, video_frame: QtWidgets.QWidget):
        self.window = window
        self.video_frame = video_frame
        self.label = QtWidgets.QLabel(window)
        self.label.setWindowFlags(
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.Tool
            | QtCore.Qt.WindowStaysOnTopHint
        )
        self.label.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.label.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        self.label.setStyleSheet(
            """
            background-color: transparent;
            border: none;
            color: white;
            font-size: 48px;
            font-weight: bold;
            padding: 10px;
            text-shadow:
                2px 0px 3px #000, -2px 0px 3px #000,
                0px 2px 3px #000, 0px -2px 3px #000,
                1px 1px 3px #000, -1px -1px 3px #000,
                1px -1px 3px #000, -1px 1px 3px #000;
        """
        )
        self.label.hide()

        self.timer = QtCore.QTimer(window)
        self.timer.setSingleShot(True)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self.label.hide)

    def show(self, text: str, duration_ms: int = 1500) -> None:
        self.label.setText(text)
        self.update_geometry()
        self.label.show()
        self.label.raise_()
        self.timer.stop()
        self.timer.setInterval(duration_ms)
        self.timer.start()

    def hide(self) -> None:
        self.label.hide()

    def update_geometry(self) -> None:
        if not self.video_frame.isVisible():
            return

        global_pos = self.video_frame.mapToGlobal(QtCore.QPoint(0, 0))
        frame_size = self.video_frame.size()
        self.label.setGeometry(
            global_pos.x(),
            global_pos.y(),
            frame_size.width(),
            frame_size.height(),
        )

    def resize_to_frame_rect(self) -> None:
        self.label.setGeometry(self.video_frame.rect())
