from PyQt5 import QtCore, QtGui, QtWidgets


class SeekSlider(QtWidgets.QSlider):
    """クリック位置ジャンプ + ドラッグ追従するスライダ"""

    clickedValue = QtCore.pyqtSignal(int)

    def _pos_to_value(self, event: QtGui.QMouseEvent) -> int:
        if self.orientation() == QtCore.Qt.Horizontal:
            pos = event.pos().x()
            span = max(1, self.width())
        else:
            pos = self.height() - event.pos().y()
            span = max(1, self.height())
        rng = self.maximum() - self.minimum()
        val = self.minimum() + int(rng * pos / span)
        return max(self.minimum(), min(self.maximum(), val))

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.LeftButton:
            val = self._pos_to_value(event)
            self.setSliderDown(True)
            self.setValue(val)
            try:
                self.sliderPressed.emit()
                self.sliderMoved.emit(val)
            except Exception:
                pass
            self.clickedValue.emit(val)
            event.accept(); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.buttons() & QtCore.Qt.LeftButton and self.isSliderDown():
            val = self._pos_to_value(event)
            if val != self.value():
                self.setValue(val)
                try:
                    self.sliderMoved.emit(val)
                except Exception:
                    pass
            event.accept(); return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.LeftButton and self.isSliderDown():
            self.setSliderDown(False)
            try:
                self.sliderReleased.emit()
            except Exception:
                pass
            event.accept(); return
        super().mouseReleaseEvent(event)

