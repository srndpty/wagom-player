from PyQt5 import QtCore, QtGui, QtWidgets

from wagom_player.dialogs import MetadataDialog, ShortcutListDialog
from wagom_player.overlay import OverlayLabel
from wagom_player.seek_slider import SeekSlider


def _mouse_event(event_type, pos, button=QtCore.Qt.LeftButton, buttons=QtCore.Qt.LeftButton):
    return QtGui.QMouseEvent(
        event_type,
        pos,
        button,
        buttons,
        QtCore.Qt.NoModifier,
    )


def test_metadata_dialog_copy_to_clipboard(qapp):
    dialog = MetadataDialog("name: movie.mp4")

    dialog._copy_to_clipboard()

    assert QtWidgets.QApplication.clipboard().text() == "name: movie.mp4"
    assert dialog.copy_button.text() == "コピーしました！"


def test_shortcut_list_dialog_populates_table(qapp):
    dialog = ShortcutListDialog([("Space", "再生", "基本"), ("M", "ミュート", "音量")])
    table = dialog.findChild(QtWidgets.QTableWidget)

    assert table.rowCount() == 2
    assert table.columnCount() == 3
    assert table.item(0, 0).text() == "Space"
    assert not table.item(0, 0).flags() & QtCore.Qt.ItemIsEditable


def test_overlay_label_show_hide_and_geometry(qapp):
    window = QtWidgets.QWidget()
    frame = QtWidgets.QFrame(window)
    frame.setGeometry(10, 20, 200, 100)
    frame.show()
    overlay = OverlayLabel(window, frame)

    overlay.show("12:34", duration_ms=50)
    assert overlay.label.text() == "12:34"
    assert overlay.label.isVisible()
    assert overlay.timer.interval() == 50

    overlay.resize_to_frame_rect()
    assert overlay.label.geometry() == frame.rect()

    overlay.hide()
    assert not overlay.label.isVisible()


def test_overlay_geometry_ignores_hidden_frame(qapp):
    window = QtWidgets.QWidget()
    frame = QtWidgets.QFrame(window)
    overlay = OverlayLabel(window, frame)
    overlay.label.setGeometry(1, 2, 3, 4)

    overlay.update_geometry()

    assert overlay.label.geometry() == QtCore.QRect(1, 2, 3, 4)


def test_seek_slider_mouse_events_emit_values(qapp):
    slider = SeekSlider(QtCore.Qt.Horizontal)
    slider.resize(100, 20)
    slider.setRange(0, 1000)
    clicked = []
    moved = []
    released = []
    slider.clickedValue.connect(clicked.append)
    slider.sliderMoved.connect(moved.append)
    slider.sliderReleased.connect(lambda: released.append(True))

    slider.mousePressEvent(_mouse_event(QtCore.QEvent.MouseButtonPress, QtCore.QPointF(25, 10)))
    slider.mouseMoveEvent(_mouse_event(QtCore.QEvent.MouseMove, QtCore.QPointF(75, 10)))
    slider.mouseReleaseEvent(
        _mouse_event(
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QPointF(75, 10),
            buttons=QtCore.Qt.NoButton,
        )
    )

    assert clicked == [250]
    assert moved[-1] == 750
    assert released
    assert slider.value() == 750


def test_seek_slider_vertical_position_is_clamped(qapp):
    slider = SeekSlider(QtCore.Qt.Vertical)
    slider.resize(20, 100)
    slider.setRange(10, 110)

    value = slider._pos_to_value(
        _mouse_event(QtCore.QEvent.MouseButtonPress, QtCore.QPointF(10, -50))
    )

    assert value == 110


def test_seek_slider_paint_event_handles_empty_and_ticked_ranges(qapp):
    slider = SeekSlider(QtCore.Qt.Horizontal)
    slider.resize(240, 24)
    slider.setRange(0, 0)
    slider.show()
    qapp.processEvents()

    image = QtGui.QImage(slider.size(), QtGui.QImage.Format_ARGB32)
    image.fill(QtCore.Qt.transparent)
    slider.render(image)

    slider.setRange(0, 180_000)
    slider.render(image)

    assert image.size() == slider.size()
